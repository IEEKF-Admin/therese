"""
apps/tasks/views/detail/requester.py
Für den Ersteller (Procurement Requester) – Read-Only
"""

from django.shortcuts import render
from ...forms import PurchaseOrderTaskForm
from .base import get_task_or_404


def requester_task_detail(request, task):
    """Read-Only Ansicht für den Ersteller"""
    form = PurchaseOrderTaskForm(
        instance=task, user=request.user, is_creation=False
    )

    context = {
        'task': task,
        'form': form,
        'can_edit': False,
        'is_creator': True,
    }
    return render(request, 'tasks/detail/requester.html', context)