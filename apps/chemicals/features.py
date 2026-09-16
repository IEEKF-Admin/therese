"""Feature flag for the chemicals module."""

from functools import wraps

from django.core.exceptions import PermissionDenied


def chemicals_enabled():
    from apps.core.models import GlobalSetting

    return bool(getattr(GlobalSetting.get_solo(), 'chemicals_enabled', True))


def chemicals_module_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not chemicals_enabled():
            raise PermissionDenied('The chemicals module is disabled.')
        return view_func(request, *args, **kwargs)

    return wrapped
