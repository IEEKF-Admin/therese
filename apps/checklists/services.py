"""Business logic for process checklists."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models, transaction
from django.utils import timezone

from apps.checklists.access import user_can_edit_node
from apps.checklists.models import (
    ChecklistFieldResponse,
    ChecklistInstance,
    ChecklistTemplateNode,
    ChecklistTemplateVersion,
)
from apps.hr.document_utils import create_document_version, validate_personnel_document
from apps.hr.models import EmployeeDocumentType


def copy_version_nodes(source_version, target_version):
    """Copy the node tree from one version to another (new draft)."""
    old_nodes = list(source_version.nodes.prefetch_related('editable_by_employees').order_by('sort_order', 'pk'))
    id_map = {}

    for old in old_nodes:
        new_node = ChecklistTemplateNode.objects.create(
            version=target_version,
            parent=None,
            sort_order=old.sort_order,
            node_kind=old.node_kind,
            field_type=old.field_type,
            choice_key=old.choice_key,
            label_en=old.label_en,
            label_de=old.label_de,
            help_en=old.help_en,
            help_de=old.help_de,
            required_for_completion=old.required_for_completion,
            allow_not_applicable=old.allow_not_applicable,
            editable_by_subject=old.editable_by_subject,
            editable_by_coordinators=old.editable_by_coordinators,
            visible_to_subject=old.visible_to_subject,
            file_target=old.file_target,
            employee_document_type=old.employee_document_type,
            storage_label_en=old.storage_label_en,
            storage_label_de=old.storage_label_de,
        )
        id_map[old.pk] = new_node

    for old in old_nodes:
        if old.parent_id:
            new_node = id_map[old.pk]
            new_node.parent = id_map.get(old.parent_id)
            new_node.save(update_fields=['parent', 'updated_at'])

    for old in old_nodes:
        new_node = id_map[old.pk]
        employee_ids = list(old.editable_by_employees.values_list('pk', flat=True))
        if employee_ids:
            new_node.editable_by_employees.set(employee_ids)

    return id_map


def create_next_version(template, user, *, copy_from_version):
    next_number = (
        template.versions.aggregate(models.Max('version_number'))['version_number__max'] or 0
    ) + 1
    new_version = ChecklistTemplateVersion.objects.create(
        template=template,
        version_number=next_number,
        status=ChecklistTemplateVersion.Status.DRAFT,
        completion_mode=copy_from_version.completion_mode,
        created_by=user,
    )
    id_map = copy_version_nodes(copy_from_version, new_version)
    if copy_from_version.anchor_node_id and copy_from_version.anchor_node_id in id_map:
        new_version.anchor_node = id_map[copy_from_version.anchor_node_id]
        new_version.save(update_fields=['anchor_node', 'updated_at'])
    return new_version


def publish_version(version, user):
    if version.status != ChecklistTemplateVersion.Status.DRAFT:
        raise ValidationError('Only draft versions can be published.')
    version.status = ChecklistTemplateVersion.Status.PUBLISHED
    version.published_at = timezone.now()
    version.published_by = user
    version.save(update_fields=['status', 'published_at', 'published_by', 'updated_at'])

    version.template.versions.filter(
        status=ChecklistTemplateVersion.Status.PUBLISHED,
    ).exclude(pk=version.pk).update(status=ChecklistTemplateVersion.Status.DEPRECATED)


def assign_instance(subject, template_version, assigned_by):
    if template_version.status != ChecklistTemplateVersion.Status.PUBLISHED:
        raise ValidationError('Only published template versions can be assigned.')
    return ChecklistInstance.objects.create(
        subject=subject,
        template_version=template_version,
        status=ChecklistInstance.Status.NOT_STARTED,
        assigned_by=assigned_by,
    )


def _get_or_create_response(instance, node):
    response, _ = ChecklistFieldResponse.objects.get_or_create(
        instance=instance,
        node=node,
    )
    return response


def _sync_employee_document(instance, node, uploaded_file, user):
    if node.file_target != ChecklistTemplateNode.FileTarget.EMPLOYEE_DOCUMENT:
        return
    if not node.employee_document_type:
        return
    employee = instance.subject
    uploaded_by = getattr(user, 'employee', None)
    create_document_version(
        employee,
        node.employee_document_type,
        uploaded_file,
        uploaded_by=uploaded_by,
    )
    if node.employee_document_type == EmployeeDocumentType.SCAN_OF_CONTRACT:
        employee.scan_of_contract = uploaded_file
        employee.save(update_fields=['scan_of_contract', 'updated_at'])
    elif node.employee_document_type == EmployeeDocumentType.PROFILE_PICTURE:
        employee.profile_picture = uploaded_file
        employee.save(update_fields=['profile_picture', 'updated_at'])


def field_is_fulfilled(instance, node, response=None):
    if node.node_kind != ChecklistTemplateNode.NodeKind.FIELD:
        return True
    if response is None:
        response = instance.responses.filter(node=node).first()
    if not response:
        return False
    if response.not_applicable and node.allow_not_applicable:
        return True

    field_type = node.field_type
    if field_type == ChecklistTemplateNode.FieldType.CHECKBOX:
        return response.value_bool is True
    if field_type in (
        ChecklistTemplateNode.FieldType.TEXT,
        ChecklistTemplateNode.FieldType.TEXTAREA,
        ChecklistTemplateNode.FieldType.DATE,
    ):
        return bool((response.value_text or '').strip())
    if field_type == ChecklistTemplateNode.FieldType.RADIO_GROUP:
        return bool((response.value_choice or '').strip())
    if field_type == ChecklistTemplateNode.FieldType.FILE:
        return bool(response.file)
    return False


def compute_progress(instance):
    required_nodes = instance.template_version.nodes.filter(
        node_kind=ChecklistTemplateNode.NodeKind.FIELD,
        required_for_completion=True,
    )
    total = required_nodes.count()
    if total == 0:
        return 100, 0, 0
    responses = {
        r.node_id: r
        for r in instance.responses.filter(node__in=required_nodes)
    }
    fulfilled = sum(
        1 for node in required_nodes if field_is_fulfilled(instance, node, responses.get(node.pk))
    )
    percent = int(round(fulfilled * 100 / total))
    return percent, fulfilled, total


def _set_instance_in_progress(instance):
    if instance.status == ChecklistInstance.Status.NOT_STARTED:
        instance.status = ChecklistInstance.Status.IN_PROGRESS
        instance.save(update_fields=['status', 'updated_at'])


def complete_instance(instance, user):
    if instance.is_locked:
        raise ValidationError('This checklist is already completed and locked.')
    instance.status = ChecklistInstance.Status.COMPLETED
    instance.completed_at = timezone.now()
    instance.completed_by = user
    instance.save(update_fields=['status', 'completed_at', 'completed_by', 'updated_at'])


def try_auto_complete(instance):
    if instance.is_locked:
        return False
    version = instance.template_version
    mode = version.completion_mode

    if mode == ChecklistTemplateVersion.CompletionMode.COORDINATOR_CONFIRM:
        return False

    if mode == ChecklistTemplateVersion.CompletionMode.ANCHOR_FIELD:
        anchor = version.anchor_node
        if not anchor:
            return False
        response = instance.responses.filter(node=anchor).first()
        if field_is_fulfilled(instance, anchor, response):
            complete_instance(instance, user=None)
            return True
        return False

    _, fulfilled, total = compute_progress(instance)
    if total > 0 and fulfilled == total:
        complete_instance(instance, user=None)
        return True
    return False


@transaction.atomic
def save_field_response(user, instance, node, *, data, uploaded_file=None):
    if not user_can_edit_node(user, instance, node):
        raise PermissionDenied('You cannot edit this field.')

    if node.node_kind != ChecklistTemplateNode.NodeKind.FIELD:
        raise ValidationError('Only field nodes accept responses.')

    response = _get_or_create_response(instance, node)
    not_applicable = bool(data.get('not_applicable'))

    if not_applicable:
        if not node.allow_not_applicable:
            raise ValidationError('Not applicable is not allowed for this field.')
        response.not_applicable = True
        response.value_bool = None
        response.value_text = ''
        response.value_choice = ''
    else:
        response.not_applicable = False
        field_type = node.field_type
        if field_type == ChecklistTemplateNode.FieldType.CHECKBOX:
            response.value_bool = bool(data.get('value_bool'))
        elif field_type in (
            ChecklistTemplateNode.FieldType.TEXT,
            ChecklistTemplateNode.FieldType.TEXTAREA,
            ChecklistTemplateNode.FieldType.DATE,
        ):
            response.value_text = (data.get('value_text') or '').strip()
        elif field_type == ChecklistTemplateNode.FieldType.RADIO_GROUP:
            response.value_choice = (data.get('value_choice') or '').strip()
        elif field_type == ChecklistTemplateNode.FieldType.FILE and uploaded_file:
            validate_personnel_document(uploaded_file)
            if response.file:
                response.file.delete(save=False)
            response.file = uploaded_file
            response.original_filename = uploaded_file.name
            _sync_employee_document(instance, node, uploaded_file, user)

    response.last_changed_by = user
    response.save()
    _set_instance_in_progress(instance)
    try_auto_complete(instance)
    return response


def build_node_tree(nodes):
    """Return nested dicts: {'node': node, 'children': [...]}."""
    by_parent = {}
    for node in nodes:
        by_parent.setdefault(node.parent_id, []).append(node)
    for children in by_parent.values():
        children.sort(key=lambda n: (n.sort_order, n.pk))

    def attach(parent_id):
        return [
            {'node': node, 'children': attach(node.pk)}
            for node in by_parent.get(parent_id, [])
        ]

    return attach(None)


def responses_by_node_id(instance):
    return {r.node_id: r for r in instance.responses.select_related('node').all()}