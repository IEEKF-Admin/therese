"""Temporary storage for recruitment file uploads during multi-step form validation."""

import uuid

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

SESSION_KEY = 'recruitment_draft_uploads'
FILE_FIELDS = ('cv_file', 'latest_degree_certificate_file')


def get_stashed_uploads(request):
    return dict(request.session.get(SESSION_KEY, {}))


def stash_recruitment_uploads(request):
    """Persist newly uploaded files and keep previously stashed ones."""
    uploads = get_stashed_uploads(request)
    changed = False

    for field_name in FILE_FIELDS:
        uploaded = request.FILES.get(field_name)
        if not uploaded:
            continue
        if uploads.get(field_name, {}).get('name') == uploaded.name and uploads.get(field_name, {}).get('size') == uploaded.size:
            continue
        storage_path = default_storage.save(
            f'recruitment_tasks/draft/{uuid.uuid4().hex}/{uploaded.name}',
            uploaded,
        )
        old_path = uploads.get(field_name, {}).get('path')
        if old_path and old_path != storage_path:
            default_storage.delete(old_path)
        uploads[field_name] = {
            'path': storage_path,
            'name': uploaded.name,
            'size': uploaded.size,
        }
        changed = True

    if uploads:
        request.session[SESSION_KEY] = uploads
        request.session.modified = True
    elif changed:
        request.session.modified = True

    return uploads


def apply_stashed_uploads(cleaned_data, stashed_uploads):
    """Inject cached uploads into cleaned_data when the browser did not resend them."""
    for field_name in FILE_FIELDS:
        if cleaned_data.get(field_name) or field_name not in stashed_uploads:
            continue
        info = stashed_uploads[field_name]
        with default_storage.open(info['path'], 'rb') as handle:
            cleaned_data[field_name] = ContentFile(handle.read(), name=info['name'])
    return cleaned_data


def clear_stashed_uploads(request, *, delete_files=True):
    uploads = request.session.pop(SESSION_KEY, {})
    if delete_files:
        for info in uploads.values():
            path = info.get('path')
            if path and default_storage.exists(path):
                default_storage.delete(path)
    request.session.modified = True