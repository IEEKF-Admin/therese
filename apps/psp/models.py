from django.db import models
from apps.core.models import BaseModel
from apps.accounts.models import CustomUser


class PSPElement(BaseModel):
    """PSP-Element (Projekt, Stelle, etc.)"""
    title = models.CharField(max_length=200, verbose_name="Titel")
    
    responsible = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Verantwortlich"
    )
    
    comments = models.TextField(blank=True, verbose_name="Allgemeine Kommentare")

    # Aktueller Stand (wird über History aktualisiert)
    current_secured_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        verbose_name="Aktueller gesicherter Betrag (€)"
    )

    class Meta:
        verbose_name = "PSP-Element"
        verbose_name_plural = "PSP-Elemente"
        ordering = ['title']

    def __str__(self):
        return self.title


class PSPBudgetHistory(BaseModel):
    """Historie der Budget-Änderungen für ein PSP-Element"""
    psp_element = models.ForeignKey(
        PSPElement,
        on_delete=models.CASCADE,
        related_name='budget_history'
    )
    
    effective_date = models.DateField(verbose_name="Gültig ab (1.1. des Jahres)")
    
    secured_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Gesicherter Betrag (€)"
    )
    
    changed_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Geändert von"
    )
    
    comment = models.TextField(blank=True, verbose_name="Kommentar zur Änderung")

    class Meta:
        verbose_name = "Budget-Änderung"
        verbose_name_plural = "Budget-Historie"
        ordering = ['-effective_date', '-created_at']

    def __str__(self):
        return f"{self.psp_element.title} – {self.effective_date}: {self.secured_amount} €"
