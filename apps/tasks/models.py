"""
apps/tasks/models.py

Project: THERESE – Transparent HR Resource System Enhanced
Robust polymorphic Task System
"""

from django.db import models
from apps.core.models import BaseModel
from apps.hr.models import Employee
from apps.finances.models import WBSElement


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
        ('generic_text', 'General Request'),
    ]

    task_type = models.CharField(max_length=50, choices=TASK_TYPES, verbose_name="Task Type")
    title = models.CharField(max_length=255, verbose_name="Title", blank=True)
    task_number = models.CharField(
        max_length=20, 
        unique=True, 
        blank=True, 
        null=True,           # Wichtig fÃ¼r bestehende DatensÃ¤tze bei der Migration
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
    comment = models.TextField(blank=True)

    archived_by = models.ManyToManyField(
        Employee, 
        related_name='archived_tasks', 
        blank=True,
        verbose_name="Archived by users"
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Task"
        verbose_name_plural = "Tasks"

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
        if self.task_type in ('personnel_reallocation', 'personnel_contract_extension'):
            return 'not_yet_processed'
        return 'seen'  # generic_text

    def get_status_display(self):
        """Human readable status depending on task type"""
        if self.task_type == 'generic_text':
            mapping = dict(GENERIC_STATUSES)
            return mapping.get(self.status, self.status)
        if self.task_type in ('personnel_reallocation', 'personnel_contract_extension'):
            mapping = dict(PERSONNEL_STATUSES)
            return mapping.get(self.status, self.status)
        # Fallback for purchase orders and unknown types
        return self.status


# = Kommentare & AnhÃ¤nge =
class TaskComment(BaseModel):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(Employee, on_delete=models.CASCADE)
    text = models.TextField()

    class Meta:
        ordering = ['-created_at']


class TaskAttachment(BaseModel):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='task_attachments/%Y/%m/%d/')
    uploaded_by = models.ForeignKey(Employee, on_delete=models.CASCADE)
    description = models.CharField(max_length=255, blank=True)


# = Concrete Tasks =
class PurchaseOrderTask(Task):
    """Bestellung"""
    supplier = models.CharField(max_length=200, verbose_name="Supplier")
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

    class Meta:
        verbose_name = "Purchase Order Task"
        verbose_name_plural = "Purchase Order Tasks"

    @property
    def total_price(self):
        return sum(item.total_price for item in self.items.all()) if self.items.exists() else 0

    def __str__(self):
        return f"Purchase Order {self.supplier} - {self.created_at.date()}"


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
    target_wbs = models.ForeignKey(WBSElement, on_delete=models.PROTECT, related_name='+')
    valid_from = models.DateField()
    valid_until = models.DateField(null=True, blank=True)
    plan_position_number = models.CharField(max_length=50)

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


class GenericTextTask(Task):
    recipient = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    class Meta:
        verbose_name = "Generic Text Task"


class StandardPurchaseItem(BaseModel):
    """
    Standard / catalog items that can be quickly reused when creating new Purchase Orders.
    Supports optional product image stored as binary (like documents).
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

