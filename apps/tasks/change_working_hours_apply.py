"""Apply Change Working Hours onto the employee's current contract."""

from django.utils import timezone


class ApplyWorkingHoursError(Exception):
    def __init__(self, message):
        self.message = message


def apply_change_working_hours(task):
    """Write ``task.new_weekly_hours`` onto the contract open today."""
    employee = getattr(task, 'employee', None)
    if employee is None:
        raise ApplyWorkingHoursError('This task has no employee.')
    hours = getattr(task, 'new_weekly_hours', None)
    if hours is None:
        raise ApplyWorkingHoursError('New weekly working hours are not set.')
    contract = employee.get_contract_as_of(timezone.localdate())
    if contract is None:
        raise ApplyWorkingHoursError(
            'No active contract found for this employee. '
            'The weekly hours could not be applied.'
        )
    from django.core.exceptions import ValidationError

    contract.weekly_hours = hours
    try:
        contract.save(update_fields=[
            'weekly_hours', 'monthly_salary', 'pay_scale_group', 'experience_level', 'updated_at',
        ])
    except ValidationError as exc:
        messages = exc.messages if hasattr(exc, 'messages') else [str(exc)]
        raise ApplyWorkingHoursError(messages[0] if messages else str(exc)) from exc
    return contract
