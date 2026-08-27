"""
therese/context_processors.py
"""
from apps.checklists.access import (
    checklists_menu_needs_attention,
    user_has_active_checklists,
)
from apps.documents.sidebar_notifications import documents_menu_needs_attention
from apps.holidays.access import holidays_menu_needs_attention, user_can_approve_workgroup
from apps.holidays.features import holiday_flags


def user_groups(request):
    """Stellt die Gruppen des aktuellen Users als Liste bereit + has_employee flag"""
    if request.user.is_authenticated:
        has_employee = hasattr(request.user, 'employee') and request.user.employee is not None
        flags = holiday_flags()
        return {
            'user_groups': list(request.user.groups.values_list('name', flat=True)),
            'has_employee': has_employee,
            'documents_menu_needs_attention': documents_menu_needs_attention(request.user),
            'user_has_active_checklists': user_has_active_checklists(request.user),
            'checklists_menu_needs_attention': checklists_menu_needs_attention(request.user),
            'holiday_flags': flags,
            'holidays_menu_needs_attention': holidays_menu_needs_attention(request.user),
            'user_can_approve_holidays': flags['approval'] and user_can_approve_workgroup(request.user),
        }
    return {
        'user_groups': [],
        'has_employee': False,
        'documents_menu_needs_attention': False,
        'user_has_active_checklists': False,
        'checklists_menu_needs_attention': False,
        'holiday_flags': {'module': False, 'planning': False, 'approval': False, 'gantt': False},
        'holidays_menu_needs_attention': False,
        'user_can_approve_holidays': False,
    }
