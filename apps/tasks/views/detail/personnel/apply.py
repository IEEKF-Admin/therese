"""Apply reallocation funding allocations onto the employee record."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from apps.tasks.reallocation_apply import ApplyReallocationError, apply_reallocation_funding
from apps.tasks.task_protocol import record_task_update
from apps.tasks.utils import is_personnel_approver
from apps.tasks.views.detail.base import get_task_or_404
from apps.tasks.views.redirects import redirect_to_my_tasks


def _posted_map(post, prefix):
    collected = {}
    for key, value in post.items():
        if key.startswith(prefix):
            collected[key[len(prefix):]] = value
    return collected


@login_required
@require_POST
def apply_reallocation_funding_view(request, pk):
    """Write saved reallocation funding rows onto the employee's contract."""
    task = get_task_or_404(pk, request.user, request=request)
    from django.http import HttpResponseBase
    if isinstance(task, HttpResponseBase):
        return task

    if getattr(task, 'task_type', None) != 'personnel_reallocation':
        messages.error(request, 'Funding can only be applied from a reallocation task.')
        return redirect_to_my_tasks()

    if not is_personnel_approver(request.user):
        messages.error(request, "You don't have permission to apply reallocation funding.")
        return redirect('tasks:task_detail', pk=task.pk)

    if task.status != 'completed':
        messages.error(request, 'Funding can only be applied when the task status is Completed.')
        return redirect('tasks:task_detail', pk=task.pk)

    job_numbers = _posted_map(request.POST, 'apply_job_number-')
    continuation_choices = _posted_map(request.POST, 'apply_existing_choice-')
    try:
        created = apply_reallocation_funding(
            task,
            job_numbers=job_numbers,
            continuation_choices=continuation_choices,
        )
    except ApplyReallocationError as exc:
        messages.error(request, exc.message)
        return redirect('tasks:task_detail', pk=task.pk)

    employee = getattr(request.user, 'employee', None)
    if employee:
        task.last_changed_by = employee
        task.save(update_fields=['last_changed_by', 'last_status_change'])
        record_task_update(
            task,
            employee,
            new_message=(
                f'Applied funding allocations to {task.employee.get_full_name()} '
                f'({created} new allocation(s)).'
            ),
        )
    messages.success(request, 'Funding allocations were applied to the employee.')
    return redirect('tasks:task_detail', pk=task.pk)
