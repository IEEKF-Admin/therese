"""Consistent redirects to the tasks dashboard (/tasks/)."""

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse

from ..models import Task


def redirect_to_my_tasks(*, permanent=False):
    """Redirect to the tasks overview (PRG-safe HTTP 303 after POST)."""
    url = reverse('tasks:my_tasks')
    if permanent:
        return HttpResponseRedirect(url, status=301)
    return HttpResponseRedirect(url, status=303)


def try_handle_archive_post(request):
    """
    Handle archive / unarchive POST from task detail pages.
    Returns a redirect response, or None if this POST is not an archive action.
    """
    if request.method != 'POST':
        return None

    task_id = request.POST.get('archive_task') or request.POST.get('archive_po')
    if not task_id:
        return None

    employee = getattr(request.user, 'employee', None)
    if not employee:
        messages.error(request, "Your user account has no linked employee profile.")
        return redirect_to_my_tasks()

    try:
        task = Task.objects.get(pk=task_id)
    except Task.DoesNotExist:
        messages.error(request, "Task not found.")
        return redirect_to_my_tasks()

    # Only allow archive toggle for tasks the user can already see.
    from .detail.base import get_task_or_404
    from django.http import HttpResponseBase

    visible = get_task_or_404(task.pk, request.user, request=request)
    if isinstance(visible, HttpResponseBase):
        return visible

    if request.POST.get('action') == 'unarchive':
        task.archived_by.remove(employee)
        messages.success(request, "Task removed from your archive.")
    else:
        task.archived_by.add(employee)
        messages.success(request, "Task moved to your archive.")

    return redirect_to_my_tasks()