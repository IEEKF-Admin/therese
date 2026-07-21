"""
Employee list/edit access control.

Workgroup-scoped vs institute-wide permissions:

- ``can_view_employees`` / ``manage_employee``:
  only employees who share at least one workgroup with the current user.
- ``can_view_all_employees`` / ``manage_all_employees``:
  all employees, regardless of workgroup membership.
- Superuser: full access.
"""

from __future__ import annotations

from apps.hr.models import Employee
from apps.hr.workgroup_access import user_workgroup_ids


def user_can_view_employee_list(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return (
        user.has_perm('hr.can_view_employees')
        or user.has_perm('hr.can_view_all_employees')
        or user.has_perm('hr.manage_employee')
        or user.has_perm('hr.manage_all_employees')
    )


def user_can_manage_employees(user) -> bool:
    """May create/edit/delete employees (subject to object scope)."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.has_perm('hr.manage_employee') or user.has_perm('hr.manage_all_employees')


def user_sees_all_employees(user) -> bool:
    """Institute-wide view scope (not limited by own workgroups)."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return (
        user.has_perm('hr.can_view_all_employees')
        or user.has_perm('hr.manage_all_employees')
    )


def user_manages_all_employees(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.has_perm('hr.manage_all_employees')


def filter_employees_for_user(queryset, user):
    """
    Restrict employee queryset by workgroup scope unless user has institute-wide rights.
    """
    if user_sees_all_employees(user):
        return queryset
    if not (
        user.has_perm('hr.can_view_employees')
        or user.has_perm('hr.manage_employee')
    ):
        return queryset.none()
    wg_ids = user_workgroup_ids(user)
    if not wg_ids:
        return queryset.none()
    return queryset.filter(workgroups__in=wg_ids).distinct()


def user_can_view_employee(user, employee: Employee) -> bool:
    if not user_can_view_employee_list(user) or employee is None:
        return False
    if user_sees_all_employees(user):
        return True
    wg_ids = set(user_workgroup_ids(user))
    if not wg_ids:
        return False
    return employee.workgroups.filter(pk__in=wg_ids).exists()


def user_can_manage_employee(user, employee: Employee | None = None) -> bool:
    """
    Manage permission, optionally for a specific employee object.

    Without ``employee``: whether the user may manage employees at all
    (create, or edit any in scope).
    """
    if not user_can_manage_employees(user):
        return False
    if employee is None:
        return True
    if user_manages_all_employees(user):
        return True
    # Workgroup-scoped manage
    if not user.has_perm('hr.manage_employee'):
        return False
    wg_ids = set(user_workgroup_ids(user))
    if not wg_ids:
        return False
    return employee.workgroups.filter(pk__in=wg_ids).exists()
