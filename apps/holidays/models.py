"""Holiday request, entitlement, and related settings."""

from django.conf import settings
from django.db import models

from apps.core.models import BaseModel
from apps.hr.models import Employee


class HolidayProfile(BaseModel):
    """Per-employee holiday settings (workdays, consent, signature)."""

    employee = models.OneToOneField(
        Employee,
        on_delete=models.CASCADE,
        related_name='holiday_profile',
        verbose_name='Employee',
    )
    works_monday = models.BooleanField(default=True, verbose_name='Monday')
    works_tuesday = models.BooleanField(default=True, verbose_name='Tuesday')
    works_wednesday = models.BooleanField(default=True, verbose_name='Wednesday')
    works_thursday = models.BooleanField(default=True, verbose_name='Thursday')
    works_friday = models.BooleanField(default=True, verbose_name='Friday')
    share_with_institute = models.BooleanField(
        default=False,
        verbose_name='Show my holidays on the institute Gantt chart',
    )
    signature = models.ImageField(
        upload_to='holidays/signatures/',
        blank=True,
        null=True,
        verbose_name='Signature',
    )

    class Meta:
        verbose_name = 'Holiday Profile'
        verbose_name_plural = 'Holiday Profiles'

    def __str__(self):
        return f'Holiday profile {self.employee}'

    def weekday_flags(self):
        return [
            self.works_monday,
            self.works_tuesday,
            self.works_wednesday,
            self.works_thursday,
            self.works_friday,
            False,
            False,
        ]

    def workdays_per_week(self):
        return sum(1 for flag in self.weekday_flags()[:5] if flag)

    def works_on_weekday(self, weekday):
        flags = self.weekday_flags()
        if weekday < 0 or weekday > 6:
            return False
        return bool(flags[weekday])


class HolidayYearEntitlement(BaseModel):
    """Gross annual leave claim entered by the employee (this year / next year)."""

    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='holiday_entitlements',
        verbose_name='Employee',
    )
    year = models.PositiveIntegerField(verbose_name='Year')
    days = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        verbose_name='Entitlement (days)',
    )

    class Meta:
        verbose_name = 'Holiday Year Entitlement'
        verbose_name_plural = 'Holiday Year Entitlements'
        constraints = [
            models.UniqueConstraint(
                fields=['employee', 'year'],
                name='holiday_entitlement_employee_year_uniq',
            ),
        ]

    def __str__(self):
        return f'{self.employee} {self.year}: {self.days}'


class HolidayCustomDay(BaseModel):
    """Institute custom day (Brauchtum) for a calendar year."""

    class Mode(models.TextChoices):
        ALWAYS = 'always', 'Always a holiday'
        EXCEPT_AND = 'except_and', 'Holiday unless leave immediately before AND after'
        EXCEPT_OR = 'except_or', 'Holiday unless leave immediately before OR after'

    year = models.PositiveIntegerField(verbose_name='Year')
    day = models.DateField(verbose_name='Date')
    name = models.CharField(max_length=120, verbose_name='Name')
    mode = models.CharField(
        max_length=20,
        choices=Mode.choices,
        default=Mode.ALWAYS,
        verbose_name='Rule',
    )

    class Meta:
        verbose_name = 'Custom holiday (Brauchtum)'
        verbose_name_plural = 'Custom holidays (Brauchtum)'
        ordering = ['day']
        constraints = [
            models.UniqueConstraint(fields=['day'], name='holiday_custom_day_uniq'),
        ]

    def __str__(self):
        return f'{self.day}: {self.name}'


class HolidayEntitlementRate(BaseModel):
    """Editable lookup: workdays/week × contract months → claim days."""

    weekdays = models.PositiveSmallIntegerField(verbose_name='Workdays per week')
    contract_months = models.PositiveSmallIntegerField(verbose_name='Contract months in year')
    days = models.DecimalField(max_digits=5, decimal_places=1, verbose_name='Days')

    class Meta:
        verbose_name = 'Holiday entitlement rate'
        verbose_name_plural = 'Holiday entitlement rates'
        constraints = [
            models.UniqueConstraint(
                fields=['weekdays', 'contract_months'],
                name='holiday_entitlement_rate_uniq',
            ),
        ]

    def __str__(self):
        return f'{self.weekdays}d/w × {self.contract_months}m = {self.days}'


class HolidayRequest(BaseModel):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    class Kind(models.TextChoices):
        ORIGINAL = 'original', 'Original'
        AMENDMENT = 'amendment', 'Amendment'

    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='holiday_requests',
        verbose_name='Employee',
    )
    start_date = models.DateField(verbose_name='From')
    end_date = models.DateField(verbose_name='Until')
    day_count = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        verbose_name='Vacation days',
    )
    counted_dates = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Counted dates',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name='Status',
    )
    kind = models.CharField(
        max_length=20,
        choices=Kind.choices,
        default=Kind.ORIGINAL,
        verbose_name='Kind',
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='amendments',
        verbose_name='Amends request',
    )
    comment = models.TextField(blank=True, verbose_name='Comment')
    rejection_comment = models.TextField(blank=True, verbose_name='Rejection comment')
    submitted_at = models.DateTimeField(null=True, blank=True, verbose_name='Submitted at')
    decided_at = models.DateTimeField(null=True, blank=True, verbose_name='Decided at')
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='holiday_decisions',
        verbose_name='Decided by',
    )
    pdf_file = models.FileField(
        upload_to='holidays/pdfs/',
        blank=True,
        null=True,
        verbose_name='Generated PDF',
    )

    class Meta:
        verbose_name = 'Holiday Request'
        verbose_name_plural = 'Holiday Requests'
        ordering = ['-start_date', '-pk']
        default_permissions = ()
        permissions = [
            (
                'approve_workgroup_holiday',
                'Can approve holiday requests in own workgroups',
            ),
            (
                'approve_all_holiday',
                'Can approve holiday requests institute-wide',
            ),
        ]

    def __str__(self):
        return f'{self.employee} {self.start_date}–{self.end_date}'
