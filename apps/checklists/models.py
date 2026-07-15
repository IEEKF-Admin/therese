"""Process checklist models."""

from django.conf import settings
from django.db import models

from apps.core.models import BaseModel
from apps.hr.models import Employee, EmployeeDocumentType


class ChecklistTemplate(BaseModel):
    slug = models.SlugField(max_length=80, unique=True, verbose_name='Slug')
    name_en = models.CharField(max_length=200, verbose_name='Name (EN)')
    name_de = models.CharField(max_length=200, verbose_name='Name (DE)')
    description_en = models.TextField(blank=True, verbose_name='Description (EN)')
    description_de = models.TextField(blank=True, verbose_name='Description (DE)')

    class Meta:
        verbose_name = 'Checklist Template'
        verbose_name_plural = 'Checklist Templates'
        ordering = ['name_en']
        default_permissions = ()
        permissions = [
            ('view_checklist', 'Can view checklists'),
            ('manage_checklist', 'Can manage checklist templates and assignments'),
            ('view_workgroup_progress', 'Can view checklist progress for own workgroup'),
            ('view_institute_progress', 'Can view institute-wide checklist progress'),
        ]

    def __str__(self):
        return self.name_en


class ChecklistTemplateVersion(BaseModel):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PUBLISHED = 'published', 'Published'
        DEPRECATED = 'deprecated', 'Deprecated'

    class CompletionMode(models.TextChoices):
        AUTO = 'auto', 'Auto when all required fields fulfilled'
        COORDINATOR_CONFIRM = 'coordinator_confirm', 'Coordinator must confirm'
        ANCHOR_FIELD = 'anchor_field', 'Complete when anchor field fulfilled'

    template = models.ForeignKey(
        ChecklistTemplate,
        on_delete=models.CASCADE,
        related_name='versions',
        verbose_name='Template',
    )
    version_number = models.PositiveIntegerField(verbose_name='Version number')
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name='Status',
    )
    completion_mode = models.CharField(
        max_length=30,
        choices=CompletionMode.choices,
        default=CompletionMode.COORDINATOR_CONFIRM,
        verbose_name='Completion mode',
    )
    anchor_node = models.ForeignKey(
        'ChecklistTemplateNode',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='anchor_for_versions',
        verbose_name='Anchor node',
    )
    published_at = models.DateTimeField(null=True, blank=True, verbose_name='Published at')
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='checklist_versions_published',
        verbose_name='Published by',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='checklist_versions_created',
        verbose_name='Created by',
    )

    class Meta:
        verbose_name = 'Checklist Template Version'
        verbose_name_plural = 'Checklist Template Versions'
        ordering = ['template', '-version_number']
        constraints = [
            models.UniqueConstraint(
                fields=['template', 'version_number'],
                name='checklist_template_version_number_uniq',
            ),
        ]

    def __str__(self):
        return f'{self.template.slug} v{self.version_number}'

    @property
    def version_label(self):
        return f'v{self.version_number}'


class ChecklistTemplateNode(BaseModel):
    class NodeKind(models.TextChoices):
        SECTION = 'section', 'Section'
        FIELD = 'field', 'Field'
        RADIO_OPTION = 'radio_option', 'Radio option'

    class FieldType(models.TextChoices):
        CHECKBOX = 'checkbox', 'Checkbox'
        TEXT = 'text', 'Text'
        TEXTAREA = 'textarea', 'Textarea'
        RADIO_GROUP = 'radio_group', 'Radio group'
        FILE = 'file', 'File upload'
        DATE = 'date', 'Date'

    class FileTarget(models.TextChoices):
        EMPLOYEE_DOCUMENT = 'employee_document', 'Employee document'
        CHECKLIST_STORAGE = 'checklist_storage', 'Checklist storage only'

    version = models.ForeignKey(
        ChecklistTemplateVersion,
        on_delete=models.CASCADE,
        related_name='nodes',
        verbose_name='Version',
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        verbose_name='Parent',
    )
    sort_order = models.PositiveIntegerField(default=0, verbose_name='Sort order')
    node_kind = models.CharField(max_length=20, choices=NodeKind.choices, verbose_name='Node kind')
    field_type = models.CharField(
        max_length=20,
        choices=FieldType.choices,
        blank=True,
        verbose_name='Field type',
    )
    choice_key = models.CharField(max_length=80, blank=True, verbose_name='Choice key')
    label_en = models.CharField(max_length=255, blank=True, verbose_name='Label (EN)')
    label_de = models.CharField(max_length=255, blank=True, verbose_name='Label (DE)')
    help_en = models.TextField(blank=True, verbose_name='Help (EN)')
    help_de = models.TextField(blank=True, verbose_name='Help (DE)')
    required_for_completion = models.BooleanField(default=False, verbose_name='Required for completion')
    allow_not_applicable = models.BooleanField(default=False, verbose_name='Allow N/A')
    editable_by_subject = models.BooleanField(default=True, verbose_name='Editable by subject')
    editable_by_coordinators = models.BooleanField(default=True, verbose_name='Editable by coordinators')
    editable_by_employees = models.ManyToManyField(
        Employee,
        blank=True,
        related_name='editable_checklist_nodes',
        verbose_name='Editable by employees',
    )
    visible_to_subject = models.BooleanField(default=True, verbose_name='Visible to subject')
    file_target = models.CharField(
        max_length=30,
        choices=FileTarget.choices,
        blank=True,
        verbose_name='File target',
    )
    employee_document_type = models.CharField(
        max_length=30,
        choices=EmployeeDocumentType.choices,
        blank=True,
        verbose_name='Employee document type',
    )
    storage_label_en = models.CharField(max_length=255, blank=True, verbose_name='Storage label (EN)')
    storage_label_de = models.CharField(max_length=255, blank=True, verbose_name='Storage label (DE)')

    class Meta:
        verbose_name = 'Checklist Template Node'
        verbose_name_plural = 'Checklist Template Nodes'
        ordering = ['sort_order', 'pk']

    def __str__(self):
        return self.label_en or self.choice_key or f'Node {self.pk}'


class ChecklistInstance(BaseModel):
    class Status(models.TextChoices):
        NOT_STARTED = 'not_started', 'Not started'
        IN_PROGRESS = 'in_progress', 'In progress'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'

    ACTIVE_STATUSES = (Status.NOT_STARTED, Status.IN_PROGRESS)

    subject = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='checklist_instances',
        verbose_name='Subject',
    )
    template_version = models.ForeignKey(
        ChecklistTemplateVersion,
        on_delete=models.PROTECT,
        related_name='instances',
        verbose_name='Template version',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NOT_STARTED,
        verbose_name='Status',
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='checklists_assigned',
        verbose_name='Assigned by',
    )
    assigned_at = models.DateTimeField(auto_now_add=True, verbose_name='Assigned at')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='Completed at')
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='checklists_completed',
        verbose_name='Completed by',
    )

    class Meta:
        verbose_name = 'Checklist Instance'
        verbose_name_plural = 'Checklist Instances'
        ordering = ['-assigned_at']

    def __str__(self):
        return f'{self.subject} — {self.template_version}'

    @property
    def is_locked(self):
        return self.status == self.Status.COMPLETED


class ChecklistFieldResponse(BaseModel):
    instance = models.ForeignKey(
        ChecklistInstance,
        on_delete=models.CASCADE,
        related_name='responses',
        verbose_name='Instance',
    )
    node = models.ForeignKey(
        ChecklistTemplateNode,
        on_delete=models.CASCADE,
        related_name='responses',
        verbose_name='Node',
    )
    value_bool = models.BooleanField(null=True, blank=True, verbose_name='Boolean value')
    value_text = models.TextField(blank=True, verbose_name='Text value')
    value_choice = models.CharField(max_length=80, blank=True, verbose_name='Choice value')
    not_applicable = models.BooleanField(default=False, verbose_name='Not applicable')
    file = models.FileField(upload_to='checklists/%Y/%m/%d/', null=True, blank=True, verbose_name='File')
    original_filename = models.CharField(max_length=255, blank=True, verbose_name='Original filename')
    last_changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='checklist_field_changes',
        verbose_name='Last changed by',
    )

    class Meta:
        verbose_name = 'Checklist Field Response'
        verbose_name_plural = 'Checklist Field Responses'
        constraints = [
            models.UniqueConstraint(
                fields=['instance', 'node'],
                name='checklist_response_instance_node_uniq',
            ),
        ]

    def __str__(self):
        return f'Response {self.node_id} on instance {self.instance_id}'


class ChecklistAssignmentAck(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='checklist_assignment_acks',
        verbose_name='User',
    )
    instance = models.ForeignKey(
        ChecklistInstance,
        on_delete=models.CASCADE,
        related_name='assignment_acks',
        verbose_name='Instance',
    )
    acknowledged_at = models.DateTimeField(auto_now_add=True, verbose_name='Acknowledged at')

    class Meta:
        verbose_name = 'Checklist Assignment Acknowledgement'
        verbose_name_plural = 'Checklist Assignment Acknowledgements'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'instance'],
                name='checklist_assignment_ack_user_instance_uniq',
            ),
        ]

    def __str__(self):
        return f'{self.user} ack {self.instance_id}'