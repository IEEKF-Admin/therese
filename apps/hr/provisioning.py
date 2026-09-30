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
from apps.core.mail import mail_configured
from apps.core.models import GlobalSetting
from apps.core.sympa import (
    SympaError,
    normalize_list_address,
    quiet_add,
    quiet_delete,
    send_sympa_commands,
    subscriber_gecos,
)
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


def _existing_account(
    employee: Employee,
    kind: str = EmployeeExternalAccount.Kind.GOOGLE_CALENDAR,
) -> EmployeeExternalAccount | None:
    cached = getattr(employee, '_prefetched_objects_cache', {}).get('external_accounts')
    if cached is not None:
        for row in cached:
            if row.kind == kind:
                return row
        return None
    return employee.external_accounts.filter(kind=kind).first()


def _account(
    employee: Employee,
    kind: str = EmployeeExternalAccount.Kind.GOOGLE_CALENDAR,
) -> EmployeeExternalAccount:
    existing = _existing_account(employee, kind)
    if existing is not None:
        return existing
    account, _ = EmployeeExternalAccount.objects.get_or_create(
        employee=employee,
        kind=kind,
        defaults={'status': EmployeeExternalAccount.Status.REMOVED},
    )
    return account


def _mark(
    account: EmployeeExternalAccount,
    *,
    status: str,
    identifier: str = '',
    detail: str = '',
    lists=None,
):
    account.status = status
    if identifier:
        account.identifier = identifier
    account.detail = detail
    account.last_synced_at = timezone.now()
    update_fields = [
        'status', 'identifier', 'detail', 'last_synced_at', 'updated_at',
    ]
    if lists is not None:
        account.lists = lists
        update_fields.append('lists')
    account.save(update_fields=update_fields)


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
                identifier=desired or previous,
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


def employee_should_have_sympa(employee: Employee) -> bool:
    if getattr(employee, 'is_external', False):
        return False
    if not normalize_google_email(employee.email_professional):
        return False
    return employee_is_active_for_provisioning(employee)


def desired_sympa_lists(employee: Employee, setting: GlobalSetting | None = None) -> list[str]:
    setting = setting or GlobalSetting.get_solo()
    found: list[str] = []
    seen: set[str] = set()

    def _add(address: str):
        value = normalize_list_address(address)
        if value and value not in seen:
            seen.add(value)
            found.append(value)

    _add(setting.sympa_institute_list)
    workgroups = getattr(employee, '_prefetched_objects_cache', {}).get('workgroups')
    if workgroups is None:
        workgroups = employee.workgroups.all()
    for workgroup in workgroups:
        _add(getattr(workgroup, 'sympa_list', ''))
    return found


def _sympa_ready(setting: GlobalSetting | None = None) -> tuple[bool, str]:
    setting = setting or GlobalSetting.get_solo()
    if not setting.sympa_enabled:
        return False, 'disabled'
    if not (setting.sympa_robot or '').strip():
        return False, 'Sympa robot address is not set.'
    if not mail_configured(setting):
        return False, 'Outbound email From address is not set.'
    return True, ''


def schedule_sympa_sync(employee_id):
    if not employee_id:
        return
    try:
        if not GlobalSetting.get_sympa_enabled():
            return
    except Exception:
        return

    def _run():
        try:
            sync_employee_sympa(employee_id)
        except Exception:
            logger.exception('Sympa sync failed for employee %s', employee_id)

    transaction.on_commit(_run)


def unsubscribe_employee_sympa(employee: Employee) -> None:
    """Best-effort list removal (employee delete). Runs even if sharing is disabled."""
    setting = GlobalSetting.get_solo()
    email = ''
    lists: list[str] = []
    try:
        row = employee.external_accounts.filter(
            kind=EmployeeExternalAccount.Kind.SYMPA,
        ).first()
        if row is not None:
            email = normalize_google_email(row.identifier)
            lists = list(row.lists or [])
    except Exception:
        row = None
    if not email:
        email = normalize_google_email(employee.email_professional)
    if not lists:
        lists = desired_sympa_lists(employee, setting)
    if not email or not lists:
        return
    if not mail_configured(setting):
        return
    if not (setting.sympa_robot or '').strip():
        return
    try:
        send_sympa_commands(
            [quiet_delete(item, email) for item in lists],
            setting,
        )
    except Exception:
        logger.exception('Could not unsubscribe Sympa for deleted employee %s', employee.pk)


def sync_employee_sympa(employee_or_id, *, send_commands=None) -> str:
    """
    Align Sympa membership with the employee.

    Returns 'active', 'removed', 'skipped', 'error', or 'missing'.
    """
    if isinstance(employee_or_id, Employee):
        employee = employee_or_id
    else:
        try:
            employee = Employee.objects.prefetch_related(
                'contracts', 'external_accounts', 'workgroups',
            ).get(pk=employee_or_id)
        except Employee.DoesNotExist:
            return 'missing'

    setting = GlobalSetting.get_solo()
    ready, reason = _sympa_ready(setting)
    desired = normalize_google_email(employee.email_professional)
    should = employee_should_have_sympa(employee)
    wanted = desired_sympa_lists(employee, setting) if should and desired else []
    account = _existing_account(employee, EmployeeExternalAccount.Kind.SYMPA)
    previous = normalize_google_email(account.identifier) if account else ''
    previous_lists = list(account.lists or []) if account else []
    if not ready:
        if reason == 'disabled' or (account is None and not should and not desired):
            return 'skipped'
        if getattr(employee, 'is_external', False) and not previous:
            return 'skipped'
        account = account or _account(employee, EmployeeExternalAccount.Kind.SYMPA)
        _mark(
            account,
            status=EmployeeExternalAccount.Status.ERROR,
            identifier=desired or previous,
            detail=reason,
            lists=previous_lists,
        )
        return 'error'

    if getattr(employee, 'is_external', False) and not previous:
        return 'skipped'
    if not should and not desired and not previous:
        return 'skipped'
    account = account or _account(employee, EmployeeExternalAccount.Kind.SYMPA)
    commands: list[str] = []
    if previous and previous != desired:
        for item in previous_lists:
            commands.append(quiet_delete(item, previous))
    elif previous:
        for item in previous_lists:
            if item not in wanted:
                commands.append(quiet_delete(item, previous))
    if should and desired:
        for item in wanted:
            if previous != desired or item not in previous_lists:
                commands.append(quiet_add(item, desired, subscriber_gecos(employee)))
    elif previous or desired:
        target = previous or desired
        leftover = previous_lists or desired_sympa_lists(employee, setting)
        for item in leftover:
            commands.append(quiet_delete(item, target))
    try:
        sender = send_commands or send_sympa_commands
        if commands:
            sender(commands, setting)
        if should and desired and wanted:
            _mark(
                account,
                status=EmployeeExternalAccount.Status.ACTIVE,
                identifier=desired,
                detail='',
                lists=wanted,
            )
            return 'active'
        if previous or desired:
            _mark(
                account,
                status=EmployeeExternalAccount.Status.REMOVED,
                identifier=desired or previous,
                detail='',
                lists=[],
            )
            return 'removed'
        return 'skipped'
    except Exception as exc:
        logger.warning('Sympa sync error for employee %s: %s', employee.pk, exc)
        _mark(
            account,
            status=EmployeeExternalAccount.Status.ERROR,
            identifier=desired or previous,
            detail=str(exc),
            lists=previous_lists,
        )
        return 'error'


def sync_all_sympa() -> tuple[int, int, int]:
    ok = errors = skipped = 0
    setting = GlobalSetting.get_solo()
    ready, reason = _sympa_ready(setting)
    if not ready:
        if reason == 'disabled':
            return 0, 0, 0
        raise SympaError(reason)
    employees = Employee.objects.prefetch_related(
        'contracts', 'external_accounts', 'workgroups',
    ).order_by('last_name', 'first_name', 'pk')
    for employee in employees:
        result = sync_employee_sympa(employee)
        if result in ('active', 'removed'):
            ok += 1
        elif result == 'error':
            errors += 1
        else:
            skipped += 1
    return ok, errors, skipped
