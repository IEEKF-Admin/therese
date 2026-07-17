"""
apps/tasks/views/router.py

Project: THERESE - Transparent HR Employee Resource Evaluation System Enhanced

Features / Requirements:
- Central entry point for all task detail views
- Route by task type first (generic, personnel), then by user role
- Procurement coordinator view takes precedence for purchase orders
- Creator coordinator fallback when no workgroup coordinators are configured
- Archive POST handling before routing
- Permission denied redirects to my_tasks with message

Do not remove any existing requirements from this header without explicit instruction.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required

from ..utils import is_procurement_coordinator
from ..workflow_config import creator_has_coordinator_fallback
from .detail.base import get_task_or_404
from .redirects import redirect_to_my_tasks, try_handle_archive_post


@login_required
def task_detail(request, pk):
    """
    Route the user to the appropriate task detail view.

    Order of checks:
    1. Archive/unarchive POST (any task type)
    2. Load task with type-specific queryset and visibility rules
    3. Task-type branches: generic_text, personnel_*
    4. Purchase order role branches: coordinator, creator+fallback, requester, fulfiller
    """
    archive_response = try_handle_archive_post(request)
    if archive_response is not None:
        return archive_response

    task = get_task_or_404(pk, request.user, request=request)
    from django.http import HttpResponseBase
    if isinstance(task, HttpResponseBase):
        return task

    from ..task_protocol import try_handle_message_only_post
    message_response = try_handle_message_only_post(request, task)
    if message_response is not None:
        return message_response

    # General requests use a dedicated detail flow (creator / recipient).
    if getattr(task, 'task_type', None) == 'generic_text':
        from .detail.generic import generic_task_detail
        return generic_task_detail(request, task)

    # Personnel tasks: reallocation, contract extension, recruitment.
    if getattr(task, 'task_type', None) in (
        'personnel_reallocation', 'personnel_contract_extension', 'personnel_recruitment',
    ):
        from .detail.personnel import personnel_task_detail
        return personnel_task_detail(request, task)

    # Procurement coordinator (purchase orders only).
    if is_procurement_coordinator(request.user):
        from .detail.coordinator import coordinator_task_detail
        return coordinator_task_detail(request, task)

    # Creator acts as coordinator when none configured for their workgroup.
    if (
        hasattr(task, 'creator')
        and task.creator == request.user.employee
        and creator_has_coordinator_fallback(request.user, task)
    ):
        from .detail.coordinator import coordinator_task_detail
        return coordinator_task_detail(request, task)

    # Creator (requester) — read-only purchase order view.
    if hasattr(task, 'creator') and task.creator == request.user.employee:
        from .detail.requester import requester_task_detail
        return requester_task_detail(request, task)

    # Assignee (fulfiller) — limited edit (e.g. status).
    if hasattr(task, 'assignee') and task.assignee == request.user.employee:
        from .detail.fulfiller import fulfiller_task_detail
        return fulfiller_task_detail(request, task)

    messages.error(request, "You don't have permission to view this task.")
    return redirect_to_my_tasks()