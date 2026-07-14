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
    
    can_delete = is_procurement_coordinator(request.user) or (
        task.creator == request.user.employee and 
        task.status in ['not_yet_processed', 'in_coordination']
    )

    if not can_delete:
        messages.error(request, "You are not allowed to delete this order.")
        return redirect('tasks:task_detail', pk=task.pk)

    if request.method == 'POST':
        supplier_name = getattr(task, 'supplier', task.title)
        task.delete()
        messages.success(request, f"Order '{supplier_name}' has been successfully deleted.")
        return redirect_to_my_tasks()

    return render(request, 'tasks/task_confirm_delete.html', {'task': task})

