"""
apps/finances/models.py
Project: THERESE – Transparent HR Employee Resource Evaluation System Enhanced
"""

from django.db import models
from apps.core.models import BaseModel


class PayScale(BaseModel):
    """TV-L Pay Scale groups and experience levels"""
    pay_scale_group = models.CharField(
        max_length=50, 
        verbose_name="Pay Scale Group"
    )
    experience_level = models.PositiveSmallIntegerField(
        verbose_name="Experience Level"
    )
    monthly_salary = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        verbose_name="Monthly Salary"
    )
    effective_as_of = models.DateField(verbose_name="Effective As Of")

    class Meta:
        verbose_name = "Pay Scale"
        verbose_name_plural = "Pay Scales"
        unique_together = ('pay_scale_group', 'experience_level', 'effective_as_of')
        ordering = ['pay_scale_group', 'experience_level']
        permissions = [
            ("import_pay_scale", "Can import pay scales / TV-L"),
        ]

    def __str__(self):
        return f"{self.pay_scale_group} Level {self.experience_level} — {self.monthly_salary} €"

    @classmethod
    def get_current(cls):
        """
        Return only the most recent PayScale entry per (pay_scale_group, experience_level)
        based on the latest effective_as_of.
        """
        from django.db.models import Max, Q

        latest_dates = list(
            cls.objects
            .values('pay_scale_group', 'experience_level')
            .annotate(latest_date=Max('effective_as_of'))
        )

        if not latest_dates:
            return cls.objects.none()

        q = Q()
        for item in latest_dates:
            q |= Q(
                pay_scale_group=item['pay_scale_group'],
                experience_level=item['experience_level'],
                effective_as_of=item['latest_date']
            )
        return cls.objects.filter(q).order_by('pay_scale_group', 'experience_level')


class CostCenter(BaseModel):
    cost_center = models.CharField(max_length=50, unique=True, verbose_name="Cost Center")
    comments = models.TextField(blank=True, verbose_name="Comments")

    class Meta:
        verbose_name = "Cost Center"
        verbose_name_plural = "Cost Centers"
        ordering = ['cost_center']

    def __str__(self):
        return self.cost_center


class CostCenterInitialBalance(BaseModel):
    cost_center = models.ForeignKey(
        CostCenter,
        on_delete=models.CASCADE,
        related_name='initial_balances',
        verbose_name="Cost Center"
    )
    year = models.PositiveIntegerField(verbose_name="Year")
    initial_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Initial Balance")

    class Meta:
        verbose_name = "Cost Center Initial Balance"
        verbose_name_plural = "Cost Center Initial Balances"
        unique_together = ('cost_center', 'year')
        ordering = ['cost_center', '-year']


class WBSElementQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_inactive=False)


class WBSElement(BaseModel):
    """PSP Element"""
    wbs_code = models.CharField(max_length=50, unique=True, verbose_name="PSP Element")
    title = models.CharField(max_length=255, verbose_name="Title")
    cost_center = models.ForeignKey(
        CostCenter,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='wbs_elements',
        verbose_name="Cost Center",
    )
    responsible_person = models.ForeignKey(
        'hr.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='responsible_wbs_elements',
        verbose_name="Responsible Person",
    )
    comment = models.TextField(blank=True, verbose_name="Comment")
    work_group = models.ForeignKey(
        'hr.Workgroup',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Work Group",
        related_name='wbs_elements',
    )
    period_start = models.DateField(
        null=True,
        blank=True,
        verbose_name="Period Start",
    )
    period_end = models.DateField(
        null=True,
        blank=True,
        verbose_name="Period End",
    )
    subject_to_annual_recurrence = models.BooleanField(
        default=False,
        verbose_name="Subject to Annual Recurrence",
    )
    is_inactive = models.BooleanField(
        default=False,
        verbose_name="Is Inactive",
    )

    objects = WBSElementQuerySet.as_manager()

    class Meta:
        verbose_name = "PSP Element"
        verbose_name_plural = "PSP Elements"
        ordering = ['wbs_code']
        permissions = [
            ("view_psp_element", "Can view individual PSP elements"),
            ("manage_psp_element", "Can manage PSP elements"),
            ("view_psp_overview", "Can view PSP overview with bookings and costs"),
        ]

    def __str__(self):
        short_title = (self.title[:80] + '...') if len(self.title) > 80 else self.title
        return f"{self.wbs_code} - {short_title}"


class WBSElementYearEstimate(BaseModel):
    """Yearly funding and cost estimates for a PSP element."""
    wbs_element = models.ForeignKey(
        WBSElement,
        on_delete=models.CASCADE,
        related_name='year_estimates',
        verbose_name="PSP Element",
    )
    year = models.PositiveIntegerField(verbose_name="Year / Period")
    funding = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Funding",
    )
    consumables_estimate = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Consumables Estimate",
    )
    travel_estimate = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Travel Costs Estimate",
    )
    animal_costs_estimate = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Animal Costs Estimate",
    )

    class Meta:
        verbose_name = "PSP Element Year Estimate"
        verbose_name_plural = "PSP Element Year Estimates"
        unique_together = ('wbs_element', 'year')
        ordering = ['year']

