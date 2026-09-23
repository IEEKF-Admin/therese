"""Access helpers for Bugs & Features."""


def user_employee(user):
    if not user or not user.is_authenticated:
        return None
    return getattr(user, 'employee', None)


def user_can_use_feedback(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user_employee(user) is not None


def user_can_manage_feedback(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.has_perm('feedback.manage_feedback')


def user_can_edit_item(user, item):
    if user_can_manage_feedback(user):
        return True
    employee = user_employee(user)
    return employee is not None and item.created_by_id == employee.pk
