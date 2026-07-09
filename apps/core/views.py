from django.contrib.auth.decorators import login_required
from django.http import Http404

from .file_service import ThereseFileService


@login_required
def serve_stored_file(request, file_path):
    if not ThereseFileService.exists(file_path):
        raise Http404('File not found.')
    return ThereseFileService.as_response(file_path)