"""
Analyze uploaded third-party funding reports and apply a confirmed import plan.

Preview is session-JSON based: analyze → user confirms decisions → commit.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction

from apps.core.import_tracking import (
    extract_xlsx_document_timestamps,
    find_completed_import_by_hash,
    parse_scopes_from_import_summary,
    record_data_import,
    remaining_scopes_for_hash,
    scopes_already_imported_for_hash,
    sha256_bytes,
)
from apps.core.models import DataImportLog
from apps.finances.models import (
    ContactPerson,
    CostCenter,
    WBSElement,
    WBSElementObligo,
    WBSElementTrueYearlySpending,
    WBSElementYearEstimate,
)
from apps.finances.psp_cost_types import PSP_COST_TYPE_AMOUNT_FIELDS
from apps.finances.report_import.parsers import detect_and_parse
from apps.finances.report_import.parsers.personalkosten import (
    extract_beleg_date_range,
    parse_personalkosten_sheet,
)
from apps.finances.report_import.personnel_match import (
    BLOCKING_PERSONNEL_STATUSES,
    apply_personnel_decisions,
    build_personnel_checks,
    decision_key_for,
)
from apps.finances.report_import.suffix_map import SUFFIX_TO_COST_TYPE


def _dec(value) -> Decimal | None:
    if value is None or value == '':
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _date(value) -> date | None:
    if value is None or value == '':
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def cost_center_lookup_candidates(code: str) -> list[str]:
    """
    Codes to try when matching a file cost center to the database.

    Excel often uses SAP-style ``0001/991000`` while THERESE may already store
    only the local part ``991000`` (or vice versa).
    """
    raw = (code or '').strip()
    if not raw:
        return []
    candidates = [raw]
    if '/' in raw:
        suffix = raw.rsplit('/', 1)[-1].strip()
        if suffix and suffix not in candidates:
            candidates.append(suffix)
    return candidates


def find_cost_center(code: str) -> CostCenter | None:
    """Find an existing cost center by exact or prefix-stripped code."""
    candidates = cost_center_lookup_candidates(code)
    if not candidates:
        return None
    for candidate in candidates:
        match = CostCenter.objects.filter(cost_center=candidate).first()
        if match:
            return match
    # Also: DB has ``0001/991000`` while file only has ``991000``
    primary = candidates[0]
    if '/' not in primary:
        match = (
            CostCenter.objects.filter(cost_center__endswith=f'/{primary}')
            .order_by('cost_center')
            .first()
        )
        if match:
            return match
    return None


def get_or_create_cost_center(code: str) -> tuple[CostCenter, bool]:
    """
    Resolve a cost center without duplicating prefix variants.

    If ``0001/991000`` is imported and ``991000`` already exists, reuses it.
    Creates only when no flexible match is found (stored under the file code).
    """
    existing = find_cost_center(code)
    if existing:
        return existing, False
    raw = (code or '').strip()
    if not raw:
        raise ValueError('Cost center code is empty.')
    return CostCenter.objects.get_or_create(cost_center=raw)


# Import scope keys (orders reserved for a later PO import pass).
SCOPE_PSP = 'psp'
SCOPE_PERSONNEL = 'personnel'
SCOPE_ORDERS = 'orders'
AVAILABLE_SCOPES = (SCOPE_PSP, SCOPE_PERSONNEL, SCOPE_ORDERS)


def normalize_import_scopes(raw=None) -> dict[str, bool]:
    """
    Normalize scope flags.

    ``raw`` may be:
    - None → defaults (PSP + personnel on; orders always off)
    - list/set of scope names
    - dict with ``scope_psp`` / ``scope_personnel`` (form POST) or
      ``psp`` / ``personnel`` booleans
    """
    if raw is None:
        return {
            SCOPE_PSP: True,
            SCOPE_PERSONNEL: True,
            SCOPE_ORDERS: False,
        }
    if isinstance(raw, (list, tuple, set)):
        selected = set(raw)
        return {
            SCOPE_PSP: SCOPE_PSP in selected,
            SCOPE_PERSONNEL: SCOPE_PERSONNEL in selected,
            SCOPE_ORDERS: False,
        }
    get = raw.get
    # Form POST uses scope_psp / scope_personnel checkboxes
    if 'scope_psp' in raw or 'scope_personnel' in raw or 'scope_orders' in raw:
        return {
            SCOPE_PSP: _truthy(get('scope_psp')),
            SCOPE_PERSONNEL: _truthy(get('scope_personnel')),
            SCOPE_ORDERS: False,
        }
    return {
        SCOPE_PSP: _truthy(get(SCOPE_PSP, True)),
        SCOPE_PERSONNEL: _truthy(get(SCOPE_PERSONNEL, True)),
        SCOPE_ORDERS: False,
    }


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {'1', 'true', 'on', 'yes', 'y'}


def scope_enabled(plan: dict, scope: str) -> bool:
    scopes = plan.get('import_scopes') or normalize_import_scopes(None)
    return bool(scopes.get(scope))


def analyze_uploaded_files(
    files,
    import_year: int,
    snapshot_date: date | None = None,
    import_scopes=None,
) -> dict:
    """
    Parse one or more uploaded files and build a preview plan against the DB.

    ``files``: iterable of Django UploadedFile (or file-like with .name).
    ``import_scopes``: which areas to update (psp / personnel / orders).
    """
    scopes = normalize_import_scopes(import_scopes)
    if not scopes[SCOPE_PSP] and not scopes[SCOPE_PERSONNEL]:
        return {
            'import_year': import_year,
            'snapshot_date': (snapshot_date or date.today()).isoformat(),
            'import_kind': DataImportLog.Kind.THIRD_PARTY_FUNDING_REPORT,
            'import_scopes': scopes,
            'files': [],
            'upload_meta': [],
            'parents': [],
            'personnel_checks': [],
            'global_warnings': [],
            'has_blocking_errors': True,
            'has_duplicate_files': False,
            'requires_year_confirmation': False,
            'requires_snapshot_update_option': False,
            'requires_personnel_decisions': False,
            'requires_personnel_resolution': False,
            'blocking_personnel_checks': [],
            'scope_error': (
                'Bitte mindestens einen Import-Bereich wählen '
                '(PSP-Element und/oder Personaldaten).'
            ),
        }

    snapshot_date = snapshot_date or date.today()
    file_results = []
    parents: list[dict] = []
    upload_meta = []
    kind = DataImportLog.Kind.THIRD_PARTY_FUNDING_REPORT

    for uploaded in files:
        filename = getattr(uploaded, 'name', 'upload.xlsx') or 'upload.xlsx'
        if hasattr(uploaded, 'open'):
            uploaded.open('rb')
        raw = uploaded.read()
        if hasattr(uploaded, 'seek'):
            uploaded.seek(0)

        file_hash = sha256_bytes(raw)
        file_created_at, file_modified_at = extract_xlsx_document_timestamps(raw)
        already_scopes, remaining_scopes, requested_scopes = remaining_scopes_for_hash(
            kind, file_hash, scopes,
        )
        # Full duplicate only when every selected scope was already imported
        # for this file hash (same bytes may be re-used for a new scope).
        is_duplicate = bool(requested_scopes) and not remaining_scopes
        prior = find_completed_import_by_hash(kind, file_hash)
        meta = {
            'filename': filename,
            'file_sha256': file_hash,
            'file_size': len(raw),
            'file_created_at': file_created_at.isoformat() if file_created_at else None,
            'file_modified_at': file_modified_at.isoformat() if file_modified_at else None,
            'is_duplicate': is_duplicate,
            'scopes_already_imported': sorted(already_scopes),
            'scopes_remaining': sorted(remaining_scopes),
            'prior_import': None,
        }
        if prior:
            meta['prior_import'] = {
                'id': prior.pk,
                'created_at': prior.created_at.isoformat(),
                'uploaded_by': (
                    str(prior.uploaded_by) if prior.uploaded_by_id else 'unknown'
                ),
                'original_filename': prior.original_filename,
                'scopes': sorted(parse_scopes_from_import_summary(prior.summary)),
            }

        parsed = detect_and_parse(raw, filename)
        parsed_dict = parsed.to_dict()
        # Prefer report_created_on from first parent in this file
        report_created_on = None
        for parent in parsed.parents:
            if parent.report_created_on:
                report_created_on = parent.report_created_on.isoformat()
                break
        meta['report_created_on'] = report_created_on

        # Personalkosten sheet (salary matching against funding allocations)
        pk_entries = parse_personalkosten_sheet(raw, filename)
        meta['personalkosten_entries'] = [
            {
                'personalnummer': e.personalnummer,
                'kostenart': e.kostenart,
                'personalkosten': str(e.personalkosten),
                'belegdatum': e.belegdatum.isoformat() if e.belegdatum else None,
                'psp_code': e.psp_code,
                'parent_psp_code': e.parent_psp_code,
                'source_filename': e.source_filename,
            }
            for e in pk_entries
        ]
        # Heuristic coverage window: min/max Belegdatum on Personalkosten sheet
        beleg_from, beleg_to = extract_beleg_date_range(raw)
        meta['beleg_from'] = beleg_from.isoformat() if beleg_from else None
        meta['beleg_to'] = beleg_to.isoformat() if beleg_to else None

        parsed_dict['upload_meta'] = meta
        file_results.append(parsed_dict)
        upload_meta.append(meta)
        for parent in parsed.parents:
            parents.append(parent.to_dict())

    plan_parents = []
    global_warnings = []
    has_blocking_errors = any(bool(f.get('errors')) for f in file_results)
    duplicate_files = [m for m in upload_meta if m.get('is_duplicate')]

    # Scope summary for the user
    active = []
    if scopes[SCOPE_PSP]:
        active.append('PSP-Element')
    if scopes[SCOPE_PERSONNEL]:
        active.append('Personaldaten')
    if scopes[SCOPE_ORDERS]:
        active.append('Bestelldaten')
    global_warnings.append(
        'Import-Bereiche: ' + (', '.join(active) if active else '—')
        + '. Nicht gewählte Bereiche werden nicht geschrieben.'
    )

    for parent in parents:
        plan_parents.append(_enrich_parent_against_db(parent, import_year, snapshot_date))

    # Personnel-only: ensure parent stubs exist for Personalkosten grouping
    if scopes[SCOPE_PERSONNEL]:
        existing_codes = {p['wbs_code'] for p in plan_parents}
        for meta in upload_meta:
            for entry in meta.get('personalkosten_entries') or []:
                code = entry.get('parent_psp_code')
                if code and code not in existing_codes:
                    plan_parents.append({
                        'wbs_code': code,
                        'source_filename': entry.get('source_filename') or meta.get('filename'),
                        'exists': WBSElement.objects.filter(wbs_code=code).exists(),
                        'action': (
                            'update'
                            if WBSElement.objects.filter(wbs_code=code).exists()
                            else 'create'
                        ),
                        'personnel_only_stub': True,
                        'cost_center': {'needs_user_choice': False},
                        'needs_title': False,
                        'year_plausibility_warning': False,
                        'snapshot_conflict': False,
                        'true_spending': {'amounts': {}, 'exists': False},
                        'obligo': {'amounts': {}, 'exists': False, 'personal': None},
                    })
                    existing_codes.add(code)

    plan_shell = {
        'import_year': import_year,
        'snapshot_date': snapshot_date.isoformat(),
        'upload_meta': upload_meta,
        'parents': plan_parents,
        'global_warnings': global_warnings,
        'import_scopes': scopes,
    }

    if scopes[SCOPE_PERSONNEL]:
        _attach_personnel_checks(plan_shell, snapshot_date)
    else:
        plan_shell['personnel_checks'] = []
        plan_shell['requires_personnel_decisions'] = False
        plan_shell['requires_personnel_resolution'] = False
        plan_shell['blocking_personnel_checks'] = []
        for parent in plan_parents:
            parent['personnel_checks'] = []

    personnel_checks = plan_shell.get('personnel_checks') or []
    global_warnings = plan_shell.get('global_warnings') or global_warnings

    # Year / snapshot plausibility only when writing PSP data
    year_conflict_parents = []
    snapshot_conflicts = []
    if scopes[SCOPE_PSP]:
        year_conflict_parents = [
            p['wbs_code']
            for p in plan_parents
            if p.get('year_plausibility_warning') and not p.get('personnel_only_stub')
        ]
        if year_conflict_parents:
            global_warnings.append(
                f'Import year {import_year} is earlier than last booking year(s) for: '
                + ', '.join(year_conflict_parents)
                + '. Confirm the import year before committing.'
            )

        snapshot_conflicts = [
            p['wbs_code']
            for p in plan_parents
            if p.get('snapshot_conflict') and not p.get('personnel_only_stub')
        ]
        if snapshot_conflicts:
            global_warnings.append(
                'True spending and/or obligo snapshots already exist for today for: '
                + ', '.join(snapshot_conflicts)
                + '. Commit will fail unless you enable “Update existing snapshots”.'
            )

    if duplicate_files:
        names = ', '.join(m['filename'] for m in duplicate_files)
        global_warnings.append(
            f'Duplicate file content for the selected import areas: {names}. '
            'These scope(s) were already imported successfully for this file. '
            'Commit is blocked — choose remaining areas (if any) or a different file.'
        )
        has_blocking_errors = True

    # Partial re-upload: same file, new scope(s) still open
    partial_reuploads = [
        m for m in upload_meta
        if not m.get('is_duplicate') and m.get('scopes_already_imported')
    ]
    for meta in partial_reuploads:
        already = ', '.join(meta.get('scopes_already_imported') or []) or '—'
        remaining = ', '.join(meta.get('scopes_remaining') or []) or '—'
        global_warnings.append(
            f'File "{meta.get("filename")}" was already imported for: {already}. '
            f'This run will only apply remaining selected areas: {remaining}.'
        )

    if scopes[SCOPE_PSP] and not plan_parents and not has_blocking_errors:
        # No parents from Übersicht — only relevant when PSP scope is selected
        pass

    return {
        'import_year': import_year,
        'snapshot_date': snapshot_date.isoformat(),
        'import_kind': kind,
        'import_scopes': scopes,
        'files': file_results,
        'upload_meta': upload_meta,
        'parents': plan_parents,
        'personnel_checks': personnel_checks,
        'global_warnings': global_warnings,
        'has_blocking_errors': has_blocking_errors,
        'has_duplicate_files': bool(duplicate_files),
        'requires_year_confirmation': bool(year_conflict_parents),
        'requires_snapshot_update_option': bool(snapshot_conflicts),
        'requires_personnel_decisions': plan_shell.get('requires_personnel_decisions', False),
        'requires_personnel_resolution': plan_shell.get('requires_personnel_resolution', False),
        'blocking_personnel_checks': plan_shell.get('blocking_personnel_checks', []),
    }


def _attach_personnel_checks(plan: dict, snapshot_date: date | None = None) -> dict:
    """
    (Re)build Personalkosten checks against the current DB and set plan flags.

    Called on analyze and whenever the preview is shown/refreshed so that
    employees / funding allocations created in another tab are picked up.
    """
    if snapshot_date is None:
        snapshot_date = _date(plan.get('snapshot_date')) or date.today()

    upload_meta = plan.get('upload_meta') or []
    personnel_checks: list[dict] = []
    for parent in plan.get('parents') or []:
        wbs_code = parent['wbs_code']
        entries_for_parent = []
        for meta in upload_meta:
            for entry in meta.get('personalkosten_entries') or []:
                if entry.get('parent_psp_code') == wbs_code:
                    entries_for_parent.append(entry)
        checks = build_personnel_checks(entries_for_parent, wbs_code, as_of=snapshot_date)
        parent['personnel_checks'] = checks
        personnel_checks.extend(checks)

    plan['personnel_checks'] = personnel_checks

    # Drop previous personnel-related warnings, then re-add current ones.
    kept_warnings = [
        w for w in (plan.get('global_warnings') or [])
        if not (
            'Personalkosten' in w
            or 'Personalnummer' in w
            or 'Funding Allocation' in w
            or 'funding allocation' in w
        )
    ]
    personnel_mismatches = [c for c in personnel_checks if c.get('status') == 'mismatch']
    blocking = [c for c in personnel_checks if c.get('status') in BLOCKING_PERSONNEL_STATUSES]

    if personnel_mismatches:
        kept_warnings.append(
            f'{len(personnel_mismatches)} Personalkosten-Zeile(n) weichen von '
            f'Monatsgehalt × Multiplikator × % um mehr als ±2,5 % ab. '
            f'Pro Zeile „Ignore“ oder „Adjust salary“ wählen '
            f'(Adjust setzt ebenfalls import_completed).'
        )
    if blocking:
        no_emp = sum(1 for c in blocking if c.get('status') == 'no_employee')
        no_alloc = sum(1 for c in blocking if c.get('status') == 'no_allocation')
        parts = []
        if no_emp:
            parts.append(f'{no_emp} unbekannte Personalnummer(n)')
        if no_alloc:
            parts.append(f'{no_alloc} ohne aktuelle Funding Allocation')
        kept_warnings.append(
            'Personalkosten: Import blockiert wegen '
            + ' und '.join(parts)
            + '. Bitte Mitarbeiter/FA anlegen und „Status neu prüfen“, '
            'oder „Diesen Mitarbeiter ignorieren“ wählen.'
        )

    plan['global_warnings'] = kept_warnings
    plan['requires_personnel_decisions'] = bool(personnel_mismatches)
    plan['requires_personnel_resolution'] = bool(blocking)
    plan['blocking_personnel_checks'] = blocking
    return plan


def refresh_personnel_checks(plan: dict) -> dict:
    """Public helper: re-run personnel matching on an existing session plan."""
    plan = deepcopy(plan)
    if not scope_enabled(plan, SCOPE_PERSONNEL):
        plan['personnel_checks'] = []
        plan['requires_personnel_decisions'] = False
        plan['requires_personnel_resolution'] = False
        plan['blocking_personnel_checks'] = []
        for parent in plan.get('parents') or []:
            parent['personnel_checks'] = []
        return plan
    return _attach_personnel_checks(plan)


def _enrich_parent_against_db(parent: dict, import_year: int, snapshot_date: date) -> dict:
    item = deepcopy(parent)
    wbs_code = item['wbs_code']
    existing = (
        WBSElement.objects.filter(wbs_code=wbs_code)
        .select_related('cost_center', 'contact_person')
        .first()
    )
    item['exists'] = existing is not None
    item['action'] = 'update' if existing else 'create'
    item['existing_pk'] = existing.pk if existing else None
    item['existing_title'] = existing.title if existing else ''
    item['needs_title'] = existing is None
    item['proposed_title'] = ''

    # Cost center resolution (flexible: ``0001/991000`` ↔ ``991000``)
    file_cc = (item.get('cost_center_code') or '').strip()
    placeholder = bool(item.get('cost_center_is_placeholder'))
    existing_cc = existing.cost_center if existing else None
    existing_cc_code = existing_cc.cost_center if existing_cc else ''

    matched_cc = None
    matched_via = ''
    if file_cc and not placeholder:
        matched_cc = find_cost_center(file_cc)
        if matched_cc:
            if matched_cc.cost_center == file_cc:
                matched_via = 'exact'
            else:
                matched_via = 'prefix_stripped'

    needs_cc_choice = placeholder or (not file_cc)
    item['cost_center'] = {
        'file_code': file_cc,
        'is_placeholder': placeholder,
        'exists_in_db': matched_cc is not None,
        'matched_pk': matched_cc.pk if matched_cc else None,
        'matched_code': matched_cc.cost_center if matched_cc else '',
        'matched_via': matched_via,
        'will_create': bool(file_cc and not placeholder and matched_cc is None),
        'needs_user_choice': needs_cc_choice,
        'suggested_pk': existing_cc.pk if existing_cc else None,
        'suggested_code': existing_cc_code,
        'selected_pk': matched_cc.pk if matched_cc else None,
        'selected_code': (
            '' if needs_cc_choice
            else (matched_cc.cost_center if matched_cc else file_cc)
        ),
    }

    # Diffs for simple fields (do not touch title)
    diffs = []
    if existing:
        funder = item.get('third_party_funder_identifier') or ''
        if funder and funder != (existing.third_party_funder_identifier or ''):
            diffs.append({
                'field': 'third_party_funder_identifier',
                'label': 'Third-party funder identifier',
                'old': existing.third_party_funder_identifier or '',
                'new': funder,
            })
        ps = _date(item.get('period_start'))
        if ps and existing.period_start != ps:
            diffs.append({
                'field': 'period_start',
                'label': 'Period start',
                'old': existing.period_start.isoformat() if existing.period_start else '',
                'new': ps.isoformat(),
            })
        pe = _date(item.get('period_end'))
        if pe and existing.period_end != pe:
            diffs.append({
                'field': 'period_end',
                'label': 'Period end',
                'old': existing.period_end.isoformat() if existing.period_end else '',
                'new': pe.isoformat(),
            })
    item['field_diffs'] = diffs

    # Cost-type flags to set
    flags_to_set = []
    for suffix in (item.get('cost_types') or {}):
        flag, _amount = SUFFIX_TO_COST_TYPE[suffix]
        currently = getattr(existing, flag, False) if existing else False
        if not currently:
            flags_to_set.append({
                'suffix': suffix,
                'flag': flag,
                'label': f'.{suffix}',
                'already_set': False,
            })
        else:
            flags_to_set.append({
                'suffix': suffix,
                'flag': flag,
                'label': f'.{suffix}',
                'already_set': True,
            })
    item['flags'] = flags_to_set

    # Lifetime plan (non-annual): one estimate row for the full PSP runtime.
    # Current Drittmittel Übersicht import always targets non-annual projects.
    estimate_amounts = {}
    for suffix, data in (item.get('cost_types') or {}).items():
        _flag, amount_field = SUFFIX_TO_COST_TYPE[suffix]
        estimate_amounts[amount_field] = data.get('approved_budget')

    existing_estimate = None
    existing_estimate_count = 0
    if existing:
        existing_estimates = list(
            WBSElementYearEstimate.objects.filter(wbs_element=existing).order_by('year')
        )
        existing_estimate_count = len(existing_estimates)
        if existing_estimate_count == 1:
            existing_estimate = existing_estimates[0]
        elif existing_estimate_count > 1:
            year_key = _lifetime_estimate_year_key(item, existing, import_year)
            existing_estimate = next(
                (e for e in existing_estimates if e.year == year_key),
                existing_estimates[0],
            )

    technical_year = (
        existing_estimate.year
        if existing_estimate
        else _lifetime_estimate_year_key(item, existing, import_year)
    )
    item['is_non_annual'] = True
    item['year_estimate'] = {
        'scope': 'lifetime',
        'year': technical_year,  # technical key only; amounts cover full project
        'action': 'update' if existing_estimate else 'create',
        'existing_count': existing_estimate_count,
        'amounts': estimate_amounts,
        'previous_amounts': {
            f: (
                str(getattr(existing_estimate, f))
                if existing_estimate and getattr(existing_estimate, f) is not None
                else None
            )
            for f in PSP_COST_TYPE_AMOUNT_FIELDS
        } if existing_estimate else {},
    }

    # True spending from Verfügt
    verfuegt_amounts = {}
    for suffix, data in (item.get('cost_types') or {}).items():
        _flag, amount_field = SUFFIX_TO_COST_TYPE[suffix]
        verfuegt_amounts[amount_field] = data.get('verfuegt')

    existing_true = None
    if existing:
        existing_true = WBSElementTrueYearlySpending.objects.filter(
            wbs_element=existing, date_of_update=snapshot_date
        ).first()

    # Obligo + personal
    obligo_amounts = {}
    personal_total = None
    for suffix, data in (item.get('cost_types') or {}).items():
        _flag, amount_field = SUFFIX_TO_COST_TYPE[suffix]
        obligo_amounts[amount_field] = data.get('obligo')
        po = _dec(data.get('personal_obligo'))
        if po is not None:
            personal_total = (personal_total or Decimal('0')) + po

    existing_obligo = None
    if existing:
        existing_obligo = WBSElementObligo.objects.filter(
            wbs_element=existing, date_of_update=snapshot_date
        ).first()

    item['true_spending'] = {
        'date_of_update': snapshot_date.isoformat(),
        'amounts': verfuegt_amounts,
        'exists': existing_true is not None,
    }
    item['obligo'] = {
        'date_of_update': snapshot_date.isoformat(),
        'amounts': obligo_amounts,
        'personal': str(personal_total) if personal_total is not None else None,
        'exists': existing_obligo is not None,
    }
    item['snapshot_conflict'] = bool(existing_true or existing_obligo)

    # Contact
    contact = item.get('contact') or {}
    last_name = (contact.get('last_name') or '').strip()
    first_name = (contact.get('first_name') or '').strip()
    contact_obj = None
    if last_name:
        contact_obj = ContactPerson.objects.filter(
            last_name__iexact=last_name,
            first_name__iexact=first_name,
        ).first()
    item['contact_plan'] = {
        'last_name': last_name,
        'first_name': first_name,
        'exists': contact_obj is not None,
        'pk': contact_obj.pk if contact_obj else None,
        'action': 'link' if contact_obj else ('create' if last_name else 'none'),
    }

    # Year plausibility
    booking_years = item.get('last_booking_years') or []
    future_years = [y for y in booking_years if y > import_year]
    item['year_plausibility_warning'] = bool(future_years)
    item['booking_years_after_import_year'] = future_years

    return item


def merge_user_decisions(plan: dict, post_data) -> tuple[dict, list[str]]:
    """
    Merge preview form POST into the plan. Returns (plan, errors).
    """
    errors: list[str] = []
    plan = deepcopy(plan)
    # Ensure scopes exist (older sessions / tests)
    if 'import_scopes' not in plan:
        plan['import_scopes'] = normalize_import_scopes(None)
    do_psp = scope_enabled(plan, SCOPE_PSP)
    do_personnel = scope_enabled(plan, SCOPE_PERSONNEL)

    plan['confirm_import_year'] = post_data.get('confirm_import_year') == 'on'
    plan['update_existing_snapshots'] = post_data.get('update_existing_snapshots') == 'on'

    if do_psp and plan.get('requires_year_confirmation') and not plan['confirm_import_year']:
        errors.append(
            'Please confirm that the import year is correct '
            '(last booking dates after the import year were found).'
        )

    if do_psp and plan.get('requires_snapshot_update_option'):
        conflicts = [
            p for p in plan['parents']
            if p.get('snapshot_conflict') and not p.get('personnel_only_stub')
        ]
        if conflicts and not plan['update_existing_snapshots']:
            errors.append(
                'Snapshots for today already exist. Enable “Update existing snapshots” '
                'to overwrite them, or cancel and try another day.'
            )

    # Personnel decisions (only when personnel scope is active)
    personnel_decisions = {}
    if do_personnel:
        for check in plan.get('personnel_checks') or []:
            status = check.get('status')
            dkey = check.get('decision_key') or decision_key_for(
                str(check.get('personalnummer') or ''),
                str(check.get('parent_psp_code') or check.get('psp_code') or ''),
            )
            form_key = f'personnel_action__{dkey}'
            alloc_pk = check.get('allocation_pk')
            legacy_key = f'personnel_action__{alloc_pk}' if alloc_pk else None

            if status in BLOCKING_PERSONNEL_STATUSES:
                raw = (post_data.get(form_key) or '').strip()
                if raw != 'ignore':
                    pn = check.get('personalnummer') or '?'
                    if status == 'no_employee':
                        errors.append(
                            f'Der Mitarbeiter mit der Personalnummer {pn} existiert noch nicht '
                            f'im System. Bitte lege ihn an oder wähle '
                            f'„Diesen Mitarbeiter ignorieren“.'
                        )
                    else:
                        errors.append(
                            f'Keine aktuelle Funding Allocation für Personalnummer {pn} '
                            f'auf PSP {check.get("parent_psp_code")}. '
                            f'Bitte lege eine FA an oder wähle „Diesen Mitarbeiter ignorieren“.'
                        )
                else:
                    personnel_decisions[dkey] = 'ignore'
                continue

            if status != 'mismatch':
                continue

            action = (
                post_data.get(form_key)
                or (post_data.get(legacy_key) if legacy_key else None)
                or 'ignore'
            ).strip()
            if action not in {'ignore', 'adjust_salary'}:
                action = 'ignore'
            personnel_decisions[dkey] = action
            if alloc_pk:
                personnel_decisions[str(alloc_pk)] = action
    plan['personnel_decisions'] = personnel_decisions

    if do_psp:
        for parent in plan['parents']:
            if parent.get('personnel_only_stub'):
                continue
            code = parent['wbs_code']
            if parent.get('needs_title'):
                title = (post_data.get(f'title__{code}') or '').strip()
                if not title:
                    errors.append(f'Title is required for new PSP element {code}.')
                parent['proposed_title'] = title

            cc_info = parent.get('cost_center') or {}
            if cc_info.get('needs_user_choice'):
                selected = (post_data.get(f'cost_center__{code}') or '').strip()
                if not selected:
                    errors.append(f'Please choose a cost center for {code}.')
                else:
                    if selected.isdigit():
                        cc = CostCenter.objects.filter(pk=int(selected)).first()
                        if not cc:
                            errors.append(f'Invalid cost center selection for {code}.')
                        else:
                            cc_info['selected_pk'] = cc.pk
                            cc_info['selected_code'] = cc.cost_center
                            cc_info['will_create'] = False
                    else:
                        existing_cc = find_cost_center(selected)
                        if existing_cc:
                            cc_info['selected_pk'] = existing_cc.pk
                            cc_info['selected_code'] = existing_cc.cost_center
                            cc_info['will_create'] = False
                        else:
                            cc_info['selected_pk'] = None
                            cc_info['selected_code'] = selected
                            cc_info['will_create'] = True

    return plan, errors


@transaction.atomic
def apply_import_plan(plan: dict, *, uploaded_by=None) -> dict:
    """Persist a confirmed plan. Raises ValueError on snapshot conflicts without update flag."""
    import_year = int(plan['import_year'])
    snapshot_date = _date(plan['snapshot_date']) or date.today()
    update_snapshots = bool(plan.get('update_existing_snapshots'))
    kind = plan.get('import_kind') or DataImportLog.Kind.THIRD_PARTY_FUNDING_REPORT
    if 'import_scopes' not in plan:
        plan['import_scopes'] = normalize_import_scopes(None)
    do_psp = scope_enabled(plan, SCOPE_PSP)
    do_personnel = scope_enabled(plan, SCOPE_PERSONNEL)

    # Scope-aware duplicate check: same file bytes may be re-imported only for
    # scopes not yet completed for that hash.
    effective_scopes = dict(plan['import_scopes'])
    for meta in plan.get('upload_meta') or []:
        file_hash = meta.get('file_sha256') or ''
        if not file_hash:
            continue
        already, remaining, requested = remaining_scopes_for_hash(
            kind, file_hash, effective_scopes,
        )
        if requested and not remaining:
            prior = find_completed_import_by_hash(kind, file_hash)
            when = (
                f'{prior.created_at:%Y-%m-%d %H:%M}' if prior else 'earlier'
            )
            who = (str(prior.uploaded_by) if prior and prior.uploaded_by_id else 'unknown')
            raise ValueError(
                f'File "{meta.get("filename")}" was already imported for the '
                f'selected areas ({", ".join(sorted(requested)) or "—"}) '
                f'on {when} by {who} (SHA-256 {file_hash[:12]}…). '
                f'Re-import blocked for those scopes.'
            )
        # Drop already-imported scopes from this run (apply only remaining)
        for scope_name in already:
            effective_scopes[scope_name] = False

    plan['import_scopes'] = effective_scopes
    do_psp = scope_enabled(plan, SCOPE_PSP)
    do_personnel = scope_enabled(plan, SCOPE_PERSONNEL)

    if not do_psp and not do_personnel:
        raise ValueError(
            'Nothing left to import: all selected areas were already imported '
            'for this file content.'
        )

    summary = {
        'psp_created': 0,
        'psp_updated': 0,
        'cost_centers_created': 0,
        'contacts_created': 0,
        'year_estimates_written': 0,
        'true_spending_written': 0,
        'obligos_written': 0,
        'import_logs': 0,
        'scopes': plan['import_scopes'],
        'details': [],
    }

    if do_psp:
        for parent in plan['parents']:
            if parent.get('personnel_only_stub'):
                continue
            detail = {'wbs_code': parent['wbs_code'], 'actions': []}
            wbs = _upsert_psp(parent, summary, detail)
            _apply_year_estimate(wbs, parent, import_year, summary, detail)
            _apply_true_spending(
                wbs, parent, snapshot_date, update_snapshots, summary, detail
            )
            _apply_obligo(wbs, parent, snapshot_date, update_snapshots, summary, detail)
            summary['details'].append(detail)
    else:
        summary['details'].append({
            'wbs_code': 'Scopes',
            'actions': ['PSP-Element-Import übersprungen (Scope deaktiviert).'],
        })

    # Personalkosten salary matching → FundingAllocation.import_completed
    if do_personnel:
        personnel_notes = apply_personnel_decisions(
            plan.get('personnel_checks') or [],
            plan.get('personnel_decisions') or {},
            as_of=snapshot_date,
        )
        summary['personnel_notes'] = personnel_notes
        for note in personnel_notes:
            summary['details'].append({'wbs_code': 'Personalkosten', 'actions': [note]})
    else:
        summary['personnel_notes'] = []
        summary['details'].append({
            'wbs_code': 'Scopes',
            'actions': ['Personaldaten-Import übersprungen (Scope deaktiviert).'],
        })

    # One audit log row per uploaded file
    scopes = plan['import_scopes']
    scope_label = ','.join(
        k for k in (SCOPE_PSP, SCOPE_PERSONNEL, SCOPE_ORDERS) if scopes.get(k)
    ) or 'none'
    summary_text = (
        f"scopes={scope_label}; "
        f"year={import_year}; "
        f"psp_created={summary['psp_created']}; "
        f"psp_updated={summary['psp_updated']}; "
        f"estimates={summary['year_estimates_written']}; "
        f"true_spending={summary['true_spending_written']}; "
        f"obligos={summary['obligos_written']}"
    )
    for meta in plan.get('upload_meta') or []:
        report_created_on = _date(meta.get('report_created_on'))
        # Fallback: first parent of matching source file
        if report_created_on is None:
            for parent in plan.get('parents') or []:
                if parent.get('source_filename') == meta.get('filename'):
                    report_created_on = _date(parent.get('report_created_on'))
                    if report_created_on:
                        break
        record_data_import(
            kind=kind,
            uploaded_by=uploaded_by,
            original_filename=meta.get('filename') or '',
            file_sha256=meta.get('file_sha256') or '',
            file_size=int(meta.get('file_size') or 0),
            file_created_at=_datetime(meta.get('file_created_at')),
            file_modified_at=_datetime(meta.get('file_modified_at')),
            report_created_on=report_created_on,
            beleg_from=_date(meta.get('beleg_from')),
            beleg_to=_date(meta.get('beleg_to')),
            status=DataImportLog.Status.COMPLETED,
            summary=summary_text,
        )
        summary['import_logs'] += 1

    return summary


def _datetime(value):
    """Parse ISO datetime from plan JSON (or pass through)."""
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    try:
        # Handle trailing Z
        if text.endswith('Z'):
            text = text[:-1] + '+00:00'
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _resolve_cost_center(parent: dict, summary: dict) -> CostCenter | None:
    cc_info = parent['cost_center']
    if cc_info.get('needs_user_choice'):
        pk = cc_info.get('selected_pk')
        if pk:
            return CostCenter.objects.get(pk=pk)
        code = (cc_info.get('selected_code') or '').strip()
        if code:
            cc, created = get_or_create_cost_center(code)
            if created:
                summary['cost_centers_created'] += 1
            return cc
        return None

    pk = cc_info.get('selected_pk') or cc_info.get('matched_pk')
    if pk:
        return CostCenter.objects.get(pk=pk)

    code = (cc_info.get('selected_code') or cc_info.get('file_code') or '').strip()
    if not code:
        return None
    cc, created = get_or_create_cost_center(code)
    if created:
        summary['cost_centers_created'] += 1
    return cc


def _resolve_contact(parent: dict, summary: dict) -> ContactPerson | None:
    contact = parent.get('contact_plan') or {}
    last_name = (contact.get('last_name') or '').strip()
    first_name = (contact.get('first_name') or '').strip()
    if not last_name:
        return None
    obj, created = ContactPerson.objects.get_or_create(
        last_name=last_name,
        first_name=first_name,
        defaults={
            'business_area': '',
            'phone': '',
            'email': '',
        },
    )
    if created:
        summary['contacts_created'] += 1
    return obj


def _upsert_psp(parent: dict, summary: dict, detail: dict) -> WBSElement:
    wbs_code = parent['wbs_code']
    existing = WBSElement.objects.filter(wbs_code=wbs_code).first()
    cost_center = _resolve_cost_center(parent, summary)
    contact = _resolve_contact(parent, summary)

    if existing is None:
        title = (parent.get('proposed_title') or '').strip()
        if not title:
            raise ValueError(f'Title missing for new PSP {wbs_code}')
        wbs = WBSElement(
            wbs_code=wbs_code,
            title=title,
            cost_center=cost_center,
            contact_person=contact,
            third_party_funder_identifier=parent.get('third_party_funder_identifier') or '',
            period_start=_date(parent.get('period_start')),
            period_end=_date(parent.get('period_end')),
            # Übersicht import is for non-annual projects (one plan for full runtime).
            subject_to_annual_recurrence=False,
        )
        for flag_info in parent.get('flags') or []:
            setattr(wbs, flag_info['flag'], True)
        wbs.save()
        summary['psp_created'] += 1
        detail['actions'].append('created PSP (non-annual)')
        return wbs

    # Update existing — never change title
    changed = []
    funder = parent.get('third_party_funder_identifier') or ''
    if funder and funder != (existing.third_party_funder_identifier or ''):
        existing.third_party_funder_identifier = funder
        changed.append('third_party_funder_identifier')

    ps = _date(parent.get('period_start'))
    if ps and existing.period_start != ps:
        existing.period_start = ps
        changed.append('period_start')
    pe = _date(parent.get('period_end'))
    if pe and existing.period_end != pe:
        existing.period_end = pe
        changed.append('period_end')

    if existing.subject_to_annual_recurrence:
        existing.subject_to_annual_recurrence = False
        changed.append('subject_to_annual_recurrence')

    if cost_center and existing.cost_center_id != cost_center.pk:
        existing.cost_center = cost_center
        changed.append('cost_center')
    if contact and existing.contact_person_id != contact.pk:
        existing.contact_person = contact
        changed.append('contact_person')

    for flag_info in parent.get('flags') or []:
        if not getattr(existing, flag_info['flag'], False):
            setattr(existing, flag_info['flag'], True)
            changed.append(flag_info['flag'])

    if changed:
        existing.save()
        summary['psp_updated'] += 1
        detail['actions'].append(f'updated PSP fields: {", ".join(changed)}')
    else:
        detail['actions'].append('PSP unchanged (flags/fields already current)')
    return existing


def _lifetime_estimate_year_key(parent: dict, wbs: WBSElement | None, import_year: int) -> int:
    """
    Technical year key for the single non-annual plan row.

    Amounts always cover the full project runtime; the year column is only a
    storage key (prefer project start year).
    """
    ps = _date(parent.get('period_start')) if parent else None
    if ps:
        return ps.year
    if wbs and wbs.period_start:
        return wbs.period_start.year
    if wbs:
        existing = (
            WBSElementYearEstimate.objects
            .filter(wbs_element=wbs)
            .order_by('year')
            .first()
        )
        if existing:
            return existing.year
    return int(import_year)


def _apply_year_estimate(wbs, parent, import_year, summary, detail):
    """
    Write the single lifetime plan for a non-annual PSP.

    - 0 existing rows → create one (year = project start year)
    - 1 existing row → overwrite amounts (keep its year key)
    - multiple rows → overwrite preferred lifetime row only and note the rest
    """
    amounts = (parent.get('year_estimate') or {}).get('amounts') or {}
    defaults = {f: _dec(amounts.get(f)) for f in PSP_COST_TYPE_AMOUNT_FIELDS}
    qs = WBSElementYearEstimate.objects.filter(wbs_element=wbs).order_by('year')
    count = qs.count()

    if count == 0:
        year_key = _lifetime_estimate_year_key(parent, wbs, import_year)
        WBSElementYearEstimate.objects.create(
            wbs_element=wbs,
            year=year_key,
            **defaults,
        )
        summary['year_estimates_written'] += 1
        detail['actions'].append(
            f'lifetime plan created (technical year key {year_key})'
        )
        return

    if count == 1:
        est = qs.first()
        for field, value in defaults.items():
            setattr(est, field, value)
        est.save()
        summary['year_estimates_written'] += 1
        detail['actions'].append(
            f'lifetime plan overwritten (technical year key {est.year})'
        )
        return

    year_key = _lifetime_estimate_year_key(parent, wbs, import_year)
    est = qs.filter(year=year_key).first() or qs.first()
    for field, value in defaults.items():
        setattr(est, field, value)
    est.save()
    summary['year_estimates_written'] += 1
    detail['actions'].append(
        f'lifetime plan overwritten on year={est.year}; '
        f'{count - 1} other estimate row(s) left unchanged (non-annual expects one row)'
    )


def _apply_true_spending(wbs, parent, snapshot_date, update_snapshots, summary, detail):
    amounts = (parent.get('true_spending') or {}).get('amounts') or {}
    defaults = {f: _dec(amounts.get(f)) for f in PSP_COST_TYPE_AMOUNT_FIELDS}
    existing = WBSElementTrueYearlySpending.objects.filter(
        wbs_element=wbs, date_of_update=snapshot_date
    ).first()
    if existing and not update_snapshots:
        raise ValueError(
            f'True yearly spending snapshot for {wbs.wbs_code} on {snapshot_date} '
            f'already exists. Enable update or use another date.'
        )
    obj, created = WBSElementTrueYearlySpending.objects.update_or_create(
        wbs_element=wbs,
        date_of_update=snapshot_date,
        defaults=defaults,
    )
    summary['true_spending_written'] += 1
    detail['actions'].append(
        f'true spending {"created" if created else "updated"} ({snapshot_date})'
    )


def _apply_obligo(wbs, parent, snapshot_date, update_snapshots, summary, detail):
    obligo = parent.get('obligo') or {}
    amounts = obligo.get('amounts') or {}
    defaults = {f: _dec(amounts.get(f)) for f in PSP_COST_TYPE_AMOUNT_FIELDS}
    defaults['personal'] = _dec(obligo.get('personal'))
    existing = WBSElementObligo.objects.filter(
        wbs_element=wbs, date_of_update=snapshot_date
    ).first()
    if existing and not update_snapshots:
        raise ValueError(
            f'Obligo snapshot for {wbs.wbs_code} on {snapshot_date} already exists. '
            f'Enable update or use another date.'
        )
    obj, created = WBSElementObligo.objects.update_or_create(
        wbs_element=wbs,
        date_of_update=snapshot_date,
        defaults=defaults,
    )
    summary['obligos_written'] += 1
    detail['actions'].append(
        f'obligo {"created" if created else "updated"} ({snapshot_date})'
    )
