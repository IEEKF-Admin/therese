"""
Management command: python manage.py ensure_groups

Forces creation of the new view-specific permission groups,
assigns the required permissions to them, and removes legacy groups.

Use this on production after deploy when "No migrations to apply"
(prevents post_migrate from running the setup).
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group

from apps.accounts.permissions import (
    get_or_create_default_groups,
    assign_permissions_to_groups,
    audit_groups_and_permissions,
)


class Command(BaseCommand):
    help = "Ensure new groups exist, old groups are cleaned up, and permissions assigned."

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("Ensuring default groups and permissions..."))

        created = get_or_create_default_groups()
        assign_permissions_to_groups()

        groups = sorted(g.name for g in Group.objects.all())
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Vorhandene Gruppen ({len(groups)}):"))
        for gname in groups:
            self.stdout.write(f" - {gname}")
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Gesamt: {len(groups)}"))
        self.stdout.write("")
        audit_groups_and_permissions()
        self.stdout.write(self.style.SUCCESS("Fertig."))
