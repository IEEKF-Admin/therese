"""Recruitment job field rules, limitation reasons, and duration helpers."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any


STANDARD_JOB_NAME = 'Standard'


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
    INHERIT = 'inherit'
    ALWAYS = 'always'
    NEVER = 'never'
    WHEN_DURATION = 'when_duration'
    WHEN_FIELD_SET = 'when_field_set'

    CHOICES = [
        (ALWAYS, 'Always visible'),
        (NEVER, 'Never visible'),
        (WHEN_DURATION, 'Visible when duration matches'),
        (WHEN_FIELD_SET, 'Visible when field X is set'),
    ]
    CHOICES_WITH_INHERIT = [
        (INHERIT, 'Use Standard'),
        *CHOICES,
    ]


class RequiredMode:
    INHERIT = 'inherit'
    NEVER = 'never'
    ALWAYS = 'always'
    WHEN_DURATION = 'when_duration'

    CHOICES = [
        (NEVER, 'Optional'),
        (ALWAYS, 'Always required'),
        (WHEN_DURATION, 'Required when duration matches'),
    ]
    CHOICES_WITH_INHERIT = [
        (INHERIT, 'Use Standard'),
        *CHOICES,
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
    ('qualification', 'Qualification', 'Qualifikation'),
    ('job', 'Job', 'Job'),
    ('working_as', 'Working As', 'Tätigkeit'),
    ('pay_scale_group', 'Pay Scale Group', 'Entgeltstufe'),
    ('experience_level', 'Experience Level', 'Erfahrungsstufe'),
    ('weekly_hours', 'Weekly Working Hours', 'Wochenarbeitszeit'),
    ('monthly_salary', 'Theoretical Monthly Salary for 100% Workload', 'Theoretisches Monatsgehalt bei 100%'),
    ('valid_from', 'Contract Start Date', 'Vertragsbeginn'),
    ('valid_until', 'Contract End Date', 'Vertragsende'),
    ('limitation_reason', 'Limitation Reason', 'Befristungsgrund'),
    ('cv_file', 'Curriculum Vitae', 'Lebenslauf'),
    ('latest_degree_certificate_file', 'Latest Degree Certificate', 'Zeugnis des letzten Abschlusses'),
    ('funding_allocations', 'Funding Allocations', 'Finanzierungszuordnungen'),
]

CONFIGURABLE_FIELD_KEYS = [field_key for field_key, _, _ in RECRUITMENT_CONFIGURABLE_FIELDS]
CONFIGURABLE_FIELD_LABELS = {
    field_key: label_en for field_key, label_en, _label_de in RECRUITMENT_CONFIGURABLE_FIELDS
}

DEFAULT_OPTIONAL_FIELDS = {
    'prefix',
    'gender',
    'private_phone_number',
    'qualification',
    'limitation_reason',
    'working_as',
    'pay_scale_group',
    'experience_level',
    'monthly_salary',
    'weekly_hours',
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


def _value_is_set(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def is_field_visible(rule, months: int | None, field_values: dict | None = None) -> bool:
    if rule is None:
        return True
    mode = getattr(rule, 'visibility_mode', VisibilityMode.ALWAYS)
    if mode in (VisibilityMode.INHERIT, '', None):
        return True
    if mode == VisibilityMode.NEVER:
        return False
    if mode == VisibilityMode.WHEN_DURATION:
        if months is None:
            return False
        return _compare_duration(
            months,
            getattr(rule, 'visibility_duration_operator', ''),
            getattr(rule, 'visibility_duration_months', None),
        )
    if mode == VisibilityMode.WHEN_FIELD_SET:
        trigger = getattr(rule, 'visibility_trigger_field', '') or ''
        if not trigger:
            return False
        values = field_values or {}
        return _value_is_set(values.get(trigger))
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

    mode = getattr(rule, 'required_mode', RequiredMode.NEVER)
    if mode in (RequiredMode.INHERIT, '', None):
        if field_key in DEFAULT_OPTIONAL_FIELDS:
            return False
        if field_key in FILE_FIELDS:
            return is_creation
        return True
    if mode == RequiredMode.NEVER:
        return False
    if mode == RequiredMode.WHEN_DURATION:
        if months is None:
            return False
        if not _compare_duration(
            months,
            getattr(rule, 'required_duration_operator', ''),
            getattr(rule, 'required_duration_months', None),
        ):
            return False
        return True
    if mode == RequiredMode.ALWAYS:
        return True
    return False


def default_rule_payload(field_key: str) -> dict:
    return {
        'visibility_mode': VisibilityMode.ALWAYS,
        'visibility_duration_operator': '',
        'visibility_duration_months': None,
        'visibility_trigger_field': '',
        'required_mode': (
            RequiredMode.NEVER if field_key in DEFAULT_OPTIONAL_FIELDS else RequiredMode.ALWAYS
        ),
        'required_duration_operator': '',
        'required_duration_months': None,
        'help_text': '',
    }


def rule_to_payload(rule, field_key: str) -> dict:
    payload = default_rule_payload(field_key)
    if rule is None:
        return payload
    payload.update({
        'visibility_mode': getattr(rule, 'visibility_mode', payload['visibility_mode']),
        'visibility_duration_operator': getattr(rule, 'visibility_duration_operator', '') or '',
        'visibility_duration_months': getattr(rule, 'visibility_duration_months', None),
        'visibility_trigger_field': getattr(rule, 'visibility_trigger_field', '') or '',
        'required_mode': getattr(rule, 'required_mode', payload['required_mode']),
        'required_duration_operator': getattr(rule, 'required_duration_operator', '') or '',
        'required_duration_months': getattr(rule, 'required_duration_months', None),
        'help_text': (getattr(rule, 'help_text', '') or '').strip(),
    })
    return payload


def _merge_payload(job_payload: dict, standard_payload: dict) -> dict:
    merged = dict(standard_payload)
    vis_mode = job_payload.get('visibility_mode') or VisibilityMode.INHERIT
    if vis_mode != VisibilityMode.INHERIT:
        merged['visibility_mode'] = vis_mode
        merged['visibility_duration_operator'] = job_payload.get('visibility_duration_operator') or ''
        merged['visibility_duration_months'] = job_payload.get('visibility_duration_months')
        merged['visibility_trigger_field'] = job_payload.get('visibility_trigger_field') or ''
    req_mode = job_payload.get('required_mode') or RequiredMode.INHERIT
    if req_mode != RequiredMode.INHERIT:
        merged['required_mode'] = req_mode
        merged['required_duration_operator'] = job_payload.get('required_duration_operator') or ''
        merged['required_duration_months'] = job_payload.get('required_duration_months')
    help_text = (job_payload.get('help_text') or '').strip()
    if help_text:
        merged['help_text'] = help_text
    else:
        merged['help_text'] = (standard_payload.get('help_text') or '').strip()
    return merged


def payload_as_rule(payload: dict) -> SimpleNamespace:
    return SimpleNamespace(**payload)


def get_standard_job():
    from apps.tasks.models import RecruitmentJob

    return (
        RecruitmentJob.objects.filter(is_standard=True)
        .prefetch_related('field_rules')
        .first()
    )


def visible_recruitment_jobs(*, include=None):
    from django.db.models import Q

    from apps.tasks.models import RecruitmentJob

    queryset = RecruitmentJob.objects.filter(is_active=True, is_standard=False)
    if include is not None:
        include_pk = getattr(include, 'pk', include)
        if include_pk:
            queryset = RecruitmentJob.objects.filter(
                Q(pk__in=queryset.values('pk')) | Q(pk=include_pk)
            )
    return queryset.order_by('name')


def get_rules_for_job(job) -> dict[str, Any]:
    if not job:
        return {}
    return {rule.field_key: rule for rule in job.field_rules.all()}


def get_effective_rules_for_job(job) -> dict[str, SimpleNamespace]:
    """Resolved rules: Standard values fill in any inherit/empty settings."""
    if not job:
        return {
            field_key: payload_as_rule(default_rule_payload(field_key))
            for field_key, _, _ in RECRUITMENT_CONFIGURABLE_FIELDS
        }

    job_rules = get_rules_for_job(job)
    standard = None if getattr(job, 'is_standard', False) else get_standard_job()
    standard_rules = get_rules_for_job(standard) if standard else {}

    effective = {}
    for field_key, _, _ in RECRUITMENT_CONFIGURABLE_FIELDS:
        std_payload = rule_to_payload(standard_rules.get(field_key), field_key)
        if getattr(job, 'is_standard', False):
            job_payload = rule_to_payload(job_rules.get(field_key), field_key)
            if job_payload['visibility_mode'] == VisibilityMode.INHERIT:
                job_payload['visibility_mode'] = VisibilityMode.ALWAYS
            if job_payload['required_mode'] == RequiredMode.INHERIT:
                job_payload['required_mode'] = default_rule_payload(field_key)['required_mode']
            effective[field_key] = payload_as_rule(job_payload)
            continue
        job_payload = rule_to_payload(job_rules.get(field_key), field_key)
        if not job_rules.get(field_key):
            job_payload['visibility_mode'] = VisibilityMode.INHERIT
            job_payload['required_mode'] = RequiredMode.INHERIT
        effective[field_key] = payload_as_rule(_merge_payload(job_payload, std_payload))
    return effective


def serialize_job_rules(job) -> dict[str, dict]:
    rules = get_effective_rules_for_job(job)
    payload = {}
    for field_key, _, _ in RECRUITMENT_CONFIGURABLE_FIELDS:
        rule = rules[field_key]
        payload[field_key] = {
            'visibility_mode': rule.visibility_mode,
            'visibility_duration_operator': rule.visibility_duration_operator,
            'visibility_duration_months': rule.visibility_duration_months,
            'visibility_trigger_field': rule.visibility_trigger_field,
            'required_mode': rule.required_mode,
            'required_duration_operator': rule.required_duration_operator,
            'required_duration_months': rule.required_duration_months,
            'help_text': rule.help_text,
        }
    return payload


def serialize_all_job_rules() -> dict[str, dict]:
    from apps.tasks.models import RecruitmentJob

    return {
        str(job.pk): serialize_job_rules(job)
        for job in visible_recruitment_jobs().prefetch_related('field_rules')
    }


def inherited_job_text(job, attr: str) -> str:
    value = (getattr(job, attr, None) or '').strip() if job else ''
    if value:
        return value
    if job and getattr(job, 'is_standard', False):
        return ''
    standard = get_standard_job()
    if not standard or standard == job:
        return ''
    return (getattr(standard, attr, None) or '').strip()


def inherited_job_payscale(job) -> dict:
    """TV-L / estimate defaults, falling back to the Standard job when unset."""
    empty = {
        'pay_scale_group': '',
        'experience_level': None,
        'estimated_monthly_salary': None,
        'has_fixed_estimate': False,
    }
    if not job:
        return empty

    def from_job(source):
        if not source:
            return empty
        group = source.pay_scale_group or ''
        level = source.experience_level
        estimate = source.estimated_monthly_salary
        has_tvl = bool(group) and level is not None
        has_estimate = estimate is not None and not has_tvl
        return {
            'pay_scale_group': group,
            'experience_level': level,
            'estimated_monthly_salary': estimate,
            'has_fixed_estimate': has_estimate,
        }

    own = from_job(job)
    has_own = bool(own['pay_scale_group']) or own['experience_level'] is not None or own['has_fixed_estimate']
    if has_own or getattr(job, 'is_standard', False):
        return own
    return from_job(get_standard_job())


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
