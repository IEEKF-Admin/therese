"""Placeholder catalog and substitution for login popups and trigger emails."""

import re
from datetime import date, datetime, timedelta

from django.utils import timezone
from django.utils.html import escape


GROUP_LABELS = {
    'person': 'Person / system',
    'contract': 'Contract',
    'task': 'Task / order',
    'checklist': 'Checklist',
    'chemical': 'Chemicals',
    'lists': 'Lists (several records)',
}

LIST_MAX_ROWS = 50
LIST_PARAM_RE = re.compile(
    r'\{\{\s*(purchase_orders|my_purchase_orders|assigned_tasks|'
    r'personnel_tasks|my_personnel_tasks):([a-z0-9_]+)\s*\}\}'
)

VARIABLES = [
    {'key': 'first_name', 'label': 'First name', 'group': 'person'},
    {'key': 'last_name', 'label': 'Last name', 'group': 'person'},
    {'key': 'full_name', 'label': 'Full name', 'group': 'person'},
    {'key': 'prefix', 'label': 'Prefix / title', 'group': 'person'},
    {'key': 'employee_number', 'label': 'Employee number', 'group': 'person'},
    {'key': 'username', 'label': 'Username', 'group': 'person'},
    {'key': 'email', 'label': 'User email', 'group': 'person'},
    {'key': 'email_professional', 'label': 'Professional email', 'group': 'person'},
    {'key': 'email_private', 'label': 'Private email', 'group': 'person'},
    {'key': 'phone_number', 'label': 'Office phone', 'group': 'person'},
    {'key': 'private_phone_number', 'label': 'Private phone', 'group': 'person'},
    {'key': 'job', 'label': 'Job', 'group': 'person'},
    {'key': 'workgroups', 'label': 'Work groups', 'group': 'person'},
    {'key': 'room', 'label': 'Room', 'group': 'person'},
    {'key': 'today', 'label': 'Today (date)', 'group': 'person'},
    {'key': 'now', 'label': 'Now (date and time)', 'group': 'person'},
    {'key': 'title', 'label': 'Application title (THERESE)', 'group': 'person'},
    {'key': 'contract_end', 'label': 'Contract valid until', 'group': 'contract'},
    {'key': 'contract_start', 'label': 'Contract valid from', 'group': 'contract'},
    {'key': 'pay_scale_group', 'label': 'Pay scale group', 'group': 'contract'},
    {'key': 'experience_level', 'label': 'Experience level', 'group': 'contract'},
    {'key': 'weekly_hours', 'label': 'Weekly hours', 'group': 'contract'},
    {'key': 'job_number', 'label': 'Job number', 'group': 'contract'},
    {'key': 'contract_employee_name', 'label': 'Contract holder name', 'group': 'contract'},
    {'key': 'contract_employee_number', 'label': 'Contract holder number', 'group': 'contract'},
    {'key': 'task_number', 'label': 'Task number', 'group': 'task'},
    {'key': 'task_title', 'label': 'Task title', 'group': 'task'},
    {'key': 'task_type', 'label': 'Task type', 'group': 'task'},
    {'key': 'task_status', 'label': 'Task status', 'group': 'task'},
    {'key': 'task_priority', 'label': 'Task priority', 'group': 'task'},
    {'key': 'task_due_date', 'label': 'Task due date', 'group': 'task'},
    {'key': 'task_assignee', 'label': 'Task assignee', 'group': 'task'},
    {'key': 'task_creator', 'label': 'Task creator', 'group': 'task'},
    {'key': 'supplier', 'label': 'Supplier (purchase order)', 'group': 'task'},
    {'key': 'personnel_employee_name', 'label': 'Personnel task employee name', 'group': 'task'},
    {'key': 'personnel_employee_number', 'label': 'Personnel task employee number', 'group': 'task'},
    {'key': 'personnel_valid_from', 'label': 'Personnel task valid from', 'group': 'task'},
    {'key': 'personnel_valid_until', 'label': 'Personnel task valid until', 'group': 'task'},
    {'key': 'personnel_plan_position', 'label': 'Personnel task plan position', 'group': 'task'},
    {'key': 'personnel_limitation_reason', 'label': 'Personnel task limitation reason', 'group': 'task'},
    {'key': 'recruitment_name', 'label': 'Recruitment candidate name', 'group': 'task'},
    {'key': 'recruitment_email', 'label': 'Recruitment candidate private email', 'group': 'task'},
    {'key': 'recruitment_job', 'label': 'Recruitment job', 'group': 'task'},
    {'key': 'recruitment_working_as', 'label': 'Recruitment working as', 'group': 'task'},
    {'key': 'recruitment_pay_scale_group', 'label': 'Recruitment pay scale group', 'group': 'task'},
    {'key': 'recruitment_weekly_hours', 'label': 'Recruitment weekly hours', 'group': 'task'},
    {'key': 'comment_author', 'label': 'Comment author', 'group': 'task'},
    {'key': 'comment_text', 'label': 'Comment text', 'group': 'task'},
    {'key': 'checklist_name', 'label': 'Checklist name (EN)', 'group': 'checklist'},
    {'key': 'checklist_name_de', 'label': 'Checklist name (DE)', 'group': 'checklist'},
    {'key': 'checklist_status', 'label': 'Checklist status', 'group': 'checklist'},
    {'key': 'checklist_version', 'label': 'Checklist version', 'group': 'checklist'},
    {'key': 'checklist_assigned_at', 'label': 'Checklist assigned at', 'group': 'checklist'},
    {'key': 'chemical_name', 'label': 'Chemical name', 'group': 'chemical'},
    {'key': 'cas_number', 'label': 'CAS number', 'group': 'chemical'},
    {'key': 'product_name', 'label': 'Product / trade name', 'group': 'chemical'},
    {'key': 'chemical_status', 'label': 'Chemical item status', 'group': 'chemical'},
    {'key': 'quantity_range', 'label': 'Quantity range', 'group': 'chemical'},
    {'key': 'work_area', 'label': 'Work area', 'group': 'chemical'},
    {'key': 'storage_room', 'label': 'Storage room', 'group': 'chemical'},
    {'key': 'missing_fields', 'label': 'Missing inventory fields', 'group': 'chemical'},
    {'key': 'delivered_at', 'label': 'Delivered at', 'group': 'chemical'},
    {'key': 'mhd', 'label': 'Best-before date (MHD)', 'group': 'chemical'},
    {
        'key': 'purchase_orders',
        'label': 'Visible unarchived purchase orders',
        'group': 'lists',
    },
    {
        'key': 'purchase_orders_not_yet_processed',
        'label': 'Visible unarchived POs — Not yet processed',
        'group': 'lists',
    },
    {
        'key': 'purchase_orders_in_coordination',
        'label': 'Visible unarchived POs — In coordination',
        'group': 'lists',
    },
    {
        'key': 'purchase_orders_sent_to_administration',
        'label': 'Visible unarchived POs — Sent to administration',
        'group': 'lists',
    },
    {
        'key': 'purchase_orders_delivered',
        'label': 'Visible unarchived POs — Delivered',
        'group': 'lists',
    },
    {
        'key': 'my_purchase_orders',
        'label': 'Purchase orders assigned to you (unarchived)',
        'group': 'lists',
    },
    {
        'key': 'my_purchase_orders_not_yet_processed',
        'label': 'Your assigned unarchived POs — Not yet processed',
        'group': 'lists',
    },
    {
        'key': 'my_purchase_orders_in_coordination',
        'label': 'Your assigned unarchived POs — In coordination',
        'group': 'lists',
    },
    {
        'key': 'my_purchase_orders_sent_to_administration',
        'label': 'Your assigned unarchived POs — Sent to administration',
        'group': 'lists',
    },
    {
        'key': 'assigned_tasks',
        'label': 'Tasks assigned to you (unarchived)',
        'group': 'lists',
    },
    {
        'key': 'personnel_tasks',
        'label': 'Visible unarchived personnel tasks',
        'group': 'lists',
    },
    {
        'key': 'personnel_tasks_not_yet_processed',
        'label': 'Visible unarchived personnel tasks — Not yet processed',
        'group': 'lists',
    },
    {
        'key': 'personnel_tasks_sent_to_hr',
        'label': 'Visible unarchived personnel tasks — Sent to HR',
        'group': 'lists',
    },
    {
        'key': 'personnel_tasks_hr_processing',
        'label': 'Visible unarchived personnel tasks — Processing by HR',
        'group': 'lists',
    },
    {
        'key': 'personnel_tasks_works_council',
        'label': 'Visible unarchived personnel tasks — Works Council',
        'group': 'lists',
    },
    {
        'key': 'personnel_tasks_completed',
        'label': 'Visible unarchived personnel tasks — Completed',
        'group': 'lists',
    },
    {
        'key': 'my_personnel_tasks',
        'label': 'Personnel tasks assigned to you (unarchived)',
        'group': 'lists',
    },
    {
        'key': 'my_personnel_tasks_not_yet_processed',
        'label': 'Your assigned personnel tasks — Not yet processed',
        'group': 'lists',
    },
    {
        'key': 'my_personnel_tasks_sent_to_hr',
        'label': 'Your assigned personnel tasks — Sent to HR',
        'group': 'lists',
    },
    {
        'key': 'my_personnel_tasks_hr_processing',
        'label': 'Your assigned personnel tasks — Processing by HR',
        'group': 'lists',
    },
    {
        'key': 'my_personnel_tasks_works_council',
        'label': 'Your assigned personnel tasks — Works Council',
        'group': 'lists',
    },
    {
        'key': 'my_personnel_tasks_completed',
        'label': 'Your assigned personnel tasks — Completed',
        'group': 'lists',
    },
    {
        'key': 'personnel_tasks_coordination_completed',
        'label': 'Visible unarchived personnel tasks — Coordination completed',
        'group': 'lists',
    },
    {
        'key': 'personnel_tasks_sent_to_administration',
        'label': 'Visible unarchived personnel tasks — Sent to administration',
        'group': 'lists',
    },
    {
        'key': 'personnel_tasks_recruitment_completed',
        'label': 'Visible unarchived personnel tasks — Recruitment completed',
        'group': 'lists',
    },
    {
        'key': 'my_personnel_tasks_coordination_completed',
        'label': 'Your assigned personnel tasks — Coordination completed',
        'group': 'lists',
    },
    {
        'key': 'my_personnel_tasks_sent_to_administration',
        'label': 'Your assigned personnel tasks — Sent to administration',
        'group': 'lists',
    },
    {
        'key': 'my_personnel_tasks_recruitment_completed',
        'label': 'Your assigned personnel tasks — Recruitment completed',
        'group': 'lists',
    },
    {
        'key': 'ending_contracts',
        'label': 'Own contracts ending within 6 months',
        'group': 'lists',
    },
    {
        'key': 'incomplete_chemical_items',
        'label': 'Your incomplete chemical items',
        'group': 'lists',
    },
]

TRIGGER_GROUPS = {
    'first_login': ['person', 'lists'],
    'login_after_datetime': ['person', 'lists'],
    'contract_ending_soon': ['person', 'contract', 'lists'],
    'any_contract_ending_soon': ['person', 'contract', 'lists'],
    'new_task_assigned': ['person', 'task', 'lists'],
    'purchase_order_created': ['person', 'task', 'lists'],
    'personnel_task_created': ['person', 'task', 'lists'],
    'task_status_changed': ['person', 'task', 'lists'],
    'task_comment_on_created_task': ['person', 'task', 'lists'],
    'checklist_assigned': ['person', 'checklist', 'lists'],
    'chemical_item_incomplete': ['person', 'chemical', 'lists'],
    'chemical_item_delivered': ['person', 'chemical', 'lists'],
}


def variable_token(key):
    return '{{ ' + key + ' }}'


def catalog_for_trigger(trigger):
    groups = set(TRIGGER_GROUPS.get(trigger) or ['person'])
    return [var for var in VARIABLES if var['group'] in groups]


def catalog_by_trigger():
    return {
        trigger: [
            {
                'key': var['key'],
                'token': variable_token(var['key']),
                'label': var['label'],
                'group': var['group'],
                'group_label': GROUP_LABELS[var['group']],
            }
            for var in catalog_for_trigger(trigger)
        ]
        for trigger in TRIGGER_GROUPS
    }


def recipient_email(user, employee=None):
    """Professional email first, then the Django user email."""
    if employee is not None:
        professional = (getattr(employee, 'email_professional', '') or '').strip()
        if professional:
            return professional
    return (getattr(user, 'email', '') or '').strip()


def _fmt_date(value):
    if not value:
        return ''
    if isinstance(value, datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        return value.strftime('%d.%m.%Y')
    if isinstance(value, date):
        return value.strftime('%d.%m.%Y')
    return str(value)


def _fmt_datetime(value):
    if not value:
        return ''
    if isinstance(value, datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        return value.strftime('%d.%m.%Y %H:%M')
    if isinstance(value, date):
        return value.strftime('%d.%m.%Y')
    return str(value)


def _person_name(obj):
    if obj is None:
        return ''
    first = getattr(obj, 'first_name', '') or ''
    last = getattr(obj, 'last_name', '') or ''
    full = (first + ' ' + last).strip()
    if full:
        return full
    getter = getattr(obj, 'get_full_name', None)
    if callable(getter):
        return getter() or ''
    return str(obj)


def _choice_display(obj, field):
    getter = getattr(obj, f'get_{field}_display', None)
    if callable(getter):
        return getter() or ''
    return str(getattr(obj, field, '') or '')


class TemplateList:
    """A multi-record value: HTML table in emails, plain lines in popups/subjects."""

    def __init__(self, headers, rows, *, empty_label='None'):
        self.headers = list(headers or [])
        self.rows = [tuple('' if cell is None else str(cell) for cell in row) for row in rows]
        self.empty_label = empty_label

    def as_text(self):
        if not self.rows:
            return self.empty_label
        lines = []
        for row in self.rows:
            line = ' — '.join(cell for cell in row if cell)
            if line:
                lines.append('- ' + line)
        return '\n'.join(lines) if lines else self.empty_label

    def as_html(self):
        if not self.rows:
            return f'<p><em>{escape(self.empty_label)}</em></p>'
        parts = [
            '<table style="border-collapse:collapse;width:100%;font-size:14px;">',
            '<thead><tr>',
        ]
        for header in self.headers:
            parts.append(
                '<th style="text-align:left;border-bottom:1px solid #cbd5e1;'
                f'padding:4px 8px;">{escape(header)}</th>'
            )
        parts.append('</tr></thead><tbody>')
        for row in self.rows:
            parts.append('<tr>')
            for cell in row:
                parts.append(
                    '<td style="padding:4px 8px;border-bottom:1px solid #e2e8f0;'
                    f'vertical-align:top;">{escape(cell)}</td>'
                )
            parts.append('</tr>')
        parts.append('</tbody></table>')
        return ''.join(parts)


def _status_label(status):
    if not status:
        return ''
    from apps.tasks.models import (
        GENERIC_STATUSES,
        PERSONNEL_STATUSES,
        PURCHASE_STATUSES,
        RECRUITMENT_STATUSES,
    )

    mapping = {}
    mapping.update(PURCHASE_STATUSES)
    mapping.update(GENERIC_STATUSES)
    mapping.update(PERSONNEL_STATUSES)
    mapping.update(RECRUITMENT_STATUSES)
    return mapping.get(status, status)


def _unarchived(qs, employee):
    if employee is None:
        return qs
    return qs.exclude(archived_by=employee)


def _po_list(qs):
    headers = ['Number', 'Supplier', 'Status', 'Creator', 'Assignee']
    rows = []
    items = list(qs.select_related('creator', 'assignee').order_by('-created_at')[: LIST_MAX_ROWS + 1])
    extra = max(0, len(items) - LIST_MAX_ROWS)
    for po in items[:LIST_MAX_ROWS]:
        number = (getattr(po, 'task_number', '') or '').strip() or f'#{po.pk}'
        rows.append((
            number,
            getattr(po, 'supplier', '') or '',
            _status_label(po.status) or (po.status or ''),
            _person_name(getattr(po, 'creator', None)),
            _person_name(getattr(po, 'assignee', None)),
        ))
    if extra:
        rows.append((f'… and {extra} more', '', '', '', ''))
    return TemplateList(headers, rows)


def _task_list(qs):
    headers = ['Number', 'Type', 'Title', 'Status', 'Assignee']
    items = list(
        qs.select_related('creator', 'assignee').order_by('-created_at')[: LIST_MAX_ROWS + 1]
    )
    extra = max(0, len(items) - LIST_MAX_ROWS)
    rows = []
    for task in items[:LIST_MAX_ROWS]:
        number = (getattr(task, 'task_number', '') or '').strip() or f'#{task.pk}'
        rows.append((
            number,
            _choice_display(task, 'task_type'),
            getattr(task, 'title', '') or '',
            _status_label(task.status) or (task.status or ''),
            _person_name(getattr(task, 'assignee', None)),
        ))
    if extra:
        rows.append((f'… and {extra} more', '', '', '', ''))
    return TemplateList(headers, rows)


def list_purchase_orders(user, employee, status=None):
    from apps.tasks.utils import get_purchase_orders_queryset

    if user is None:
        return TemplateList(
            ['Number', 'Supplier', 'Status', 'Creator', 'Assignee'],
            [],
        )
    qs = _unarchived(get_purchase_orders_queryset(user), employee)
    if status:
        qs = qs.filter(status=status)
    return _po_list(qs)


def list_my_purchase_orders(employee, status=None):
    from apps.tasks.models import PurchaseOrderTask

    headers = ['Number', 'Supplier', 'Status', 'Creator', 'Assignee']
    if employee is None:
        return TemplateList(headers, [])
    qs = PurchaseOrderTask.objects.filter(assignee=employee)
    qs = _unarchived(qs, employee)
    if status:
        qs = qs.filter(status=status)
    return _po_list(qs)


def list_assigned_tasks(employee, status=None):
    from apps.tasks.models import Task

    headers = ['Number', 'Type', 'Title', 'Status', 'Assignee']
    if employee is None:
        return TemplateList(headers, [])
    qs = Task.objects.filter(assignee=employee)
    qs = _unarchived(qs, employee)
    if status:
        qs = qs.filter(status=status)
    return _task_list(qs)


def list_personnel_tasks(user, employee, status=None):
    from apps.tasks.utils import get_personnel_tasks_queryset

    headers = ['Number', 'Type', 'Title', 'Status', 'Assignee']
    if user is None:
        return TemplateList(headers, [])
    qs = _unarchived(get_personnel_tasks_queryset(user), employee)
    if status:
        qs = qs.filter(status=status)
    return _task_list(qs)


def list_my_personnel_tasks(employee, status=None):
    from apps.tasks.models import PERSONNEL_TASK_TYPES, Task

    headers = ['Number', 'Type', 'Title', 'Status', 'Assignee']
    if employee is None:
        return TemplateList(headers, [])
    qs = Task.objects.filter(assignee=employee, task_type__in=PERSONNEL_TASK_TYPES)
    qs = _unarchived(qs, employee)
    if status:
        qs = qs.filter(status=status)
    return _task_list(qs)


def list_ending_contracts(employee, months=6):
    headers = ['Employee', 'Valid until', 'Pay scale', 'Weekly hours']
    if employee is None:
        return TemplateList(headers, [])
    today = date.today()
    cutoff = today + timedelta(days=max(1, int(months)) * 30)
    contracts = (
        employee.contracts.filter(
            valid_until__isnull=False,
            valid_until__gte=today,
            valid_until__lte=cutoff,
        )
        .select_related('employee')
        .order_by('valid_until')[: LIST_MAX_ROWS + 1]
    )
    items = list(contracts)
    extra = max(0, len(items) - LIST_MAX_ROWS)
    rows = []
    for contract in items[:LIST_MAX_ROWS]:
        rows.append((
            _person_name(contract.employee),
            _fmt_date(contract.valid_until),
            contract.pay_scale_group or '',
            '' if contract.weekly_hours is None else str(contract.weekly_hours),
        ))
    if extra:
        rows.append((f'… and {extra} more', '', '', ''))
    return TemplateList(headers, rows)


def list_incomplete_chemical_items(employee):
    headers = ['CAS', 'Name', 'Product', 'Missing']
    if employee is None:
        return TemplateList(headers, [])
    from apps.chemicals.models import ChemicalItem

    qs = (
        ChemicalItem.objects.filter(ordered_by=employee)
        .exclude(status=ChemicalItem.Status.ARCHIVED)
        .select_related('chemical')
        .order_by('-created_at')
    )
    rows = []
    extra = 0
    for item in qs:
        if not item.is_incomplete:
            continue
        if len(rows) >= LIST_MAX_ROWS:
            extra += 1
            continue
        chemical = item.chemical
        missing = []
        getter = getattr(item, 'missing_info_fields', None)
        if callable(getter):
            missing = getter()
        rows.append((
            getattr(chemical, 'cas_number', '') or '',
            getattr(chemical, 'name', '') or '',
            item.product_name or '',
            ', '.join(missing),
        ))
    if extra:
        rows.append((f'… and {extra} more', '', '', ''))
    return TemplateList(headers, rows)


def resolve_param_list(kind, status, user, employee):
    if kind == 'purchase_orders':
        return list_purchase_orders(user, employee, status=status)
    if kind == 'my_purchase_orders':
        return list_my_purchase_orders(employee, status=status)
    if kind == 'assigned_tasks':
        return list_assigned_tasks(employee, status=status)
    if kind == 'personnel_tasks':
        return list_personnel_tasks(user, employee, status=status)
    if kind == 'my_personnel_tasks':
        return list_my_personnel_tasks(employee, status=status)
    return TemplateList([], [])


def _render_value(value, *, html):
    if isinstance(value, TemplateList):
        return value.as_html() if html else value.as_text()
    rendered = '' if value is None else str(value)
    if html:
        rendered = escape(rendered)
    return rendered


def build_replacement_map(
    user,
    employee=None,
    *,
    contract=None,
    task=None,
    checklist=None,
    chemical_item=None,
    comment=None,
):
    first = getattr(user, 'first_name', '') or ''
    last = getattr(user, 'last_name', '') or ''
    if employee is not None:
        first = first or (employee.first_name or '')
        last = last or (employee.last_name or '')

    full = (first + ' ' + last).strip()
    if not full:
        full = _person_name(employee) or _person_name(user)

    workgroups = ''
    job = ''
    room = ''
    prefix = ''
    emp_no = ''
    email_professional = ''
    email_private = ''
    phone_number = ''
    private_phone_number = ''
    if employee is not None:
        emp_no = getattr(employee, 'employee_number', '') or ''
        prefix = getattr(employee, 'prefix', '') or ''
        email_professional = getattr(employee, 'email_professional', '') or ''
        email_private = getattr(employee, 'email_private', '') or ''
        phone_number = getattr(employee, 'phone_number', '') or ''
        private_phone_number = getattr(employee, 'private_phone_number', '') or ''
        if getattr(employee, 'job_id', None):
            job = str(employee.job)
        if getattr(employee, 'room_id', None):
            room = str(employee.room)
        try:
            workgroups = ', '.join(
                employee.workgroups.order_by('short_name').values_list('short_name', flat=True)
            )
        except Exception:
            workgroups = ''

    now = timezone.localtime()
    values = {
        'first_name': first,
        'last_name': last,
        'full_name': full,
        'prefix': prefix,
        'employee_number': emp_no,
        'username': getattr(user, 'username', '') or '',
        'email': getattr(user, 'email', '') or '',
        'email_professional': email_professional,
        'email_private': email_private,
        'phone_number': phone_number,
        'private_phone_number': private_phone_number,
        'job': job,
        'workgroups': workgroups,
        'room': room,
        'today': now.strftime('%d.%m.%Y'),
        'now': now.strftime('%d.%m.%Y %H:%M'),
        'title': 'THERESE',
        'contract_end': '',
        'contract_start': '',
        'pay_scale_group': '',
        'experience_level': '',
        'weekly_hours': '',
        'job_number': '',
        'contract_employee_name': '',
        'contract_employee_number': '',
        'task_number': '',
        'task_title': '',
        'task_type': '',
        'task_status': '',
        'task_priority': '',
        'task_due_date': '',
        'task_assignee': '',
        'task_creator': '',
        'supplier': '',
        'personnel_employee_name': '',
        'personnel_employee_number': '',
        'personnel_valid_from': '',
        'personnel_valid_until': '',
        'personnel_plan_position': '',
        'personnel_limitation_reason': '',
        'recruitment_name': '',
        'recruitment_email': '',
        'recruitment_job': '',
        'recruitment_working_as': '',
        'recruitment_pay_scale_group': '',
        'recruitment_weekly_hours': '',
        'comment_author': '',
        'comment_text': '',
        'checklist_name': '',
        'checklist_name_de': '',
        'checklist_status': '',
        'checklist_version': '',
        'checklist_assigned_at': '',
        'chemical_name': '',
        'cas_number': '',
        'product_name': '',
        'chemical_status': '',
        'quantity_range': '',
        'work_area': '',
        'storage_room': '',
        'missing_fields': '',
        'delivered_at': '',
        'mhd': '',
    }

    resolved_contract = contract
    if resolved_contract is None and employee is not None:
        resolved_contract = (
            employee.contracts.filter(valid_until__isnull=False).order_by('-valid_until').first()
        )
    if resolved_contract is not None:
        values['contract_end'] = _fmt_date(resolved_contract.valid_until)
        values['contract_start'] = _fmt_date(resolved_contract.valid_from)
        values['pay_scale_group'] = resolved_contract.pay_scale_group or ''
        values['experience_level'] = (
            '' if resolved_contract.experience_level is None else str(resolved_contract.experience_level)
        )
        values['weekly_hours'] = (
            '' if resolved_contract.weekly_hours is None else str(resolved_contract.weekly_hours)
        )
        values['job_number'] = resolved_contract.job_number or ''
        holder = getattr(resolved_contract, 'employee', None)
        values['contract_employee_name'] = _person_name(holder)
        values['contract_employee_number'] = getattr(holder, 'employee_number', '') or ''

    if task is not None:
        values['task_number'] = getattr(task, 'task_number', '') or ''
        values['task_title'] = getattr(task, 'title', '') or ''
        values['task_type'] = _choice_display(task, 'task_type')
        values['task_status'] = getattr(task, 'status', '') or ''
        values['task_priority'] = _choice_display(task, 'priority')
        values['task_due_date'] = _fmt_date(getattr(task, 'due_date', None))
        values['task_assignee'] = _person_name(getattr(task, 'assignee', None))
        values['task_creator'] = _person_name(getattr(task, 'creator', None))
        values['supplier'] = getattr(task, 'supplier', '') or ''
        _fill_personnel_task_values(values, task)

    if comment is not None:
        values['comment_author'] = _person_name(getattr(comment, 'author', None))
        text = (getattr(comment, 'text', '') or '').strip()
        if len(text) > 500:
            text = text[:497] + '...'
        values['comment_text'] = text
        if task is None and getattr(comment, 'task', None) is not None:
            comment_task = comment.task
            values['task_number'] = getattr(comment_task, 'task_number', '') or ''
            values['task_title'] = getattr(comment_task, 'title', '') or ''

    if checklist is not None:
        version = getattr(checklist, 'template_version', None)
        template = getattr(version, 'template', None) if version is not None else None
        values['checklist_name'] = getattr(template, 'name_en', '') or ''
        values['checklist_name_de'] = getattr(template, 'name_de', '') or ''
        values['checklist_status'] = _choice_display(checklist, 'status')
        values['checklist_version'] = getattr(version, 'version_label', '') or ''
        values['checklist_assigned_at'] = _fmt_datetime(getattr(checklist, 'assigned_at', None))

    if chemical_item is not None:
        chemical = getattr(chemical_item, 'chemical', None)
        values['chemical_name'] = getattr(chemical, 'name', '') or ''
        values['cas_number'] = getattr(chemical, 'cas_number', '') or ''
        values['product_name'] = chemical_item.product_name or getattr(chemical, 'name', '') or ''
        values['chemical_status'] = _choice_display(chemical_item, 'status')
        values['quantity_range'] = _choice_display(chemical_item, 'quantity_range')
        values['work_area'] = str(chemical_item.work_area) if chemical_item.work_area_id else ''
        values['storage_room'] = str(chemical_item.storage_room) if chemical_item.storage_room_id else ''
        missing = []
        getter = getattr(chemical_item, 'missing_info_fields', None)
        if callable(getter):
            missing = getter()
        values['missing_fields'] = ', '.join(missing)
        values['delivered_at'] = _fmt_datetime(getattr(chemical_item, 'delivered_at', None))
        values['mhd'] = _fmt_date(getattr(chemical_item, 'mhd', None))

    from apps.tasks.models import PERSONNEL_STATUSES, PURCHASE_STATUSES, RECRUITMENT_STATUSES

    values['purchase_orders'] = list_purchase_orders(user, employee)
    values['my_purchase_orders'] = list_my_purchase_orders(employee)
    values['assigned_tasks'] = list_assigned_tasks(employee)
    values['personnel_tasks'] = list_personnel_tasks(user, employee)
    values['my_personnel_tasks'] = list_my_personnel_tasks(employee)
    values['ending_contracts'] = list_ending_contracts(employee)
    values['incomplete_chemical_items'] = list_incomplete_chemical_items(employee)
    for status_key, _label in PURCHASE_STATUSES:
        values[f'purchase_orders_{status_key}'] = list_purchase_orders(
            user, employee, status=status_key
        )
        values[f'my_purchase_orders_{status_key}'] = list_my_purchase_orders(
            employee, status=status_key
        )
    personnel_status_keys = []
    for status_key, _label in PERSONNEL_STATUSES + RECRUITMENT_STATUSES:
        if status_key in personnel_status_keys:
            continue
        personnel_status_keys.append(status_key)
        values[f'personnel_tasks_{status_key}'] = list_personnel_tasks(
            user, employee, status=status_key
        )
        values[f'my_personnel_tasks_{status_key}'] = list_my_personnel_tasks(
            employee, status=status_key
        )

    return values


def _fill_personnel_task_values(values, task):
    from apps.tasks.models import PERSONNEL_TASK_TYPES

    task_type = getattr(task, 'task_type', '') or ''
    if task_type not in PERSONNEL_TASK_TYPES:
        return
    subject = getattr(task, 'employee', None)
    if subject is not None:
        values['personnel_employee_name'] = _person_name(subject)
        values['personnel_employee_number'] = getattr(subject, 'employee_number', '') or ''
    values['personnel_valid_from'] = _fmt_date(getattr(task, 'valid_from', None))
    values['personnel_valid_until'] = _fmt_date(getattr(task, 'valid_until', None))
    values['personnel_plan_position'] = getattr(task, 'plan_position_number', '') or ''
    reason = (getattr(task, 'limitation_reason', '') or '').strip()
    if len(reason) > 400:
        reason = reason[:397] + '...'
    values['personnel_limitation_reason'] = reason
    if task_type != 'personnel_recruitment':
        return
    first = getattr(task, 'first_name', '') or ''
    last = getattr(task, 'last_name', '') or ''
    candidate = (first + ' ' + last).strip()
    if candidate:
        values['personnel_employee_name'] = candidate
        values['recruitment_name'] = candidate
    values['recruitment_email'] = getattr(task, 'email_private', '') or ''
    job = getattr(task, 'job', None)
    values['recruitment_job'] = str(job) if job else ''
    values['recruitment_working_as'] = getattr(task, 'working_as', '') or ''
    values['recruitment_pay_scale_group'] = getattr(task, 'pay_scale_group', '') or ''
    hours = getattr(task, 'weekly_hours', None)
    values['recruitment_weekly_hours'] = '' if hours is None else str(hours)


def render_placeholders(template, replacements, *, html=False, user=None, employee=None):
    text = template or ''
    keys = sorted(
        (key for key in replacements if not str(key).startswith('_')),
        key=len,
        reverse=True,
    )
    for key in keys:
        rendered = _render_value(replacements[key], html=html)
        for token in (variable_token(key), '{{' + key + '}}'):
            text = text.replace(token, rendered)

    def _param_repl(match):
        kind, status = match.group(1), match.group(2)
        named_key = f'{kind}_{status}'
        if named_key in replacements:
            return _render_value(replacements[named_key], html=html)
        return _render_value(
            resolve_param_list(kind, status, user, employee),
            html=html,
        )

    return LIST_PARAM_RE.sub(_param_repl, text)
