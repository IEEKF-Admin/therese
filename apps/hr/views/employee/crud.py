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
    SalaryFormSet,
    WorkgroupFormSet,
    build_contract_cards,
    collect_funding_formsets_from_post,
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
def employee_list(request):
    """List of all employees."""
    user_groups = list(request.user.groups.values_list('name', flat=True))
    if not (request.user.is_superuser or
            request.user.has_perm('hr.can_view_employees') or
            request.user.has_perm('hr.manage_employee')):
        messages.error(request, "You don't have permission to view employees.")
        return redirect('tasks:my_tasks')

    archive_mode = request.GET.get('archive') == '1'
    search_query = request.GET.get('q', '').strip()
    sort_field = request.GET.get('sort', 'last_name')
    sort_dir = request.GET.get('dir', 'asc')

    employees = Employee.objects.select_related(
        'room__building', 'cost_center', 'user'
    ).prefetch_related('contracts')

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
            models.Q(first_name__icontains=search_query) |
            models.Q(last_name__icontains=search_query) |
            models.Q(employee_number__icontains=search_query)
        )

    if sort_field == 'employee_number':
        order_by = 'employee_number'
    else:
        order_by = 'last_name' if sort_dir == 'asc' else '-last_name'
    if sort_dir == 'desc' and sort_field != 'employee_number':
        order_by = '-' + order_by

    employees = employees.order_by(order_by, 'first_name')

    context = {
        'employees': employees,
        'user_groups': user_groups,
        'archive_mode': archive_mode,
        'search_query': search_query,
        'current_sort': sort_field,
        'current_dir': sort_dir,
    }

    if request.method == 'POST' and request.POST.get('action') == 'delete_selected':
        if not (request.user.is_superuser or request.user.has_perm('hr.manage_employee')):
            messages.error(request, "You do not have permission to delete employees.")
            return redirect('hr:employee_list')
        ids = request.POST.getlist('selected_ids')
        deleted = 0
        for eid in ids:
            try:
                Employee.objects.get(pk=eid).delete()
                deleted += 1
            except Exception:
                pass
        if deleted:
            messages.success(request, f"{deleted} employees deleted.")
        return redirect('hr:employee_list')

    return render(request, 'hr/employee_list.html', context)


def _safe_next_url(request, default='/hr/employees/'):
    """Allow only relative same-site next URLs (from import preview etc.)."""
    next_url = request.GET.get('next') or request.POST.get('next') or ''
    next_url = next_url.strip()
    if next_url.startswith('/') and not next_url.startswith('//'):
        return next_url
    return default


def _cards_from_nested(nested, data=None):
    cards = []
    for index, cform, fa_fs in nested:
        inst = cform.instance
        is_existing = bool(getattr(inst, 'pk', None))
        is_active = True
        if is_existing:
            # Prefer POST cleaned is_active when available
            if data is not None and hasattr(cform, 'data'):
                raw = data.get(cform.add_prefix('is_active'))
                # checkbox missing => False
                is_active = raw in ('on', 'true', 'True', '1')
            else:
                is_active = bool(inst.is_active)
        cards.append({
            'index': index,
            'form': cform,
            'funding_formset': fa_fs if is_active else None,
            'prefix': fa_fs.prefix,
            'is_existing': is_existing,
            'is_active': is_active,
            'contract_pk': inst.pk if is_existing else None,
            'funding_readonly': list(
                inst.funding_allocations.order_by('start_date', 'end_date', 'pk')
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
            card['funding_formset'] = None
        else:
            card.setdefault('funding_readonly', [])

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


class EmployeeCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Employee
    form_class = EmployeeForm
    template_name = 'hr/employee_form.html'
    success_url = '/hr/employees/'

    def test_func(self):
        user = self.request.user
        if user.is_superuser or user.has_perm('hr.manage_employee'):
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
            contract_fs = ContractFormSet(self.request.POST, instance=employee)
            nested = collect_funding_formsets_from_post(
                employee, contract_fs, self.request.POST
            )
            context['contract_formset'] = contract_fs
            context['contract_cards'] = _cards_from_nested(nested, self.request.POST)
            context['salary_formset'] = SalaryFormSet(self.request.POST, instance=employee)
            context['workgroup_formset'] = WorkgroupFormSet(self.request.POST, instance=employee)
            context['nested_funding'] = nested
            context['show_archived_contracts'] = (
                self.request.POST.get('show_archived_contracts') == '1'
            )
        else:
            ui = _contract_ui_context(self.request, employee, task=task)
            context.update(ui)
            context['salary_formset'] = SalaryFormSet(instance=employee)
            context['workgroup_formset'] = WorkgroupFormSet(instance=employee)
            context['nested_funding'] = [
                (c['index'], c['form'], c['funding_formset'])
                for c in ui['contract_cards']
                if c.get('funding_formset') is not None
            ]
        context['from_recruitment_task'] = task
        context['next_url'] = self.request.GET.get('next') or self.request.POST.get('next') or ''
        context.update(employee_document_context(self.request))
        context['current_payscales_json'] = current_payscales_json()
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        contract_fs = context['contract_formset']
        nested = context.get('nested_funding') or []
        employee, errors = save_employee_with_formsets(
            self.request,
            form,
            (contract_fs, context['salary_formset'], context['workgroup_formset']),
            nested_funding=nested,
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
        user = self.request.user
        return user.is_superuser or user.has_perm('hr.manage_employee')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee = self.object
        if self.request.POST:
            contract_fs = ContractFormSet(self.request.POST, instance=employee)
            nested = collect_funding_formsets_from_post(
                employee, contract_fs, self.request.POST
            )
            context['contract_formset'] = contract_fs
            context['contract_cards'] = _cards_from_nested(nested, self.request.POST)
            context['salary_formset'] = SalaryFormSet(self.request.POST, instance=employee)
            context['workgroup_formset'] = WorkgroupFormSet(self.request.POST, instance=employee)
            context['nested_funding'] = nested
            context['show_archived_contracts'] = (
                self.request.POST.get('show_archived_contracts') == '1'
            )
        else:
            ui = _contract_ui_context(self.request, employee, task=None)
            context.update(ui)
            context['salary_formset'] = SalaryFormSet(instance=employee)
            context['workgroup_formset'] = WorkgroupFormSet(instance=employee)
            context['nested_funding'] = [
                (c['index'], c['form'], c['funding_formset'])
                for c in ui['contract_cards']
                if c.get('funding_formset') is not None
            ]
        context['next_url'] = self.request.GET.get('next') or self.request.POST.get('next') or ''
        context['current_payscales_json'] = current_payscales_json()
        context.update(employee_document_context(self.request, self.object))
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        contract_fs = context['contract_formset']
        nested = context.get('nested_funding') or []
        employee, errors = save_employee_with_formsets(
            self.request,
            form,
            (contract_fs, context['salary_formset'], context['workgroup_formset']),
            nested_funding=nested,
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
