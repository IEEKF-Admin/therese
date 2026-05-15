"""
apps/tasks/models.py

Project: THERESE – Transparent HR Resource System Enhanced
Robust polymorphic Task System
"""

from django.db import models
from apps.core.models import BaseModel
from apps.hr.models import Employee
from apps.finances.models import WBSElement


# ====================== STATUS DEFINITIONS ======================
PURCHASE_STATUSES = [
    ('not_yet_processed', 'Not yet processed'),
    ('in_coordination', 'In coordination'),
    ('coordination_completed', 'Coordination completed'),
    ('sent_to_administration', 'Sent to administration'),
    ('ordered_from_supplier', 'Ordered from supplier'),
    ('received_in_warehouse', 'Received in warehouse'),
    ('delivered', 'Delivered'),
    ('completed', 'Completed'),
]

PERSONNEL_STATUSES = [
    ('noch nicht bearbeitet', 'Noch nicht bearbeitet'),
    ('an die Personalabteilung gesendet', 'An Personalabteilung gesendet'),
    ('Bearbeitung durch Personalabteilung', 'Bearbeitung durch Personalabteilung'),
    ('Personalrat', 'Personalrat'),
    ('abgeschlossen', 'Abgeschlossen'),
]

GENERIC_STATUSES = [
    ('noch nicht bearbeitet', 'Noch nicht bearbeitet'),
    ('in Bearbeitung', 'In Bearbeitung'),
    ('abgeschlossen', 'Abgeschlossen'),
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
    title = models.CharField(max_length=255, verbose_name="Title")

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

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Task"
        verbose_name_plural = "Tasks"

    def __str__(self):
        return f"{self.get_task_type_display()} - {self.title}"

    def save(self, *args, **kwargs):
        if not self.pk:
            self.status = self.get_initial_status()
        super().save(*args, **kwargs)

    def get_initial_status(self):
        if self.task_type == 'purchase_order':
            return 'not_yet_processed'
        return 'noch nicht bearbeitet'


# ====================== Kommentare & Anhänge ======================
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


# ====================== Concrete Tasks ======================
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
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Unit Price")
    quantity = models.DecimalField(max_digits=8, decimal_places=2, default=1, verbose_name="Quantity")

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
    is_limited = models.BooleanField(default=True)
    limitation_reason = models.TextField(blank=True)

    class Meta:
        verbose_name = "Contract Extension Task"


class GenericTextTask(Task):
    recipient = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')

    class Meta:
        verbose_name = "Generic Text Task"