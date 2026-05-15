"""
apps/hr/views/employee.py

Project: THERESE - Transparent HR Employee Resource Evaluation System Enhanced
"""

from datetime import date

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic import CreateView, UpdateView
from django.db import models

from ..models import Employee
from ..forms import EmployeeForm
from .employee_form_helpers import (
    ContractFormSet, FundingFormSet, 
    SalaryFormSet, WorkgroupFormSet
)


# ====================== LIST VIEW ======================
@login_required
def employee_list(request):
    """Liste aller Mitarbeiter"""
    print("🔍 [DEBUG] employee_list view called")
    
    user_groups = list(request.user.groups.values_list('name', flat=True))
    print(f"🔍 User groups: {user_groups}")

    allowed_groups = {'PI', 'Personnel Approver', 'Personnel Fulfiller', 'Personnel Coordinator'}
    
    if not allowed_groups.intersection(user_groups):
        messages.error(request, "You don't have permission to view employees.")
        print("❌ Permission denied for employee list")
        return redirect('tasks:my_tasks')

    archive_mode = request.GET.get('archive') == '1'
    search_query = request.GET.get('q', '').strip()
    sort_field = request.GET.get('sort', 'last_name')
    sort_dir = request.GET.get('dir', 'asc')

    print(f"🔍 Archive mode: {archive_mode} | Search: '{search_query}'")

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

    # Sorting
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

    print(f"🔍 Returning {employees.count()} employees to template")
    return render(request, 'hr/employee_list.html', context)


# ====================== CREATE VIEW ======================
class EmployeeCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = Employee
    form_class = EmployeeForm
    template_name = 'hr/employee_form.html'
    success_url = '/hr/employees/'

    def test_func(self):
        print("🔍 [DEBUG] EmployeeCreateView.test_func called")
        user_groups = list(self.request.user.groups.values_list('name', flat=True))
        allowed = {'PI', 'Personnel Approver', 'Personnel Fulfiller', 'Personnel Coordinator'}
        result = bool(allowed.intersection(user_groups))
        print(f"🔍 Permission check result: {result}")
        return result

    def get_context_data(self, **kwargs):
        print("🔍 [DEBUG] EmployeeCreateView.get_context_data called")
        context = super().get_context_data(**kwargs)
        context['contract_formset'] = ContractFormSet()
        context['funding_formset'] = FundingFormSet()
        context['salary_formset'] = SalaryFormSet()
        context['workgroup_formset'] = WorkgroupFormSet()
        return context

    def form_valid(self, form):
        print("🔍 [DEBUG] EmployeeCreateView.form_valid called")
        # ... (die gleiche form_valid Logik wie vorher)
        return super().form_valid(form)   # Platzhalter – bei Bedarf erweitern


# ====================== UPDATE VIEW ======================
class EmployeeUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Employee
    form_class = EmployeeForm
    template_name = 'hr/employee_form.html'
    success_url = '/hr/employees/'

    def test_func(self):
        print("🔍 [DEBUG] EmployeeUpdateView.test_func called")
        user_groups = list(self.request.user.groups.values_list('name', flat=True))
        allowed = {'PI', 'Personnel Approver', 'Personnel Fulfiller', 'Personnel Coordinator'}
        result = bool(allowed.intersection(user_groups))
        print(f"🔍 Permission check result: {result}")
        return result

    def get_context_data(self, **kwargs):
        print("🔍 [DEBUG] EmployeeUpdateView.get_context_data called - PK:", self.object.pk if self.object else None)
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['contract_formset'] = ContractFormSet(self.request.POST, instance=self.object)
            context['funding_formset'] = FundingFormSet(self.request.POST, instance=self.object)
            context['salary_formset'] = SalaryFormSet(self.request.POST, instance=self.object)
            context['workgroup_formset'] = WorkgroupFormSet(self.request.POST, instance=self.object)
        else:
            context['contract_formset'] = ContractFormSet(instance=self.object)
            context['funding_formset'] = FundingFormSet(instance=self.object)
            context['salary_formset'] = SalaryFormSet(instance=self.object)
            context['workgroup_formset'] = WorkgroupFormSet(instance=self.object)
        return context

    def form_valid(self, form):
        print("🔍 [DEBUG] EmployeeUpdateView.form_valid called - checking all inlines...")
        context = self.get_context_data()
        
        contract_valid = context['contract_formset'].is_valid()
        funding_valid = context['funding_formset'].is_valid()
        salary_valid = context['salary_formset'].is_valid()
        workgroup_valid = context['workgroup_formset'].is_valid()

        print(f"Contract valid: {contract_valid}")
        print(f"Funding valid: {funding_valid}")
        print(f"Salary valid: {salary_valid}")
        print(f"Workgroup valid: {workgroup_valid}")

        if not all([contract_valid, funding_valid, salary_valid, workgroup_valid]):
            if not contract_valid:
                messages.error(self.request, "❌ Fehler in den Verträgen (Contracts). Bitte prüfen Sie Pflichtfelder.")
            if not funding_valid:
                messages.error(self.request, "❌ Fehler in den Funding Allocations.")
            return self.form_invalid(form)

        self.object = form.save(commit=False)
        if not self.object.user_id and self.object.pk:
            existing = Employee.objects.filter(pk=self.object.pk).first()
            if existing and existing.user_id:
                self.object.user = existing.user

        self.object.save()

        for fs in [context['contract_formset'], context['funding_formset'],
                   context['salary_formset'], context['workgroup_formset']]:
            fs.instance = self.object
            fs.save()

        messages.success(self.request, "✅ Employee successfully saved!")
        return redirect(self.success_url)

    def form_invalid(self, form):
        print("❌ form_invalid called in UpdateView")
        messages.error(self.request, "Please correct the errors below.")
        return self.render_to_response(self.get_context_data(form=form))