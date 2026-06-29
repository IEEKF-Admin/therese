"""
apps/accounts/permissions.py

Zentrale Definition aller benutzerdefinierten Gruppen (Custom Groups) im System.

Vorteile:
- Einziger Ort, an dem Gruppennamen definiert sind
- Verhindert Tippfehler bei String-Vergleichen
- Ermöglicht automatische Erstellung nach Migrationen
"""

from django.contrib.auth.models import Group, Permission
from django.db.models import Q


class GroupNames:
    """Alle Custom Groups im THERESE System."""

    # === Personal / HR Rollen ===
    PI = "PI"
    PERSONNEL_COORDINATOR = "Personnel Coordinator"
    PERSONNEL_FULFILLER = "Personnel Fulfiller"
    PERSONNEL_APPROVER = "Personnel Approver"
    PERSONNEL_REQUESTER = "Personnel Requester"

    # === Procurement Rollen ===
    PROCUREMENT_REQUESTER = "Procurement Requester"
    PROCUREMENT_COORDINATOR = "Procurement Coordinator"
    PROCUREMENT_APPROVER = "Procurement Approver"

    # === Weitere Rollen ===
    ORDER_MANAGER = "Order Manager"
    INSTITUTE_ADMIN = "Institute Admin"


# Alle Gruppen als Liste (nützlich für Iterationen)
ALL_GROUPS = [
    GroupNames.PI,
    GroupNames.PERSONNEL_COORDINATOR,
    GroupNames.PERSONNEL_FULFILLER,
    GroupNames.PERSONNEL_APPROVER,
    GroupNames.PERSONNEL_REQUESTER,
    GroupNames.PROCUREMENT_REQUESTER,
    GroupNames.PROCUREMENT_COORDINATOR,
    GroupNames.PROCUREMENT_APPROVER,
    GroupNames.ORDER_MANAGER,
    GroupNames.INSTITUTE_ADMIN,
]


def get_or_create_default_groups():
    """
    Stellt sicher, dass alle definierten Gruppen existieren.
    Wird automatisch nach jeder Migration aufgerufen (post_migrate Signal).
    """
    created_groups = []

    for group_name in ALL_GROUPS:
        group, created = Group.objects.get_or_create(name=group_name)
        if created:
            created_groups.append(group_name)
            print(f"  [Groups] Created group: {group_name}")

    if created_groups:
        print(f"  [Groups] {len(created_groups)} new groups created.")

    return created_groups


# Optional: Hier könnten später auch Default-Permissions pro Gruppe vergeben werden.
# Beispiel:
# def assign_default_permissions():
#     pi_group = Group.objects.get(name=GroupNames.PI)
#     pi_group.permissions.add(...)
