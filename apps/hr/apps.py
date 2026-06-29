"""
apps/hr/apps.py

Project: THERESE - Transparent HR Employee Resource Evaluation System Enhanced
"""

from django.apps import AppConfig


class HrConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.hr'
    verbose_name = "HR & Employees"

    def ready(self):
        import apps.hr.signals  # Register signals