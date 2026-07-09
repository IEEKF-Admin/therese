"""
therese/context_processors.py
"""
from apps.documents.sidebar_notifications import documents_menu_needs_attention


def user_groups(request):
    """Stellt die Gruppen des aktuellen Users als Liste bereit + has_employee flag"""
    if request.user.is_authenticated:
        has_employee = hasattr(request.user, 'employee') and request.user.employee is not None
        return {
            'user_groups': list(request.user.groups.values_list('name', flat=True)),
            'has_employee': has_employee,
            'documents_menu_needs_attention': documents_menu_needs_attention(request.user),
        }
    return {
        'user_groups': [],
        'has_employee': False,
        'documents_menu_needs_attention': False,
    }


