"""Permission helpers for process checklists."""

from apps.checklists.models import ChecklistAssignmentAck, ChecklistInstance, ChecklistTemplateNode


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
    return False


def user_can_fill_instance(user, instance):
    if not user.is_authenticated or instance.is_locked:
        return False
    if instance.status == ChecklistInstance.Status.CANCELLED:
        return False
    employee = _user_employee(user)
    return employee is not None and instance.subject_id == employee.pk


def user_can_edit_node(user, instance, node):
    if instance.is_locked or instance.status == ChecklistInstance.Status.CANCELLED:
        return False
    if user_can_manage(user) and node.editable_by_coordinators:
        return True
    employee = _user_employee(user)
    if not employee:
        return False
    if instance.subject_id == employee.pk and node.editable_by_subject:
        return True
    if node.editable_by_employees.filter(pk=employee.pk).exists():
        return True
    return False


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
    return subject_active_instances(user).exists()


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
    return unacked_assignments(user).exists()


def acknowledge_instance(user, instance):
    ChecklistAssignmentAck.objects.get_or_create(user=user, instance=instance)


def get_user_first_workgroup(user):
    employee = _user_employee(user)
    if not employee:
        return None
    return employee.workgroups.order_by('short_name').first()


def employees_in_workgroup(workgroup):
    if not workgroup:
        return []
    return list(workgroup.members.order_by('last_name', 'first_name'))
