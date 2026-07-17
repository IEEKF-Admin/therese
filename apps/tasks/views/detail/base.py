"""
apps/tasks/views/detail/base.py

Shared helpers for all task detail views.

get_task_or_404() loads the concrete task subclass with appropriate
select_related / prefetch_related and enforces type-specific visibility
before the role-specific view runs.
"""

from django.shortcuts import get_object_or_404
from django.contrib import messages

from ...models import (
    Task, PurchaseOrderTask, GenericTextTask,
    PersonnelReallocationTask, PersonnelContractExtensionTask,
    PersonnelRecruitmentTask,
)
from ...utils import can_view_personnel_task, can_view_purchase_order
from ..redirects import redirect_to_my_tasks


def _deny_view(request):
    messages.error(request, "You don't have permission to view this task.")
    return redirect_to_my_tasks()


def get_task_or_404(pk, user, request=None):
    """
    Load task by pk and apply basic visibility checks.

    Returns the concrete model instance, or an HttpResponse redirect when
    the user may not view the task.
    """
    base_task = get_object_or_404(Task, pk=pk)

    if base_task.task_type == 'purchase_order':
        task = PurchaseOrderTask.objects.select_related(
            'assignee', 'creator', 'wbs_element', 'last_changed_by'
        ).prefetch_related('items', 'comments', 'comments__author').get(pk=pk)

        if not can_view_purchase_order(user, task):
            return _deny_view(request or user)
        return task

    if base_task.task_type == 'generic_text':
        task = GenericTextTask.objects.select_related(
            'assignee', 'creator', 'recipient', 'last_changed_by'
        ).prefetch_related('comments', 'comments__author').get(pk=pk)
        employee = getattr(user, 'employee', None)
        if not (
            user.is_superuser
            or (employee and (task.creator == employee or task.recipient == employee))
        ):
            return _deny_view(request or user)
        return task

    if base_task.task_type == 'personnel_reallocation':
        task = PersonnelReallocationTask.objects.select_related(
            'assignee', 'creator', 'employee', 'last_changed_by'
        ).prefetch_related(
            'comments', 'comments__author',
            'funding_allocations__wbs_element', 'funding_allocations__cost_center',
        ).get(pk=pk)
        if not can_view_personnel_task(user, task):
            return _deny_view(request or user)
        return task

    if base_task.task_type == 'personnel_contract_extension':
        task = PersonnelContractExtensionTask.objects.select_related(
            'assignee', 'creator', 'employee', 'last_changed_by'
        ).prefetch_related('comments', 'comments__author').get(pk=pk)
        if not can_view_personnel_task(user, task):
            return _deny_view(request or user)
        return task

    if base_task.task_type == 'personnel_recruitment':
        task = PersonnelRecruitmentTask.objects.select_related(
            'job',
            'assignee', 'creator', 'created_employee', 'last_changed_by',
        ).prefetch_related(
            'comments', 'comments__author',
            'funding_allocations__wbs_element', 'funding_allocations__cost_center',
        ).get(pk=pk)
        if not can_view_personnel_task(user, task):
            return _deny_view(request or user)
        return task

    return base_task