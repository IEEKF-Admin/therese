"""
apps/tasks/views/delete.py
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from ..models import Task
from ..utils import is_procurement_coordinator
from .redirects import redirect_to_my_tasks


@login_required
def task_delete(request, pk):
    task = get_object_or_404(Task, pk=pk)
    employee = getattr(request.user, 'employee', None)

    # Procurement coordinators may only delete purchase orders.
    # Creators may delete their own task while still in early status.
    can_delete = False
    if is_procurement_coordinator(request.user) and task.task_type == 'purchase_order':
        can_delete = True
    elif employee and task.creator_id == employee.pk and task.status in (
        'not_yet_processed', 'in_coordination',
    ):
        can_delete = True

    if not can_delete:
        messages.error(request, "You are not allowed to delete this task.")
        return redirect('tasks:task_detail', pk=task.pk)

    if request.method == 'POST':
        supplier_name = getattr(task, 'supplier', task.title)
        task.delete()
        messages.success(request, f"Task '{supplier_name}' has been successfully deleted.")
        return redirect_to_my_tasks()

    return render(request, 'tasks/task_confirm_delete.html', {'task': task})
