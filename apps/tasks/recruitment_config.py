"""Recruitment job field rules, limitation reasons, and duration helpers."""

from __future__ import annotations

from datetime import date
from typing import Any


class DurationOperator:
    LT = 'lt'
    LTE = 'lte'
    GT = 'gt'
    GTE = 'gte'
    EQ = 'eq'

    CHOICES = [
        (LT, 'Less than'),
        (LTE, 'Less than or equal'),
        (GT, 'Greater than'),
        (GTE, 'Greater than or equal'),
        (EQ, 'Equal to'),
    ]


class VisibilityMode:
    ALWAYS = 'always'
    NEVER = 'never'
    WHEN_DURATION = 'when_duration'

    CHOICES = [
        (ALWAYS, 'Always visible'),
        (NEVER, 'Never visible'),
        (WHEN_DURATION, 'Visible when duration matches'),
    ]


class RequiredMode:
    NEVER = 'never'
    ALWAYS = 'always'
    WHEN_DURATION = 'when_duration'

    CHOICES = [
        (NEVER, 'Optional'),
        (ALWAYS, 'Always required'),
        (WHEN_DURATION, 'Required when duration matches'),
    ]


RECRUITMENT_CONFIGURABLE_FIELDS = [
    ('prefix', 'Prefix / Title', 'Präfix / Titel'),
    ('first_name', 'First Name', 'Vorname'),
    ('last_name', 'Last Name', 'Nachname'),
    ('gender', 'Gender', 'Geschlecht'),
    ('date_of_birth', 'Date of Birth', 'Geburtsdatum'),
    ('country_of_origin', 'Country of Origin', 'Herkunftsland'),
    ('place_of_birth', 'Place of Birth', 'Geburtsort'),
    ('street', 'Street', 'Straße'),
    ('house_number', 'House Number', 'Hausnummer'),
    ('postal_code', 'Postal Code', 'Postleitzahl'),
    ('city', 'City', 'Stadt'),
    ('country', 'Country', 'Land'),
    ('email_private', 'Private Email', 'Private E-Mail'),
    ('private_phone_number', 'Private Phone', 'Private Telefonnummer'),
    ('job', 'Job', 'Job'),
    ('pay_scale_group', 'Pay Scale Group', 'Entgeltgruppe'),
    ('experience_level', 'Experience Level', 'Erfahrungsstufe'),
    ('plan_position_number', 'Plan Position Number', 'Planstellen-Nummer'),
    ('valid_from', 'Contract Start Date', 'Vertragsbeginn'),
    ('valid_until', 'Contract End Date', 'Vertragsende'),
    ('limitation_reason', 'Limitation Reason', 'Befristungsgrund'),
    ('cv_file', 'Curriculum Vitae', 'Lebenslauf'),
    ('latest_degree_certificate_file', 'Latest Degree Certificate', 'Zeugnis des letzten Abschlusses'),
    ('funding_allocations', 'Funding Allocations', 'Finanzierungszuordnungen'),
]

DEFAULT_OPTIONAL_FIELDS = {
    'prefix',
    'gender',
    'private_phone_number',
    'plan_position_number',
    'limitation_reason',
}

FILE_FIELDS = {'cv_file', 'latest_degree_certificate_file'}


def contract_duration_months(start: date | None, end: date | None) -> int | None:
    """Return the contract duration in full calendar months."""
    if not start or not end:
        return None
    if end < start:
        return 0
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day >= start.day:
        months += 1
    return max(months, 0)


def _compare_duration(months: int, operator: str, threshold: int) -> bool:
    if operator == DurationOperator.LT:
        return months < threshold
    if operator == DurationOperator.LTE:
        return months <= threshold
    if operator == DurationOperator.GT:
        return months > threshold
    if operator == DurationOperator.GTE:
        return months >= threshold
    if operator == DurationOperator.EQ:
        return months == threshold
    return False


def is_field_visible(rule, months: int | None) -> bool:
    if rule is None:
        return True
    if rule.visibility_mode == VisibilityMode.NEVER:
        return False
    if rule.visibility_mode == VisibilityMode.WHEN_DURATION:
        if months is None:
            return False
        return _compare_duration(
            months,
            rule.visibility_duration_operator,
            rule.visibility_duration_months,
        )
    return True


def is_field_required(rule, months: int | None, field_key: str, *, is_creation: bool = True) -> bool:
    if rule is None:
        if field_key in DEFAULT_OPTIONAL_FIELDS:
            return False
        if field_key in FILE_FIELDS:
            return is_creation
        if field_key == 'funding_allocations':
            return True
        return True

    if rule.required_mode == RequiredMode.NEVER:
        return False
    if rule.required_mode == RequiredMode.WHEN_DURATION:
        if months is None:
            return False
        if not _compare_duration(
            months,
            rule.required_duration_operator,
            rule.required_duration_months,
        ):
            return False
        return True
    if rule.required_mode == RequiredMode.ALWAYS:
        return True
    return False


def get_rules_for_job(job) -> dict[str, Any]:
    if not job:
        return {}
    return {rule.field_key: rule for rule in job.field_rules.all()}


def serialize_job_rules(job) -> dict[str, dict]:
    rules = get_rules_for_job(job)
    payload = {}
    for field_key, _, _ in RECRUITMENT_CONFIGURABLE_FIELDS:
        rule = rules.get(field_key)
        payload[field_key] = {
            'visibility_mode': getattr(rule, 'visibility_mode', VisibilityMode.ALWAYS),
            'visibility_duration_operator': getattr(rule, 'visibility_duration_operator', ''),
            'visibility_duration_months': getattr(rule, 'visibility_duration_months', None),
            'required_mode': getattr(rule, 'required_mode', RequiredMode.NEVER if field_key in DEFAULT_OPTIONAL_FIELDS else RequiredMode.ALWAYS),
            'required_duration_operator': getattr(rule, 'required_duration_operator', ''),
            'required_duration_months': getattr(rule, 'required_duration_months', None),
        }
    return payload


def serialize_all_job_rules() -> dict[str, dict]:
    from apps.tasks.models import RecruitmentJob

    return {
        str(job.pk): serialize_job_rules(job)
        for job in RecruitmentJob.objects.filter(is_active=True).prefetch_related('field_rules')
    }


def serialize_limitation_reasons() -> list[dict]:
    from apps.tasks.models import LimitationReason

    reasons = []
    for reason in LimitationReason.objects.filter(is_active=True).prefetch_related('jobs'):
        reasons.append({
            'id': reason.pk,
            'title': reason.title,
            'text': reason.text,
            'applies_to_all_jobs': reason.applies_to_all_jobs,
            'job_ids': list(reason.jobs.values_list('pk', flat=True)),
        })
    return reasons


def limitation_reasons_for_job(job_id: int | None) -> list[dict]:
    reasons = serialize_limitation_reasons()
    if not job_id:
        return reasons
    filtered = []
    for reason in reasons:
        if reason['applies_to_all_jobs'] or job_id in reason['job_ids']:
            filtered.append(reason)
    return filtered