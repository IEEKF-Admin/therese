"""Unopened (not yet initially viewed) tasks for coordinators and approvers."""

from django.db.models import Q

from .models import PERSONNEL_TASK_TYPES, Task, TaskInitialOpen
from .utils import (
    is_personnel_approver,
    is_personnel_coordinator,
    is_procurement_approver,
    is_procurement_coordinator,
)

CLOSED_STATUSES = frozenset({
    'delivered',
    'completed',
    'recruitment_completed',
    'done',
})


def mark_task_opened(user, task):
    if not user or not getattr(user, 'is_authenticated', False) or task is None:
        return
    TaskInitialOpen.objects.get_or_create(user=user, task=task)


def unopened_tasks_queryset(user):
    """Open tasks this user should look at and has not opened yet."""
    if not user or not user.is_authenticated:
        return Task.objects.none()
    employee = getattr(user, 'employee', None)
    if not employee:
        return Task.objects.none()

    is_pers_coord = is_personnel_coordinator(user)
    is_proc_coord = is_procurement_coordinator(user)
    is_pers_appr = is_personnel_approver(user)
    is_proc_appr = is_procurement_approver(user)
    if not (is_pers_coord or is_proc_coord or is_pers_appr or is_proc_appr):
        return Task.objects.none()

    opened_ids = TaskInitialOpen.objects.filter(user=user).values_list('task_id', flat=True)
    qs = (
        Task.objects.exclude(status__in=CLOSED_STATUSES)
        .exclude(archived_by=employee)
        .exclude(pk__in=opened_ids)
    )

    clauses = []
    if is_pers_appr:
        clauses.append(Q(assignee=employee, task_type__in=PERSONNEL_TASK_TYPES))
    if is_proc_appr:
        clauses.append(Q(assignee=employee, task_type='purchase_order'))
    if is_pers_coord:
        clauses.append(Q(assignee__isnull=True, task_type__in=PERSONNEL_TASK_TYPES))
    if is_proc_coord:
        clauses.append(Q(assignee__isnull=True, task_type='purchase_order'))
    if not clauses:
        return Task.objects.none()

    combined = clauses[0]
    for clause in clauses[1:]:
        combined |= clause
    return qs.filter(combined)


def unopened_tasks_for_user(user):
    return (
        unopened_tasks_queryset(user)
        .select_related('assignee', 'creator')
        .order_by('-created_at')
    )


def tasks_menu_needs_attention(user):
    if not user or not user.is_authenticated:
        return False
    return unopened_tasks_queryset(user).exists()
