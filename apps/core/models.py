from django.db import models
from django.utils import timezone

class BaseModel(models.Model):
    """Basis-Modell mit Zeitstempeln für alle anderen Models"""
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Erstellt am")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Zuletzt geändert am")

    class Meta:
        abstract = True  # Wichtig: Dies ist kein eigenes Model, sondern nur eine Vorlage


class GlobalSetting(models.Model):
    """Globale Einstellungen der Anwendung"""
    default_weekly_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=39.00,
        verbose_name="Standard-Wochenarbeitszeit (Stunden)"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Globale Einstellung"
        verbose_name_plural = "Globale Einstellungen"

    def __str__(self):
        return f"Standard-Wochenstunden: {self.default_weekly_hours}h"

    @classmethod
    def get_default_weekly_hours(cls):
        setting, _ = cls.objects.get_or_create(pk=1)
        return setting.default_weekly_hours
