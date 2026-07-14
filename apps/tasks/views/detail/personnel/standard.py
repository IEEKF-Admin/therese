"""
Personnel reallocation and contract extension detail views.

Do not remove any existing requirements from this module without explicit instruction.
"""

from django.contrib import messages
from django.shortcuts import render

from ....forms import (
    PersonnelContractExtensionTaskForm,
    PersonnelReallocationTaskForm,
)
from ....recruitment_form_helpers import build_recruitment_template_context
from ....utils import is_personnel_coordinator
from ....workflow_config import creator_has_coordinator_fallback
from ...redirects import redirect_to_my_tasks
from ....task_protocol import extract_new_message, record_task_update
from .common import (
    personnel_documents_context,
    save_personnel_coordinator_steps,
)


def handle_standard_personnel_detail(request, task):
    """Render and process reallocation or contract extension task detail."""
    employee = getattr(request.user, 'employee', None)
    task_type = task.task_type
    is_creator = task.creator == employee
    is_coordinator = is_personnel_coordinator(request.user)
    coordinator_fallback = is_creator and creator_has_coordinator_fallback(request.user, task)

    can_edit = (
        request.user.is_superuser
        or is_coordinator
        or task.assignee == employee
    )
    can_edit_coordinator_steps = is_coordinator or coordinator_fallback
    can_set_assignee = is_coordinator or coordinator_fallback

    if task_type == 'personnel_reallocation':
        form_class = PersonnelReallocationTaskForm
        template = 'tasks/detail/reallocation.html'
    elif task_type == 'personnel_contract_extension':
        form_class = PersonnelContractExtensionTaskForm
        template = 'tasks/detail/extension.html'
    else:
        messages.error(request, "Unknown personnel task type.")
        return redirect_to_my_tasks()

    # POST: coordinator / creator fallback — assignee + status + comment only.
    if request.method == 'POST' and can_edit_coordinator_steps and not can_edit:
        return save_personnel_coordinator_steps(request, task, employee=employee)

    # POST: full form save (coordinator, assignee, or superuser).
    if request.method == 'POST' and can_edit:
        form = form_class(
            request.POST,
            instance=task,
            user=request.user,
            is_creation=False,
        )
        if form.is_valid():
            saved = form.save(commit=False)
            if employee:
                saved.last_changed_by = employee
            saved.save()
            record_task_update(
                saved,
                employee,
                new_message=extract_new_message(request),
            )
            messages.success(request, "Task updated successfully.")
            return redirect_to_my_tasks()
        messages.error(request, "Please correct the errors below.")
    else:
        form = form_class(
            instance=task,
            user=request.user,
            is_creation=False,
        )

    is_archived_by_user = employee and employee in task.archived_by.all()

    context = {
        'task': task,
        'form': form,
        'can_edit': can_edit,
        'can_edit_coordinator_steps': can_edit_coordinator_steps,
        'can_set_assignee': can_set_assignee,
        'is_creator': is_creator,
        'is_coordinator': is_coordinator,
        'coordinator_fallback': coordinator_fallback,
        'task_type': task_type,
        'employee': employee,
        'is_archived_by_user': is_archived_by_user,
    }
    if task_type == 'personnel_contract_extension':
        context.update(build_recruitment_template_context())
    context.update(personnel_documents_context(request, task))
    return render(request, template, context)