from django.contrib.auth.decorators import login_required
from django.http import Http404

from .file_service import ThereseFileService
from .media_access import user_can_access_stored_file


@login_required
def serve_stored_file(request, file_path):
    if not ThereseFileService.exists(file_path):
        raise Http404('File not found.')
    if not user_can_access_stored_file(request.user, file_path):
        raise Http404('File not found.')
    # Default to attachment; allow inline only for known-safe image/PDF types.
    return ThereseFileService.as_response(file_path, allow_inline=True)
