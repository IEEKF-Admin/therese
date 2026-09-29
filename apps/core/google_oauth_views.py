"""OAuth connect/disconnect and bulk sync for Google Calendar sharing."""

from __future__ import annotations

import secrets

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts.permissions import user_can_edit_global_settings
from apps.core.google_calendar import (
    GoogleCalendarError,
    exchange_code_for_tokens,
    oauth_authorize_url,
    oauth_configured,
    oauth_redirect_uri,
    probe_calendar_connection,
    revoke_token,
)
from apps.core.models import GlobalSetting

_SESSION_STATE = 'google_calendar_oauth_state'


def _integrations_redirect():
    return redirect(reverse('core_settings:global_settings') + '?tab=integrations')


def _require_settings_admin(user):
    if not user_can_edit_global_settings(user):
        raise PermissionDenied


@login_required
@require_POST
def google_calendar_connect(request):
    _require_settings_admin(request.user)
    if not oauth_configured():
        messages.error(
            request,
            'Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET in .env first.',
        )
        return _integrations_redirect()
    state = secrets.token_urlsafe(32)
    request.session[_SESSION_STATE] = state
    return redirect(oauth_authorize_url(request, state))


@login_required
def google_calendar_callback(request):
    _require_settings_admin(request.user)
    error = (request.GET.get('error') or '').strip()
    if error:
        messages.error(request, f'Google authorization was cancelled ({error}).')
        return _integrations_redirect()
    state = (request.GET.get('state') or '').strip()
    expected = request.session.pop(_SESSION_STATE, '')
    if not state or state != expected:
        messages.error(request, 'OAuth state mismatch. Connect Google Calendar again.')
        return _integrations_redirect()
    code = (request.GET.get('code') or '').strip()
    if not code:
        messages.error(request, 'Google did not return an authorization code.')
        return _integrations_redirect()
    try:
        tokens = exchange_code_for_tokens(code, oauth_redirect_uri(request))
    except GoogleCalendarError as exc:
        messages.error(request, f'Google Calendar connection failed: {exc}')
        return _integrations_redirect()
    refresh = (tokens.get('refresh_token') or '').strip()
    if not refresh:
        messages.error(
            request,
            'Google did not return a refresh token. Remove THERESE from the '
            'Google account permissions and connect again.',
        )
        return _integrations_redirect()
    email = (tokens.get('email') or '').strip()
    setting = GlobalSetting.get_solo()
    setting.google_calendar_refresh_token = refresh
    setting.google_calendar_connected_email = email
    setting.save(update_fields=[
        'google_calendar_refresh_token',
        'google_calendar_connected_email',
        'updated_at',
    ])
    if email:
        messages.success(request, f'Google Calendar connected as {email}.')
    else:
        messages.success(request, 'Google Calendar connected.')
    return _integrations_redirect()


@login_required
@require_POST
def google_calendar_disconnect(request):
    _require_settings_admin(request.user)
    setting = GlobalSetting.get_solo()
    token = (setting.google_calendar_refresh_token or '').strip()
    if token:
        try:
            revoke_token(token)
        except GoogleCalendarError:
            pass
    setting.google_calendar_refresh_token = ''
    setting.google_calendar_connected_email = ''
    setting.save(update_fields=[
        'google_calendar_refresh_token',
        'google_calendar_connected_email',
        'updated_at',
    ])
    messages.success(request, 'Google Calendar disconnected.')
    return _integrations_redirect()


@login_required
@require_POST
def google_calendar_test(request):
    _require_settings_admin(request.user)
    setting = GlobalSetting.get_solo()
    if not (setting.google_calendar_refresh_token or '').strip():
        messages.error(request, 'Connect a Google account first.')
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
    email = (setting.google_calendar_connected_email or '').strip()
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
    if not (setting.google_calendar_refresh_token or '').strip():
        messages.error(request, 'Connect a Google account first.')
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
