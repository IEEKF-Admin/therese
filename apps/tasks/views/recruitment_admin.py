"""Administration views for recruitment jobs and limitation reasons."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.tasks.forms import LimitationReasonForm, RecruitmentJobForm
from apps.tasks.models import LimitationReason, RecruitmentJob
from apps.tasks.recruitment_config import (
    DurationOperator,
    RECRUITMENT_CONFIGURABLE_FIELDS,
    RequiredMode,
    VisibilityMode,
)
from apps.finances.models import PayScale
from apps.tasks.recruitment_form_helpers import get_field_rule_context, save_field_rules_from_post


def _job_form_payscale_context():
    current = PayScale.get_current()
    payscale_data = {}
    for ps in current:
        group = ps.pay_scale_group
        if group not in payscale_data:
            payscale_data[group] = []
        payscale_data[group].append({
            'experience_level': ps.experience_level,
            'monthly_salary': str(ps.monthly_salary),
        })
    return {'recruitment_payscale_data_json': payscale_data}


def user_is_assisting_admin(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name='Assisting Admins').exists()


class AssistingAdminMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return user_is_assisting_admin(self.request.user)


class RecruitmentJobListView(AssistingAdminMixin, ListView):
    model = RecruitmentJob
    template_name = 'tasks/recruitment_admin/job_list.html'
    context_object_name = 'jobs'

    def get_queryset(self):
        return RecruitmentJob.objects.all().order_by('name')


class RecruitmentJobCreateView(AssistingAdminMixin, CreateView):
    model = RecruitmentJob
    form_class = RecruitmentJobForm
    template_name = 'tasks/recruitment_admin/job_form.html'
    success_url = reverse_lazy('tasks:recruitment_job_manage')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Create Job'
        context['field_rules'] = get_field_rule_context(None)
        context['visibility_modes'] = VisibilityMode.CHOICES
        context['required_modes'] = RequiredMode.CHOICES
        context['duration_operators'] = DurationOperator.CHOICES
        context.update(_job_form_payscale_context())
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        save_field_rules_from_post(self.object, self.request.POST)
        messages.success(self.request, f'Job "{self.object.name}" was created.')
        return response


class RecruitmentJobUpdateView(AssistingAdminMixin, UpdateView):
    model = RecruitmentJob
    form_class = RecruitmentJobForm
    template_name = 'tasks/recruitment_admin/job_form.html'
    success_url = reverse_lazy('tasks:recruitment_job_manage')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Edit Job'
        context['field_rules'] = get_field_rule_context(self.object)
        context['visibility_modes'] = VisibilityMode.CHOICES
        context['required_modes'] = RequiredMode.CHOICES
        context['duration_operators'] = DurationOperator.CHOICES
        context.update(_job_form_payscale_context())
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        save_field_rules_from_post(self.object, self.request.POST)
        messages.success(self.request, f'Job "{self.object.name}" was updated.')
        return response


class RecruitmentJobDeleteView(AssistingAdminMixin, DeleteView):
    model = RecruitmentJob
    template_name = 'tasks/recruitment_admin/job_confirm_delete.html'
    success_url = reverse_lazy('tasks:recruitment_job_manage')

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.recruitment_tasks.exists() or obj.employees.exists():
            messages.error(
                request,
                f'Job "{obj.name}" cannot be deleted because recruitment tasks or employees reference it.',
            )
            return redirect(self.success_url)
        messages.success(request, f'Job "{obj.name}" was deleted.')
        return super().delete(request, *args, **kwargs)


class LimitationReasonListView(AssistingAdminMixin, ListView):
    model = LimitationReason
    template_name = 'tasks/recruitment_admin/limitation_reason_list.html'
    context_object_name = 'limitation_reasons'

    def get_queryset(self):
        return LimitationReason.objects.prefetch_related('jobs').order_by('title')


class LimitationReasonCreateView(AssistingAdminMixin, CreateView):
    model = LimitationReason
    form_class = LimitationReasonForm
    template_name = 'tasks/recruitment_admin/limitation_reason_form.html'
    success_url = reverse_lazy('tasks:limitation_reason_manage')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Create Limitation Reason'
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Limitation reason "{form.instance.title}" was created.')
        return super().form_valid(form)


class LimitationReasonUpdateView(AssistingAdminMixin, UpdateView):
    model = LimitationReason
    form_class = LimitationReasonForm
    template_name = 'tasks/recruitment_admin/limitation_reason_form.html'
    success_url = reverse_lazy('tasks:limitation_reason_manage')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Edit Limitation Reason'
        return context

    def form_valid(self, form):
        messages.success(self.request, f'Limitation reason "{form.instance.title}" was updated.')
        return super().form_valid(form)


class LimitationReasonDeleteView(AssistingAdminMixin, DeleteView):
    model = LimitationReason
    template_name = 'tasks/recruitment_admin/limitation_reason_confirm_delete.html'
    success_url = reverse_lazy('tasks:limitation_reason_manage')

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        messages.success(request, f'Limitation reason "{obj.title}" was deleted.')
        return super().delete(request, *args, **kwargs)