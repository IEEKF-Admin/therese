"""Custom admin views for THERESE."""

from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.db.models import F
from django.template.response import TemplateResponse

from apps.accounts.models import CustomUser
from apps.accounts.permissions import NEW_GROUPS


def _ordered_groups():
    """THERESE groups first (defined order), then any other groups alphabetically."""
    groups_by_name = {group.name: group for group in Group.objects.all()}
    ordered = []
    seen = set()

    for name in NEW_GROUPS:
        group = groups_by_name.get(name)
        if group:
            ordered.append(group)
            seen.add(name)

    for group in Group.objects.order_by('name'):
        if group.name not in seen:
            ordered.append(group)

    return ordered


def _user_display_name(user):
    employee = getattr(user, 'employee', None)
    if employee:
        return employee.get_full_name()
    full_name = user.get_full_name().strip()
    return full_name or user.username


def build_user_group_matrix(include_inactive=False):
    groups = _ordered_groups()
    users_qs = (
        CustomUser.objects
        .prefetch_related('groups')
        .select_related('employee')
    )
    if not include_inactive:
        users_qs = users_qs.filter(is_active=True)

    users = list(
        users_qs.order_by(
            F('employee__last_name').asc(nulls_last=True),
            F('employee__first_name').asc(nulls_last=True),
            'last_name',
            'first_name',
            'username',
        )
    )

    rows = []
    for user in users:
        member_ids = {group.id for group in user.groups.all()}
        rows.append({
            'user': user,
            'display_name': _user_display_name(user),
            'cells': [
                {'group': group, 'is_member': group.id in member_ids}
                for group in groups
            ],
        })

    return groups, rows


def user_group_matrix_view(request):
    if not (request.user.is_staff or request.user.is_superuser):
        raise PermissionDenied

    from therese.admin import therese_admin

    include_inactive = request.GET.get('include_inactive') == '1'
    groups, rows = build_user_group_matrix(include_inactive=include_inactive)

    context = {
        **therese_admin.each_context(request),
        'title': 'User Group Matrix',
        'groups': groups,
        'rows': rows,
        'include_inactive': include_inactive,
        'user_count': len(rows),
        'group_count': len(groups),
    }
    return TemplateResponse(
        request,
        'admin/user_group_matrix.html',
        context,
    )