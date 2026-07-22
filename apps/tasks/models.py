"""
apps/tasks/models.py

Project: THERESE – Transparent HR Resource System Enhanced
Robust polymorphic Task System
"""

from django.db import models

from apps.core.models import BaseModel
from apps.finances.models import WBSElement
from apps.hr.models import Employee, Gender
from apps.tasks.recruitment_config import DurationOperator, RequiredMode, VisibilityMode


# = STATUS DEFINITIONS =
PURCHASE_STATUSES = [
    ('not_yet_processed', 'Not yet processed'),
    ('in_coordination', 'In coordination'),
    ('sent_to_administration', 'Sent to administration'),
]

# Note: 'coordination_completed' status has been removed as per streamlined workflow.
# Approvers now see POs as soon as WBS element is set by coordinator.
# Legacy data with old status will display the raw value until updated.

PERSONNEL_STATUSES = [
    ('not_yet_processed', 'Not yet processed'),
    ('sent_to_hr', 'Sent to HR Department'),
    ('hr_processing', 'Processing by HR Department'),
    ('works_council', 'Works Council'),
    ('completed', 'Completed'),
]

RECRUITMENT_STATUSES = [
    ('not_yet_processed', 'Not yet processed / Noch nicht bearbeitet'),
    ('coordination_completed', 'Coordination completed / Koordination abgeschlossen'),
    ('sent_to_administration', 'Sent to administration / An Verwaltung geschickt'),
    ('recruitment_completed', 'Recruitment completed / Einstellung abgeschlossen'),
]

RECRUITMENT_STATUS_ORDER = [
    'not_yet_processed',
    'coordination_completed',
    'sent_to_administration',
    'recruitment_completed',
]

GENERIC_STATUSES = [
    ('seen', 'Seen'),
    ('in_progress', 'In Progress'),
    ('done', 'Done'),
]


class Task(BaseModel):
    """Base Task Model"""
    TASK_TYPES = [
        ('purchase_order', 'Purchase Order'),
        ('personnel_reallocation', 'Personnel Reallocation'),
        ('personnel_contract_extension', 'Personnel Contract Extension'),
        ('personnel_recruitment', 'Personnel Recruitment'),
        ('generic_text', 'General Request'),
    ]

    task_type = models.CharField(max_length=50, choices=TASK_TYPES, verbose_name="Task Type")
    title = models.CharField(max_length=255, verbose_name="Title", blank=True)
    task_number = models.CharField(
        max_length=20, 
        unique=True, 
        blank=True, 
        null=True,           # Required for existing rows during task_number migration
        editable=False, 
        verbose_name="Task Number"
    )

    creator = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='created_tasks')
    assignee = models.ForeignKey(
        Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_tasks'
    )

    status = models.CharField(max_length=100, verbose_name="Status")
    last_status_change = models.DateTimeField(auto_now=True)
    last_changed_by = models.ForeignKey(
        Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='changed_tasks'
    )

    priority = models.CharField(
        max_length=20,
        choices=[('low', 'Low'), ('medium', 'Medium'), ('high', 'High')],
        default='medium'
    )
    due_date = models.DateField(null=True, blank=True)

    archived_by = models.ManyToManyField(
        Employee, 
        related_name='archived_tasks', 
        blank=True,
        verbose_name="Archived by users"
    )
    creator_workgroup = models.ForeignKey(
        'hr.Workgroup',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_tasks',
        verbose_name="Creator Workgroup",
        help_text="Workgroup of the creator at task creation time.",
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Task"
        verbose_name_plural = "Tasks"
        permissions = [
            ('view_all_personnel_tasks', 'Can view all personnel tasks'),
            ('approve_personnel_task', 'Can approve personnel tasks'),
        ]

    def __str__(self):
        display = self.task_number or self.title
        return f"{self.get_task_type_display()} - {display}"

    def save(self, *args, **kwargs):
        if not self.pk:
            self.status = self.get_initial_status()
        super().save(*args, **kwargs)

    def get_initial_status(self):
        if self.task_type == 'purchase_order':
            return 'not_yet_processed'
        if self.task_type in ('personnel_reallocation', 'personnel_contract_extension', 'personnel_recruitment'):
            return 'not_yet_processed'
        return 'seen'  # generic_text

    def get_status_display(self):
        """Human readable status depending on task type"""
        if self.task_type == 'generic_text':
            mapping = dict(GENERIC_STATUSES)
            return mapping.get(self.status, self.status)
        if self.task_type == 'personnel_recruitment':
            mapping = dict(RECRUITMENT_STATUSES)
            return mapping.get(self.status, self.status)
        if self.task_type in ('personnel_reallocation', 'personnel_contract_extension'):
            mapping = dict(PERSONNEL_STATUSES)
            return mapping.get(self.status, self.status)
        # Fallback for purchase orders and unknown types
        return self.status


# = Comments & attachments =
class TaskComment(BaseModel):
    ENTRY_CREATED = 'created'
    ENTRY_EDITED = 'edited'
    ENTRY_USER_MESSAGE = 'user_message'
    ENTRY_TYPE_CHOICES = [
        (ENTRY_CREATED, 'Created'),
        (ENTRY_EDITED, 'Edited'),
        (ENTRY_USER_MESSAGE, 'User message'),
    ]

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(Employee, on_delete=models.CASCADE)
    entry_type = models.CharField(
        max_length=20,
        choices=ENTRY_TYPE_CHOICES,
        default=ENTRY_USER_MESSAGE,
    )
    text = models.TextField(blank=True)

    class Meta:
        ordering = ['created_at']

    @property
    def author_username(self):
        if self.author and getattr(self.author, 'user', None):
            return self.author.user.username
        return 'unknown'

    @property
    def display_line(self):
        timestamp = self.created_at.strftime('%d.%m.%Y %H:%M')
        username = self.author_username
        if self.entry_type == self.ENTRY_CREATED:
            return f'{timestamp} {username} hat den Task erstellt'
        if self.entry_type == self.ENTRY_EDITED:
            return f'{timestamp} {username} hat den Task bearbeitet'
        return f'{timestamp} {username}: {self.text}'


class TaskAttachment(BaseModel):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='task_attachments/%Y/%m/%d/')
    uploaded_by = models.ForeignKey(Employee, on_delete=models.CASCADE)
    description = models.CharField(max_length=255, blank=True)


# = Concrete Tasks =
class PurchaseOrderTask(Task):
    """Bestellung"""
    supplier = models.CharField(max_length=200, verbose_name="Supplier", blank=True, default='')
    is_quote_order = models.BooleanField(
        default=False,
        verbose_name="Order with Quote",
        help_text="Quote-only variant: creator uploads a PDF instead of line items.",
    )
    quote_file = models.FileField(
        upload_to='purchase_orders/quotes/%Y/%m/%d/',
        blank=True,
        null=True,
        verbose_name="Quote",
    )
    wbs_element = models.ForeignKey(
        WBSElement, 
        on_delete=models.PROTECT, 
        null=True, 
        blank=True,
        verbose_name="WBS Element"
    )
    at_beleg_nummer = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="AT - Beleg Nummer"
    )
    kostenart = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="Kostenart",
    )
    referenzbeleg_nr = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name="Referenzbeleg-Nr",
    )
    einkaufsbeleg_nr = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name="Einkaufsbeleg-Nr",
    )
    v_kurztext = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name="V-Kurztext",
    )
    v_buchungsdatum = models.DateField(
        null=True,
        blank=True,
        verbose_name="V-Buchungsdatum",
    )
    v_belegdatum = models.DateField(
        null=True,
        blank=True,
        verbose_name="V-Belegdatum",
    )
    v_istkosten = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="V-Istkosten",
    )
    # Marked by import when administration data for this purchase order is complete.
    import_completed = models.BooleanField(
        default=False,
        verbose_name="Import completed",
        help_text=(
            "True when imported data confirms the administration process "
            "for this purchase order is complete."
        ),
    )

    class Meta:
        verbose_name = "Purchase Order Task"
        verbose_name_plural = "Purchase Order Tasks"
        permissions = [
            ("create_purchase_order", "Can create purchase orders"),
            ("view_all_purchase_orders", "Can view all purchase orders"),
            ("change_wbs_on_purchase_order", "Can change WBS element on purchase orders"),
            ("approve_purchase_order", "Can approve purchase orders"),
            ("create_personnel_task", "Can create personnel tasks"),
            ("create_general_request", "Can create general requests"),
        ]

    @property
    def total_price(self):
        return sum(item.total_price for item in self.items.all()) if self.items.exists() else 0

    @property
    def order_display_name(self):
        """Human-readable label for lists and page headers."""
        if self.is_quote_order and not (self.supplier or '').strip():
            return "Order with Quote"
        if (self.supplier or '').strip():
            return self.supplier
        return "Purchase Order"

    def __str__(self):
        return f"Purchase Order {self.order_display_name} - {self.created_at.date()}"


class PurchaseItem(BaseModel):
    """Bestellposition"""
    purchase_task = models.ForeignKey(
        PurchaseOrderTask, 
        on_delete=models.CASCADE, 
        related_name='items'
    )
    product_name = models.CharField(max_length=255, verbose_name="Product Name")
    product_description = models.TextField(blank=True, verbose_name="Product Description")
    link_to_product = models.URLField(blank=True, verbose_name="Link to Product")
    order_number = models.CharField(max_length=50, blank=True, verbose_name="Order Number")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Unit Price")
    quantity = models.PositiveIntegerField(default=1, verbose_name="Quantity")

    @property
    def total_price(self):
        return self.unit_price * self.quantity

    def __str__(self):
        return f"{self.product_name} × {self.quantity}"


class PersonnelReallocationTask(Task):
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name='reallocation_tasks')
    valid_from = models.DateField()
    valid_until = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "Personnel Reallocation Task"


class PersonnelContractExtensionTask(Task):
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name='extension_tasks')
    plan_position_number = models.CharField(max_length=50)
    valid_from = models.DateField()
    valid_until = models.DateField(null=True, blank=True)
    is_limited = models.BooleanField(default=True)
    limitation_reason = models.TextField(blank=True)

    class Meta:
        verbose_name = "Contract Extension Task"


class RecruitmentJob(BaseModel):
    """Configurable job type for personnel recruitment tasks."""
    name = models.CharField(max_length=200, unique=True, verbose_name="Job Name")
    is_active = models.BooleanField(default=True, verbose_name="Active")
    help_text = models.TextField(
        blank=True,
        default='',
        verbose_name="Help text",
        help_text="Shown in the recruitment form when this job is selected.",
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
    estimated_monthly_salary = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Estimated monthly salary (€)",
        help_text=(
            "Fixed theoretical monthly salary for 100% workload when no TV-L "
            "group/level is set. Mutually exclusive with TV-L defaults."
        ),
    )

    class Meta:
        verbose_name = "Recruitment Job"
        verbose_name_plural = "Recruitment Jobs"
        ordering = ['name']
        permissions = [
            ("manage_recruitment_job", "Can manage recruitment jobs"),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        from django.core.exceptions import ValidationError

        has_group = bool(self.pay_scale_group)
        has_level = self.experience_level is not None
        has_tvl = has_group or has_level
        has_estimate = self.estimated_monthly_salary is not None
        if has_group != has_level:
            raise ValidationError(
                'Please set both pay scale group and experience level, or leave both empty.'
            )
        if has_tvl and has_estimate:
            raise ValidationError(
                'Provide either TV-L defaults or an estimated monthly salary, not both.'
            )

    def get_estimated_monthly_salary(self):
        """Theoretical monthly salary at 100% workload from TV-L or fixed estimate."""
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
                return salary
        return self.estimated_monthly_salary


class RecruitmentJobFieldRule(BaseModel):
    """Per-job visibility and required rules for recruitment form fields."""
    job = models.ForeignKey(
        RecruitmentJob,
        on_delete=models.CASCADE,
        related_name='field_rules',
        verbose_name="Job",
    )
    field_key = models.CharField(max_length=50, verbose_name="Field Key")
    visibility_mode = models.CharField(
        max_length=20,
        choices=VisibilityMode.CHOICES,
        default=VisibilityMode.ALWAYS,
        verbose_name="Visibility",
    )
    visibility_duration_operator = models.CharField(
        max_length=5,
        choices=DurationOperator.CHOICES,
        blank=True,
        verbose_name="Visibility Duration Operator",
    )
    visibility_duration_months = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Visibility Duration (months)",
    )
    required_mode = models.CharField(
        max_length=20,
        choices=RequiredMode.CHOICES,
        default=RequiredMode.NEVER,
        verbose_name="Required",
    )
    required_duration_operator = models.CharField(
        max_length=5,
        choices=DurationOperator.CHOICES,
        blank=True,
        verbose_name="Required Duration Operator",
    )
    required_duration_months = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Required Duration (months)",
    )

    class Meta:
        verbose_name = "Recruitment Job Field Rule"
        verbose_name_plural = "Recruitment Job Field Rules"
        unique_together = ('job', 'field_key')
        ordering = ['field_key']

    def __str__(self):
        return f"{self.job} — {self.field_key}"


class LimitationReason(BaseModel):
    """Template texts for limitation reasons on recruitment and extension tasks."""
    title = models.CharField(max_length=200, verbose_name="Title")
    text = models.TextField(verbose_name="Limitation Reason Text")
    applies_to_all_jobs = models.BooleanField(
        default=False,
        verbose_name="Applies to All Jobs",
    )
    jobs = models.ManyToManyField(
        RecruitmentJob,
        blank=True,
        related_name='limitation_reasons',
        verbose_name="Associated Jobs",
    )
    is_active = models.BooleanField(default=True, verbose_name="Active")

    class Meta:
        verbose_name = "Limitation Reason"
        verbose_name_plural = "Limitation Reasons"
        ordering = ['title']
        permissions = [
            ("manage_limitation_reason", "Can manage limitation reasons"),
        ]

    def __str__(self):
        return self.title


class PersonnelRecruitmentTask(Task):
    """New hire recruitment workflow."""

    prefix = models.CharField(max_length=20, blank=True, verbose_name="Prefix / Title")
    first_name = models.CharField(max_length=100, verbose_name="First Name")
    last_name = models.CharField(max_length=100, verbose_name="Last Name")
    gender = models.CharField(
        max_length=1,
        choices=Gender.choices,
        default=Gender.NOT_SPECIFIED,
        verbose_name="Gender",
    )
    date_of_birth = models.DateField(verbose_name="Date of Birth")
    country_of_origin = models.CharField(max_length=100, verbose_name="Country of Origin")
    place_of_birth = models.CharField(max_length=100, verbose_name="Place of Birth")
    email_private = models.EmailField(verbose_name="Private Email")
    private_phone_number = models.CharField(
        max_length=30,
        blank=True,
        verbose_name="Private Phone",
    )
    street = models.CharField(max_length=100, verbose_name="Street")
    house_number = models.CharField(max_length=20, verbose_name="House Number")
    postal_code = models.CharField(max_length=10, verbose_name="Postal Code")
    city = models.CharField(max_length=100, verbose_name="City")
    country = models.CharField(max_length=100, default="Germany", verbose_name="Country")
    job = models.ForeignKey(
        RecruitmentJob,
        on_delete=models.PROTECT,
        related_name='recruitment_tasks',
        verbose_name="Job",
    )
    working_as = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Working As",
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
    monthly_salary = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Theoretical Monthly Salary for 100% Workload",
    )
    weekly_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Weekly Working Hours",
    )
    valid_from = models.DateField(verbose_name="Contract Start Date")
    valid_until = models.DateField(verbose_name="Contract End Date")
    limitation_reason = models.TextField(blank=True, verbose_name="Limitation Reason")
    application_file = models.FileField(
        upload_to='recruitment_tasks/application/',
        blank=True,
        null=True,
        verbose_name="Application",
    )
    cv_file = models.FileField(
        upload_to='recruitment_tasks/cv/',
        verbose_name="Curriculum Vitae",
    )
    latest_degree_certificate_file = models.FileField(
        upload_to='recruitment_tasks/degree_certificates/',
        verbose_name="Latest Degree Certificate",
    )
    created_employee = models.OneToOneField(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='recruitment_source_task',
        verbose_name="Created Employee",
    )

    class Meta:
        verbose_name = "Personnel Recruitment Task"

    def get_estimated_monthly_salary(self):
        """Theoretical monthly salary for 100% workload."""
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
                return salary
        if self.monthly_salary is not None:
            return self.monthly_salary
        if self.job_id:
            return self.job.get_estimated_monthly_salary()
        return None

    def get_workload_fraction(self):
        """Weekly hours / default full-time hours; missing weekly hours ⇒ 100%."""
        from decimal import Decimal

        from apps.core.models import GlobalSetting

        if self.weekly_hours is None:
            return Decimal('1')
        default_hours = GlobalSetting.get_default_weekly_hours()
        if not default_hours or default_hours <= 0:
            return Decimal('1')
        return (Decimal(self.weekly_hours) / Decimal(default_hours)).quantize(
            Decimal('0.0001')
        )

    def get_estimated_monthly_costs(self):
        """
        Pro-rata monthly costs:
        theoretical 100% salary × (weekly_hours / default_weekly_hours) × true-cost factor.
        Without weekly hours, full-time (100%) is assumed.
        """
        from decimal import Decimal

        from apps.core.models import GlobalSetting

        salary = self.get_estimated_monthly_salary()
        if salary is None:
            return None
        multiplicator = GlobalSetting.get_true_cost_multiplicator()
        fraction = self.get_workload_fraction()
        return (
            Decimal(salary) * fraction * Decimal(multiplicator)
        ).quantize(Decimal('0.01'))


class RecruitmentFundingAllocation(BaseModel):
    """PSP/cost center + workhours percentage for a recruitment task."""
    recruitment_task = models.ForeignKey(
        PersonnelRecruitmentTask,
        on_delete=models.CASCADE,
        related_name='funding_allocations',
        verbose_name="Recruitment Task",
    )
    wbs_element = models.ForeignKey(
        WBSElement,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="WBS Element",
    )
    cost_center = models.ForeignKey(
        'finances.CostCenter',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='recruitment_funding_allocations',
        verbose_name="Cost Center",
    )
    workhours_percentage = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        verbose_name="Percentage of Workhours",
    )
    plan_position_number = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Plan Position Number",
    )

    class Meta:
        verbose_name = "Recruitment Funding Allocation"
        verbose_name_plural = "Recruitment Funding Allocations"
        ordering = ['id']
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(wbs_element__isnull=False, cost_center__isnull=True)
                    | models.Q(wbs_element__isnull=True, cost_center__isnull=False)
                ),
                name='recruitment_funding_allocation_one_target',
            ),
        ]

    def __str__(self):
        from apps.finances.funding_sources import funding_target_display
        return f"{funding_target_display(self)} ({self.workhours_percentage}%)"

    @property
    def funding_target_label(self):
        from apps.finances.funding_sources import funding_target_display
        return funding_target_display(self)


class ReallocationFundingAllocation(BaseModel):
    """PSP/cost center + workhours percentage for a reallocation task."""
    reallocation_task = models.ForeignKey(
        PersonnelReallocationTask,
        on_delete=models.CASCADE,
        related_name='funding_allocations',
        verbose_name="Reallocation Task",
    )
    wbs_element = models.ForeignKey(
        WBSElement,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="WBS Element",
    )
    cost_center = models.ForeignKey(
        'finances.CostCenter',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='reallocation_funding_allocations',
        verbose_name="Cost Center",
    )
    workhours_percentage = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        verbose_name="Percentage of Workhours",
    )
    plan_position_number = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Plan Position Number",
    )
    notes = models.TextField(blank=True, verbose_name="Notes")

    class Meta:
        verbose_name = "Reallocation Funding Allocation"
        verbose_name_plural = "Reallocation Funding Allocations"
        ordering = ['id']
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(wbs_element__isnull=False, cost_center__isnull=True)
                    | models.Q(wbs_element__isnull=True, cost_center__isnull=False)
                ),
                name='reallocation_funding_allocation_one_target',
            ),
        ]

    def __str__(self):
        from apps.finances.funding_sources import funding_target_display
        return f"{funding_target_display(self)} ({self.workhours_percentage}%)"

    @property
    def funding_target_label(self):
        from apps.finances.funding_sources import funding_target_display
        return funding_target_display(self)


class TaskWorkflowCoordinator(BaseModel):
    """Coordinator assignment per workgroup and task type for workflow routing."""
    workgroup = models.ForeignKey(
        'hr.Workgroup',
        on_delete=models.CASCADE,
        related_name='task_workflow_coordinators',
        verbose_name="Workgroup",
    )
    task_type = models.CharField(max_length=50, choices=Task.TASK_TYPES, verbose_name="Task Type")
    coordinator = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name='task_workflow_coordinator_assignments',
        verbose_name="Coordinator",
    )

    class Meta:
        verbose_name = "Task Workflow Coordinator"
        verbose_name_plural = "Task Workflow Coordinators"
        ordering = ['workgroup__short_name', 'task_type', 'coordinator__last_name']
        constraints = [
            models.UniqueConstraint(
                fields=['workgroup', 'task_type', 'coordinator'],
                name='unique_task_workflow_coordinator',
            ),
        ]

    def __str__(self):
        return f"{self.workgroup} / {self.get_task_type_display()} → {self.coordinator}"


class GenericTextTask(Task):
    recipient = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    class Meta:
        verbose_name = "Generic Text Task"


class StandardPurchaseItem(BaseModel):
    """
    Standard / catalog items that can be quickly reused when creating new Purchase Orders.
    Supports optional product image stored as binary.
    Duplicate check is done on (supplier + order_number).
    """

    supplier = models.CharField(max_length=200)
    product_name = models.CharField(max_length=255)
    product_description = models.TextField(blank=True)
    link_to_product = models.URLField(blank=True)
    order_number = models.CharField(max_length=50, blank=True)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    # Image stored in DB (optional)
    image = models.BinaryField(null=True, blank=True)
    image_filename = models.CharField(max_length=255, blank=True)
    image_content_type = models.CharField(max_length=100, blank=True)

    # Small thumbnail for selection lists (generated on upload)
    thumbnail = models.BinaryField(null=True, blank=True)

    created_by = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name='created_standard_items'
    )

    class Meta:
        ordering = ['supplier', 'product_name']
        verbose_name = "Standard Purchase Item"
        verbose_name_plural = "Standard Purchase Items"
        permissions = [
            ("view_standard_order", "Can view standard orders"),
            ("manage_standard_order", "Can manage standard orders"),
        ]

    def __str__(self):
        return f"{self.supplier} - {self.product_name} ({self.order_number or 'no order #'})"

    @classmethod
    def already_exists(cls, supplier: str, order_number: str) -> bool:
        """Used to decide whether to show the 'Mark as Standard' checkbox."""
        if not order_number:
            return False
        return cls.objects.filter(
            supplier__iexact=supplier.strip(),
            order_number__iexact=order_number.strip()
        ).exists()

