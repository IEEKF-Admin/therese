"""
apps/tasks/views/detail/personnel.py
Detail views for Personnel Reallocation and Contract Extension tasks.
Only accessible to PI users and involved employees.
"""

from django.shortcuts import render, redirect
from django.contrib import messages

from ...forms import (
    PersonnelReallocationTaskForm,
    PersonnelContractExtensionTaskForm,
)
from ...utils import is_personnel_coordinator


def can_view_personnel_task(user, task):
    employee = getattr(user, 'employee', None)
    if not employee:
        return False
    if user.is_superuser or is_personnel_coordinator(user):
        return True
    if task.creator == employee or task.assignee == employee:
        return True
    return False


def personnel_task_detail(request, task):
    """
    Shared detail handler for both personnel task types.
    Uses the correct form based on task_type.
    """
    employee = getattr(request.user, 'employee', None)

    if not can_view_personnel_task(request.user, task):
        messages.error(request, "You don't have permission to view this task.")
        return redirect('tasks:my_tasks')

    task_type = task.task_type
    is_creator = task.creator == employee
    is_coordinator = is_personnel_coordinator(request.user)
    is_assignee = task.assignee == employee

    # Coordinator: full edit inkl. Assignee | Approver (Assignee): bearbeiten | Creator: read-only
    can_edit = (
        request.user.is_superuser
        or is_coordinator
        or is_assignee
    )
    can_set_assignee = is_coordinator

    if task_type == 'personnel_reallocation':
        form_class = PersonnelReallocationTaskForm
        template = 'tasks/detail/reallocation.html'
    elif task_type == 'personnel_contract_extension':
        form_class = PersonnelContractExtensionTaskForm
        template = 'tasks/detail/extension.html'
    else:
        messages.error(request, "Unknown personnel task type.")
        return redirect('tasks:my_tasks')

    if request.method == 'POST' and can_edit:
        form = form_class(
            request.POST,
            instance=task,
            user=request.user,
            is_creation=False
        )
        if form.is_valid():
            old_status = task.status
            saved = form.save(commit=False)
            if employee:
                saved.last_changed_by = employee
            saved.save()
            # Log status change
            from ...models import TaskComment
            if old_status != saved.status:
                TaskComment.objects.create(
                    task=saved,
                    author=employee,
                    text=f"Status changed from '{old_status}' to '{saved.status}'"
                )
            messages.success(request, "Task updated successfully.")
            return redirect('tasks:my_tasks')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = form_class(
            instance=task,
            user=request.user,
            is_creation=False
        )

    is_archived_by_user = employee and employee in task.archived_by.all() if hasattr(task, 'archived_by') else False

    context = {
        'task': task,
        'form': form,
        'can_edit': can_edit,
        'can_set_assignee': can_set_assignee,
        'is_creator': is_creator,
        'is_coordinator': is_coordinator,
        'task_type': task_type,
        'employee': employee,
        'is_archived_by_user': is_archived_by_user,
    }
    return render(request, template, context)


