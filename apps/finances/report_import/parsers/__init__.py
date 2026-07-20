from .base import ParsedPspParent, ParsedReportFile, ReportParser
from .uebersicht import UebersichtPspParser, is_placeholder_cost_center

# Registry for future report kinds (cost center, annual PSP, …).
PARSERS = {
    UebersichtPspParser.report_kind: UebersichtPspParser,
}


def detect_and_parse(file_obj, filename: str) -> ParsedReportFile:
    """
    Detect report type and parse.

    Currently always uses Übersicht PSP parser. Detection hooks can branch
    later (sheet names, headers, annual markers) without changing the UI.
    """
    parser = UebersichtPspParser()
    return parser.parse(file_obj, filename)


__all__ = [
    'PARSERS',
    'ParsedPspParent',
    'ParsedReportFile',
    'ReportParser',
    'UebersichtPspParser',
    'detect_and_parse',
    'is_placeholder_cost_center',
]
