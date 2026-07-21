"""Helpers for employee document versioning and recruitment document transfer."""

import os

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile

from .models import Employee, EmployeeDocumentType, EmployeeDocumentVersion

from apps.core.upload_validation import (
    IMAGE_EXT,
    MAX_DEFAULT_UPLOAD_BYTES,
    PDF_EXT,
    validate_upload,
)

MAX_DOCUMENT_SIZE_BYTES = MAX_DEFAULT_UPLOAD_BYTES
ALLOWED_DOCUMENT_EXTENSIONS = PDF_EXT | IMAGE_EXT


def validate_personnel_document(uploaded_file):
    validate_upload(
        uploaded_file,
        allowed_extensions=ALLOWED_DOCUMENT_EXTENSIONS,
        max_bytes=MAX_DOCUMENT_SIZE_BYTES,
        require_magic=True,
    )


DOCUMENT_TYPE_DEFINITIONS = [
    {
        'type': EmployeeDocumentType.APPLICATION,
        'label_en': 'Application',
        'label_de': 'Bewerbung',
        'upload_field': 'upload_application',
    },
    {
        'type': EmployeeDocumentType.CV,
        'label_en': 'Curriculum Vitae',
        'label_de': 'Lebenslauf',
        'upload_field': 'upload_cv',
    },
    {
        'type': EmployeeDocumentType.LATEST_DEGREE_CERTIFICATE,
        'label_en': 'Latest Degree Certificate',
        'label_de': 'Zeugnis des letzten Abschlusses',
        'upload_field': 'upload_latest_degree_certificate',
    },
    {
        'type': EmployeeDocumentType.SCAN_OF_CONTRACT,
        'label_en': 'Scan of Contract',
        'label_de': 'Vertragsscan',
        'upload_field': 'upload_scan_of_contract',
    },
    {
        'type': EmployeeDocumentType.PROFILE_PICTURE,
        'label_en': 'Profile Picture',
        'label_de': 'Profilbild',
        'upload_field': 'upload_profile_picture',
    },
]


def get_document_versions_by_type(employee):
    grouped = {item['type']: [] for item in DOCUMENT_TYPE_DEFINITIONS}
    if not employee or not employee.pk:
        return grouped
    for version in employee.document_versions.select_related('uploaded_by').all():
        grouped.setdefault(version.document_type, []).append(version)
    return grouped


def get_document_blocks_for_template(employee):
    grouped = get_document_versions_by_type(employee)
    blocks = []
    for definition in DOCUMENT_TYPE_DEFINITIONS:
        versions = list(grouped.get(definition['type'], []))
        # Ordering is newest first; first entry is the current/relevant document.
        version_rows = [
            {
                'version': version,
                'is_current': index == 0,
            }
            for index, version in enumerate(versions)
        ]
        blocks.append({
            **definition,
            'versions': versions,
            'version_rows': version_rows,
        })
    return blocks


def _sync_current_employee_file(employee, document_type, stored_file):
    """
    Keep legacy Employee FileFields pointing at the latest version (current doc).
    Older versions remain in EmployeeDocumentVersion and are never deleted on upload.
    """
    if not stored_file:
        return
    if document_type == EmployeeDocumentType.SCAN_OF_CONTRACT:
        field_name = 'scan_of_contract'
    elif document_type == EmployeeDocumentType.PROFILE_PICTURE:
        field_name = 'profile_picture'
    else:
        return
    # Point at the same stored path as the version file (no re-upload / overwrite of history).
    setattr(employee, field_name, stored_file.name)
    employee.save(update_fields=[field_name, 'updated_at'])


def create_document_version(employee, document_type, uploaded_file, uploaded_by=None):
    """
    Always create a new version. Previous versions stay available;
    the newest is the current/relevant document.
    """
    validate_personnel_document(uploaded_file)
    version = EmployeeDocumentVersion.objects.create(
        employee=employee,
        document_type=document_type,
        file=uploaded_file,
        original_filename=uploaded_file.name,
        uploaded_by=uploaded_by,
    )
    _sync_current_employee_file(employee, document_type, version.file)
    return version


def process_document_uploads(request, employee, uploaded_by=None):
    """Create new document versions from POST file fields on employee forms."""
    created = []
    for definition in DOCUMENT_TYPE_DEFINITIONS:
        uploaded = request.FILES.get(definition['upload_field'])
        if not uploaded:
            continue
        created.append(
            create_document_version(
                employee,
                definition['type'],
                uploaded,
                uploaded_by=uploaded_by,
            )
        )
    return created


def copy_file_to_document_version(employee, document_type, source_field, uploaded_by=None):
    if not source_field:
        return None
    source_field.open('rb')
    try:
        content = source_field.read()
    finally:
        source_field.close()
    version = EmployeeDocumentVersion(
        employee=employee,
        document_type=document_type,
        original_filename=os.path.basename(source_field.name),
        uploaded_by=uploaded_by,
    )
    version.file.save(version.original_filename, ContentFile(content), save=True)
    _sync_current_employee_file(employee, document_type, version.file)
    return version


def copy_recruitment_documents_to_employee(task, employee, uploaded_by=None):
    mapping = [
        (EmployeeDocumentType.APPLICATION, task.application_file),
        (EmployeeDocumentType.CV, task.cv_file),
        (EmployeeDocumentType.LATEST_DEGREE_CERTIFICATE, task.latest_degree_certificate_file),
    ]
    created = []
    for document_type, source_field in mapping:
        version = copy_file_to_document_version(employee, document_type, source_field, uploaded_by)
        if version:
            created.append(version)
    return created


def user_can_manage_employee_documents(user, employee):
    if not user.is_authenticated or not employee:
        return False
    from apps.hr.employee_access import user_can_manage_employee
    if user_can_manage_employee(user, employee):
        return True
    profile = getattr(user, 'employee', None)
    return profile is not None and profile.pk == employee.pk


def user_can_delete_document_version(user, version):
    if not user.is_authenticated:
        return False
    from apps.hr.employee_access import user_can_manage_employee
    if user_can_manage_employee(user, version.employee if version else None):
        return True
    profile = getattr(user, 'employee', None)
    return (
        profile is not None
        and version.uploaded_by_id == profile.pk
        and version.employee_id == profile.pk
    )