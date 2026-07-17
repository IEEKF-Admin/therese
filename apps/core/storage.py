"""
Database-backed file storage for all uploaded media.
Works with SQLite and MariaDB/MySQL via Django's ORM.
"""

import mimetypes
import os
import uuid

from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible


def _posix_join(*parts):
    """Join path parts with forward slashes (stable storage keys on all OSes)."""
    cleaned = [str(p).replace('\\', '/').strip('/') for p in parts if p]
    return '/'.join(cleaned)


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
        # Keep only the basename; truncate to StoredFile.original_filename max_length.
        original_basename = os.path.basename(str(original).replace('\\', '/'))[:255]
        content_type = (
            getattr(content, 'content_type', None)
            or mimetypes.guess_type(original_basename)[0]
            or 'application/octet-stream'
        )

        StoredFile.objects.update_or_create(
            name=name,
            defaults={
                'original_filename': original_basename or os.path.basename(name),
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
        """
        Return a free storage key.

        Django FileFields default to max_length=100 for the stored path. Long
        original filenames (plus upload_to prefix) therefore fail unless we
        rename. When the proposed name is too long or already taken, use a
        short UUID basename and keep the directory + extension. The human
        filename remains in StoredFile.original_filename for downloads/UI.
        """
        name = str(name or '').replace('\\', '/')
        dir_name, file_name = name.rsplit('/', 1) if '/' in name else ('', name)
        _file_root, file_ext = os.path.splitext(file_name)

        def fits(candidate):
            return max_length is None or len(candidate) <= max_length

        if fits(name) and not self.exists(name):
            return name

        # Collision or oversize: rename to a short unique basename.
        for _ in range(100):
            short_basename = f'{uuid.uuid4().hex}{file_ext}'
            candidate = _posix_join(dir_name, short_basename) if dir_name else short_basename
            if fits(candidate) and not self.exists(candidate):
                return candidate

        # Directory prefix alone already exceeds max_length (misconfigured field).
        raise SuspiciousFileOperation(
            f'Storage can not find an available filename for "{name}". '
            f'Please make sure that the corresponding file field allows sufficient "max_length".'
        )
