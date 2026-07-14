"""
Quote PDF download and replacement for purchase orders.

Do not remove any existing requirements from this module without explicit instruction.
"""

import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponseBase
from django.shortcuts import get_object_or_404, redirect

from ..forms import PurchaseOrderQuoteReplaceForm
from ..models import PurchaseOrderTask, TaskComment
from ..utils import can_view_purchase_order
from .detail.base import get_task_or_404
from .redirects import redirect_to_my_tasks


def _quote_download_filename(task):
    if task.quote_file and task.quote_file.name:
        return os.path.basename(task.quote_file.name)
    return 'quote.pdf'


@login_required
def purchase_order_quote_download(request, pk):
    task = get_task_or_404(pk, request.user)
    if isinstance(task, HttpResponseBase):
        return task
    if not isinstance(task, PurchaseOrderTask):
        raise Http404
    if not can_view_purchase_order(request.user, task):
        messages.error(request, "You don't have permission to download this quote.")
        return redirect_to_my_tasks()
    if not task.quote_file:
        raise Http404
    return FileResponse(
        task.quote_file.open('rb'),
        as_attachment=True,
        filename=_quote_download_filename(task),
        content_type='application/pdf',
    )


@login_required
def purchase_order_quote_replace(request, pk):
    task = get_object_or_404(PurchaseOrderTask, pk=pk)
    employee = getattr(request.user, 'employee', None)
    if not employee or task.creator_id != employee.pk:
        messages.error(request, "Only the creator can replace the quote file.")
        return redirect_to_my_tasks()

    if request.method != 'POST':
        return redirect_to_my_tasks()

    form = PurchaseOrderQuoteReplaceForm(request.POST, request.FILES, instance=task)
    if form.is_valid():
        form.save()
        TaskComment.objects.create(
            task=task,
            author=employee,
            text='Quote file updated.',
        )
        messages.success(request, 'Quote file updated successfully.')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f'{field}: {error}')
    return redirect('tasks:task_detail', pk=pk)