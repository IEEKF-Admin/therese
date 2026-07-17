"""
Central API for reading and serving files stored in the database.
Application code can use this without caring about the active database engine.
"""

import mimetypes

from django.core.files.storage import default_storage
from django.http import FileResponse, Http404, HttpResponse

from .http_utils import content_disposition
from .models import StoredFile

# Safe inline types only (never HTML/SVG).
_INLINE_CONTENT_TYPES = frozenset({
    'image/jpeg',
    'image/png',
    'image/gif',
    'image/webp',
    'application/pdf',
})


class ThereseFileService:
    @staticmethod
    def save(name, content):
        return default_storage.save(name, content)

    @staticmethod
    def open(name, mode='rb'):
        return default_storage.open(name, mode)

    @staticmethod
    def delete(name):
        default_storage.delete(name)

    @staticmethod
    def exists(name):
        return default_storage.exists(name)

    @staticmethod
    def url(name):
        return default_storage.url(name)

    @staticmethod
    def get_stored_file(name):
        try:
            return StoredFile.objects.get(name=name)
        except StoredFile.DoesNotExist as exc:
            raise Http404('File not found.') from exc

    @staticmethod
    def as_response(name, *, filename=None, as_attachment=None, allow_inline=False):
        stored = ThereseFileService.get_stored_file(name)
        content = bytes(stored.content)
        display_name = filename or stored.original_filename or name.rsplit('/', 1)[-1]

        guessed, _ = mimetypes.guess_type(display_name)
        content_type = stored.content_type or guessed or 'application/octet-stream'
        # Never trust client-supplied HTML/SVG types for inline display.
        if content_type in ('text/html', 'image/svg+xml', 'application/xhtml+xml'):
            content_type = 'application/octet-stream'
            allow_inline = False

        if as_attachment is None:
            if allow_inline and content_type in _INLINE_CONTENT_TYPES:
                as_attachment = False
            else:
                as_attachment = True

        response = HttpResponse(content, content_type=content_type)
        response['Content-Disposition'] = content_disposition(
            display_name, as_attachment=as_attachment,
        )
        response['Content-Length'] = len(content)
        response['X-Content-Type-Options'] = 'nosniff'
        return response

    @staticmethod
    def as_file_response(name, *, filename=None, as_attachment=True):
        stored = ThereseFileService.get_stored_file(name)
        display_name = filename or stored.original_filename or name.rsplit('/', 1)[-1]
        return FileResponse(
            ThereseFileService.open(name, 'rb'),
            as_attachment=as_attachment,
            filename=display_name,
        )
