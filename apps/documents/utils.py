import os

from django.core.files.base import ContentFile
from django.db import models
from django.utils import timezone

from .models import DocumentActivityLog, DocumentAttachment, DocumentVersion


def log_document_activity(document, user, action, *, version=None, details=''):
    DocumentActivityLog.objects.create(
        document=document,
        version=version,
        user=user,
        action=action,
        details=details,
    )


def copy_attachments_to_version(source_version, target_version):
    for attachment in source_version.attachments.all():
        if not attachment.file:
            continue
        attachment.file.open('rb')
        try:
            data = attachment.file.read()
        finally:
            attachment.file.close()
        base_name = os.path.basename(attachment.file.name)
        new_attachment = DocumentAttachment(
            version=target_version,
            label=attachment.label,
        )
        new_attachment.file.save(base_name, ContentFile(data), save=True)


def publish_version(version, user):
    version.status = DocumentVersion.Status.PUBLISHED
    version.published_by = user
    version.published_at = timezone.now()
    version.save(update_fields=['status', 'published_by', 'published_at', 'updated_at'])

    document = version.document
    document.current_published_version = version
    document.save(update_fields=['current_published_version', 'updated_at'])

    log_document_activity(
        document,
        user,
        'published',
        version=version,
        details=f'Published {version.version_label}',
    )


def create_next_version(document, user, *, copy_from_version):
    next_number = (document.versions.aggregate(
        models.Max('version_number')
    )['version_number__max'] or 0) + 1

    new_version = DocumentVersion.objects.create(
        document=document,
        version_number=next_number,
        status=DocumentVersion.Status.DRAFT,
        content_html=copy_from_version.content_html,
        created_by=user,
    )
    copy_attachments_to_version(copy_from_version, new_version)
    log_document_activity(
        document,
        user,
        'new_version_started',
        version=new_version,
        details=f'Started {new_version.version_label} from {copy_from_version.version_label}',
    )
    return new_version