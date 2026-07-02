"""
apps/tasks/utils.py
Helper functions for task permissions, visibility and status logic.
"""

from django.db.models import Q
from .models import PurchaseOrderTask
# GroupNames removed - using permissions now


def is_procurement_coordinator(user):
    if not user or not user.is_authenticated:
        return False
    return user.is_superuser or user.has_perm('tasks.view_all_purchase_orders') or user.has_perm('tasks.change_wbs_on_purchase_order')


def is_procurement_approver(user):
    if not user or not user.is_authenticated:
        return False
    # Approver typically has specific rights, here we use a reasonable check
    # For simplicity we can keep group or use a perm if added, but for now use existing logic
    return user.has_perm('tasks.view_all_purchase_orders') or user.has_perm('tasks.change_wbs_on_purchase_order')


def can_view_purchase_order(user, task):
    """Entscheidet, ob ein User diese Bestellung sehen darf"""
    if not user or not user.is_authenticated:
        return False

    employee = getattr(user, 'employee', None)
    if not employee:
        return False

    if is_procurement_coordinator(user):
        return True

    # Jeder Ersteller sieht **immer** seine eigene Bestellung
    if task.creator == employee:
        return True

    if is_procurement_approver(user):
        # Approver sehen Bestellungen sobald ein WBS-Element gesetzt wurde
        # (auch wenn sie jemand anderem zugewiesen sind)
        if task.wbs_element_id is not None:
            return True
    else:
        # Normale Nutzer nur, wenn sie selbst Assignee sind und WBS gesetzt
        if (task.assignee == employee and task.wbs_element_id is not None):
            return True

    return False


def get_purchase_orders_queryset(user):
    """Zentrale Query fÃ¼r alle Purchase Orders"""
    if not user or not user.is_authenticated:
        return PurchaseOrderTask.objects.none()

    employee = getattr(user, 'employee', None)
    if not employee:
        return PurchaseOrderTask.objects.none()

    queryset = PurchaseOrderTask.objects.select_related(
        'assignee', 'creator', 'wbs_element'
    ).order_by('-created_at')

    if is_procurement_coordinator(user):
        return queryset  # Coordinator sieht alles

    # Jeder sieht immer seine eigenen Bestellungen
    visible = Q(creator=employee)

    if is_procurement_approver(user):
        # Approver sehen zusÃ¤tzlich alle Bestellungen, sobald WBS gesetzt ist
        # (auch wenn sie jemand anderem assigned sind)
        approver_visible = Q(wbs_element__isnull=False)
        visible |= approver_visible
    else:
        # Normale Nutzer (inkl. Fulfiller etc.) sehen Bestellungen nur,
        # wenn sie selbst Assignee sind und WBS gesetzt ist
        visible |= Q(
            assignee=employee,
            wbs_element__isnull=False
        )

    return queryset.filter(visible)


def can_change_status(user, task):
    if is_procurement_coordinator(user):
        return True
    if is_procurement_approver(user):
        # Approver can change status once WBS is set
        return task.wbs_element_id is not None
    return False


def can_edit_wbs_element(user):
    return is_procurement_coordinator(user)


def can_create_purchase_order(user):
    """
    Users who are allowed to create Purchase Orders.
    This group can also access the Standard Orders catalog when creating a PO.
    """
    if not user or not user.is_authenticated:
        return False

    return (
        user.is_superuser or
        user.has_perm('tasks.create_purchase_order') or
        user.has_perm('tasks.view_all_purchase_orders')
    )

