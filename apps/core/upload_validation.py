"""Shared upload validation (size, extension, magic bytes)."""

from __future__ import annotations

import os

from django.core.exceptions import ValidationError

MAX_DEFAULT_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_QUOTE_UPLOAD_BYTES = 25 * 1024 * 1024

PDF_EXT = {'.pdf'}
IMAGE_EXT = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
DOC_ATTACHMENT_EXT = PDF_EXT | IMAGE_EXT | {'.doc', '.docx', '.xls', '.xlsx', '.txt'}

_MAGIC = {
    b'%PDF': 'pdf',
    b'\xff\xd8\xff': 'jpeg',
    b'\x89PNG\r\n\x1a\n': 'png',
    b'GIF87a': 'gif',
    b'GIF89a': 'gif',
    b'RIFF': 'webp',  # WebP is RIFF....WEBP
}


def _read_header(uploaded_file, n=16):
    pos = uploaded_file.tell() if hasattr(uploaded_file, 'tell') else 0
    header = uploaded_file.read(n)
    if hasattr(uploaded_file, 'seek'):
        uploaded_file.seek(pos)
    return header or b''


def validate_upload(
    uploaded_file,
    *,
    allowed_extensions,
    max_bytes=MAX_DEFAULT_UPLOAD_BYTES,
    require_magic=True,
):
    if not uploaded_file:
        return
    size = getattr(uploaded_file, 'size', None)
    if size is not None and size > max_bytes:
        raise ValidationError(f'File must be {max_bytes // (1024 * 1024)} MB or smaller.')

    name = getattr(uploaded_file, 'name', '') or ''
    ext = os.path.splitext(name)[1].lower()
    if ext not in allowed_extensions:
        raise ValidationError(
            f'Allowed file types: {", ".join(sorted(allowed_extensions))}.'
        )

    if not require_magic:
        return

    header = _read_header(uploaded_file)
    if ext == '.pdf':
        if not header.startswith(b'%PDF'):
            raise ValidationError('Invalid PDF file.')
    elif ext in {'.jpg', '.jpeg'}:
        if not header.startswith(b'\xff\xd8\xff'):
            raise ValidationError('Invalid JPEG image.')
    elif ext == '.png':
        if not header.startswith(b'\x89PNG\r\n\x1a\n'):
            raise ValidationError('Invalid PNG image.')
    elif ext == '.gif':
        if not header.startswith(b'GIF87a') and not header.startswith(b'GIF89a'):
            raise ValidationError('Invalid GIF image.')
    elif ext == '.webp':
        if not (header.startswith(b'RIFF') and b'WEBP' in header[:16]):
            raise ValidationError('Invalid WebP image.')
