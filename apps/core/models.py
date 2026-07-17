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

from django.db import models
from django.utils import timezone


class BaseModel(models.Model):
    """Abstract base model with timestamps"""
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated At")

    class Meta:
        abstract = True


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
        help_text="Monthly costs = monthly salary × this factor (default 1.3).",
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


