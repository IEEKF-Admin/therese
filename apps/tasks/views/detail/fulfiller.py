"""
apps/tasks/views/detail/fulfiller.py

Project: THERESE - Transparent HR Employee Resource Evaluation System Enhanced

Features / Requirements:
- View for fulfiller role (assignee / warehouse / order processing)
- Correct namespace usage ('tasks:my_tasks')
- Read-only for most fields; status may be updated on POST
- Approvers see standard-order checkboxes without full coordinator edit rights

Do not remove any existing requirements from this header without explicit instruction.
"""

from django.shortcuts import render
from django.contrib import messages

from ...forms import PurchaseOrderTaskForm
from ...utils import is_procurement_approver
from ..redirects import redirect_to_my_tasks


def fulfiller_task_detail(request, task):
    """Purchase order view for the assignee (fulfiller)."""
    if request.method == 'POST':
        form = PurchaseOrderTaskForm(
            request.POST,
            instance=task,
            user=request.user,
            is_creation=False,
        )
        if form.is_valid():
            old_status = task.status
            saved_task = form.save(commit=False)
            saved_task.last_changed_by = request.user.employee
            saved_task.save()
            # Log status change for activity trail.
            from ...models import TaskComment
            employee = request.user.employee
            if old_status != saved_task.status:
                TaskComment.objects.create(
                    task=saved_task,
                    author=employee,
                    text=f"Status changed from '{old_status}' to '{saved_task.status}'",
                )
            messages.success(request, "Status successfully updated.")
            return redirect_to_my_tasks()
        messages.error(request, "Please correct the errors below.")
    else:
        form = PurchaseOrderTaskForm(
            instance=task,
            user=request.user,
            is_creation=False,
        )

    # Approvers can mark items as standard orders without coordinator edit rights.
    is_approver = is_procurement_approver(request.user)

    employee = getattr(request.user, 'employee', None)
    is_archived_by_user = (
        employee and employee in task.archived_by.all()
        if hasattr(task, 'archived_by')
        else False
    )

    context = {
        'task': task,
        'form': form,
        'can_edit': True,
        'is_fulfiller': True,
        'show_standard_checkboxes': is_approver,
        'employee': employee,
        'is_archived_by_user': is_archived_by_user,
    }
    return render(request, 'tasks/detail/fulfiller.html', context)