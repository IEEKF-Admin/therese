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

    class Meta:
        verbose_name = "Room"
        verbose_name_plural = "Rooms"
        unique_together = ('building', 'room_number')
        ordering = ['building__number', 'room_number']

    def __str__(self):
        if self.colloquial_name:
            return f"{self.colloquial_name} ({self.room_number})"
        return self.room_number


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

    class Meta:
        verbose_name = "Employee"
        verbose_name_plural = "Employees"
        ordering = ['last_name', 'first_name']
    
    website = models.URLField(blank=True, verbose_name="Website")

    class Meta:
        verbose_name = "Employee"
        verbose_name_plural = "Employees"
        ordering = ['last_name', 'first_name']
        permissions = [
            ("can_view_employees", "Can view employee list and details"),
            ("manage_employee", "Can manage employees (create and fully edit)"),
        ]

    def __str__(self):
        prefix = f"{self.prefix} " if self.prefix else ""
        return f"{prefix}{self.first_name} {self.last_name} ({self.employee_number})"

    def get_full_name(self):
        prefix = f"{self.prefix} " if self.prefix else ""
        return f"{prefix}{self.first_name} {self.last_name}".strip()

    def get_contract_as_of(self, as_of=None):
        """Return the contract valid on as_of (defaults to today)."""
        from django.utils import timezone
        from django.db.models import Q

        if as_of is None:
            as_of = timezone.now().date()
        return (
            self.contracts.filter(
                Q(valid_until__isnull=True) | Q(valid_until__gte=as_of),
                valid_from__lte=as_of,
            )
            .order_by('-valid_from')
            .first()
        )

    def get_monthly_salary(self, as_of=None):
        """
        Monthly salary for cost calculations and displays.
        Always taken from the relevant contract (never Employee.monthly_salary).
        """
        contract = self.get_contract_as_of(as_of)
        if contract is None:
            return None
        return contract.get_monthly_salary()


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
    plan_position_number = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Plan Position Number",
    )
    monthly_salary = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Monthly Salary",
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

    comments = models.TextField(blank=True, verbose_name="Contract Comments")

    class Meta:
        verbose_name = "Contract"
        verbose_name_plural = "Contracts"
        ordering = ['employee', '-valid_from']

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValidationError({
                'valid_until': 'End date cannot be before start date.'
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
        super().save(*args, **kwargs)

    def get_monthly_salary(self):
        """Resolved monthly salary for this contract (stored value, with payscale fallback)."""
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

    def __str__(self):
        return f"Contract for {self.employee} from {self.valid_from} ({self.weekly_hours} hours)"

    @property
    def is_current(self):
        from django.utils import timezone
        if not self.valid_from:
            return False
        today = timezone.now().date()
        return (self.valid_from <= today) and (
            self.valid_until is None or self.valid_until >= today
        )


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
    """Hours-based funding allocation for an employee on a WBS Element"""
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='allocations',
        verbose_name="Employee"
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
    
    weekly_hours_allocated = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name="Allocated Weekly Hours"
    )
    
    start_date = models.DateField(verbose_name="Valid From")
    end_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Valid Until"
    )
    
    comments = models.TextField(blank=True, verbose_name="Comments")

    class Meta:
        verbose_name = "Funding Allocation"
        verbose_name_plural = "Funding Allocations"
        ordering = ['-start_date']
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
        return f"{self.employee} → {funding_target_display(self)} ({self.weekly_hours_allocated} hours)"

    @property
    def funding_target_label(self):
        from apps.finances.funding_sources import funding_target_display
        return funding_target_display(self)


class SalarySupplement(BaseModel):
    """Salary supplement for an employee"""
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='salary_supplements',
        verbose_name="Employee"
    )
    percentage = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="Percentage")
    comment = models.TextField(blank=True, verbose_name="Comment")

    class Meta:
        verbose_name = "Salary Supplement"
        verbose_name_plural = "Salary Supplements"
        ordering = ['employee', '-created_at']

    def __str__(self):
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

