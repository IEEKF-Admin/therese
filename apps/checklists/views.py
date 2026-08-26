from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.checklists.forms import (
    ChecklistAssignForm,
    ChecklistNodeBulkForm,
    ChecklistTemplateForm,
    ChecklistTemplateNodeForm,
    ChecklistTemplateVersionForm,
)
from django.views.decorators.http import require_POST

from apps.checklists.access import (
    acknowledge_instance,
    employees_in_user_workgroups,
    get_user_workgroups_ordered,
    subject_active_instances,
    user_can_edit_node,
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
    copy_template_latest_version,
    create_next_version,
    duplicate_node_subtree,
    publish_version,
    responses_by_node_id,
    save_field_response,
)
from django.utils.text import slugify
from apps.hr.models import Employee


def _completable(user, instance):
    return (
        user_can_manage(user)
        and not instance.is_locked
        and instance.template_version.completion_mode
        == ChecklistTemplateVersion.CompletionMode.COORDINATOR_CONFIRM
    )


def _instance_context(request, instance, *, can_edit):
    version = instance.template_version
    nodes = list(
        version.nodes.prefetch_related(
            'editable_by_employees', 'editable_by_groups', 'children',
        ).order_by('sort_order', 'pk')
    )
    if can_edit:
        visible_nodes = nodes
    else:
        viewer = getattr(request.user, 'employee', None)
        visible_nodes = [
            n for n in nodes
            if n.visible_to_subject or not viewer or instance.subject_id != viewer.pk
        ]
    tree = build_node_tree(visible_nodes)
    percent, fulfilled, total = compute_progress(instance)
    editable_node_ids = set()
    if can_edit:
        editable_node_ids = {
            n.pk
            for n in visible_nodes
            if n.node_kind == ChecklistTemplateNode.NodeKind.FIELD
            and user_can_edit_node(request.user, instance, n)
        }
    return {
        'instance': instance,
        'template': version.template,
        'version': version,
        'tree': tree,
        'responses': responses_by_node_id(instance),
        'can_edit': can_edit,
        'editable_node_ids': editable_node_ids,
        'progress_percent': percent,
        'progress_fulfilled': fulfilled,
        'progress_total': total,
        'can_complete': _completable(request.user, instance),
    }


def _parse_field_post(request, instance):
    saved = 0
    field_nodes = instance.template_version.nodes.filter(
        node_kind=ChecklistTemplateNode.NodeKind.FIELD,
    )
    for node in field_nodes:
        if not user_can_edit_node(request.user, instance, node):
            continue
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




def _get_draft_version(template, version_pk):
    version = get_object_or_404(template.versions, pk=version_pk)
    if version.status != ChecklistTemplateVersion.Status.DRAFT:
        raise Http404('Only draft versions can be edited.')
    return version


def _parent_choices_json(version):
    nodes = version.nodes.select_related('parent').order_by('sort_order', 'pk')
    sections = [
        {'id': n.pk, 'label': n.parent_choice_label}
        for n in nodes
        if n.node_kind == ChecklistTemplateNode.NodeKind.SECTION
    ]
    radio_groups = [
        {'id': n.pk, 'label': n.parent_choice_label}
        for n in nodes
        if n.node_kind == ChecklistTemplateNode.NodeKind.FIELD
        and n.field_type == ChecklistTemplateNode.FieldType.RADIO_GROUP
    ]
    return {
        'section': sections,
        'field': sections,
        'html': sections,
        'radio_option': radio_groups,
    }


def _preview_progress(version):
    total = version.nodes.filter(
        node_kind=ChecklistTemplateNode.NodeKind.FIELD,
        required_for_completion=True,
    ).count()
    if total == 0:
        return 100, 0, 0
    return 0, 0, total


def _node_indent_label(node):
    prefix = '— ' * (1 if node.parent_id else 0)
    if node.parent and node.parent.parent_id:
        prefix = '— ' * 2
    kind = node.get_node_kind_display()
    label = node.label_en or node.choice_key or kind
    return f'{prefix}{kind}: {label}'


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
def manage_template_create(request):
    if request.method == 'POST':
        form = ChecklistTemplateForm(request.POST)
        if form.is_valid():
            template = form.save()
            version = ChecklistTemplateVersion.objects.create(
                template=template,
                version_number=1,
                status=ChecklistTemplateVersion.Status.DRAFT,
                created_by=request.user,
            )
            messages.success(request, f'Template "{template.name_en}" created with draft v1.')
            return redirect('checklists:manage_version_edit', pk=template.pk, vid=version.pk)
    else:
        form = ChecklistTemplateForm()
    return render(request, 'checklists/manage/template_form.html', {
        'form': form,
        'title': 'New Checklist Template',
        'submit_label': 'Create template',
    })


@login_required
@permission_required('checklists.manage_checklist', raise_exception=True)
def manage_template_edit(request, pk):
    template = get_object_or_404(ChecklistTemplate, pk=pk)
    if request.method == 'POST':
        form = ChecklistTemplateForm(request.POST, instance=template)
        if form.is_valid():
            form.save()
            messages.success(request, 'Template saved.')
            return redirect('checklists:manage_template_detail', pk=pk)
    else:
        form = ChecklistTemplateForm(instance=template)
    return render(request, 'checklists/manage/template_form.html', {
        'form': form,
        'template': template,
        'title': f'Edit {template.name_en}',
        'submit_label': 'Save template',
    })


def _suggested_copy_slug(source):
    base = slugify(source.slug) or 'template'
    candidate = f'{base}-copy'
    n = 2
    while ChecklistTemplate.objects.filter(slug=candidate).exists():
        candidate = f'{base}-copy-{n}'
        n += 1
    return candidate


@login_required
@permission_required('checklists.manage_checklist', raise_exception=True)
def manage_template_copy(request, pk):
    source = get_object_or_404(ChecklistTemplate, pk=pk)
    initial = {
        'slug': _suggested_copy_slug(source),
        'name_en': f'Copy of {source.name_en}' if source.name_en else '',
        'name_de': f'Kopie von {source.name_de}' if source.name_de else '',
        'description_en': source.description_en,
        'description_de': source.description_de,
    }
    if request.method == 'POST':
        form = ChecklistTemplateForm(request.POST)
        if form.is_valid():
            new_template, new_version = copy_template_latest_version(
                source,
                request.user,
                slug=form.cleaned_data['slug'],
                name_en=form.cleaned_data['name_en'],
                name_de=form.cleaned_data['name_de'],
                description_en=form.cleaned_data.get('description_en') or '',
                description_de=form.cleaned_data.get('description_de') or '',
            )
            messages.success(
                request,
                f'Copied latest version of “{source.name_en}” to “{new_template.name_en}” as {new_version.version_label}.',
            )
            return redirect('checklists:manage_version_edit', pk=new_template.pk, vid=new_version.pk)
    else:
        form = ChecklistTemplateForm(initial=initial)
    return render(request, 'checklists/manage/template_form.html', {
        'form': form,
        'title': f'Copy checklist — {source.name_en}',
        'submit_label': 'Create copy',
        'copy_source': source,
    })


def _version_edit_redirect(pk, vid, node=None, nodes=None):
    url = reverse('checklists:manage_version_edit', args=[pk, vid])
    if nodes:
        ids = ','.join(str(n.pk) for n in nodes)
        return redirect(f'{url}?nodes={ids}')
    if node is not None:
        return redirect(f'{url}?node={node.pk}')
    return redirect(url)


def _parse_selected_node_ids(request):
    values = []
    if request.method == 'POST' and request.POST.get('action') == 'save_bulk':
        values = request.POST.getlist('node_pks')
    elif request.GET.get('nodes'):
        values = request.GET.getlist('nodes')
        if len(values) == 1 and ',' in values[0]:
            values = values[0].split(',')
    elif request.GET.get('node'):
        values = [request.GET.get('node')]
    elif request.POST.get('node_pk'):
        values = [request.POST.get('node_pk')]
    ids = []
    seen = set()
    for value in values:
        value = str(value).strip()
        if value.isdigit():
            node_id = int(value)
            if node_id not in seen:
                seen.add(node_id)
                ids.append(node_id)
    return ids


@login_required
@permission_required('checklists.manage_checklist', raise_exception=True)
def manage_version_edit(request, pk, vid):
    template = get_object_or_404(ChecklistTemplate, pk=pk)
    version = _get_draft_version(template, vid)
    nodes = list(version.nodes.select_related('parent').order_by('sort_order', 'pk'))

    version_form = ChecklistTemplateVersionForm(instance=version, version=version)
    add_form = ChecklistTemplateNodeForm(version=version, auto_id='id_add_%s')
    edit_node = None
    edit_form = None
    bulk_form = None
    edit_nodes = []
    show_add_modal = False

    selected_ids = _parse_selected_node_ids(request)
    if selected_ids:
        by_id = {n.pk: n for n in nodes}
        edit_nodes = [by_id[i] for i in selected_ids if i in by_id]
        if len(edit_nodes) == 1:
            edit_node = edit_nodes[0]
            edit_form = ChecklistTemplateNodeForm(
                instance=edit_node, version=version, auto_id='id_edit_%s',
            )
        elif len(edit_nodes) > 1:
            bulk_form = ChecklistNodeBulkForm(version=version, nodes=edit_nodes)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'save_version':
            version_form = ChecklistTemplateVersionForm(request.POST, instance=version, version=version)
            if version_form.is_valid():
                version_form.save()
                messages.success(request, 'Version settings saved.')
                return redirect('checklists:manage_version_edit', pk=pk, vid=vid)
        elif action == 'add_node':
            add_form = ChecklistTemplateNodeForm(
                request.POST, version=version, auto_id='id_add_%s',
            )
            if add_form.is_valid():
                new_node = add_form.save()
                messages.success(request, 'Node added.')
                return _version_edit_redirect(pk, vid, new_node)
            show_add_modal = True
        elif action == 'save_node' and edit_node:
            edit_form = ChecklistTemplateNodeForm(
                request.POST, instance=edit_node, version=version, auto_id='id_edit_%s',
            )
            if edit_form.is_valid():
                edit_form.save()
                messages.success(request, 'Node saved.')
                return _version_edit_redirect(pk, vid, edit_node)
        elif action == 'save_bulk' and edit_nodes:
            bulk_form = ChecklistNodeBulkForm(
                request.POST, version=version, nodes=edit_nodes,
            )
            if bulk_form.is_valid():
                updated = bulk_form.apply()
                messages.success(request, f'Updated {updated} node(s).')
                return _version_edit_redirect(pk, vid, nodes=edit_nodes)
        elif action == 'copy_node':
            source = get_object_or_404(version.nodes, pk=request.POST.get('node_pk'))
            copied = duplicate_node_subtree(source)
            messages.success(request, 'Node copied.')
            return _version_edit_redirect(pk, vid, copied)

    selected_node_ids = {n.pk for n in edit_nodes}
    return render(request, 'checklists/manage/version_edit.html', {
        'template': template,
        'version': version,
        'nodes': nodes,
        'tree': build_node_tree(nodes),
        'version_form': version_form,
        'add_form': add_form,
        'edit_node': edit_node,
        'edit_form': edit_form,
        'edit_nodes': edit_nodes,
        'bulk_form': bulk_form,
        'selected_node_ids': selected_node_ids,
        'show_add_modal': show_add_modal,
        'parent_choices_json': _parent_choices_json(version),
    })


@login_required
@permission_required('checklists.manage_checklist', raise_exception=True)
def manage_version_preview(request, pk, vid):
    template = get_object_or_404(ChecklistTemplate, pk=pk)
    version = _get_draft_version(template, vid)
    nodes = list(
        version.nodes.prefetch_related(
            'editable_by_employees', 'editable_by_groups', 'children',
        ).order_by('sort_order', 'pk')
    )
    tree = build_node_tree(nodes)
    percent, fulfilled, total = _preview_progress(version)
    editable_node_ids = {
        n.pk for n in nodes if n.node_kind == ChecklistTemplateNode.NodeKind.FIELD
    }
    return render(request, 'checklists/manage/version_preview.html', {
        'template': template,
        'version': version,
        'tree': tree,
        'responses': {},
        'can_edit': True,
        'preview_mode': True,
        'editable_node_ids': editable_node_ids,
        'progress_percent': percent,
        'progress_fulfilled': fulfilled,
        'progress_total': total,
    })


@login_required
@permission_required('checklists.manage_checklist', raise_exception=True)
def manage_node_edit(request, pk, vid, node_pk):
    template = get_object_or_404(ChecklistTemplate, pk=pk)
    version = _get_draft_version(template, vid)
    node = get_object_or_404(version.nodes, pk=node_pk)
    if request.method == 'POST':
        form = ChecklistTemplateNodeForm(request.POST, instance=node, version=version)
        if form.is_valid():
            form.save()
            messages.success(request, 'Node saved.')
            return _version_edit_redirect(pk, vid, node)
    return redirect(f"{reverse('checklists:manage_version_edit', args=[pk, vid])}?node={node.pk}")


@login_required
@require_POST
@permission_required('checklists.manage_checklist', raise_exception=True)
def manage_node_delete(request, pk, vid, node_pk):
    template = get_object_or_404(ChecklistTemplate, pk=pk)
    version = _get_draft_version(template, vid)
    node = get_object_or_404(version.nodes, pk=node_pk)
    node.delete()
    messages.success(request, 'Node deleted.')
    return redirect('checklists:manage_version_edit', pk=pk, vid=vid)


@login_required
@permission_required('checklists.manage_checklist', raise_exception=True)
def manage_assign(request, pk=None):
    template = get_object_or_404(ChecklistTemplate, pk=pk) if pk else None
    published_versions = (
        ChecklistTemplateVersion.objects.filter(status=ChecklistTemplateVersion.Status.PUBLISHED)
        .select_related('template')
        .order_by('template__name_en', '-version_number')
    )
    lock_version = None
    if template:
        published_versions = published_versions.filter(template=template)
        lock_version = published_versions.first()
        if not lock_version:
            messages.error(
                request,
                'Publish a version before assigning this checklist. / Bitte zuerst eine Version veröffentlichen.',
            )
            return redirect('checklists:manage_template_detail', pk=template.pk)

    form = ChecklistAssignForm(
        request.POST or None,
        published_versions=published_versions,
        lock_version=lock_version,
    )
    if request.method == 'POST' and form.is_valid():
        version = form.cleaned_data['template_version']
        created = 0
        for employee in form.cleaned_data['employees']:
            assign_instance(employee, version, assigned_by=request.user)
            created += 1
        messages.success(
            request,
            f'Assigned checklist to {created} employee(s). / Checkliste {created} Mitarbeiter(n) zugewiesen.',
        )
        if template:
            return redirect('checklists:manage_template_assign', pk=template.pk)
        return redirect('checklists:manage_assign')

    return render(request, 'checklists/manage/assign.html', {
        'form': form,
        'template': template,
        'lock_version': lock_version,
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
    """Checklist progress for employees in all of the user's workgroups."""
    workgroups = get_user_workgroups_ordered(request.user)
    employees = employees_in_user_workgroups(request.user)
    templates = ChecklistTemplate.objects.order_by('name_en')
    rows = _progress_matrix(employees, templates)
    return render(request, 'checklists/progress/workgroup_matrix.html', {
        'workgroups': workgroups,
        'workgroup': workgroups[0] if len(workgroups) == 1 else None,
        'templates': templates,
        'rows': rows,
    })


@login_required
@permission_required('checklists.view_institute_progress', raise_exception=True)
def progress_institute(request):
    """Institute-wide checklist progress (all employees)."""
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
    context['can_switch_to_edit'] = user_can_fill_instance(request.user, instance)
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
