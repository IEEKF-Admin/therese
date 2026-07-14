"""
Task activity protocol and user messages (TaskComment timeline).

Do not remove any existing requirements from this module without explicit instruction.
"""

from django.contrib import messages
from django.shortcuts import redirect

from apps.tasks.models import TaskComment

ENTRY_CREATED = TaskComment.ENTRY_CREATED
ENTRY_EDITED = TaskComment.ENTRY_EDITED
ENTRY_USER_MESSAGE = TaskComment.ENTRY_USER_MESSAGE


def author_username(employee):
    if employee and getattr(employee, 'user', None):
        return employee.user.username
    return 'unknown'


def log_task_created(task, author):
    TaskComment.objects.create(
        task=task,
        author=author,
        entry_type=ENTRY_CREATED,
        text='',
    )


def log_task_edited(task, author):
    TaskComment.objects.create(
        task=task,
        author=author,
        entry_type=ENTRY_EDITED,
        text='',
    )


def log_user_message(task, author, message):
    text = (message or '').strip()
    if not text:
        return None
    return TaskComment.objects.create(
        task=task,
        author=author,
        entry_type=ENTRY_USER_MESSAGE,
        text=text,
    )


def extract_new_message(request):
    return (request.POST.get('new_message') or '').strip()


def extract_initial_message(request):
    return (request.POST.get('initial_message') or '').strip()


def record_task_creation(task, author, *, initial_message=''):
    log_task_created(task, author)
    log_user_message(task, author, initial_message)


def record_task_update(task, author, *, new_message=''):
    log_task_edited(task, author)
    log_user_message(task, author, new_message)


def try_handle_message_only_post(request, task):
    """Handle standalone timeline message POST (read-only detail views)."""
    if request.method != 'POST' or not request.POST.get('add_message_only'):
        return None
    employee = getattr(request.user, 'employee', None)
    if not employee:
        messages.error(request, 'You need an employee profile to post messages.')
        return redirect('tasks:task_detail', pk=task.pk)
    msg = extract_new_message(request)
    if msg:
        log_user_message(task, employee, msg)
        messages.success(request, 'Message added.')
    return redirect('tasks:task_detail', pk=task.pk)