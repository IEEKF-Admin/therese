"""
Shared cost-type flags and matching yearly amount fields for PSP / cost centers.

Each cost type has:
- flag_field: Boolean on WBSElement or CostCenter
- amount_field: Decimal on year-estimate / true-spending / obligo rows
- code: numeric suffix historically used in WBS codes (.1 … .9)
- label_de / label_en: bilingual UI labels
"""

from django.utils.html import format_html

# (flag_field, amount_field, code, German label, English label)
PSP_COST_TYPES = (
    ('has_material_costs', 'material_costs', '1', 'Sachkosten', 'Material costs'),
    ('has_personnel_costs', 'personnel_costs', '2', 'Personalkosten', 'Personnel costs'),
    ('has_domestic_travel_costs', 'domestic_travel_costs', '3', 'Reisekosten Inland', 'Domestic travel costs'),
    ('has_foreign_travel_costs', 'foreign_travel_costs', '4', 'Reisekosten Ausland', 'Foreign travel costs'),
    (
        'has_third_party_investments',
        'third_party_investments',
        '5',
        'Drittmittel-Investitionen',
        'Third-party investments',
    ),
    ('has_publication_costs', 'publication_costs', '6', 'Publikationskosten', 'Publication costs'),
    (
        'has_animal_husbandry_costs',
        'animal_husbandry_costs',
        '7',
        'Tierhaltungskosten',
        'Animal husbandry costs',
    ),
    (
        'has_transfer_to_third_parties',
        'transfer_to_third_parties',
        '8',
        'Weitergabe an Dritte',
        'Transfer to third parties',
    ),
    (
        'has_internal_service_charges',
        'internal_service_charges',
        '9',
        'Interne Leistungsverrechnung',
        'Internal service charges',
    ),
)

PSP_COST_TYPE_FLAG_FIELDS = tuple(item[0] for item in PSP_COST_TYPES)
PSP_COST_TYPE_AMOUNT_FIELDS = tuple(item[1] for item in PSP_COST_TYPES)


def bilingual_cost_type_label(code, label_de, label_en, *, include_code=True):
    """HTML label: German primary, English secondary (smaller/muted)."""
    if include_code:
        de_part = f'.{code} - {label_de}'
    else:
        de_part = label_de
    return format_html(
        '<span class="bilingual-label">'
        '<span class="bilingual-label__de">{}</span>'
        '<span class="bilingual-label__en">{}</span>'
        '</span>',
        de_part,
        label_en,
    )


def bilingual_cost_type_labels(*, include_code=True):
    """Map flag_field -> safe HTML label for forms."""
    return {
        flag: bilingual_cost_type_label(code, de, en, include_code=include_code)
        for flag, _amount, code, de, en in PSP_COST_TYPES
    }


def short_header_label(code, label_de):
    """Compact header for year-estimate columns."""
    return f'.{code} {label_de}'


def clear_disabled_year_estimate_amounts(parent):
    """
    Null amount fields whose matching cost-type flag is false.

    Works for WBSElement and CostCenter (both use related_name='year_estimates').
    """
    for estimate in parent.year_estimates.all():
        update_fields = []
        for flag_field, amount_field, *_rest in PSP_COST_TYPES:
            if not getattr(parent, flag_field) and getattr(estimate, amount_field) is not None:
                setattr(estimate, amount_field, None)
                update_fields.append(amount_field)
        if update_fields:
            estimate.save(update_fields=update_fields + ['updated_at'])
