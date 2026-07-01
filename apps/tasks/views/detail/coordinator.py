"""
apps/tasks/views/detail/coordinator.py

Project: THERESE - Transparent HR Employee Resource Evaluation System Enhanced

Features / Requirements:
- Full edit view for Procurement Coordinator
- Correct namespace usage for redirects ('tasks:my_tasks')
- Proper form handling and success/error messages

Do not remove any existing requirements from this header without explicit instruction.
"""

from django.shortcuts import render, redirect
from django.contrib import messages

from ...forms import PurchaseOrderTaskForm


def coordinator_task_detail(request, task):
    """Voll editierbare Ansicht fÃ¼r Coordinator"""
    if request.method == 'POST':
        form = PurchaseOrderTaskForm(
            request.POST, 
            instance=task, 
            user=request.user, 
            is_creation=False
        )
        if form.is_valid():
            old_wbs = task.wbs_element_id if hasattr(task, 'wbs_element_id') else None
            old_status = task.status
            saved_task = form.save(commit=False)
            saved_task.last_changed_by = request.user.employee
            saved_task.save()
            # Log key changes for activity
            from ...models import TaskComment
            employee = request.user.employee
            if old_wbs != saved_task.wbs_element_id and saved_task.wbs_element:
                TaskComment.objects.create(
                    task=saved_task,
                    author=employee,
                    text=f"WBS Element set to {saved_task.wbs_element}"
                )
            if old_status != saved_task.status:
                TaskComment.objects.create(
                    task=saved_task,
                    author=employee,
                    text=f"Status changed from '{old_status}' to '{saved_task.status}'"
                )
            if hasattr(task, 'assignee') and task.assignee != saved_task.assignee:
                new_assignee = saved_task.assignee.get_full_name() if saved_task.assignee else "unassigned"
                TaskComment.objects.create(
                    task=saved_task,
                    author=employee,
                    text=f"Assignee changed to {new_assignee}"
                )
            messages.success(request, "Changes have been saved successfully.")
            return redirect('tasks:my_tasks')          # ← Namespace korrigiert
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = PurchaseOrderTaskForm(
            instance=task, 
            user=request.user, 
            is_creation=False
        )

    employee = getattr(request.user, 'employee', None)
    is_archived_by_user = employee and employee in task.archived_by.all() if hasattr(task, 'archived_by') else False

    context = {
        'task': task,
        'form': form,
        'can_edit': True,
        'is_coordinator': True,
        'employee': employee,
        'is_archived_by_user': is_archived_by_user,
    }
    return render(request, 'tasks/detail/coordinator.html', context)

