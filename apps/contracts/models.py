from django.db import models
from django.utils import timezone
from apps.core.models import BaseModel


class Contract(BaseModel):
    """Arbeitsvertrag / Vertragsversion eines Mitarbeiters"""
    
    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='contracts',
        verbose_name="Mitarbeiter"
    )

    pay_scale_group = models.CharField(max_length=50, verbose_name="Entgeltgruppe")
    experience_level = models.PositiveSmallIntegerField(verbose_name="Erfahrungsstufe")

    # Angepasstes Feld für Wochenarbeitszeit mit Nachkommastellen
    weekly_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,          # erlaubt bis zu zwei Nachkommastellen
        verbose_name="Wochenarbeitszeit (Stunden)"
    )

    valid_from = models.DateField(verbose_name="Gültig ab")
    valid_until = models.DateField(
        null=True,
        blank=True,
        verbose_name="Gültig bis"
    )

    comments = models.TextField(blank=True, verbose_name="Vertragskommentare")

    class Meta:
        verbose_name = "Vertrag"
        verbose_name_plural = "Verträge"
        ordering = ['employee', '-valid_from']

    def __str__(self):
        return f"Vertrag {self.employee} ab {self.valid_from} ({self.weekly_hours}h)"

    @property
    def is_current(self):
        """Prüft, ob dieser Vertrag aktuell gültig ist"""
        if not self.valid_from:
            return False
        today = timezone.now().date()
        return (self.valid_from <= today) and (
            self.valid_until is None or self.valid_until >= today
        )
