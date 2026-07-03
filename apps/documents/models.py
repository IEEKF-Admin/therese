from django.conf import settings
from django.contrib.auth.models import Group
from django.db import models

from apps.core.models import BaseModel


class DocumentCategory(BaseModel):
    name = models.CharField(max_length=120, verbose_name='Name')
    parent = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='children',
        verbose_name='Parent category',
    )

    class Meta:
        verbose_name = 'Document Category'
        verbose_name_plural = 'Document Categories'
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['parent', 'name'],
                name='documents_category_parent_name_uniq',
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def breadcrumb(self):
        from .category_utils import category_breadcrumb
        return category_breadcrumb(self)


class Document(BaseModel):
    AUDIENCE_MATCH_CHOICES = [
        ('or', 'OR — match any selected criterion'),
        ('and', 'AND — match all selected criteria'),
    ]

    title = models.CharField(max_length=255, verbose_name='Title')
    category = models.ForeignKey(
        DocumentCategory,
        on_delete=models.PROTECT,
        related_name='documents',
        verbose_name='Category',
    )
    is_archived = models.BooleanField(default=False, verbose_name='Archived')
    requires_read_acknowledgement = models.BooleanField(
        default=False,
        verbose_name='Requires read acknowledgement',
    )
    audience_match_mode = models.CharField(
        max_length=3,
        choices=AUDIENCE_MATCH_CHOICES,
        default='or',
        verbose_name='Audience match mode',
    )
    target_users = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='targeted_documents',
        blank=True,
        verbose_name='Target users',
    )
    target_workgroups = models.ManyToManyField(
        'hr.Workgroup',
        related_name='targeted_documents',
        blank=True,
        verbose_name='Target work groups',
    )
    target_groups = models.ManyToManyField(
        Group,
        related_name='targeted_documents',
        blank=True,
        verbose_name='Target Django groups',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_documents',
        verbose_name='Created by',
    )
    current_published_version = models.ForeignKey(
        'DocumentVersion',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        verbose_name='Current published version',
    )

    class Meta:
        verbose_name = 'Document'
        verbose_name_plural = 'Documents'
        ordering = ['title']
        default_permissions = ()
        permissions = [
            ('view_document', 'Can view documents and SOPs'),
            ('manage_document', 'Can manage documents and SOPs'),
        ]

    def __str__(self):
        return self.title

    @property
    def latest_version(self):
        return self.versions.order_by('-version_number').first()

    @property
    def latest_draft(self):
        return self.versions.filter(status=DocumentVersion.Status.DRAFT).order_by('-version_number').first()


class DocumentVersion(BaseModel):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PUBLISHED = 'published', 'Published'

    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name='versions',
        verbose_name='Document',
    )
    version_number = models.PositiveIntegerField(verbose_name='Version number')
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name='Status',
    )
    content_html = models.TextField(blank=True, verbose_name='Content')
    change_summary = models.CharField(max_length=500, blank=True, verbose_name='Change summary')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='document_versions_created',
        verbose_name='Created by',
    )
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='document_versions_published',
        verbose_name='Published by',
    )
    published_at = models.DateTimeField(null=True, blank=True, verbose_name='Published at')

    class Meta:
        verbose_name = 'Document Version'
        verbose_name_plural = 'Document Versions'
        ordering = ['document', '-version_number']
        unique_together = [('document', 'version_number')]

    def __str__(self):
        return f'{self.document.title} {self.version_label}'

    @property
    def version_label(self):
        return f'v{self.version_number}'

    @property
    def is_editable(self):
        return self.status == self.Status.DRAFT


class DocumentAttachment(BaseModel):
    version = models.ForeignKey(
        DocumentVersion,
        on_delete=models.CASCADE,
        related_name='attachments',
        verbose_name='Version',
    )
    label = models.CharField(max_length=255, blank=True, verbose_name='Label')
    file = models.FileField(upload_to='documents/attachments/%Y/%m/', verbose_name='File')

    class Meta:
        verbose_name = 'Document Attachment'
        verbose_name_plural = 'Document Attachments'
        ordering = ['label', 'id']

    def __str__(self):
        return self.label or self.file.name


class DocumentActivityLog(models.Model):
    document = models.ForeignKey(
        Document,
        on_delete=models.CASCADE,
        related_name='activity_logs',
    )
    version = models.ForeignKey(
        DocumentVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='activity_logs',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
    )
    action = models.CharField(max_length=64)
    details = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Document Activity Log'
        verbose_name_plural = 'Document Activity Logs'
        ordering = ['-created_at']


class DocumentReadAcknowledgement(models.Model):
    class Status(models.TextChoices):
        CONFIRMED = 'confirmed', 'Seen and confirmed'
        DECLINED = 'declined', 'Seen and declined'

    version = models.ForeignKey(
        DocumentVersion,
        on_delete=models.CASCADE,
        related_name='read_acknowledgements',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='document_read_acks',
    )
    status = models.CharField(max_length=20, choices=Status.choices)
    decided_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Document Read Acknowledgement'
        verbose_name_plural = 'Document Read Acknowledgements'
        unique_together = [('version', 'user')]


class DocumentPublishPopupAck(models.Model):
    """User dismissed the login popup for a published document version."""
    version = models.ForeignKey(
        DocumentVersion,
        on_delete=models.CASCADE,
        related_name='publish_popup_acks',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='document_publish_popup_acks',
    )
    acknowledged_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('version', 'user')]