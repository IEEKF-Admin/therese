"""
apps/tasks/workflow_config.py

Per-workgroup coordinator configuration for task routing.

Each workgroup can have one or more employees assigned as coordinators for each
task type (purchase order, personnel variants, generic text). The detail router
(views/router.py) uses these assignments to decide which view a user sees.

When no coordinators are configured for a task's creator_workgroup + task_type,
the task creator acts as coordinator via creator_has_coordinator_fallback() —
see utils.py for how that affects permissions.

Eligible coordinators are restricted by auth group:
- purchase_order → PROCUREMENT_COORDINATION_RIGHTS
- personnel_*     → PERSONNEL_COORDINATION_RIGHTS
- generic_text    → union of both coordination groups
"""

from django.db.models import Q

from apps.accounts.permissions import GroupNames
from apps.hr.models import Employee

# Task types handled by the personnel detail view and personnel coordinator pool.
PERSONNEL_TASK_TYPES = frozenset({
    'personnel_reallocation',
    'personnel_contract_extension',
    'personnel_recruitment',
})


def resolve_creator_workgroup(employee):
    """
    Return the workgroup fixed on the task at creation time.

    Uses the employee's first workgroup (ordered by short_name) as the snapshot
    stored on Task.creator_workgroup. None if the employee has no workgroup.
    """
    if not employee:
        return None
    return employee.workgroups.order_by('short_name').first()


def coordination_eligible_employees(task_type):
    """
    Employees that may be selected as workflow coordinators for *task_type*.

    Eligibility is enforced in the admin/UI config form and again when saving
    POST data (save_workflow_coordinators_from_post).
    """
    from apps.tasks.utils import employees_in_group

    if task_type == 'purchase_order':
        return employees_in_group(GroupNames.PROCUREMENT_COORDINATION_RIGHTS)
    if task_type in PERSONNEL_TASK_TYPES:
        return employees_in_group(GroupNames.PERSONNEL_COORDINATION_RIGHTS)
    if task_type == 'generic_text':
        return Employee.objects.filter(
            user__is_active=True,
        ).filter(
            Q(user__groups__name=GroupNames.PERSONNEL_COORDINATION_RIGHTS)
            | Q(user__groups__name=GroupNames.PROCUREMENT_COORDINATION_RIGHTS)
        ).order_by('last_name', 'first_name').distinct()
    return Employee.objects.none()


def get_workflow_coordinators(workgroup, task_type):
    """Active coordinator employees assigned to workgroup + task_type."""
    from apps.tasks.models import TaskWorkflowCoordinator

    if not workgroup:
        return Employee.objects.none()
    return Employee.objects.filter(
        task_workflow_coordinator_assignments__workgroup=workgroup,
        task_workflow_coordinator_assignments__task_type=task_type,
    ).order_by('last_name', 'first_name').distinct()


def has_workflow_coordinators(workgroup, task_type):
    """True if at least one TaskWorkflowCoordinator row exists for the pair."""
    if not workgroup:
        return False
    from apps.tasks.models import TaskWorkflowCoordinator

    return TaskWorkflowCoordinator.objects.filter(
        workgroup=workgroup,
        task_type=task_type,
    ).exists()


def creator_has_coordinator_fallback(user, task):
    """
    True when the task creator must perform coordinator steps.

    Conditions (all required):
    - user is authenticated with an employee profile
    - user is the task creator
    - no coordinators configured for task.creator_workgroup + task.task_type

    If creator_workgroup is missing, fallback is enabled so ungrouped creators
    are not blocked from progressing their tasks.
    """
    employee = getattr(user, 'employee', None)
    if not employee or not task or task.creator_id != employee.id:
        return False
    workgroup = task.creator_workgroup
    if not workgroup:
        return True
    return not has_workflow_coordinators(workgroup, task.task_type)


def _post_value_list(post_data, field_name):
    """Normalize single or multi-value POST fields to a list of strings."""
    if hasattr(post_data, 'getlist'):
        return post_data.getlist(field_name)
    value = post_data.get(field_name, [])
    if isinstance(value, list):
        return value
    if value in (None, ''):
        return []
    return [value]


def save_workflow_coordinators_from_post(workgroup, post_data):
    """
    Sync TaskWorkflowCoordinator rows from a workgroup config form POST.

    For each task type:
    - Remove coordinators no longer selected
    - Create rows for newly selected eligible employees
    - Ignore IDs that are not in coordination_eligible_employees()
    """
    from apps.tasks.models import Task, TaskWorkflowCoordinator

    for task_type, _label in Task.TASK_TYPES:
        field_name = f'coordinators_{task_type}'
        selected_ids = {
            int(value)
            for value in _post_value_list(post_data, field_name)
            if str(value).isdigit()
        }
        eligible_ids = set(
            coordination_eligible_employees(task_type).values_list('pk', flat=True)
        )
        valid_ids = selected_ids & eligible_ids

        TaskWorkflowCoordinator.objects.filter(
            workgroup=workgroup,
            task_type=task_type,
        ).exclude(coordinator_id__in=valid_ids).delete()

        existing_ids = set(
            TaskWorkflowCoordinator.objects.filter(
                workgroup=workgroup,
                task_type=task_type,
            ).values_list('coordinator_id', flat=True)
        )
        for coordinator_id in valid_ids - existing_ids:
            TaskWorkflowCoordinator.objects.create(
                workgroup=workgroup,
                task_type=task_type,
                coordinator_id=coordinator_id,
            )


def workflow_config_context_for_workgroup(workgroup):
    """
    Template context for the workgroup workflow configuration page.

    Returns config_rows: one dict per task type with eligible employees and
    currently selected coordinator primary keys.
    """
    from apps.tasks.models import Task

    config_rows = []
    for task_type, label in Task.TASK_TYPES:
        config_rows.append({
            'task_type': task_type,
            'label': label,
            'eligible': coordination_eligible_employees(task_type),
            'selected_ids': set(
                get_workflow_coordinators(workgroup, task_type).values_list('pk', flat=True)
            ),
        })
    return {'config_rows': config_rows}