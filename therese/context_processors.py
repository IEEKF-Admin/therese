"""
therese/context_processors.py
"""
def user_groups(request):
    """Stellt die Gruppen des aktuellen Users als Liste bereit + has_employee flag"""
    if request.user.is_authenticated:
        has_employee = hasattr(request.user, 'employee') and request.user.employee is not None
        return {
            'user_groups': list(request.user.groups.values_list('name', flat=True)),
            'has_employee': has_employee,
        }
    return {
        'user_groups': [],
        'has_employee': False,
    }


