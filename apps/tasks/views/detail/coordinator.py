"""
apps/tasks/views/detail/coordinator.py

Project: THERESE - Transparent HR Employee Resource Evaluation System Enhanced

Features / Requirements:
- Full edit view for Procurement Coordinator
- Correct namespace usage for redirects ('tasks:my_tasks')
- Proper form handling and success/error messages

Do not remove any existing requirements from this header without explicit instruction.
"""

from django.shortcuts import render, redirect
from django.contrib import messages

from ...forms import PurchaseOrderTaskForm


def coordinator_task_detail(request, task):
    """Voll editierbare Ansicht für Coordinator"""
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
            messages.success(request, "Changes have been saved successfully.")
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
        'can_edit': True,
        'is_coordinator': True,
    }
    return render(request, 'tasks/detail/coordinator.html', context)