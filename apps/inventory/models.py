"""Institute inventory items and issuance history."""

from django.db import models

from apps.core.models import BaseModel


class InventoryItemType(BaseModel):
    name = models.CharField(max_length=120, unique=True, verbose_name='Name')
    prefix = models.CharField(
        max_length=10,
        unique=True,
        verbose_name='ID prefix',
        help_text='Used for auto IDs, e.g. SM → SM-0001.',
    )
    next_number = models.PositiveIntegerField(default=1, verbose_name='Next sequence number')

    class Meta:
        verbose_name = 'Inventory item type'
        verbose_name_plural = 'Inventory item types'
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.prefix})'


class InventoryItem(BaseModel):
    item_type = models.ForeignKey(
        InventoryItemType,
        on_delete=models.PROTECT,
        related_name='items',
        verbose_name='Item type',
    )
    code = models.CharField(
        max_length=32,
        unique=True,
        db_index=True,
        verbose_name='ID',
    )
    name = models.CharField(max_length=200, verbose_name='Name')
    purchase_date = models.DateField(null=True, blank=True, verbose_name='Purchase date')
    purchase_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Purchase price',
    )
    description = models.TextField(blank=True, verbose_name='Description')
    current_holder = models.ForeignKey(
        'hr.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inventory_items',
        verbose_name='Issued to',
    )

    class Meta:
        verbose_name = 'Inventory item'
        verbose_name_plural = 'Inventory items'
        ordering = ['code']
        permissions = [
            ('view_own_inventory_items', 'Can view inventory items issued to self'),
            ('view_all_inventory_items', 'Can view all inventory items'),
            ('manage_inventory_items', 'Can manage inventory items'),
        ]

    def __str__(self):
        return f'{self.code} — {self.name}'


class InventoryIssuance(BaseModel):
    item = models.ForeignKey(
        InventoryItem,
        on_delete=models.CASCADE,
        related_name='issuances',
        verbose_name='Item',
    )
    employee = models.ForeignKey(
        'hr.Employee',
        on_delete=models.PROTECT,
        related_name='inventory_issuances',
        verbose_name='Employee',
    )
    issued_at = models.DateTimeField(verbose_name='Issued at')
    issued_by = models.ForeignKey(
        'hr.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inventory_issuances_recorded',
        verbose_name='Issued by',
    )
    returned_at = models.DateTimeField(null=True, blank=True, verbose_name='Returned at')
    returned_by = models.ForeignKey(
        'hr.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inventory_returns_recorded',
        verbose_name='Returned by',
    )

    class Meta:
        verbose_name = 'Inventory issuance'
        verbose_name_plural = 'Inventory issuances'
        ordering = ['-issued_at', '-pk']

    def __str__(self):
        return f'{self.item_id} → {self.employee_id}'
