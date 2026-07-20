"""
Abstract report parser interface.

Future report kinds (cost-center reports, annual-recurrence PSPs, extra sheets)
should implement the same shape so analyze/commit stay generic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


@dataclass
class ParsedContact:
    last_name: str
    first_name: str = ''


@dataclass
class ParsedCostTypeAmounts:
    """Amounts for one cost-type suffix at the parent PSP."""
    suffix: str
    label: str = ''
    approved_budget: Decimal | None = None  # Freigegebenes Budget -> year estimate
    verfuegt: Decimal | None = None  # Verfügt -> true yearly spending
    obligo: Decimal | None = None  # Obligo column
    personal_obligo: Decimal | None = None  # Personalobligo column


@dataclass
class ParsedPspParent:
    """
    One parent PSP project extracted from a report file.

    Child (.1–.9) rows are folded into cost_types; parent budget row is ignored.
    """
    wbs_code: str
    source_filename: str
    third_party_funder_identifier: str = ''
    cost_center_code: str = ''
    cost_center_is_placeholder: bool = False
    period_start: date | None = None
    period_end: date | None = None
    contact: ParsedContact | None = None
    # From sheet content, e.g. "angelegt am: 23.10.2025"
    report_created_on: date | None = None
    cost_types: dict[str, ParsedCostTypeAmounts] = field(default_factory=dict)
    last_booking_years: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return _json_safe(asdict(self))


@dataclass
class ParsedReportFile:
    """Result of parsing one Excel workbook (any supported report kind)."""
    filename: str
    report_kind: str  # e.g. 'psp_uebersicht', later 'cost_center_uebersicht', ...
    parents: list[ParsedPspParent] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return _json_safe(asdict(self))


class ReportParser(ABC):
    """Base class for sheet/report parsers."""

    report_kind: str = 'unknown'

    @abstractmethod
    def parse(self, file_obj, filename: str) -> ParsedReportFile:
        """Parse an uploaded file-like object into structured data."""
