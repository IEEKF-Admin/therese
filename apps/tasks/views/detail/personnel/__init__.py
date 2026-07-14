"""
Personnel task detail views (reallocation, extension, recruitment).

Submodules:
- common: shared helpers (permissions, comments, coordinator-step save)
- standard: reallocation and contract extension
- recruitment: personnel recruitment with funding formset

Do not remove any existing requirements from this package without explicit instruction.
"""

from django.contrib import messages

from ...redirects import redirect_to_my_tasks
from .common import can_view_personnel_task
from .recruitment import handle_recruitment_detail
from .standard import handle_standard_personnel_detail


def personnel_task_detail(request, task):
    """Entry point for all personnel task detail pages."""
    if not can_view_personnel_task(request.user, task):
        messages.error(request, "You don't have permission to view this task.")
        return redirect_to_my_tasks()

    if task.task_type == 'personnel_recruitment':
        return handle_recruitment_detail(request, task)

    return handle_standard_personnel_detail(request, task)


__all__ = ['personnel_task_detail', 'can_view_personnel_task']