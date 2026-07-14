"""
apps/tasks/views/detail/generic.py
Detail view for General Requests (generic_text).
Recipient can update status + description.
"""

from django.shortcuts import render
from django.contrib import messages

from ...forms import GenericTextTaskForm
from ...workflow_config import creator_has_coordinator_fallback
from ..redirects import redirect_to_my_tasks


def generic_task_detail(request, task):
    """Detail view for General Requests.

    - Creator: mostly read-only
    - Recipient: can update status and description
    """
    employee = getattr(request.user, 'employee', None)
    is_creator = task.creator == employee
    is_recipient = task.recipient == employee if task.recipient else False
    coordinator_fallback = is_creator and creator_has_coordinator_fallback(request.user, task)
    can_edit = is_recipient or request.user.is_staff
    can_edit_coordinator_steps = coordinator_fallback

    if request.method == 'POST' and can_edit_coordinator_steps and not can_edit:
        old_status = task.status
        new_status = request.POST.get('status')
        if new_status:
            task.status = new_status
        task.comment = request.POST.get('comment', task.comment)
        if employee:
            task.last_changed_by = employee
        task.save()
        from ...models import TaskComment
        if old_status != task.status:
            TaskComment.objects.create(
                task=task,
                author=employee,
                text=f"Status changed from '{old_status}' to '{task.status}'"
            )
        messages.success(request, "General Request updated successfully.")
        return redirect_to_my_tasks()

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
            from ...models import TaskComment
            if old_status != saved_task.status:
                TaskComment.objects.create(
                    task=saved_task,
                    author=employee,
                    text=f"Status changed from '{old_status}' to '{saved_task.status}'"
                )
            messages.success(request, "General Request updated successfully.")
            return redirect_to_my_tasks()
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
        'can_edit_coordinator_steps': can_edit_coordinator_steps,
        'is_creator': is_creator,
        'is_recipient': is_recipient,
        'coordinator_fallback': coordinator_fallback,
        'task_type': 'generic_text',
        'employee': employee,
        'is_archived_by_user': is_archived_by_user,
    }
    return render(request, 'tasks/detail/generic.html', context)


