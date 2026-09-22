"""Item codes, issuance, and Global Settings type rows."""

from __future__ import annotations

import re

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

PREFIX_RE = re.compile(r'^[A-Za-z0-9]{1,10}$')


def normalize_prefix(value: str) -> str:
    return (value or '').strip().upper()


def allocate_item_code(item_type) -> str:
    from apps.inventory.models import InventoryItemType

    with transaction.atomic():
        locked = InventoryItemType.objects.select_for_update().get(pk=item_type.pk)
        number = locked.next_number or 1
        locked.next_number = number + 1
        locked.save(update_fields=['next_number', 'updated_at'])
        return f'{locked.prefix}-{number:04d}'


def apply_holder_change(item, new_holder, *, actor=None):
    from apps.inventory.models import InventoryIssuance

    open_iss = item.issuances.filter(returned_at__isnull=True).order_by('-issued_at', '-pk').first()
    current_id = open_iss.employee_id if open_iss else None
    new_id = new_holder.pk if new_holder else None
    now = timezone.now()

    if current_id == new_id:
        if item.current_holder_id != new_id:
            item.current_holder = new_holder
            item.save(update_fields=['current_holder', 'updated_at'])
        return

    if open_iss:
        open_iss.returned_at = now
        open_iss.returned_by = actor
        open_iss.save(update_fields=['returned_at', 'returned_by', 'updated_at'])

    if new_holder:
        InventoryIssuance.objects.create(
            item=item,
            employee=new_holder,
            issued_at=now,
            issued_by=actor,
        )

    item.current_holder = new_holder
    item.save(update_fields=['current_holder', 'updated_at'])


@transaction.atomic
def save_inventory_types_from_post(post):
    if post.get('inv_types_present') != '1':
        return
    from apps.inventory.models import InventoryItemType

    keep_ids = set()
    index = 0
    seen_names = set()
    seen_prefixes = set()
    while True:
        prefix_key = f'inv_type_{index}_'
        if f'{prefix_key}name' not in post and f'{prefix_key}id' not in post:
            break
        index += 1
        if post.get(f'{prefix_key}delete') in ('1', 'on', 'true'):
            pk = post.get(f'{prefix_key}id')
            if pk:
                row = InventoryItemType.objects.filter(pk=pk).first()
                if row:
                    try:
                        row.delete()
                    except ProtectedError:
                        keep_ids.add(row.pk)
            continue
        name = (post.get(f'{prefix_key}name') or '').strip()
        prefix = normalize_prefix(post.get(f'{prefix_key}prefix') or '')
        if not name or not PREFIX_RE.match(prefix):
            pk = post.get(f'{prefix_key}id')
            if pk and str(pk).isdigit():
                keep_ids.add(int(pk))
            continue
        if name.lower() in seen_names or prefix in seen_prefixes:
            continue
        seen_names.add(name.lower())
        seen_prefixes.add(prefix)
        pk = post.get(f'{prefix_key}id')
        row = InventoryItemType.objects.filter(pk=pk).first() if pk else None
        if row:
            if row.name != name or row.prefix != prefix:
                row.name = name
                row.prefix = prefix
                try:
                    row.save(update_fields=['name', 'prefix', 'updated_at'])
                except IntegrityError:
                    keep_ids.add(row.pk)
                    continue
        else:
            try:
                row = InventoryItemType.objects.create(name=name, prefix=prefix)
            except IntegrityError:
                row = InventoryItemType.objects.filter(prefix=prefix).first()
                if row is None:
                    continue
        keep_ids.add(row.pk)

    for leftover in InventoryItemType.objects.exclude(pk__in=keep_ids):
        try:
            leftover.delete()
        except ProtectedError:
            pass
