"""
therese/context_processors.py
"""
def user_groups(request):
    """Stellt die Gruppen des aktuellen Users als Liste bereit"""
    if request.user.is_authenticated:
        return {
            'user_groups': list(request.user.groups.values_list('name', flat=True))
        }
    return {'user_groups': []}


