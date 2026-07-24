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


def find_completed_imports_by_hash(kind: str, file_sha256: str):
    """All completed imports of this kind with the same file hash (newest first)."""
    if not file_sha256:
        return DataImportLog.objects.none()
    return (
        DataImportLog.objects.filter(
            kind=kind,
            file_sha256=file_sha256,
            status=DataImportLog.Status.COMPLETED,
        )
        .select_related('uploaded_by')
        .order_by('-created_at')
    )


# Known scope keys written into DataImportLog.summary as scopes=psp,personnel
_SCOPE_KEYS = frozenset({'psp', 'personnel', 'orders'})


def parse_scopes_from_import_summary(summary: str) -> set[str]:
    """
    Parse ``scopes=psp,personnel`` from a DataImportLog.summary string.

    Legacy logs without an explicit scopes= segment are treated as a full
    import of PSP + personnel (orders never auto-enabled).
    """
    text = (summary or '').strip()
    if not text:
        return {'psp', 'personnel'}
    for part in text.split(';'):
        part = part.strip()
        if part.lower().startswith('scopes='):
            val = part.split('=', 1)[1].strip()
            if not val or val.lower() == 'none':
                return set()
            return {s.strip() for s in val.split(',') if s.strip() in _SCOPE_KEYS}
    # Older completed logs: assume both main scopes were imported
    return {'psp', 'personnel'}


def scopes_already_imported_for_hash(kind: str, file_sha256: str) -> set[str]:
    """Union of scopes already successfully imported for this file content hash."""
    already: set[str] = set()
    for log in find_completed_imports_by_hash(kind, file_sha256):
        already |= parse_scopes_from_import_summary(log.summary)
    return already


def remaining_scopes_for_hash(
    kind: str,
    file_sha256: str,
    requested_scopes: set[str] | dict[str, bool] | None,
) -> tuple[set[str], set[str], set[str]]:
    """
    Compare requested scopes against prior completed imports of the same file.

    Returns ``(already, remaining, requested)`` as sets of scope names.
    """
    if isinstance(requested_scopes, dict):
        requested = {k for k, v in requested_scopes.items() if v and k in _SCOPE_KEYS}
    elif requested_scopes is None:
        requested = {'psp', 'personnel'}
    else:
        requested = {s for s in requested_scopes if s in _SCOPE_KEYS}

    already = scopes_already_imported_for_hash(kind, file_sha256)
    remaining = requested - already
    return already & requested, remaining, requested


def effective_report_creation_date(
    *,
    report_created_on: date | None = None,
    file_created_at: datetime | None = None,
) -> date | None:
    """
    Business creation date of a funding report.

    Prefer the sheet date (``angelegt am`` / report_created_on); fall back to
    the OOXML document created timestamp when the sheet date is missing.
    """
    if report_created_on is not None:
        return report_created_on
    if file_created_at is not None:
        if timezone.is_aware(file_created_at):
            return timezone.localtime(file_created_at).date()
        return file_created_at.date()
    return None


def effective_creation_date_from_log(log: DataImportLog) -> date | None:
    return effective_report_creation_date(
        report_created_on=log.report_created_on,
        file_created_at=log.file_created_at,
    )


def latest_completed_report_creation_date(kind: str) -> tuple[date | None, DataImportLog | None]:
    """
    Latest report creation date among completed imports of ``kind``.

    Reports are cumulative (start of PSP → pull date), so only newer (or equal)
    reports should be accepted after an earlier successful import.
    """
    if not kind:
        return None, None
    logs = (
        DataImportLog.objects.filter(
            kind=kind,
            status=DataImportLog.Status.COMPLETED,
        )
        .select_related('uploaded_by')
        .order_by('-created_at')
    )
    best_date: date | None = None
    best_log: DataImportLog | None = None
    for log in logs.iterator(chunk_size=200):
        d = effective_creation_date_from_log(log)
        if d is None:
            continue
        if best_date is None or d > best_date:
            best_date = d
            best_log = log
    return best_date, best_log


def is_report_older_than_last_import(
    kind: str,
    *,
    report_created_on: date | None = None,
    file_created_at: datetime | None = None,
) -> tuple[bool, date | None, DataImportLog | None, date | None]:
    """
    True when this upload's creation date is strictly older than the latest
    completed import for the same kind.

    Returns ``(is_older, upload_date, prior_log, prior_date)``.
    If the upload date cannot be determined, returns False (no block).
    """
    upload_date = effective_report_creation_date(
        report_created_on=report_created_on,
        file_created_at=file_created_at,
    )
    if upload_date is None:
        return False, None, None, None
    prior_date, prior_log = latest_completed_report_creation_date(kind)
    if prior_date is None:
        return False, upload_date, None, None
    if upload_date < prior_date:
        return True, upload_date, prior_log, prior_date
    return False, upload_date, prior_log, prior_date


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
    beleg_from=None,
    beleg_to=None,
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
        beleg_from=beleg_from,
        beleg_to=beleg_to,
        status=status,
        summary=summary or '',
    )
