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

from apps.finances.cost_center_access import (
    cost_center_workgroup_queryset_for_user,
    filter_cost_centers_for_user,
    user_can_manage_cost_center,
    user_manages_all_cost_centers,
)
from apps.hr.workgroup_access import get_user_workgroups
from ..forms import CostCenterForm, CostCenterYearEstimateFormSet
from ..models import CostCenter
from ..psp_cost_types import clear_disabled_year_estimate_amounts


def _cost_center_manage_queryset(queryset, user):
    if user_manages_all_cost_centers(user):
        return queryset
    return filter_cost_centers_for_user(queryset, user)


def _default_workgroup_for_user(user):
    return get_user_workgroups(user).order_by('short_name').first()


def _configure_work_group_field(form, user, *, instance=None):
    form.fields['work_group'].queryset = cost_center_workgroup_queryset_for_user(
        user, instance=instance,
    )
    form.fields['work_group'].required = True
    form.fields['work_group'].empty_label = '— Select work group —'
    if instance is None or not getattr(instance, 'pk', None) or not instance.work_group_id:
        qs = form.fields['work_group'].queryset
        if qs.count() == 1:
            form.initial.setdefault('work_group', qs.first().pk)


class CostCenterListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = CostCenter
    template_name = 'finances/cost_center_list.html'
    context_object_name = 'cost_centers'

    def get_queryset(self):
        queryset = CostCenter.objects.select_related('work_group').order_by('cost_center')
        return _cost_center_manage_queryset(queryset, self.request.user)

    def test_func(self):
        return user_can_manage_cost_center(self.request.user)

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
                    obj = _cost_center_manage_queryset(
                        CostCenter.objects.filter(pk=pk),
                        request.user,
                    ).get()
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
        return user_can_manage_cost_center(self.request.user)

    def get_initial(self):
        initial = super().get_initial()
        workgroup = _default_workgroup_for_user(self.request.user)
        if workgroup and get_user_workgroups(self.request.user).count() == 1:
            initial['work_group'] = workgroup.pk
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        _configure_work_group_field(form, self.request.user)
        return form

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
            clear_disabled_year_estimate_amounts(self.object)
            messages.success(request, f'Cost center "{self.object.cost_center}" was created.')
            return redirect(self.success_url)
        return self.render_to_response(self.get_context_data(form=form, year_estimate_formset=formset))


class CostCenterUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = CostCenter
    form_class = CostCenterForm
    template_name = 'finances/cost_center_form.html'
    success_url = reverse_lazy('finances:cost_center_manage')

    def get_queryset(self):
        return _cost_center_manage_queryset(CostCenter.objects.all(), self.request.user)

    def test_func(self):
        return user_can_manage_cost_center(self.request.user)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        _configure_work_group_field(
            form,
            self.request.user,
            instance=getattr(form, 'instance', None),
        )
        return form

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
            clear_disabled_year_estimate_amounts(self.object)
            messages.success(request, f'Cost center "{self.object.cost_center}" was updated.')
            return redirect(self.success_url)
        return self.render_to_response(self.get_context_data(form=form, year_estimate_formset=formset))


class CostCenterDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = CostCenter
    template_name = 'finances/cost_center_confirm_delete.html'
    success_url = reverse_lazy('finances:cost_center_manage')

    def get_queryset(self):
        return _cost_center_manage_queryset(CostCenter.objects.all(), self.request.user)

    def test_func(self):
        return user_can_manage_cost_center(self.request.user)

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