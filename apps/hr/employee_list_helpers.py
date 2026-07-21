"""Helpers for the employee list view (contract column, expiry warnings, search)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

from django.db.models import Prefetch, Q

from apps.hr.models import Contract, Employee, FundingAllocation
from apps.hr.validity import resolve_as_of, select_contract_as_of


EXPIRY_WARNING_DAYS = 90


def select_next_future_contract(contracts: Iterable[Contract], as_of: date | None = None):
    """Earliest contract that starts strictly after ``as_of``."""
    as_of = resolve_as_of(as_of)
    future = [
        c for c in contracts
        if c.valid_from and c.valid_from > as_of
    ]
    if not future:
        return None
    return min(future, key=lambda c: (c.valid_from, c.pk or 0))


def contract_covers_day(contract: Contract, day: date) -> bool:
    if not contract.valid_from or contract.valid_from > day:
        return False
    if contract.valid_until is not None and contract.valid_until < day:
        return False
    return True


def has_seamless_followup(current: Contract, contracts: Iterable[Contract]) -> bool:
    """
    True if some other contract covers the day after ``current.valid_until``.

    Open-ended current contracts are treated as having no expiry gap.
    """
    if current.valid_until is None:
        return True
    day_after = current.valid_until + timedelta(days=1)
    for c in contracts:
        if c.pk == current.pk:
            continue
        if contract_covers_day(c, day_after):
            return True
    return False


def contract_needs_expiry_warning(
    current: Contract | None,
    contracts: Iterable[Contract],
    *,
    as_of: date | None = None,
    within_days: int = EXPIRY_WARNING_DAYS,
) -> bool:
    """
    Warning for active-employee list only (caller enforces archive mode).

    - No soft-selected contract today → gap / no contract → warning
    - Current ends within ``within_days`` and no seamless follow-up → warning
      (includes cases where a later contract exists but leaves a gap)
    - Open-ended current → no warning
    """
    as_of = resolve_as_of(as_of)
    contracts = list(contracts)

    if current is None:
        return True

    if current.valid_until is None:
        return False

    horizon = as_of + timedelta(days=within_days)
    if current.valid_until > horizon:
        return False

    return not has_seamless_followup(current, contracts)


def expiry_warning_tooltip(
    current: Contract | None,
    contracts: Iterable[Contract],
    *,
    as_of: date | None = None,
) -> str:
    as_of = resolve_as_of(as_of)
    contracts = list(contracts)
    if current is None:
        return 'No active contract covering today (gap or missing contract).'
    if current.valid_until is None:
        return ''
    end = current.valid_until.isoformat()
    if has_seamless_followup(current, contracts):
        return ''
    next_c = select_next_future_contract(contracts, as_of)
    if next_c is None:
        return f'Contract ends {end} — no follow-up contract.'
    return (
        f'Contract ends {end} — follow-up starts {next_c.valid_from.isoformat()} '
        f'(gap).'
    )


def display_contract_valid_until(
    current: Contract | None,
    contracts: Iterable[Contract],
    *,
    as_of: date | None = None,
) -> dict:
    """
    Value for the Contract Valid Until column.

    Returns dict with keys: date (date|None), open_ended (bool),
    from_date (date|None) when showing a future contract, sort_key (date|None).
    """
    as_of = resolve_as_of(as_of)
    contracts = list(contracts)

    if current is not None:
        if current.valid_until is None:
            return {
                'date': None,
                'open_ended': True,
                'from_date': None,
                'sort_key': date.max,
                'label': 'Open-ended',
            }
        return {
            'date': current.valid_until,
            'open_ended': False,
            'from_date': None,
            'sort_key': current.valid_until,
            'label': None,
        }

    future = select_next_future_contract(contracts, as_of)
    if future is None:
        return {
            'date': None,
            'open_ended': False,
            'from_date': None,
            'sort_key': date.min,
            'label': '—',
        }
    if future.valid_until is None:
        return {
            'date': None,
            'open_ended': True,
            'from_date': future.valid_from,
            'sort_key': date.max,
            'label': 'Open-ended',
        }
    return {
        'date': future.valid_until,
        'open_ended': False,
        'from_date': future.valid_from,
        'sort_key': future.valid_until,
        'label': None,
    }


def annotate_employees_for_list(employees: list[Employee], *, as_of: date | None = None, archive_mode: bool = False):
    """Attach list-only attributes used by the template."""
    as_of = resolve_as_of(as_of)
    for emp in employees:
        contracts = list(emp.contracts.all())
        current = select_contract_as_of(emp.contracts.all(), as_of)
        emp.list_current_contract = current
        emp.list_valid_until = display_contract_valid_until(current, contracts, as_of=as_of)
        if archive_mode:
            emp.list_expiry_warning = False
            emp.list_expiry_tooltip = ''
        else:
            emp.list_expiry_warning = contract_needs_expiry_warning(
                current, contracts, as_of=as_of,
            )
            emp.list_expiry_tooltip = (
                expiry_warning_tooltip(current, contracts, as_of=as_of)
                if emp.list_expiry_warning else ''
            )
    return employees


def employee_list_search_q(search_query: str, *, as_of: date | None = None) -> Q:
    """
    Search: employee number, first/last name, job number on an open contract,
    plan positions of open FAs on an open contract.
    """
    as_of = resolve_as_of(as_of)
    q = search_query.strip()
    if not q:
        return Q()

    open_contract = (
        Q(contracts__valid_from__lte=as_of)
        & (Q(contracts__valid_until__isnull=True) | Q(contracts__valid_until__gte=as_of))
        & Q(contracts__is_active=True)
    )
    open_fa = (
        Q(contracts__funding_allocations__start_date__lte=as_of)
        & (
            Q(contracts__funding_allocations__end_date__isnull=True)
            | Q(contracts__funding_allocations__end_date__gte=as_of)
        )
        & Q(contracts__funding_allocations__is_active=True)
    )

    return (
        Q(first_name__icontains=q)
        | Q(last_name__icontains=q)
        | Q(employee_number__icontains=q)
        | (Q(contracts__job_number__icontains=q) & open_contract)
        | (
            Q(contracts__funding_allocations__plan_position_number__icontains=q)
            & open_contract
            & open_fa
        )
    )


def employees_queryset_for_list():
    return Employee.objects.select_related(
        'room__building', 'cost_center', 'user',
    ).prefetch_related(
        Prefetch(
            'contracts',
            queryset=Contract.objects.prefetch_related(
                Prefetch(
                    'funding_allocations',
                    queryset=FundingAllocation.objects.order_by('start_date', 'pk'),
                ),
            ).order_by('valid_from', 'pk'),
        ),
        'workgroups',
    )
