from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _assign_holiday_permissions(sender, **kwargs):
    try:
        from apps.accounts.permissions import assign_permissions_to_groups
        assign_permissions_to_groups()
    except Exception:
        pass
    try:
        from apps.holidays.services import ensure_default_rates
        ensure_default_rates()
    except Exception:
        pass


class HolidaysConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.holidays'
    label = 'holidays'
    verbose_name = 'Holidays'

    def ready(self):
        post_migrate.connect(_assign_holiday_permissions, sender=self)
