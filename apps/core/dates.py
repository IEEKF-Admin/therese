"""Parse European dates and expand two-digit years to 20xx."""

from __future__ import annotations

import re
from datetime import date, datetime

from django import forms

_TWO_DIGIT_YEAR = re.compile(
    r'^(?P<day>\d{1,2})(?P<sep>[.\-/])(?P<month>\d{1,2})(?P=sep)(?P<year>\d{2})$'
)


def expand_two_digit_year(value):
    """Turn ``01.01.28`` into ``01.01.2028``. Four-digit years are unchanged."""
    if not isinstance(value, str):
        return value
    text = value.strip()
    match = _TWO_DIGIT_YEAR.match(text)
    if not match:
        return value
    return (
        f'{int(match.group("day")):02d}.'
        f'{int(match.group("month")):02d}.'
        f'20{match.group("year")}'
    )


class EuropeanDateField(forms.DateField):
    """Date field (DD.MM.YYYY) that treats a 2-digit year as 20xx."""

    def __init__(self, **kwargs):
        kwargs.setdefault('input_formats', ['%d.%m.%Y', '%Y-%m-%d'])
        super().__init__(**kwargs)

    def to_python(self, value):
        if value in self.empty_values:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return super().to_python(expand_two_digit_year(value))
