"""
apps/tasks/utils.py
Helper functions for task permissions, visibility and status logic.
"""

from django.db.models import Q
from .models import PurchaseOrderTask


def is_procurement_coordinator(user):
    if not user or not user.is_authenticated:
        return False
    return user.groups.filter(name='Procurement Coordinator').exists()


def is_procurement_approver(user):
    if not user or not user.is_authenticated:
        return False
    return user.groups.filter(name='Procurement Approver').exists()


def can_view_purchase_order(user, task):
    """Entscheidet, ob ein User diese Bestellung sehen darf"""
    if not user or not user.is_authenticated:
        return False

    employee = getattr(user, 'employee', None)
    if not employee:
        return False

    if is_procurement_coordinator(user):
        return True

    # Jeder Ersteller sieht **immer** seine eigene Bestellung (unabhängig vom Status)
    if task.creator == employee:
        return True

    # Assignee sieht sie ab bestimmten Stati
    if task.assignee == employee:
        visible_statuses = {
            'coordination_completed', 'sent_to_administration',
            'ordered_from_supplier', 'received_in_warehouse',
            'delivered', 'completed'
        }
        return task.status in visible_statuses

    return False


def get_purchase_orders_queryset(user):
    """Zentrale Query für alle Purchase Orders"""
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

    # Normale Nutzer sehen:
    # - Alle eigenen Bestellungen (creator)
    # - Bestellungen, bei denen sie Assignee sind und Status weit genug
    visible = Q(creator=employee) | Q(
        assignee=employee,
        status__in=[
            'coordination_completed', 'sent_to_administration',
            'ordered_from_supplier', 'received_in_warehouse',
            'delivered', 'completed'
        ]
    )

    return queryset.filter(visible)


def can_change_status(user, task):
    if is_procurement_coordinator(user):
        return True
    if is_procurement_approver(user):
        return task.status in {'coordination_completed', 'sent_to_administration',
                               'ordered_from_supplier', 'received_in_warehouse', 'delivered'}
    return False


def can_edit_wbs_element(user):
    return is_procurement_coordinator(user)