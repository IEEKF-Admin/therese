from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _assign_finance_permissions(sender, **kwargs):
    try:
        from apps.accounts.permissions import assign_permissions_to_groups
        assign_permissions_to_groups()
    except Exception:
        pass


class FinancesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.finances'      # ← wichtig: voller Pfad
    verbose_name = "Finances"

    def ready(self):
        post_migrate.connect(_assign_finance_permissions, sender=self)


