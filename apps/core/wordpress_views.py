"""Test WordPress THERESE Sync connection from Integrations."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts.permissions import user_can_edit_global_settings
from apps.core.wordpress import WordPressError, probe_wordpress_connection
from apps.hr.models import WordPressSite


def _integrations_redirect():
    return redirect(reverse('core_settings:global_settings') + '?tab=integrations')


@login_required
@require_POST
def wordpress_test(request, pk):
    if not user_can_edit_global_settings(request.user):
        raise PermissionDenied
    site = get_object_or_404(WordPressSite, pk=pk)
    if not site.is_configured():
        messages.error(
            request,
            f'Set URL, WordPress user, and application password for {site.name} first.',
        )
        return _integrations_redirect()
    try:
        info = probe_wordpress_connection(site)
    except WordPressError as exc:
        messages.error(request, f'WordPress connection failed ({site.name}): {exc}')
        return _integrations_redirect()
    post_type = info.get('post_type') or '—'
    messages.success(
        request,
        f'WordPress connection OK: {site.name} (post type {post_type}).',
    )
    return _integrations_redirect()
