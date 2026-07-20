from decimal import Decimal, InvalidOperation

from django import template
from django.utils.formats import number_format

from apps.core.file_service import ThereseFileService

register = template.Library()


@register.filter
def file_display_name(file_field):
    """
    Return the original upload filename for a FileField/FieldFile, falling back
    to the storage basename. Storage paths may be UUID-renamed when too long.
    """
    if not file_field:
        return ''
    name = getattr(file_field, 'name', None) or str(file_field)
    return ThereseFileService.display_name(name)


@register.filter(name='de_number')
def de_number(value, decimals=2):
    """
    Format a number with German thousand separators (points) and comma decimals.

    Example: 1234567.8 → "1.234.567,80"
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
