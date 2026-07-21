"""
PSP / WBS overview for authorized users.

Shows per PSP element a Plan / True / Obligo table. Personnel "True" costs use
employee funding allocations with salary × global true-cost multiplicator.

Do not remove any existing requirements from this module without explicit instruction.
"""

from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.models import GlobalSetting
from apps.hr.models import FundingAllocation, Workgroup
from apps.hr.validity import dedupe_allocations_as_of, resolve_as_of
from apps.hr.workgroup_access import get_user_workgroups
from apps.finances.models import (
    WBSElement,
    WBSElementObligo,
    WBSElementTrueYearlySpending,
    WBSElementYearEstimate,
)
from apps.finances.psp_access import (
    filter_psp_for_user,
    user_can_view_psp,
    user_can_view_psp_list,
    user_sees_all_psp,
)
from apps.finances.psp_cost_types import PSP_COST_TYPES


ZERO = Decimal('0.00')


def calculate_funding_cost(allocation, period_start, period_end):
    """
    Calculate total personnel cost for a FundingAllocation over the given period,
    using contract monthly costs (salary × true-cost multiplicator) and the
    allocation's percentage of workhours.
    """
    if not period_start:
        period_start = allocation.start_date
    if not period_end:
        period_end = allocation.end_date or date.today()

    overlap_start = max(allocation.start_date, period_start)
    alloc_end = allocation.end_date or date(9999, 12, 31)
    overlap_end = min(alloc_end, period_end)

    if overlap_start > overlap_end:
        return ZERO

    contract = allocation.employee.get_contract_as_of(overlap_start)
    if not contract:
        return ZERO

    full_monthly = contract.get_monthly_costs()
    if full_monthly is None:
        return ZERO

    percentage = Decimal(allocation.workhours_percentage or 0)
    prorated_monthly = Decimal(full_monthly) * (percentage / Decimal('100'))

    months = (
        (overlap_end.year - overlap_start.year) * 12
        + (overlap_end.month - overlap_start.month)
        + 1
    )

    return (prorated_monthly * months).quantize(Decimal('0.01'))


def _as_decimal(value) -> Decimal | None:
    if value is None or value == '':
        return None
    return Decimal(value).quantize(Decimal('0.01'))


def _period_for_year(year: int) -> tuple[date, date]:
    return date(year, 1, 1), date(year, 12, 31)


def _latest_snapshot(queryset, year: int):
    """
    Prefer the newest snapshot with date_of_update in ``year``,
    otherwise the newest snapshot overall (still useful context).
    """
    in_year = queryset.filter(
        date_of_update__year=year,
    ).order_by('-date_of_update').first()
    if in_year:
        return in_year, True
    any_row = queryset.order_by('-date_of_update').first()
    return any_row, False


def _build_personnel_rows(allocations, period_start, period_end, *, year_start=None, year_end=None):
    """
    Per-employee true-cost breakdown for the period.

    Returns (rows, total_all, total_not_booked).

    ``total_all`` / row ``period_cost`` use ``period_start``–``period_end``
    (Actual column / detail list).

    ``total_not_booked`` always uses the selected calendar year
    (``year_start``–``year_end``): salary × true-cost multiplicator ×
    workhours % × months overlapping the year and the allocation dates.
    Only funding allocations with import_completed=False are included.
    """
    if year_start is None or year_end is None:
        year_start, year_end = period_start, period_end

    rows = []
    total = ZERO
    not_booked_total = ZERO
    for alloc in allocations:
        cost = calculate_funding_cost(alloc, period_start, period_end)
        # Not booked is always scoped to the selected Year filter.
        not_booked_cost = calculate_funding_cost(alloc, year_start, year_end)
        monthly = None
        contract = alloc.employee.get_contract_as_of(period_start)
        if contract:
            monthly = contract.get_monthly_costs()
        import_completed = bool(getattr(alloc, 'import_completed', False))
        rows.append({
            'employee': alloc.employee,
            'employee_name': alloc.employee.get_full_name() if alloc.employee else '—',
            'percentage': alloc.workhours_percentage,
            'start_date': alloc.start_date,
            'end_date': alloc.end_date,
            'monthly_true_cost': monthly,
            'period_cost': cost,
            'not_booked_cost': not_booked_cost if not import_completed else ZERO,
            'plan_position_number': alloc.plan_position_number or '',
            'import_completed': import_completed,
            'allocation_pk': alloc.pk,
        })
        total += Decimal(cost or 0)
        if not import_completed:
            not_booked_total += Decimal(not_booked_cost or 0)
    rows.sort(key=lambda r: r['employee_name'].lower())
    return (
        rows,
        total.quantize(Decimal('0.01')),
        not_booked_total.quantize(Decimal('0.01')),
    )


def _resolve_plan_estimate(wbs: WBSElement, year: int):
    """
    Annual PSPs: estimate for the selected calendar year.
    Non-annual PSPs: the single lifetime plan row (full project runtime).
    """
    if wbs.subject_to_annual_recurrence:
        return (
            WBSElementYearEstimate.objects
            .filter(wbs_element=wbs, year=year)
            .first()
        ), 'year'

    estimates = list(
        WBSElementYearEstimate.objects
        .filter(wbs_element=wbs)
        .order_by('year')
    )
    if not estimates:
        return None, 'lifetime'
    if len(estimates) == 1:
        return estimates[0], 'lifetime'
    # Prefer row keyed by project start year if present
    if wbs.period_start:
        for est in estimates:
            if est.year == wbs.period_start.year:
                return est, 'lifetime'
    return estimates[0], 'lifetime'


def _personnel_cost_period(wbs: WBSElement, year: int) -> tuple[date, date, str]:
    """
    Period used for real personnel true costs.

    - Annual: selected calendar year
    - Non-annual: full PSP runtime (plan is also lifetime)
    """
    if wbs.subject_to_annual_recurrence:
        start, end = _period_for_year(year)
        return start, end, 'year'

    start = wbs.period_start or date(year, 1, 1)
    end = wbs.period_end or date.today()
    if end < start:
        end = start
    return start, end, 'lifetime'


def build_psp_financial_overview(wbs: WBSElement, year: int, multiplicator: Decimal) -> dict:
    """
    Assemble Plan / True / Obligo rows for one PSP element.

    - Plan (annual): YearEstimate for ``year``
    - Plan (non-annual): single lifetime YearEstimate for the full project
    - True (non-personnel): latest WBSElementTrueYearlySpending (prefer in-year)
    - True (personnel): funding allocations × salary × multiplicator over
      year (annual) or full project runtime (non-annual)
    - Obligo: latest WBSElementObligo (prefer in-year) + personal field
    """
    is_annual = bool(wbs.subject_to_annual_recurrence)
    estimate, plan_scope = _resolve_plan_estimate(wbs, year)
    period_start, period_end, personnel_scope = _personnel_cost_period(wbs, year)
    # Not booked always uses the Year filter (calendar year), never full lifetime.
    year_start, year_end = _period_for_year(year)

    true_spending, true_in_year = _latest_snapshot(
        wbs.true_yearly_spendings.all(), year
    )
    obligo, obligo_in_year = _latest_snapshot(wbs.obligos.all(), year)

    # Load allocations that overlap either the Actual period or the selected year
    # (so Not booked can be computed for the year even on non-annual PSPs).
    # Soft rule: per employee on this PSP, only the open allocation with the
    # latest start_date on the reference date wins (future starts ignored).
    range_start = min(period_start, year_start)
    range_end = max(period_end, year_end)
    as_of = resolve_as_of(None)
    if as_of > range_end:
        as_of = range_end
    if as_of < range_start:
        as_of = range_start
    raw_allocations = list(
        FundingAllocation.objects.filter(wbs_element=wbs)
        .filter(
            Q(end_date__isnull=True) | Q(end_date__gte=range_start),
            start_date__lte=range_end,
        )
        .select_related('employee')
        .order_by('employee__last_name', 'employee__first_name')
    )
    allocations = dedupe_allocations_as_of(raw_allocations, as_of)
    # Keep rows that only cover historical parts of the range (already ended
    # before as_of) so Actual still reflects past assignments without double-counting
    # open overlaps. If dedupe dropped everything for an employee, fall back to
    # raw list filtered to non-open historical rows only.
    winner_pks = {a.pk for a in allocations}
    for alloc in raw_allocations:
        if alloc.pk in winner_pks:
            continue
        # Include ended (historical) allocations that are not open on as_of
        if alloc.end_date is not None and alloc.end_date < as_of:
            if alloc.start_date <= range_end and alloc.end_date >= range_start:
                allocations.append(alloc)
    personnel_rows, real_personnel_total, not_booked_personnel_total = _build_personnel_rows(
        allocations,
        period_start,
        period_end,
        year_start=year_start,
        year_end=year_end,
    )

    cost_rows = []
    plan_total = ZERO
    true_total = ZERO
    obligo_total = ZERO
    not_booked_total = ZERO
    personal_obligo = _as_decimal(getattr(obligo, 'personal', None)) if obligo else None

    for flag_field, amount_field, code, label_de, label_en in PSP_COST_TYPES:
        enabled = getattr(wbs, flag_field, False)
        plan_val = _as_decimal(getattr(estimate, amount_field, None)) if estimate else None
        obligo_val = (
            _as_decimal(getattr(obligo, amount_field, None)) if obligo else None
        )
        not_booked_val = None

        if amount_field == 'personnel_costs':
            # True personnel = calculated from assigned employees (multiplicator).
            true_val = real_personnel_total
            true_source = 'real_personnel'
            imported_true = (
                _as_decimal(getattr(true_spending, amount_field, None))
                if true_spending else None
            )
            # Personalobligo belongs in the Obligo column of Personalkosten (.2),
            # not as a separate table row.
            if personal_obligo is not None:
                obligo_val = personal_obligo
            # Not booked (selected Year only): true costs for funding allocations
            # with import_completed=False.
            # cost = monthly_salary × multiplicator × (workhours% / 100) × months
            # of overlap between allocation validity and the selected calendar year.
            not_booked_val = not_booked_personnel_total
        else:
            true_val = (
                _as_decimal(getattr(true_spending, amount_field, None))
                if true_spending else None
            )
            true_source = 'imported'
            imported_true = true_val

        # Show row if cost type is enabled or any amount is present
        has_any = any(
            v is not None
            for v in (plan_val, true_val, obligo_val, imported_true, not_booked_val)
        )
        if not enabled and not has_any:
            continue

        plan_total += plan_val or ZERO
        # For personnel, always count real total; for others imported true
        if amount_field == 'personnel_costs':
            true_total += real_personnel_total or ZERO
            not_booked_total += not_booked_val or ZERO
        else:
            true_total += true_val or ZERO
        obligo_total += obligo_val or ZERO

        # Free budget = Budget − Actual − Commitment − Not booked
        free_budget = None
        if plan_val is not None:
            free_budget = (
                plan_val
                - (true_val or ZERO)
                - (obligo_val or ZERO)
                - (not_booked_val or ZERO)
            ).quantize(Decimal('0.01'))

        cost_rows.append({
            'code': code,
            'amount_field': amount_field,
            'label_de': label_de,
            'label_en': label_en,
            'enabled': enabled,
            'plan': plan_val,
            'true': true_val,
            'true_source': true_source,
            'imported_true': imported_true,
            'obligo': obligo_val,
            'not_booked': not_booked_val,
            'free_budget': free_budget,
        })

    free_budget_total = (
        plan_total - true_total - obligo_total - not_booked_total
    ).quantize(Decimal('0.01'))

    return {
        'wbs': wbs,
        'year': year,
        'is_annual': is_annual,
        'plan_scope': plan_scope,
        'personnel_scope': personnel_scope,
        'period_start': period_start,
        'period_end': period_end,
        'not_booked_period_start': year_start,
        'not_booked_period_end': year_end,
        'multiplicator': multiplicator,
        'estimate': estimate,
        'estimate_technical_year': estimate.year if estimate else None,
        'true_spending': true_spending,
        'true_spending_in_year': true_in_year,
        'true_spending_date': true_spending.date_of_update if true_spending else None,
        'obligo': obligo,
        'obligo_in_year': obligo_in_year,
        'obligo_date': obligo.date_of_update if obligo else None,
        'cost_rows': cost_rows,
        'personal_obligo': personal_obligo,
        'plan_total': plan_total.quantize(Decimal('0.01')),
        'true_total': true_total.quantize(Decimal('0.01')),
        'obligo_total': obligo_total.quantize(Decimal('0.01')),
        'not_booked_total': not_booked_total.quantize(Decimal('0.01')),
        'free_budget_total': free_budget_total,
        'personnel_rows': personnel_rows,
        'real_personnel_total': real_personnel_total,
        'not_booked_personnel_total': not_booked_personnel_total,
        'has_data': bool(cost_rows or personnel_rows or personal_obligo is not None),
    }


@login_required
def psp_elements(request):
    """PSP / WBS elements financial overview (Plan / True / Obligo)."""
    user = request.user

    if not user_can_view_psp_list(user):
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('tasks:my_tasks')

    base_wbs = (
        WBSElement.objects.active()
        .select_related('work_group', 'cost_center')
        .order_by('wbs_code')
    )
    all_wbs = filter_psp_for_user(base_wbs, user)

    if user_sees_all_psp(user):
        user_workgroups = list(Workgroup.objects.order_by('short_name'))
    else:
        user_workgroups = list(get_user_workgroups(user))

    current_year = date.today().year
    try:
        year = int(request.GET.get('year') or current_year)
    except (TypeError, ValueError):
        year = current_year

    wbs_id = request.GET.get('wbs', '') or 'all'
    filter_workgroup_id = request.GET.get('work_group', '')
    filter_workgroup = None
    if filter_workgroup_id and filter_workgroup_id != 'all':
        try:
            wg_pk = int(filter_workgroup_id)
        except (TypeError, ValueError):
            wg_pk = None
        if wg_pk is not None:
            filter_workgroup = next((wg for wg in user_workgroups if wg.pk == wg_pk), None)

    wbs_qs = all_wbs
    if filter_workgroup:
        wbs_qs = wbs_qs.filter(work_group=filter_workgroup)

    if wbs_id and wbs_id != 'all':
        try:
            wbs_qs = wbs_qs.filter(id=int(wbs_id))
        except (TypeError, ValueError, WBSElement.DoesNotExist):
            wbs_id = 'all'

    multiplicator = GlobalSetting.get_true_cost_multiplicator()

    # Prefetch related finance rows for listed PSPs
    wbs_list = list(
        wbs_qs.prefetch_related(
            'year_estimates',
            'true_yearly_spendings',
            'obligos',
        )
    )

    overviews = [
        build_psp_financial_overview(wbs, year, multiplicator)
        for wbs in wbs_list
    ]

    # Optional: only show PSPs that have some financial signal when viewing "all"
    show_empty = request.GET.get('show_empty') == '1'
    if wbs_id == 'all' and not show_empty:
        overviews = [o for o in overviews if o['has_data']]

    if request.GET.get('export'):
        return _export_csv(overviews, year)

    workgroup_choices = [('', '— All —')] + [(wg.id, str(wg)) for wg in user_workgroups]
    wbs_choices = [('all', '— All —')] + [(w.id, str(w)) for w in all_wbs]
    year_choices = list(range(current_year + 1, current_year - 8, -1))

    context = {
        'title': 'PSP Elements',
        'overviews': overviews,
        'year': year,
        'year_choices': year_choices,
        'multiplicator': multiplicator,
        'wbs_choices': wbs_choices,
        'selected_wbs': str(wbs_id),
        'workgroup_choices': workgroup_choices,
        'selected_workgroup': filter_workgroup_id,
        'show_empty': show_empty,
        'psp_count': len(overviews),
    }
    return render(request, 'finances/psp_elements.html', context)


@login_required
def psp_personnel_detail(request, pk):
    """Assigned personnel (true costs) for one PSP — opened from the Personalkosten row."""
    user = request.user
    if not user_can_view_psp_list(user):
        messages.error(request, 'You do not have permission to access this page.')
        return redirect('tasks:my_tasks')

    wbs = get_object_or_404(
        WBSElement.objects.select_related('work_group', 'cost_center'),
        pk=pk,
    )
    if not user_can_view_psp(user, wbs):
        messages.error(request, 'You do not have permission to view this PSP element.')
        return redirect('finances:psp_elements')

    current_year = date.today().year
    try:
        year = int(request.GET.get('year') or current_year)
    except (TypeError, ValueError):
        year = current_year

    multiplicator = GlobalSetting.get_true_cost_multiplicator()
    overview = build_psp_financial_overview(wbs, year, multiplicator)

    return render(request, 'finances/psp_personnel_detail.html', {
        'title': f'Personnel — {wbs.wbs_code}',
        'overview': overview,
        'wbs': wbs,
        'year': year,
        'multiplicator': multiplicator,
    })


def _export_csv(overviews, year):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = (
        f'attachment; filename="psp_plan_true_obligo_{year}.csv"'
    )
    writer = csv.writer(response)
    writer.writerow([
        'WBS',
        'Title',
        'Year',
        'Cost type',
        'Budget',
        'Actual',
        'Actual source',
        'Commitment',
        'Not booked',
        'Free budget',
    ])
    for overview in overviews:
        wbs = overview['wbs']
        for row in overview['cost_rows']:
            writer.writerow([
                wbs.wbs_code,
                wbs.title,
                year,
                row['label_de'],
                row['plan'] if row['plan'] is not None else '',
                row['true'] if row['true'] is not None else '',
                row['true_source'],
                row['obligo'] if row['obligo'] is not None else '',
                row['not_booked'] if row.get('not_booked') is not None else '',
                row['free_budget'] if row['free_budget'] is not None else '',
            ])
        for prow in overview['personnel_rows']:
            writer.writerow([
                wbs.wbs_code,
                wbs.title,
                year,
                f"Personnel detail: {prow['employee_name']} ({prow['percentage']}%)",
                '',
                prow['period_cost'],
                'real_personnel',
                '',
                '' if prow.get('import_completed') else prow['period_cost'],
                '',
            ])
    return response
