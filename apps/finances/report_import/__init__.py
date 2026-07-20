"""
Third-party funding report import (Excel).

Designed for multi-sheet SAP-style reports. Phase 1 focuses on sheet
``Übersicht`` for non-annual PSP parents. Parsers are structured so cost-center
and annual-recurrence report variants can be added later without rewriting
the preview/commit UI.
"""

from .service import analyze_uploaded_files, apply_import_plan

__all__ = [
    'analyze_uploaded_files',
    'apply_import_plan',
]
