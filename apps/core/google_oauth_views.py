"""Test connection and bulk sync for Google Calendar sharing."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts.permissions import user_can_edit_global_settings
from apps.core.google_calendar import (
    GoogleCalendarError,
    probe_calendar_connection,
    service_account_configured,
    service_account_email,
)
from apps.core.models import GlobalSetting


def _integrations_redirect():
    return redirect(reverse('core_settings:global_settings') + '?tab=integrations')


def _require_settings_admin(user):
    if not user_can_edit_global_settings(user):
        raise PermissionDenied


@login_required
@require_POST
def google_calendar_test(request):
    _require_settings_admin(request.user)
    setting = GlobalSetting.get_solo()
    if not service_account_configured(setting):
        messages.error(request, 'Save a Google service account JSON key first.')
        return _integrations_redirect()
    if not (setting.google_calendar_id or '').strip():
        messages.error(request, 'Set a Google Calendar ID first.')
        return _integrations_redirect()
    try:
        info = probe_calendar_connection(setting)
    except GoogleCalendarError as exc:
        messages.error(request, f'Calendar connection failed: {exc}')
        return _integrations_redirect()
    label = info.get('summary') or info.get('id') or setting.google_calendar_id
    email = (info.get('email') or service_account_email(setting) or '').strip()
    if email:
        messages.success(request, f'Calendar connection OK: {label} (as {email}).')
    else:
        messages.success(request, f'Calendar connection OK: {label}.')
    return _integrations_redirect()


@login_required
@require_POST
def google_calendar_sync_all(request):
    _require_settings_admin(request.user)
    setting = GlobalSetting.get_solo()
    if not setting.google_calendar_enabled:
        messages.error(request, 'Enable Google Calendar sharing before syncing.')
        return _integrations_redirect()
    if not service_account_configured(setting):
        messages.error(request, 'Save a Google service account JSON key first.')
        return _integrations_redirect()
    if not (setting.google_calendar_id or '').strip():
        messages.error(request, 'Set a Google Calendar ID first.')
        return _integrations_redirect()
    from apps.hr.provisioning import sync_all_google_calendars

    ok, errors, skipped = sync_all_google_calendars()
    messages.success(
        request,
        f'Calendar access updated: {ok} shared/removed, {skipped} skipped, {errors} error(s).',
    )
    return _integrations_redirect()
