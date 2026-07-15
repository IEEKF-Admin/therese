from django.apps import AppConfig


class ChecklistsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.checklists'
    verbose_name = 'Process Checklists'

    def ready(self):
        import apps.checklists.admin  # noqa: F401
