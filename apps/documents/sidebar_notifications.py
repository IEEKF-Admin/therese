"""Sidebar notification state for Documents & SOPs."""

from apps.documents.audience import user_matches_document_audience
from apps.documents.models import (
    Document,
    DocumentPublishPopupAck,
    DocumentReadAcknowledgement,
)


def _visible_published_documents(user):
    if not user.has_perm('documents.view_document'):
        return Document.objects.none()

    documents = (
        Document.objects.filter(
            is_archived=False,
            current_published_version__isnull=False,
        )
        .select_related('current_published_version')
        .prefetch_related('target_users', 'target_workgroups', 'target_groups')
    )
    return [doc for doc in documents if user_matches_document_audience(user, doc)]


def get_unseen_publish_version_ids(user):
    documents = _visible_published_documents(user)
    if not documents:
        return set()

    acknowledged_ids = set(
        DocumentPublishPopupAck.objects.filter(user=user).values_list('version_id', flat=True)
    )
    return {
        doc.current_published_version_id
        for doc in documents
        if doc.current_published_version_id not in acknowledged_ids
    }


def get_pending_read_ack_document_ids(user):
    documents = [
        doc for doc in _visible_published_documents(user)
        if doc.requires_read_acknowledgement
    ]
    if not documents:
        return set()

    version_ids = [doc.current_published_version_id for doc in documents]
    confirmed_version_ids = set(
        DocumentReadAcknowledgement.objects.filter(
            user=user,
            version_id__in=version_ids,
            status=DocumentReadAcknowledgement.Status.CONFIRMED,
        ).values_list('version_id', flat=True)
    )
    return {
        doc.pk
        for doc in documents
        if doc.current_published_version_id not in confirmed_version_ids
    }


def documents_menu_needs_attention(user):
    if not user.is_authenticated or not user.has_perm('documents.view_document'):
        return False
    return bool(
        get_unseen_publish_version_ids(user)
        or get_pending_read_ack_document_ids(user)
    )


def mark_publish_notifications_seen(user):
    """Called when the user opens the document list."""
    version_ids = get_unseen_publish_version_ids(user)
    for version_id in version_ids:
        DocumentPublishPopupAck.objects.get_or_create(user=user, version_id=version_id)