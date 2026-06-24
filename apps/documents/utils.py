from django.db.models import Q
from apps.hr.models import Employee
from .models import Document, DocumentShare


def get_visible_documents_for_user(employee: Employee, include_archived: bool = False):
    """
    Gibt alle Dokumente zurück, die der User sehen darf.
    - Immer: Dokumente, die der User selbst erstellt hat
    - Plus: Dokumente, die explizit mit ihm / seinen Gruppen / "Jeden" / "Administration" geteilt wurden
    - Archivierte Dokumente (persönlich) werden standardmäßig ausgeblendet
    """
    if not employee:
        return Document.objects.none()

    user = employee.user

    # 1. Immer alle selbst erstellten Dokumente (höchste Priorität)
    created_qs = Document.objects.filter(created_by=employee)

    # 2. Dokumente, die explizit geteilt wurden
    direct_user_shares = DocumentShare.objects.filter(
        share_type='user', shared_with_user=employee
    ).values_list('document_id', flat=True)

    user_groups = list(user.groups.values_list('id', flat=True))

    group_shares = DocumentShare.objects.filter(
        share_type='group',
        shared_with_group_id__in=user_groups
    ).values_list('document_id', flat=True)

    everyone_shares = DocumentShare.objects.filter(
        share_type='everyone'
    ).values_list('document_id', flat=True)

    # "Administration"
    administration_groups = ['Personnel Coordinator', 'Personnel Approver']
    is_administration = user.groups.filter(name__in=administration_groups).exists()

    admin_shares = Document.objects.none()
    if is_administration:
        admin_shares = DocumentShare.objects.filter(
            share_type='administration'
        ).values_list('document_id', flat=True)

    shared_ids = set(direct_user_shares) | set(group_shares) | set(everyone_shares)
    if is_administration:
        shared_ids |= set(admin_shares)

    # Kombiniere selbst erstellte + geteilte
    visible_ids = set(created_qs.values_list('id', flat=True)) | shared_ids

    qs = Document.objects.filter(id__in=visible_ids)

    # Persönliches Archiv ausblenden (außer gewünscht)
    if not include_archived:
        archived_ids = employee.archived_documents.values_list('document_id', flat=True)
        qs = qs.exclude(id__in=archived_ids)

    return qs.select_related('current_version', 'created_by').prefetch_related('tags').distinct().order_by('-created_at')


def get_user_permission_for_document(employee, document):
    """
    Gibt die höchste Berechtigung zurück, die ein User für ein Dokument hat.
    Mögliche Rückgabewerte: None, 'viewer', 'editor', 'manager'
    """
    if not employee or not document:
        return None

    # Ersteller hat immer Manager-Rechte
    if document.created_by == employee:
        return 'manager'

    user = employee.user
    user_groups = list(user.groups.values_list('id', flat=True))

    shares = DocumentShare.objects.filter(document=document)

    highest_permission = None
    permission_order = {'viewer': 1, 'editor': 2, 'manager': 3}

    for share in shares:
        perm = share.permission
        has_access = False

        if share.share_type == 'user' and share.shared_with_user == employee:
            has_access = True
        elif share.share_type == 'group' and share.shared_with_group_id in user_groups:
            has_access = True
        elif share.share_type == 'everyone':
            has_access = True
        elif share.share_type == 'administration':
            administration_groups = ['Personnel Coordinator', 'Personnel Approver']
            if user.groups.filter(name__in=administration_groups).exists():
                has_access = True

        if has_access:
            if highest_permission is None or permission_order.get(perm, 0) > permission_order.get(highest_permission, 0):
                highest_permission = perm

    return highest_permission

