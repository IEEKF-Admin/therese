"""
apps/accounts/permissions.py

Zentrale Definition aller benutzerdefinierten Gruppen (Custom Groups) im System.

Vorteile:
- Einziger Ort, an dem Gruppennamen definiert sind
- Verhindert Tippfehler bei String-Vergleichen
- ErmÃ¶glicht automatische Erstellung nach Migrationen
"""

from django.contrib.auth.models import Group, Permission
from django.db.models import Q


class GroupNames:
    """Neue, view- und funktionsspezifische Gruppen (Permission-basiert)."""

    EMPLOYEES_VIEW = "Employees - View"
    EMPLOYEES_MANAGE = "Employees - Manage"
    WORKING_GROUPS_MANAGE = "Working Groups - Manage"
    LOCATIONS_MANAGE = "Locations - Manage"

    PSP_ELEMENTS_VIEW = "PSP Elements - View"
    PSP_ELEMENTS_MANAGE = "PSP Elements - Manage"

    PURCHASE_ORDERS_CREATE = "Purchase Orders - Create"
    STANDARD_ORDERS_VIEW = "Standard Orders - View"
    STANDARD_ORDERS_MANAGE = "Standard Orders - Manage"
    PROCUREMENT_COORDINATION_RIGHTS = "Procurement - Coordination Rights"

    PERSONNEL_TASKS_CREATE = "Personnel Tasks - Create"
    PAY_SCALES_IMPORT = "Pay Scales - Import"
    PERSONNEL_COORDINATION_RIGHTS = "Personnel - Coordination Rights"

    GENERAL_REQUESTS_CREATE = "General Requests - Create"

    ASSISTING_ADMINS = "Assisting Admins"


# Alle Gruppen als Liste (nÃ¼tzlich fÃ¼r Iterationen)
NEW_GROUPS = [
    GroupNames.EMPLOYEES_VIEW,
    GroupNames.EMPLOYEES_MANAGE,
    GroupNames.WORKING_GROUPS_MANAGE,
    GroupNames.LOCATIONS_MANAGE,
    GroupNames.PSP_ELEMENTS_VIEW,
    GroupNames.PSP_ELEMENTS_MANAGE,
    GroupNames.PURCHASE_ORDERS_CREATE,
    GroupNames.STANDARD_ORDERS_VIEW,
    GroupNames.STANDARD_ORDERS_MANAGE,
    GroupNames.PROCUREMENT_COORDINATION_RIGHTS,
    GroupNames.PERSONNEL_TASKS_CREATE,
    GroupNames.PAY_SCALES_IMPORT,
    GroupNames.PERSONNEL_COORDINATION_RIGHTS,
    GroupNames.GENERAL_REQUESTS_CREATE,
    GroupNames.ASSISTING_ADMINS,
]

OLD_GROUPS = [
    "PI",
    "Personnel Coordinator",
    "Personnel Fulfiller",
    "Personnel Approver",
    "Personnel Requester",
    "Procurement Requester",
    "Procurement Coordinator",
    "Procurement Approver",
    "Order Manager",
    "Institute Admin",
    "Institute Leader",
    "Documents - View",
    "Documents - Manage",
]


def get_or_create_default_groups():
    """
    Erstellt die neuen Gruppen und entfernt die alten, nutzlosen Gruppen.
    Wird automatisch nach jeder Migration aufgerufen (post_migrate Signal).
    """
    created_groups = []

    # Neue Gruppen erstellen
    for group_name in NEW_GROUPS:
        group, created = Group.objects.get_or_create(name=group_name)
        if created:
            created_groups.append(group_name)
            print(f"  [Groups] Created group: {group_name}")

    if created_groups:
        print(f"  [Groups] {len(created_groups)} new groups created.")

    # Alte Gruppen entfernen (auch wenn User zugewiesen sind - sie verlieren die alte Gruppe)
    deleted = []
    for name in OLD_GROUPS:
        try:
            g = Group.objects.get(name=name)
            user_count = g.user_set.count()
            g.delete()
            deleted.append(name)
            if user_count > 0:
                print(f"  [Groups] Removed old group: {name} (had {user_count} users - assignments removed)")
            else:
                print(f"  [Groups] Removed old group: {name}")
        except Group.DoesNotExist:
            pass

    if deleted:
        print(f"  [Groups] Removed {len(deleted)} old groups.")

    return created_groups


# Optional: Hier kÃ¶nnten spÃ¤ter auch Default-Permissions pro Gruppe vergeben werden.
# Beispiel:
# def assign_default_permissions():
#     example_group = Group.objects.get(name=GroupNames.EMPLOYEES_MANAGE)
#     pi_group.permissions.add(...)


def user_can_assist(user):
    """Check if user is superuser or has management permissions for Assisting Admin areas."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    # Check for key management permissions instead of old group name
    management_perms = [
        'hr.manage_employee',
        'hr.manage_working_group',
        'hr.manage_location',
        'finances.manage_psp_element',
    ]
    return any(user.has_perm(perm) for perm in management_perms)








def assign_permissions_to_groups():
    """
    Assigns the correct permissions to the new groups.
    This should be called after groups are created (e.g. in post_migrate).
    """
    from django.contrib.contenttypes.models import ContentType
    from apps.hr.models import Employee, Workgroup, Building
    from apps.finances.models import WBSElement, PayScale
    from apps.tasks.models import PurchaseOrderTask, StandardPurchaseItem

    # Helper to get perm
    def get_perm(codename, model):
        ct = ContentType.objects.get_for_model(model)
        return Permission.objects.get(codename=codename, content_type=ct)

    try:
        # Employees
        view_emp = get_perm("can_view_employees", Employee)
        manage_emp = get_perm("manage_employee", Employee)

        g = Group.objects.get(name="Employees - View")
        g.permissions.add(view_emp)

        g = Group.objects.get(name="Employees - Manage")
        g.permissions.add(view_emp, manage_emp)

        # Working Groups
        g = Group.objects.get(name="Working Groups - Manage")
        g.permissions.add(get_perm("manage_working_group", Workgroup))

        # Locations
        g = Group.objects.get(name="Locations - Manage")
        g.permissions.add(get_perm("manage_location", Building))

        # PSP
        view_overview = get_perm("view_psp_overview", WBSElement)
        view_psp = get_perm("view_psp_element", WBSElement)
        manage_psp = get_perm("manage_psp_element", WBSElement)

        g = Group.objects.get(name="PSP Elements - View")
        g.permissions.add(view_overview)

        g = Group.objects.get(name="PSP Elements - Manage")
        g.permissions.add(view_psp, manage_psp)

        # Procurement
        create_po = get_perm("create_purchase_order", PurchaseOrderTask)
        view_all_po = get_perm("view_all_purchase_orders", PurchaseOrderTask)
        change_wbs = get_perm("change_wbs_on_purchase_order", PurchaseOrderTask)
        view_std = get_perm("view_standard_order", StandardPurchaseItem)
        manage_std = get_perm("manage_standard_order", StandardPurchaseItem)

        g = Group.objects.get(name="Purchase Orders - Create")
        g.permissions.add(create_po)

        g = Group.objects.get(name="Standard Orders - View")
        g.permissions.add(view_std)

        g = Group.objects.get(name="Standard Orders - Manage")
        g.permissions.add(view_std, manage_std)

        g = Group.objects.get(name="Procurement - Coordination Rights")
        g.permissions.add(view_all_po, change_wbs, manage_std)

        # Personnel
        create_personnel = get_perm("create_personnel_task", PurchaseOrderTask)
        import_scale = get_perm("import_pay_scale", PayScale)

        g = Group.objects.get(name="Personnel Tasks - Create")
        g.permissions.add(create_personnel)

        g = Group.objects.get(name="Pay Scales - Import")
        g.permissions.add(import_scale)

        # Personnel Coordination placeholder (no perms yet)
        # g = Group.objects.get(name="Personnel - Coordination Rights")

        # General Requests
        g = Group.objects.get(name="General Requests - Create")
        g.permissions.add(get_perm("create_general_request", PurchaseOrderTask))

        # Assisting Admins gets the key management permissions for broad access
        assisting = Group.objects.get(name="Assisting Admins")
        assisting.permissions.add(
            get_perm("manage_employee", Employee),
            get_perm("manage_working_group", Workgroup),
            get_perm("manage_location", Building),
            get_perm("manage_psp_element", WBSElement),
            get_perm("view_psp_overview", WBSElement),
            get_perm("view_all_purchase_orders", PurchaseOrderTask),
            get_perm("manage_standard_order", StandardPurchaseItem),
        )

        print("  [Permissions] Assigned permissions to new groups.")
    except Exception as e:
        print(f"  [Permissions] Could not assign all permissions yet (may need full migrate): {e}")

