"""Current-funding snapshot and highlight helpers for contract extensions."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from apps.finances.funding_sources import funding_source_value_for_instance


def _dec_str(value):
    if value in (None, ''):
        return ''
    try:
        return format(Decimal(str(value)), 'f')
    except (InvalidOperation, TypeError, ValueError):
        return str(value).strip()


def serialize_open_funding(employee):
    """Employee FAs open today, as snapshot/prefill dicts."""
    if employee is None:
        return []
    rows = []
    for fa in employee.get_open_funding_allocations_as_of():
        rows.append({
            'source_id': fa.pk,
            'wbs_element_id': fa.wbs_element_id,
            'cost_center_id': fa.cost_center_id,
            'funding_source': funding_source_value_for_instance(fa),
            'funding_target_label': fa.funding_target_label,
            'workhours_percentage': _dec_str(fa.workhours_percentage),
            'plan_position_number': (fa.plan_position_number or '').strip(),
            'job_number': (fa.job_number or '').strip(),
            'notes': (fa.comments or '').strip(),
        })
    return rows


def formset_initial_from_snapshot(snapshot):
    initial = []
    for item in snapshot or []:
        initial.append({
            'funding_source': item.get('funding_source') or '',
            'workhours_percentage': item.get('workhours_percentage') or '',
            'plan_position_number': item.get('plan_position_number') or '',
            'job_number': item.get('job_number') or '',
            'notes': item.get('notes') or '',
            'source_allocation_id': item.get('source_id') or None,
        })
    return initial


def _norm_text(value):
    return ('' if value is None else str(value)).strip()


def _source_key(value):
    if value in (None, ''):
        return None
    return str(value)


def allocation_as_values(allocation):
    return {
        'funding_source': funding_source_value_for_instance(allocation),
        'workhours_percentage': _dec_str(allocation.workhours_percentage),
        'plan_position_number': _norm_text(allocation.plan_position_number),
        'job_number': _norm_text(allocation.job_number),
        'notes': _norm_text(allocation.notes),
        'funding_target_label': allocation.funding_target_label,
        'source_id': allocation.source_allocation_id,
    }


COMPARE_FIELDS = (
    'funding_source',
    'workhours_percentage',
    'plan_position_number',
    'job_number',
    'notes',
)


def _changed_fields(current, original):
    changed = []
    for name in COMPARE_FIELDS:
        if name == 'workhours_percentage':
            left, right = _dec_str(current.get(name)), _dec_str(original.get(name))
        else:
            left, right = _norm_text(current.get(name)), _norm_text(original.get(name))
        if left != right:
            changed.append(name)
    return changed


def diff_extension_funding(task):
    """Compare saved extension funding rows to the creation snapshot."""
    snapshot = list(getattr(task, 'original_funding_snapshot', None) or [])
    if not snapshot:
        rows = []
        for allocation in task.funding_allocations.all():
            rows.append({
                'allocation': allocation,
                'status': 'unchanged',
                'changed_fields': [],
                'values': allocation_as_values(allocation),
            })
        return rows, []
    by_source = {}
    for item in snapshot:
        key = _source_key(item.get('source_id'))
        if key:
            by_source[key] = item
    used = set()
    rows = []
    for allocation in task.funding_allocations.all():
        values = allocation_as_values(allocation)
        key = _source_key(allocation.source_allocation_id)
        original = by_source.get(key) if key else None
        if original:
            used.add(key)
            changed = _changed_fields(values, original)
            rows.append({
                'allocation': allocation,
                'status': 'changed' if changed else 'unchanged',
                'changed_fields': changed,
                'values': values,
            })
        else:
            rows.append({
                'allocation': allocation,
                'status': 'added',
                'changed_fields': [],
                'values': values,
            })
    removed = []
    for key, item in by_source.items():
        if key not in used:
            removed.append({
                'allocation': None,
                'status': 'removed',
                'changed_fields': [],
                'values': {
                    'funding_source': item.get('funding_source') or '',
                    'workhours_percentage': item.get('workhours_percentage') or '',
                    'plan_position_number': item.get('plan_position_number') or '',
                    'job_number': item.get('job_number') or '',
                    'notes': item.get('notes') or '',
                    'funding_target_label': item.get('funding_target_label') or '—',
                    'source_id': item.get('source_id'),
                },
            })
    return rows, removed


def attach_funding_highlights(formset, snapshot):
    """Set row_status / changed_fields on each form for the extension inline."""
    if not snapshot:
        return
    by_source = {}
    for item in snapshot or []:
        key = _source_key(item.get('source_id'))
        if key:
            by_source[key] = item
    for form in formset.forms:
        form.row_status = ''
        form.changed_fields = []
        instance = getattr(form, 'instance', None)
        source_id = None
        if instance is not None:
            source_id = getattr(instance, 'source_allocation_id', None)
        if not source_id:
            source_id = (form.initial or {}).get('source_allocation_id')
        key = _source_key(source_id)
        has_row = bool(instance and (instance.pk or getattr(instance, 'funding_source', None)))
        if instance and instance.pk:
            values = allocation_as_values(instance)
            original = by_source.get(key) if key else None
            if original:
                changed = _changed_fields(values, original)
                form.row_status = 'changed' if changed else 'unchanged'
                form.changed_fields = changed
            else:
                form.row_status = 'added'
        elif key and key in by_source:
            form.row_status = 'unchanged'
        elif has_row:
            form.row_status = 'added'


def apply_snapshot_job_numbers(formset, snapshot):
    """Keep original job numbers when the field was hidden on create."""
    by_source = {
        _source_key(item.get('source_id')): item
        for item in (snapshot or [])
        if item.get('source_id') is not None
    }
    for form in formset.forms:
        data = getattr(form, 'cleaned_data', None) or {}
        if not data or data.get('DELETE'):
            continue
        instance = form.instance
        if not instance.pk:
            continue
        if (instance.job_number or '').strip():
            continue
        key = _source_key(instance.source_allocation_id or data.get('source_allocation_id'))
        original = by_source.get(key)
        if not original:
            continue
        job_number = (original.get('job_number') or '').strip()
        if job_number:
            instance.job_number = job_number
            instance.save(update_fields=['job_number'])
