"""
apps/tasks/views/detail/fulfiller.py

Project: THERESE - Transparent HR Employee Resource Evaluation System Enhanced

Features / Requirements:
- View for Fulfiller role (warehouse / order processing)
- Correct namespace usage ('tasks:my_tasks')
- Read-only for most fields, only status can be updated

Do not remove any existing requirements from this header without explicit instruction.
"""

from django.shortcuts import render, redirect
from django.contrib import messages

from ...forms import PurchaseOrderTaskForm
from ...utils import is_procurement_approver


def fulfiller_task_detail(request, task):
    """Ansicht fÃ¼r Fulfiller (z. B. Wareneingang)"""
    if request.method == 'POST':
        form = PurchaseOrderTaskForm(
            request.POST, 
            instance=task, 
            user=request.user, 
            is_creation=False
        )
        if form.is_valid():
            old_status = task.status
            saved_task = form.save(commit=False)
            saved_task.last_changed_by = request.user.employee
            saved_task.save()
            # Log status change
            from ...models import TaskComment
            employee = request.user.employee
            if old_status != saved_task.status:
                TaskComment.objects.create(
                    task=saved_task,
                    author=employee,
                    text=f"Status changed from '{old_status}' to '{saved_task.status}'"
                )
            messages.success(request, "Status successfully updated.")
            return redirect('tasks:my_tasks')          # â† Namespace korrigiert
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = PurchaseOrderTaskForm(
            instance=task, 
            user=request.user, 
            is_creation=False
        )

    # Approvers can mark items as Standard Orders without getting full edit rights
    is_approver = is_procurement_approver(request.user)

    employee = getattr(request.user, 'employee', None)
    is_archived_by_user = employee and employee in task.archived_by.all() if hasattr(task, 'archived_by') else False

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

