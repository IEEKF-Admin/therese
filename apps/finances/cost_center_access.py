"""
Cost center access control.

Mirrors PSP workgroup-scoped vs institute-wide permissions:

- ``manage_cost_center``: only cost centers assigned to the user's workgroups
  (null work_group excluded).
- ``manage_all_cost_centers``: all cost centers, including those without a work group.
- Superuser: full access.
"""

from __future__ import annotations

from apps.hr.workgroup_access import get_user_workgroups, user_workgroup_ids


def user_can_manage_cost_center(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return (
        user.has_perm('finances.manage_cost_center')
        or user.has_perm('finances.manage_all_cost_centers')
    )


def user_manages_all_cost_centers(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.has_perm('finances.manage_all_cost_centers')


def filter_cost_centers_for_user(queryset, user):
    if user_manages_all_cost_centers(user):
        return queryset
    if not user.has_perm('finances.manage_cost_center'):
        return queryset.none()
    wg_ids = user_workgroup_ids(user)
    if not wg_ids:
        return queryset.none()
    return queryset.filter(work_group_id__in=wg_ids)


def user_can_manage_cost_center_object(user, cost_center=None) -> bool:
    if not user_can_manage_cost_center(user):
        return False
    if cost_center is None:
        return True
    if user_manages_all_cost_centers(user):
        return True
    if not user.has_perm('finances.manage_cost_center'):
        return False
    if cost_center.work_group_id is None:
        return False
    wg_ids = set(user_workgroup_ids(user))
    return cost_center.work_group_id in wg_ids


def cost_center_workgroup_queryset_for_user(user, instance=None):
    from apps.hr.models import Workgroup

    if user_manages_all_cost_centers(user):
        queryset = Workgroup.objects.all()
    else:
        queryset = get_user_workgroups(user)
    if instance and getattr(instance, 'work_group_id', None):
        queryset = queryset | Workgroup.objects.filter(pk=instance.work_group_id)
    return queryset.distinct().order_by('short_name')
