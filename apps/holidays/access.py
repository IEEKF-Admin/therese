"""Permission helpers for holiday requests."""

from apps.accounts.permissions import GroupNames
from apps.holidays.features import holiday_flags
from apps.holidays.models import HolidayRequest


def _employee(user):
    return getattr(user, 'employee', None) if user and user.is_authenticated else None


def _workgroup_ids(employee):
    if not employee:
        return set()
    return set(employee.workgroups.values_list('pk', flat=True))


def user_can_approve_all(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.has_perm('holidays.approve_all_holiday')


def user_can_approve_workgroup(user):
    if not user or not user.is_authenticated:
        return False
    if user_can_approve_all(user):
        return True
    return user.has_perm('holidays.approve_workgroup_holiday')


def user_can_approve_request(user, holiday_request):
    if not holiday_flags()['approval']:
        return False
    if user_can_approve_all(user):
        return True
    if not user.has_perm('holidays.approve_workgroup_holiday'):
        return False
    approver = _employee(user)
    subject = holiday_request.employee
    return bool(_workgroup_ids(approver) & _workgroup_ids(subject))


def pending_requests_for_approver(user):
    if not holiday_flags()['approval']:
        return HolidayRequest.objects.none()
    qs = HolidayRequest.objects.filter(status=HolidayRequest.Status.PENDING).select_related(
        'employee',
    )
    if user_can_approve_all(user):
        return qs
    if not user.has_perm('holidays.approve_workgroup_holiday'):
        return HolidayRequest.objects.none()
    approver = _employee(user)
    wg_ids = _workgroup_ids(approver)
    if not wg_ids:
        return HolidayRequest.objects.none()
    return qs.filter(employee__workgroups__in=wg_ids).distinct()


def holidays_menu_needs_attention(user):
    if not holiday_flags()['approval']:
        return False
    if not user_can_approve_workgroup(user):
        return False
    return pending_requests_for_approver(user).exists()


def user_in_holiday_approver_groups(user):
    if not user or not user.is_authenticated:
        return False
    return user.groups.filter(
        name__in=[GroupNames.HOLIDAY_APPROVER, GroupNames.HOLIDAY_SUPER_APPROVER],
    ).exists()
