"""Systemadmin overview of external accounts / registrations per employee."""

from datetime import date

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch
from django.shortcuts import render

from apps.accounts.permissions import user_is_systemadmin
from apps.core.sympa import list_name
from apps.hr.employee_list_helpers import employee_list_search_q
from apps.hr.models import Contract, Employee, EmployeeExternalAccount
from apps.hr.wordpress import (
    WP_QUEUE_SESSION,
    configured_sites,
    employee_wordpress_states,
    wordpress_position_choices,
)
from apps.hr.import_enrollments import known_sympa_lists
from apps.hr.provisioning import account_status_by_kind, employee_is_active_for_provisioning

_STATUS_ICONS = {
    'active': ('fas fa-check-circle', 'is-shared', 'Shared'),
    'removed': ('fas fa-times-circle', 'is-removed', 'Removed'),
    'error': ('fas fa-exclamation-triangle', 'is-error', 'Error'),
    'missing': ('fas fa-minus-circle', 'is-missing', 'Not shared'),
}


@login_required
def employee_accounts(request):
    if not user_is_systemadmin(request.user):
        raise PermissionDenied

    today = date.today()
    search_query = request.GET.get('q', '').strip()
    employees_qs = Employee.objects.visible().select_related(
        'user', 'room__building',
    ).prefetch_related(
        Prefetch(
            'contracts',
            queryset=Contract.objects.order_by('valid_from', 'pk'),
        ),
        'external_accounts',
        'workgroups',
        'wordpress_enrollments',
    ).order_by('last_name', 'first_name')
    if search_query:
        employees_qs = employees_qs.filter(
            employee_list_search_q(search_query, as_of=today)
        ).distinct()
    employees = list(employees_qs)
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
                    lists = [
                        list_name(item) for item in (account.lists or []) if list_name(item)
                    ]
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
            icon, icon_class, icon_label = _STATUS_ICONS.get(status, ('', '', label))
            cells.append({
                'kind': item['kind'],
                'status': status,
                'label': icon_label or label,
                'detail': detail,
                'lists': lists,
                'icon': icon,
                'icon_class': icon_class,
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
        visible_wp = [
            cell for cell in wp_cells
            if cell['assigned'] or cell['published'] or cell['action']
        ]
        rows.append({
            'employee': employee,
            'is_active': employee_is_active_for_provisioning(employee, today),
            'cells': cells,
            'wp_cells': visible_wp,
            'wp_marked': any(cell['marked'] for cell in wp_cells),
        })
    context = {
        'rows': rows,
        'kinds': kinds,
        'wp_sites': wp_sites,
        'wp_positions': wp_positions,
        'wp_payloads': wp_payloads,
        'wp_queue': list(request.session.get(WP_QUEUE_SESSION) or []),
        'search_query': search_query,
        'sympa_lists': known_sympa_lists(),
        'table_colspan': 3 + len(kinds),
        'user_groups': list(request.user.groups.values_list('name', flat=True)),
    }
    if request.GET.get('partial') == '1':
        return render(request, 'hr/_employee_accounts_table_body.html', context)
    return render(request, 'hr/employee_accounts.html', context)
