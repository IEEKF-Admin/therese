"""Map WBS cost-type suffixes (.1–.9) to model flag/amount fields."""

from apps.finances.psp_cost_types import PSP_COST_TYPES

# code ('1'..'9') -> (flag_field, amount_field)
SUFFIX_TO_COST_TYPE = {
    code: (flag, amount)
    for flag, amount, code, _de, _en in PSP_COST_TYPES
}

COST_TYPE_LABELS = {
    code: f'.{code} {de}'
    for _flag, _amount, code, de, _en in PSP_COST_TYPES
}
