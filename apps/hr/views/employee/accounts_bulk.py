"""Bulk add/remove of calendar, Sympa, and WordPress from the accounts tab."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts.permissions import user_is_systemadmin
from apps.core.wordpress import WordPressError
from apps.hr.models import Employee
from apps.hr.provisioning import (
    enroll_employee_google_calendar,
    enroll_employee_sympa,
    unenroll_employee_google_calendar,
    unenroll_employee_sympa,
)
from apps.hr.wordpress import (
    WP_QUEUE_SESSION,
    configured_sites,
    employee_wordpress_states,
    unpublish_employee_from_site,
)


def _accounts_redirect(request):
    url = reverse('hr:employee_accounts')
    query = (request.POST.get('q') or '').strip()
    if query:
        from urllib.parse import urlencode
        url = f'{url}?{urlencode({"q": query})}'
    return redirect(url)


def _selected_employees(request):
    ids = []
    for raw in request.POST.getlist('selected_ids'):
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    if not ids:
        return []
    found = {
        employee.pk: employee
        for employee in Employee.objects.visible().select_related(
            'room__building',
        ).prefetch_related(
            'contracts',
            'external_accounts',
            'workgroups',
            'wordpress_enrollments',
        ).filter(pk__in=ids)
    }
    return [found[pk] for pk in ids if pk in found]


def _summarize(request, *, added=0, removed=0, skipped=0, errors=0, noun=''):
    parts = []
    if added:
        parts.append(f'Added {added}.')
    if removed:
        parts.append(f'Removed {removed}.')
    if skipped:
        parts.append(f'Skipped {skipped}.')
    if errors:
        parts.append(f'{errors} failed.')
    if not parts:
        messages.info(request, f'No {noun} changes for the selection.')
        return
    text = ' '.join(parts)
    if errors:
        messages.error(request, text)
    else:
        messages.success(request, text)


@login_required
@require_POST
def employee_accounts_bulk(request):
    if not user_is_systemadmin(request.user):
        raise PermissionDenied
    action = (request.POST.get('action') or '').strip()
    if action == 'website_queue_cancel':
        request.session.pop(WP_QUEUE_SESSION, None)
        return _accounts_redirect(request)

    employees = _selected_employees(request)
    if not employees:
        messages.info(request, 'Select at least one employee.')
        return _accounts_redirect(request)

    if action == 'calendar_add':
        added = skipped = errors = 0
        for employee in employees:
            result = enroll_employee_google_calendar(employee)
            if result == 'active':
                added += 1
            elif result == 'error':
                errors += 1
            else:
                skipped += 1
        _summarize(request, added=added, skipped=skipped, errors=errors, noun='calendar')
    elif action == 'calendar_remove':
        removed = skipped = errors = 0
        for employee in employees:
            result = unenroll_employee_google_calendar(employee)
            if result == 'removed':
                removed += 1
            elif result == 'error':
                errors += 1
            else:
                skipped += 1
        _summarize(request, removed=removed, skipped=skipped, errors=errors, noun='calendar')
    elif action == 'sympa_add':
        added = skipped = errors = 0
        for employee in employees:
            result = enroll_employee_sympa(employee)
            if result == 'active':
                added += 1
            elif result == 'error':
                errors += 1
            else:
                skipped += 1
        _summarize(request, added=added, skipped=skipped, errors=errors, noun='Sympa')
    elif action == 'sympa_remove':
        removed = skipped = errors = 0
        for employee in employees:
            result = unenroll_employee_sympa(employee)
            if result == 'removed':
                removed += 1
            elif result == 'error':
                errors += 1
            else:
                skipped += 1
        _summarize(request, removed=removed, skipped=skipped, errors=errors, noun='Sympa')
    elif action == 'website_add':
        sites = configured_sites()
        queue = []
        for employee in employees:
            for state in employee_wordpress_states(employee, sites):
                if state['action'] in ('add', 'update'):
                    queue.append({
                        'employee': employee.pk,
                        'site': state['site_id'],
                        'site_name': state['site_name'],
                        'action': state['action'],
                        'name': f'{employee.last_name}, {employee.first_name}',
                    })
        if not queue:
            messages.info(request, 'None of the selected employees need to be added or updated on a website.')
        else:
            request.session[WP_QUEUE_SESSION] = queue
    elif action == 'website_remove':
        sites = configured_sites()
        removed = skipped = errors = 0
        for employee in employees:
            any_published = False
            for state in employee_wordpress_states(employee, sites):
                if not state['published']:
                    continue
                any_published = True
                try:
                    unpublish_employee_from_site(employee, state['site'])
                    removed += 1
                except WordPressError:
                    errors += 1
            if not any_published:
                skipped += 1
        _summarize(request, removed=removed, skipped=skipped, errors=errors, noun='website')
    else:
        messages.error(request, 'Unknown action.')
    return _accounts_redirect(request)
