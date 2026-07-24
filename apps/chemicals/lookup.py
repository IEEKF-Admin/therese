"""
Free public chemical data lookups (PubChem).

No paid APIs. Classification is mapped against GlobalSetting.chemical_hazard_threshold.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import requests
from django.utils import timezone

logger = logging.getLogger(__name__)

PUBCHEM_TIMEOUT = 12
CAS_RE = re.compile(
    r'^\s*(\d{2,7})-(\d{2})-(\d)\s*$'
)


def normalize_cas(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    # Allow plain digits with dashes already
    m = CAS_RE.match(text)
    if m:
        return f'{m.group(1)}-{m.group(2)}-{m.group(3)}'
    # Extract CAS-like pattern from longer text
    m = re.search(r'(\d{2,7}-\d{2}-\d)', text)
    if m:
        return m.group(1)
    return None


def looks_like_cas(value: str | None) -> bool:
    return normalize_cas(value) is not None


def _get_json(url: str) -> dict | list | None:
    try:
        resp = requests.get(url, timeout=PUBCHEM_TIMEOUT, headers={'User-Agent': 'THERESE/1.0'})
        if resp.status_code != 200:
            logger.info('PubChem HTTP %s for %s', resp.status_code, url)
            return None
        return resp.json()
    except requests.RequestException as exc:
        logger.warning('PubChem request failed: %s', exc)
        return None


def fetch_pubchem_by_cas(cas: str) -> dict[str, Any]:
    """
    Return structured data for a CAS number from PubChem (free).

    Keys: name, iupac_name, molecular_formula, pubchem_cid,
          ghs_signal_word, ghs_hazard_codes (list), ghs_pictograms (list),
          sds_source_url, raw
    """
    cas = normalize_cas(cas) or cas
    result: dict[str, Any] = {
        'cas_number': cas,
        'name': '',
        'iupac_name': '',
        'molecular_formula': '',
        'pubchem_cid': None,
        'ghs_signal_word': '',
        'ghs_hazard_codes': [],
        'ghs_pictograms': [],
        'sds_source_url': '',
        'raw': {},
        'error': '',
    }

    props_url = (
        f'https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/xref/RN/{cas}/'
        f'property/Title,IUPACName,MolecularFormula/JSON'
    )
    props = _get_json(props_url)
    result['raw']['properties'] = props
    cid = None
    if isinstance(props, dict):
        props_list = (props.get('PropertyTable') or {}).get('Properties') or []
        if props_list:
            first = props_list[0]
            cid = first.get('CID')
            result['pubchem_cid'] = cid
            result['name'] = first.get('Title') or ''
            result['iupac_name'] = first.get('IUPACName') or ''
            result['molecular_formula'] = first.get('MolecularFormula') or ''

    if not cid:
        result['error'] = 'CAS not found in PubChem'
        return result

    # GHS section via PUG View
    view_url = (
        f'https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON'
        f'?heading=GHS+Classification'
    )
    view = _get_json(view_url)
    result['raw']['ghs_view'] = view
    signal, hazards, pictos = _parse_ghs_from_pug_view(view)
    result['ghs_signal_word'] = signal
    result['ghs_hazard_codes'] = hazards
    result['ghs_pictograms'] = pictos

    # Prefer PubChem compound page as documentation link (SDS rarely free via API)
    result['sds_source_url'] = f'https://pubchem.ncbi.nlm.nih.gov/compound/{cid}#section=Safety-and-Hazards'

    return result


def _parse_ghs_from_pug_view(view: dict | None) -> tuple[str, list[str], list[str]]:
    signal = ''
    hazards: list[str] = []
    pictos: list[str] = []
    if not isinstance(view, dict):
        return signal, hazards, pictos

    def walk(node):
        nonlocal signal, hazards, pictos
        if not isinstance(node, dict):
            return
        toc = (node.get('TOCHeading') or '')
        # Information blocks
        for info in node.get('Information') or []:
            name = (info.get('Name') or '').lower()
            value = info.get('Value') or {}
            strings = []
            for s in value.get('StringWithMarkup') or []:
                if isinstance(s, dict) and s.get('String'):
                    strings.append(s['String'])
                elif isinstance(s, str):
                    strings.append(s)
            text = ' '.join(strings)
            if 'signal' in name and text and not signal:
                if 'danger' in text.lower():
                    signal = 'Danger'
                elif 'warning' in text.lower():
                    signal = 'Warning'
                else:
                    signal = text.strip()[:32]
            if 'h-statement' in name or 'hazard statement' in name or toc == 'GHS Classification':
                for code in re.findall(r'\bH\d{3}[A-Za-z]?\b', text):
                    if code not in hazards:
                        hazards.append(code)
            if 'pictogram' in name:
                for p in re.findall(r'GHS\d{2}', text, flags=re.I):
                    up = p.upper()
                    if up not in pictos:
                        pictos.append(up)
        for child in node.get('Section') or []:
            walk(child)

    record = (view.get('Record') or {})
    for section in record.get('Section') or []:
        walk(section)

    # Fallback: scan entire JSON text for H-codes / signal
    blob = str(view)
    if not hazards:
        for code in re.findall(r'\bH\d{3}[A-Za-z]?\b', blob):
            if code not in hazards:
                hazards.append(code)
    if not signal:
        if re.search(r'\bDanger\b', blob):
            signal = 'Danger'
        elif re.search(r'\bWarning\b', blob):
            signal = 'Warning'
    if not pictos:
        for p in re.findall(r'GHS0\d', blob, flags=re.I):
            up = p.upper()
            if up not in pictos:
                pictos.append(up)

    return signal, hazards, pictos


def evaluate_is_hazardous(
    *,
    signal_word: str = '',
    hazard_codes: list[str] | None = None,
    pictograms: list[str] | None = None,
    threshold: str | None = None,
) -> bool:
    """
    Apply institute threshold from GlobalSetting.chemical_hazard_threshold.

    Thresholds (ordered by strictness, default any_ghs):
    - any_ghs: any signal word, H-code, or pictogram
    - signal_warning_or_danger: Warning or Danger
    - signal_danger_only: Danger only
    - any_pictogram: at least one GHS pictogram
    - any_h_code: at least one H-code
    - never: never treat as hazardous (manual only)
    """
    from apps.core.models import GlobalSetting

    if threshold is None:
        threshold = GlobalSetting.get_chemical_hazard_threshold()

    hazard_codes = hazard_codes or []
    pictograms = pictograms or []
    signal = (signal_word or '').strip().lower()
    has_signal = signal in ('danger', 'warning')
    has_danger = signal == 'danger'
    has_h = bool(hazard_codes)
    has_p = bool(pictograms)

    if threshold == 'never':
        return False
    if threshold == 'signal_danger_only':
        return has_danger
    if threshold == 'signal_warning_or_danger':
        return has_signal
    if threshold == 'any_pictogram':
        return has_p
    if threshold == 'any_h_code':
        return has_h
    # default: any_ghs
    return has_signal or has_h or has_p


def upsert_chemical_from_cas(cas: str, *, force_refresh: bool = False):
    """Get or create Chemical, refresh from PubChem if new or force_refresh."""
    from apps.chemicals.models import Chemical

    cas_n = normalize_cas(cas)
    if not cas_n:
        raise ValueError(f'Invalid CAS number: {cas!r}')

    chemical, created = Chemical.objects.get_or_create(
        cas_number=cas_n,
        defaults={'name': cas_n},
    )
    if not created and not force_refresh and chemical.last_lookup_at:
        # Re-evaluate hazard against current threshold
        chemical.is_hazardous = evaluate_is_hazardous(
            signal_word=chemical.ghs_signal_word,
            hazard_codes=[c.strip() for c in (chemical.ghs_hazard_codes or '').split(',') if c.strip()],
            pictograms=[c.strip() for c in (chemical.ghs_pictograms or '').split(',') if c.strip()],
        )
        chemical.save(update_fields=['is_hazardous', 'updated_at'])
        return chemical

    data = fetch_pubchem_by_cas(cas_n)
    chemical.name = data.get('name') or chemical.name or cas_n
    chemical.iupac_name = data.get('iupac_name') or chemical.iupac_name
    chemical.molecular_formula = data.get('molecular_formula') or chemical.molecular_formula
    chemical.pubchem_cid = data.get('pubchem_cid') or chemical.pubchem_cid
    chemical.ghs_signal_word = data.get('ghs_signal_word') or ''
    chemical.ghs_hazard_codes = ','.join(data.get('ghs_hazard_codes') or [])
    chemical.ghs_pictograms = ','.join(data.get('ghs_pictograms') or [])
    if data.get('sds_source_url') and not chemical.sds_source_url:
        chemical.sds_source_url = data['sds_source_url']
    chemical.pubchem_raw = data.get('raw') or {}
    chemical.lookup_error = data.get('error') or ''
    chemical.last_lookup_at = timezone.now()
    chemical.is_hazardous = evaluate_is_hazardous(
        signal_word=chemical.ghs_signal_word,
        hazard_codes=data.get('ghs_hazard_codes') or [],
        pictograms=data.get('ghs_pictograms') or [],
    )
    chemical.save()
    return chemical
