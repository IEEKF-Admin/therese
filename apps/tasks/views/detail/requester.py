"""
apps/tasks/views/detail/requester.py

Project: THERESE - Transparent HR Employee Resource Evaluation System Enhanced

Features / Requirements:
- Read-only detail view for the purchase order creator (requester)
- Form rendered disabled for display; no POST handling
- Approvers who are also creators may see standard-order checkboxes in template

Do not remove any existing requirements from this header without explicit instruction.
"""

from django.shortcuts import render

from ...forms import PurchaseOrderTaskForm
from ...utils import is_procurement_approver


def requester_task_detail(request, task):
    """Read-only purchase order view for the task creator."""
    form = PurchaseOrderTaskForm(
        instance=task, user=request.user, is_creation=False
    )

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
        'can_edit': False,
        'is_creator': True,
        'show_standard_checkboxes': is_approver,
        'employee': employee,
        'is_archived_by_user': is_archived_by_user,
    }
    return render(request, 'tasks/detail/requester.html', context)