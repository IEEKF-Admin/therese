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

        # Automatische Erstellung der Custom Groups nach jeder Migration
        from django.db.models.signals import post_migrate
        from apps.accounts.permissions import (
    get_or_create_default_groups,
    assign_permissions_to_groups,
)

        def create_groups_after_migrate(sender, **kwargs):
            # Accounts- oder Tasks-Migrationen können neue Permissions anlegen
            if sender.name in ('apps.accounts', 'apps.tasks'):
                print(f"[Accounts] Running group/permission setup after {sender.name} migrate...")
                get_or_create_default_groups()
                assign_permissions_to_groups()

        post_migrate.connect(create_groups_after_migrate, sender=self)

        # Hinweis: Bei 'No migrations to apply' (kein post_migrate für accounts) auf Prod:
        #   python manage.py ensure_groups


