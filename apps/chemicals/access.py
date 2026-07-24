"""Permission helpers for Chemicals and Chemical Items."""

from __future__ import annotations

from django.db.models import Q

from apps.hr.workgroup_access import user_workgroup_ids


def _emp(user):
    return getattr(user, 'employee', None)


def user_can_view_chemical_list(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return (
        user.has_perm('chemicals.view_all_chemicals')
        or user.has_perm('chemicals.manage_all_chemicals')
        or user.has_perm('chemicals.view_chemical_workgroup')
        or user.has_perm('chemicals.manage_chemical_workgroup')
        or user.has_perm('chemicals.view_all_chemical_items')
        or user.has_perm('chemicals.manage_all_chemical_items')
        or user.has_perm('chemicals.view_workgroup_chemical_items')
        or user.has_perm('chemicals.manage_workgroup_chemical_items')
        or user.has_perm('chemicals.view_own_chemical_items')
        or user.has_perm('chemicals.manage_own_chemical_items')
    )


def user_can_manage_all_chemicals(user) -> bool:
    return bool(
        user and user.is_authenticated
        and (user.is_superuser or user.has_perm('chemicals.manage_all_chemicals'))
    )


def user_can_create_chemical(user) -> bool:
    """Who may manually create a Chemical (CAS master) record."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return (
        user.has_perm('chemicals.manage_all_chemicals')
        or user.has_perm('chemicals.manage_chemical_workgroup')
        or user.has_perm('chemicals.manage_all_chemical_items')
        or user.has_perm('chemicals.manage_workgroup_chemical_items')
        or user.has_perm('chemicals.manage_own_chemical_items')
    )


def user_can_manage_chemical(user, chemical=None) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.has_perm('chemicals.manage_all_chemicals'):
        return True
    if chemical is None:
        return user.has_perm('chemicals.manage_chemical_workgroup')
    if not user.has_perm('chemicals.manage_chemical_workgroup'):
        return False
    wg_ids = user_workgroup_ids(user)
    if not wg_ids:
        return False
    return chemical.items.filter(workgroup_id__in=wg_ids).exists()


def user_can_view_chemical(user, chemical) -> bool:
    if not user_can_view_chemical_list(user):
        return False
    if user.is_superuser or user.has_perm('chemicals.view_all_chemicals') or user.has_perm('chemicals.manage_all_chemicals'):
        return True
    # Linked via items user can see
    from apps.chemicals.models import ChemicalItem
    return filter_chemical_items_for_user(ChemicalItem.objects.filter(chemical=chemical), user).exists()


def user_can_view_chemical_item_list(user) -> bool:
    return user_can_view_chemical_list(user)


def user_can_manage_chemical_item(user, item=None) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.has_perm('chemicals.manage_all_chemical_items'):
        return True
    emp = _emp(user)
    if item is None:
        return (
            user.has_perm('chemicals.manage_own_chemical_items')
            or user.has_perm('chemicals.manage_workgroup_chemical_items')
        )
    # Orderer always with manage_own
    if (
        user.has_perm('chemicals.manage_own_chemical_items')
        and emp
        and item.ordered_by_id == emp.pk
    ):
        return True
    if user.has_perm('chemicals.manage_workgroup_chemical_items'):
        wg_ids = set(user_workgroup_ids(user))
        if item.workgroup_id and item.workgroup_id in wg_ids:
            return True
    return False


def user_can_view_chemical_item(user, item) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or user.has_perm('chemicals.view_all_chemical_items') or user.has_perm('chemicals.manage_all_chemical_items'):
        return True
    emp = _emp(user)
    if (
        (user.has_perm('chemicals.view_own_chemical_items') or user.has_perm('chemicals.manage_own_chemical_items'))
        and emp
        and item.ordered_by_id == emp.pk
    ):
        return True
    if user.has_perm('chemicals.view_workgroup_chemical_items') or user.has_perm('chemicals.manage_workgroup_chemical_items'):
        wg_ids = set(user_workgroup_ids(user))
        if item.workgroup_id and item.workgroup_id in wg_ids:
            return True
    return False


def filter_chemical_items_for_user(qs, user):
    if not user or not user.is_authenticated:
        return qs.none()
    if user.is_superuser or user.has_perm('chemicals.view_all_chemical_items') or user.has_perm('chemicals.manage_all_chemical_items'):
        return qs
    emp = _emp(user)
    q = Q()
    if emp and (
        user.has_perm('chemicals.view_own_chemical_items')
        or user.has_perm('chemicals.manage_own_chemical_items')
    ):
        q |= Q(ordered_by=emp)
    if user.has_perm('chemicals.view_workgroup_chemical_items') or user.has_perm('chemicals.manage_workgroup_chemical_items'):
        wg_ids = user_workgroup_ids(user)
        if wg_ids:
            q |= Q(workgroup_id__in=wg_ids)
    if q == Q():
        return qs.none()
    return qs.filter(q).distinct()


def filter_chemicals_for_user(qs, user):
    if not user or not user.is_authenticated:
        return qs.none()
    if user.is_superuser or user.has_perm('chemicals.view_all_chemicals') or user.has_perm('chemicals.manage_all_chemicals'):
        return qs
    from apps.chemicals.models import ChemicalItem
    item_ids = filter_chemical_items_for_user(ChemicalItem.objects.all(), user).values_list('chemical_id', flat=True)
    return qs.filter(pk__in=item_ids).distinct()


def user_can_mark_items_delivered(user) -> bool:
    """Undelivered order items view: coordinators or procurement approvers."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return (
        user.has_perm('tasks.view_all_purchase_orders')
        or user.has_perm('tasks.change_wbs_on_purchase_order')
        or user.has_perm('tasks.approve_purchase_order')
    )
