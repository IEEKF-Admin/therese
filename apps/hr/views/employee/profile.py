"""
Employee self-service profile view.

Do not remove any existing requirements from this module without explicit instruction.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import UpdateView

from ...forms import EmployeeProfileForm
from ...models import Employee
from ...document_utils import process_document_uploads
from ...validity import contract_open_on_q, resolve_as_of
from ..employee_form_helpers import WorkgroupFormSet
from .common import employee_document_context


class MyProfileView(LoginRequiredMixin, UpdateView):
    """Self-service view for employees to edit their own data (with restrictions)."""
    model = Employee
    form_class = EmployeeProfileForm
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        emp = self.object
        today = resolve_as_of(None)

        # Soft rule: only started (not future) and not ended; latest first.
        context['current_contracts'] = emp.contracts.filter(
            contract_open_on_q(today)
        ).order_by('-valid_from', '-pk')
        # Soft-winning contract used for salary/costs
        context['active_contract'] = emp.get_contract_as_of(today)

        # One open FA per funding target (WBS / cost center)
        context['current_fundings'] = emp.get_open_funding_allocations_as_of(today)

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