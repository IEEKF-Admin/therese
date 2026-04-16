from django.apps import AppConfig

class AllocationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.allocations'   # ← Hier ändern
    verbose_name = "Allocations"
