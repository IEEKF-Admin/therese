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
    contract.weekly_hours = hours
    contract.save(update_fields=['weekly_hours', 'updated_at'])
    return contract
