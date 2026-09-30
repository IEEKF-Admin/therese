"""Test connection and bulk sync for Sympa mailing lists."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts.permissions import user_can_edit_global_settings
from apps.core.mail import mail_configured
from apps.core.models import GlobalSetting
from apps.core.sympa import SympaError, probe_sympa_connection


def _integrations_redirect():
    return redirect(reverse('core_settings:global_settings') + '?tab=integrations')


def _require_settings_admin(user):
    if not user_can_edit_global_settings(user):
        raise PermissionDenied


@login_required
@require_POST
def sympa_test(request):
    _require_settings_admin(request.user)
    setting = GlobalSetting.get_solo()
    if not (setting.sympa_robot or '').strip():
        messages.error(request, 'Set a Sympa robot address first.')
        return _integrations_redirect()
    if not mail_configured(setting):
        messages.error(request, 'Set a From address first.')
        return _integrations_redirect()
    try:
        probe_sympa_connection(setting)
    except Exception as exc:
        messages.error(request, f'Sympa command mail failed: {exc}')
        return _integrations_redirect()
    messages.success(
        request,
        f'Sent HELP to {setting.sympa_robot}. SMTP accepted the message; '
        'Sympa does not confirm the result here.',
    )
    return _integrations_redirect()


@login_required
@require_POST
def sympa_sync_all(request):
    _require_settings_admin(request.user)
    setting = GlobalSetting.get_solo()
    if not setting.sympa_enabled:
        messages.error(request, 'Enable Sympa mailing lists before syncing.')
        return _integrations_redirect()
    if not (setting.sympa_robot or '').strip():
        messages.error(request, 'Set a Sympa robot address first.')
        return _integrations_redirect()
    if not mail_configured(setting):
        messages.error(request, 'Set a From address first.')
        return _integrations_redirect()
    from apps.hr.provisioning import sync_all_sympa

    try:
        ok, errors, skipped = sync_all_sympa()
    except SympaError as exc:
        messages.error(request, str(exc))
        return _integrations_redirect()
    messages.success(
        request,
        f'Mailing lists updated: {ok} added/removed, {skipped} skipped, {errors} error(s).',
    )
    return _integrations_redirect()
