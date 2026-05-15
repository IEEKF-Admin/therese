"""
apps/accounts/apps.py

Project: THERESE - Transparent HR Employee Resource Evaluation System Enhanced

Features / Requirements:
- Registers signals for automatic password_changed flag handling
- Header block must be maintained and only extended when new requirements are explicitly added
"""

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.accounts'
    verbose_name = "Accounts"

    def ready(self):
        import apps.accounts.signals   # Register signals
