"""
PSP / WBS element CRUD views.

Do not remove any existing requirements from this module without explicit instruction.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models.deletion import ProtectedError
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView
from django.views.generic.edit import DeleteView

from apps.finances.cost_center_access import (
    filter_cost_centers_for_user,
    user_can_manage_cost_center,
    user_manages_all_cost_centers,
)
from apps.finances.psp_access import (
    filter_psp_for_user,
    psp_workgroup_queryset_for_user,
    user_can_manage_psp,
    user_manages_all_psp,
)
from apps.core.record_nav import adjacent_item_urls
from apps.hr.workgroup_access import get_user_workgroups
from ..forms import WBSElementForm, WBSElementYearEstimateFormSet
from ..models import CostCenter, WBSElement
from ..psp_cost_types import clear_disabled_year_estimate_amounts


def _show_inactive_psp(request) -> bool:
    return (request.GET.get('show_inactive') or '').strip() in {'1', 'on', 'true', 'yes'}


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


def _psp_manage_queryset(queryset, user):
    """Managers only see elements they may manage (scoped or institute-wide)."""
    if user_manages_all_psp(user):
        return queryset
    return filter_psp_for_user(queryset, user)


def _default_workgroup_for_user(user):
    return get_user_workgroups(user).order_by('short_name').first()


def _configure_work_group_field(form, user, *, instance=None):
    form.fields['work_group'].queryset = psp_workgroup_queryset_for_user(
        user, instance=instance,
    )
    form.fields['work_group'].required = True
    form.fields['work_group'].empty_label = '— Select work group —'
    # Prefill when the user has exactly one assignable workgroup and none set yet.
    if instance is None or not getattr(instance, 'pk', None) or not instance.work_group_id:
        qs = form.fields['work_group'].queryset
        if qs.count() == 1:
            form.initial.setdefault('work_group', qs.first().pk)


class PSPListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = WBSElement
    template_name = 'finances/psp_cost_center_manage.html'
    context_object_name = 'psp_elements'

    def get_queryset(self):
        if not user_can_manage_psp(self.request.user):
            return WBSElement.objects.none()
        queryset = WBSElement.objects.select_related(
            'work_group', 'responsible_person', 'cost_center',
        ).order_by('wbs_code', 'pk')
        queryset = _psp_manage_queryset(queryset, self.request.user)
        if not _show_inactive_psp(self.request):
            queryset = queryset.filter(is_inactive=False)
        return queryset

    def test_func(self):
        user = self.request.user
        return user_can_manage_psp(user) or user_can_manage_cost_center(user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        can_psp = user_can_manage_psp(user)
        can_cc = user_can_manage_cost_center(user)
        tab = (self.request.GET.get('tab') or '').strip()
        if tab == 'cost-centers' and can_cc:
            active_tab = 'cost-centers'
        elif can_psp:
            active_tab = 'psp'
        else:
            active_tab = 'cost-centers'
        cost_centers = CostCenter.objects.none()
        if can_cc:
            cost_qs = CostCenter.objects.select_related('work_group').order_by('cost_center')
            if user_manages_all_cost_centers(user):
                cost_centers = cost_qs
            else:
                cost_centers = filter_cost_centers_for_user(cost_qs, user)
        context.update({
            'can_manage_psp': can_psp,
            'can_manage_cost_centers': can_cc,
            'active_tab': active_tab,
            'cost_centers': cost_centers,
            'show_inactive': _show_inactive_psp(self.request),
        })
        return context

    def post(self, request, *args, **kwargs):
        action = request.POST.get('action')
        if action == 'delete_selected_cc':
            if not user_can_manage_cost_center(request.user):
                messages.error(request, 'You do not have permission to delete cost centers.')
                return redirect(reverse('finances:psp_manage') + '?tab=cost-centers')
            ids = [i for i in request.POST.getlist('selected_ids') if i]
            if not ids:
                messages.warning(request, "No entries selected.")
                return redirect(reverse('finances:psp_manage') + '?tab=cost-centers')
            deleted = 0
            protected = 0
            for pk in ids:
                try:
                    cc_qs = CostCenter.objects.filter(pk=pk)
                    if not user_manages_all_cost_centers(request.user):
                        cc_qs = filter_cost_centers_for_user(cc_qs, request.user)
                    obj = cc_qs.get()
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
            return redirect(reverse('finances:psp_manage') + '?tab=cost-centers')
        if action in ('delete_selected', 'delete_selected_psp'):
            if not user_can_manage_psp(request.user):
                messages.error(request, 'You do not have permission to delete PSP elements.')
                return redirect('finances:psp_manage')
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
        return user_can_manage_psp(self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.method == 'POST':
            kwargs['files'] = self.request.FILES
        return kwargs

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
            context['year_estimate_formset'] = WBSElementYearEstimateFormSet(self.request.POST)
        else:
            context['year_estimate_formset'] = WBSElementYearEstimateFormSet()
        context['title'] = 'Create PSP element'
        context['hide_work_group_field'] = False
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
        return user_can_manage_psp(self.request.user)

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
        context['title'] = 'Edit PSP element'
        context['hide_work_group_field'] = False
        nav_qs = _psp_manage_queryset(
            WBSElement.objects.all(), self.request.user,
        ).order_by('wbs_code', 'pk')
        prev_url, next_url = adjacent_item_urls(
            nav_qs, self.object.pk, 'finances:psp_update',
        )
        context['prev_item_url'] = prev_url
        context['next_item_url'] = next_url
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
        return user_can_manage_psp(self.request.user)

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
