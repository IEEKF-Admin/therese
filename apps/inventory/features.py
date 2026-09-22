from functools import wraps

from django.core.exceptions import PermissionDenied


def inventory_enabled():
    from apps.core.models import GlobalSetting

    return bool(getattr(GlobalSetting.get_solo(), 'inventory_enabled', False))


def inventory_module_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not inventory_enabled():
            raise PermissionDenied('The inventory module is disabled.')
        return view_func(request, *args, **kwargs)

    return wrapped
