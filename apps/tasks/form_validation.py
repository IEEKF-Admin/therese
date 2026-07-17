"""Shared server-side validation helpers for task creation forms."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django import forms
from django.core.validators import URLValidator


DATE_PARSE_FORMATS = ('%d.%m.%Y', '%Y-%m-%d')


def parse_german_date(value):
    """Parse DD.MM.YYYY or ISO date strings; return date or None."""
    if not value:
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in DATE_PARSE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def strip_cleaned_text(cleaned_data, *field_names):
    """Strip whitespace from string fields in cleaned_data."""
    for field_name in field_names:
        value = cleaned_data.get(field_name)
        if isinstance(value, str):
            cleaned_data[field_name] = value.strip()


def validate_pdf_upload(form, uploaded_file, field_name, *, required=False):
    """Accept a single PDF upload; optionally required."""
    if not uploaded_file:
        if required:
            form.add_error(field_name, 'This field is required.')
        return
    from apps.core.upload_validation import MAX_QUOTE_UPLOAD_BYTES, PDF_EXT, validate_upload
    from django.core.exceptions import ValidationError

    try:
        validate_upload(
            uploaded_file,
            allowed_extensions=PDF_EXT,
            max_bytes=MAX_QUOTE_UPLOAD_BYTES,
            require_magic=True,
        )
    except ValidationError as exc:
        form.add_error(field_name, exc.messages[0] if exc.messages else str(exc))


def require_non_empty_text(form, cleaned_data, field_name, *, message=None):
    """Reject blank or whitespace-only text."""
    value = cleaned_data.get(field_name)
    if value is None:
        return
    if isinstance(value, str):
        value = value.strip()
        cleaned_data[field_name] = value
    if value in (None, ''):
        form.add_error(
            field_name,
            message or 'This field is required.',
        )


def validate_contract_dates(
    form,
    cleaned_data,
    *,
    start_field='valid_from',
    end_field='valid_until',
    require_start=False,
    require_end=False,
):
    """Ensure contract dates are present and end is not before start."""
    start = cleaned_data.get(start_field)
    end = cleaned_data.get(end_field)

    if require_start and not start:
        form.add_error(start_field, 'Start date is required.')
    if require_end and not end:
        form.add_error(end_field, 'End date is required.')
    if start and end and end < start:
        form.add_error(
            end_field,
            'End date must be on or after the start date.',
        )


def validate_positive_decimal(
    form,
    cleaned_data,
    field_name,
    *,
    min_value=Decimal('0'),
    allow_zero=False,
    message=None,
):
    """Validate numeric fields are positive (or non-negative if allow_zero)."""
    value = cleaned_data.get(field_name)
    if value in (None, ''):
        return
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        form.add_error(field_name, 'Enter a valid number.')
        return
    cleaned_data[field_name] = decimal_value
    threshold = min_value if allow_zero else min_value
    if not allow_zero and decimal_value <= threshold:
        form.add_error(
            field_name,
            message or f'Value must be greater than {threshold}.',
        )
    elif allow_zero and decimal_value < threshold:
        form.add_error(
            field_name,
            message or f'Value must be at least {threshold}.',
        )


def validate_positive_integer(
    form,
    cleaned_data,
    field_name,
    *,
    min_value=1,
    message=None,
):
    """Validate integer fields (e.g. quantity)."""
    value = cleaned_data.get(field_name)
    if value in (None, ''):
        return
    try:
        int_value = int(value)
    except (TypeError, ValueError):
        form.add_error(field_name, 'Enter a valid whole number.')
        return
    cleaned_data[field_name] = int_value
    if int_value < min_value:
        form.add_error(
            field_name,
            message or f'Value must be at least {min_value}.',
        )


def validate_url_field(form, cleaned_data, field_name, *, required=False):
    """Validate URL format when a value is provided."""
    value = cleaned_data.get(field_name)
    if isinstance(value, str):
        value = value.strip()
        cleaned_data[field_name] = value
    if not value:
        if required:
            form.add_error(field_name, 'This field is required.')
        return
    validator = URLValidator()
    try:
        validator(value)
    except forms.ValidationError:
        form.add_error(field_name, 'Enter a valid URL (e.g. https://example.com).')