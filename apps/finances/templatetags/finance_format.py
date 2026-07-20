"""Formatting helpers for finances UI (German thousand separators)."""

from decimal import Decimal, InvalidOperation

from django import template
from django.utils.formats import number_format

register = template.Library()


@register.filter(name='de_number')
def de_number(value, decimals=2):
    """
    Format a number with German thousand separators (points) and comma decimals.

    Example: 1234567.8 → "1.234.567,80"
    Returns empty string for None so templates can still show a fallback.
    """
    if value is None or value == '':
        return ''
    try:
        if not isinstance(value, Decimal):
            value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return str(value)

    try:
        decimals = int(decimals)
    except (TypeError, ValueError):
        decimals = 2

    return number_format(
        value,
        decimal_pos=decimals,
        use_l10n=True,
        force_grouping=True,
    )
