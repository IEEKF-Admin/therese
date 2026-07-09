"""
Central API for reading and serving files stored in the database.
Application code can use this without caring about the active database engine.
"""

from django.core.files.storage import default_storage
from django.http import FileResponse, Http404, HttpResponse

from .models import StoredFile


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
    def as_response(name, *, filename=None, as_attachment=None):
        stored = ThereseFileService.get_stored_file(name)
        content = bytes(stored.content)
        content_type = stored.content_type or 'application/octet-stream'
        display_name = filename or stored.original_filename or name.rsplit('/', 1)[-1]

        if as_attachment is None:
            as_attachment = not content_type.startswith('image/')

        disposition = 'attachment' if as_attachment else 'inline'
        response = HttpResponse(content, content_type=content_type)
        response['Content-Disposition'] = f'{disposition}; filename="{display_name}"'
        response['Content-Length'] = len(content)
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