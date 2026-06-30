"""
apps/tasks/views/detail/generic.py
Detail view for General Requests (generic_text).
Recipient can update status + description.
"""

from django.shortcuts import render, redirect
from django.contrib import messages

from ...forms import GenericTextTaskForm


def generic_task_detail(request, task):
    """Detail view for General Requests.

    - Creator: mostly read-only
    - Recipient: can update status and description
    """
    employee = getattr(request.user, 'employee', None)
    is_creator = task.creator == employee
    is_recipient = task.recipient == employee if task.recipient else False
    can_edit = is_recipient or request.user.is_staff

    if request.method == 'POST' and can_edit:
        form = GenericTextTaskForm(
            request.POST,
            instance=task,
            user=request.user,
            is_creation=False
        )
        if form.is_valid():
            old_status = task.status
            saved_task = form.save(commit=False)
            if employee:
                saved_task.last_changed_by = employee
            saved_task.save()
            # Log status change
            from ...models import TaskComment
            if old_status != saved_task.status:
                TaskComment.objects.create(
                    task=saved_task,
                    author=employee,
                    text=f"Status changed from '{old_status}' to '{saved_task.status}'"
                )
            messages.success(request, "General Request updated successfully.")
            return redirect('tasks:my_tasks')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = GenericTextTaskForm(
            instance=task,
            user=request.user,
            is_creation=False
        )

    is_archived_by_user = employee and employee in task.archived_by.all() if hasattr(task, 'archived_by') else False

    context = {
        'task': task,
        'form': form,
        'can_edit': can_edit,
        'is_creator': is_creator,
        'is_recipient': is_recipient,
        'task_type': 'generic_text',
        'employee': employee,
        'is_archived_by_user': is_archived_by_user,
    }
    return render(request, 'tasks/detail/generic.html', context)


