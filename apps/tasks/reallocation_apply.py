"""Apply reallocation funding rows onto the employee's funding allocations."""

from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.urls import NoReverseMatch, reverse

from apps.hr.models import FundingAllocation

COMPLETED_STATUS = 'completed'
CHOICE_END = 'end'
CHOICE_RESUME = 'resume'
VALID_CHOICES = {CHOICE_END, CHOICE_RESUME}


class ApplyReallocationError(Exception):
    """User-facing apply failure (missing contract, job number, or choice)."""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


def _format_date(value):
    if not value:
        return ''
    return value.strftime('%d.%m.%Y')


def reallocation_exceeds_contract(task, contract):
    """True when the reallocation outlasts the contract open on Valid From."""
    if contract is None or contract.valid_until is None:
        return False
    if task.valid_until is None:
        return True
    return task.valid_until > contract.valid_until


def contract_extension_required_message(task, contract):
    contract_end = _format_date(contract.valid_until)
    if task.valid_until is None:
        return (
            f'This reallocation has no end date, but the current contract ends on '
            f'{contract_end}. Please create a follow-on contract first, then apply '
            f'the funding allocations.'
        )
    return (
        f'This reallocation runs until {_format_date(task.valid_until)}, which is after '
        f'the current contract ends on {contract_end}. Please create a follow-on '
        f'contract first, then apply the funding allocations.'
    )


def overlapping_employee_allocations(employee, valid_from, valid_until):
    """Active FAs on active contracts that overlap the reallocation window."""
    qs = employee.allocations.filter(
        is_active=True,
        contract__is_active=True,
    ).filter(
        Q(end_date__isnull=True) | Q(end_date__gte=valid_from),
    )
    if valid_until is not None:
        qs = qs.filter(start_date__lte=valid_until)
    return qs.select_related('wbs_element', 'cost_center', 'contract').order_by(
        'start_date', 'end_date', 'pk',
    )


def allocation_runs_longer(allocation, valid_until):
    """True when the existing FA continues after the reallocation ends."""
    if valid_until is None:
        return True
    if allocation.end_date is None:
        return True
    return allocation.end_date > valid_until


def is_reallocation_period_row(allocation, task):
    """Skip FAs that already cover exactly this reallocation window."""
    return (
        allocation.start_date == task.valid_from
        and allocation.end_date == task.valid_until
    )


def longer_running_conflicts(task):
    """Existing FAs that overlap and outlast the reallocation (will be split)."""
    conflicts = []
    for allocation in overlapping_employee_allocations(
        task.employee, task.valid_from, task.valid_until,
    ):
        if is_reallocation_period_row(allocation, task):
            continue
        if allocation_runs_longer(allocation, task.valid_until):
            conflicts.append(allocation)
    return conflicts


def build_apply_preview(task):
    """JSON-serializable payload for the Apply confirmation modal."""
    contract = task.employee.get_contract_as_of(task.valid_from)
    allocations = []
    for row in task.funding_allocations.all():
        allocations.append({
            'id': row.pk,
            'label': row.funding_target_label,
            'percentage': str(row.workhours_percentage),
            'job_number': (row.job_number or '').strip(),
            'plan_position': (row.plan_position_number or '').strip(),
        })
    conflicts = []
    for existing in longer_running_conflicts(task):
        conflicts.append({
            'id': existing.pk,
            'label': existing.funding_target_label,
            'percentage': str(existing.workhours_percentage),
            'job_number': (existing.job_number or existing.contract.job_number or '').strip(),
            'start': _format_date(existing.start_date),
            'end': _format_date(existing.end_date),
        })
    exceeds_contract = reallocation_exceeds_contract(task, contract)
    employee_url = ''
    if task.employee_id:
        try:
            employee_url = reverse('hr:employee_update', args=[task.employee_id])
        except NoReverseMatch:
            employee_url = ''
    return {
        'has_contract': contract is not None,
        'can_resume': task.valid_until is not None,
        'valid_from': _format_date(task.valid_from),
        'valid_until': _format_date(task.valid_until),
        'employee_name': task.employee.get_full_name(),
        'allocations': allocations,
        'conflicts': [] if exceeds_contract else conflicts,
        'exceeds_contract': exceeds_contract,
        'exceeds_contract_message': (
            contract_extension_required_message(task, contract) if exceeds_contract else ''
        ),
        'employee_url': employee_url,
    }


def _matching_applied_row(contract, source_row, task):
    qs = contract.funding_allocations.filter(
        start_date=task.valid_from,
        end_date=task.valid_until,
        workhours_percentage=source_row.workhours_percentage,
    )
    if source_row.wbs_element_id:
        qs = qs.filter(
            wbs_element_id=source_row.wbs_element_id,
            cost_center__isnull=True,
        )
    else:
        qs = qs.filter(
            cost_center_id=source_row.cost_center_id,
            wbs_element__isnull=True,
        )
    return qs.first()


def _resume_after_reallocation(allocation, original_end, task):
    """Create a continuation FA from the day after the reallocation ends."""
    if task.valid_until is None:
        return None
    resume_start = task.valid_until + timedelta(days=1)
    if original_end is not None and original_end < resume_start:
        return None
    return FundingAllocation.objects.create(
        contract=allocation.contract,
        employee=allocation.employee,
        wbs_element=allocation.wbs_element,
        cost_center=allocation.cost_center,
        workhours_percentage=allocation.workhours_percentage,
        plan_position_number=allocation.plan_position_number,
        job_number=allocation.job_number,
        start_date=resume_start,
        end_date=original_end,
        is_active=True,
        comments=allocation.comments,
    )


def _should_resume(allocation, task):
    """True when the old FA still has a period after the reallocation."""
    return (
        task.valid_until is not None
        and allocation_runs_longer(allocation, task.valid_until)
    )


def _adjust_existing_allocation(allocation, task):
    """
    Split an overlapping FA around the reallocation.

    The original row ends the day before Valid From. If it would have continued
    after Valid Until, a copy starts the day after the reallocation.
    """
    original_end = allocation.end_date
    resume = _should_resume(allocation, task)
    if allocation.start_date >= task.valid_from:
        if resume:
            allocation.start_date = task.valid_until + timedelta(days=1)
            if original_end is not None and allocation.start_date > original_end:
                allocation.is_active = False
            allocation.save()
            return
        allocation.is_active = False
        allocation.save()
        return
    allocation.end_date = task.valid_from - timedelta(days=1)
    allocation.save()
    if resume:
        _resume_after_reallocation(allocation, original_end, task)


@transaction.atomic
def apply_reallocation_funding(task, *, job_numbers, continuation_choices):
    """
    Write reallocation funding rows onto the employee's open contract.

    ``job_numbers`` maps reallocation-row pk (str or int) → job number.
    ``continuation_choices`` is accepted for older callers and ignored;
    overlapping FAs that run longer are always split around the reallocation.
    """
    if task.status != COMPLETED_STATUS:
        raise ApplyReallocationError(
            'Funding can only be applied when the task status is Completed.'
        )
    if not task.funding_allocations.exists():
        raise ApplyReallocationError('At least one funding allocation is required.')

    contract = task.employee.get_contract_as_of(task.valid_from)
    if contract is None:
        raise ApplyReallocationError(
            'No contract is open on the reallocation start date. '
            'Create or extend a contract before applying funding.'
        )
    if reallocation_exceeds_contract(task, contract):
        raise ApplyReallocationError(contract_extension_required_message(task, contract))

    job_numbers = {str(key): (value or '').strip() for key, value in (job_numbers or {}).items()}

    source_rows = list(task.funding_allocations.all())
    for row in source_rows:
        posted = job_numbers.get(str(row.pk), '')
        if posted and row.job_number != posted:
            row.job_number = posted
            row.save(update_fields=['job_number'])
        if not (row.job_number or '').strip():
            raise ApplyReallocationError(
                f'Job number is required for {row.funding_target_label}.'
            )

    overlapping = list(
        overlapping_employee_allocations(task.employee, task.valid_from, task.valid_until)
    )
    for existing in overlapping:
        if is_reallocation_period_row(existing, task):
            continue
        _adjust_existing_allocation(existing, task)

    created = 0
    for row in source_rows:
        if _matching_applied_row(contract, row, task):
            continue
        FundingAllocation.objects.create(
            contract=contract,
            employee=task.employee,
            wbs_element=row.wbs_element,
            cost_center=row.cost_center,
            workhours_percentage=row.workhours_percentage,
            plan_position_number=row.plan_position_number,
            job_number=row.job_number,
            start_date=task.valid_from,
            end_date=task.valid_until,
            is_active=True,
            comments=row.notes or '',
        )
        created += 1
    return created
