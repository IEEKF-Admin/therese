import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.db.models import ProtectedError, Q
from django.http import Http404, HttpResponseForbidden, JsonResponse
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.documents.audience import user_matches_document_audience
from apps.documents.category_utils import (
    build_category_tree_rows,
    build_document_list_sections,
    document_sort_key,
    load_categories_by_id,
)
from apps.documents.forms import (
    DocumentAttachmentFormSet,
    DocumentCategoryForm,
    DocumentMetaForm,
    DocumentVersionDraftForm,
)
from apps.documents.models import (
    Document,
    DocumentAttachment,
    DocumentCategory,
    DocumentReadAcknowledgement,
    DocumentVersion,
)
from apps.documents.pdf import render_document_pdf_response
from apps.documents.sidebar_notifications import (
    get_pending_read_ack_document_ids,
    mark_publish_notifications_seen,
)
from apps.documents.utils import (
    create_next_version,
    log_document_activity,
    publish_version,
)

User = get_user_model()

EDITOR_IMAGE_MAX_BYTES = 5 * 1024 * 1024
EDITOR_IMAGE_TYPES = {
    'image/jpeg': '.jpg',
    'image/png': '.png',
    'image/gif': '.gif',
    'image/webp': '.webp',
}


def _get_readable_document(user, pk):
    document = get_object_or_404(
        Document.objects.select_related('category', 'current_published_version'),
        pk=pk,
    )
    if user.has_perm('documents.manage_document'):
        return document
    if document.is_archived or not document.current_published_version_id:
        raise Http404
    if not user.has_perm('documents.view_document'):
        raise Http404
    if not user_matches_document_audience(user, document):
        raise Http404
    return document


def _get_version_for_reading(document, user, version_pk=None):
    if version_pk:
        version = get_object_or_404(document.versions, pk=version_pk)
        if user.has_perm('documents.manage_document'):
            return version
        if version.status != DocumentVersion.Status.PUBLISHED:
            raise Http404
        return version
    if document.current_published_version_id:
        return document.current_published_version
    raise Http404


@login_required
@permission_required('documents.view_document', raise_exception=True)
def document_list(request):
    query = request.GET.get('q', '').strip()
    documents = Document.objects.filter(
        is_archived=False,
        current_published_version__isnull=False,
    ).select_related('category', 'current_published_version').prefetch_related(
        'target_users', 'target_workgroups', 'target_groups'
    )

    visible = []
    for doc in documents:
        if user_matches_document_audience(request.user, doc):
            visible.append(doc)

    if query:
        q_lower = query.lower()
        visible = [
            d for d in visible
            if q_lower in d.title.lower()
            or q_lower in (d.current_published_version.content_html or '').lower()
        ]

    mark_publish_notifications_seen(request.user)
    pending_read_ack_ids = get_pending_read_ack_document_ids(request.user)
    for document in visible:
        document.pending_read_ack = document.pk in pending_read_ack_ids

    return render(request, 'documents/document_list.html', {
        'sections': build_document_list_sections(visible),
        'search_query': query,
        'pending_read_ack_count': len(pending_read_ack_ids & {doc.pk for doc in visible}),
    })


@login_required
def document_detail(request, pk, version_pk=None):
    document = _get_readable_document(request.user, pk)
    version = _get_version_for_reading(document, request.user, version_pk)

    read_ack = None
    can_reconsider = False
    if document.requires_read_acknowledgement and version == document.current_published_version:
        if request.user.has_perm('documents.view_document'):
            read_ack = DocumentReadAcknowledgement.objects.filter(
                version=version, user=request.user
            ).first()
            can_reconsider = (
                read_ack is not None
                and read_ack.status == DocumentReadAcknowledgement.Status.DECLINED
            )

    older_versions = document.versions.filter(
        status=DocumentVersion.Status.PUBLISHED,
    ).exclude(pk=version.pk).order_by('-version_number')

    return render(request, 'documents/document_detail.html', {
        'document': document,
        'version': version,
        'older_versions': older_versions,
        'read_ack': read_ack,
        'can_reconsider': can_reconsider,
        'is_current_version': version.pk == document.current_published_version_id,
    })


@login_required
def document_pdf(request, pk, version_pk):
    document = _get_readable_document(request.user, pk)
    version = _get_version_for_reading(document, request.user, version_pk)
    return render_document_pdf_response(version)


@login_required
@permission_required('documents.view_document', raise_exception=True)
def document_ack_confirm(request, pk):
    if request.method != 'POST':
        return redirect('documents:detail', pk=pk)
    document = _get_readable_document(request.user, pk)
    if not document.requires_read_acknowledgement:
        return redirect('documents:detail', pk=pk)
    version = document.current_published_version
    DocumentReadAcknowledgement.objects.update_or_create(
        version=version,
        user=request.user,
        defaults={'status': DocumentReadAcknowledgement.Status.CONFIRMED, 'decided_at': timezone.now()},
    )
    messages.success(request, 'Read acknowledgement saved.')
    return redirect('documents:detail', pk=pk)


@login_required
@permission_required('documents.view_document', raise_exception=True)
def document_ack_decline(request, pk):
    if request.method != 'POST':
        return redirect('documents:detail', pk=pk)
    document = _get_readable_document(request.user, pk)
    if not document.requires_read_acknowledgement:
        return redirect('documents:detail', pk=pk)
    version = document.current_published_version
    DocumentReadAcknowledgement.objects.update_or_create(
        version=version,
        user=request.user,
        defaults={'status': DocumentReadAcknowledgement.Status.DECLINED, 'decided_at': timezone.now()},
    )
    messages.info(request, 'You declined this document. You may reconsider and confirm later.')
    return redirect('documents:detail', pk=pk)


@login_required
@permission_required('documents.view_document', raise_exception=True)
def document_ack_reconsider(request, pk):
    if request.method != 'POST':
        return redirect('documents:detail', pk=pk)
    document = _get_readable_document(request.user, pk)
    version = document.current_published_version
    ack = DocumentReadAcknowledgement.objects.filter(version=version, user=request.user).first()
    if not ack or ack.status != DocumentReadAcknowledgement.Status.DECLINED:
        return redirect('documents:detail', pk=pk)
    ack.status = DocumentReadAcknowledgement.Status.CONFIRMED
    ack.decided_at = timezone.now()
    ack.save(update_fields=['status', 'decided_at'])
    messages.success(request, 'You confirmed the document.')
    return redirect('documents:detail', pk=pk)


@login_required
@permission_required('documents.manage_document', raise_exception=True)
def manage_document_list(request):
    query = request.GET.get('q', '').strip()
    documents = Document.objects.select_related(
        'category', 'current_published_version', 'created_by'
    ).prefetch_related('versions')

    if query:
        documents = documents.filter(
            Q(title__icontains=query)
            | Q(versions__content_html__icontains=query)
        ).distinct()

    categories_by_id = load_categories_by_id()
    documents = list(documents.select_related('category', 'category__parent'))
    documents.sort(key=lambda doc: document_sort_key(doc, categories_by_id=categories_by_id))

    return render(request, 'documents/manage_list.html', {
        'documents': documents,
        'search_query': query,
    })


def _save_document_forms(request, document, version, meta_form, content_form, attachment_formset):
    if not all([
        meta_form.is_valid(),
        content_form.is_valid(),
        attachment_formset.is_valid(),
    ]):
        return False

    meta_form.save()
    content_form.save()
    attachment_formset.instance = version
    attachment_formset.save()
    log_document_activity(document, request.user, 'edited_draft', version=version)
    return True


@login_required
@permission_required('documents.manage_document', raise_exception=True)
def manage_document_create(request):
    document = None
    version = None

    if request.method == 'POST':
        meta_form = DocumentMetaForm(request.POST)
        content_form = DocumentVersionDraftForm(request.POST)
        if meta_form.is_valid() and content_form.is_valid():
            document = meta_form.save(commit=False)
            document.created_by = request.user
            document.save()
            meta_form.save_m2m()

            version = DocumentVersion.objects.create(
                document=document,
                version_number=1,
                status=DocumentVersion.Status.DRAFT,
                content_html=content_form.cleaned_data.get('content_html', ''),
                change_summary=content_form.cleaned_data.get('change_summary', ''),
                created_by=request.user,
            )
            attachment_formset = DocumentAttachmentFormSet(
                request.POST, request.FILES, instance=version
            )
            if attachment_formset.is_valid():
                attachment_formset.save()
            else:
                messages.warning(request, 'Draft created. Please review attachments on the edit page.')
            log_document_activity(document, request.user, 'created', version=version)
            messages.success(request, f'Document "{document.title}" created as draft v1.')
            return redirect('documents:manage_edit', pk=document.pk)
        else:
            attachment_formset = DocumentAttachmentFormSet(
                request.POST, request.FILES, instance=DocumentVersion()
            )
    else:
        meta_form = DocumentMetaForm()
        content_form = DocumentVersionDraftForm()
        attachment_formset = DocumentAttachmentFormSet(instance=DocumentVersion())

    return render(request, 'documents/manage_form.html', {
        'title': 'Create Document',
        'document': document,
        'version': version,
        'meta_form': meta_form,
        'content_form': content_form,
        'attachment_formset': attachment_formset,
        'can_publish': version is not None,
        'can_new_version': False,
    })


@login_required
@permission_required('documents.manage_document', raise_exception=True)
def manage_document_edit(request, pk):
    document = get_object_or_404(Document, pk=pk)
    draft = document.latest_draft
    if not draft:
        messages.info(request, 'No draft version exists. Start a new version to edit content.')
        return redirect('documents:manage_detail', pk=pk)

    if request.method == 'POST':
        meta_form = DocumentMetaForm(request.POST, instance=document)
        content_form = DocumentVersionDraftForm(request.POST, instance=draft)
        attachment_formset = DocumentAttachmentFormSet(
            request.POST, request.FILES, instance=draft
        )
        if _save_document_forms(request, document, draft, meta_form, content_form, attachment_formset):
            messages.success(request, 'Draft saved.')
            return redirect('documents:manage_edit', pk=pk)
    else:
        meta_form = DocumentMetaForm(instance=document)
        content_form = DocumentVersionDraftForm(instance=draft)
        attachment_formset = DocumentAttachmentFormSet(instance=draft)

    return render(request, 'documents/manage_form.html', {
        'title': f'Edit Draft — {document.title}',
        'document': document,
        'version': draft,
        'meta_form': meta_form,
        'content_form': content_form,
        'attachment_formset': attachment_formset,
        'can_publish': True,
        'can_new_version': False,
    })


@login_required
@permission_required('documents.manage_document', raise_exception=True)
def manage_document_detail(request, pk):
    document = get_object_or_404(
        Document.objects.select_related('category', 'created_by', 'current_published_version')
        .prefetch_related(
            'versions__attachments',
            'target_users',
            'target_workgroups',
            'target_groups',
            'activity_logs__user',
            'activity_logs__version',
        ),
        pk=pk,
    )
    return render(request, 'documents/manage_detail.html', {
        'document': document,
        'versions': document.versions.order_by('-version_number'),
        'activity_logs': document.activity_logs.select_related('user', 'version')[:50],
    })


@login_required
@permission_required('documents.manage_document', raise_exception=True)
@require_POST
def upload_editor_image(request):
    upload = request.FILES.get('file')
    if not upload:
        return JsonResponse({'error': 'No file provided.'}, status=400)

    if upload.size > EDITOR_IMAGE_MAX_BYTES:
        return JsonResponse({'error': 'Image too large (max 5 MB).'}, status=400)

    content_type = getattr(upload, 'content_type', '')
    extension = EDITOR_IMAGE_TYPES.get(content_type)
    if not extension:
        return JsonResponse({'error': 'Invalid image type. Use JPEG, PNG, GIF, or WebP.'}, status=400)

    now = timezone.now()
    path = f'documents/content/{now:%Y/%m}/{uuid.uuid4().hex}{extension}'
    saved_path = default_storage.save(path, upload)
    location = request.build_absolute_uri(default_storage.url(saved_path))
    return JsonResponse({'location': location})


@login_required
@permission_required('documents.manage_document', raise_exception=True)
@require_POST
def manage_attachment_delete(request, pk, attachment_pk):
    document = get_object_or_404(Document, pk=pk)
    draft = document.latest_draft
    if not draft:
        return JsonResponse({'error': 'No draft version.'}, status=400)

    attachment = get_object_or_404(
        DocumentAttachment,
        pk=attachment_pk,
        version=draft,
    )
    if attachment.file:
        attachment.file.delete(save=False)
    label = attachment.label or attachment.file.name
    attachment.delete()
    log_document_activity(
        document,
        request.user,
        'edited_draft',
        version=draft,
        details=f'Removed attachment: {label}',
    )

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'ok': True})

    messages.success(request, 'Attachment removed.')
    return redirect('documents:manage_edit', pk=pk)


@login_required
@permission_required('documents.manage_document', raise_exception=True)
def manage_document_publish(request, pk):
    document = get_object_or_404(Document, pk=pk)
    draft = document.latest_draft
    if not draft:
        messages.error(request, 'No draft version to publish.')
        return redirect('documents:manage_detail', pk=pk)
    publish_version(draft, request.user)
    messages.success(request, f'Published {draft.version_label}.')
    return redirect('documents:manage_detail', pk=pk)


@login_required
@permission_required('documents.manage_document', raise_exception=True)
def manage_document_new_version(request, pk):
    document = get_object_or_404(Document, pk=pk)
    if document.latest_draft:
        messages.warning(request, 'A draft already exists. Publish or edit it first.')
        return redirect('documents:manage_edit', pk=pk)
    source = document.current_published_version or document.versions.order_by('-version_number').first()
    if not source:
        messages.error(request, 'No version to copy from.')
        return redirect('documents:manage_detail', pk=pk)
    new_version = create_next_version(document, request.user, copy_from_version=source)
    messages.success(request, f'Created {new_version.version_label} as draft.')
    return redirect('documents:manage_edit', pk=pk)


@login_required
@permission_required('documents.manage_document', raise_exception=True)
def manage_document_archive(request, pk):
    document = get_object_or_404(Document, pk=pk)
    document.is_archived = True
    document.save(update_fields=['is_archived', 'updated_at'])
    log_document_activity(document, request.user, 'archived')
    messages.success(request, f'"{document.title}" archived.')
    return redirect('documents:manage_list')


@login_required
@permission_required('documents.manage_document', raise_exception=True)
def manage_categories(request):
    if request.method == 'POST':
        if request.POST.get('delete_pk'):
            category = DocumentCategory.objects.filter(pk=request.POST['delete_pk']).first()
            if not category:
                messages.error(request, 'Category not found.')
            elif category.children.exists():
                messages.error(request, 'Category has subcategories and cannot be deleted.')
            else:
                try:
                    category.delete()
                    messages.success(request, 'Category deleted.')
                except ProtectedError:
                    messages.error(request, 'Category is in use by documents and cannot be deleted.')
            return redirect('documents:manage_categories')
        pk = request.POST.get('pk')
        instance = DocumentCategory.objects.filter(pk=pk).first() if pk else None
        form = DocumentCategoryForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, 'Category saved.')
            return redirect('documents:manage_categories')
    else:
        form = DocumentCategoryForm()

    categories = DocumentCategory.objects.select_related('parent').prefetch_related('children')
    return render(request, 'documents/manage_categories.html', {
        'category_rows': build_category_tree_rows(categories),
        'form': form,
    })


@login_required
@permission_required('documents.manage_document', raise_exception=True)
def read_ack_matrix(request):
    users = User.objects.filter(
        Q(groups__permissions__codename='view_document')
        | Q(user_permissions__codename='view_document')
        | Q(is_superuser=True)
    ).distinct().order_by('last_name', 'first_name', 'username')

    documents = Document.objects.filter(
        requires_read_acknowledgement=True,
        is_archived=False,
        current_published_version__isnull=False,
    ).select_related('current_published_version')

    filter_user_id = request.GET.get('user', '')
    filter_doc_id = request.GET.get('document', '')

    if filter_user_id:
        users = users.filter(pk=filter_user_id)
    if filter_doc_id:
        documents = documents.filter(pk=filter_doc_id)

    ack_map = {}
    for ack in DocumentReadAcknowledgement.objects.filter(
        version_id__in=[d.current_published_version_id for d in documents]
    ).select_related('user', 'version'):
        ack_map[(ack.user_id, ack.version_id)] = ack.status

    rows = []
    for user in users:
        cells = []
        for doc in documents:
            version_id = doc.current_published_version_id
            in_audience = user_matches_document_audience(user, doc)
            status = ack_map.get((user.pk, version_id), '')
            if not in_audience:
                status = 'n/a'
            cells.append({
                'document': doc,
                'status': status,
            })
        rows.append({'user': user, 'cells': cells})

    return render(request, 'documents/read_ack_matrix.html', {
        'rows': rows,
        'documents': documents,
        'all_users': User.objects.filter(is_active=True).order_by('last_name', 'first_name'),
        'all_documents': Document.objects.filter(
            requires_read_acknowledgement=True, is_archived=False
        ),
        'filter_user_id': filter_user_id,
        'filter_doc_id': filter_doc_id,
    })