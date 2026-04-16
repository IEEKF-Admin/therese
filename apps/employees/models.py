from django.db import models
from apps.core.models import BaseModel


class PayScale(models.Model):
    """TV-L Gehaltseintrag"""
    pay_scale_group = models.CharField(max_length=50, verbose_name="Entgeltgruppe")
    experience_level = models.PositiveSmallIntegerField(verbose_name="Erfahrungsstufe")
    monthly_salary = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Monatsgehalt (Brutto)")
    effective_as_of = models.DateField(verbose_name="Gültig ab")

    class Meta:
        verbose_name = "TV-L Gehaltseintrag"
        verbose_name_plural = "TV-L Gehaltseinträge"
        ordering = ['pay_scale_group', 'experience_level', '-effective_as_of']
        unique_together = ('pay_scale_group', 'experience_level', 'effective_as_of')

    def __str__(self):
        return f"{self.pay_scale_group} Stufe {self.experience_level} ab {self.effective_as_of}"


class Employee(BaseModel):
    """Mitarbeiter"""
    user = models.OneToOneField(
        'accounts.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employee'
    )

    first_name = models.CharField(max_length=100, verbose_name="Vorname")
    last_name = models.CharField(max_length=100, verbose_name="Nachname")
    employee_number = models.CharField(max_length=50, unique=True, verbose_name="Personalnummer")

    class Meta:
        verbose_name = "Mitarbeiter"
        verbose_name_plural = "Mitarbeiter"
        ordering = ['last_name', 'first_name']

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.employee_number})"
