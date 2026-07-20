"""
Soft temporal resolution for Contract and FundingAllocation.

Product rule (soft, not a hard DB constraint):
- A record is *open on* ``as_of`` if it is **active** (``is_active``), has
  started (start ≤ as_of), and has not ended (end empty or end ≥ as_of).
- If several records are open, the one with the **latest start date** wins.
- Starts in the future (start > as_of) never win.
- ``is_active`` is manual, but forced to No when end date is in the past
  (see ``apply_past_end_deactivation``).

Different funding targets (distinct WBS / cost centers) can all be open at once;
the winner rule applies **per target** (employee + WBS, or employee + cost center).
"""

from __future__ import annotations

from datetime import date
from typing import Iterable

from django.db.models import Q, QuerySet
from django.utils import timezone


def resolve_as_of(as_of: date | None = None) -> date:
    if as_of is None:
        return timezone.now().date()
    return as_of


def apply_past_end_deactivation(instance, *, end_attr: str, as_of: date | None = None) -> bool:
    """
    If ``end_attr`` is a date strictly before ``as_of``, set ``is_active=False``.

    Returns True if the instance was deactivated by this rule.
    Manual deactivation (is_active=False with open end) is left as-is.
    """
    as_of = resolve_as_of(as_of)
    end = getattr(instance, end_attr, None)
    if end is not None and end < as_of:
        if getattr(instance, 'is_active', True):
            instance.is_active = False
            return True
        instance.is_active = False
        return True
    return False


def _require_active_flag(as_of: date) -> bool:
    """
    For ``as_of`` today or later, respect ``is_active`` (manual or auto off).
    For historical ``as_of``, use only date windows so past periods still resolve.
    """
    return as_of >= resolve_as_of(None)


def contract_open_on_q(as_of: date) -> Q:
    """Django Q: contracts open on ``as_of`` (started, not ended; + is_active if current)."""
    q = Q(valid_from__lte=as_of) & (
        Q(valid_until__isnull=True) | Q(valid_until__gte=as_of)
    )
    if _require_active_flag(as_of):
        q &= Q(is_active=True)
    return q


def allocation_open_on_q(as_of: date) -> Q:
    """Django Q: FAs open on ``as_of`` (started, not ended; + is_active if current)."""
    q = Q(start_date__lte=as_of) & (
        Q(end_date__isnull=True) | Q(end_date__gte=as_of)
    )
    if _require_active_flag(as_of):
        q &= Q(is_active=True)
    return q


def pick_latest_start(records: Iterable, start_attr: str):
    """
    Among already-filtered open records, pick the one with the latest start.

    Tie-break: higher primary key wins (stable, prefers more recently created).
    """
    best = None
    best_start = None
    best_pk = None
    for rec in records:
        start = getattr(rec, start_attr, None)
        if start is None:
            continue
        pk = getattr(rec, 'pk', 0) or 0
        if best is None or start > best_start or (start == best_start and pk > best_pk):
            best = rec
            best_start = start
            best_pk = pk
    return best


def select_contract_as_of(queryset: QuerySet, as_of: date | None = None):
    """
    Soft-select one contract from ``queryset`` (typically ``employee.contracts``).
    """
    as_of = resolve_as_of(as_of)
    return (
        queryset.filter(contract_open_on_q(as_of))
        .order_by('-valid_from', '-pk')
        .first()
    )


def select_allocation_as_of(queryset: QuerySet, as_of: date | None = None):
    """
    Soft-select one funding allocation from ``queryset``.

    Callers should already filter to one employee and one funding target
    (WBS or cost center) when they want a single “current” row for that target.
    """
    as_of = resolve_as_of(as_of)
    return (
        queryset.filter(allocation_open_on_q(as_of))
        .order_by('-start_date', '-pk')
        .first()
    )


def dedupe_allocations_as_of(allocations: Iterable, as_of: date | None = None) -> list:
    """
    Keep at most one open allocation per (employee, target) as of ``as_of``.

    Allocations that are not open on ``as_of`` are dropped.
    Target key = (employee_id, wbs_element_id, cost_center_id).
    """
    as_of = resolve_as_of(as_of)
    require_active = _require_active_flag(as_of)
    groups: dict[tuple, list] = {}
    for alloc in allocations:
        if require_active and not getattr(alloc, 'is_active', True):
            continue
        start = getattr(alloc, 'start_date', None)
        end = getattr(alloc, 'end_date', None)
        if start is None or start > as_of:
            continue
        if end is not None and end < as_of:
            continue
        key = (
            getattr(alloc, 'employee_id', None),
            getattr(alloc, 'wbs_element_id', None),
            getattr(alloc, 'cost_center_id', None),
        )
        groups.setdefault(key, []).append(alloc)

    winners = []
    for group in groups.values():
        winners.append(pick_latest_start(group, 'start_date'))
    return [w for w in winners if w is not None]
