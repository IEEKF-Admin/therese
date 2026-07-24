"""Business logic: link purchase items to chemicals / inventory rows."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.chemicals.lookup import looks_like_cas, normalize_cas, upsert_chemical_from_cas
from apps.chemicals.models import ChemicalItem


def resolve_orderer_and_workgroup(purchase_item):
    """Return (employee, workgroup) for the PO creator."""
    task = getattr(purchase_item, 'purchase_task', None)
    if task is None:
        return None, None
    creator = getattr(task, 'creator', None)
    wg = getattr(task, 'creator_workgroup', None)
    if wg is None and creator is not None:
        wg = creator.workgroups.order_by('short_name').first()
    return creator, wg


@transaction.atomic
def sync_purchase_item_chemical(purchase_item, *, force_refresh: bool = False) -> ChemicalItem | None:
    """
    After a purchase line is saved: if CAS is hazardous, ensure Chemical + ChemicalItem.

    - Creates/updates Chemical master from free PubChem data
    - Sets purchase_item.is_dangerous
    - Creates draft ChemicalItem once per purchase line when dangerous
    - Does nothing further if item already linked and still dangerous
    """
    cas = normalize_cas(getattr(purchase_item, 'cas_number', None) or '')
    if not cas:
        if getattr(purchase_item, 'is_dangerous', False):
            purchase_item.is_dangerous = False
            purchase_item.save(update_fields=['is_dangerous', 'updated_at'])
        return getattr(purchase_item, 'chemical_item', None)

    try:
        chemical = upsert_chemical_from_cas(cas, force_refresh=force_refresh)
    except Exception:
        # Keep CAS, mark not dangerous if lookup fails hard
        purchase_item.is_dangerous = False
        purchase_item.save(update_fields=['is_dangerous', 'updated_at'])
        return None

    is_dangerous = bool(chemical.is_hazardous)
    if purchase_item.is_dangerous != is_dangerous:
        purchase_item.is_dangerous = is_dangerous
        purchase_item.save(update_fields=['is_dangerous', 'updated_at'])

    if not is_dangerous:
        return None

    existing = ChemicalItem.objects.filter(purchase_item=purchase_item).first()
    if existing:
        # Keep master link / product name fresh
        updates = []
        if existing.chemical_id != chemical.pk:
            existing.chemical = chemical
            updates.append('chemical')
        name = (purchase_item.product_name or '').strip()
        if name and existing.product_name != name:
            existing.product_name = name
            updates.append('product_name')
        if updates:
            updates.append('updated_at')
            existing.save(update_fields=updates)
        return existing

    orderer, workgroup = resolve_orderer_and_workgroup(purchase_item)
    ordered_at = None
    task = purchase_item.purchase_task
    if task and getattr(task, 'created_at', None):
        ordered_at = task.created_at.date()

    item = ChemicalItem.objects.create(
        chemical=chemical,
        purchase_item=purchase_item,
        ordered_by=orderer,
        workgroup=workgroup,
        ordered_at=ordered_at or timezone.now().date(),
        status=ChemicalItem.Status.DRAFT,
        product_name=purchase_item.product_name or chemical.name or cas,
    )
    return item


def _activate_chemical_for_purchase_item(purchase_item):
    """Activate linked ChemicalItem on first (partial) delivery."""
    ci = ChemicalItem.objects.filter(purchase_item=purchase_item).first()
    if ci and ci.status != ChemicalItem.Status.ARCHIVED:
        if ci.status != ChemicalItem.Status.ACTIVE or not ci.delivered_at:
            ci.mark_active_delivered()


def refresh_purchase_order_delivery_status(task):
    """
    Set PO status to delivered when all lines are fully delivered;
    if status was delivered and any line is incomplete, reopen to sent_to_administration.
    """
    from apps.tasks.models import PurchaseItem, PurchaseOrderTask

    if not isinstance(task, PurchaseOrderTask):
        task = PurchaseOrderTask.objects.filter(pk=task.pk).first()
    if not task:
        return
    remaining = PurchaseItem.objects.filter(
        purchase_task=task, delivered=False,
    ).exists()
    if not remaining:
        if task.status != 'delivered':
            task.status = 'delivered'
            task.save(update_fields=['status', 'last_status_change', 'updated_at'])
    elif task.status == 'delivered':
        task.status = 'sent_to_administration'
        task.save(update_fields=['status', 'last_status_change', 'updated_at'])


def apply_delivered_number(purchase_item, delivered_number: int, *, user=None):
    """
    Set cumulative delivered_number on a purchase line (partial delivery).

    - 0 ≤ delivered_number ≤ quantity
    - delivered=True when delivered_number == quantity
    - ChemicalItem activates when delivered_number > 0
    - Lowering is allowed (may clear full-delivery flag)
    """
    from apps.tasks.models import PurchaseItem

    if not isinstance(purchase_item, PurchaseItem):
        purchase_item = PurchaseItem.objects.get(pk=purchase_item)
    try:
        n = int(delivered_number)
    except (TypeError, ValueError) as exc:
        raise ValueError('Delivered number must be an integer.') from exc
    qty = int(purchase_item.quantity or 0)
    if n < 0 or n > qty:
        raise ValueError(f'Delivered number must be between 0 and {qty}.')

    purchase_item.delivered_number = n
    if n >= qty and qty > 0:
        purchase_item.delivered = True
        if not purchase_item.delivered_at:
            purchase_item.delivered_at = timezone.now()
    else:
        purchase_item.delivered = False
        if n == 0:
            purchase_item.delivered_at = None
        elif not purchase_item.delivered_at:
            purchase_item.delivered_at = timezone.now()

    purchase_item.save(update_fields=[
        'delivered_number', 'delivered', 'delivered_at', 'updated_at',
    ])
    if n > 0:
        _activate_chemical_for_purchase_item(purchase_item)
    refresh_purchase_order_delivery_status(purchase_item.purchase_task)
    return purchase_item


def mark_purchase_items_delivered(purchase_items, *, user=None):
    """
    Mark given PurchaseItems as fully delivered (delivered_number = quantity).

    Activates linked ChemicalItems when present. When all lines of a PO
    are delivered, set the purchase order status to delivered automatically.
    """
    from apps.tasks.models import PurchaseItem

    items = list(purchase_items)
    task_ids = set()
    for item in items:
        apply_delivered_number(item, int(item.quantity or 0), user=user)
        task_ids.add(item.purchase_task_id)
    return len(items)


def cas_live_check(cas_raw: str) -> dict:
    """JSON-friendly live response for purchase forms."""
    cas = normalize_cas(cas_raw)
    if not cas:
        return {
            'valid_cas': False,
            'cas_number': '',
            'is_dangerous': False,
            'name': '',
            'message': 'Not a CAS number',
        }
    try:
        chemical = upsert_chemical_from_cas(cas)
    except Exception as exc:
        return {
            'valid_cas': True,
            'cas_number': cas,
            'is_dangerous': False,
            'name': '',
            'message': f'Lookup failed: {exc}',
        }
    return {
        'valid_cas': True,
        'cas_number': chemical.cas_number,
        'is_dangerous': chemical.is_hazardous,
        'name': chemical.name,
        'signal_word': chemical.ghs_signal_word,
        'hazard_codes': chemical.ghs_hazard_codes,
        'message': (
            'Hazardous substance (Gefahrstoff)'
            if chemical.is_hazardous
            else 'Not classified as hazardous under current threshold'
        ),
    }


def ensure_cas_field_value(raw: str) -> str:
    if looks_like_cas(raw):
        return normalize_cas(raw) or ''
    return (raw or '').strip()


def apply_chemical_item_fields_from_purchase_form(purchase_item, data: dict) -> ChemicalItem | None:
    """
    After a purchase line is saved: if a ChemicalItem exists (hazardous CAS),
    apply inventory fields collected on the PO form (chem_* extras).
    """
    if not purchase_item or not purchase_item.pk:
        return None
    ci = ChemicalItem.objects.filter(purchase_item=purchase_item).select_related('chemical').first()
    if not ci:
        # Ensure sync ran (signal may have been skipped on import edge cases)
        ci = sync_purchase_item_chemical(purchase_item)
    if not ci:
        return None

    updates = []
    qty = (data.get('quantity_range') or '').strip()
    if qty and qty != ci.quantity_range:
        ci.quantity_range = qty
        updates.append('quantity_range')
    work_area = data.get('work_area')
    work_area_id = getattr(work_area, 'pk', work_area) if work_area else None
    if work_area_id and work_area_id != ci.work_area_id:
        ci.work_area_id = work_area_id
        updates.append('work_area')
    room = data.get('storage_room')
    room_id = getattr(room, 'pk', room) if room else None
    if room_id and room_id != ci.storage_room_id:
        ci.storage_room_id = room_id
        updates.append('storage_room')
    storage = data.get('storage_item')
    storage_id = getattr(storage, 'pk', storage) if storage else None
    if storage_id and storage_id != ci.storage_item_id:
        ci.storage_item_id = storage_id
        updates.append('storage_item')
    notes = (data.get('notes') or '').strip()
    if notes and notes != (ci.notes or ''):
        ci.notes = notes
        updates.append('notes')
    if updates:
        updates.append('updated_at')
        ci.save(update_fields=updates)
    return ci


def apply_chemical_fields_from_item_formset(formset) -> int:
    """Apply chem_* extras from a PurchaseItem formset. Returns number of items updated."""
    count = 0
    for form in formset.forms:
        if not getattr(form, 'cleaned_data', None):
            continue
        if form.cleaned_data.get('DELETE'):
            continue
        instance = getattr(form, 'instance', None)
        if not instance or not instance.pk:
            continue
        if not (form.cleaned_data.get('cas_number') or getattr(instance, 'cas_number', '')):
            continue
        data = form.chemical_item_data() if hasattr(form, 'chemical_item_data') else {}
        if apply_chemical_item_fields_from_purchase_form(instance, data):
            count += 1
    return count
