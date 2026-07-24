"""
apps/hr/models.py

Project: THERESE – Transparent HR Employee Resource Evaluation System Enhanced
All models related to employees, contracts, allocations and salary supplements.
Fully in English.
"""

from django.db import models
from django.core.validators import RegexValidator
from apps.core.models import BaseModel
from apps.accounts.models import CustomUser

# Finance models - nur das, was wirklich benötigt wird
from apps.finances.models import CostCenter, WBSElement


class Gender(models.TextChoices):
    MALE = 'M', 'Male'
    FEMALE = 'F', 'Female'
    DIVERSE = 'D', 'Diverse'
    NOT_SPECIFIED = 'X', 'Not specified'


class Building(BaseModel):
    number = models.CharField(max_length=20, unique=True, verbose_name="Building Number")
    name = models.CharField(max_length=100, blank=True, verbose_name="Building Name")
    address = models.TextField(blank=True, verbose_name="Address")

    class Meta:
        verbose_name = "Building"
        verbose_name_plural = "Buildings"
        ordering = ['number']
        permissions = [
            ("manage_location", "Can manage buildings, rooms and phones"),
        ]

    def __str__(self):
        return f"{self.number} - {self.name}" if self.name else self.number


class Room(BaseModel):
    building = models.ForeignKey(
        Building,
        on_delete=models.PROTECT,
        related_name='rooms',
        verbose_name="Building"
    )
    room_number = models.CharField(max_length=50, verbose_name="Room Number")
    colloquial_name = models.CharField(max_length=100, blank=True, verbose_name="Colloquial Name")
    comment = models.TextField(blank=True, verbose_name="Comment")
    chemical = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name='Chemical (work area)',
        help_text=(
            'If set, this room can be selected as a chemical work area / exposure area '
            'on chemical inventory items.'
        ),
    )

    class Meta:
        verbose_name = "Room"
        verbose_name_plural = "Rooms"
        unique_together = ('building', 'room_number')
        ordering = ['building__number', 'room_number']

    def __str__(self):
        building = self.building.number if self.building_id else '?'
        if self.colloquial_name:
            return f'{building} / {self.colloquial_name} ({self.room_number})'
        return f'{building} / {self.room_number}'

    @classmethod
    def chemical_work_area_qs(cls):
        """Rooms selectable as chemical work areas."""
        return cls.objects.filter(chemical=True).select_related('building').order_by(
            'building__number', 'room_number',
        )

    @classmethod
    def with_storage_qs(cls):
        """Rooms that have at least one storage location (cabinet/shelf/…)."""
        return (
            cls.objects.filter(storage_items__isnull=False)
            .select_related('building')
            .distinct()
            .order_by('building__number', 'room_number')
        )


class PhoneNumber(BaseModel):
    room = models.ForeignKey(
        Room,
        on_delete=models.CASCADE,
        related_name='phone_numbers',
        verbose_name="Room"
    )
    phone_number = models.CharField(max_length=30, verbose_name="Phone Number")

    class Meta:
        verbose_name = "Phone Number"
        verbose_name_plural = "Phone Numbers"
        ordering = ['room', 'phone_number']

    def __str__(self):
        return self.phone_number


class RoomStorageItem(BaseModel):
    """
    Storage location within a room (cabinet, fridge, shelf, …).

    Used by Chemicals inventory items similarly to phone numbers for rooms.
    """

    room = models.ForeignKey(
        Room,
        on_delete=models.CASCADE,
        related_name='storage_items',
        verbose_name='Room',
    )
    name = models.CharField(max_length=120, verbose_name='Storage name')
    storage_type = models.CharField(
        max_length=80,
        blank=True,
        verbose_name='Type',
        help_text='e.g. cabinet, fridge, shelf, gas store',
    )
    comment = models.TextField(blank=True, verbose_name='Comment')

    class Meta:
        verbose_name = 'Room storage item'
        verbose_name_plural = 'Room storage items'
        ordering = ['room', 'name']
        unique_together = ('room', 'name')

    def __str__(self):
        label = self.name
        if self.storage_type:
            label = f'{self.name} ({self.storage_type})'
        return f'{self.room}: {label}'


class Employee(BaseModel):
    employee_number = models.CharField(max_length=20, unique=True, verbose_name="Employee Number")
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employee',
        verbose_name="Django User"
    )

    # Personal Information
    prefix = models.CharField(max_length=20, blank=True, verbose_name="Prefix / Title")
    first_name = models.CharField(max_length=100, verbose_name="First Name")
    last_name = models.CharField(max_length=100, verbose_name="Last Name")
    gender = models.CharField(
        max_length=1,
        choices=Gender.choices,
        default=Gender.NOT_SPECIFIED,
        verbose_name="Gender"
    )
    date_of_birth = models.DateField(null=True, blank=True, verbose_name="Date of Birth")
    country_of_origin = models.CharField(max_length=100, blank=True, verbose_name="Country of Origin")
    place_of_birth = models.CharField(max_length=100, blank=True, verbose_name="Place of Birth")

    # Contact Information
    email_professional = models.EmailField(blank=True, verbose_name="Professional Email")
    email_private = models.EmailField(blank=True, verbose_name="Private Email")
    google_account = models.EmailField(blank=True, verbose_name="Google Account")
    private_phone_number = models.CharField(max_length=30, blank=True, verbose_name="Private Phone")

    # Office Location
    room = models.ForeignKey(
        Room,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employees',
        verbose_name="Room"
    )
    phone_number = models.CharField(max_length=30, blank=True, null=True, verbose_name="Office Phone")

    # Address
    street = models.CharField(max_length=100, blank=True, verbose_name="Street")
    house_number = models.CharField(max_length=20, blank=True, verbose_name="House Number")
    postal_code = models.CharField(max_length=10, blank=True, verbose_name="Postal Code")
    city = models.CharField(max_length=100, blank=True, verbose_name="City")
    country = models.CharField(max_length=100, default="Germany", verbose_name="Country")

    scan_of_contract = models.FileField(
        upload_to='contract_scans/',
        null=True,
        blank=True,
        verbose_name="Scan of Contract"
    )
    profile_picture = models.ImageField(
        upload_to='employee_pictures/',
        null=True,
        blank=True,
        verbose_name="Profile Picture"
    )
    monthly_salary = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Monthly Salary (€)"
    )
    job = models.ForeignKey(
        'tasks.RecruitmentJob',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='employees',
        verbose_name="Job",
    )

    cost_center = models.ForeignKey(
        'finances.CostCenter',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employees',
        verbose_name="Cost Center"
    )
    website = models.URLField(blank=True, verbose_name="Website")

    is_pending = models.BooleanField(
        default=False,
        verbose_name="Pending",
        help_text=(
            "Employee was created from a funding-report import and is still "
            "pending review. Visible in the employee list."
        ),
    )
    check_needed = models.BooleanField(
        default=False,
        verbose_name="Check needed",
        help_text=(
            "Manual review required. A Django login user may only be linked "
            "when this flag is No."
        ),
    )

    class Meta:
        verbose_name = "Employee"
        verbose_name_plural = "Employees"
        ordering = ['last_name', 'first_name']
        permissions = [
            (
                "can_view_employees",
                "Can view employees in shared workgroups",
            ),
            (
                "manage_employee",
                "Can manage employees in shared workgroups (create and edit)",
            ),
            (
                "can_view_all_employees",
                "Can view all employees institute-wide (ignore workgroup scope)",
            ),
            (
                "manage_all_employees",
                "Can manage all employees institute-wide (ignore workgroup scope)",
            ),
        ]

    def __str__(self):
        prefix = f"{self.prefix} " if self.prefix else ""
        return f"{prefix}{self.first_name} {self.last_name} ({self.employee_number})"

    def get_full_name(self):
        prefix = f"{self.prefix} " if self.prefix else ""
        return f"{prefix}{self.first_name} {self.last_name}".strip()

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.user_id and self.check_needed:
            raise ValidationError({
                'user': (
                    'A Django login user can only be linked when '
                    '“Check needed” is No.'
                ),
            })
        if self.user_id and self.is_pending:
            raise ValidationError({
                'user': (
                    'A Django login user can only be linked when the employee '
                    'is no longer pending.'
                ),
            })

    def get_contract_as_of(self, as_of=None):
        """
        Soft-select the contract open on ``as_of`` (defaults to today).

        Among contracts that have started and not yet ended, the one with the
        latest ``valid_from`` wins. Future-dated contracts are ignored.
        See ``apps.hr.validity``.
        """
        from apps.hr.validity import select_contract_as_of

        return select_contract_as_of(self.contracts.all(), as_of)

    def get_funding_allocation_as_of(self, *, wbs_element=None, cost_center=None, as_of=None):
        """
        Soft-select the funding allocation for one target open on ``as_of``.

        Pass exactly one of ``wbs_element`` or ``cost_center``.
        Winner = latest ``start_date`` among open rows (not future-started).
        Only allocations on an active contract are considered for current lookups.
        """
        from apps.hr.validity import select_allocation_as_of

        qs = self.allocations.filter(contract__is_active=True)
        if wbs_element is not None:
            qs = qs.filter(wbs_element=wbs_element, cost_center__isnull=True)
        elif cost_center is not None:
            qs = qs.filter(cost_center=cost_center, wbs_element__isnull=True)
        else:
            raise ValueError('Pass wbs_element or cost_center.')
        return select_allocation_as_of(qs, as_of)

    def get_open_funding_allocations_as_of(self, as_of=None):
        """
        All soft-winning open funding allocations on ``as_of`` (one per target).
        """
        from apps.hr.validity import (
            allocation_open_on_q,
            dedupe_allocations_as_of,
            resolve_as_of,
        )

        as_of = resolve_as_of(as_of)
        open_rows = list(
            self.allocations.filter(allocation_open_on_q(as_of), contract__is_active=True)
            .select_related('wbs_element', 'cost_center', 'contract')
            .order_by('-start_date', '-pk')
        )
        return dedupe_allocations_as_of(open_rows, as_of)

    def get_monthly_salary(self, as_of=None):
        """
        Full-time (100%) base monthly salary from the relevant contract.
        Always taken from the contract (never Employee.monthly_salary).
        Does not include supplements; use contract true-cost helpers for costs.
        """
        contract = self.get_contract_as_of(as_of)
        if contract is None:
            return None
        return contract.get_monthly_salary()

    def get_monthly_costs(self, as_of=None):
        """True monthly personnel costs from the relevant contract (as of date)."""
        contract = self.get_contract_as_of(as_of)
        if contract is None:
            return None
        return contract.get_monthly_costs()


class Contract(BaseModel):
    """Employment contract version for an employee"""
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='contracts',
        verbose_name="Employee"
    )

    pay_scale_group = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Pay Scale Group",
    )
    experience_level = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Experience Level",
    )
    job_number = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Job Number",
    )
    monthly_salary = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Monthly Salary (100% workload)",
        help_text=(
            "Monthly salary the person would receive at 100% working time "
            "(full-time reference). Part-time hours are applied only when "
            "calculating true costs. Salary supplements are added on top."
        ),
    )

    weekly_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name="Weekly Working Hours"
    )

    valid_from = models.DateField(verbose_name="Valid From")
    valid_until = models.DateField(
        null=True,
        blank=True,
        verbose_name="Valid Until"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Active",
        help_text=(
            "Yes/No. Can be set manually. Automatically set to No when "
            "Valid Until is in the past."
        ),
    )
    check_needed = models.BooleanField(
        default=False,
        verbose_name="Check needed",
        help_text=(
            "Manual review required for this contract "
            "(e.g. after funding-report import)."
        ),
    )

    comments = models.TextField(blank=True, verbose_name="Contract Comments")

    class Meta:
        verbose_name = "Contract"
        verbose_name_plural = "Contracts"
        # Chronological: start date, then end date (open ends last via formset/nulls_last)
        ordering = ['employee', 'valid_from', 'valid_until', 'pk']

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValidationError({
                'valid_until': 'End date cannot be before start date.'
            })
        # Auto-deactivate when end date is in the past (still allows manual No).
        from apps.hr.validity import apply_past_end_deactivation
        apply_past_end_deactivation(self, end_attr='valid_until')
        # At most one active contract per employee.
        if self.is_active and self.employee_id:
            others = Contract.objects.filter(
                employee_id=self.employee_id,
                is_active=True,
            )
            if self.pk:
                others = others.exclude(pk=self.pk)
            if others.exists():
                raise ValidationError({
                    'is_active': (
                        'Only one active contract is allowed per employee. '
                        'Deactivate the other contract first.'
                    ),
                })
        # When both payscale fields are set, store the TV-L monthly salary.
        if self.pay_scale_group and self.experience_level is not None:
            from apps.finances.models import PayScale
            salary = (
                PayScale.get_current()
                .filter(
                    pay_scale_group=self.pay_scale_group,
                    experience_level=self.experience_level,
                )
                .values_list('monthly_salary', flat=True)
                .first()
            )
            if salary is not None:
                self.monthly_salary = salary

    def save(self, *args, **kwargs):
        self.full_clean()
        was_active = True
        if self.pk:
            was_active = (
                Contract.objects.filter(pk=self.pk)
                .values_list('is_active', flat=True)
                .first()
            )
            if was_active is None:
                was_active = True
        super().save(*args, **kwargs)
        # Expired / inactive contract → all its funding allocations inactive.
        if not self.is_active:
            self.funding_allocations.filter(is_active=True).update(is_active=False)
        elif was_active is False and self.is_active:
            # Re-activated contract does not auto-reactivate FAs (manual).
            pass

    def get_monthly_salary(self):
        """
        Full-time (100% workload) monthly base salary for this contract.

        Stored value first, otherwise current TV-L table for group/level.
        Does not include salary supplements or part-time scaling.
        """
        if self.monthly_salary is not None:
            return self.monthly_salary
        if self.pay_scale_group and self.experience_level is not None:
            from apps.finances.models import PayScale
            return (
                PayScale.get_current()
                .filter(
                    pay_scale_group=self.pay_scale_group,
                    experience_level=self.experience_level,
                )
                .values_list('monthly_salary', flat=True)
                .first()
            )
        return None

    def get_salary_supplements_total(self):
        """
        Sum of salary supplements on this contract at 100% workload.

        Percentage supplements are taken of the base monthly salary;
        fixed amounts are added as euro amounts per month.
        """
        from decimal import Decimal, ROUND_HALF_UP

        base = self.get_monthly_salary()
        base_dec = Decimal(base) if base is not None else Decimal('0')
        total = Decimal('0.00')
        # Prefer prefetched relation when present
        supplements = self.salary_supplements.all()
        for ss in supplements:
            if ss.fixed_amount is not None:
                total += Decimal(ss.fixed_amount)
            elif ss.percentage is not None and base is not None:
                total += base_dec * Decimal(ss.percentage) / Decimal('100')
        return total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def get_monthly_salary_with_supplements(self):
        """
        Full-time (100%) monthly salary including salary supplements.

        ``base + Σ(percentage of base) + Σ(fixed amounts)``.
        """
        from decimal import Decimal, ROUND_HALF_UP

        base = self.get_monthly_salary()
        supplements = self.get_salary_supplements_total()
        if base is None and supplements == 0:
            return None
        base_dec = Decimal(base) if base is not None else Decimal('0')
        return (base_dec + Decimal(supplements)).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )

    def get_workload_fraction(self):
        """
        Contract weekly hours / global default full-time hours.

        Missing or invalid default ⇒ 1 (100%). Missing weekly hours ⇒ 1.
        """
        from decimal import Decimal, ROUND_HALF_UP

        from apps.core.models import GlobalSetting

        if self.weekly_hours is None:
            return Decimal('1')
        default_hours = GlobalSetting.get_default_weekly_hours()
        if not default_hours or default_hours <= 0:
            return Decimal('1')
        return (Decimal(self.weekly_hours) / Decimal(default_hours)).quantize(
            Decimal('0.0001'), rounding=ROUND_HALF_UP
        )

    def get_monthly_costs(self):
        """
        True monthly personnel costs for this contract:

        (monthly_salary_100% + supplements) × (weekly_hours / default_weekly_hours)
        × true_cost_multiplicator
        """
        from decimal import Decimal, ROUND_HALF_UP

        from apps.core.models import GlobalSetting

        salary = self.get_monthly_salary_with_supplements()
        if salary is None:
            return None
        multiplicator = GlobalSetting.get_true_cost_multiplicator()
        fraction = self.get_workload_fraction()
        return (
            Decimal(salary) * fraction * Decimal(multiplicator)
        ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def suggest_base_monthly_salary_for_allocation_amount(
        self, excel_amount, workhours_percentage
    ):
        """
        Reverse-calculate the 100% base ``monthly_salary`` so that

        (base + supplements(base)) × workload_fraction × multi × (workhours_% / 100)
        equals ``excel_amount``.

        Percentage supplements are treated as shares of the (unknown) base;
        fixed supplements are held constant.
        """
        from decimal import Decimal, ROUND_HALF_UP

        from apps.core.models import GlobalSetting

        multi = Decimal(GlobalSetting.get_true_cost_multiplicator())
        fraction = self.get_workload_fraction()
        share = Decimal(workhours_percentage or 0) / Decimal('100')
        denom = fraction * multi * share
        if denom <= 0:
            return None

        gehalt_100 = Decimal(excel_amount) / denom

        pct_sum = Decimal('0')
        fixed_sum = Decimal('0')
        for ss in self.salary_supplements.all():
            if ss.fixed_amount is not None:
                fixed_sum += Decimal(ss.fixed_amount)
            elif ss.percentage is not None:
                pct_sum += Decimal(ss.percentage)

        factor = Decimal('1') + (pct_sum / Decimal('100'))
        if factor <= 0:
            return None
        base = (gehalt_100 - fixed_sum) / factor
        return base.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def active_funding_percentage_total(self):
        """Sum of workhours % of active funding allocations on this contract."""
        from decimal import Decimal

        total = Decimal('0.00')
        for pct in self.funding_allocations.filter(is_active=True).values_list(
            'workhours_percentage', flat=True
        ):
            total += Decimal(pct or 0)
        return total.quantize(Decimal('0.01'))

    def __str__(self):
        return f"Contract for {self.employee} from {self.valid_from} ({self.weekly_hours} hours)"

    def is_open_on(self, as_of=None) -> bool:
        """True if this contract is open on ``as_of`` (see apps.hr.validity)."""
        from apps.hr.validity import _require_active_flag, resolve_as_of

        as_of = resolve_as_of(as_of)
        if _require_active_flag(as_of) and not self.is_active:
            return False
        if not self.valid_from or self.valid_from > as_of:
            return False
        if self.valid_until is not None and self.valid_until < as_of:
            return False
        return True

    @property
    def is_current(self):
        """Open today (active, started, not ended). Soft winner is selected separately."""
        return self.is_open_on(None)


class EmployeeDocumentType(models.TextChoices):
    APPLICATION = 'application', 'Application / Bewerbung'
    CV = 'cv', 'Curriculum Vitae / Lebenslauf'
    LATEST_DEGREE_CERTIFICATE = (
        'latest_degree_certificate',
        'Latest Degree Certificate / Zeugnis des letzten Abschlusses',
    )
    SCAN_OF_CONTRACT = 'scan_of_contract', 'Scan of Contract / Vertragsscan'
    PROFILE_PICTURE = 'profile_picture', 'Profile Picture / Profilbild'


class EmployeeDocumentVersion(BaseModel):
    """Versioned employee documents (multiple uploads per document type)."""
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='document_versions',
        verbose_name="Employee",
    )
    document_type = models.CharField(
        max_length=30,
        choices=EmployeeDocumentType.choices,
        verbose_name="Document Type",
    )
    file = models.FileField(upload_to='employee_documents/%Y/%m/%d/')
    original_filename = models.CharField(max_length=255)
    uploaded_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_document_versions',
        verbose_name="Uploaded By",
    )

    class Meta:
        verbose_name = "Employee Document Version"
        verbose_name_plural = "Employee Document Versions"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_document_type_display()} – {self.original_filename}"


class FundingAllocation(BaseModel):
    """Percentage-based funding allocation for an employee on a WBS / cost center.

    Always belongs to exactly one Contract. ``employee`` is kept in sync with
    ``contract.employee`` for efficient filtering.
    """
    contract = models.ForeignKey(
        'Contract',
        on_delete=models.CASCADE,
        related_name='funding_allocations',
        verbose_name="Contract",
    )
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='allocations',
        verbose_name="Employee",
    )

    wbs_element = models.ForeignKey(
        WBSElement,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="WBS Element",
    )
    cost_center = models.ForeignKey(
        CostCenter,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='funding_allocations',
        verbose_name="Cost Center",
    )

    workhours_percentage = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        verbose_name="Percentage of Workhours",
        help_text="Share of the employee's contract weekly hours (0–100+).",
    )
    plan_position_number = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Plan Position Number",
    )
    
    start_date = models.DateField(verbose_name="Valid From")
    end_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Valid Until"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Active",
        help_text=(
            "Yes/No. Can be set manually. Automatically set to No when "
            "Valid Until is in the past."
        ),
    )

    comments = models.TextField(blank=True, verbose_name="Comments")
    # Marked by import when payroll/admin data for this allocation is confirmed.
    import_completed = models.BooleanField(
        default=False,
        verbose_name="Import completed",
        help_text=(
            "True when imported data confirms the administration process "
            "for this funding allocation is complete."
        ),
    )

    class Meta:
        verbose_name = "Funding Allocation"
        verbose_name_plural = "Funding Allocations"
        # Chronological: start date, then end date
        ordering = ['start_date', 'end_date', 'pk']
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(wbs_element__isnull=False, cost_center__isnull=True)
                    | models.Q(wbs_element__isnull=True, cost_center__isnull=False)
                ),
                name='funding_allocation_one_target',
            ),
        ]

    def __str__(self):
        from apps.finances.funding_sources import funding_target_display
        return (
            f"{self.employee} → {funding_target_display(self)} "
            f"({self.workhours_percentage}%)"
        )

    def is_open_on(self, as_of=None) -> bool:
        """True if this allocation is open on ``as_of`` (see apps.hr.validity)."""
        from apps.hr.validity import _require_active_flag, resolve_as_of

        as_of = resolve_as_of(as_of)
        if _require_active_flag(as_of) and not self.is_active:
            return False
        if not self.start_date or self.start_date > as_of:
            return False
        if self.end_date is not None and self.end_date < as_of:
            return False
        return True

    @property
    def is_current(self):
        """Open today (active, started, not ended). Soft winner via validity helpers."""
        return self.is_open_on(None)

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({
                'end_date': 'End date cannot be before start date.',
            })
        from apps.hr.validity import apply_past_end_deactivation
        apply_past_end_deactivation(self, end_attr='end_date')
        # Sync employee from contract; force inactive if contract is inactive.
        if self.contract_id:
            contract = self.contract
            self.employee_id = contract.employee_id
            if not contract.is_active:
                self.is_active = False
        elif self.contract and getattr(self.contract, 'employee_id', None):
            self.employee_id = self.contract.employee_id
            if not self.contract.is_active:
                self.is_active = False

    def save(self, *args, **kwargs):
        # Keep date order sane; soft overlap rule lives in validity helpers.
        if self.contract_id or getattr(self, 'contract', None):
            contract = self.contract
            if contract is not None:
                self.employee_id = contract.employee_id
                if not contract.is_active:
                    self.is_active = False
        self.full_clean()
        super().save(*args, **kwargs)

    @classmethod
    def for_employee_wbs_as_of(cls, employee, wbs_element, as_of=None):
        """Soft-select current FA for employee + PSP on ``as_of``."""
        from apps.hr.validity import select_allocation_as_of

        return select_allocation_as_of(
            cls.objects.filter(
                employee=employee,
                wbs_element=wbs_element,
                contract__is_active=True,
            ),
            as_of,
        )

    @property
    def funding_target_label(self):
        from apps.finances.funding_sources import funding_target_display
        return funding_target_display(self)


class SalarySupplement(BaseModel):
    """Salary supplement belonging to exactly one Contract.

    Use either ``percentage`` (%) or ``fixed_amount`` (€), not both.
    """
    contract = models.ForeignKey(
        'Contract',
        on_delete=models.CASCADE,
        related_name='salary_supplements',
        verbose_name="Contract",
    )
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='salary_supplements',
        verbose_name="Employee",
    )
    percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Percentage (%)",
        help_text=(
            "Percentage of the contract's 100% monthly salary. "
            "Leave empty if using a fixed amount."
        ),
    )
    fixed_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Fixed amount (€)",
        help_text=(
            "Fixed euro amount per month at 100% workload "
            "(scaled with weekly hours in true costs). "
            "Leave empty if using a percentage."
        ),
    )
    comment = models.TextField(blank=True, verbose_name="Comment")

    class Meta:
        verbose_name = "Salary Supplement"
        verbose_name_plural = "Salary Supplements"
        ordering = ['contract', '-created_at']

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.contract_id:
            self.employee_id = self.contract.employee_id
        elif self.contract and getattr(self.contract, 'employee_id', None):
            self.employee_id = self.contract.employee_id

        has_pct = self.percentage is not None
        has_fixed = self.fixed_amount is not None
        if has_pct and has_fixed:
            raise ValidationError(
                'Enter either a percentage or a fixed amount, not both.'
            )
        if not has_pct and not has_fixed:
            raise ValidationError(
                'Enter either a percentage (%) or a fixed amount (€).'
            )
        if has_pct and self.percentage < 0:
            raise ValidationError({'percentage': 'Percentage cannot be negative.'})
        if has_fixed and self.fixed_amount < 0:
            raise ValidationError({'fixed_amount': 'Fixed amount cannot be negative.'})

    def save(self, *args, **kwargs):
        if self.contract_id or getattr(self, 'contract', None):
            contract = self.contract
            if contract is not None:
                self.employee_id = contract.employee_id
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def is_fixed(self) -> bool:
        return self.fixed_amount is not None

    def __str__(self):
        if self.fixed_amount is not None:
            return f"{self.employee} - {self.fixed_amount} € (fixed)"
        return f"{self.employee} - {self.percentage}%"


class Workgroup(models.Model):
    """
    Project: THERESE
    Workgroup / Research Group Management
    """
    auth_group = models.OneToOneField(
        'auth.Group',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='workgroup',
        verbose_name='Django group',
    )
    short_name = models.CharField(
        max_length=80, 
        unique=True,
        help_text="Kurzbezeichnung, z.B. 'AI-Lab', 'MedTech-Team'"
    )
    long_name = models.CharField(
        max_length=200,
        help_text="Vollständiger Name der Arbeitsgruppe"
    )
    pi = models.ForeignKey(
        'Employee',
        on_delete=models.PROTECT,
        related_name='led_workgroups',
        verbose_name="Principal Investigator"
    )
    members = models.ManyToManyField(
        'Employee',                    # ← Geändert von CustomUser zu Employee
        related_name='workgroups',
        blank=True,
        verbose_name="Mitglieder"
    )

    class Meta:
        verbose_name = "Workgroup"
        verbose_name_plural = "Workgroups"
        ordering = ['short_name']
        permissions = [
            ("manage_working_group", "Can manage working groups"),
        ]

    def __str__(self):
        return f"{self.short_name} ({self.long_name})"

