from .base import ParsedPspParent, ParsedReportFile, ReportParser
from .gesamtbericht import GesamtberichtPspParser, looks_like_gesamtbericht
from .uebersicht import (
    UebersichtPspParser,
    is_placeholder_cost_center,
    load_uebersicht_rows,
)

# Registry for future report kinds (cost center, annual PSP, …).
PARSERS = {
    UebersichtPspParser.report_kind: UebersichtPspParser,
    GesamtberichtPspParser.report_kind: GesamtberichtPspParser,
}


def detect_and_parse(file_obj, filename: str) -> ParsedReportFile:
    """Detect Einzelbericht vs Gesamtbericht and parse sheet Übersicht."""
    data = file_obj.read() if hasattr(file_obj, 'read') else file_obj
    rows, _names, error = load_uebersicht_rows(data)
    if error:
        kind = (
            GesamtberichtPspParser.report_kind
            if 'gesamtbericht' in (filename or '').lower()
            else UebersichtPspParser.report_kind
        )
        return ParsedReportFile(filename=filename, report_kind=kind, errors=[error])
    if looks_like_gesamtbericht(filename, rows):
        return GesamtberichtPspParser().parse_rows(rows, filename)
    return UebersichtPspParser().parse_rows(rows, filename)


__all__ = [
    'PARSERS',
    'GesamtberichtPspParser',
    'ParsedPspParent',
    'ParsedReportFile',
    'ReportParser',
    'UebersichtPspParser',
    'detect_and_parse',
    'is_placeholder_cost_center',
    'looks_like_gesamtbericht',
]
