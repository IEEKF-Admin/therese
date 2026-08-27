"""Permission helpers for process checklists."""

from django.db.models import Q

from apps.checklists.models import (
    ChecklistAssignmentAck,
    ChecklistEditorArchive,
    ChecklistEditorSeen,
    ChecklistInstance,
    ChecklistTemplateNode,
)


def user_can_manage(user):
    if not user.is_authenticated:
        return False
    return user.is_superuser or user.has_perm('checklists.manage_checklist')


def _user_employee(user):
    return getattr(user, 'employee', None)


def _user_workgroup_ids(user):
    employee = _user_employee(user)
    if not employee:
        return set()
    return set(employee.workgroups.values_list('pk', flat=True))


def user_can_view_instance_readonly(user, instance):
    if not user.is_authenticated:
        return False
    if user_can_manage(user):
        return True
    employee = _user_employee(user)
    if employee and instance.subject_id == employee.pk:
        return True
    if user.has_perm('checklists.view_institute_progress'):
        return user.has_perm('checklists.view_checklist')
    if user.has_perm('checklists.view_workgroup_progress') and user.has_perm('checklists.view_checklist'):
        subject_wg_ids = set(instance.subject.workgroups.values_list('pk', flat=True))
        if subject_wg_ids & _user_workgroup_ids(user):
            return True
    if user_can_edit_any_node(user, instance):
        return True
    if _user_has_editor_match(user, instance):
        return True
    return False


def _user_has_editor_match(user, instance):
    if not user.is_authenticated:
        return False
    nodes = instance.template_version.nodes.filter(
        node_kind=ChecklistTemplateNode.NodeKind.FIELD,
    )
    return any(_user_matches_node_editors(user, instance, node) for node in nodes)


def _user_matches_node_editors(user, instance, node):
    """Whether this user is allowed to edit the node, ignoring instance lock."""
    if user_can_manage(user) and node.editable_by_coordinators:
        return True
    user_group_ids = set(user.groups.values_list('pk', flat=True))
    if user_group_ids and node.editable_by_groups.filter(pk__in=user_group_ids).exists():
        return True
    employee = _user_employee(user)
    if not employee:
        return False
    if instance.subject_id == employee.pk and node.editable_by_subject:
        return True
    if node.editable_by_employees.filter(pk=employee.pk).exists():
        return True
    return False


def user_can_edit_node(user, instance, node):
    if not user.is_authenticated:
        return False
    if instance.is_locked or instance.status == ChecklistInstance.Status.CANCELLED:
        return False
    return _user_matches_node_editors(user, instance, node)


def user_can_edit_any_node(user, instance):
    if not user.is_authenticated or instance.is_locked:
        return False
    if instance.status == ChecklistInstance.Status.CANCELLED:
        return False
    nodes = instance.template_version.nodes.filter(
        node_kind=ChecklistTemplateNode.NodeKind.FIELD,
    )
    return any(user_can_edit_node(user, instance, node) for node in nodes)


def user_can_fill_instance(user, instance):
    if not user.is_authenticated or instance.is_locked:
        return False
    if instance.status == ChecklistInstance.Status.CANCELLED:
        return False
    employee = _user_employee(user)
    if employee and instance.subject_id == employee.pk:
        return True
    return user_can_edit_any_node(user, instance)


def subject_active_instances(user):
    employee = _user_employee(user)
    if not employee:
        return ChecklistInstance.objects.none()
    return (
        ChecklistInstance.objects.filter(
            subject=employee,
            status__in=ChecklistInstance.ACTIVE_STATUSES,
        )
        .select_related('template_version', 'template_version__template')
        .order_by('-assigned_at')
    )


def user_has_active_checklists(user):
    return (
        subject_active_instances(user).exists()
        or instances_editable_by_user(user).exists()
        or ChecklistEditorArchive.objects.filter(user=user).exists()
    )


def _editor_nodes_q(user):
    """Q for field nodes this user may edit (employee, group, or coordinator)."""
    q = Q()
    employee = _user_employee(user)
    if employee:
        q |= Q(editable_by_employees=employee)
    group_ids = list(user.groups.values_list('pk', flat=True))
    if group_ids:
        q |= Q(editable_by_groups__in=group_ids)
    if user_can_manage(user):
        q |= Q(editable_by_coordinators=True)
    return q


def instances_editable_by_user(user):
    """Active instances the user may edit, excluding those assigned to them as subject."""
    if not user or not user.is_authenticated:
        return ChecklistInstance.objects.none()
    nodes_q = _editor_nodes_q(user)
    if nodes_q == Q():
        return ChecklistInstance.objects.none()
    version_ids = (
        ChecklistTemplateNode.objects.filter(
            node_kind=ChecklistTemplateNode.NodeKind.FIELD,
        )
        .filter(nodes_q)
        .values_list('version_id', flat=True)
        .distinct()
    )
    qs = ChecklistInstance.objects.filter(
        status__in=ChecklistInstance.ACTIVE_STATUSES,
        template_version_id__in=version_ids,
    ).select_related(
        'subject', 'template_version', 'template_version__template',
    )
    employee = _user_employee(user)
    if employee:
        qs = qs.exclude(subject=employee)
    return qs.distinct()


def editor_work_complete(user, instance):
    """True when every field this user may edit on the instance is fulfilled."""
    from apps.checklists.services import field_is_fulfilled

    nodes = [
        node
        for node in instance.template_version.nodes.filter(
            node_kind=ChecklistTemplateNode.NodeKind.FIELD,
        )
        if user_can_edit_node(user, instance, node)
    ]
    if not nodes:
        return False
    responses = {
        response.node_id: response
        for response in instance.responses.filter(node__in=nodes)
    }
    return all(
        field_is_fulfilled(instance, node, responses.get(node.pk))
        for node in nodes
    )


def archive_editor_instance(user, instance):
    ChecklistEditorArchive.objects.get_or_create(user=user, instance=instance)


def sync_editor_archives(user, instances):
    """Archive instances whose editor fields are already fulfilled."""
    archived_ids = set()
    for instance in instances:
        if editor_work_complete(user, instance):
            archive_editor_instance(user, instance)
            archived_ids.add(instance.pk)
    return archived_ids


def mark_editor_seen(user, instance):
    employee = _user_employee(user)
    if employee and instance.subject_id == employee.pk:
        return
    ChecklistEditorSeen.objects.get_or_create(user=user, instance=instance)


def editor_archive_ids_for_user(user):
    return set(
        ChecklistEditorArchive.objects.filter(user=user).values_list('instance_id', flat=True)
    )


def unacked_assignments(user):
    employee = _user_employee(user)
    if not employee:
        return ChecklistInstance.objects.none()
    acked_ids = ChecklistAssignmentAck.objects.filter(user=user).values_list('instance_id', flat=True)
    return (
        ChecklistInstance.objects.filter(
            subject=employee,
            status__in=ChecklistInstance.ACTIVE_STATUSES,
        )
        .exclude(pk__in=acked_ids)
        .select_related('template_version', 'template_version__template')
        .order_by('-assigned_at')
    )


def checklists_menu_needs_attention(user):
    if not user.is_authenticated:
        return False
    if unacked_assignments(user).exists():
        return True
    editor_qs = list(
        instances_editable_by_user(user).prefetch_related(
            'template_version__nodes__editable_by_employees',
            'template_version__nodes__editable_by_groups',
            'responses',
        )
    )
    archived_ids = editor_archive_ids_for_user(user)
    newly_archived = sync_editor_archives(
        user,
        [inst for inst in editor_qs if inst.pk not in archived_ids],
    )
    open_ids = {
        inst.pk for inst in editor_qs
        if inst.pk not in archived_ids and inst.pk not in newly_archived
    }
    if not open_ids:
        return False
    seen_ids = set(
        ChecklistEditorSeen.objects.filter(
            user=user, instance_id__in=open_ids,
        ).values_list('instance_id', flat=True)
    )
    return bool(open_ids - seen_ids)


def acknowledge_instance(user, instance):
    ChecklistAssignmentAck.objects.get_or_create(user=user, instance=instance)


def get_user_first_workgroup(user):
    employee = _user_employee(user)
    if not employee:
        return None
    return employee.workgroups.order_by('short_name').first()


def get_user_workgroups_ordered(user):
    """All workgroups the user's employee belongs to, ordered by short_name."""
    employee = _user_employee(user)
    if not employee:
        return []
    return list(employee.workgroups.order_by('short_name'))


def employees_in_workgroup(workgroup):
    if not workgroup:
        return []
    return list(workgroup.members.order_by('last_name', 'first_name'))


def employees_in_user_workgroups(user):
    """
    Distinct employees who share at least one workgroup with the current user.
    Covers all of the user's workgroups (not only the first).
    """
    from apps.hr.models import Employee

    wg_ids = _user_workgroup_ids(user)
    if not wg_ids:
        return []
    return list(
        Employee.objects.filter(workgroups__in=wg_ids)
        .distinct()
        .order_by('last_name', 'first_name')
    )
