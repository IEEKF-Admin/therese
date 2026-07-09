"""Shared helpers for recruitment and contract extension forms."""

from django import forms

from apps.hr.document_utils import validate_personnel_document
from apps.tasks.recruitment_config import (
    FILE_FIELDS,
    RECRUITMENT_CONFIGURABLE_FIELDS,
    contract_duration_months,
    get_rules_for_job,
    is_field_required,
    is_field_visible,
    limitation_reasons_for_job,
    serialize_limitation_reasons,
)


def add_limitation_reason_template_field(form, *, job_id=None, include_all_reasons=False):
    if include_all_reasons or not job_id:
        reasons = serialize_limitation_reasons()
    else:
        reasons = limitation_reasons_for_job(job_id)

    choices = [('', '-Empty-')]
    for reason in reasons:
        choices.append((str(reason['id']), reason['title']))

    form.fields['limitation_reason_template'] = forms.ChoiceField(
        choices=choices,
        required=False,
        label='Limitation Reason Template',
        widget=forms.Select(attrs={
            'class': 'form-control limitation-reason-template',
            'data-limitation-template': 'true',
        }),
    )


def configure_recruitment_job_field(form):
    from apps.tasks.models import RecruitmentJob

    form.fields['job'] = forms.ModelChoiceField(
        queryset=RecruitmentJob.objects.filter(is_active=True).order_by('name'),
        empty_label='— Select job —',
        label='Job',
        widget=forms.Select(attrs={
            'class': 'form-control',
            'data-recruitment-job': 'true',
        }),
    )
    form.fields['job'].required = True


def apply_recruitment_field_defaults(form, *, is_creation):
    optional_always = {'prefix', 'comment', 'gender', 'private_phone_number', 'limitation_reason'}
    for field_name, field in form.fields.items():
        if field_name in optional_always:
            field.required = False
        elif field_name in FILE_FIELDS:
            field.required = is_creation
        elif field_name == 'plan_position_number':
            field.required = not is_creation
        elif field_name not in ('assignee', 'status'):
            field.required = True

    if 'limitation_reason' in form.fields:
        form.fields['limitation_reason'].widget = forms.Textarea(attrs={
            'class': 'form-control limitation-reason-text',
            'rows': 3,
            'data-limitation-text': 'true',
        })


def validate_recruitment_dynamic_rules(form, cleaned_data, *, is_creation, files=None):
    job = cleaned_data.get('job')
    months = contract_duration_months(
        cleaned_data.get('valid_from'),
        cleaned_data.get('valid_until'),
    )
    rules = get_rules_for_job(job)
    files = files or {}

    for field_key, label_en, _label_de in RECRUITMENT_CONFIGURABLE_FIELDS:
        rule = rules.get(field_key)
        visible = is_field_visible(rule, months)
        required = is_field_required(rule, months, field_key, is_creation=is_creation)

        if not visible:
            continue

        if field_key == 'funding_allocations':
            continue

        if field_key in FILE_FIELDS:
            uploaded = cleaned_data.get(field_key) or files.get(field_key)
            existing = getattr(form.instance, field_key, None) if form.instance and form.instance.pk else None
            if required and not uploaded and not existing:
                form.add_error(field_key, 'This document is required.')
            elif uploaded:
                try:
                    validate_personnel_document(uploaded)
                except forms.ValidationError as exc:
                    form.add_error(field_key, exc.messages[0])
            continue

        if not required:
            continue

        value = cleaned_data.get(field_key)
        if value in (None, ''):
            form.add_error(field_key, 'This field is required.')


def validate_funding_allocations_required(formset, job, cleaned_data, *, is_creation):
    months = contract_duration_months(
        cleaned_data.get('valid_from'),
        cleaned_data.get('valid_until'),
    )
    rules = get_rules_for_job(job)
    rule = rules.get('funding_allocations')
    required = is_field_required(rule, months, 'funding_allocations', is_creation=is_creation)
    if not required:
        return

    active_forms = [
        item_form for item_form in formset.forms
        if item_form.cleaned_data
        and not item_form.cleaned_data.get('DELETE', False)
        and item_form.cleaned_data.get('wbs_element')
    ]
    if not active_forms:
        raise forms.ValidationError('At least one funding allocation is required.')


def parse_post_date(value):
    if not value:
        return None
    from datetime import datetime
    for fmt in ('%d.%m.%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            continue
    return None


def build_recruitment_template_context():
    import json

    from apps.finances.models import PayScale
    from apps.tasks.models import RecruitmentJob
    from apps.tasks.recruitment_config import (
        RECRUITMENT_CONFIGURABLE_FIELDS,
        serialize_all_job_rules,
        serialize_limitation_reasons,
    )

    field_keys = {field_key: True for field_key, _, _ in RECRUITMENT_CONFIGURABLE_FIELDS}
    job_payscale = {}
    for job in RecruitmentJob.objects.filter(is_active=True):
        salary = job.get_estimated_monthly_salary()
        job_payscale[str(job.pk)] = {
            'pay_scale_group': job.pay_scale_group or '',
            'experience_level': job.experience_level,
            'estimated_salary': str(salary) if salary is not None else None,
        }

    current = PayScale.get_current()
    payscale_data = {}
    for ps in current:
        group = ps.pay_scale_group
        if group not in payscale_data:
            payscale_data[group] = []
        payscale_data[group].append({
            'experience_level': ps.experience_level,
            'monthly_salary': str(ps.monthly_salary),
        })

    return {
        'recruitment_job_rules_json': json.dumps(serialize_all_job_rules()),
        'limitation_reasons_json': json.dumps(serialize_limitation_reasons()),
        'recruitment_field_keys_json': json.dumps(field_keys),
        'recruitment_job_payscale_json': json.dumps(job_payscale),
        'recruitment_payscale_data_json': json.dumps(payscale_data),
    }


def funding_formset_kwargs_from_post(post_data, *, is_creation=True):
    from apps.tasks.models import RecruitmentJob

    job = None
    job_id = post_data.get('job')
    if job_id:
        job = RecruitmentJob.objects.filter(pk=job_id).first()
    return {
        'job': job,
        'contract_dates': {
            'valid_from': parse_post_date(post_data.get('valid_from')),
            'valid_until': parse_post_date(post_data.get('valid_until')),
        },
        'is_creation': is_creation,
    }


def save_field_rules_from_post(job, post_data):
    from apps.tasks.models import RecruitmentJobFieldRule
    from apps.tasks.recruitment_config import DurationOperator, RequiredMode, VisibilityMode

    for field_key, _, _ in RECRUITMENT_CONFIGURABLE_FIELDS:
        visibility_mode = post_data.get(f'rule_{field_key}_visibility_mode', VisibilityMode.ALWAYS)
        required_mode = post_data.get(f'rule_{field_key}_required_mode', RequiredMode.NEVER)

        visibility_months = post_data.get(f'rule_{field_key}_visibility_months') or None
        required_months = post_data.get(f'rule_{field_key}_required_months') or None
        if visibility_months:
            visibility_months = int(visibility_months)
        if required_months:
            required_months = int(required_months)

        rule, _ = RecruitmentJobFieldRule.objects.get_or_create(job=job, field_key=field_key)
        rule.visibility_mode = visibility_mode
        rule.visibility_duration_operator = post_data.get(
            f'rule_{field_key}_visibility_operator', '',
        ) or DurationOperator.LT
        rule.visibility_duration_months = visibility_months
        rule.required_mode = required_mode
        rule.required_duration_operator = post_data.get(
            f'rule_{field_key}_required_operator', '',
        ) or DurationOperator.LT
        rule.required_duration_months = required_months
        rule.save()


def get_field_rule_context(job):
    from apps.tasks.recruitment_config import DurationOperator, RequiredMode, VisibilityMode

    existing = {rule.field_key: rule for rule in job.field_rules.all()} if job and job.pk else {}
    rows = []
    for field_key, label_en, label_de in RECRUITMENT_CONFIGURABLE_FIELDS:
        rule = existing.get(field_key)
        rows.append({
            'field_key': field_key,
            'label_en': label_en,
            'label_de': label_de,
            'visibility_mode': getattr(rule, 'visibility_mode', VisibilityMode.ALWAYS),
            'visibility_duration_operator': getattr(rule, 'visibility_duration_operator', DurationOperator.LT),
            'visibility_duration_months': getattr(rule, 'visibility_duration_months', ''),
            'required_mode': getattr(
                rule,
                'required_mode',
                RequiredMode.NEVER,
            ),
            'required_duration_operator': getattr(rule, 'required_duration_operator', DurationOperator.LT),
            'required_duration_months': getattr(rule, 'required_duration_months', ''),
        })
    return rows