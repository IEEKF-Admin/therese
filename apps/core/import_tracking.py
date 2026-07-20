"""
Helpers for data-import audit logging and duplicate-file detection.
"""

from __future__ import annotations

import hashlib
import re
import zipfile
from datetime import date, datetime
from io import BytesIO
from xml.etree import ElementTree as ET

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.core.models import DataImportLog

_NS = {
    'cp': 'http://schemas.openxmlformats.org/package/2006/metadata/core-properties',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'dcterms': 'http://purl.org/dc/terms/',
    'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
}
_DATE_RE = re.compile(r'(\d{1,2})\.(\d{1,2})\.(\d{4})')


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def extract_xlsx_document_timestamps(content: bytes) -> tuple[datetime | None, datetime | None]:
    """
    Read created/modified timestamps from OOXML docProps/core.xml.

    Returns timezone-aware datetimes when possible.
    """
    created = None
    modified = None
    try:
        with zipfile.ZipFile(BytesIO(content), 'r') as zf:
            if 'docProps/core.xml' not in zf.namelist():
                return None, None
            root = ET.fromstring(zf.read('docProps/core.xml'))
    except (zipfile.BadZipFile, ET.ParseError, KeyError, OSError):
        return None, None

    created_el = root.find('dcterms:created', _NS)
    modified_el = root.find('dcterms:modified', _NS)
    created = _parse_ooxml_datetime(created_el.text if created_el is not None else None)
    modified = _parse_ooxml_datetime(modified_el.text if modified_el is not None else None)
    return created, modified


def _parse_ooxml_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    dt = parse_datetime(text)
    if dt is None:
        # Fallback: bare ISO without timezone
        try:
            dt = datetime.fromisoformat(text.replace('Z', '+00:00'))
        except ValueError:
            return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.utc)
    return dt


def parse_german_date_from_text(value) -> date | None:
    """Parse first DD.MM.YYYY date from a label string such as 'angelegt am: 23.10.2025'."""
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    match = _DATE_RE.search(str(value))
    if not match:
        return None
    day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
    try:
        return date(year, month, day)
    except ValueError:
        return None


def find_completed_import_by_hash(kind: str, file_sha256: str) -> DataImportLog | None:
    """Return the latest completed import of this kind with the same file hash."""
    if not file_sha256:
        return None
    return (
        DataImportLog.objects.filter(
            kind=kind,
            file_sha256=file_sha256,
            status=DataImportLog.Status.COMPLETED,
        )
        .select_related('uploaded_by')
        .order_by('-created_at')
        .first()
    )


def record_data_import(
    *,
    kind: str,
    uploaded_by,
    original_filename: str = '',
    file_sha256: str = '',
    file_size: int = 0,
    file_created_at=None,
    file_modified_at=None,
    report_created_on=None,
    status: str = DataImportLog.Status.COMPLETED,
    summary: str = '',
) -> DataImportLog:
    return DataImportLog.objects.create(
        kind=kind,
        uploaded_by=uploaded_by if getattr(uploaded_by, 'is_authenticated', False) else None,
        original_filename=(original_filename or '')[:500],
        file_sha256=file_sha256 or '',
        file_size=file_size or 0,
        file_created_at=file_created_at,
        file_modified_at=file_modified_at,
        report_created_on=report_created_on,
        status=status,
        summary=summary or '',
    )
