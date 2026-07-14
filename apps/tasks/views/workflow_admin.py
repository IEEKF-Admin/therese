"""Administration views for per-workgroup task workflow coordinators."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from apps.hr.models import Workgroup
from apps.tasks.models import Task, TaskWorkflowCoordinator
from apps.tasks.views.recruitment_admin import AssistingAdminMixin
from apps.tasks.workflow_config import (
    save_workflow_coordinators_from_post,
    workflow_config_context_for_workgroup,
)


class TaskWorkflowConfigListView(AssistingAdminMixin, View):
    template_name = 'tasks/workflow_admin/config_list.html'

    def get(self, request):
        workgroups = Workgroup.objects.select_related('pi').order_by('short_name')
        rows = []
        for workgroup in workgroups:
            assignment_count = TaskWorkflowCoordinator.objects.filter(workgroup=workgroup).count()
            configured_types = (
                TaskWorkflowCoordinator.objects.filter(workgroup=workgroup)
                .values_list('task_type', flat=True)
                .distinct()
                .count()
            )
            rows.append({
                'workgroup': workgroup,
                'assignment_count': assignment_count,
                'configured_types': configured_types,
                'total_types': len(Task.TASK_TYPES),
            })
        return render(request, self.template_name, {'rows': rows})


class TaskWorkflowConfigUpdateView(AssistingAdminMixin, View):
    template_name = 'tasks/workflow_admin/config_form.html'

    def get(self, request, pk):
        workgroup = get_object_or_404(Workgroup.objects.select_related('pi'), pk=pk)
        context = {
            'workgroup': workgroup,
            **workflow_config_context_for_workgroup(workgroup),
        }
        return render(request, self.template_name, context)

    def post(self, request, pk):
        workgroup = get_object_or_404(Workgroup, pk=pk)
        save_workflow_coordinators_from_post(workgroup, request.POST)
        messages.success(
            request,
            f'Workflow coordinators updated for {workgroup.short_name}.',
        )
        return redirect(reverse('tasks:workflow_config_update', kwargs={'pk': workgroup.pk}))