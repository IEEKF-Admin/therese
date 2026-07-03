"""Helpers for employee document versioning and recruitment document transfer."""

import os

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile

from .models import Employee, EmployeeDocumentType, EmployeeDocumentVersion

MAX_DOCUMENT_SIZE_BYTES = 10 * 1024 * 1024
ALLOWED_DOCUMENT_EXTENSIONS = {'.pdf', '.jpg', '.jpeg', '.png', '.gif', '.webp'}


def validate_personnel_document(uploaded_file):
    if uploaded_file.size > MAX_DOCUMENT_SIZE_BYTES:
        raise ValidationError('File must be 10 MB or smaller.')
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    if ext not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise ValidationError('Allowed file types: PDF and images (JPG, PNG, GIF, WebP).')


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
        'type': EmployeeDocumentType.MEASLES_PROOF,
        'label_en': 'Measles Vaccination Proof',
        'label_de': 'Nachweis Masernschutzimpfung',
        'upload_field': 'upload_measles_proof',
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
    return [
        {
            **definition,
            'versions': grouped.get(definition['type'], []),
        }
        for definition in DOCUMENT_TYPE_DEFINITIONS
    ]


def create_document_version(employee, document_type, uploaded_file, uploaded_by=None):
    validate_personnel_document(uploaded_file)
    return EmployeeDocumentVersion.objects.create(
        employee=employee,
        document_type=document_type,
        file=uploaded_file,
        original_filename=uploaded_file.name,
        uploaded_by=uploaded_by,
    )


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
    return version


def copy_recruitment_documents_to_employee(task, employee, uploaded_by=None):
    mapping = [
        (EmployeeDocumentType.APPLICATION, task.application_file),
        (EmployeeDocumentType.CV, task.cv_file),
        (EmployeeDocumentType.MEASLES_PROOF, task.measles_proof_file),
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
    if user.is_superuser or user.has_perm('hr.manage_employee'):
        return True
    profile = getattr(user, 'employee', None)
    return profile is not None and profile.pk == employee.pk


def user_can_delete_document_version(user, version):
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.has_perm('hr.manage_employee'):
        return True
    profile = getattr(user, 'employee', None)
    return (
        profile is not None
        and version.uploaded_by_id == profile.pk
        and version.employee_id == profile.pk
    )