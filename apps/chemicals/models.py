"""
Chemicals catalogue (CAS masters) and Chemical Items (concrete inventory rows).
"""

from __future__ import annotations

import calendar
import uuid
from datetime import date, datetime

from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel


def add_calendar_months(start: date, months: int) -> date:
    """Add whole calendar months; clamp day to last day of target month."""
    if months < 0:
        raise ValueError('months must be >= 0')
    year = start.year + (start.month - 1 + months) // 12
    month = (start.month - 1 + months) % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


class Chemical(BaseModel):
    """
    Master data for a chemical substance identified primarily by CAS number.

    Populated from free public sources (PubChem GHS/properties) where possible.
    """

    cas_number = models.CharField(
        max_length=32,
        unique=True,
        db_index=True,
        verbose_name='CAS number',
    )
    name = models.CharField(max_length=500, blank=True, verbose_name='Name')
    iupac_name = models.CharField(max_length=500, blank=True, verbose_name='IUPAC name')
    molecular_formula = models.CharField(max_length=200, blank=True, verbose_name='Molecular formula')
    pubchem_cid = models.PositiveIntegerField(null=True, blank=True, verbose_name='PubChem CID')

    # GHS / hazard summary from free sources
    ghs_signal_word = models.CharField(
        max_length=32,
        blank=True,
        verbose_name='GHS signal word',
        help_text='e.g. Danger, Warning (from PubChem / GHS).',
    )
    ghs_hazard_codes = models.TextField(
        blank=True,
        verbose_name='GHS hazard codes',
        help_text='Comma-separated H-codes, e.g. H225, H319.',
    )
    ghs_pictograms = models.TextField(
        blank=True,
        verbose_name='GHS pictograms',
        help_text='Comma-separated pictogram codes or labels.',
    )
    is_hazardous = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name='Classified as hazardous (Gefahrstoff)',
        help_text='Set according to the institute hazard threshold in Global Settings.',
    )
    hazard_classification_notes = models.TextField(blank=True, verbose_name='Classification notes')
    shelf_life_months = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Shelf life (months)',
        help_text=(
            'Typical shelf life in months. Used to auto-calculate MHD on chemical items '
            '(from delivery date). Leave empty if unknown.'
        ),
    )

    safety_data_sheet = models.FileField(
        upload_to='chemicals/sds/%Y/%m/',
        blank=True,
        null=True,
        max_length=255,
        verbose_name='Safety data sheet (local copy)',
    )
    sds_source_url = models.URLField(blank=True, verbose_name='SDS source URL')

    pubchem_raw = models.JSONField(default=dict, blank=True, verbose_name='PubChem raw data')
    last_lookup_at = models.DateTimeField(null=True, blank=True, verbose_name='Last API lookup')
    lookup_error = models.TextField(blank=True, verbose_name='Last lookup error')

    class Meta:
        verbose_name = 'Chemical'
        verbose_name_plural = 'Chemicals'
        ordering = ['cas_number']
        permissions = [
            ('view_chemical_workgroup', 'Can view chemicals linked to own workgroup items'),
            ('view_all_chemicals', 'Can view all chemicals institute-wide'),
            ('manage_chemical_workgroup', 'Can manage chemicals linked to own workgroup items'),
            ('manage_all_chemicals', 'Can manage all chemicals institute-wide'),
        ]

    def __str__(self):
        label = self.name or self.cas_number
        return f'{self.cas_number} — {label}' if self.name else self.cas_number

    def missing_info_fields(self) -> list[str]:
        missing = []
        if not (self.name or '').strip():
            missing.append('name')
        if not self.is_hazardous and not (self.ghs_signal_word or self.ghs_hazard_codes):
            # Non-hazardous may still be incomplete if never looked up
            if self.last_lookup_at is None:
                missing.append('classification_lookup')
        if self.is_hazardous:
            if not (self.ghs_hazard_codes or self.ghs_signal_word):
                missing.append('hazard_classification')
            if not self.safety_data_sheet and not self.sds_source_url:
                missing.append('safety_data_sheet')
        return missing

    @property
    def is_incomplete(self) -> bool:
        return bool(self.missing_info_fields())


class ChemicalItem(BaseModel):
    """
    Concrete inventory quantity of a chemical present at the institute.

    One row per purchase line (or manual entry). Multiple items may share one Chemical (CAS).
    """

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft (ordered, not delivered)'
        ACTIVE = 'active', 'Active (delivered / in inventory)'
        ARCHIVED = 'archived', 'Archived'

    class QuantityRange(models.TextChoices):
        LT_1 = 'lt_1', '< 1 kg / L'
        R_1_10 = '1_10', '1–10 kg / L'
        R_10_100 = '10_100', '10–100 kg / L'
        GT_100 = 'gt_100', '> 100 kg / L'
        UNKNOWN = 'unknown', 'Unknown / not set'

    public_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name='Item ID',
    )
    chemical = models.ForeignKey(
        Chemical,
        on_delete=models.PROTECT,
        related_name='items',
        verbose_name='Chemical',
    )
    purchase_item = models.OneToOneField(
        'tasks.PurchaseItem',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='chemical_item',
        verbose_name='Purchase order item',
    )
    ordered_by = models.ForeignKey(
        'hr.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ordered_chemical_items',
        verbose_name='Ordered by',
    )
    workgroup = models.ForeignKey(
        'hr.Workgroup',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='chemical_items',
        verbose_name='Work group',
    )
    ordered_at = models.DateField(
        null=True,
        blank=True,
        verbose_name='Order date',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
        verbose_name='Status',
    )
    # Free-text display name may differ from master (e.g. kit trade name)
    product_name = models.CharField(max_length=255, blank=True, verbose_name='Product / trade name')
    quantity_range = models.CharField(
        max_length=20,
        choices=QuantityRange.choices,
        default=QuantityRange.UNKNOWN,
        verbose_name='Quantity range in use',
    )
    work_area = models.ForeignKey(
        'hr.Room',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='chemical_work_area_items',
        verbose_name='Work area / exposure area',
        help_text=(
            'Room where employees may be exposed (GefStoffV §6). '
            'Only rooms marked as Chemical work areas are selectable.'
        ),
        limit_choices_to={'chemical': True},
    )
    storage_room = models.ForeignKey(
        'hr.Room',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='chemical_storage_items',
        verbose_name='Storage room',
        help_text='Only rooms that have a storage location (cabinet/shelf/…) are selectable.',
    )
    storage_item = models.ForeignKey(
        'hr.RoomStorageItem',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='chemical_items',
        verbose_name='Storage location (cabinet / shelf / …)',
    )
    notes = models.TextField(blank=True, verbose_name='Notes')
    delivered_at = models.DateTimeField(null=True, blank=True, verbose_name='Delivered at')
    mhd = models.DateField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name='MHD (best before)',
        help_text=(
            'Mindesthaltbarkeitsdatum. Auto-filled from delivery date + chemical shelf life '
            'when empty; can be overridden manually.'
        ),
    )

    class Meta:
        verbose_name = 'Chemical item'
        verbose_name_plural = 'Chemical items'
        ordering = ['-created_at']
        permissions = [
            (
                'view_own_chemical_items',
                'Can view own chemical items (as orderer)',
            ),
            (
                'view_workgroup_chemical_items',
                'Can view chemical items of own workgroups',
            ),
            (
                'view_all_chemical_items',
                'Can view all chemical items institute-wide',
            ),
            (
                'manage_own_chemical_items',
                'Can manage own chemical items (as orderer)',
            ),
            (
                'manage_workgroup_chemical_items',
                'Can manage chemical items of own workgroups',
            ),
            (
                'manage_all_chemical_items',
                'Can manage all chemical items institute-wide',
            ),
        ]

    def __str__(self):
        return f'{self.public_id.hex[:8]} — {self.chemical.cas_number}'

    def _reference_date_for_mhd(self) -> date | None:
        """Prefer delivery date; fall back to order date."""
        if self.delivered_at:
            if isinstance(self.delivered_at, datetime):
                return timezone.localtime(self.delivered_at).date()
            return self.delivered_at
        if self.ordered_at:
            return self.ordered_at
        return None

    def compute_mhd_from_shelf_life(self) -> date | None:
        """
        MHD = reference date + Chemical.shelf_life_months.

        Returns None if shelf life or a reference date is missing.
        """
        if not self.chemical_id:
            return None
        months = self.chemical.shelf_life_months
        if not months:
            return None
        ref = self._reference_date_for_mhd()
        if not ref:
            return None
        return add_calendar_months(ref, int(months))

    def apply_auto_mhd(self, *, force: bool = False) -> bool:
        """
        Set mhd from shelf life when empty (or always if force=True).

        Returns True if mhd was changed.
        """
        computed = self.compute_mhd_from_shelf_life()
        if computed is None:
            return False
        if not force and self.mhd:
            return False
        if self.mhd == computed:
            return False
        self.mhd = computed
        return True

    def missing_info_fields(self) -> list[str]:
        missing = []
        if self.quantity_range in ('', ChemicalItem.QuantityRange.UNKNOWN):
            missing.append('quantity_range')
        if not self.work_area_id:
            missing.append('work_area')
        if not self.storage_room_id:
            missing.append('storage_room')
        if self.chemical_id and self.chemical.is_incomplete:
            missing.append('chemical_master_incomplete')
        return missing

    @property
    def is_incomplete(self) -> bool:
        return bool(self.missing_info_fields())

    @property
    def is_mhd_expired(self) -> bool:
        return bool(self.mhd and self.mhd < timezone.localdate())

    def mark_active_delivered(self):
        self.status = self.Status.ACTIVE
        if not self.delivered_at:
            self.delivered_at = timezone.now()
        self.apply_auto_mhd(force=False)
        self.save(update_fields=['status', 'delivered_at', 'mhd', 'updated_at'])
