"""
apps/finances/models.py
Project: THERESE – Transparent HR Employee Resource Evaluation System Enhanced
"""

from django.core.validators import FileExtensionValidator
from django.db import models

from apps.core.models import BaseModel

THIRD_PARTY_FUNDING_EXTENSIONS = ['pdf', 'jpg', 'jpeg', 'png', 'gif', 'webp']


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


class ContactPerson(BaseModel):
    """
    Lightweight contact (e.g. from third-party funding reports).

    Intentionally simpler than Employee: name + optional org/contact details only.
    A contact may be linked to zero, one, or many PSP elements / cost centers.
    """
    first_name = models.CharField(max_length=100, blank=True, verbose_name="First name")
    last_name = models.CharField(max_length=100, verbose_name="Last name")
    business_area = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Business area",
    )
    phone = models.CharField(max_length=50, blank=True, verbose_name="Phone")
    email = models.EmailField(blank=True, verbose_name="Email")
    comments = models.CharField(
        max_length=400,
        blank=True,
        verbose_name="Comments",
    )

    class Meta:
        verbose_name = "Contact Person"
        verbose_name_plural = "Contact Persons"
        ordering = ['last_name', 'first_name']
        unique_together = ('last_name', 'first_name')
        permissions = [
            ("view_contact_person_list", "Can view contact persons"),
            ("manage_contact_person", "Can manage contact persons"),
        ]

    def __str__(self):
        if self.first_name:
            return f"{self.last_name}, {self.first_name}"
        return self.last_name


class CostCenter(BaseModel):
    cost_center = models.CharField(max_length=50, unique=True, verbose_name="Cost Center")
    comments = models.TextField(blank=True, verbose_name="Comments")
    contact_person = models.ForeignKey(
        ContactPerson,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cost_centers',
        verbose_name="Contact person",
    )
    # Cost-type flags: control which year-estimate amount columns apply (LOMV is always shown).
    has_material_costs = models.BooleanField(
        default=False,
        verbose_name="Sachkosten / Material costs",
    )
    has_personnel_costs = models.BooleanField(
        default=False,
        verbose_name="Personalkosten / Personnel costs",
    )
    has_domestic_travel_costs = models.BooleanField(
        default=False,
        verbose_name="Reisekosten Inland / Domestic travel costs",
    )
    has_foreign_travel_costs = models.BooleanField(
        default=False,
        verbose_name="Reisekosten Ausland / Foreign travel costs",
    )
    has_third_party_investments = models.BooleanField(
        default=False,
        verbose_name="Drittmittel-Investitionen / Third-party investments",
    )
    has_publication_costs = models.BooleanField(
        default=False,
        verbose_name="Publikationskosten / Publication costs",
    )
    has_animal_husbandry_costs = models.BooleanField(
        default=False,
        verbose_name="Tierhaltungskosten / Animal husbandry costs",
    )
    has_transfer_to_third_parties = models.BooleanField(
        default=False,
        verbose_name="Weitergabe an Dritte / Transfer to third parties",
    )
    has_internal_service_charges = models.BooleanField(
        default=False,
        verbose_name="Interne Leistungsverrechnung / Internal service charges",
    )

    class Meta:
        verbose_name = "Cost Center"
        verbose_name_plural = "Cost Centers"
        ordering = ['cost_center']
        permissions = [
            ("manage_cost_center", "Can manage cost centers"),
        ]

    def __str__(self):
        return self.cost_center


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
    contact_person = models.ForeignKey(
        ContactPerson,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='wbs_elements',
        verbose_name="Contact person",
    )
    # Cost-type flags (.1–.9): control which year-estimate amount columns apply.
    has_material_costs = models.BooleanField(
        default=False,
        verbose_name=".1 - Sachkosten / Material costs",
    )
    has_personnel_costs = models.BooleanField(
        default=False,
        verbose_name=".2 - Personalkosten / Personnel costs",
    )
    has_domestic_travel_costs = models.BooleanField(
        default=False,
        verbose_name=".3 - Reisekosten Inland / Domestic travel costs",
    )
    has_foreign_travel_costs = models.BooleanField(
        default=False,
        verbose_name=".4 - Reisekosten Ausland / Foreign travel costs",
    )
    has_third_party_investments = models.BooleanField(
        default=False,
        verbose_name=".5 - Drittmittel-Investitionen / Third-party investments",
    )
    has_publication_costs = models.BooleanField(
        default=False,
        verbose_name=".6 - Publikationskosten / Publication costs",
    )
    has_animal_husbandry_costs = models.BooleanField(
        default=False,
        verbose_name=".7 - Tierhaltungskosten / Animal husbandry costs",
    )
    has_transfer_to_third_parties = models.BooleanField(
        default=False,
        verbose_name=".8 - Weitergabe an Dritte / Transfer to third parties",
    )
    has_internal_service_charges = models.BooleanField(
        default=False,
        verbose_name=".9 - Interne Leistungsverrechnung / Internal service charges",
    )
    third_party_funding_commitment = models.FileField(
        upload_to='finances/psp/third_party_funding/%Y/%m/',
        blank=True,
        null=True,
        max_length=255,
        verbose_name="Third-party funding commitment",
        validators=[FileExtensionValidator(allowed_extensions=THIRD_PARTY_FUNDING_EXTENSIONS)],
    )
    third_party_funder_identifier = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Third-party funder identifier",
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
            (
                "import_third_party_funding_report",
                "Can import third-party funding reports",
            ),
        ]

    def __str__(self):
        short_title = (self.title[:80] + '...') if len(self.title) > 80 else self.title
        return f"{self.wbs_code} - {short_title}"


class PSPYearlyCostAmounts(BaseModel):
    """
    Shared cost-type amount columns for estimates, true spending, and obligo.
    Not used as a table itself — only via concrete subclasses.
    """
    material_costs = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=".1 - Sachkosten / Material costs",
    )
    personnel_costs = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=".2 - Personalkosten / Personnel costs",
    )
    domestic_travel_costs = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=".3 - Reisekosten Inland / Domestic travel costs",
    )
    foreign_travel_costs = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=".4 - Reisekosten Ausland / Foreign travel costs",
    )
    third_party_investments = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=".5 - Drittmittel-Investitionen / Third-party investments",
    )
    publication_costs = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=".6 - Publikationskosten / Publication costs",
    )
    animal_husbandry_costs = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=".7 - Tierhaltungskosten / Animal husbandry costs",
    )
    transfer_to_third_parties = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=".8 - Weitergabe an Dritte / Transfer to third parties",
    )
    internal_service_charges = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=".9 - Interne Leistungsverrechnung / Internal service charges",
    )

    class Meta:
        abstract = True


class CostCenterYearEstimate(PSPYearlyCostAmounts):
    """Yearly Lomv + cost-type estimates for a cost center."""
    cost_center = models.ForeignKey(
        CostCenter,
        on_delete=models.CASCADE,
        related_name='year_estimates',
        verbose_name="Cost Center",
    )
    year = models.PositiveIntegerField(verbose_name="Year / Period")
    lomv = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Lomv",
    )

    class Meta:
        verbose_name = "Cost Center Year Estimate"
        verbose_name_plural = "Cost Center Year Estimates"
        unique_together = ('cost_center', 'year')
        ordering = ['year']

    def __str__(self):
        return f"{self.cost_center.cost_center} — {self.year} (estimate)"


class CostCenterTrueYearlySpending(PSPYearlyCostAmounts):
    """
    Actual incurred costs for a cost center (snapshot by date of update).

    Not shown in the cost-center editor UI (managed separately, e.g. admin).
    """
    cost_center = models.ForeignKey(
        CostCenter,
        on_delete=models.CASCADE,
        related_name='true_yearly_spendings',
        verbose_name="Cost Center",
    )
    date_of_update = models.DateField(verbose_name="Date of update")

    class Meta:
        verbose_name = "Cost Center True Yearly Spending"
        verbose_name_plural = "Cost Center True Yearly Spendings"
        unique_together = ('cost_center', 'date_of_update')
        ordering = ['-date_of_update']

    def __str__(self):
        return f"{self.cost_center.cost_center} — {self.date_of_update} (true spending)"


class CostCenterObligo(PSPYearlyCostAmounts):
    """
    Open commitments (Obligo) for a cost center, snapshot by date of update.

    Not shown in the cost-center editor UI (managed separately, e.g. admin).
    """
    cost_center = models.ForeignKey(
        CostCenter,
        on_delete=models.CASCADE,
        related_name='obligos',
        verbose_name="Cost Center",
    )
    date_of_update = models.DateField(verbose_name="Date of update")
    personal = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Personalobligo",
    )

    class Meta:
        verbose_name = "Cost Center Obligo"
        verbose_name_plural = "Cost Center Obligos"
        unique_together = ('cost_center', 'date_of_update')
        ordering = ['-date_of_update']

    def __str__(self):
        return f"{self.cost_center.cost_center} — {self.date_of_update} (obligo)"


class WBSElementYearEstimate(PSPYearlyCostAmounts):
    """Yearly cost estimates for a PSP element (one amount per enabled cost type)."""
    wbs_element = models.ForeignKey(
        WBSElement,
        on_delete=models.CASCADE,
        related_name='year_estimates',
        verbose_name="PSP Element",
    )
    year = models.PositiveIntegerField(verbose_name="Year / Period")

    class Meta:
        verbose_name = "PSP Element Year Estimate"
        verbose_name_plural = "PSP Element Year Estimates"
        unique_together = ('wbs_element', 'year')
        ordering = ['year']

    def __str__(self):
        return f"{self.wbs_element.wbs_code} — {self.year} (estimate)"


class WBSElementTrueYearlySpending(PSPYearlyCostAmounts):
    """
    Actual incurred costs for a PSP element (snapshot by date of update).

    Same amount columns as year estimates, but not shown in the PSP element
    editor UI (managed separately, e.g. via import or admin).
    """
    wbs_element = models.ForeignKey(
        WBSElement,
        on_delete=models.CASCADE,
        related_name='true_yearly_spendings',
        verbose_name="PSP Element",
    )
    date_of_update = models.DateField(verbose_name="Date of update")

    class Meta:
        verbose_name = "PSP Element True Yearly Spending"
        verbose_name_plural = "PSP Element True Yearly Spendings"
        unique_together = ('wbs_element', 'date_of_update')
        ordering = ['-date_of_update']

    def __str__(self):
        return f"{self.wbs_element.wbs_code} — {self.date_of_update} (true spending)"


class WBSElementObligo(PSPYearlyCostAmounts):
    """
    Open commitments (Obligo) for a PSP element, snapshot by date of update.

    Not shown in the PSP element editor UI (managed separately, e.g. admin).
    """
    wbs_element = models.ForeignKey(
        WBSElement,
        on_delete=models.CASCADE,
        related_name='obligos',
        verbose_name="PSP Element",
    )
    date_of_update = models.DateField(verbose_name="Date of update")
    personal = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Personalobligo",
    )

    class Meta:
        verbose_name = "PSP Element Obligo"
        verbose_name_plural = "PSP Element Obligos"
        unique_together = ('wbs_element', 'date_of_update')
        ordering = ['-date_of_update']

    def __str__(self):
        return f"{self.wbs_element.wbs_code} — {self.date_of_update} (obligo)"
