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
    FundingFormSet,
    SalaryFormSet,
    WorkgroupFormSet,
    make_contract_formset,
    make_funding_formset,
)
from apps.tasks.utils import can_create_employee_from_recruitment
from .common import (
    current_payscales_json,
    employee_document_context,
    finalize_recruitment_task,
    get_recruitment_task,
    recruitment_contract_initial,
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
        # Prefill from third-party funding import preview link
        employee_number = (self.request.GET.get('employee_number') or '').strip()
        if employee_number and 'employee_number' not in initial:
            initial['employee_number'] = employee_number
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        task = get_recruitment_task(self.request)
        if self.request.POST:
            # TOTAL_FORMS on POST drives how many forms bind.
            context['contract_formset'] = ContractFormSet(self.request.POST)
            context['funding_formset'] = FundingFormSet(self.request.POST)
            context['salary_formset'] = SalaryFormSet(self.request.POST)
            context['workgroup_formset'] = WorkgroupFormSet(self.request.POST)
        else:
            contract_initial = []
            funding_initial = []
            if task:
                contract_initial = [recruitment_contract_initial(task)]
                from apps.finances.funding_sources import funding_source_value_for_instance
                funding_initial = [
                    {
                        'funding_source': funding_source_value_for_instance(allocation),
                        'workhours_percentage': allocation.workhours_percentage,
                        'plan_position_number': allocation.plan_position_number,
                        'start_date': task.valid_from,
                        'end_date': task.valid_until,
                    }
                    for allocation in task.funding_allocations.all()
                ]
            ContractFS = make_contract_formset(extra=len(contract_initial))
            FundingFS = make_funding_formset(extra=len(funding_initial))
            context['contract_formset'] = ContractFS(initial=contract_initial)
            context['funding_formset'] = FundingFS(initial=funding_initial)
            context['salary_formset'] = SalaryFormSet()
            context['workgroup_formset'] = WorkgroupFormSet()
        context['from_recruitment_task'] = task
        context['next_url'] = self.request.GET.get('next') or self.request.POST.get('next') or ''
        context.update(employee_document_context(self.request))
        context['current_payscales_json'] = current_payscales_json()
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formsets = (
            context['contract_formset'],
            context['funding_formset'],
            context['salary_formset'],
            context['workgroup_formset'],
        )
        employee = save_employee_with_formsets(self.request, form, formsets)
        if employee is None:
            if not context['contract_formset'].is_valid():
                messages.error(self.request, "Please correct errors in Contracts.")
            elif not context['funding_formset'].is_valid():
                messages.error(self.request, "Please correct errors in Funding Allocations.")
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
        if self.request.POST:
            context['contract_formset'] = ContractFormSet(self.request.POST, instance=self.object)
            context['funding_formset'] = FundingFormSet(self.request.POST, instance=self.object)
            context['salary_formset'] = SalaryFormSet(self.request.POST, instance=self.object)
            context['workgroup_formset'] = WorkgroupFormSet(self.request.POST, instance=self.object)
        else:
            # extra=0: only existing contracts / allocations, no blank rows —
            # unless import preview asked to add a funding row for a WBS.
            add_wbs = (self.request.GET.get('add_funding_wbs') or '').strip()
            funding_initial = []
            if add_wbs:
                from apps.finances.models import WBSElement
                from apps.finances.funding_sources import WBS_PREFIX
                wbs = WBSElement.objects.filter(wbs_code=add_wbs).first()
                if wbs:
                    funding_initial = [{
                        'funding_source': f'{WBS_PREFIX}:{wbs.pk}',
                        'workhours_percentage': None,
                        'plan_position_number': '',
                        'start_date': date.today(),
                        'end_date': None,
                    }]
            if funding_initial:
                FundingFS = make_funding_formset(extra=len(funding_initial))
                # Existing allocations + one prefilled extra row for the import WBS
                context['funding_formset'] = FundingFS(
                    instance=self.object,
                    initial=funding_initial,
                )
            else:
                context['funding_formset'] = FundingFormSet(instance=self.object)
            context['contract_formset'] = ContractFormSet(instance=self.object)
            context['salary_formset'] = SalaryFormSet(instance=self.object)
            context['workgroup_formset'] = WorkgroupFormSet(instance=self.object)

        context['next_url'] = self.request.GET.get('next') or self.request.POST.get('next') or ''
        context['current_payscales_json'] = current_payscales_json()
        context.update(employee_document_context(self.request, self.object))
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        formsets = (
            context['contract_formset'],
            context['funding_formset'],
            context['salary_formset'],
            context['workgroup_formset'],
        )
        employee = save_employee_with_formsets(self.request, form, formsets)
        if employee is None:
            messages.error(self.request, "Please correct errors in the related sections.")
            return self.form_invalid(form)

        messages.success(self.request, "Employee successfully saved.")
        return redirect(_safe_next_url(self.request, self.success_url))

    def form_invalid(self, form):
        messages.error(self.request, "Please correct the errors below.")
        return self.render_to_response(self.get_context_data(form=form))