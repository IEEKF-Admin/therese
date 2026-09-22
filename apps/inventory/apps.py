from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _assign_inventory_permissions(sender, **kwargs):
    try:
        from apps.accounts.permissions import assign_permissions_to_groups
        assign_permissions_to_groups()
    except Exception:
        pass


class InventoryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.inventory'
    label = 'inventory'
    verbose_name = 'Inventory'

    def ready(self):
        post_migrate.connect(_assign_inventory_permissions, sender=self)
