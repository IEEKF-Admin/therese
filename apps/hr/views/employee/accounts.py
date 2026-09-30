"""Systemadmin overview of external accounts / registrations per employee."""

from datetime import date

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch
from django.shortcuts import render

from apps.accounts.permissions import user_is_systemadmin
from apps.hr.models import Contract, Employee, EmployeeExternalAccount
from apps.hr.provisioning import account_status_by_kind, employee_is_active_for_provisioning
from apps.hr.wordpress import (
    configured_sites,
    employee_wordpress_states,
    wordpress_position_choices,
)


@login_required
def employee_accounts(request):
    if not user_is_systemadmin(request.user):
        raise PermissionDenied

    today = date.today()
    employees = list(
        Employee.objects.visible().select_related('user', 'room__building').prefetch_related(
            Prefetch(
                'contracts',
                queryset=Contract.objects.order_by('valid_from', 'pk'),
            ),
            'external_accounts',
            'workgroups',
            'wordpress_enrollments',
        ).order_by('last_name', 'first_name')
    )
    wp_sites = configured_sites()
    wp_positions = wordpress_position_choices()
    wp_payloads = {}
    kinds = [
        {'kind': kind, 'label': EmployeeExternalAccount.Kind(kind).label}
        for kind in EmployeeExternalAccount.TAB_KINDS
    ]
    rows = []
    for employee in employees:
        by_kind = account_status_by_kind(employee)
        cells = []
        for item in kinds:
            account = by_kind.get(item['kind'])
            identifier = ''
            lists = []
            if item['kind'] == EmployeeExternalAccount.Kind.GOOGLE_CALENDAR:
                identifier = (employee.google_account or '').strip()
                if not identifier and account is not None:
                    identifier = account.identifier or ''
            elif item['kind'] == EmployeeExternalAccount.Kind.SYMPA:
                identifier = (employee.email_professional or '').strip()
                if not identifier and account is not None:
                    identifier = account.identifier or ''
                if account is not None:
                    lists = list(account.lists or [])
            elif account is not None:
                identifier = account.identifier or ''
            if account is None and not identifier:
                status = 'none'
                label = '—'
                detail = ''
            elif account is None:
                status = 'missing'
                label = 'Not shared'
                detail = ''
            else:
                status = account.status
                label = account.get_status_display()
                detail = account.detail
            cells.append({
                'kind': item['kind'],
                'identifier': identifier,
                'status': status,
                'label': label,
                'detail': detail,
                'lists': lists,
            })
        wp_cells = employee_wordpress_states(employee, wp_sites)
        for state in wp_cells:
            if state['action'] in ('add', 'update'):
                wp_payloads[f'{employee.pk}:{state["site_id"]}'] = {
                    'employee': employee.pk,
                    'site': state['site_id'],
                    'site_name': state['site_name'],
                    'action': state['action'],
                    'prefill': state['prefill'],
                    'has_picture': state['has_picture'],
                    'picture_url': state['picture_url'],
                }
        rows.append({
            'employee': employee,
            'is_active': employee_is_active_for_provisioning(employee, today),
            'cells': cells,
            'wp_cells': wp_cells,
            'wp_marked': any(cell['marked'] for cell in wp_cells),
        })
    return render(request, 'hr/employee_accounts.html', {
        'rows': rows,
        'kinds': kinds,
        'wp_sites': wp_sites,
        'wp_positions': wp_positions,
        'wp_payloads': wp_payloads,
        'table_colspan': 2 + len(kinds) + len(wp_sites),
        'user_groups': list(request.user.groups.values_list('name', flat=True)),
    })
