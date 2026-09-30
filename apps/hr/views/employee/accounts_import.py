"""Import existing Calendar, WordPress, and Sympa enrollments onto the accounts tab."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_POST

from apps.accounts.permissions import user_is_systemadmin
from apps.core.google_calendar import GoogleCalendarError
from apps.hr.import_enrollments import (
    import_google_calendar,
    import_sympa_csv,
    import_wordpress_sites,
)
from apps.hr.views.employee.accounts_bulk import _accounts_redirect


def _flash_import(request, source: str, result: dict):
    if result.get('empty'):
        messages.info(request, f'No {source} are configured.')
        return
    matched = result.get('matched') or 0
    unmatched = result.get('unmatched') or 0
    errors = result.get('errors') or 0
    parts = []
    if matched:
        parts.append(f'{matched} marked Shared.')
    if unmatched:
        parts.append(f'{unmatched} had no matching employee.')
    if errors:
        parts.append(f'{errors} failed.')
        parts.extend(str(item) for item in (result.get('error_messages') or []) if item)
    if not parts:
        messages.info(request, f'No matching {source} entries found.')
        return
    text = f'Imported {source}: ' + ' '.join(parts)
    if errors:
        messages.error(request, text)
    else:
        messages.success(request, text)


@login_required
@require_POST
def employee_accounts_import_calendar(request):
    if not user_is_systemadmin(request.user):
        raise PermissionDenied
    try:
        result = import_google_calendar()
    except GoogleCalendarError as exc:
        messages.error(request, str(exc))
        return _accounts_redirect(request)
    _flash_import(request, 'Google Calendar', result)
    return _accounts_redirect(request)


@login_required
@require_POST
def employee_accounts_import_websites(request):
    if not user_is_systemadmin(request.user):
        raise PermissionDenied
    result = import_wordpress_sites()
    if result.get('empty'):
        messages.info(request, 'No WordPress sites are configured.')
        return _accounts_redirect(request)
    _flash_import(request, 'WordPress', result)
    return _accounts_redirect(request)


@login_required
@require_POST
def employee_accounts_import_sympa(request):
    if not user_is_systemadmin(request.user):
        raise PermissionDenied
    uploaded = request.FILES.get('csv')
    if not uploaded:
        messages.error(request, 'Choose a CSV file.')
        return _accounts_redirect(request)
    try:
        result = import_sympa_csv(request.POST.get('list_address') or '', uploaded.read())
    except ValueError as exc:
        messages.error(request, str(exc))
        return _accounts_redirect(request)
    _flash_import(request, 'Sympa', result)
    return _accounts_redirect(request)
