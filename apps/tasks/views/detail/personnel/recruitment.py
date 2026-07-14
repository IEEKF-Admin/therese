"""
Personnel recruitment task detail view.

Do not remove any existing requirements from this module without explicit instruction.
"""

from django.contrib import messages
from django.shortcuts import render

from ....forms import PersonnelRecruitmentTaskForm, RecruitmentFundingFormSet
from ....models import RECRUITMENT_STATUS_ORDER
from ....recruitment_form_helpers import (
    build_recruitment_template_context,
    funding_formset_kwargs_from_post,
)
from ....utils import (
    can_create_employee_from_recruitment,
    can_edit_recruitment_fields,
    can_edit_recruitment_status,
    is_personnel_approver,
    is_personnel_coordinator,
)
from ....workflow_config import creator_has_coordinator_fallback
from ...redirects import redirect_to_my_tasks
from .common import log_task_changes, personnel_documents_context


def handle_recruitment_detail(request, task):
    """Render and process the personnel recruitment task detail page."""
    employee = getattr(request.user, 'employee', None)
    is_creator = task.creator == employee
    is_coordinator = is_personnel_coordinator(request.user)
    is_assignee = task.assignee == employee
    can_edit_fields = can_edit_recruitment_fields(request.user, task)
    can_edit_status = can_edit_recruitment_status(request.user, task)
    can_edit = can_edit_fields or can_edit_status
    coordinator_fallback = is_creator and creator_has_coordinator_fallback(request.user, task)
    can_set_assignee = is_coordinator or coordinator_fallback
    form = None
    funding_formset = None

    # POST: approver assignee — status forward-only (no full field edit).
    if request.method == 'POST' and can_edit_status and not can_edit_fields:
        new_status = request.POST.get('status')
        old_status = task.status
        try:
            current_index = RECRUITMENT_STATUS_ORDER.index(old_status)
            new_index = RECRUITMENT_STATUS_ORDER.index(new_status)
        except ValueError:
            messages.error(request, "Invalid status value.")
        else:
            if new_index <= current_index:
                messages.error(request, "Approvers may only move the status forward.")
            else:
                task.status = new_status
                if employee:
                    task.last_changed_by = employee
                task.save(update_fields=['status', 'last_changed_by', 'last_status_change'])
                log_task_changes(task, employee, old_status, task, task.assignee_id)
                messages.success(request, "Task updated successfully.")
                return redirect_to_my_tasks()

    # POST: coordinator, creator fallback, or creator while not_yet_processed.
    elif request.method == 'POST' and can_edit_fields:
        form = PersonnelRecruitmentTaskForm(
            request.POST,
            request.FILES,
            instance=task,
            user=request.user,
            is_creation=False,
        )
        funding_formset = RecruitmentFundingFormSet(
            request.POST,
            instance=task,
            **funding_formset_kwargs_from_post(request.POST, is_creation=False),
        )
        if form.is_valid() and funding_formset.is_valid():
            old_status = task.status
            old_assignee_id = task.assignee_id
            saved = form.save(commit=False)
            if employee:
                saved.last_changed_by = employee
            saved.save()
            funding_formset.instance = saved
            funding_formset.save()
            log_task_changes(task, employee, old_status, saved, old_assignee_id)
            messages.success(request, "Task updated successfully.")
            return redirect_to_my_tasks()
        messages.error(request, "Please correct the errors below.")

    else:
        form = PersonnelRecruitmentTaskForm(
            instance=task,
            user=request.user,
            is_creation=False,
        )
        funding_formset = RecruitmentFundingFormSet(
            instance=task,
            job=task.job,
            contract_dates={
                'valid_from': task.valid_from,
                'valid_until': task.valid_until,
            },
            is_creation=False,
        )

    if form is None:
        form = PersonnelRecruitmentTaskForm(
            instance=task,
            user=request.user,
            is_creation=False,
        )
    if funding_formset is None:
        funding_formset = RecruitmentFundingFormSet(
            instance=task,
            job=task.job,
            contract_dates={
                'valid_from': task.valid_from,
                'valid_until': task.valid_until,
            },
            is_creation=False,
        )

    is_archived_by_user = employee and employee in task.archived_by.all()

    context = {
        'task': task,
        'form': form,
        'funding_formset': funding_formset,
        'can_edit': can_edit,
        'can_edit_fields': can_edit_fields,
        'can_edit_status': can_edit_status,
        'can_set_assignee': can_set_assignee,
        'is_creator': is_creator,
        'is_coordinator': is_coordinator,
        'is_assignee': is_assignee,
        'task_type': task.task_type,
        'employee': employee,
        'is_archived_by_user': is_archived_by_user,
        'can_create_employee': can_create_employee_from_recruitment(request.user, task),
        'created_employee': task.created_employee,
        'is_creation': False,
        'coordinator_fallback': coordinator_fallback,
    }
    context.update(build_recruitment_template_context())
    context.update(personnel_documents_context(request, task))
    return render(request, 'tasks/detail/recruitment.html', context)