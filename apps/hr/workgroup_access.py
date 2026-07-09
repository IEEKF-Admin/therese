"""Workgroup-based data access helpers."""

from apps.hr.models import Workgroup


def get_user_workgroups(user):
    employee = getattr(user, 'employee', None)
    if employee is None:
        return Workgroup.objects.none()
    return employee.workgroups.all()


def user_workgroup_ids(user):
    return list(get_user_workgroups(user).values_list('pk', flat=True))


def filter_by_user_workgroups(queryset, user, *, field_name='work_group'):
    workgroup_ids = user_workgroup_ids(user)
    if not workgroup_ids:
        return queryset.none()
    return queryset.filter(**{f'{field_name}__in': workgroup_ids})