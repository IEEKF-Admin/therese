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
    Auf Produktion bei 'No migrations to apply' stattdessen ausführen:
        python manage.py ensure_groups
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
    # WICHTIG für Produktion: Der Block löscht die alten Gruppen.
    # Wenn du die alten Gruppen (z.B. Assisting Admins) erstmal behalten willst,
    # kommentiere den folgenden Block temporär aus.
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
    Safe to call multiple times; idempotent.
    On production after deploy when no migrations run:
        python manage.py ensure_groups
    """
    from django.contrib.contenttypes.models import ContentType
    from apps.hr.models import Employee, Workgroup, Building
    from apps.finances.models import WBSElement, PayScale
    from apps.tasks.models import PurchaseOrderTask, StandardPurchaseItem

    # Ensure groups exist first (in case assign is called standalone)
    get_or_create_default_groups()

    # Helper to get perm - returns None on failure
    def get_perm(codename, model):
        try:
            ct = ContentType.objects.get_for_model(model)
            return Permission.objects.get(codename=codename, content_type=ct)
        except Exception:
            return None

    assigned_count = 0

    def safe_add(group_name, *perms):
        nonlocal assigned_count
        try:
            g = Group.objects.get(name=group_name)
            valid_perms = [p for p in perms if p is not None]
            if valid_perms:
                g.permissions.add(*valid_perms)
                assigned_count += 1
        except Group.DoesNotExist:
            print(f"  [Permissions] Group not found (skipping): {group_name}")
        except Exception as e:
            print(f"  [Permissions] Error for group {group_name}: {e}")

    # Employees
    view_emp = get_perm("can_view_employees", Employee)
    manage_emp = get_perm("manage_employee", Employee)
    safe_add("Employees - View", view_emp)
    safe_add("Employees - Manage", view_emp, manage_emp)

    # Working Groups
    safe_add("Working Groups - Manage", get_perm("manage_working_group", Workgroup))

    # Locations
    safe_add("Locations - Manage", get_perm("manage_location", Building))

    # PSP
    view_overview = get_perm("view_psp_overview", WBSElement)
    view_psp = get_perm("view_psp_element", WBSElement)
    manage_psp = get_perm("manage_psp_element", WBSElement)
    safe_add("PSP Elements - View", view_overview)
    safe_add("PSP Elements - Manage", view_psp, manage_psp)

    # Procurement
    create_po = get_perm("create_purchase_order", PurchaseOrderTask)
    view_all_po = get_perm("view_all_purchase_orders", PurchaseOrderTask)
    change_wbs = get_perm("change_wbs_on_purchase_order", PurchaseOrderTask)
    view_std = get_perm("view_standard_order", StandardPurchaseItem)
    manage_std = get_perm("manage_standard_order", StandardPurchaseItem)
    safe_add("Purchase Orders - Create", create_po)
    safe_add("Standard Orders - View", view_std)
    safe_add("Standard Orders - Manage", view_std, manage_std)
    safe_add("Procurement - Coordination Rights", view_all_po, change_wbs, manage_std)

    # Personnel
    create_personnel = get_perm("create_personnel_task", PurchaseOrderTask)
    import_scale = get_perm("import_pay_scale", PayScale)
    safe_add("Personnel Tasks - Create", create_personnel)
    safe_add("Pay Scales - Import", import_scale)
    # Personnel - Coordination Rights intentionally left without auto-assigned perms for now

    # General Requests
    safe_add("General Requests - Create", get_perm("create_general_request", PurchaseOrderTask))

    # Assisting Admins gets the key management permissions for broad access
    safe_add(
        "Assisting Admins",
        get_perm("manage_employee", Employee),
        get_perm("manage_working_group", Workgroup),
        get_perm("manage_location", Building),
        get_perm("manage_psp_element", WBSElement),
        get_perm("view_psp_overview", WBSElement),
        get_perm("view_all_purchase_orders", PurchaseOrderTask),
        get_perm("manage_standard_order", StandardPurchaseItem),
    )

    if assigned_count:
        print(f"  [Permissions] Assigned/updated permissions for {assigned_count} group(s).")
    else:
        print("  [Permissions] No new permission assignments (or groups/permissions not ready).")

