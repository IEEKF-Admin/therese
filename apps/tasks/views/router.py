"""
apps/tasks/views/detail.py
Zentraler Einstiegspunkt für alle Task-Detailansichten
"""

from django.shortcuts import redirect
from django.contrib import messages
from ..utils import is_procurement_coordinator
from .detail.base import get_task_or_404


def task_detail(request, pk):
    """Router – leitet je nach Rolle zur passenden Detail-View weiter"""
    task = get_task_or_404(pk, request.user)

    # Special handling for General Requests
    if getattr(task, 'task_type', None) == 'generic_text':
        from .detail.generic import generic_task_detail
        return generic_task_detail(request, task)

    # Personnel tasks (Reallocation + Contract Extension)
    if getattr(task, 'task_type', None) in ('personnel_reallocation', 'personnel_contract_extension'):
        from .detail.personnel import personnel_task_detail
        return personnel_task_detail(request, task)

    # Coordinator hat Vorrang (only relevant for purchase orders)
    if is_procurement_coordinator(request.user):
        from .detail.coordinator import coordinator_task_detail
        return coordinator_task_detail(request, task)

    # Creator (Requester) → Read-Only
    if hasattr(task, 'creator') and task.creator == request.user.employee:
        from .detail.requester import requester_task_detail
        return requester_task_detail(request, task)

    # Assignee (Fulfiller)
    if hasattr(task, 'assignee') and task.assignee == request.user.employee:
        from .detail.fulfiller import fulfiller_task_detail
        return fulfiller_task_detail(request, task)

    # Fallback
    messages.error(request, "You don't have permission to view this task.")
    return redirect('tasks:my_tasks')