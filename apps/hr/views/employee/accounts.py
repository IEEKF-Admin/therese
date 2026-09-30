"""Systemadmin overview of external accounts / registrations per employee."""

from datetime import date

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch
from django.shortcuts import render

from apps.accounts.permissions import user_is_systemadmin
from apps.hr.models import Contract, Employee, EmployeeExternalAccount
from apps.hr.provisioning import account_status_by_kind, employee_is_active_for_provisioning


@login_required
def employee_accounts(request):
    if not user_is_systemadmin(request.user):
        raise PermissionDenied

    today = date.today()
    employees = list(
        Employee.objects.visible().select_related('user').prefetch_related(
            Prefetch(
                'contracts',
                queryset=Contract.objects.order_by('valid_from', 'pk'),
            ),
            'external_accounts',
        ).order_by('last_name', 'first_name')
    )
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
        rows.append({
            'employee': employee,
            'is_active': employee_is_active_for_provisioning(employee, today),
            'cells': cells,
        })
    return render(request, 'hr/employee_accounts.html', {
        'rows': rows,
        'kinds': kinds,
        'user_groups': list(request.user.groups.values_list('name', flat=True)),
    })
