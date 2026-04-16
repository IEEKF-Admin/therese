from django.db import models
from apps.core.models import BaseModel


class FundingAllocation(BaseModel):
    """Stunden-basierte Finanzierung eines Mitarbeiters auf einem PSP-Element"""
    
    employee = models.ForeignKey(
        'employees.Employee',
        on_delete=models.CASCADE,
        related_name='allocations',
        verbose_name="Mitarbeiter"
    )
    
    psp_element = models.ForeignKey(
        'psp.PSPElement',
        on_delete=models.PROTECT,
        verbose_name="PSP-Element"
    )
    
    weekly_hours_allocated = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name="Zugewiesene Wochenstunden"
    )
    
    start_date = models.DateField(verbose_name="Gültig ab")
    end_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Gültig bis"
    )
    
    comments = models.TextField(blank=True, verbose_name="Kommentare")

    class Meta:
        verbose_name = "Finanzierungsanteil"
        verbose_name_plural = "Finanzierungsanteile"
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.employee} → {self.psp_element} ({self.weekly_hours_allocated}h)"

    # Optional: Hilfsmethode für spätere Validierung
    def clean(self):
        if self.weekly_hours_allocated <= 0:
            raise ValidationError("Die zugewiesenen Stunden müssen größer als 0 sein.")
