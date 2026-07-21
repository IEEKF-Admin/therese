"""
PSP / WBS element access control.

Workgroup-scoped vs institute-wide permissions:

- ``view_psp_overview`` / ``manage_psp_element``:
  only PSP elements assigned to the user's workgroups (null work_group excluded).
- ``view_all_psp_elements`` / ``manage_all_psp_elements``:
  all PSP elements, including those without a work group.
- Superuser: full access.
"""

from __future__ import annotations

from apps.hr.workgroup_access import get_user_workgroups, user_workgroup_ids


def user_can_view_psp_list(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return (
        user.has_perm('finances.view_psp_overview')
        or user.has_perm('finances.view_psp_element')
        or user.has_perm('finances.view_all_psp_elements')
        or user.has_perm('finances.manage_psp_element')
        or user.has_perm('finances.manage_all_psp_elements')
    )


def user_can_manage_psp(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return (
        user.has_perm('finances.manage_psp_element')
        or user.has_perm('finances.manage_all_psp_elements')
    )


def user_sees_all_psp(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return (
        user.has_perm('finances.view_all_psp_elements')
        or user.has_perm('finances.manage_all_psp_elements')
    )


def user_manages_all_psp(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.has_perm('finances.manage_all_psp_elements')


def filter_psp_for_user(queryset, user):
    """
    Restrict PSP queryset by workgroup scope unless user has institute-wide rights.
    Elements without a work group are only included for institute-wide viewers.
    """
    if user_sees_all_psp(user):
        return queryset
    if not (
        user.has_perm('finances.view_psp_overview')
        or user.has_perm('finances.view_psp_element')
        or user.has_perm('finances.manage_psp_element')
    ):
        return queryset.none()
    wg_ids = user_workgroup_ids(user)
    if not wg_ids:
        return queryset.none()
    return queryset.filter(work_group_id__in=wg_ids)


def user_can_view_psp(user, wbs) -> bool:
    if not user_can_view_psp_list(user) or wbs is None:
        return False
    if user_sees_all_psp(user):
        return True
    if wbs.work_group_id is None:
        return False
    wg_ids = set(user_workgroup_ids(user))
    return wbs.work_group_id in wg_ids


def user_can_manage_psp_object(user, wbs=None) -> bool:
    if not user_can_manage_psp(user):
        return False
    if wbs is None:
        return True
    if user_manages_all_psp(user):
        return True
    if not user.has_perm('finances.manage_psp_element'):
        return False
    if wbs.work_group_id is None:
        return False
    wg_ids = set(user_workgroup_ids(user))
    return wbs.work_group_id in wg_ids


def psp_workgroup_queryset_for_user(user, instance=None):
    """Work groups the user may assign when creating/editing a PSP."""
    from apps.hr.models import Workgroup

    if user_manages_all_psp(user):
        queryset = Workgroup.objects.all()
    else:
        queryset = get_user_workgroups(user)
    if instance and getattr(instance, 'work_group_id', None):
        queryset = queryset | Workgroup.objects.filter(pk=instance.work_group_id)
    return queryset.distinct().order_by('short_name')
