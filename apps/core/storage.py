"""
Database-backed file storage for all uploaded media.
Works with SQLite and MariaDB/MySQL via Django's ORM.
"""

import mimetypes
import os

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible


@deconstructible
class DatabaseStorage(Storage):
    """Store file content in the StoredFile model instead of the filesystem."""

    def _open(self, name, mode='rb'):
        from .models import StoredFile

        try:
            stored = StoredFile.objects.get(name=name)
        except StoredFile.DoesNotExist as exc:
            raise FileNotFoundError(f'File not found in database: {name}') from exc

        content = bytes(stored.content)
        if 'b' not in mode:
            content = content.decode('utf-8', errors='replace')
        return ContentFile(content, name=stored.original_filename or name)

    def _save(self, name, content):
        from .models import StoredFile

        if hasattr(content, 'chunks'):
            data = b''.join(chunk if isinstance(chunk, bytes) else chunk.encode('utf-8') for chunk in content.chunks())
        else:
            content.seek(0)
            raw = content.read()
            data = raw if isinstance(raw, bytes) else raw.encode('utf-8')

        original = getattr(content, 'name', None) or os.path.basename(name)
        content_type = getattr(content, 'content_type', None) or mimetypes.guess_type(original)[0] or 'application/octet-stream'

        StoredFile.objects.update_or_create(
            name=name,
            defaults={
                'original_filename': os.path.basename(original),
                'content_type': content_type,
                'size': len(data),
                'content': data,
            },
        )
        return name

    def delete(self, name):
        from .models import StoredFile

        if name:
            StoredFile.objects.filter(name=name).delete()

    def exists(self, name):
        from .models import StoredFile

        return bool(name) and StoredFile.objects.filter(name=name).exists()

    def size(self, name):
        from .models import StoredFile

        try:
            return StoredFile.objects.values_list('size', flat=True).get(name=name)
        except StoredFile.DoesNotExist as exc:
            raise FileNotFoundError(f'File not found in database: {name}') from exc

    def url(self, name):
        if not name:
            return ''
        base = settings.MEDIA_URL
        if not base.endswith('/'):
            base = f'{base}/'
        return f'{base}{name}'

    def get_available_name(self, name, max_length=None):
        dir_name, file_name = os.path.split(name)
        file_root, file_ext = os.path.splitext(file_name)
        candidate = name
        counter = 1
        while self.exists(candidate):
            candidate = os.path.join(dir_name, f'{file_root}_{counter}{file_ext}')
            counter += 1
        return candidate