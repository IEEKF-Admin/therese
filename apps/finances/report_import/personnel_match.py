"""
Match Personalkosten sheet rows against FundingAllocations for import.

Cases:
- a) Employee + FA for PSP open in booking month → amount plausibility
- b) Employee, no FA for PSP in booking month → ignore or create FA
- c) Unknown personalnummer → ignore or create pending employee

Expected amount =
  (monthly_salary_100% + supplements)
  × (weekly_hours / default_weekly_hours)
  × true_cost_multiplicator
  × (workhours_percentage / 100)

Tolerance: GlobalSetting (default ±2.5%); January always ±4%.
import_completed is sticky True (per FA).
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Q, Sum

from apps.core.models import GlobalSetting
from apps.hr.models import Contract, Employee, FundingAllocation

ZERO = Decimal('0.00')
JANUARY_TOLERANCE = Decimal('0.04')

# Statuses that block commit until ignore or create_* is chosen.
BLOCKING_PERSONNEL_STATUSES = frozenset({'no_employee', 'no_allocation'})


def _q2(value: Decimal) -> Decimal:
    return value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def decision_key_for(personalnummer: str, parent_psp_code: str) -> str:
    """Stable form field key for a Personalkosten row (pn + parent PSP)."""
    return f'{personalnummer}__{parent_psp_code}'


def month_bounds(d: date) -> tuple[date, date]:
    """Return (first day, last day) of the calendar month of ``d``."""
    start = date(d.year, d.month, 1)
    end = date(d.year, d.month, monthrange(d.year, d.month)[1])
    return start, end


def tolerance_for_booking_date(booking_date: date | None) -> Decimal:
    """Relative tolerance; January always 4%."""
    if booking_date is not None and booking_date.month == 1:
        return JANUARY_TOLERANCE
    return Decimal(GlobalSetting.get_personnel_import_tolerance())


def _entry_as_dict(entry) -> dict:
    if hasattr(entry, '__dict__') and not isinstance(entry, dict):
        return {
            'personalnummer': entry.personalnummer,
            'kostenart': entry.kostenart,
            'personalkosten': entry.personalkosten,
            'belegdatum': entry.belegdatum.isoformat() if entry.belegdatum else None,
            'buchungsdatum': (
                entry.buchungsdatum.isoformat() if getattr(entry, 'buchungsdatum', None) else None
            ),
            'buchungstext': getattr(entry, 'buchungstext', '') or '',
            'psp_code': entry.psp_code,
            'parent_psp_code': entry.parent_psp_code,
            'source_filename': entry.source_filename,
        }
    data = dict(entry)
    data.setdefault('buchungstext', '')
    data.setdefault('buchungsdatum', None)
    return data


def _booking_date_from_data(data: dict) -> date | None:
    for key in ('buchungsdatum', 'belegdatum'):
        raw = data.get(key)
        if not raw:
            continue
        if isinstance(raw, date):
            return raw
        try:
            return date.fromisoformat(str(raw)[:10])
        except ValueError:
            continue
    return None


def allocation_for_employee_wbs_in_month(employee, wbs, booking_date: date):
    """
    First active FA for employee+PSP that overlaps the booking calendar month.
    """
    month_start, month_end = month_bounds(booking_date)
    qs = (
        FundingAllocation.objects.filter(
            employee=employee,
            wbs_element=wbs,
            is_active=True,
            start_date__lte=month_end,
        )
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=month_start))
        .order_by('start_date', 'pk')
    )
    return qs.first()


def active_open_fa_percentage_total(contract: Contract, as_of: date) -> Decimal:
    """Sum workhours_% of active FAs on contract that are open on ``as_of``."""
    total = (
        contract.funding_allocations.filter(
            is_active=True,
            start_date__lte=as_of,
        )
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=as_of))
        .aggregate(s=Sum('workhours_percentage'))
        .get('s')
    )
    return Decimal(total or 0).quantize(Decimal('0.01'))


def build_personnel_checks(entries: list, parent_wbs_code: str, as_of: date | None = None) -> list[dict]:
    """
    Build preview rows for one parent PSP.

    ``entries``: list of ParsedPersonalkostenEntry (or dicts with same keys).
    """
    as_of = as_of or date.today()
    from apps.finances.models import WBSElement

    wbs = WBSElement.objects.filter(wbs_code=parent_wbs_code).first()
    multi = Decimal(GlobalSetting.get_true_cost_multiplicator())
    checks = []

    for entry in entries:
        data = _entry_as_dict(entry)
        excel_amount = Decimal(str(data['personalkosten']))
        personalnummer = data['personalnummer']
        parent_code = data.get('parent_psp_code') or parent_wbs_code
        if parent_code != parent_wbs_code:
            continue

        booking_date = _booking_date_from_data(data)
        tol = tolerance_for_booking_date(booking_date)
        dkey = decision_key_for(personalnummer, parent_wbs_code)
        check = {
            **data,
            'excel_amount': str(_q2(excel_amount)),
            'status': 'pending',
            'case': None,
            'decision_key': dkey,
            'employee_pk': None,
            'employee_name': '',
            'allocation_pk': None,
            'percentage': None,
            'monthly_salary': None,
            'salary_with_supplements': None,
            'workload_fraction': None,
            'multiplicator': str(multi),
            'tolerance': str(tol),
            'booking_date': booking_date.isoformat() if booking_date else None,
            'expected_amount': None,
            'delta_pct': None,
            'import_completed_current': False,
            'requires_resolution': False,
            'employee_edit_url': None,
            'message': '',
        }

        if wbs is None:
            check['status'] = 'no_psp'
            check['case'] = 'a'
            check['message'] = f'PSP {parent_wbs_code} not found in database (create on commit).'
            checks.append(check)
            continue

        if booking_date is None:
            check['status'] = 'no_booking_date'
            check['case'] = 'a'
            check['message'] = 'No Buchungsdatum/Belegdatum on Personalkosten row.'
            checks.append(check)
            continue

        employee = Employee.objects.filter(employee_number=personalnummer).first()
        if employee is None:
            # Case c
            check['status'] = 'no_employee'
            check['case'] = 'c'
            check['requires_resolution'] = True
            check['message'] = (
                f'Der Mitarbeiter mit der Personalnummer {personalnummer} '
                f'existiert noch nicht. Anlegen (Pending) oder ignorieren.'
            )
            checks.append(check)
            continue

        check['employee_pk'] = employee.pk
        check['employee_name'] = employee.get_full_name()
        check['employee_edit_url'] = f'/hr/employees/{employee.pk}/edit/'
        if employee.is_pending:
            check['employee_name'] = f'{check["employee_name"]} (Pending)'

        allocation = allocation_for_employee_wbs_in_month(employee, wbs, booking_date)
        if allocation is None:
            # Case b
            check['status'] = 'no_allocation'
            check['case'] = 'b'
            check['requires_resolution'] = True
            contract = employee.get_contract_as_of(as_of)
            pct_sum = (
                active_open_fa_percentage_total(contract, as_of)
                if contract
                else ZERO
            )
            check['contract_fa_pct_sum'] = str(pct_sum)
            check['will_split_contract'] = bool(contract and pct_sum >= Decimal('100'))
            check['message'] = (
                f'Keine Funding Allocation für {check["employee_name"]} '
                f'auf PSP {parent_wbs_code} im Buchungsmonat '
                f'{booking_date.strftime("%Y-%m")}. '
                f'FA anlegen oder ignorieren.'
                + (
                    ' (Contract bereits 100 % → neuer Contract wird angelegt.)'
                    if check['will_split_contract']
                    else ''
                )
            )
            checks.append(check)
            continue

        # Case a — plausibility
        check['case'] = 'a'
        check['allocation_pk'] = allocation.pk
        check['import_completed_current'] = bool(allocation.import_completed)
        percentage = Decimal(allocation.workhours_percentage or 0)
        check['percentage'] = str(percentage)

        contract = allocation.contract or employee.get_contract_as_of(as_of)
        true_monthly = contract.get_monthly_costs() if contract else None
        base_salary = contract.get_monthly_salary() if contract else None
        if true_monthly is None:
            check['status'] = 'no_salary'
            check['message'] = (
                f'No monthly salary / true costs on contract for '
                f'{check["employee_name"]} as of {as_of.isoformat()}.'
            )
            checks.append(check)
            continue

        if base_salary is not None:
            check['monthly_salary'] = str(_q2(Decimal(base_salary)))
        salary_with_sup = contract.get_monthly_salary_with_supplements()
        if salary_with_sup is not None:
            check['salary_with_supplements'] = str(_q2(Decimal(salary_with_sup)))
        fraction = contract.get_workload_fraction()
        check['workload_fraction'] = str(fraction)

        if percentage == 0:
            check['status'] = 'zero_percentage'
            check['message'] = 'Funding allocation workhours percentage is 0.'
            checks.append(check)
            continue

        share = percentage / Decimal('100')
        expected = _q2(Decimal(true_monthly) * share)
        check['expected_amount'] = str(expected)

        if excel_amount == 0:
            check['status'] = 'mismatch'
            check['requires_resolution'] = True
            check['delta_pct'] = '100'
            check['message'] = 'Excel amount is zero.'
            checks.append(check)
            continue

        delta_pct = abs(expected - excel_amount) / excel_amount
        check['delta_pct'] = str(_q2(delta_pct * Decimal('100')))

        if delta_pct <= tol:
            check['status'] = 'match'
            check['message'] = (
                f'Match within ±{_q2(tol * 100)}% '
                f'(expected {expected} € vs Excel {_q2(excel_amount)} €). '
                'Will set import_completed = Yes.'
            )
        else:
            suggested_salary = contract.suggest_base_monthly_salary_for_allocation_amount(
                excel_amount, percentage
            )
            if suggested_salary is not None:
                check['suggested_monthly_salary'] = str(suggested_salary)
            check['status'] = 'mismatch'
            check['requires_resolution'] = True
            base_disp = check['monthly_salary'] or '—'
            sup_disp = check['salary_with_supplements'] or base_disp
            check['message'] = (
                f'Mismatch: expected {expected} € '
                f'(100% salary+supplements {sup_disp} € × workload {fraction} '
                f'× multi {multi} × {percentage}%) '
                f'vs Excel {_q2(excel_amount)} € '
                f'(Δ {check["delta_pct"]}%, tol ±{_q2(tol * 100)}%). '
                f'Current import_completed={check["import_completed_current"]}. '
                f'Base monthly salary (100%): {base_disp} €. '
                + (
                    f'Suggested base monthly salary (100%) to match: '
                    f'{check.get("suggested_monthly_salary")} €.'
                    if check.get('suggested_monthly_salary')
                    else 'Could not reverse-calculate a suggested base salary.'
                )
            )
        checks.append(check)

    return checks


def _copy_contract_fields(source: Contract, **overrides) -> Contract:
    """Create an unsaved Contract copy of ``source`` with optional overrides."""
    skip = {
        'id', 'pk', 'created_at', 'updated_at',
        'employee_id', 'employee',
    }
    kwargs = {}
    for field in source._meta.fields:
        name = field.name
        if name in skip or name in overrides:
            continue
        kwargs[name] = getattr(source, name)
    kwargs.update(overrides)
    kwargs['employee'] = source.employee
    return Contract(**kwargs)


def _create_placeholder_fa(
    *,
    contract: Contract,
    employee: Employee,
    wbs,
    as_of: date,
) -> FundingAllocation:
    """FA defaults: 1%, start=today, end=tomorrow."""
    start = as_of
    end = as_of + timedelta(days=1)
    fa = FundingAllocation(
        contract=contract,
        employee=employee,
        wbs_element=wbs,
        cost_center=None,
        workhours_percentage=Decimal('1.00'),
        start_date=start,
        end_date=end,
        is_active=True,
        import_completed=False,
    )
    fa.save()
    return fa


def _create_employee_from_check(check: dict, as_of: date) -> tuple[Employee, list[str]]:
    from apps.finances.models import WBSElement
    from apps.finances.report_import.parsers.personalkosten import parse_name_from_buchungstext

    notes = []
    personalnummer = check['personalnummer']
    existing = Employee.objects.filter(employee_number=personalnummer).first()
    if existing:
        notes.append(
            f'{personalnummer}: employee already exists (pk={existing.pk}); not re-created.'
        )
        return existing, notes

    last_name, first_name = parse_name_from_buchungstext(check.get('buchungstext') or '')
    employee = Employee(
        employee_number=personalnummer,
        first_name=first_name or 'Unknown',
        last_name=last_name or 'Unknown',
        is_pending=True,
        check_needed=True,
        user=None,
    )
    employee.save()

    parent_code = check.get('parent_psp_code') or ''
    wbs = WBSElement.objects.filter(wbs_code=parent_code).first()
    if wbs is None and parent_code:
        wbs = WBSElement.objects.create(
            wbs_code=parent_code,
            title=f'Auto-created from import ({parent_code})',
            has_personnel_costs=True,
        )
        notes.append(f'{personalnummer}: created stub PSP {parent_code}.')

    default_hours = GlobalSetting.get_default_weekly_hours()
    multi = Decimal(GlobalSetting.get_true_cost_multiplicator())
    excel_amount = Decimal(str(check.get('excel_amount') or check.get('personalkosten') or 0))
    # Excel Personalkosten is the full booked Lohn/Gehalt for this person/PSP/month.
    # The placeholder FA is intentionally only 1% (review stub) and must NOT be used
    # in the reverse formula — that would inflate the 100% base salary by ~100×.
    #
    # Derive 100% base monthly salary assuming full-time workload and that the
    # booking reflects true monthly costs at 100% of this person's work on the PSP:
    #   true_monthly ≈ base_100% × multi  ⇒  base_100% = excel / multi
    if multi > 0:
        base_salary = _q2(excel_amount / multi)
    else:
        base_salary = _q2(excel_amount)

    contract = Contract(
        employee=employee,
        weekly_hours=default_hours,
        monthly_salary=base_salary,
        valid_from=as_of,
        valid_until=as_of + timedelta(days=1),
        is_active=True,
        check_needed=True,
    )
    contract.save()

    if wbs is not None:
        fa = _create_placeholder_fa(
            contract=contract, employee=employee, wbs=wbs, as_of=as_of,
        )
        notes.append(
            f'{personalnummer}: created pending employee {employee.get_full_name()}, '
            f'contract, FA {fa.workhours_percentage}% on {wbs.wbs_code} '
            f'(base salary {base_salary} €).'
        )
    else:
        notes.append(
            f'{personalnummer}: created pending employee {employee.get_full_name()} '
            f'and contract (no PSP to attach FA).'
        )
    return employee, notes


def _create_fa_from_check(check: dict, as_of: date) -> list[str]:
    from apps.finances.models import WBSElement

    notes = []
    personalnummer = check.get('personalnummer')
    employee = Employee.objects.filter(pk=check.get('employee_pk')).first()
    if employee is None:
        employee = Employee.objects.filter(employee_number=personalnummer).first()
    if employee is None:
        notes.append(f'{personalnummer}: cannot create FA — employee missing.')
        return notes

    parent_code = check.get('parent_psp_code') or ''
    wbs = WBSElement.objects.filter(wbs_code=parent_code).first()
    if wbs is None:
        notes.append(f'{personalnummer}: cannot create FA — PSP {parent_code} missing.')
        return notes

    booking_date = _booking_date_from_data(check)
    contract = employee.get_contract_as_of(as_of)
    if contract is None:
        # No contract: create short contract like 3.2
        default_hours = GlobalSetting.get_default_weekly_hours()
        contract = Contract(
            employee=employee,
            weekly_hours=default_hours,
            monthly_salary=None,
            valid_from=as_of,
            valid_until=as_of + timedelta(days=1),
            is_active=True,
            check_needed=True,
        )
        contract.save()
        notes.append(f'{personalnummer}: created short contract (no prior contract).')
    else:
        pct_sum = active_open_fa_percentage_total(contract, as_of)
        if pct_sum >= Decimal('100.00'):
            # Contract split
            if contract.valid_until is not None:
                new_from = contract.valid_until + timedelta(days=1)
            elif booking_date is not None:
                new_from = date(booking_date.year, booking_date.month, 1)
            else:
                new_from = as_of
            new_until = new_from + timedelta(days=1)
            # Only one active contract: deactivate old
            contract.is_active = False
            if contract.valid_until is None:
                contract.valid_until = new_from - timedelta(days=1)
            contract.save(update_fields=['is_active', 'valid_until', 'updated_at'])

            new_contract = _copy_contract_fields(
                contract,
                valid_from=new_from,
                valid_until=new_until,
                is_active=True,
                check_needed=True,
            )
            new_contract.save()
            contract = new_contract
            notes.append(
                f'{personalnummer}: contract split — new contract '
                f'{new_from}–{new_until} (check_needed).'
            )

    fa = _create_placeholder_fa(
        contract=contract, employee=employee, wbs=wbs, as_of=as_of,
    )
    employee.check_needed = True
    employee.save(update_fields=['check_needed', 'updated_at'])
    notes.append(
        f'{personalnummer}: created FA 1% on {wbs.wbs_code} '
        f'({fa.start_date}–{fa.end_date}); employee check_needed=Yes.'
    )
    return notes


def apply_personnel_decisions(checks: list[dict], decisions: dict, as_of: date | None = None) -> list[str]:
    """
    Apply match / user decisions.

    ``decisions`` maps decision_key →
    'ignore' | 'adjust_salary' | 'create_fa' | 'create_employee'.
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

        if status == 'no_employee':
            if action == 'create_employee':
                _emp, create_notes = _create_employee_from_check(check, as_of)
                notes.extend(create_notes)
            elif action == 'ignore':
                notes.append(
                    f"{check.get('personalnummer')}: ignored (no_employee)."
                )
            else:
                notes.append(
                    f"{check.get('personalnummer')}: unresolved (no_employee) — skipped."
                )
            continue

        if status == 'no_allocation':
            if action == 'create_fa':
                notes.extend(_create_fa_from_check(check, as_of))
            elif action == 'ignore':
                notes.append(
                    f"{check.get('personalnummer')}: ignored (no_allocation)."
                )
            else:
                notes.append(
                    f"{check.get('personalnummer')}: unresolved (no_allocation) — skipped."
                )
            continue

        if status == 'match' and alloc_pk:
            FA = FundingAllocation.objects.filter(pk=alloc_pk).first()
            if FA and not FA.import_completed:
                FA.import_completed = True
                FA.save(update_fields=['import_completed', 'updated_at'])
                notes.append(
                    f"{check.get('personalnummer')}: import_completed=Yes (salary match)."
                )
            elif FA and FA.import_completed:
                notes.append(
                    f"{check.get('personalnummer')}: already import_completed=Yes."
                )
            continue

        if status != 'mismatch' or not alloc_pk:
            if status in {'no_salary', 'no_psp', 'zero_percentage', 'no_booking_date'}:
                notes.append(
                    f"{check.get('personalnummer')}: skipped ({status}) — "
                    f"import_completed unchanged."
                )
            continue

        action = action or 'ignore'
        FA = FundingAllocation.objects.filter(pk=alloc_pk).select_related(
            'employee', 'contract'
        ).first()
        if FA is None:
            continue

        if action == 'adjust_salary':
            suggested = check.get('suggested_monthly_salary')
            if not suggested:
                notes.append(f"{check.get('personalnummer')}: no suggested salary; ignored.")
                continue
            contract = FA.contract or FA.employee.get_contract_as_of(as_of)
            if contract is None:
                notes.append(
                    f"{check.get('personalnummer')}: no contract to adjust salary."
                )
                continue
            # Clear TV-L so clean() does not overwrite the adjusted base.
            contract.pay_scale_group = ''
            contract.experience_level = None
            contract.monthly_salary = Decimal(suggested)
            contract.save(update_fields=[
                'pay_scale_group',
                'experience_level',
                'monthly_salary',
                'updated_at',
            ])
            FA.import_completed = True
            FA.save(update_fields=['import_completed', 'updated_at'])
            notes.append(
                f"{check.get('personalnummer')}: base monthly salary (100%) set to "
                f"{suggested} € (TV-L cleared); import_completed=Yes."
            )
        else:
            notes.append(
                f"{check.get('personalnummer')}: ignored "
                f"(import_completed stays {FA.import_completed})."
            )

    return notes
