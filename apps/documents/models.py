from django.db import models
from apps.hr.models import Employee
from django.contrib.auth.models import Group


class DocumentTag(models.Model):
    """Tags are user-specific for history, but can be renamed later."""
    name = models.CharField(max_length=100)
    created_by = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='created_tags')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('name', 'created_by')
        ordering = ['name']

    def __str__(self):
        return self.name


class Document(models.Model):
    """Main document with metadata. One current version + history of old versions."""
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    current_version = models.OneToOneField(
        'DocumentVersion',
        on_delete=models.PROTECT,
        related_name='current_for_document'
    )

    created_by = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name='created_documents')
    created_at = models.DateTimeField(auto_now_add=True)

    tags = models.ManyToManyField(DocumentTag, blank=True, related_name='documents')

    def __str__(self):
        return self.title


class DocumentVersion(models.Model):
    """A specific version of a document. The actual file is stored in the database."""
    document = models.ForeignKey(
        Document, 
        on_delete=models.CASCADE, 
        related_name='versions',
        null=True, 
        blank=True
    )
    version_number = models.PositiveIntegerField()

    file = models.BinaryField()  # File stored directly in DB
    original_filename = models.CharField(max_length=255)

    uploaded_by = models.ForeignKey(Employee, on_delete=models.PROTECT)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    comment = models.TextField(blank=True)

    class Meta:
        unique_together = ('document', 'version_number')
        ordering = ['-version_number']

    def __str__(self):
        return f"{self.document.title} - v{self.version_number}"


class DocumentShare(models.Model):
    """Controls who has access to a document and with which permission level."""

    SHARE_TYPE_CHOICES = [
        ('user', 'Einzelner Benutzer'),
        ('group', 'Gruppe'),
        ('everyone', 'Jeder'),
        ('administration', 'Administration'),
    ]

    PERMISSION_CHOICES = [
        ('viewer', 'Nur ansehen & herunterladen'),
        ('editor', 'Darf neue Versionen hochladen + Metadaten ändern'),
        ('manager', 'Darf auch Freigaben verwalten'),
    ]

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='shares')

    share_type = models.CharField(max_length=20, choices=SHARE_TYPE_CHOICES)
    shared_with_user = models.ForeignKey(
        Employee, on_delete=models.CASCADE, null=True, blank=True, related_name='document_shares'
    )
    shared_with_group = models.ForeignKey(
        Group, on_delete=models.CASCADE, null=True, blank=True, related_name='document_shares'
    )

    permission = models.CharField(max_length=20, choices=PERMISSION_CHOICES)

    SIGNATURE_CHOICES = [
        ('', 'No signature required'),
        ('signature', 'Signature (prompt on open)'),
        ('ask_for_signature', 'Ask for signature (popup on login)'),
    ]

    signature_requirement = models.CharField(
        max_length=20,
        choices=SIGNATURE_CHOICES,
        default='',
        blank=True,
        help_text="Requires the recipient to confirm they have seen and understood this document version."
    )

    shared_by = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name='shared_documents')
    shared_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['document', 'share_type', 'shared_with_user', 'shared_with_group'],
                name='unique_document_share'
            )
        ]

    def __str__(self):
        if self.share_type == 'user' and self.shared_with_user:
            return f"{self.document} → User: {self.shared_with_user}"
        elif self.share_type == 'group' and self.shared_with_group:
            return f"{self.document} → Gruppe: {self.shared_with_group}"
        return f"{self.document} → {self.get_share_type_display()}"


class UserDocumentArchive(models.Model):
    """Personal archive per user. Documents here are hidden from normal views for this user."""
    user = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='archived_documents')
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='archived_by_users')
    archived_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'document')

    def __str__(self):
        return f"{self.user} archived {self.document}"
