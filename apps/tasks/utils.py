"""
apps/tasks/utils.py

Permission helpers, visibility rules, and status logic for the tasks app.

Permission matrix (purchase orders)
-----------------------------------
Roles are derived from Django auth groups / custom permissions (see GroupNames).

| Role                    | View PO                         | Edit WBS | Change status      |
|-------------------------|---------------------------------|----------|--------------------|
| Procurement coordinator | All POs                         | Yes      | Yes                |
| Procurement approver    | Own + any PO with WBS set      | No       | Yes (if WBS set)   |
| Creator (requester)     | Always own POs                  | No       | No                 |
| Assignee (fulfiller)    | Only when assignee + WBS set    | No       | No (view only*)    |

* Fulfiller detail view allows status updates via form when user is assignee;
  can_change_status() is used for coordinator/approver field enablement.

Permission matrix (personnel / recruitment)
-------------------------------------------
| Role                         | View              | Edit fields        | Edit status        |
|------------------------------|-------------------|--------------------|--------------------|
| Personnel coordinator        | All               | Yes                | Yes                |
| Personnel approver (assignee)| When assignee     | No                 | Forward-only       |
| Creator                      | Own tasks         | While not_yet_*    | No                 |
| Creator + coordinator fallback | Own tasks       | Yes (coordinator)  | Yes (coordinator)  |

Coordinator fallback (workflow_config.creator_has_coordinator_fallback)
-----------------------------------------------------------------------
When no TaskWorkflowCoordinator rows exist for the task's creator_workgroup and
task_type, the creator temporarily acts as coordinator (assignee, status, WBS-like
steps). This keeps workflows usable before HR configures coordinators per workgroup.
"""

from django.db.models import Q
from .models import PurchaseOrderTask, RECRUITMENT_STATUSES, RECRUITMENT_STATUS_ORDER
from .workflow_config import creator_has_coordinator_fallback
from apps.accounts.permissions import GroupNames


def employees_in_group(group_name):
    """Return active employees whose user belongs to the given auth group."""
    from apps.hr.models import Employee

    return Employee.objects.filter(
        user__is_active=True,
        user__groups__name=group_name,
    ).order_by('last_name', 'first_name').distinct()


def procurement_approver_employees():
    """Employees in the procurement approval rights group."""
    return employees_in_group(GroupNames.PROCUREMENT_APPROVAL_RIGHTS)


def personnel_approver_employees():
    """Employees in the personnel approval rights group."""
    return employees_in_group(GroupNames.PERSONNEL_APPROVAL_RIGHTS)


def is_procurement_coordinator(user):
    """True if user may coordinate all purchase orders (WBS, assignee, status)."""
    if not user or not user.is_authenticated:
        return False
    return (
        user.is_superuser
        or user.has_perm('tasks.view_all_purchase_orders')
        or user.has_perm('tasks.change_wbs_on_purchase_order')
    )


def is_procurement_approver(user):
    """True if user may approve POs after a coordinator sets the WBS element."""
    if not user or not user.is_authenticated:
        return False
    return user.is_superuser or user.has_perm('tasks.approve_purchase_order')


def is_personnel_coordinator(user):
    """True if user may view and edit all personnel tasks."""
    if not user or not user.is_authenticated:
        return False
    return user.is_superuser or user.has_perm('tasks.view_all_personnel_tasks')


def is_personnel_approver(user):
    """True if user may advance personnel/recruitment status when assigned."""
    if not user or not user.is_authenticated:
        return False
    return user.is_superuser or user.has_perm('tasks.approve_personnel_task')


def can_view_purchase_order(user, task):
    """
    Decide whether *user* may open the purchase order detail view.

    Visibility rules:
    - Coordinators: all POs.
    - Creators: always their own POs (even before WBS is set).
    - Approvers: own POs plus any PO where wbs_element is set.
    - Everyone else: only if they are assignee and WBS is set.
    """
    if not user or not user.is_authenticated:
        return False

    employee = getattr(user, 'employee', None)
    if not employee:
        return False

    if is_procurement_coordinator(user):
        return True

    # Creators always see their own purchase orders.
    if task.creator == employee:
        return True

    if is_procurement_approver(user):
        # Approvers see POs as soon as a WBS element exists (any assignee).
        if task.wbs_element_id is not None:
            return True
    else:
        # Non-approvers only when they are assignee and WBS is set.
        if task.assignee == employee and task.wbs_element_id is not None:
            return True

    return False


def get_purchase_orders_queryset(user):
    """
    Central queryset for purchase orders visible on the dashboard.

    Mirrors can_view_purchase_order() but expressed as Q objects for filtering.
    """
    if not user or not user.is_authenticated:
        return PurchaseOrderTask.objects.none()

    employee = getattr(user, 'employee', None)
    if not employee:
        return PurchaseOrderTask.objects.none()

    queryset = PurchaseOrderTask.objects.select_related(
        'assignee', 'creator', 'wbs_element'
    ).order_by('-created_at')

    if is_procurement_coordinator(user):
        return queryset

    # Everyone always sees POs they created.
    visible = Q(creator=employee)

    if is_procurement_approver(user):
        # Approvers additionally see all POs with a WBS element.
        visible |= Q(wbs_element__isnull=False)
    else:
        # Fulfiller / requester path: assignee + WBS required.
        visible |= Q(
            assignee=employee,
            wbs_element__isnull=False,
        )

    return queryset.filter(visible)


def can_change_status(user, task):
    """PO status changes: coordinators always; approvers only after WBS is set."""
    if is_procurement_coordinator(user):
        return True
    if is_procurement_approver(user):
        return task.wbs_element_id is not None
    return False


def can_edit_wbs_element(user):
    """Only procurement coordinators may set or change the WBS element."""
    return is_procurement_coordinator(user)


def can_view_personnel_task(user, task):
    """
    Visibility for recruitment / reallocation / contract extension tasks.

    Coordinators and superusers see all; creators see own; approvers see when assignee.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser or is_personnel_coordinator(user):
        return True
    employee = getattr(user, 'employee', None)
    if not employee:
        return False
    if task.creator_id == employee.pk:
        return True
    if is_personnel_approver(user) and task.assignee_id == employee.pk:
        return True
    return False


def can_view_recruitment_task(user, task):
    """Recruitment task visibility (alias of can_view_personnel_task)."""
    return can_view_personnel_task(user, task)


def can_edit_recruitment_fields(user, task):
    """
    Recruitment form fields (candidate data, documents, funding).

    Coordinators and creator-with-fallback may edit anytime.
    Creators may edit only while status is not_yet_processed.
    """
    employee = getattr(user, 'employee', None)
    if not employee:
        return False
    if user.is_superuser or is_personnel_coordinator(user):
        return True
    if creator_has_coordinator_fallback(user, task):
        return True
    if task.creator == employee and task.status == 'not_yet_processed':
        return True
    return False


def can_edit_recruitment_status(user, task):
    """
    Recruitment status dropdown.

    Coordinators, creator fallback, and assigned approvers may change status.
    """
    employee = getattr(user, 'employee', None)
    if not employee:
        return False
    if user.is_superuser or is_personnel_coordinator(user):
        return True
    if creator_has_coordinator_fallback(user, task):
        return True
    if is_personnel_approver(user) and task.assignee == employee:
        return True
    return False


def get_recruitment_status_choices(user, task):
    """
    Status choices shown in the recruitment form.

    Coordinators / fallback: full list.
    Approvers (assignee): only statuses strictly after the current one.
    Others: empty list.
    """
    choices = list(RECRUITMENT_STATUSES)
    if user.is_superuser or is_personnel_coordinator(user) or creator_has_coordinator_fallback(user, task):
        return choices
    if is_personnel_approver(user) and getattr(user, 'employee', None) == task.assignee:
        try:
            current_index = RECRUITMENT_STATUS_ORDER.index(task.status)
        except ValueError:
            return choices
        return [
            choice
            for choice in choices
            if RECRUITMENT_STATUS_ORDER.index(choice[0]) > current_index
        ]
    return []


def can_create_employee_from_recruitment(user, task):
    """
    Final step: create HR Employee record from recruitment when status is
    sent_to_administration and user is the assigned personnel approver.
    """
    employee = getattr(user, 'employee', None)
    if not employee or task.created_employee_id:
        return False
    if not (user.is_superuser or is_personnel_approver(user)):
        return False
    return task.assignee == employee and task.status == 'sent_to_administration'


def can_create_purchase_order(user):
    """
    Users allowed to create purchase orders.

    This permission also gates access to the Standard Orders catalog during PO creation.
    """
    if not user or not user.is_authenticated:
        return False

    return (
        user.is_superuser
        or user.has_perm('tasks.create_purchase_order')
        or user.has_perm('tasks.view_all_purchase_orders')
    )