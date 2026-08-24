from django.urls import reverse

from apps.documents.audience import user_matches_document_audience
from apps.documents.models import Document, DocumentPublishPopupAck, DocumentVersion


def evaluate_document_publish_popups(user):
    if not user.has_perm('documents.view_document'):
        return []

    acknowledged_version_ids = set(
        DocumentPublishPopupAck.objects.filter(user=user).values_list('version_id', flat=True)
    )

    documents = (
        Document.objects.filter(
            is_archived=False,
            requires_read_acknowledgement=True,
            current_published_version__isnull=False,
        )
        .select_related('current_published_version', 'category')
        .prefetch_related('target_users', 'target_workgroups', 'target_groups')
        .distinct()
    )

    popups = []
    seen_document_ids = set()
    for document in documents:
        if document.pk in seen_document_ids:
            continue
        seen_document_ids.add(document.pk)
        if not user_matches_document_audience(user, document):
            continue
        version = document.current_published_version
        if not version or version.pk in acknowledged_version_ids:
            continue
        popups.append({
            'text': (
                f'A document has been published or updated: {document.title} '
                f'({version.version_label}). Please review it.'
            ),
            'link': '',
            'url': reverse('documents:detail', args=[document.pk]),
            'version_id': version.pk,
            'document_id': document.pk,
        })
    return popups


def persist_document_publish_popup_acks(user, popups):
    document_ids = [popup.get('document_id') for popup in popups if popup.get('document_id')]
    version_ids = [popup.get('version_id') for popup in popups if popup.get('version_id')]
    if not version_ids and not document_ids:
        return

    versions = DocumentVersion.objects.filter(pk__in=version_ids).select_related('document')
    if document_ids:
        versions = DocumentVersion.objects.filter(
            document_id__in=document_ids,
            status=DocumentVersion.Status.PUBLISHED,
        ).select_related('document')

    for version in versions:
        DocumentPublishPopupAck.objects.get_or_create(user=user, version=version)
