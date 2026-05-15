"""
apps/tasks/views/detail/fulfiller.py

Project: THERESE - Transparent HR Employee Resource Evaluation System Enhanced

Features / Requirements:
- View for Fulfiller role (warehouse / order processing)
- Correct namespace usage ('tasks:my_tasks')
- Read-only for most fields, only status can be updated

Do not remove any existing requirements from this header without explicit instruction.
"""

from django.shortcuts import render, redirect
from django.contrib import messages

from ...forms import PurchaseOrderTaskForm


def fulfiller_task_detail(request, task):
    """Ansicht für Fulfiller (z. B. Wareneingang)"""
    if request.method == 'POST':
        form = PurchaseOrderTaskForm(
            request.POST, 
            instance=task, 
            user=request.user, 
            is_creation=False
        )
        if form.is_valid():
            saved_task = form.save(commit=False)
            saved_task.last_changed_by = request.user.employee
            saved_task.save()
            messages.success(request, "Status successfully updated.")
            return redirect('tasks:my_tasks')          # ← Namespace korrigiert
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = PurchaseOrderTaskForm(
            instance=task, 
            user=request.user, 
            is_creation=False
        )

    context = {
        'task': task,
        'form': form,
        'can_edit': True,           # Fulfiller darf Status ändern
        'is_fulfiller': True,
    }
    return render(request, 'tasks/detail/fulfiller.html', context)