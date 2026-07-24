"""
apps/core/models.py

Project: THERESE - Transparent HR Employee Resource Evaluation System Enhanced

Features / Requirements:
- BaseModel with created_at and updated_at timestamps for all models
- GlobalSetting for application-wide defaults (e.g. default weekly hours)
- All user-facing text must be in English
- Header block must be maintained and only extended when new requirements are explicitly added

Do not remove any existing requirements from this header without explicit instruction.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class BaseModel(models.Model):
    """Abstract base model with timestamps"""
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated At")

    class Meta:
        abstract = True


class DataImportLog(BaseModel):
    """
    Audit log for data imports of any kind (Excel, paste tables, …).

    Stores who uploaded what and when, plus a content hash to detect accidental
    re-imports of the same file.
    """

    class Kind(models.TextChoices):
        THIRD_PARTY_FUNDING_REPORT = (
            'third_party_funding_report',
            'Third-party funding report',
        )
        PAY_SCALE = 'pay_scale', 'Pay scale / TV-L'
        COST_CENTER_PASTE = 'cost_center_paste', 'Cost center paste import'
        WBS_PASTE = 'wbs_paste', 'WBS element paste import'
        OTHER = 'other', 'Other'

    class Status(models.TextChoices):
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'
        REJECTED_DUPLICATE = 'rejected_duplicate', 'Rejected (duplicate file)'

    kind = models.CharField(
        max_length=64,
        choices=Kind.choices,
        verbose_name='Import kind',
        db_index=True,
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='data_imports',
        verbose_name='Uploaded by',
    )
    original_filename = models.CharField(
        max_length=500,
        blank=True,
        default='',
        verbose_name='Original filename',
        help_text='Client filename; may be long.',
    )
    file_sha256 = models.CharField(
        max_length=64,
        blank=True,
        default='',
        db_index=True,
        verbose_name='File SHA-256',
        help_text='Hex digest of the uploaded content (empty for paste-only imports).',
    )
    file_size = models.PositiveBigIntegerField(
        default=0,
        verbose_name='File size (bytes)',
    )
    # From OOXML package metadata (docProps/core.xml) when available
    file_created_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Document created at',
        help_text='Creation timestamp from Excel/OOXML core properties, if present.',
    )
    file_modified_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Document modified at',
        help_text='Last-modified timestamp from Excel/OOXML core properties, if present.',
    )
    # From report sheet content (e.g. "angelegt am" on Übersicht)
    report_created_on = models.DateField(
        null=True,
        blank=True,
        verbose_name='Report created on',
        help_text='Business report creation date from file content (e.g. angelegt am).',
    )
    # Min/max Belegdatum on Personalkosten sheet (informational; reports are cumulative)
    beleg_from = models.DateField(
        null=True,
        blank=True,
        verbose_name='Beleg period from',
        help_text=(
            'Earliest Belegdatum found on the Personalkosten sheet '
            '(informational only; funding reports cover PSP start → report pull date).'
        ),
    )
    beleg_to = models.DateField(
        null=True,
        blank=True,
        verbose_name='Beleg period to',
        help_text=(
            'Latest Belegdatum found on the Personalkosten sheet '
            '(informational only; funding reports cover PSP start → report pull date).'
        ),
    )
    status = models.CharField(
        max_length=32,
        choices=Status.choices,
        default=Status.COMPLETED,
        verbose_name='Status',
        db_index=True,
    )
    summary = models.TextField(
        blank=True,
        default='',
        verbose_name='Summary',
    )

    class Meta:
        verbose_name = 'Data import log'
        verbose_name_plural = 'Data import logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['kind', 'file_sha256']),
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        name = self.original_filename or '(no file)'
        return f'{self.get_kind_display()}: {name} ({self.created_at:%Y-%m-%d %H:%M})'


class StoredFile(BaseModel):
    """Binary file content stored in the database (used by DatabaseStorage)."""
    name = models.CharField(
        max_length=500,
        unique=True,
        verbose_name='Storage Path',
        help_text='Logical path, e.g. recruitment_tasks/cv/example.pdf',
    )
    original_filename = models.CharField(max_length=255, verbose_name='Original Filename')
    content_type = models.CharField(max_length=100, blank=True, verbose_name='Content Type')
    size = models.PositiveBigIntegerField(default=0, verbose_name='Size (bytes)')
    content = models.BinaryField(verbose_name='File Content')

    class Meta:
        verbose_name = 'Stored File'
        verbose_name_plural = 'Stored Files'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.original_filename} ({self.size} bytes)'


class GlobalSetting(models.Model):
    """Global application settings"""
    default_weekly_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=39.00,
        verbose_name="Default Weekly Working Hours"
    )
    true_cost_multiplicator = models.DecimalField(
        max_digits=5,
        decimal_places=3,
        default=1.300,
        verbose_name="True-Cost Multiplicator",
        help_text=(
            "True costs = (100% monthly salary + supplements) × "
            "(weekly hours / default weekly hours) × this factor (default 1.3)."
        ),
    )
    personnel_import_tolerance = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=0.0250,
        verbose_name="Personnel import amount tolerance",
        help_text=(
            "Relative tolerance for Personalkosten vs expected true costs "
            "(e.g. 0.025 = ±2.5%). January always uses 4% instead."
        ),
    )
    irresponsible = models.BooleanField(
        default=False,
        verbose_name="Irresponsible mode",
        help_text=(
            "When enabled, the third-party funding import UI shows an option to "
            "force re-import of files that were already uploaded or are older "
            "than the latest imported report. Use only for recovery/admin."
        ),
    )
    CHEMICAL_HAZARD_THRESHOLD_CHOICES = [
        ('any_ghs', 'Any GHS signal, H-code, or pictogram'),
        ('signal_warning_or_danger', 'GHS signal Warning or Danger'),
        ('signal_danger_only', 'GHS signal Danger only'),
        ('any_pictogram', 'Any GHS pictogram'),
        ('any_h_code', 'Any GHS H-code'),
        ('never', 'Never auto-classify (manual only)'),
    ]
    chemical_hazard_threshold = models.CharField(
        max_length=40,
        choices=CHEMICAL_HAZARD_THRESHOLD_CHOICES,
        default='any_ghs',
        verbose_name='Chemical hazard threshold (Gefahrstoff)',
        help_text=(
            'When a CAS number is looked up (free PubChem data), chemicals meeting '
            'this threshold are treated as hazardous substances.'
        ),
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Global Setting"
        verbose_name_plural = "Global Settings"

    def __str__(self):
        return (
            f"Default Weekly Hours: {self.default_weekly_hours}h, "
            f"True-Cost Multiplicator: {self.true_cost_multiplicator}"
        )

    @classmethod
    def get_solo(cls):
        setting, _ = cls.objects.get_or_create(pk=1)
        return setting

    @classmethod
    def get_default_weekly_hours(cls):
        return cls.get_solo().default_weekly_hours

    @classmethod
    def get_true_cost_multiplicator(cls):
        return cls.get_solo().true_cost_multiplicator

    @classmethod
    def get_personnel_import_tolerance(cls):
        return cls.get_solo().personnel_import_tolerance

    @classmethod
    def get_irresponsible(cls) -> bool:
        return bool(cls.get_solo().irresponsible)

    @classmethod
    def get_chemical_hazard_threshold(cls):
        return cls.get_solo().chemical_hazard_threshold


