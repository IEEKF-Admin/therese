"""
Object-level authorization for database-stored media files.

Generic /media/<path> must not serve arbitrary files to any logged-in user.
"""

from __future__ import annotations

from django.db.models import Q


def user_can_access_stored_file(user, file_path: str) -> bool:
    """Return True only if the authenticated user may download this storage path."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True

    path = (file_path or '').lstrip('/')
    if not path or '..' in path.split('/'):
        return False

    # Draft uploads are session-scoped during form flows; never via generic media URL.
    if path.startswith('recruitment_tasks/draft/'):
        return False

    if path.startswith('employee_documents/'):
        return _employee_document_version(user, path)
    if path.startswith('contract_scans/') or path.startswith('employee_pictures/'):
        return _employee_legacy_file(user, path)
    if path.startswith('recruitment_tasks/'):
        return _recruitment_task_file(user, path)
    if path.startswith('purchase_orders/quotes/'):
        return _purchase_quote_file(user, path)
    if path.startswith('task_attachments/'):
        return _task_attachment_file(user, path)
    if path.startswith('checklists/'):
        return _checklist_file(user, path)
    if path.startswith('documents/'):
        return _document_file(user, path)
    if path.startswith('finances/'):
        return _finance_file(user, path)

    # Unknown prefixes: deny (no open media dump).
    return False


def _employee_document_version(user, path) -> bool:
    from apps.hr.document_utils import user_can_manage_employee_documents
    from apps.hr.models import EmployeeDocumentVersion

    version = EmployeeDocumentVersion.objects.filter(file=path).select_related('employee').first()
    if not version:
        return False
    return user_can_manage_employee_documents(user, version.employee)


def _employee_legacy_file(user, path) -> bool:
    from apps.hr.document_utils import user_can_manage_employee_documents
    from apps.hr.models import Employee

    employee = (
        Employee.objects.filter(Q(scan_of_contract=path) | Q(profile_picture=path)).first()
    )
    if not employee:
        return False
    # Profile pictures: managers and the employee themselves.
    if path.startswith('employee_pictures/'):
        if user_can_manage_employee_documents(user, employee):
            return True
        if user.has_perm('hr.can_view_employees') or user.has_perm('hr.manage_employee'):
            return True
        return False
    return user_can_manage_employee_documents(user, employee)


def _recruitment_task_file(user, path) -> bool:
    from apps.tasks.models import PersonnelRecruitmentTask
    from apps.tasks.personnel_documents import can_download_personnel_documents
    from apps.tasks.utils import can_view_personnel_task

    task = PersonnelRecruitmentTask.objects.filter(
        Q(application_file=path)
        | Q(cv_file=path)
        | Q(latest_degree_certificate_file=path)
    ).first()
    if not task:
        return False
    if not can_view_personnel_task(user, task):
        return False
    # Sensitive candidate docs: only download role (coordinator/approver), not every viewer.
    if path.startswith('recruitment_tasks/cv/') or path.startswith(
        'recruitment_tasks/degree_certificates/'
    ) or path.startswith('recruitment_tasks/application/'):
        return can_download_personnel_documents(user)
    return True


def _purchase_quote_file(user, path) -> bool:
    from apps.tasks.models import PurchaseOrderTask
    from apps.tasks.utils import can_view_purchase_order

    task = PurchaseOrderTask.objects.filter(quote_file=path).first()
    if not task:
        return False
    return can_view_purchase_order(user, task)


def _task_attachment_file(user, path) -> bool:
    from apps.tasks.models import TaskAttachment
    from apps.tasks.utils import can_view_purchase_order, can_view_personnel_task

    attachment = TaskAttachment.objects.filter(file=path).select_related('task').first()
    if not attachment:
        return False
    task = attachment.task
    if task.task_type == 'purchase_order':
        from apps.tasks.models import PurchaseOrderTask
        po = PurchaseOrderTask.objects.filter(pk=task.pk).first()
        return bool(po and can_view_purchase_order(user, po))
    if task.task_type in (
        'personnel_recruitment',
        'personnel_reallocation',
        'personnel_contract_extension',
    ):
        return can_view_personnel_task(user, task)
    if task.task_type == 'generic_text':
        employee = getattr(user, 'employee', None)
        return bool(
            employee
            and (
                task.creator_id == employee.pk
                or getattr(task, 'recipient_id', None) == employee.pk
            )
        )
    return False


def _checklist_file(user, path) -> bool:
    from apps.checklists.access import user_can_view_instance_readonly
    from apps.checklists.models import ChecklistFieldResponse

    response = (
        ChecklistFieldResponse.objects.filter(file=path)
        .select_related('instance', 'instance__subject')
        .first()
    )
    if not response:
        return False
    return user_can_view_instance_readonly(user, response.instance)


def _document_file(user, path) -> bool:
    from apps.documents.models import DocumentAttachment
    from apps.documents.audience import user_matches_document_audience

    attachment = (
        DocumentAttachment.objects.filter(file=path)
        .select_related('version', 'version__document')
        .first()
    )
    if not attachment:
        # Editor images: only document managers (not every viewer).
        return user.has_perm('documents.manage_document')

    document = attachment.version.document
    if user.has_perm('documents.manage_document'):
        return True
    if not user.has_perm('documents.view_document'):
        return False
    if document.is_archived or not document.current_published_version_id:
        return False
    return user_matches_document_audience(user, document)


def _finance_file(user, path) -> bool:
    from apps.finances.models import CostCenter, WBSElement

    from apps.finances.psp_access import filter_psp_for_user, user_can_view_psp_list

    if not (
        user_can_view_psp_list(user)
        or user.has_perm('finances.manage_cost_center')
    ):
        return False

    if path.startswith('finances/psp/'):
        qs = filter_psp_for_user(
            WBSElement.objects.filter(third_party_funding_commitment=path),
            user,
        )
        return qs.exists()
    # Legacy cost-center third-party uploads (field removed); managers only.
    if path.startswith('finances/cost_center/'):
        return user.has_perm('finances.manage_cost_center')
    return False
