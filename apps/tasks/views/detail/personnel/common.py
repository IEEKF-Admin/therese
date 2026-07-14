"""
Shared helpers for personnel task detail views.

Do not remove any existing requirements from this module without explicit instruction.
"""

from django.contrib import messages

from ....personnel_documents import (
    can_download_personnel_documents,
    get_personnel_task_documents,
)
from ....task_protocol import extract_new_message, record_task_update
from ....utils import (
    is_personnel_coordinator,
    can_view_recruitment_task,
    personnel_approver_employees,
)
from ...redirects import redirect_to_my_tasks


def personnel_documents_context(request, task):
    """Build template context for the personnel documents download section."""
    can_download = can_download_personnel_documents(request.user)
    documents = get_personnel_task_documents(task) if can_download else []
    return {
        'can_download_personnel_documents': can_download,
        'personnel_documents': documents,
        'has_personnel_documents': bool(documents),
    }


def can_view_personnel_task(user, task):
    """Return True when the user may open a personnel task detail page."""
    if task.task_type == 'personnel_recruitment':
        return can_view_recruitment_task(user, task)

    employee = getattr(user, 'employee', None)
    if not employee:
        return False
    if user.is_superuser or is_personnel_coordinator(user):
        return True
    if task.creator == employee or task.assignee == employee:
        return True
    return False


def save_personnel_coordinator_steps(request, task, *, employee):
    """
    Persist assignee and status when the creator performs coordinator steps.

    Used for reallocation/extension when the creator has coordinator fallback and
    cannot edit the full form (employee, WBS, dates remain read-only).
    """
    assignee_raw = request.POST.get('assignee', '').strip()
    if assignee_raw:
        task.assignee = personnel_approver_employees().filter(pk=assignee_raw).first()
    else:
        task.assignee = None

    new_status = request.POST.get('status')
    if new_status:
        task.status = new_status
    if employee:
        task.last_changed_by = employee
    task.save()
    record_task_update(task, employee, new_message=extract_new_message(request))
    messages.success(request, "Task updated successfully.")
    return redirect_to_my_tasks()