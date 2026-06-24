"""
apps/tasks/views/detail/requester.py
Für den Ersteller (Procurement Requester) – Read-Only
"""

from django.shortcuts import render
from ...forms import PurchaseOrderTaskForm
from .base import get_task_or_404
from ...utils import is_procurement_approver


def requester_task_detail(request, task):
    """Read-Only Ansicht für den Ersteller"""
    form = PurchaseOrderTaskForm(
        instance=task, user=request.user, is_creation=False
    )

    is_approver = is_procurement_approver(request.user)

    employee = getattr(request.user, 'employee', None)
    is_archived_by_user = employee and employee in task.archived_by.all() if hasattr(task, 'archived_by') else False

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