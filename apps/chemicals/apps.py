from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _assign_chemical_permissions(sender, **kwargs):
    """Re-run group permission assignment after chemicals perms exist."""
    try:
        from apps.accounts.permissions import assign_permissions_to_groups
        assign_permissions_to_groups()
    except Exception:
        pass


class ChemicalsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.chemicals'
    label = 'chemicals'
    verbose_name = 'Chemicals'

    def ready(self):
        # Import signal handlers
        from . import signals  # noqa: F401
        post_migrate.connect(_assign_chemical_permissions, sender=self)
