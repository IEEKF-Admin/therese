from django.urls import reverse

from apps.documents.audience import user_matches_document_audience
from apps.documents.models import Document, DocumentPublishPopupAck


def evaluate_document_publish_popups(user):
    if not user.has_perm('documents.view_document'):
        return []

    acknowledged_version_ids = set(
        DocumentPublishPopupAck.objects.filter(user=user).values_list('version_id', flat=True)
    )

    documents = (
        Document.objects.filter(
            is_archived=False,
            current_published_version__isnull=False,
        )
        .select_related('current_published_version', 'category')
        .prefetch_related('target_users', 'target_workgroups', 'target_groups')
    )

    popups = []
    for document in documents:
        if not user_matches_document_audience(user, document):
            continue
        version = document.current_published_version
        if version.pk in acknowledged_version_ids:
            continue
        popups.append({
            'text': (
                f'A document has been published or updated: {document.title} '
                f'({version.version_label}). Please review it.'
            ),
            'link': '',
            'url': reverse('documents:detail', args=[document.pk]),
            'version_id': version.pk,
        })
    return popups


def persist_document_publish_popup_acks(user, popups):
    from apps.documents.models import DocumentVersion

    for popup in popups:
        if not popup.get('version_id'):
            continue
        try:
            version = DocumentVersion.objects.get(pk=popup['version_id'])
        except DocumentVersion.DoesNotExist:
            continue
        DocumentPublishPopupAck.objects.get_or_create(user=user, version=version)