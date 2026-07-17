"""Download, view, and delete employee document versions."""

import mimetypes

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse

from apps.core.http_utils import content_disposition, safe_redirect
from ..document_utils import user_can_manage_employee_documents, user_can_delete_document_version
from ..models import Employee, EmployeeDocumentVersion


def _get_permitted_version(request, employee_pk, version_pk):
    employee = get_object_or_404(Employee, pk=employee_pk)
    if not user_can_manage_employee_documents(request.user, employee):
        return None, None
    version = get_object_or_404(
        EmployeeDocumentVersion,
        pk=version_pk,
        employee=employee,
    )
    if not version.file:
        raise Http404("Document file not found.")
    return employee, version


def _file_response(version, *, as_attachment):
    content_type, _ = mimetypes.guess_type(version.original_filename)
    if not content_type or content_type in (
        'text/html', 'image/svg+xml', 'application/xhtml+xml',
    ):
        content_type = 'application/octet-stream'
        as_attachment = True
    response = FileResponse(
        version.file.open('rb'),
        as_attachment=as_attachment,
        filename=version.original_filename,
        content_type=content_type,
    )
    response['Content-Disposition'] = content_disposition(
        version.original_filename, as_attachment=as_attachment,
    )
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@login_required
def employee_document_download(request, employee_pk, version_pk):
    employee, version = _get_permitted_version(request, employee_pk, version_pk)
    if version is None:
        messages.error(request, "You do not have permission to download this document.")
        return redirect('tasks:my_tasks')
    return _file_response(version, as_attachment=True)


@login_required
def employee_document_view(request, employee_pk, version_pk):
    """Open document inline in the browser (PDF/image preview only)."""
    employee, version = _get_permitted_version(request, employee_pk, version_pk)
    if version is None:
        messages.error(request, "You do not have permission to view this document.")
        return redirect('tasks:my_tasks')
    return _file_response(version, as_attachment=False)


@login_required
def employee_document_delete(request, employee_pk, version_pk):
    employee = get_object_or_404(Employee, pk=employee_pk)
    version = get_object_or_404(
        EmployeeDocumentVersion,
        pk=version_pk,
        employee=employee,
    )
    if not user_can_delete_document_version(request.user, version):
        messages.error(request, "You do not have permission to delete this document.")
        return redirect('hr:employee_update', pk=employee_pk)

    version.file.delete(save=False)
    version.delete()
    messages.success(request, "Document version deleted.")
    next_url = request.GET.get('next')
    fallback = (
        reverse('hr:employee_update', kwargs={'pk': employee_pk})
        if request.user.has_perm('hr.manage_employee')
        else reverse('hr:my_profile')
    )
    if next_url:
        return safe_redirect(request, next_url, fallback=fallback)
    return redirect(fallback)
