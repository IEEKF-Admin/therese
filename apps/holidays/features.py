"""Feature flags for the holidays module."""


def holiday_flags():
    from apps.core.models import GlobalSetting

    setting = GlobalSetting.get_solo()
    module = bool(getattr(setting, 'holidays_enabled', True))
    if not module:
        return {
            'module': False,
            'planning': False,
            'approval': False,
            'gantt': False,
        }
    planning = bool(getattr(setting, 'holidays_planning_enabled', False))
    approval = bool(getattr(setting, 'holidays_approval_enabled', False))
    gantt = bool(getattr(setting, 'holidays_gantt_enabled', False))
    if approval or gantt:
        planning = True
    return {
        'module': True,
        'planning': planning,
        'approval': approval,
        'gantt': gantt,
    }
