"""
apps/tasks/views/detail/base.py
Gemeinsame Hilfsfunktionen für alle Detail-Views
"""

from django.shortcuts import get_object_or_404
from django.contrib import messages
from django.shortcuts import redirect

from ...models import Task, PurchaseOrderTask
from ...utils import can_view_purchase_order


def get_task_or_404(pk, user):
    """Lädt die Aufgabe und prüft grundlegende Sichtbarkeit"""
    base_task = get_object_or_404(Task, pk=pk)

    if base_task.task_type == 'purchase_order':
        task = PurchaseOrderTask.objects.select_related(
            'assignee', 'creator', 'wbs_element', 'last_changed_by'
        ).prefetch_related('items').get(pk=pk)

        if not can_view_purchase_order(user, task):
            messages.error(user, "You don't have permission to view this task.")
            return redirect('my_tasks')
        return task
    return base_task