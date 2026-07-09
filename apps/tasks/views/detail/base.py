"""
apps/tasks/views/detail/base.py
Gemeinsame Hilfsfunktionen fÃ¼r alle Detail-Views
"""

from django.shortcuts import get_object_or_404
from django.contrib import messages
from django.shortcuts import redirect

from ...models import (
    Task, PurchaseOrderTask, GenericTextTask,
    PersonnelReallocationTask, PersonnelContractExtensionTask,
    PersonnelRecruitmentTask,
)
from ...utils import can_view_purchase_order


def get_task_or_404(pk, user):
    """LÃ¤dt die Aufgabe und prÃ¼ft grundlegende Sichtbarkeit"""
    base_task = get_object_or_404(Task, pk=pk)

    if base_task.task_type == 'purchase_order':
        task = PurchaseOrderTask.objects.select_related(
            'assignee', 'creator', 'wbs_element', 'last_changed_by'
        ).prefetch_related('items', 'comments', 'comments__author').get(pk=pk)

        if not can_view_purchase_order(user, task):
            messages.error(user, "You don't have permission to view this task.")
            return redirect('my_tasks')
        return task

    if base_task.task_type == 'generic_text':
        task = GenericTextTask.objects.select_related(
            'assignee', 'creator', 'recipient', 'last_changed_by'
        ).prefetch_related('comments', 'comments__author').get(pk=pk)
        employee = getattr(user, 'employee', None)
        if not (user.is_staff or 
                (employee and (task.creator == employee or task.recipient == employee))):
            messages.error(user, "You don't have permission to view this task.")
            return redirect('my_tasks')
        return task

    if base_task.task_type == 'personnel_reallocation':
        task = PersonnelReallocationTask.objects.select_related(
            'assignee', 'creator', 'employee', 'target_wbs', 'last_changed_by'
        ).prefetch_related('comments', 'comments__author').get(pk=pk)
        return task

    if base_task.task_type == 'personnel_contract_extension':
        task = PersonnelContractExtensionTask.objects.select_related(
            'assignee', 'creator', 'employee', 'last_changed_by'
        ).prefetch_related('comments', 'comments__author').get(pk=pk)
        return task

    if base_task.task_type == 'personnel_recruitment':
        task = PersonnelRecruitmentTask.objects.select_related(
            'job',
            'assignee', 'creator', 'created_employee', 'last_changed_by',
        ).prefetch_related(
            'comments', 'comments__author', 'funding_allocations__wbs_element',
        ).get(pk=pk)
        return task

    return base_task

