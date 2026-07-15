"""
PSP / WBS element CRUD views for assisting admins.

Do not remove any existing requirements from this module without explicit instruction.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models.deletion import ProtectedError
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView
from django.views.generic.edit import DeleteView

from apps.hr.models import Workgroup
from apps.hr.workgroup_access import filter_by_user_workgroups
from ..forms import WBSElementForm, WBSElementYearEstimateFormSet
from ..models import WBSElement


def _psp_manage_queryset(queryset, user):
    """Assisting admins with manage_psp_element may manage all PSP elements."""
    if user.has_perm('finances.manage_psp_element'):
        return queryset
    return filter_by_user_workgroups(queryset, user)


def _psp_workgroup_queryset(user, instance=None):
    """Work group choices for the PSP editor."""
    if user.has_perm('finances.manage_psp_element'):
        queryset = Workgroup.objects.all()
    else:
        queryset = filter_by_user_workgroups(Workgroup.objects.all(), user)
    if instance and instance.work_group_id:
        queryset = queryset | Workgroup.objects.filter(pk=instance.work_group_id)
    return queryset.distinct().order_by('short_name')


class PSPListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = WBSElement
    template_name = 'finances/psp_list.html'
    context_object_name = 'psp_elements'

    def get_queryset(self):
        queryset = WBSElement.objects.select_related(
            'work_group', 'responsible_person', 'cost_center',
        )
        return _psp_manage_queryset(queryset, self.request.user)

    def test_func(self):
        return self.request.user.has_perm('finances.manage_psp_element')

    def post(self, request, *args, **kwargs):
        if request.POST.get('action') == 'delete_selected':
            ids = [i for i in request.POST.getlist('selected_ids') if i]
            if not ids:
                messages.warning(request, "No entries selected.")
                return redirect('finances:psp_manage')

            deleted = 0
            protected = 0
            for pk in ids:
                try:
                    obj = _psp_manage_queryset(
                        WBSElement.objects.filter(pk=pk),
                        request.user,
                    ).get()
                    obj.delete()
                    deleted += 1
                except WBSElement.DoesNotExist:
                    pass
                except ProtectedError:
                    protected += 1
            if deleted:
                messages.success(request, f"{deleted} PSP element(s) deleted.")
            if protected:
                messages.error(
                    request,
                    f"{protected} PSP element(s) could not be deleted "
                    "(e.g. because of Funding Allocations or bookings).",
                )
            return redirect('finances:psp_manage')
        return super().post(request, *args, **kwargs)


class PSPCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = WBSElement
    form_class = WBSElementForm
    template_name = 'finances/psp_form.html'
    success_url = reverse_lazy('finances:psp_manage')

    def test_func(self):
        return self.request.user.has_perm('finances.manage_psp_element')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.method == 'POST':
            kwargs['files'] = self.request.FILES
        return kwargs

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['work_group'].queryset = _psp_workgroup_queryset(self.request.user)
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['year_estimate_formset'] = WBSElementYearEstimateFormSet(self.request.POST)
        else:
            context['year_estimate_formset'] = WBSElementYearEstimateFormSet()
        context['title'] = 'Create PSP Element'
        return context

    def post(self, request, *args, **kwargs):
        self.object = None
        form = self.get_form()
        formset = WBSElementYearEstimateFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            self.object = form.save()
            formset.instance = self.object
            formset.save()
            messages.success(request, f'PSP element "{self.object.wbs_code}" was created.')
            return redirect(self.success_url)
        return self.render_to_response(self.get_context_data(form=form, year_estimate_formset=formset))


class PSPUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = WBSElement
    form_class = WBSElementForm
    template_name = 'finances/psp_form.html'
    success_url = reverse_lazy('finances:psp_manage')

    def get_queryset(self):
        return _psp_manage_queryset(WBSElement.objects.all(), self.request.user)

    def test_func(self):
        return self.request.user.has_perm('finances.manage_psp_element')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.method == 'POST':
            kwargs['files'] = self.request.FILES
        return kwargs

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['work_group'].queryset = _psp_workgroup_queryset(
            self.request.user,
            instance=getattr(form, 'instance', None),
        )
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['year_estimate_formset'] = WBSElementYearEstimateFormSet(
                self.request.POST, instance=self.object,
            )
        else:
            context['year_estimate_formset'] = WBSElementYearEstimateFormSet(instance=self.object)
        context['title'] = 'Edit PSP Element'
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        formset = WBSElementYearEstimateFormSet(request.POST, instance=self.object)
        if form.is_valid() and formset.is_valid():
            self.object = form.save()
            formset.instance = self.object
            formset.save()
            messages.success(request, f'PSP element "{self.object.wbs_code}" was updated.')
            return redirect(self.success_url)
        return self.render_to_response(self.get_context_data(form=form, year_estimate_formset=formset))


class PSPDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = WBSElement
    template_name = 'finances/psp_confirm_delete.html'
    success_url = reverse_lazy('finances:psp_manage')

    def get_queryset(self):
        return _psp_manage_queryset(WBSElement.objects.all(), self.request.user)

    def test_func(self):
        return self.request.user.has_perm('finances.manage_psp_element')

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        code = obj.wbs_code
        try:
            response = super().delete(request, *args, **kwargs)
            messages.success(request, f'PSP element "{code}" was deleted.')
            return response
        except ProtectedError:
            messages.error(
                request,
                f'PSP element "{code}" cannot be deleted because dependent data exists '
                '(e.g. Funding Allocations).',
            )
            return redirect(self.success_url)

    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)