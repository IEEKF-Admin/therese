"""
Employee list, create, and update views.

Do not remove any existing requirements from this module without explicit instruction.
"""

from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import models
from django.shortcuts import redirect, render
from django.views.generic import CreateView, UpdateView

from ...forms import EmployeeForm
from ...models import Employee
from ..employee_form_helpers import (
    ContractFormSet,
    WorkgroupFormSet,
    build_contract_cards,
    collect_funding_formsets_from_post,
    collect_salary_formsets_from_post,
    funding_prefix_for_existing,
    funding_prefix_for_new,
    salary_prefix_for_existing,
    salary_prefix_for_new,
)
from apps.hr.employee_access import (
    filter_employees_for_user,
    user_can_manage_employee,
    user_can_manage_employees,
    user_can_view_employee_list,
)
from apps.tasks.utils import can_create_employee_from_recruitment
from .common import (
    current_payscales_json,
    employee_document_context,
    finalize_recruitment_task,
    get_recruitment_task,
    recruitment_employee_initial,
    save_employee_with_formsets,
)


@login_required
def phone_list(request):
    """
    Institute phone directory: employees with a soft-open contract today.

    Visible to any logged-in user with an employee profile (sidebar: has_employee).
    Live search is client-side on first/last name.
    """
    if getattr(request.user, 'employee', None) is None and not request.user.is_superuser:
        messages.error(
            request,
            "Phone list is only available for users linked to an employee profile.",
        )
        return redirect('tasks:my_tasks')

    from apps.hr.models import Contract
    from apps.hr.validity import contract_open_on_q

    today = date.today()
    open_employee_ids = (
        Contract.objects.filter(contract_open_on_q(today))
        .values_list('employee_id', flat=True)
        .distinct()
    )
    employees = (
        Employee.objects.filter(pk__in=open_employee_ids)
        .order_by('last_name', 'first_name')
        .only('first_name', 'last_name', 'phone_number', 'email_professional')
    )

    return render(request, 'hr/phone_list.html', {
        'employees': employees,
    })


@login_required
def employee_list(request):
    """List employees visible to the current user (workgroup-scoped unless *all* rights)."""
    user_groups = list(request.user.groups.values_list('name', flat=True))
    if not user_can_view_employee_list(request.user):
        messages.error(request, "You don't have permission to view employees.")
        return redirect('tasks:my_tasks')

    can_manage = user_can_manage_employees(request.user)
    can_create_personnel = (
        request.user.is_superuser
        or request.user.has_perm('tasks.create_personnel_task')
    )
    can_edit_any = can_manage  # row-click edit; object-level checked on update view

    archive_mode = request.GET.get('archive') == '1'
    search_query = request.GET.get('q', '').strip()
    sort_field = request.GET.get('sort', 'last_name')
    sort_dir = request.GET.get('dir', 'asc')
    list_filter = (request.GET.get('filter') or '').strip()

    from apps.hr.employee_list_helpers import (
        annotate_employees_for_list,
        employee_list_search_q,
        employees_queryset_for_list,
    )

    employees = employees_queryset_for_list()
    employees = filter_employees_for_user(employees, request.user)

    today = date.today()
    if archive_mode:
        employees = employees.filter(
            models.Q(contracts__valid_until__lt=today) | models.Q(contracts__isnull=True)
        ).distinct()
    else:
        employees = employees.filter(
            models.Q(contracts__valid_until__isnull=True) |
            models.Q(contracts__valid_until__gte=today)
        ).distinct()

    if search_query:
        employees = employees.filter(
            employee_list_search_q(search_query, as_of=today)
        ).distinct()

    if sort_field == 'employee_number':
        order_by = 'employee_number' if sort_dir != 'desc' else '-employee_number'
        employees = employees.order_by(order_by, 'last_name', 'first_name')
        employee_list = list(employees)
        annotate_employees_for_list(employee_list, as_of=today, archive_mode=archive_mode)
    elif sort_field == 'valid_until':
        employees = employees.order_by('last_name', 'first_name')
        employee_list = list(employees)
        annotate_employees_for_list(employee_list, as_of=today, archive_mode=archive_mode)
        reverse = sort_dir == 'desc'
        employee_list.sort(
            key=lambda e: (
                e.list_valid_until.get('sort_key') or date.min,
                e.last_name or '',
                e.first_name or '',
            ),
            reverse=reverse,
        )
    else:
        order_by = 'last_name' if sort_dir != 'desc' else '-last_name'
        employees = employees.order_by(order_by, 'first_name')
        employee_list = list(employees)
        annotate_employees_for_list(employee_list, as_of=today, archive_mode=archive_mode)

    if not archive_mode and list_filter == 'expiring_soon':
        employee_list = [e for e in employee_list if e.list_expiry_warning]
    elif not archive_mode and list_filter == 'no_followup':
        # Same set as warning for now (warning encodes no seamless follow-up / gap)
        employee_list = [e for e in employee_list if e.list_expiry_warning]
    elif not archive_mode and list_filter == 'check_needed':
        employee_list = [
            e for e in employee_list
            if e.check_needed or getattr(e, 'list_contract_check_needed', False)
        ]
    elif not archive_mode and list_filter == 'pending':
        employee_list = [e for e in employee_list if e.is_pending]

    # Per-row manage right for row click (scoped managers)
    if can_manage:
        for emp in employee_list:
            emp.list_can_edit = user_can_manage_employee(request.user, emp)
    else:
        for emp in employee_list:
            emp.list_can_edit = False

    show_actions = can_create_personnel
    show_checkboxes = can_manage

    context = {
        'employees': employee_list,
        'user_groups': user_groups,
        'archive_mode': archive_mode,
        'search_query': search_query,
        'current_sort': sort_field,
        'current_dir': sort_dir,
        'list_filter': list_filter,
        'can_manage_employees': can_manage,
        'can_create_personnel': can_create_personnel,
        'can_edit_any': can_edit_any,
        'show_actions': show_actions,
        'show_checkboxes': show_checkboxes,
    }

    if request.method == 'POST' and request.POST.get('action') == 'delete_selected':
        if not can_manage:
            messages.error(request, "You do not have permission to delete employees.")
            return redirect('hr:employee_list')
        from django.db.models.deletion import ProtectedError, RestrictedError

        ids = request.POST.getlist('selected_ids')
        deleted = 0
        skipped_perm = 0
        blocked = []
        for eid in ids:
            try:
                emp = Employee.objects.get(pk=eid)
            except (Employee.DoesNotExist, ValueError, TypeError):
                continue
            if not user_can_manage_employee(request.user, emp):
                skipped_perm += 1
                continue
            label = f'{emp.get_full_name()} ({emp.employee_number})'
            try:
                emp.delete()
                deleted += 1
            except (ProtectedError, RestrictedError) as exc:
                # Collect human-readable blockers (e.g. Workgroup.pi)
                reasons = []
                protected_objects = getattr(exc, 'protected_objects', None) or []
                for obj in protected_objects:
                    reasons.append(f'{obj.__class__.__name__}: {obj}')
                detail = '; '.join(reasons) if reasons else str(exc)
                blocked.append(f'{label} — {detail}')
            except Exception as exc:  # noqa: BLE001
                blocked.append(f'{label} — {exc}')
        if deleted:
            messages.success(request, f'{deleted} employee(s) deleted.')
        if skipped_perm:
            messages.warning(
                request,
                f'{skipped_perm} employee(s) skipped (no manage permission).',
            )
        if blocked:
            messages.error(
                request,
                'Could not delete '
                + f'{len(blocked)} employee(s) because other records still reference them: '
                + ' | '.join(blocked[:5])
                + (' …' if len(blocked) > 5 else '')
                + ' Typical cause: employee is Principal Investigator of a workgroup '
                '(change or delete the workgroup first).',
            )
        if not deleted and not blocked and not skipped_perm:
            messages.info(request, 'No employees were selected for deletion.')
        return redirect('hr:employee_list')

    return render(request, 'hr/employee_list.html', context)


def _safe_next_url(request, default='/hr/employees/'):
    """Allow only relative same-site next URLs (from import preview etc.)."""
    next_url = request.GET.get('next') or request.POST.get('next') or ''
    next_url = next_url.strip()
    if next_url.startswith('/') and not next_url.startswith('//'):
        return next_url
    return default


def _is_active_from_post(cform, data, inst):
    is_existing = bool(getattr(inst, 'pk', None))
    if not is_existing:
        return True
    if data is not None:
        raw = data.get(cform.add_prefix('is_active'))
        return raw in ('on', 'true', 'True', '1')
    return bool(inst.is_active)


def _cards_from_nested(nested_funding, nested_salary, data=None):
    """Merge funding + salary nested formsets into card dicts by index."""
    salary_by_index = {idx: (cform, ss_fs) for idx, cform, ss_fs in nested_salary}
    cards = []
    for index, cform, fa_fs in nested_funding:
        inst = cform.instance
        is_existing = bool(getattr(inst, 'pk', None))
        is_active = _is_active_from_post(cform, data, inst)
        ss_pair = salary_by_index.get(index)
        ss_fs = ss_pair[1] if ss_pair else None
        if is_existing:
            fa_prefix = funding_prefix_for_existing(inst.pk)
            ss_prefix = salary_prefix_for_existing(inst.pk)
        else:
            fa_prefix = funding_prefix_for_new(index)
            ss_prefix = salary_prefix_for_new(index)
        cards.append({
            'index': index,
            'form': cform,
            'funding_formset': fa_fs if is_active else None,
            'salary_formset': ss_fs if is_active else None,
            'prefix': fa_fs.prefix if fa_fs else fa_prefix,
            'salary_prefix': ss_fs.prefix if ss_fs else ss_prefix,
            'is_existing': is_existing,
            'is_active': is_active,
            'contract_pk': inst.pk if is_existing else None,
            'funding_readonly': list(
                inst.funding_allocations.order_by('start_date', 'end_date', 'pk')
            ) if is_existing and not is_active else [],
            'salary_readonly': list(
                inst.salary_supplements.order_by('-created_at', 'pk')
            ) if is_existing and not is_active else [],
        })
    return cards


def _contract_ui_context(request, employee, task=None):
    funding_initial_by_index = {}
    contract_extra = 0

    contract_initial = None
    if request.method != 'POST' and task is not None:
        from .common import recruitment_contract_initial
        from apps.finances.funding_sources import funding_source_value_for_instance
        contract_extra = 1
        contract_initial = [recruitment_contract_initial(task)]
        funding_initial_by_index[0] = [
            {
                'funding_source': funding_source_value_for_instance(allocation),
                'workhours_percentage': allocation.workhours_percentage,
                'plan_position_number': allocation.plan_position_number,
                'start_date': task.valid_from,
                'end_date': task.valid_until,
                'is_active': True,
            }
            for allocation in task.funding_allocations.all()
        ]

    if request.method != 'POST' and employee and getattr(employee, 'pk', None):
        add_wbs = (request.GET.get('add_funding_wbs') or '').strip()
        if add_wbs and not employee.contracts.filter(is_active=True).exists():
            messages.warning(
                request,
                'No active contract found. Create/activate a contract before adding a funding allocation.',
            )

    data = request.POST if request.method == 'POST' else None
    built = build_contract_cards(
        employee,
        data,
        contract_extra=contract_extra,
        contract_initial=contract_initial,
        funding_initial_by_index=funding_initial_by_index,
    )

    for card in built['contract_cards']:
        cform = card['form']
        inst = cform.instance
        if inst.pk and not inst.is_active and data is None:
            card['funding_readonly'] = list(
                inst.funding_allocations.order_by('start_date', 'end_date', 'pk')
            )
            card['salary_readonly'] = list(
                inst.salary_supplements.order_by('-created_at', 'pk')
            )
            card['funding_formset'] = None
            card['salary_formset'] = None
        else:
            card.setdefault('funding_readonly', [])
            card.setdefault('salary_readonly', [])

    return {
        **built,
        'add_funding_wbs': (
            (request.GET.get('add_funding_wbs') or '').strip()
            if request.method != 'POST' else ''
        ),
        'show_archived_contracts': (
            request.GET.get('show_archived_contracts') == '1'
            or request.POST.get('show_archived_contracts') == '1'
        ),
    }


def _bind_post_context(context, employee, request):
    contract_fs = ContractFormSet(request.POST, instance=employee)
    nested_fa = collect_funding_formsets_from_post(employee, contract_fs, request.POST)
    nested_ss = collect_salary_formsets_from_post(employee, contract_fs, request.POST)
    context['contract_formset'] = contract_fs
    context['contract_cards'] = _cards_from_nested(nested_fa, nested_ss, request.POST)
    context['workgroup_formset'] = WorkgroupFormSet(request.POST, instance=employee)
    context['nested_funding'] = nested_fa
    context['nested_salary'] = nested_ss
    context['show_archived_contracts'] = request.POST.get('show_archived_contracts') == '1'
    return context


class EmployeeCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Employee
    form_class = EmployeeForm
    template_name = 'hr/employee_form.html'
    success_url = '/hr/employees/'

    def test_func(self):
        user = self.request.user
        if user_can_manage_employees(user):
            return True
        task = get_recruitment_task(self.request)
        return task is not None and can_create_employee_from_recruitment(user, task)

    def get_initial(self):
        initial = super().get_initial()
        task = get_recruitment_task(self.request)
        if task:
            initial.update(recruitment_employee_initial(task))
        employee_number = (self.request.GET.get('employee_number') or '').strip()
        if employee_number and 'employee_number' not in initial:
            initial['employee_number'] = employee_number
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        task = get_recruitment_task(self.request)
        employee = Employee()
        if self.request.POST:
            _bind_post_context(context, employee, self.request)
        else:
            ui = _contract_ui_context(self.request, employee, task=task)
            context.update(ui)
            context['workgroup_formset'] = WorkgroupFormSet(instance=employee)
            context['nested_funding'] = [
                (c['index'], c['form'], c['funding_formset'])
                for c in ui['contract_cards']
                if c.get('funding_formset') is not None
            ]
            context['nested_salary'] = [
                (c['index'], c['form'], c['salary_formset'])
                for c in ui['contract_cards']
                if c.get('salary_formset') is not None
            ]
        context['from_recruitment_task'] = task
        context['next_url'] = self.request.GET.get('next') or self.request.POST.get('next') or ''
        context.update(employee_document_context(self.request))
        context['current_payscales_json'] = current_payscales_json()
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        contract_fs = context['contract_formset']
        employee, errors = save_employee_with_formsets(
            self.request,
            form,
            (contract_fs, context['workgroup_formset']),
            nested_funding=context.get('nested_funding') or [],
            nested_salary=context.get('nested_salary') or [],
        )
        if employee is None:
            for err in errors:
                messages.error(self.request, err)
            return self.form_invalid(form)

        finalize_recruitment_task(self.request, employee)
        messages.success(self.request, "Employee successfully created.")
        return redirect(_safe_next_url(self.request, self.success_url))


class EmployeeUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Employee
    form_class = EmployeeForm
    template_name = 'hr/employee_form.html'
    success_url = '/hr/employees/'

    def test_func(self):
        # Object permission checked in dispatch after object is loaded
        return user_can_manage_employees(self.request.user)

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not user_can_manage_employee(request.user, self.object):
            messages.error(request, "You don't have permission to edit this employee.")
            return redirect('hr:employee_list')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee = self.object
        if self.request.POST:
            _bind_post_context(context, employee, self.request)
        else:
            ui = _contract_ui_context(self.request, employee, task=None)
            context.update(ui)
            context['workgroup_formset'] = WorkgroupFormSet(instance=employee)
            context['nested_funding'] = [
                (c['index'], c['form'], c['funding_formset'])
                for c in ui['contract_cards']
                if c.get('funding_formset') is not None
            ]
            context['nested_salary'] = [
                (c['index'], c['form'], c['salary_formset'])
                for c in ui['contract_cards']
                if c.get('salary_formset') is not None
            ]
        context['next_url'] = self.request.GET.get('next') or self.request.POST.get('next') or ''
        context['current_payscales_json'] = current_payscales_json()
        context.update(employee_document_context(self.request, self.object))
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        contract_fs = context['contract_formset']
        employee, errors = save_employee_with_formsets(
            self.request,
            form,
            (contract_fs, context['workgroup_formset']),
            nested_funding=context.get('nested_funding') or [],
            nested_salary=context.get('nested_salary') or [],
        )
        if employee is None:
            for err in errors:
                messages.error(self.request, err)
            return self.form_invalid(form)

        messages.success(self.request, "Employee successfully saved.")
        return redirect(_safe_next_url(self.request, self.success_url))

    def form_invalid(self, form):
        messages.error(self.request, "Please correct the errors below.")
        return self.render_to_response(self.get_context_data(form=form))
