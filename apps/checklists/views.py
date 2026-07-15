from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.checklists.access import (
    acknowledge_instance,
    employees_in_workgroup,
    get_user_first_workgroup,
    subject_active_instances,
    user_can_fill_instance,
    user_can_manage,
    user_can_view_instance_readonly,
)
from apps.checklists.models import (
    ChecklistFieldResponse,
    ChecklistInstance,
    ChecklistTemplate,
    ChecklistTemplateNode,
    ChecklistTemplateVersion,
)
from apps.checklists.services import (
    assign_instance,
    build_node_tree,
    complete_instance,
    compute_progress,
    create_next_version,
    publish_version,
    responses_by_node_id,
    save_field_response,
)
from apps.hr.models import Employee


def _instance_context(request, instance, *, can_edit):
    version = instance.template_version
    nodes = list(
        version.nodes.prefetch_related('editable_by_employees', 'children').order_by('sort_order', 'pk')
    )
    if can_edit:
        visible_nodes = nodes
    else:
        visible_nodes = [n for n in nodes if n.visible_to_subject or not request.user.employee or instance.subject_id != request.user.employee.pk]
    tree = build_node_tree(visible_nodes)
    percent, fulfilled, total = compute_progress(instance)
    return {
        'instance': instance,
        'template': version.template,
        'version': version,
        'tree': tree,
        'responses': responses_by_node_id(instance),
        'can_edit': can_edit,
        'progress_percent': percent,
        'progress_fulfilled': fulfilled,
        'progress_total': total,
    }


def _parse_field_post(request, instance):
    saved = 0
    field_nodes = instance.template_version.nodes.filter(
        node_kind=ChecklistTemplateNode.NodeKind.FIELD,
    )
    for node in field_nodes:
        prefix = f'field_{node.pk}'
        has_file = f'{prefix}_file' in request.FILES
        is_checkbox = node.field_type == ChecklistTemplateNode.FieldType.CHECKBOX
        if not is_checkbox and prefix not in request.POST and not has_file:
            if request.POST.get(f'{prefix}_na') != '1':
                continue
        data = {
            'not_applicable': request.POST.get(f'{prefix}_na') == '1',
            'value_bool': request.POST.get(prefix) == 'on',
            'value_text': request.POST.get(prefix, ''),
            'value_choice': request.POST.get(prefix, ''),
        }
        uploaded = request.FILES.get(f'{prefix}_file')
        try:
            save_field_response(request.user, instance, node, data=data, uploaded_file=uploaded)
            saved += 1
        except (PermissionDenied, ValidationError) as exc:
            messages.error(request, str(exc))
    return saved


@login_required
def my_list(request):
    instances = subject_active_instances(request.user)
    if not instances.exists():
        messages.info(request, 'You have no active checklists. / Sie haben keine aktiven Checklisten.')
        return redirect('tasks:my_tasks')
    for inst in instances:
        acknowledge_instance(request.user, inst)
    return render(request, 'checklists/my_list.html', {'instances': instances})


@login_required
def instance_fill(request, pk):
    instance = get_object_or_404(
        ChecklistInstance.objects.select_related(
            'subject', 'template_version', 'template_version__template',
        ),
        pk=pk,
    )
    if not user_can_fill_instance(request.user, instance):
        if user_can_view_instance_readonly(request.user, instance):
            return redirect('checklists:instance_view', pk=pk)
        return HttpResponseForbidden('Access denied.')

    acknowledge_instance(request.user, instance)

    if request.method == 'POST':
        saved = _parse_field_post(request, instance)
        if saved:
            messages.success(request, f'Saved {saved} field(s). / {saved} Feld(er) gespeichert.')
        instance.refresh_from_db()
        return redirect('checklists:instance_fill', pk=pk)

    context = _instance_context(request, instance, can_edit=True)
    return render(request, 'checklists/instance_fill.html', context)


@login_required
@permission_required('checklists.manage_checklist', raise_exception=True)
def manage_template_list(request):
    templates = ChecklistTemplate.objects.prefetch_related('versions').order_by('name_en')
    return render(request, 'checklists/manage/template_list.html', {'templates': templates})


@login_required
@permission_required('checklists.manage_checklist', raise_exception=True)
def manage_template_detail(request, pk):
    template = get_object_or_404(ChecklistTemplate, pk=pk)
    versions = template.versions.select_related('published_by', 'created_by').order_by('-version_number')

    if request.method == 'POST':
        action = request.POST.get('action')
        version_pk = request.POST.get('version_id')
        version = get_object_or_404(template.versions, pk=version_pk) if version_pk else None
        try:
            if action == 'publish' and version:
                publish_version(version, request.user)
                messages.success(request, f'Published {version.version_label}.')
            elif action == 'new_version' and version:
                new_version = create_next_version(template, request.user, copy_from_version=version)
                messages.success(request, f'Created draft {new_version.version_label}.')
            else:
                messages.error(request, 'Unknown action.')
        except ValidationError as exc:
            messages.error(request, str(exc))
        return redirect('checklists:manage_template_detail', pk=pk)

    return render(request, 'checklists/manage/template_detail.html', {
        'template': template,
        'versions': versions,
    })


@login_required
@permission_required('checklists.manage_checklist', raise_exception=True)
def manage_assign(request):
    published_versions = (
        ChecklistTemplateVersion.objects.filter(status=ChecklistTemplateVersion.Status.PUBLISHED)
        .select_related('template')
        .order_by('template__name_en', '-version_number')
    )
    employees = Employee.objects.select_related('user').order_by('last_name', 'first_name')

    if request.method == 'POST':
        version_id = request.POST.get('template_version')
        employee_ids = request.POST.getlist('employees')
        version = get_object_or_404(published_versions, pk=version_id)
        selected = employees.filter(pk__in=employee_ids)
        if not selected.exists():
            messages.error(request, 'Select at least one employee. / Mindestens einen Mitarbeiter auswählen.')
        else:
            created = 0
            for employee in selected:
                assign_instance(employee, version, assigned_by=request.user)
                created += 1
            messages.success(
                request,
                f'Assigned checklist to {created} employee(s). / Checkliste {created} Mitarbeiter(n) zugewiesen.',
            )
            return redirect('checklists:manage_assign')

    return render(request, 'checklists/manage/assign.html', {
        'published_versions': published_versions,
        'employees': employees,
    })


def _progress_matrix(employees, templates):
    rows = []
    for employee in employees:
        cells = []
        for template in templates:
            instance = (
                ChecklistInstance.objects.filter(
                    subject=employee,
                    template_version__template=template,
                )
                .exclude(status=ChecklistInstance.Status.CANCELLED)
                .select_related('template_version')
                .order_by('-assigned_at')
                .first()
            )
            if instance:
                percent, fulfilled, total = compute_progress(instance)
                cells.append({
                    'instance': instance,
                    'percent': percent,
                    'status': instance.status,
                    'fulfilled': fulfilled,
                    'total': total,
                })
            else:
                cells.append({'instance': None, 'percent': None, 'status': None})
        rows.append({'employee': employee, 'cells': cells})
    return rows


@login_required
@permission_required('checklists.view_workgroup_progress', raise_exception=True)
def progress_workgroup(request):
    workgroup = get_user_first_workgroup(request.user)
    employees = employees_in_workgroup(workgroup)
    templates = ChecklistTemplate.objects.order_by('name_en')
    rows = _progress_matrix(employees, templates)
    return render(request, 'checklists/progress/workgroup_matrix.html', {
        'workgroup': workgroup,
        'templates': templates,
        'rows': rows,
    })


@login_required
@permission_required('checklists.view_institute_progress', raise_exception=True)
def progress_institute(request):
    employees = list(Employee.objects.order_by('last_name', 'first_name'))
    templates = ChecklistTemplate.objects.order_by('name_en')
    rows = _progress_matrix(employees, templates)
    return render(request, 'checklists/progress/institute_matrix.html', {
        'templates': templates,
        'rows': rows,
    })


@login_required
def instance_view(request, pk):
    instance = get_object_or_404(
        ChecklistInstance.objects.select_related(
            'subject', 'template_version', 'template_version__template',
        ),
        pk=pk,
    )
    if not user_can_view_instance_readonly(request.user, instance):
        return HttpResponseForbidden('Access denied.')
    context = _instance_context(request, instance, can_edit=False)
    context['can_complete'] = (
        user_can_manage(request.user)
        and not instance.is_locked
        and instance.template_version.completion_mode
        == ChecklistTemplateVersion.CompletionMode.COORDINATOR_CONFIRM
    )
    return render(request, 'checklists/instance_fill.html', context)


@login_required
def instance_file_download(request, pk, response_pk):
    instance = get_object_or_404(ChecklistInstance, pk=pk)
    if not user_can_view_instance_readonly(request.user, instance):
        return HttpResponseForbidden('Access denied.')
    response = get_object_or_404(
        ChecklistFieldResponse.objects.select_related('node'),
        pk=response_pk,
        instance=instance,
    )
    if not response.file:
        raise Http404('File not found.')
    return FileResponse(
        response.file.open('rb'),
        as_attachment=True,
        filename=response.original_filename or response.file.name,
    )


@login_required
@require_POST
@permission_required('checklists.manage_checklist', raise_exception=True)
def instance_complete(request, pk):
    instance = get_object_or_404(ChecklistInstance, pk=pk)
    try:
        complete_instance(instance, request.user)
        messages.success(request, 'Checklist marked as completed. / Checkliste als abgeschlossen markiert.')
    except ValidationError as exc:
        messages.error(request, str(exc))
    return redirect('checklists:instance_view', pk=pk)
