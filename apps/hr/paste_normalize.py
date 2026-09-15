"""Normalize a single Excel/Word clipboard cell for employee-form paste."""

from __future__ import annotations

import re
from datetime import date

from apps.tasks.form_validation import parse_loose_decimal

# Prefer 4-digit years so 15.09.2026 is not read as 15.09.20.
_EU_DATE = re.compile(r'(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4}|\d{2})')
_ISO_DATE = re.compile(r'^(\d{4})-(\d{2})-(\d{2})')


def first_clipboard_cell(text) -> str:
    """First cell of TSV/newline clipboard text. NBSP stripped, trimmed."""
    if text is None:
        return ''
    raw = str(text).replace('\u00a0', ' ').replace('\r\n', '\n').replace('\r', '\n')
    first_line = raw.split('\n', 1)[0]
    first_cell = first_line.split('\t', 1)[0]
    return first_cell.strip()


def looks_like_table(text) -> bool:
    if not text:
        return False
    raw = str(text)
    if '\t' in raw:
        return True
    lines = [ln for ln in raw.replace('\r\n', '\n').replace('\r', '\n').split('\n') if ln.strip()]
    return len(lines) > 1


def normalize_pasted_date(text) -> str:
    """First recognizable EU date in the first cell as DD.MM.YYYY, else ''."""
    cell = first_clipboard_cell(text)
    if not cell:
        return ''
    iso = _ISO_DATE.match(cell)
    if iso:
        try:
            d = date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            d = None
        if d:
            return d.strftime('%d.%m.%Y')
    match = _EU_DATE.search(cell)
    if not match:
        return ''
    day = int(match.group(1))
    month = int(match.group(2))
    year_part = match.group(3)
    year = 2000 + int(year_part) if len(year_part) == 2 else int(year_part)
    try:
        d = date(year, month, day)
    except ValueError:
        return ''
    if d.day != day or d.month != month or d.year != year:
        return ''
    return d.strftime('%d.%m.%Y')


def normalize_pasted_decimal(text) -> str:
    """German/Excel decimal in the first cell as a Django-style decimal string."""
    cell = first_clipboard_cell(text)
    if not cell:
        return ''
    parsed = parse_loose_decimal(cell)
    if parsed is None:
        return ''
    return str(parsed).strip()
