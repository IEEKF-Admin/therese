"""
Cost center CRUD views for assisting admins.

Do not remove any existing requirements from this module without explicit instruction.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models.deletion import ProtectedError
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView
from django.views.generic.edit import DeleteView

from ..forms import CostCenterForm, CostCenterYearEstimateFormSet
from ..models import CostCenter


class CostCenterListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = CostCenter
    template_name = 'finances/cost_center_list.html'
    context_object_name = 'cost_centers'

    def get_queryset(self):
        return CostCenter.objects.all().order_by('cost_center')

    def test_func(self):
        return self.request.user.has_perm('finances.manage_cost_center')

    def post(self, request, *args, **kwargs):
        if request.POST.get('action') == 'delete_selected':
            ids = [i for i in request.POST.getlist('selected_ids') if i]
            if not ids:
                messages.warning(request, "No entries selected.")
                return redirect('finances:cost_center_manage')

            deleted = 0
            protected = 0
            for pk in ids:
                try:
                    obj = CostCenter.objects.get(pk=pk)
                    obj.delete()
                    deleted += 1
                except CostCenter.DoesNotExist:
                    pass
                except ProtectedError:
                    protected += 1
            if deleted:
                messages.success(request, f"{deleted} cost center(s) deleted.")
            if protected:
                messages.error(
                    request,
                    f"{protected} cost center(s) could not be deleted "
                    "(e.g. because of linked PSP elements).",
                )
            return redirect('finances:cost_center_manage')
        return super().post(request, *args, **kwargs)


class CostCenterCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = CostCenter
    form_class = CostCenterForm
    template_name = 'finances/cost_center_form.html'
    success_url = reverse_lazy('finances:cost_center_manage')

    def test_func(self):
        return self.request.user.has_perm('finances.manage_cost_center')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['files'] = self.request.FILES
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['year_estimate_formset'] = CostCenterYearEstimateFormSet(self.request.POST)
        else:
            context['year_estimate_formset'] = CostCenterYearEstimateFormSet()
        context['title'] = 'Create Cost Center'
        return context

    def post(self, request, *args, **kwargs):
        self.object = None
        form = self.get_form()
        formset = CostCenterYearEstimateFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            self.object = form.save()
            formset.instance = self.object
            formset.save()
            messages.success(request, f'Cost center "{self.object.cost_center}" was created.')
            return redirect(self.success_url)
        return self.render_to_response(self.get_context_data(form=form, year_estimate_formset=formset))


class CostCenterUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = CostCenter
    form_class = CostCenterForm
    template_name = 'finances/cost_center_form.html'
    success_url = reverse_lazy('finances:cost_center_manage')

    def test_func(self):
        return self.request.user.has_perm('finances.manage_cost_center')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['files'] = self.request.FILES
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['year_estimate_formset'] = CostCenterYearEstimateFormSet(
                self.request.POST, instance=self.object,
            )
        else:
            context['year_estimate_formset'] = CostCenterYearEstimateFormSet(instance=self.object)
        context['title'] = 'Edit Cost Center'
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        formset = CostCenterYearEstimateFormSet(request.POST, instance=self.object)
        if form.is_valid() and formset.is_valid():
            self.object = form.save()
            formset.instance = self.object
            formset.save()
            messages.success(request, f'Cost center "{self.object.cost_center}" was updated.')
            return redirect(self.success_url)
        return self.render_to_response(self.get_context_data(form=form, year_estimate_formset=formset))


class CostCenterDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = CostCenter
    template_name = 'finances/cost_center_confirm_delete.html'
    success_url = reverse_lazy('finances:cost_center_manage')

    def test_func(self):
        return self.request.user.has_perm('finances.manage_cost_center')

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        code = obj.cost_center
        try:
            response = super().delete(request, *args, **kwargs)
            messages.success(request, f'Cost center "{code}" was deleted.')
            return response
        except ProtectedError:
            messages.error(
                request,
                f'Cost center "{code}" cannot be deleted because dependent data exists (e.g. PSP elements).',
            )
            return redirect(self.success_url)