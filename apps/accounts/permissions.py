"""
apps/accounts/permissions.py

Central definition of all custom groups in the system.

Benefits:
- Single place where group names are defined
- Prevents typos in string comparisons
- Enables automatic creation after migrations
"""

from django.contrib.auth.models import Group, Permission


class GroupNames:
    """View- and function-specific groups (permission-based)."""

    # Baseline role for all institute staff (login + order + read docs)
    EMPLOYEE = "Employee"
    # Principal Investigator: Employee baseline + personnel create, docs manage, WG checklist progress
    PI = "PI"

    # Granular employee / PSP bundles (still useful next to Assistant roles)
    EMPLOYEES_MANAGE = "Employees - Manage"
    EMPLOYEES_MANAGE_ALL = "Employees - Manage All"
    PSP_ELEMENTS_MANAGE = "PSP Elements - Manage"
    PSP_ELEMENTS_MANAGE_ALL = "PSP Elements - Manage All"

    CONTACT_PERSONS_VIEW = "Contact Persons - View"
    CONTACT_PERSONS_MANAGE = "Contact Persons - Manage"

    PURCHASE_ORDERS_CREATE = "Purchase Orders - Create"
    STANDARD_ORDERS_VIEW = "Standard Orders - View"
    STANDARD_ORDERS_MANAGE = "Standard Orders - Manage"
    PROCUREMENT_COORDINATION_RIGHTS = "Procurement - Coordination Rights"
    PROCUREMENT_APPROVAL_RIGHTS = "Procurement - Approval Rights"

    PERSONNEL_TASKS_CREATE = "Personnel Tasks - Create"
    PERSONNEL_COORDINATION_RIGHTS = "Personnel - Coordination Rights"
    PERSONNEL_APPROVAL_RIGHTS = "Personnel - Approval Rights"

    DOCUMENTS_MANAGE = "Documents & SOPs - Manage"

    # Domain assistants (workgroup-scoped where applicable) and superassistants (institute-wide)
    HR_ASSISTANT = "HR - Assistant"
    HR_SUPERASSISTANT = "HR - Superassistant"
    FINANCES_ASSISTANT = "Finances - Assistant"
    FINANCES_SUPERASSISTANT = "Finances - Superassistant"
    DOCUMENTS_ASSISTANT = "Documents - Assistant"
    DOCUMENTS_SUPERASSISTANT = "Documents - Superassistant"

    CHECKLISTS_MANAGE = "Checklists - Manage"
    CHECKLISTS_WORKGROUP_PROGRESS = "Checklists - Workgroup Progress"
    CHECKLISTS_INSTITUTE_PROGRESS = "Checklists - Institute Progress"


# All groups as a list (useful for iteration)
NEW_GROUPS = [
    GroupNames.EMPLOYEE,
    GroupNames.PI,
    GroupNames.EMPLOYEES_MANAGE,
    GroupNames.EMPLOYEES_MANAGE_ALL,
    GroupNames.PSP_ELEMENTS_MANAGE,
    GroupNames.PSP_ELEMENTS_MANAGE_ALL,
    GroupNames.CONTACT_PERSONS_VIEW,
    GroupNames.CONTACT_PERSONS_MANAGE,
    GroupNames.PURCHASE_ORDERS_CREATE,
    GroupNames.STANDARD_ORDERS_VIEW,
    GroupNames.STANDARD_ORDERS_MANAGE,
    GroupNames.PROCUREMENT_COORDINATION_RIGHTS,
    GroupNames.PROCUREMENT_APPROVAL_RIGHTS,
    GroupNames.PERSONNEL_TASKS_CREATE,
    GroupNames.PERSONNEL_COORDINATION_RIGHTS,
    GroupNames.PERSONNEL_APPROVAL_RIGHTS,
    GroupNames.DOCUMENTS_MANAGE,
    GroupNames.HR_ASSISTANT,
    GroupNames.HR_SUPERASSISTANT,
    GroupNames.FINANCES_ASSISTANT,
    GroupNames.FINANCES_SUPERASSISTANT,
    GroupNames.DOCUMENTS_ASSISTANT,
    GroupNames.DOCUMENTS_SUPERASSISTANT,
    GroupNames.CHECKLISTS_MANAGE,
    GroupNames.CHECKLISTS_WORKGROUP_PROGRESS,
    GroupNames.CHECKLISTS_INSTITUTE_PROGRESS,
]

# Groups removed from the system (deleted by ensure_groups / post_migrate).
# Before delete, each member receives the group's permissions as user_permissions.
OLD_GROUPS = [
    # "PI" is a current standard group (GroupNames.PI) — do not list here.
    "Assisting Admins",
    "Employees - View",
    "Employees - View All",
    "PSP Elements - View",
    "PSP Elements - View All",
    "Working Groups - Manage",
    "Locations - Manage",
    "Cost Centers - Manage",
    "Documents & SOPs - View",
    # Permissions remain; assign via Admin → user_permissions or Superassistant roles
    "Pay Scales - Import",
    "Third-party Funding Reports - Import",
    "General Requests - Create",
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


def _preserve_permissions_from_deprecated_groups():
    """
    Before deleting OLD_GROUPS, copy each group's permissions onto its members
    as direct user_permissions so access is not silently lost.
    """
    preserved_users = 0
    for name in OLD_GROUPS:
        try:
            group = Group.objects.get(name=name)
        except Group.DoesNotExist:
            continue
        perms = list(group.permissions.all())
        if not perms:
            continue
        for user in group.user_set.all():
            before = user.user_permissions.count()
            user.user_permissions.add(*perms)
            if user.user_permissions.count() > before:
                preserved_users += 1
    if preserved_users:
        print(
            f"  [Groups] Preserved permissions on {preserved_users} user assignment(s) "
            f"before removing deprecated groups."
        )


def get_or_create_default_groups():
    """
    Creates the new groups and removes the old, obsolete groups.
    Called automatically after each migration (post_migrate signal).
    On production when 'No migrations to apply', run instead:
        python manage.py ensure_groups
    """
    created_groups = []

    # Create new groups
    for group_name in NEW_GROUPS:
        group, created = Group.objects.get_or_create(name=group_name)
        if created:
            created_groups.append(group_name)
            print(f"  [Groups] Created group: {group_name}")

    if created_groups:
        print(f"  [Groups] {len(created_groups)} new groups created.")

    # Keep access for users still only on groups we are about to delete
    _preserve_permissions_from_deprecated_groups()

    # Remove old groups (even if users are assigned - they lose the old group)
    deleted = []
    for name in OLD_GROUPS:
        try:
            g = Group.objects.get(name=name)
            user_count = g.user_set.count()
            g.delete()
            deleted.append(name)
            if user_count > 0:
                print(
                    f"  [Groups] Removed old group: {name} "
                    f"(had {user_count} users - group membership removed; "
                    f"permissions preserved on user where possible)"
                )
            else:
                print(f"  [Groups] Removed old group: {name}")
        except Group.DoesNotExist:
            pass

    if deleted:
        print(f"  [Groups] Removed {len(deleted)} old groups.")

    return created_groups


def user_can_assist(user):
    """True if user has any assistant/superassistant management permission."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    management_perms = [
        'hr.manage_employee',
        'hr.manage_all_employees',
        'hr.manage_working_group',
        'hr.manage_location',
        'finances.manage_psp_element',
        'finances.manage_all_psp_elements',
        'finances.manage_cost_center',
        'documents.manage_document',
    ]
    return any(user.has_perm(perm) for perm in management_perms)


def user_is_hr_superassistant(user):
    """
    Institute-wide HR admin tools (jobs, limitation reasons, login popup, workflow).
    Superusers and members of HR - Superassistant.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name=GroupNames.HR_SUPERASSISTANT).exists()


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
    from apps.finances.models import ContactPerson, CostCenter, WBSElement, PayScale
    from apps.tasks.models import PurchaseOrderTask, StandardPurchaseItem, Task
    from apps.documents.models import Document
    from apps.checklists.models import ChecklistTemplate

    # Ensure groups exist first (in case assign is called standalone)
    get_or_create_default_groups()

    missing_permissions = []

    def get_perm(codename, model):
        try:
            ct = ContentType.objects.get_for_model(model)
            return Permission.objects.get(codename=codename, content_type=ct)
        except Exception:
            missing_permissions.append(f"{model._meta.label}.{codename}")
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

    # Employees (workgroup-scoped vs institute-wide)
    view_emp = get_perm("can_view_employees", Employee)
    manage_emp = get_perm("manage_employee", Employee)
    view_all_emp = get_perm("can_view_all_employees", Employee)
    manage_all_emp = get_perm("manage_all_employees", Employee)
    safe_add(GroupNames.EMPLOYEES_MANAGE, view_emp, manage_emp)
    safe_add(GroupNames.EMPLOYEES_MANAGE_ALL, view_emp, manage_emp, view_all_emp, manage_all_emp)

    # PSP (workgroup-scoped vs institute-wide)
    view_overview = get_perm("view_psp_overview", WBSElement)
    view_psp = get_perm("view_psp_element", WBSElement)
    manage_psp = get_perm("manage_psp_element", WBSElement)
    view_all_psp = get_perm("view_all_psp_elements", WBSElement)
    manage_all_psp = get_perm("manage_all_psp_elements", WBSElement)
    safe_add(GroupNames.PSP_ELEMENTS_MANAGE, view_overview, view_psp, manage_psp)
    safe_add(
        GroupNames.PSP_ELEMENTS_MANAGE_ALL,
        view_overview, view_psp, manage_psp, view_all_psp, manage_all_psp,
    )

    # Cost Centers / locations / workgroups (used by Superassistants; no dedicated groups)
    manage_cc = get_perm("manage_cost_center", CostCenter)
    manage_wg = get_perm("manage_working_group", Workgroup)
    manage_loc = get_perm("manage_location", Building)

    # Contact Persons
    view_contacts = get_perm("view_contact_person_list", ContactPerson)
    manage_contacts = get_perm("manage_contact_person", ContactPerson)
    safe_add(GroupNames.CONTACT_PERSONS_VIEW, view_contacts)
    safe_add(GroupNames.CONTACT_PERSONS_MANAGE, view_contacts, manage_contacts)

    # Procurement
    create_po = get_perm("create_purchase_order", PurchaseOrderTask)
    view_all_po = get_perm("view_all_purchase_orders", PurchaseOrderTask)
    change_wbs = get_perm("change_wbs_on_purchase_order", PurchaseOrderTask)
    view_std = get_perm("view_standard_order", StandardPurchaseItem)
    manage_std = get_perm("manage_standard_order", StandardPurchaseItem)
    approve_po = get_perm("approve_purchase_order", PurchaseOrderTask)
    safe_add(GroupNames.PURCHASE_ORDERS_CREATE, create_po)
    safe_add(GroupNames.STANDARD_ORDERS_VIEW, view_std)
    safe_add(GroupNames.STANDARD_ORDERS_MANAGE, view_std, manage_std)
    safe_add(GroupNames.PROCUREMENT_COORDINATION_RIGHTS, view_all_po, change_wbs, manage_std)
    safe_add(GroupNames.PROCUREMENT_APPROVAL_RIGHTS, approve_po)

    # Documents
    view_doc = get_perm("view_document", Document)
    manage_doc = get_perm("manage_document", Document)

    # Baseline for all staff: place orders + read documents
    safe_add(
        GroupNames.EMPLOYEE,
        create_po,
        view_std,
        view_doc,
    )

    # Personnel (create/coordinate/approve — import/general-request are user_permissions only)
    create_personnel = get_perm("create_personnel_task", PurchaseOrderTask)
    view_all_personnel = get_perm("view_all_personnel_tasks", Task)
    approve_personnel = get_perm("approve_personnel_task", Task)
    # Resolve import/general-request perms so missing-perm warnings still surface
    get_perm("import_pay_scale", PayScale)
    get_perm("import_third_party_funding_report", WBSElement)
    get_perm("create_general_request", PurchaseOrderTask)
    safe_add(GroupNames.PERSONNEL_TASKS_CREATE, create_personnel)
    safe_add(GroupNames.PERSONNEL_COORDINATION_RIGHTS, view_all_personnel)
    safe_add(GroupNames.PERSONNEL_APPROVAL_RIGHTS, approve_personnel)

    # Documents & SOPs (legacy manage bundle + assistant roles)
    safe_add(GroupNames.DOCUMENTS_MANAGE, view_doc, manage_doc)

    # Checklists
    view_cl = get_perm('view_checklist', ChecklistTemplate)
    manage_cl = get_perm('manage_checklist', ChecklistTemplate)
    wg_cl = get_perm('view_workgroup_progress', ChecklistTemplate)
    inst_cl = get_perm('view_institute_progress', ChecklistTemplate)
    safe_add(GroupNames.CHECKLISTS_MANAGE, manage_cl, view_cl)
    safe_add(GroupNames.CHECKLISTS_WORKGROUP_PROGRESS, view_cl, wg_cl)
    safe_add(GroupNames.CHECKLISTS_INSTITUTE_PROGRESS, view_cl, inst_cl)

    # PI: Employee baseline + personnel create + docs manage + workgroup checklist progress
    safe_add(
        GroupNames.PI,
        create_po,
        view_std,
        view_doc,
        create_personnel,
        manage_doc,
        view_cl,
        wg_cl,
    )

    # HR Assistant: workgroup-scoped employee view/manage
    safe_add(GroupNames.HR_ASSISTANT, view_emp, manage_emp)

    # HR Superassistant: all employees + institute HR admin tools (WG, locations)
    safe_add(
        GroupNames.HR_SUPERASSISTANT,
        view_emp,
        manage_emp,
        view_all_emp,
        manage_all_emp,
        manage_wg,
        manage_loc,
    )

    # Finances Assistant: workgroup-scoped PSP view/manage
    safe_add(
        GroupNames.FINANCES_ASSISTANT,
        view_overview,
        view_psp,
        manage_psp,
    )

    # Finances Superassistant: all PSPs + cost centers + related procurement views
    # (Contact Persons: only via Contact Persons - View / Manage groups)
    safe_add(
        GroupNames.FINANCES_SUPERASSISTANT,
        view_overview,
        view_psp,
        manage_psp,
        view_all_psp,
        manage_all_psp,
        manage_cc,
        view_all_po,
        manage_std,
    )
    # Drop contact perms if previously assigned to this group
    try:
        g = Group.objects.get(name=GroupNames.FINANCES_SUPERASSISTANT)
        drop = [p for p in (view_contacts, manage_contacts) if p is not None]
        if drop:
            g.permissions.remove(*drop)
    except Group.DoesNotExist:
        pass

    # Documents: no workgroup scope on manage yet — both can manage
    safe_add(GroupNames.DOCUMENTS_ASSISTANT, view_doc, manage_doc)
    safe_add(GroupNames.DOCUMENTS_SUPERASSISTANT, view_doc, manage_doc)

    if assigned_count:
        print(f"  [Permissions] Assigned/updated permissions for {assigned_count} group(s).")
    else:
        print("  [Permissions] No new permission assignments (or groups/permissions not ready).")

    if missing_permissions:
        print("  [Permissions] WARNING - missing in database (run migrate first):")
        for perm in missing_permissions:
            print(f"    - {perm}")


def audit_groups_and_permissions():
    """Print group/permission state for deployment troubleshooting."""
    from apps.tasks.models import PurchaseOrderTask, Task

    print("=== Group / Permission Audit ===")
    for group_name in NEW_GROUPS:
        try:
            group = Group.objects.get(name=group_name)
        except Group.DoesNotExist:
            print(f"[MISSING GROUP] {group_name}")
            continue
        perm_names = sorted(group.permissions.values_list('codename', flat=True))
        user_count = group.user_set.count()
        print(f"[OK] {group_name}: {user_count} user(s), perms={perm_names or 'NONE'}")

    required = [
        ('tasks', 'approve_purchase_order', PurchaseOrderTask),
        ('tasks', 'view_all_personnel_tasks', Task),
        ('tasks', 'approve_personnel_task', Task),
        ('tasks', 'create_general_request', PurchaseOrderTask),
        ('finances', 'import_pay_scale', None),
        ('finances', 'import_third_party_funding_report', None),
    ]
    print("--- Required custom permissions (no dedicated groups) ---")
    for app_label, codename, model in required:
        qs = Permission.objects.filter(
            codename=codename,
            content_type__app_label=app_label,
        )
        if model is not None:
            qs = qs.filter(content_type__model=model._meta.model_name)
        status = "OK" if qs.exists() else "MISSING"
        print(f"[{status}] {app_label}.{codename}")
    print("=== End Audit ===")
