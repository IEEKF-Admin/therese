from django.apps import AppConfig

class ContractsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.contracts'     # ← Hier ändern
    verbose_name = "Contracts"
