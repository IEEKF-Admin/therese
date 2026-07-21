"""
Parser for sheet ``Personalkosten`` of third-party funding reports.

Phase 1: only cost type (Kostenart) 60003000, positive Personalkosten amounts.
Per Personalnummer keep the row with the latest Belegdatum.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO

from openpyxl import load_workbook

from apps.finances.report_import.parsers.uebersicht import (
    _cell_str,
    _parse_german_date,
    split_wbs_code,
)

# Currently only this payroll cost type is relevant for salary matching.
RELEVANT_KOSTENART = '60003000'


@dataclass
class ParsedPersonalkostenEntry:
    personalnummer: str
    kostenart: str
    personalkosten: Decimal
    belegdatum: date | None
    psp_code: str
    parent_psp_code: str
    source_filename: str


def _parse_decimal(value) -> Decimal | None:
    if value is None or value == '':
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = str(value).strip().replace(' ', '').replace(',', '.')
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _normalize_personalnummer(value) -> str:
    text = _cell_str(value)
    if not text:
        return ''
    # Excel may store as number → "50001094.0"
    if text.endswith('.0') and text[:-2].isdigit():
        text = text[:-2]
    return text.strip()


def _normalize_kostenart(value) -> str:
    text = _cell_str(value)
    if not text:
        return ''
    if text.endswith('.0') and text[:-2].isdigit():
        text = text[:-2]
    return text.strip()


def _detect_personalkosten_layout(rows: list) -> tuple[int, dict]:
    """
    Return (header_row_index, column_map) for a Personalkosten sheet.
    """
    header_idx = None
    col: dict = {}
    for i, row in enumerate(rows[:15]):
        cells = [_cell_str(c).lower().replace('\n', ' ') for c in row]
        joined = ' '.join(cells)
        if 'personal' in joined and 'kostenart' in joined and 'personalkosten' in joined:
            header_idx = i
            for j, c in enumerate(cells):
                if 'psp' in c and 'bezeichnung' not in c:
                    col['psp'] = j
                elif c == 'kostenart' or (
                    c.startswith('kostenart') and 'bezeichnung' not in c and 'koa' not in c
                ):
                    col.setdefault('kostenart', j)
                elif 'beleg' in c and 'datum' in c:
                    col['belegdatum'] = j
                elif 'personal' in c and 'nummer' in c:
                    col['personalnummer'] = j
                elif c.replace(' ', '') in {'personalkosten', 'personalkosten'}:
                    col['personalkosten'] = j
                elif 'personalkosten' in c:
                    col['personalkosten'] = j
            break

    if header_idx is None:
        # Fallback to known layout: B=PSP, C=Kostenart, G=Belegdatum, H=Personalnummer, I=Personalkosten
        header_idx = 1
        col = {
            'psp': 1,
            'kostenart': 2,
            'belegdatum': 6,
            'personalnummer': 7,
            'personalkosten': 8,
        }
        if rows and 'psp' in _cell_str(rows[0][1] if len(rows[0]) > 1 else '').lower():
            header_idx = 0

    required = ('psp', 'kostenart', 'personalnummer', 'personalkosten')
    if not all(k in col for k in required):
        col = {
            'psp': 1,
            'kostenart': 2,
            'belegdatum': 6,
            'personalnummer': 7,
            'personalkosten': 8,
        }
        header_idx = 1

    return header_idx, col


def extract_beleg_date_range(file_bytes: bytes) -> tuple[date | None, date | None]:
    """
    Heuristic coverage window from Personalkosten column Belegdatum.

    Scans **all** data rows with a parseable Belegdatum (not only Kostenart
    60003000 / latest-per-employee). Returns (min_date, max_date) or (None, None).
    """
    try:
        wb = load_workbook(BytesIO(file_bytes), data_only=True, read_only=True)
    except Exception:  # noqa: BLE001
        return None, None

    try:
        if 'Personalkosten' not in wb.sheetnames:
            return None, None
        ws = wb['Personalkosten']
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
    finally:
        wb.close()

    if not rows:
        return None, None

    header_idx, col = _detect_personalkosten_layout(rows)
    beleg_idx = col.get('belegdatum')
    if beleg_idx is None:
        return None, None

    dates: list[date] = []
    for row in rows[header_idx + 1 :]:
        if not row or beleg_idx >= len(row):
            continue
        d = _parse_german_date(row[beleg_idx])
        if d is not None:
            dates.append(d)

    if not dates:
        return None, None
    return min(dates), max(dates)


def parse_personalkosten_sheet(file_bytes: bytes, filename: str) -> list[ParsedPersonalkostenEntry]:
    """
    Parse Personalkosten sheet; return latest positive 60003000 row per Personalnummer.
    """
    try:
        wb = load_workbook(BytesIO(file_bytes), data_only=True, read_only=True)
    except Exception:  # noqa: BLE001
        return []

    try:
        if 'Personalkosten' not in wb.sheetnames:
            return []
        ws = wb['Personalkosten']
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
    finally:
        wb.close()

    if not rows:
        return []

    header_idx, col = _detect_personalkosten_layout(rows)

    best_by_personal: dict[str, ParsedPersonalkostenEntry] = {}

    for row in rows[header_idx + 1 :]:
        if not row:
            continue

        def get(key, default=None):
            idx = col.get(key)
            if idx is None or idx >= len(row):
                return default
            return row[idx]

        kostenart = _normalize_kostenart(get('kostenart'))
        if kostenart != RELEVANT_KOSTENART:
            continue

        amount = _parse_decimal(get('personalkosten'))
        if amount is None or amount <= 0:
            continue

        personalnummer = _normalize_personalnummer(get('personalnummer'))
        if not personalnummer:
            continue

        psp_code = _cell_str(get('psp'))
        if not psp_code:
            # sometimes PSP only on first row of a group — skip incomplete
            continue
        parent, _suffix = split_wbs_code(psp_code)

        beleg = None
        if 'belegdatum' in col:
            beleg = _parse_german_date(get('belegdatum'))

        entry = ParsedPersonalkostenEntry(
            personalnummer=personalnummer,
            kostenart=kostenart,
            personalkosten=amount,
            belegdatum=beleg,
            psp_code=psp_code,
            parent_psp_code=parent,
            source_filename=filename,
        )

        prev = best_by_personal.get(personalnummer)
        if prev is None:
            best_by_personal[personalnummer] = entry
            continue
        # Prefer latest Belegdatum; if equal/missing keep higher amount then existing
        prev_d = prev.belegdatum or date.min
        new_d = entry.belegdatum or date.min
        if new_d > prev_d:
            best_by_personal[personalnummer] = entry
        elif new_d == prev_d and entry.personalkosten > prev.personalkosten:
            best_by_personal[personalnummer] = entry

    return list(best_by_personal.values())
