"""Employee provisioning for external systems (Google Calendar first)."""

from __future__ import annotations

import logging
from datetime import date

from django.db import models, transaction
from django.utils import timezone

from apps.core.google_calendar import (
    GoogleCalendarError,
    get_calendar_client,
    service_account_configured,
)
from apps.core.models import GlobalSetting
from apps.hr.models import Employee, EmployeeExternalAccount

logger = logging.getLogger(__name__)


def normalize_google_email(value: str) -> str:
    return (value or '').strip().lower()


def employee_is_active_for_provisioning(employee: Employee, today: date | None = None) -> bool:
    """Match the active employee list: external, or any contract not yet ended."""
    if getattr(employee, 'is_external', False):
        return True
    today = today or date.today()
    contracts = getattr(employee, '_prefetched_objects_cache', {}).get('contracts')
    if contracts is not None:
        for contract in contracts:
            until = contract.valid_until
            if until is None or until >= today:
                return True
        return False
    return employee.contracts.filter(
        models.Q(valid_until__isnull=True) | models.Q(valid_until__gte=today)
    ).exists()


def employee_should_have_google_calendar(employee: Employee) -> bool:
    if not normalize_google_email(employee.google_account):
        return False
    return employee_is_active_for_provisioning(employee)


def _existing_account(employee: Employee) -> EmployeeExternalAccount | None:
    cached = getattr(employee, '_prefetched_objects_cache', {}).get('external_accounts')
    if cached is not None:
        for row in cached:
            if row.kind == EmployeeExternalAccount.Kind.GOOGLE_CALENDAR:
                return row
        return None
    return employee.external_accounts.filter(
        kind=EmployeeExternalAccount.Kind.GOOGLE_CALENDAR,
    ).first()


def _account(employee: Employee) -> EmployeeExternalAccount:
    existing = _existing_account(employee)
    if existing is not None:
        return existing
    account, _ = EmployeeExternalAccount.objects.get_or_create(
        employee=employee,
        kind=EmployeeExternalAccount.Kind.GOOGLE_CALENDAR,
        defaults={'status': EmployeeExternalAccount.Status.REMOVED},
    )
    return account


def _mark(account: EmployeeExternalAccount, *, status: str, identifier: str = '', detail: str = ''):
    account.status = status
    if identifier:
        account.identifier = identifier
    account.detail = detail
    account.last_synced_at = timezone.now()
    account.save(update_fields=[
        'status', 'identifier', 'detail', 'last_synced_at', 'updated_at',
    ])


def _feature_ready(setting: GlobalSetting | None = None) -> tuple[bool, str]:
    setting = setting or GlobalSetting.get_solo()
    if not setting.google_calendar_enabled:
        return False, 'disabled'
    if not (setting.google_calendar_id or '').strip():
        return False, 'Google Calendar ID is not set.'
    if not service_account_configured(setting):
        return False, 'Google service account JSON is not set.'
    return True, ''


def schedule_google_calendar_sync(employee_id):
    if not employee_id:
        return
    try:
        if not GlobalSetting.get_google_calendar_enabled():
            return
    except Exception:
        return

    def _run():
        try:
            sync_employee_google_calendar(employee_id)
        except Exception:
            logger.exception('Google Calendar sync failed for employee %s', employee_id)

    transaction.on_commit(_run)


def unshare_employee_google_calendar(employee: Employee) -> None:
    """Best-effort ACL removal (employee delete). Runs even if sharing is disabled."""
    setting = GlobalSetting.get_solo()
    email = ''
    try:
        row = employee.external_accounts.filter(
            kind=EmployeeExternalAccount.Kind.GOOGLE_CALENDAR,
        ).first()
        if row is not None:
            email = normalize_google_email(row.identifier)
    except Exception:
        row = None
    if not email:
        email = normalize_google_email(employee.google_account)
    if not email:
        return
    if not service_account_configured(setting):
        return
    if not (setting.google_calendar_id or '').strip():
        return
    try:
        get_calendar_client(setting).unshare(email)
    except GoogleCalendarError:
        logger.exception('Could not unshare Google Calendar for deleted employee %s', employee.pk)


def sync_employee_google_calendar(employee_or_id, *, client=None) -> str:
    """
    Align calendar ACL with the employee.

    Returns 'active', 'removed', 'skipped', 'error', or 'missing'.
    """
    if isinstance(employee_or_id, Employee):
        employee = employee_or_id
    else:
        try:
            employee = Employee.objects.prefetch_related(
                'contracts', 'external_accounts',
            ).get(pk=employee_or_id)
        except Employee.DoesNotExist:
            return 'missing'

    setting = GlobalSetting.get_solo()
    ready, reason = _feature_ready(setting)
    desired = normalize_google_email(employee.google_account)
    should = employee_should_have_google_calendar(employee)
    account = _existing_account(employee)
    previous = normalize_google_email(account.identifier) if account else ''
    if not ready:
        if reason == 'disabled' or (account is None and not should and not desired):
            return 'skipped'
        account = account or _account(employee)
        _mark(
            account,
            status=EmployeeExternalAccount.Status.ERROR,
            identifier=desired or previous,
            detail=reason,
        )
        return 'error'

    if not should and not desired and not previous:
        return 'skipped'
    account = account or _account(employee)
    try:
        client = client or get_calendar_client(setting)
        if previous and previous != desired:
            client.unshare(previous)
        if should and desired:
            client.share(desired)
            _mark(
                account,
                status=EmployeeExternalAccount.Status.ACTIVE,
                identifier=desired,
                detail='',
            )
            return 'active'
        if previous or desired:
            if previous:
                client.unshare(previous)
            elif desired:
                client.unshare(desired)
            _mark(
                account,
                status=EmployeeExternalAccount.Status.REMOVED,
                identifier=previous or desired,
                detail='',
            )
            return 'removed'
        return 'skipped'
    except GoogleCalendarError as exc:
        logger.warning('Google Calendar sync error for employee %s: %s', employee.pk, exc)
        _mark(
            account,
            status=EmployeeExternalAccount.Status.ERROR,
            identifier=desired or previous,
            detail=str(exc),
        )
        return 'error'


def sync_all_google_calendars() -> tuple[int, int, int]:
    ok = errors = skipped = 0
    setting = GlobalSetting.get_solo()
    ready, reason = _feature_ready(setting)
    if not ready:
        if reason == 'disabled':
            return 0, 0, 0
        raise GoogleCalendarError(reason)
    client = get_calendar_client(setting)
    employees = Employee.objects.prefetch_related('contracts', 'external_accounts').order_by(
        'last_name', 'first_name', 'pk',
    )
    for employee in employees:
        result = sync_employee_google_calendar(employee, client=client)
        if result in ('active', 'removed'):
            ok += 1
        elif result == 'error':
            errors += 1
        else:
            skipped += 1
    return ok, errors, skipped


def account_status_by_kind(employee: Employee) -> dict[str, EmployeeExternalAccount]:
    cached = getattr(employee, '_prefetched_objects_cache', {}).get('external_accounts')
    if cached is not None:
        rows = cached
    else:
        rows = employee.external_accounts.all()
    return {row.kind: row for row in rows}
