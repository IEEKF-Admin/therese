"""
apps/tasks/views/detail/coordinator.py

Project: THERESE - Transparent HR Employee Resource Evaluation System Enhanced

Features / Requirements:
- Full edit view for procurement coordinator (and creator coordinator fallback)
- Correct namespace usage for redirects ('tasks:my_tasks')
- Form handling with success/error messages and activity comments on WBS/status/assignee
- Distinguish true coordinator vs creator fallback in template context

Do not remove any existing requirements from this header without explicit instruction.
"""

from django.shortcuts import render
from django.contrib import messages

from ...forms import PurchaseOrderTaskForm
from ...task_protocol import extract_new_message, record_task_update
from ...workflow_config import creator_has_coordinator_fallback
from ..redirects import redirect_to_my_tasks


def coordinator_task_detail(request, task):
    """Fully editable purchase order view for coordinators (or creator fallback)."""
    if request.method == 'POST':
        form = PurchaseOrderTaskForm(
            request.POST,
            instance=task,
            user=request.user,
            is_creation=False,
        )
        if form.is_valid():
            saved_task = form.save(commit=False)
            employee = request.user.employee
            saved_task.last_changed_by = employee
            saved_task.save()
            record_task_update(
                saved_task,
                employee,
                new_message=extract_new_message(request),
            )
            messages.success(request, "Changes have been saved successfully.")
            return redirect_to_my_tasks()
        messages.error(request, "Please correct the errors below.")
    else:
        form = PurchaseOrderTaskForm(
            instance=task,
            user=request.user,
            is_creation=False,
        )

    employee = getattr(request.user, 'employee', None)
    is_archived_by_user = (
        employee and employee in task.archived_by.all()
        if hasattr(task, 'archived_by')
        else False
    )
    coordinator_fallback = creator_has_coordinator_fallback(request.user, task)

    context = {
        'task': task,
        'form': form,
        'can_edit': True,
        'is_coordinator': not coordinator_fallback,
        'is_creator': task.creator == employee,
        'coordinator_fallback': coordinator_fallback,
        'employee': employee,
        'is_archived_by_user': is_archived_by_user,
    }
    return render(request, 'tasks/detail/coordinator.html', context)