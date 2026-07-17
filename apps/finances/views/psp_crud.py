"""
PSP / WBS element CRUD views for assisting admins.

Do not remove any existing requirements from this module without explicit instruction.
"""

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models.deletion import ProtectedError
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView
from django.views.generic.edit import DeleteView

from apps.accounts.permissions import GroupNames
from apps.hr.models import Workgroup
from apps.hr.workgroup_access import filter_by_user_workgroups, get_user_workgroups
from ..forms import WBSElementForm, WBSElementYearEstimateFormSet
from ..models import WBSElement
from ..psp_cost_types import clear_disabled_year_estimate_amounts


def _psp_delete_blocker_labels(wbs_element):
    """Human-readable reasons why a PSP element cannot be deleted yet."""
    from apps.hr.models import FundingAllocation
    from apps.tasks.models import (
        PersonnelReallocationTask,
        PurchaseOrderTask,
        RecruitmentFundingAllocation,
    )

    blockers = []
    funding_count = FundingAllocation.objects.filter(wbs_element=wbs_element).count()
    if funding_count:
        blockers.append(f'{funding_count} funding allocation(s)')

    purchase_count = PurchaseOrderTask.objects.filter(wbs_element=wbs_element).count()
    if purchase_count:
        blockers.append(f'{purchase_count} purchase order(s)')

    reallocation_count = PersonnelReallocationTask.objects.filter(
        funding_allocations__wbs_element=wbs_element,
    ).distinct().count()
    if reallocation_count:
        blockers.append(f'{reallocation_count} personnel reallocation task(s)')

    recruitment_count = RecruitmentFundingAllocation.objects.filter(wbs_element=wbs_element).count()
    if recruitment_count:
        blockers.append(f'{recruitment_count} recruitment funding allocation(s)')

    return blockers


def _protected_error_message(code, protected_objects):
    labels = sorted({
        obj._meta.verbose_name_plural.capitalize()
        for obj in protected_objects
    })
    if labels:
        details = ', '.join(labels)
        return (
            f'PSP element "{code}" cannot be deleted because dependent data exists '
            f'({details}).'
        )
    return (
        f'PSP element "{code}" cannot be deleted because dependent data exists '
        '(e.g. funding allocations or bookings).'
    )


def _user_is_institute_psp_admin(user):
    """Assisting Admins and superusers manage PSP elements institute-wide."""
    if user.is_superuser:
        return True
    return user.groups.filter(name=GroupNames.ASSISTING_ADMINS).exists()


def _psp_manage_queryset(queryset, user):
    """Workgroup-scoped PSP managers only see elements from their work groups."""
    if _user_is_institute_psp_admin(user):
        return queryset
    return filter_by_user_workgroups(queryset, user)


def _psp_workgroup_queryset(user, instance=None):
    """Work group choices for the PSP editor."""
    if _user_is_institute_psp_admin(user):
        queryset = Workgroup.objects.all()
    else:
        queryset = get_user_workgroups(user)
    if instance and instance.work_group_id:
        queryset = queryset | Workgroup.objects.filter(pk=instance.work_group_id)
    return queryset.distinct().order_by('short_name')


def _default_workgroup_for_user(user):
    return get_user_workgroups(user).order_by('short_name').first()


def _work_group_field_hidden(user):
    return not _user_is_institute_psp_admin(user)


def _configure_work_group_field(form, user, *, instance=None):
    form.fields['work_group'].queryset = _psp_workgroup_queryset(user, instance=instance)
    if _work_group_field_hidden(user):
        form.fields['work_group'].widget = forms.HiddenInput()
        if instance is None or not instance.pk:
            workgroup = _default_workgroup_for_user(user)
            if workgroup:
                form.initial.setdefault('work_group', workgroup.pk)


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
                    "because dependent data exists (e.g. funding allocations or bookings).",
                )
            if not deleted and not protected and ids:
                messages.warning(request, "No selected PSP elements could be deleted.")
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

    def get_initial(self):
        initial = super().get_initial()
        if _work_group_field_hidden(self.request.user):
            workgroup = _default_workgroup_for_user(self.request.user)
            if workgroup:
                initial['work_group'] = workgroup.pk
        return initial

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        _configure_work_group_field(form, self.request.user)
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['year_estimate_formset'] = WBSElementYearEstimateFormSet(self.request.POST)
        else:
            context['year_estimate_formset'] = WBSElementYearEstimateFormSet()
        context['title'] = 'Create PSP Element'
        context['hide_work_group_field'] = _work_group_field_hidden(self.request.user)
        return context

    def post(self, request, *args, **kwargs):
        self.object = None
        form = self.get_form()
        formset = WBSElementYearEstimateFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            self.object = form.save()
            formset.instance = self.object
            formset.save()
            clear_disabled_year_estimate_amounts(self.object)
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
        _configure_work_group_field(
            form,
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
        context['hide_work_group_field'] = _work_group_field_hidden(self.request.user)
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        formset = WBSElementYearEstimateFormSet(request.POST, instance=self.object)
        if form.is_valid() and formset.is_valid():
            self.object = form.save()
            formset.instance = self.object
            formset.save()
            clear_disabled_year_estimate_amounts(self.object)
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['delete_blockers'] = _psp_delete_blocker_labels(self.object)
        context['can_delete'] = not context['delete_blockers']
        return context

    def form_valid(self, form):
        code = self.object.wbs_code
        blockers = _psp_delete_blocker_labels(self.object)
        if blockers:
            messages.error(
                self.request,
                f'PSP element "{code}" cannot be deleted: ' + '; '.join(blockers) + '.',
            )
            return redirect(self.success_url)
        try:
            response = super().form_valid(form)
            messages.success(self.request, f'PSP element "{code}" was deleted.')
            return response
        except ProtectedError as exc:
            messages.error(
                self.request,
                _protected_error_message(code, exc.protected_objects),
            )
            return redirect(self.success_url)