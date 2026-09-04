"""
Employee list, create, and update views.

Do not remove any existing requirements from this module without explicit instruction.
"""

from datetime import date

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.db import models
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.generic import CreateView, UpdateView

from ...forms import EmployeeForm, MinimalEmployeeCreateForm
from ...models import Employee
from ..employee_form_helpers import (
    ContractFormSet,
    WorkgroupFormSet,
    build_contract_cards,
    collect_funding_formsets_from_post,
    collect_salary_formsets_from_post,
    empty_contract_templates,
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
    user_is_employees_manage_all_group,
)
from apps.hr.workgroup_access import get_user_workgroups
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

    viewer = getattr(request.user, 'employee', None)
    if viewer is not None and viewer.is_external and not request.user.is_superuser:
        messages.error(request, "Phone list is only available for institute employees.")
        return redirect('tasks:my_tasks')

    today = date.today()
    open_employee_ids = (
        Contract.objects.filter(contract_open_on_q(today))
        .values_list('employee_id', flat=True)
        .distinct()
    )
    employees = (
        Employee.objects.institute().filter(pk__in=open_employee_ids)
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
    current_contract_q = (
        models.Q(contracts__valid_until__isnull=True)
        | models.Q(contracts__valid_until__gte=today)
    )
    if archive_mode:
        employees = employees.filter(is_external=False).exclude(
            current_contract_q
        ).distinct()
    else:
        employees = employees.filter(
            models.Q(is_external=True) | current_contract_q
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
    show_action_column = show_actions or (archive_mode and can_manage)
    from apps.accounts.permissions import user_can_reset_user_password
    can_reset_passwords = user_can_reset_user_password(request.user)

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
        'show_action_column': show_action_column,
        'show_checkboxes': show_checkboxes,
        'can_reset_passwords': can_reset_passwords,
    }

    if request.method == 'POST' and request.POST.get('action') == 'reset_passwords':
        if not can_reset_passwords:
            messages.error(request, 'You do not have permission to reset passwords.')
            return redirect('hr:employee_list')
        from apps.accounts.account_emails import reset_passwords_for_employees

        ids = request.POST.getlist('selected_ids')
        selected = list(Employee.objects.filter(pk__in=ids).select_related('user'))
        reset_count, skipped = reset_passwords_for_employees(selected)
        if reset_count:
            messages.success(
                request,
                f'Password reset for {reset_count} employee(s). '
                'Notification emails are sent with a short pause between messages.',
            )
        if skipped:
            messages.warning(
                request,
                f'{skipped} selected employee(s) have no login user and were skipped.',
            )
        if not reset_count and not skipped:
            messages.error(request, 'Select at least one employee.')
        return redirect('hr:employee_list')

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

    restore_id = (request.POST.get('restore_id') or '').strip()
    if request.method == 'POST' and (
        request.POST.get('action') == 'restore_selected' or restore_id
    ):
        if not can_manage:
            messages.error(request, 'You do not have permission to restore employees.')
            return redirect(reverse('hr:employee_list') + '?archive=1')
        from apps.hr.employee_list_helpers import restore_employee_from_archive

        ids = [restore_id] if restore_id else request.POST.getlist('selected_ids')
        restored = 0
        skipped_perm = 0
        no_contract = []
        failed = []
        for eid in ids:
            try:
                emp = Employee.objects.get(pk=eid)
            except (Employee.DoesNotExist, ValueError, TypeError):
                continue
            if not user_can_manage_employee(request.user, emp):
                skipped_perm += 1
                continue
            ok, reason = restore_employee_from_archive(emp)
            if ok:
                restored += 1
            elif reason == 'no_contract':
                no_contract.append(emp.get_full_name())
            else:
                failed.append(emp.get_full_name())
        if restored:
            messages.success(
                request,
                f'{restored} employee(s) restored to the active list.',
            )
        if skipped_perm:
            messages.warning(
                request,
                f'{skipped_perm} employee(s) skipped (no manage permission).',
            )
        if no_contract:
            messages.warning(
                request,
                'No contract to restore for: ' + ', '.join(no_contract[:5])
                + (' …' if len(no_contract) > 5 else '')
                + '. Open the employee and add a contract.',
            )
        if failed:
            messages.error(
                request,
                'Could not restore: ' + ', '.join(failed[:5])
                + (' …' if len(failed) > 5 else ''),
            )
        if not restored and not skipped_perm and not no_contract and not failed:
            messages.info(request, 'No employees were selected for restore.')
        if restored and not no_contract and not failed:
            return redirect('hr:employee_list')
        return redirect(reverse('hr:employee_list') + '?archive=1')

    if request.GET.get('partial') == '1':
        return render(request, 'hr/_employee_table_body.html', context)
    return render(request, 'hr/employee_list.html', context)


def _safe_next_url(request, default='/hr/employees/'):
    """Allow only relative same-site next URLs (from import preview etc.)."""
    next_url = request.GET.get('next') or request.POST.get('next') or ''
    next_url = next_url.strip()
    if next_url.startswith('/') and not next_url.startswith('//'):
        return next_url
    return default


def _url_with_query(url, **params):
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update({key: str(value) for key, value in params.items() if value is not None})
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


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

    cards = built.get('contract_cards') or []
    return {
        **built,
        'add_funding_wbs': (
            (request.GET.get('add_funding_wbs') or '').strip()
            if request.method != 'POST' else ''
        ),
        'show_archived_contracts': (
            request.GET.get('show_archived_contracts') == '1'
            or request.POST.get('show_archived_contracts') == '1'
            or (
                request.method != 'POST'
                and bool(employee.pk)
                and any(card.get('is_existing') for card in cards)
                and not any(card.get('is_active') for card in cards)
            )
        ),
        'show_funding_help': any(card.get('is_active') for card in cards),
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
    context.update(empty_contract_templates(employee))
    context['show_archived_contracts'] = request.POST.get('show_archived_contracts') == '1'
    context['show_funding_help'] = any(
        card.get('is_active') for card in context.get('contract_cards') or []
    )
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
        from apps.accounts.permissions import user_is_systemadmin
        context['can_hard_delete'] = user_is_systemadmin(self.request.user)
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


class MinimalEmployeeCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    """Create an employee with only employee number and name."""

    model = Employee
    form_class = MinimalEmployeeCreateForm
    template_name = 'hr/employee_quick_create.html'

    def test_func(self):
        return user_can_manage_employees(self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['next_url'] = self.request.GET.get('next') or self.request.POST.get('next') or ''
        context['cancel_url'] = _safe_next_url(self.request, reverse('hr:employee_list'))
        context['show_work_group'] = user_is_employees_manage_all_group(self.request.user)
        return context

    def form_valid(self, form):
        employee = form.save()
        work_group = form.cleaned_data.get('work_group') if form.show_work_group else None
        if work_group is None:
            work_group = get_user_workgroups(self.request.user).order_by('short_name').first()
        if work_group is not None:
            work_group.members.add(employee)
        messages.success(
            self.request,
            f'Employee "{employee.get_full_name()}" was created.',
        )
        next_url = _safe_next_url(self.request, reverse('hr:employee_list'))
        return redirect(_url_with_query(next_url, employee=employee.pk))


class EmployeeUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Employee
    form_class = EmployeeForm
    template_name = 'hr/employee_form.html'
    success_url = '/hr/employees/'

    def test_func(self):
        # Object permission checked in dispatch after object is loaded
        return user_can_manage_employees(self.request.user)

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
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
        from apps.accounts.permissions import user_can_reset_user_password
        context['show_reset_password'] = (
            user_can_reset_user_password(self.request.user)
            and bool(employee.user_id)
        )
        from apps.accounts.permissions import user_is_systemadmin
        context['can_hard_delete'] = user_is_systemadmin(self.request.user)
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


@login_required
def employee_reset_password(request, pk):
    from apps.accounts.account_emails import reset_and_notify
    from apps.accounts.models import AccountEmailTemplate
    from apps.accounts.permissions import user_can_reset_user_password

    if request.method != 'POST':
        return redirect('hr:employee_update', pk=pk)
    if not user_can_reset_user_password(request.user):
        raise PermissionDenied
    employee = get_object_or_404(Employee.objects.select_related('user'), pk=pk)
    if not employee.user_id:
        messages.error(request, 'This employee has no login user.')
        return redirect('hr:employee_update', pk=pk)
    _password, sent = reset_and_notify(
        employee.user,
        employee,
        kind=AccountEmailTemplate.KIND_PASSWORD_RESET,
    )
    if sent:
        messages.success(
            request,
            'A new password was generated and emailed to the user.',
        )
    else:
        messages.warning(
            request,
            'A new password was generated, but the notification email could not be sent.',
        )
    return redirect('hr:employee_update', pk=pk)


@login_required
@require_POST
def contract_hard_delete(request, pk, contract_pk):
    from apps.accounts.permissions import user_is_systemadmin
    from apps.hr.models import Contract

    if not user_is_systemadmin(request.user):
        raise PermissionDenied
    employee = get_object_or_404(Employee, pk=pk)
    if not user_can_manage_employee(request.user, employee):
        raise PermissionDenied
    contract = get_object_or_404(Contract, pk=contract_pk, employee=employee)
    contract.delete()
    messages.success(request, 'Contract was permanently deleted.')
    return _redirect_employee_edit(pk)


@login_required
@require_POST
def funding_hard_delete(request, pk, fa_pk):
    from apps.accounts.permissions import user_is_systemadmin
    from apps.hr.models import FundingAllocation

    if not user_is_systemadmin(request.user):
        raise PermissionDenied
    employee = get_object_or_404(Employee, pk=pk)
    if not user_can_manage_employee(request.user, employee):
        raise PermissionDenied
    allocation = get_object_or_404(FundingAllocation, pk=fa_pk, employee=employee)
    allocation.delete()
    messages.success(request, 'Funding allocation was permanently deleted.')
    return _redirect_employee_edit(pk)


def _redirect_employee_edit(pk):
    """303 so the browser always GETs a fresh employee form after delete."""
    response = HttpResponseRedirect(reverse('hr:employee_update', args=[pk]))
    response.status_code = 303
    return response
