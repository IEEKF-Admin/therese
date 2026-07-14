"""
Employee self-service profile view.

Do not remove any existing requirements from this module without explicit instruction.
"""

from datetime import date

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import UpdateView

from ...forms import EmployeeForm
from ...models import Employee
from ...document_utils import process_document_uploads
from ..employee_form_helpers import WorkgroupFormSet
from .common import employee_document_context


class MyProfileView(LoginRequiredMixin, UpdateView):
    """Self-service view for employees to edit their own data (with restrictions)."""
    model = Employee
    form_class = EmployeeForm
    template_name = 'hr/my_profile.html'
    success_url = reverse_lazy('hr:my_profile')

    def get_object(self):
        user = self.request.user
        if not hasattr(user, 'employee') or user.employee is None:
            return None
        return user.employee

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object is None:
            messages.error(request, "No employee profile found for your account.")
            return redirect('tasks:my_tasks')
        return super().dispatch(request, *args, **kwargs)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        for field_name in ('monthly_salary', 'cost_center', 'scan_of_contract', 'profile_picture'):
            form.fields.pop(field_name, None)
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        emp = self.object
        today = date.today()

        context['current_contracts'] = emp.contracts.filter(
            Q(valid_until__isnull=True) | Q(valid_until__gte=today)
        ).order_by('-valid_from')

        context['current_fundings'] = emp.allocations.filter(
            Q(end_date__isnull=True) | Q(end_date__gte=today)
        ).select_related('wbs_element').order_by('-start_date')

        if self.request.POST:
            workgroup_formset = WorkgroupFormSet(self.request.POST, instance=self.object)
        else:
            workgroup_formset = WorkgroupFormSet(instance=self.object)
        context['workgroup_formset'] = workgroup_formset

        context['is_self_profile'] = True
        context.update(employee_document_context(self.request, self.object))
        return context

    def form_valid(self, form):
        context = self.get_context_data()
        workgroup_formset = context.get('workgroup_formset')
        if workgroup_formset and workgroup_formset.is_valid():
            self.object = form.save()
            workgroup_formset.instance = self.object
            workgroup_formset.save()
            uploader = getattr(self.request.user, 'employee', None)
            process_document_uploads(self.request, self.object, uploaded_by=uploader)
            messages.success(self.request, "✅ Your profile has been updated!")
            return redirect(self.success_url)
        messages.error(self.request, "Please correct the errors below.")
        return self.form_invalid(form)