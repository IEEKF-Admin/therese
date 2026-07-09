"""
apps/tasks/views/detail/personnel.py
Detail views for personnel task types.
"""

from django.shortcuts import render, redirect
from django.contrib import messages

from ...forms import (
    PersonnelReallocationTaskForm,
    PersonnelContractExtensionTaskForm,
    PersonnelRecruitmentTaskForm,
    RecruitmentFundingFormSet,
)
from ...models import RECRUITMENT_STATUS_ORDER
from ...recruitment_form_helpers import (
    build_recruitment_template_context,
    funding_formset_kwargs_from_post,
)
from ...personnel_documents import (
    can_download_personnel_documents,
    get_personnel_task_documents,
)
from ...utils import (
    is_personnel_coordinator,
    is_personnel_approver,
    can_view_recruitment_task,
    can_edit_recruitment_fields,
    can_edit_recruitment_status,
    can_create_employee_from_recruitment,
)


def _personnel_documents_context(request, task):
    can_download = can_download_personnel_documents(request.user)
    documents = get_personnel_task_documents(task) if can_download else []
    return {
        'can_download_personnel_documents': can_download,
        'personnel_documents': documents,
        'has_personnel_documents': bool(documents),
    }


def can_view_personnel_task(user, task):
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


def _log_task_changes(task, employee, old_status, saved, old_assignee_id):
    from ...models import TaskComment

    if old_status != saved.status:
        TaskComment.objects.create(
            task=saved,
            author=employee,
            text=f"Status changed from '{old_status}' to '{saved.status}'"
        )
    if old_assignee_id != saved.assignee_id:
        new_assignee = saved.assignee.get_full_name() if saved.assignee else "unassigned"
        TaskComment.objects.create(
            task=saved,
            author=employee,
            text=f"Assignee changed to {new_assignee}"
        )


def _handle_recruitment_detail(request, task):
    employee = getattr(request.user, 'employee', None)
    is_creator = task.creator == employee
    is_coordinator = is_personnel_coordinator(request.user)
    is_assignee = task.assignee == employee
    can_edit_fields = can_edit_recruitment_fields(request.user, task)
    can_edit_status = can_edit_recruitment_status(request.user, task)
    can_edit = can_edit_fields or can_edit_status
    can_set_assignee = is_coordinator
    form = None
    funding_formset = None

    if request.method == 'POST' and can_edit_status and not can_edit_fields:
        new_status = request.POST.get('status')
        old_status = task.status
        try:
            current_index = RECRUITMENT_STATUS_ORDER.index(old_status)
            new_index = RECRUITMENT_STATUS_ORDER.index(new_status)
        except ValueError:
            messages.error(request, "Invalid status value.")
        elif new_index <= current_index:
            messages.error(request, "Approvers may only move the status forward.")
        else:
            task.status = new_status
            if employee:
                task.last_changed_by = employee
            task.save(update_fields=['status', 'last_changed_by', 'last_status_change'])
            _log_task_changes(task, employee, old_status, task, task.assignee_id)
            messages.success(request, "Task updated successfully.")
            return redirect('tasks:task_detail', pk=task.pk)
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
            _log_task_changes(task, employee, old_status, saved, old_assignee_id)
            messages.success(request, "Task updated successfully.")
            return redirect('tasks:task_detail', pk=task.pk)
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
    }
    context.update(build_recruitment_template_context())
    context.update(_personnel_documents_context(request, task))
    return render(request, 'tasks/detail/recruitment.html', context)


def personnel_task_detail(request, task):
    employee = getattr(request.user, 'employee', None)

    if not can_view_personnel_task(request.user, task):
        messages.error(request, "You don't have permission to view this task.")
        return redirect('tasks:my_tasks')

    if task.task_type == 'personnel_recruitment':
        return _handle_recruitment_detail(request, task)

    task_type = task.task_type
    is_creator = task.creator == employee
    is_coordinator = is_personnel_coordinator(request.user)
    is_assignee = task.assignee == employee

    can_edit = (
        request.user.is_superuser
        or is_coordinator
        or is_assignee
    )
    can_set_assignee = is_coordinator

    if task_type == 'personnel_reallocation':
        form_class = PersonnelReallocationTaskForm
        template = 'tasks/detail/reallocation.html'
    elif task_type == 'personnel_contract_extension':
        form_class = PersonnelContractExtensionTaskForm
        template = 'tasks/detail/extension.html'
    else:
        messages.error(request, "Unknown personnel task type.")
        return redirect('tasks:my_tasks')

    if request.method == 'POST' and can_edit:
        form = form_class(
            request.POST,
            instance=task,
            user=request.user,
            is_creation=False,
        )
        if form.is_valid():
            old_status = task.status
            saved = form.save(commit=False)
            if employee:
                saved.last_changed_by = employee
            saved.save()
            _log_task_changes(task, employee, old_status, saved, task.assignee_id)
            messages.success(request, "Task updated successfully.")
            return redirect('tasks:my_tasks')
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
        'can_set_assignee': can_set_assignee,
        'is_creator': is_creator,
        'is_coordinator': is_coordinator,
        'task_type': task_type,
        'employee': employee,
        'is_archived_by_user': is_archived_by_user,
    }
    if task_type == 'personnel_contract_extension':
        context.update(build_recruitment_template_context())
    context.update(_personnel_documents_context(request, task))
    return render(request, template, context)