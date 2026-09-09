"""
Parser for Drittmittel-Gesamtbericht (all PSP elements on one Übersicht sheet).

Layout: identity table (Projekt / Kostenstelle / Text / Projektdefinition /
Projektende) then repeating mini budget tables. Thinner than a single-PSP
report: no Ansprechpartner, Projektlaufzeit start, or Personalkosten sheet.
"""

from __future__ import annotations

import re
from datetime import date

from apps.finances.report_import.parsers.base import (
    ParsedCostTypeAmounts,
    ParsedPspParent,
    ParsedReportFile,
    ReportParser,
)
from apps.finances.report_import.parsers.uebersicht import (
    _cell_str,
    _parse_decimal,
    _parse_german_date,
    is_placeholder_cost_center,
    load_uebersicht_rows,
    split_wbs_code,
)
from apps.finances.report_import.suffix_map import COST_TYPE_LABELS, SUFFIX_TO_COST_TYPE

_FILENAME_DATE_RE = re.compile(r'gesamtbericht(\d{2})(\d{2})(\d{2})', re.IGNORECASE)


def report_date_from_filename(filename: str) -> date | None:
    """``Gesamtbericht070926`` → 2026-09-07."""
    match = _FILENAME_DATE_RE.search(filename or '')
    if not match:
        return None
    day, month, year = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    try:
        return date(2000 + year, month, day)
    except ValueError:
        return None


def looks_like_gesamtbericht(filename: str, rows: list[list] | None) -> bool:
    if 'gesamtbericht' in (filename or '').lower():
        return True
    if not rows:
        return False
    for row in rows[:40]:
        cells = {_cell_str(c).lower() for c in row if _cell_str(c)}
        if {'projekt', 'kostenstelle', 'text', 'projektdefinition'} <= cells:
            return True
    return False


def _header_map(row: list) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for idx, cell in enumerate(row):
        key = _cell_str(cell).lower()
        if key:
            mapping[key] = idx
    return mapping


def _col(mapping: dict[str, int], *names: str) -> int | None:
    for name in names:
        if name in mapping:
            return mapping[name]
    return None


def _is_identity_header(row: list) -> bool:
    cells = {_cell_str(c).lower() for c in row if _cell_str(c)}
    return {'projekt', 'kostenstelle', 'text', 'projektdefinition'} <= cells


def _is_budget_header(row: list) -> bool:
    cells = [_cell_str(c).lower() for c in row]
    return (
        'projekt' in cells
        and any('bezeichnung' in c for c in cells)
        and any('budget' in c for c in cells)
    )


def _looks_like_wbs(code: str) -> bool:
    if not code or code.lower() in {'projekt', 'summe', 'summe:', 'psp'}:
        return False
    return bool(re.search(r'\d', code))


class GesamtberichtPspParser(ReportParser):
    report_kind = 'psp_gesamtbericht'

    def parse(self, file_obj, filename: str) -> ParsedReportFile:
        result = ParsedReportFile(filename=filename, report_kind=self.report_kind)
        rows, _names, error = load_uebersicht_rows(file_obj)
        if error:
            result.errors.append(error)
            return result
        return self.parse_rows(rows, filename)

    def parse_rows(self, rows: list[list], filename: str) -> ParsedReportFile:
        result = ParsedReportFile(filename=filename, report_kind=self.report_kind)
        report_created_on = report_date_from_filename(filename)

        identity_header_idx = None
        first_budget_idx = None
        for r_idx, row in enumerate(rows):
            if identity_header_idx is None and _is_identity_header(row):
                identity_header_idx = r_idx
                continue
            if _is_budget_header(row):
                first_budget_idx = r_idx
                break

        if identity_header_idx is None:
            result.errors.append(
                'Gesamtbericht identity header '
                '(Projekt / Kostenstelle / Text / Projektdefinition) not found.'
            )
            return result

        id_map = _header_map(rows[identity_header_idx])
        col_code = _col(id_map, 'projekt')
        col_cc = _col(id_map, 'kostenstelle')
        col_text = _col(id_map, 'text')
        col_def = _col(id_map, 'projektdefinition')
        col_end = _col(id_map, 'projektende')
        if col_code is None:
            result.errors.append('Gesamtbericht identity table has no Projekt column.')
            return result

        identity_end = first_budget_idx if first_budget_idx is not None else len(rows)
        parent_rows: dict[str, dict] = {}
        child_rows: dict[str, list[dict]] = {}

        for row in rows[identity_header_idx + 1:identity_end]:
            code = _cell_str(row[col_code] if col_code < len(row) else None)
            if not _looks_like_wbs(code):
                continue
            rec = {
                'code': code,
                'cc': _cell_str(row[col_cc] if col_cc is not None and col_cc < len(row) else None),
                'text': _cell_str(row[col_text] if col_text is not None and col_text < len(row) else None),
                'funder': _cell_str(row[col_def] if col_def is not None and col_def < len(row) else None),
                'period_end': (
                    _parse_german_date(row[col_end])
                    if col_end is not None and col_end < len(row)
                    else None
                ),
            }
            parent_code, suffix = split_wbs_code(code)
            if suffix:
                child_rows.setdefault(parent_code, []).append(rec)
                parent_rows.setdefault(parent_code, {})
            else:
                parent_rows[parent_code] = rec

        cost_types_by_parent: dict[str, dict[str, ParsedCostTypeAmounts]] = {}
        budget_titles: dict[str, str] = {}
        if first_budget_idx is not None:
            current_map = None
            for row in rows[first_budget_idx:]:
                if _is_budget_header(row):
                    current_map = _header_map(row)
                    continue
                if current_map is None:
                    continue
                parsed = self._extract_budget_row(row, current_map)
                if not parsed:
                    continue
                parent_code, suffix = split_wbs_code(parsed['code'])
                if not suffix:
                    if parsed.get('designation'):
                        budget_titles.setdefault(parent_code, parsed['designation'])
                    continue
                if suffix not in SUFFIX_TO_COST_TYPE:
                    continue
                cost_types_by_parent.setdefault(parent_code, {})[suffix] = ParsedCostTypeAmounts(
                    suffix=suffix,
                    label=parsed.get('designation') or COST_TYPE_LABELS.get(suffix, ''),
                    approved_budget=parsed.get('approved_budget'),
                    verfuegt=parsed.get('verfuegt'),
                    obligo=parsed.get('obligo'),
                    personal_obligo=parsed.get('personal_obligo'),
                )

        parent_codes = list(parent_rows.keys())
        for code in cost_types_by_parent:
            if code not in parent_rows:
                parent_codes.append(code)
                parent_rows[code] = {}

        if not parent_codes:
            result.errors.append('No parent PSP codes found in Gesamtbericht.')
            return result

        for parent_code in parent_codes:
            ident = parent_rows.get(parent_code) or {}
            title = (ident.get('text') or budget_titles.get(parent_code) or '').strip()
            funder = (ident.get('funder') or '').strip()
            parent_cc = ident.get('cc') or ''
            if not parent_cc or is_placeholder_cost_center(parent_cc):
                for child in child_rows.get(parent_code, []):
                    cc = child.get('cc') or ''
                    if cc and not is_placeholder_cost_center(cc):
                        parent_cc = cc
                        break
            cost_types = cost_types_by_parent.get(parent_code) or {}
            warnings = []
            if not cost_types:
                warnings.append(
                    'No cost-type child rows (.1–.9) in budget tables; '
                    'financial snapshots will not be written.'
                )
            if is_placeholder_cost_center(parent_cc):
                warnings.append(
                    f'Cost center from file looks invalid/placeholder: {parent_cc!r}'
                )
            if ident.get('code') is None and not ident.get('text'):
                warnings.append('Parent row missing in identity table; title/funder may be incomplete.')

            result.parents.append(ParsedPspParent(
                wbs_code=parent_code,
                source_filename=filename,
                title=title,
                third_party_funder_identifier=funder,
                cost_center_code=parent_cc,
                cost_center_is_placeholder=is_placeholder_cost_center(parent_cc),
                period_end=ident.get('period_end'),
                report_created_on=report_created_on,
                cost_types=cost_types,
                warnings=warnings,
            ))

        result.notes.append(
            'Parsed Gesamtbericht: master data from identity table; '
            'amounts from cost-type child rows only (parent totals ignored).'
        )
        return result

    def _extract_budget_row(self, row: list, header_map: dict[str, int]) -> dict | None:
        col_code = _col(header_map, 'projekt')
        if col_code is None:
            return None
        code = _cell_str(row[col_code] if col_code < len(row) else None)
        if not _looks_like_wbs(code):
            return None

        col_name = _col(header_map, 'psp bezeichnung')
        if col_name is None:
            for key, idx in header_map.items():
                if 'bezeichnung' in key:
                    col_name = idx
                    break
        col_budget = None
        col_obligo = None
        col_personal = None
        col_verfuegt = None
        for key, idx in header_map.items():
            if 'freigegebenes' in key and 'budget' in key:
                col_budget = idx
            elif key == 'obligo':
                col_obligo = idx
            elif 'personalobligo' in key:
                col_personal = idx
            elif key in {'verfügt', 'verfuegt'}:
                col_verfuegt = idx

        def _val(col: int | None):
            if col is None or col >= len(row):
                return None
            return row[col]

        return {
            'code': code,
            'designation': _cell_str(_val(col_name)),
            'approved_budget': _parse_decimal(_val(col_budget)),
            'obligo': _parse_decimal(_val(col_obligo)),
            'personal_obligo': _parse_decimal(_val(col_personal)),
            'verfuegt': _parse_decimal(_val(col_verfuegt)),
        }
