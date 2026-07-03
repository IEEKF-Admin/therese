"""Download and delete employee document versions."""

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect

from ..document_utils import user_can_manage_employee_documents, user_can_delete_document_version
from ..models import Employee, EmployeeDocumentVersion


@login_required
def employee_document_download(request, employee_pk, version_pk):
    employee = get_object_or_404(Employee, pk=employee_pk)
    if not user_can_manage_employee_documents(request.user, employee):
        messages.error(request, "You do not have permission to download this document.")
        return redirect('tasks:my_tasks')

    version = get_object_or_404(
        EmployeeDocumentVersion,
        pk=version_pk,
        employee=employee,
    )
    if not version.file:
        raise Http404("Document file not found.")
    return FileResponse(version.file.open('rb'), as_attachment=True, filename=version.original_filename)


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
    if next_url:
        return redirect(next_url)
    if request.user.has_perm('hr.manage_employee'):
        return redirect('hr:employee_update', pk=employee_pk)
    return redirect('hr:my_profile')