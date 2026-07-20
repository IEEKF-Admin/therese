"""
Match Personalkosten sheet rows against FundingAllocations for import.

Assumptions (documented for the product owner):
- Personalnummer maps to Employee.employee_number
- Compared amount = monthly_salary × true_cost_multiplicator × (workhours_percentage / 100)
- Tolerance: ±2.5% relative to the Excel amount
- Only Kostenart 60003000, positive Personalkosten
- Per Personalnummer: latest Belegdatum wins
- Current allocation (soft rule): started (start ≤ as_of), not ended, latest
  start_date wins; future starts ignored (see apps.hr.validity)
- Match or adjust_salary → FundingAllocation.import_completed = True
- no_employee / no_allocation block commit unless explicitly ignored
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from apps.core.models import GlobalSetting
from apps.hr.models import Employee, FundingAllocation

TOLERANCE = Decimal('0.025')  # ±2.5%
ZERO = Decimal('0.00')

# Statuses that block commit until the user chooses "ignore" (or fixes data and rechecks).
BLOCKING_PERSONNEL_STATUSES = frozenset({'no_employee', 'no_allocation'})


def _q2(value: Decimal) -> Decimal:
    return value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def decision_key_for(personalnummer: str, parent_psp_code: str) -> str:
    """Stable form field key for a Personalkosten row (pn + parent PSP)."""
    return f'{personalnummer}__{parent_psp_code}'


def _current_allocation(employee: Employee, wbs, as_of: date) -> FundingAllocation | None:
    """Soft rule: open on as_of, latest start_date wins (no future starts)."""
    return FundingAllocation.for_employee_wbs_as_of(employee, wbs, as_of)


def build_personnel_checks(entries: list, parent_wbs_code: str, as_of: date | None = None) -> list[dict]:
    """
    Build preview rows for salary matching for one parent PSP.

    ``entries``: list of ParsedPersonalkostenEntry (or dicts with same keys).
    """
    as_of = as_of or date.today()
    from apps.finances.models import WBSElement

    wbs = WBSElement.objects.filter(wbs_code=parent_wbs_code).first()
    multi = Decimal(GlobalSetting.get_true_cost_multiplicator())
    checks = []

    for entry in entries:
        if hasattr(entry, '__dict__') and not isinstance(entry, dict):
            data = {
                'personalnummer': entry.personalnummer,
                'kostenart': entry.kostenart,
                'personalkosten': entry.personalkosten,
                'belegdatum': entry.belegdatum.isoformat() if entry.belegdatum else None,
                'psp_code': entry.psp_code,
                'parent_psp_code': entry.parent_psp_code,
                'source_filename': entry.source_filename,
            }
            excel_amount = Decimal(entry.personalkosten)
            personalnummer = entry.personalnummer
            parent_code = entry.parent_psp_code
        else:
            data = dict(entry)
            excel_amount = Decimal(str(data['personalkosten']))
            personalnummer = data['personalnummer']
            parent_code = data.get('parent_psp_code') or parent_wbs_code

        # Only rows for this parent PSP (or its children)
        if parent_code != parent_wbs_code:
            continue

        dkey = decision_key_for(personalnummer, parent_wbs_code)
        check = {
            **data,
            'excel_amount': str(_q2(excel_amount)),
            'status': 'pending',
            'decision_key': dkey,
            'employee_pk': None,
            'employee_name': '',
            'allocation_pk': None,
            'percentage': None,
            'monthly_salary': None,
            'multiplicator': str(multi),
            'expected_amount': None,
            'delta_pct': None,
            'import_completed_current': False,
            'requires_resolution': False,
            'message': '',
        }

        if wbs is None:
            check['status'] = 'no_psp'
            check['message'] = f'PSP {parent_wbs_code} not found in database (create on commit).'
            checks.append(check)
            continue

        employee = Employee.objects.filter(employee_number=personalnummer).first()
        if employee is None:
            check['status'] = 'no_employee'
            check['requires_resolution'] = True
            check['message'] = (
                f'Der Mitarbeiter mit der Personalnummer {personalnummer} '
                f'existiert noch nicht im System. Bitte lege ihn an.'
            )
            checks.append(check)
            continue

        check['employee_pk'] = employee.pk
        check['employee_name'] = employee.get_full_name()

        allocation = _current_allocation(employee, wbs, as_of)
        if allocation is None:
            check['status'] = 'no_allocation'
            check['requires_resolution'] = True
            check['message'] = (
                f'Für Mitarbeiter {check["employee_name"]} '
                f'(Personalnummer {personalnummer}) existiert keine aktuelle '
                f'Funding Allocation zum PSP-Element {parent_wbs_code}. '
                f'Bitte lege eine Funding Allocation an.'
            )
            checks.append(check)
            continue

        check['allocation_pk'] = allocation.pk
        check['import_completed_current'] = bool(allocation.import_completed)
        percentage = Decimal(allocation.workhours_percentage or 0)
        check['percentage'] = str(percentage)

        contract = employee.get_contract_as_of(as_of)
        salary = contract.get_monthly_salary() if contract else None
        if salary is None:
            check['status'] = 'no_salary'
            check['message'] = (
                f'No monthly salary on contract for {check["employee_name"]} as of {as_of.isoformat()}.'
            )
            checks.append(check)
            continue

        salary = Decimal(salary)
        check['monthly_salary'] = str(_q2(salary))
        if percentage == 0:
            check['status'] = 'zero_percentage'
            check['message'] = 'Funding allocation workhours percentage is 0.'
            checks.append(check)
            continue

        share = percentage / Decimal('100')
        # expected = Monatsgehalt × Multiplikator × %
        expected = _q2(salary * multi * share)
        check['expected_amount'] = str(expected)

        if excel_amount == 0:
            check['status'] = 'mismatch'
            check['delta_pct'] = '100'
            check['message'] = 'Excel amount is zero.'
            checks.append(check)
            continue

        delta_pct = abs(expected - excel_amount) / excel_amount
        check['delta_pct'] = str(_q2(delta_pct * Decimal('100')))  # as percent points string

        if delta_pct <= TOLERANCE:
            check['status'] = 'match'
            check['message'] = (
                f'Match within ±2.5% (expected {expected} € vs Excel {_q2(excel_amount)} €). '
                'Will set import_completed = Yes.'
            )
        else:
            # monthly_salary so that salary × multi × share = excel
            suggested_salary = _q2(excel_amount / (multi * share))
            check['status'] = 'mismatch'
            check['suggested_monthly_salary'] = str(suggested_salary)
            check['message'] = (
                f'Mismatch: expected {expected} € '
                f'(salary {_q2(salary)} € × multi {multi} × {percentage}%) '
                f'vs Excel {_q2(excel_amount)} € '
                f'(Δ {check["delta_pct"]}%). '
                f'Current import_completed={check["import_completed_current"]}. '
                f'Suggested monthly salary to match: {suggested_salary} € '
                f'(also sets import_completed = Yes).'
            )
        checks.append(check)

    return checks


def apply_personnel_decisions(checks: list[dict], decisions: dict, as_of: date | None = None) -> list[str]:
    """
    Apply match / user decisions.

    ``decisions`` maps decision_key (or allocation_pk str for legacy) →
    'ignore' | 'adjust_salary'.

    Returns list of human-readable action notes.
    """
    as_of = as_of or date.today()
    notes = []

    for check in checks:
        status = check.get('status')
        dkey = check.get('decision_key') or decision_key_for(
            str(check.get('personalnummer') or ''),
            str(check.get('parent_psp_code') or ''),
        )
        alloc_pk = check.get('allocation_pk')
        action = (
            decisions.get(dkey)
            or decisions.get(str(alloc_pk) if alloc_pk else '')
            or decisions.get(alloc_pk)
        )

        if status in BLOCKING_PERSONNEL_STATUSES:
            if action == 'ignore':
                notes.append(
                    f"{check.get('personalnummer')}: ignored ({status}) — "
                    f"import continues without this employee."
                )
            else:
                # Should be blocked in merge_user_decisions; defensive skip.
                notes.append(
                    f"{check.get('personalnummer')}: unresolved ({status}) — skipped."
                )
            continue

        if status == 'match' and alloc_pk:
            FA = FundingAllocation.objects.filter(pk=alloc_pk).first()
            if FA:
                FA.import_completed = True
                FA.save(update_fields=['import_completed', 'updated_at'])
                notes.append(
                    f"{check.get('personalnummer')}: import_completed=Yes (salary match)."
                )
            continue

        if status != 'mismatch' or not alloc_pk:
            if status in {'no_salary', 'no_psp', 'zero_percentage'}:
                notes.append(
                    f"{check.get('personalnummer')}: skipped ({status}) — "
                    f"import_completed unchanged."
                )
            continue

        action = action or 'ignore'
        FA = FundingAllocation.objects.filter(pk=alloc_pk).select_related('employee').first()
        if FA is None:
            continue

        if action == 'adjust_salary':
            suggested = check.get('suggested_monthly_salary')
            if not suggested:
                notes.append(f"{check.get('personalnummer')}: no suggested salary; ignored.")
                continue
            employee = FA.employee
            contract = employee.get_contract_as_of(as_of)
            if contract is None:
                notes.append(
                    f"{check.get('personalnummer')}: no contract to adjust salary."
                )
                continue
            contract.monthly_salary = Decimal(suggested)
            contract.save(update_fields=['monthly_salary', 'updated_at'])
            FA.import_completed = True
            FA.save(update_fields=['import_completed', 'updated_at'])
            notes.append(
                f"{check.get('personalnummer')}: monthly salary set to {suggested} €; "
                f"import_completed=Yes."
            )
        else:
            # ignore — leave import_completed as is
            notes.append(
                f"{check.get('personalnummer')}: ignored "
                f"(import_completed stays {FA.import_completed})."
            )

    return notes
