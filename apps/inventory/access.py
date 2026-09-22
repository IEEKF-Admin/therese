"""Permission helpers for inventory items."""


def user_can_view_inventory(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return (
        user.has_perm('inventory.view_own_inventory_items')
        or user.has_perm('inventory.view_all_inventory_items')
        or user.has_perm('inventory.manage_inventory_items')
    )


def user_can_view_all_inventory(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return (
        user.has_perm('inventory.view_all_inventory_items')
        or user.has_perm('inventory.manage_inventory_items')
    )


def user_can_manage_inventory(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.has_perm('inventory.manage_inventory_items')


def filter_items_for_user(queryset, user):
    if user_can_view_all_inventory(user):
        return queryset
    employee = getattr(user, 'employee', None)
    if employee and user.has_perm('inventory.view_own_inventory_items'):
        return queryset.filter(current_holder=employee)
    return queryset.none()
