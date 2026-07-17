"""Download views for personnel task documents."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from .redirects import redirect_to_my_tasks

from ..personnel_documents import (
    PERSONNEL_TASK_TYPES,
    build_zip_response,
    can_download_personnel_documents,
    get_personnel_document_by_key,
    get_personnel_task_documents,
)
from .detail.base import get_task_or_404


def _get_personnel_task(request, pk):
    task = get_task_or_404(pk, request.user, request=request)
    from django.http import HttpResponseBase
    if isinstance(task, HttpResponseBase):
        return task
    if getattr(task, 'task_type', None) not in PERSONNEL_TASK_TYPES:
        raise Http404('Not a personnel task.')
    return task


def _deny_download(request):
    messages.error(request, 'Sie haben keine Berechtigung, diese Dokumente herunterzuladen.')
    return redirect_to_my_tasks()


@login_required
def personnel_task_document_download(request, pk, doc_key):
    task = _get_personnel_task(request, pk)
    from django.http import HttpResponseBase
    if isinstance(task, HttpResponseBase):
        return task
    if not can_download_personnel_documents(request.user, task):
        return _deny_download(request)

    document = get_personnel_document_by_key(task, doc_key)
    if document is None:
        raise Http404('Document not found.')

    return FileResponse(
        document.open(),
        as_attachment=True,
        filename=document.download_filename,
    )


@login_required
def personnel_task_documents_zip(request, pk):
    task = _get_personnel_task(request, pk)
    from django.http import HttpResponseBase
    if isinstance(task, HttpResponseBase):
        return task
    if not can_download_personnel_documents(request.user, task):
        return _deny_download(request)

    result = build_zip_response(task)
    if result is None:
        raise Http404('No documents available.')

    buffer, zip_filename = result
    response = FileResponse(buffer, as_attachment=True, filename=zip_filename)
    response['Content-Type'] = 'application/zip'
    return response