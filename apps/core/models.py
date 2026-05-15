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


class GlobalSetting(models.Model):
    """Global application settings"""
    default_weekly_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=39.00,
        verbose_name="Default Weekly Working Hours"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Global Setting"
        verbose_name_plural = "Global Settings"

    def __str__(self):
        return f"Default Weekly Hours: {self.default_weekly_hours}h"

    @classmethod
    def get_default_weekly_hours(cls):
        setting, _ = cls.objects.get_or_create(pk=1)
        return setting.default_weekly_hours
