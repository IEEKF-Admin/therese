"""Shared helpers for recruitment and contract extension forms."""

from django import forms

from apps.core.upload_validation import PDF_EXT, validate_upload
from apps.hr.document_utils import validate_personnel_document
from apps.tasks.limitation_pdf import is_new_limitation_file
from apps.tasks.form_validation import (
    parse_german_date,
    require_non_empty_text,
    validate_contract_dates,
)
from apps.tasks.recruitment_config import (
    FILE_FIELDS,
    RECRUITMENT_CONFIGURABLE_FIELDS,
    contract_duration_months,
    get_effective_rules_for_job,
    inherited_job_payscale,
    inherited_job_text,
    is_field_required,
    is_field_visible,
    limitation_reasons_for_job,
    serialize_limitation_reasons,
    visible_recruitment_jobs,
)


def add_limitation_reason_template_field(form, *, job_id=None, include_all_reasons=False):
    if include_all_reasons or not job_id:
        reasons = serialize_limitation_reasons()
    else:
        reasons = limitation_reasons_for_job(job_id)

    choices = [('', '-Empty-')]
    for reason in reasons:
        choices.append((str(reason['id']), reason['title']))

    # CharField + Select: UI helper only, never validated against choices or saved.
    form.fields['limitation_reason_template'] = forms.CharField(
        required=False,
        label='Limitation Reason Template',
        widget=forms.Select(choices=choices, attrs={
            'class': 'form-control limitation-reason-template',
            'data-limitation-template': 'true',
        }),
    )


def strip_limitation_reason_template(cleaned_data):
    cleaned_data.pop('limitation_reason_template', None)
    return cleaned_data


def configure_recruitment_payscale_fields(form):
    from apps.finances.models import PayScale

    current = PayScale.get_current()
    groups = (
        current.values_list('pay_scale_group', flat=True)
        .distinct()
        .order_by('pay_scale_group')
    )
    pay_scale_choices = [('', '— Select pay scale group —')] + [(g, g) for g in groups]
    level_choices = [('', '— Select group first —')] + [(str(i), str(i)) for i in range(1, 7)]

    form.fields['pay_scale_group'] = forms.ChoiceField(
        choices=pay_scale_choices,
        required=False,
        label='Entgeltstufe',
        widget=forms.Select(attrs={
            'class': 'form-control',
            'data-recruitment-payscale-group': 'true',
        }),
    )
    form.fields['experience_level'] = forms.ChoiceField(
        choices=level_choices,
        required=False,
        label='Erfahrungsstufe',
        widget=forms.Select(attrs={
            'class': 'form-control',
            'data-recruitment-experience-level': 'true',
        }),
    )

    instance = form.instance
    if form.data.get('pay_scale_group'):
        form.fields['pay_scale_group'].initial = form.data.get('pay_scale_group')
    elif instance and instance.pay_scale_group:
        form.fields['pay_scale_group'].initial = instance.pay_scale_group
    elif instance and getattr(instance, 'job_id', None) and instance.job.pay_scale_group:
        form.fields['pay_scale_group'].initial = instance.job.pay_scale_group

    if form.data.get('experience_level'):
        form.fields['experience_level'].initial = form.data.get('experience_level')
    elif instance and instance.experience_level is not None:
        form.fields['experience_level'].initial = str(instance.experience_level)
    elif instance and getattr(instance, 'job_id', None) and instance.job.experience_level is not None:
        form.fields['experience_level'].initial = str(instance.job.experience_level)


def configure_recruitment_job_field(form):
    include = None
    instance = getattr(form, 'instance', None)
    if instance and getattr(instance, 'job_id', None):
        include = instance.job
    form.fields['job'] = forms.ModelChoiceField(
        queryset=visible_recruitment_jobs(include=include),
        empty_label='— Select job —',
        label='Job',
        widget=forms.Select(attrs={
            'class': 'form-control',
            'data-recruitment-job': 'true',
        }),
    )
    form.fields['job'].required = True


def apply_recruitment_field_defaults(form, *, is_creation):
    optional_always = {
        'prefix', 'initial_message', 'gender', 'private_phone_number',
        'limitation_reason', 'limitation_reason_file', 'working_as', 'weekly_hours',
        'pay_scale_group', 'experience_level', 'monthly_salary',
        'qualification', 'valid_until',
    }
    for field_name, field in form.fields.items():
        if field_name in optional_always:
            field.required = False
        elif field_name in FILE_FIELDS:
            field.required = is_creation
        elif field_name not in ('assignee', 'status'):
            field.required = True

    if 'limitation_reason' in form.fields:
        form.fields['limitation_reason'].widget = forms.Textarea(attrs={
            'class': 'form-control limitation-reason-text',
            'rows': 3,
            'data-limitation-text': 'true',
        })


def configure_limitation_reason_file_field(form):
    field = form.fields.get('limitation_reason_file')
    if field is None:
        return
    field.required = False
    attrs = {
        'class': 'form-control',
        'accept': '.pdf,application/pdf',
        'data-limitation-file': 'true',
    }
    instance = getattr(form, 'instance', None)
    has_file = bool(
        instance
        and getattr(instance, 'pk', None)
        and getattr(instance, 'limitation_reason_file', None)
        and instance.limitation_reason_file
    )
    generated = bool(instance and getattr(instance, 'limitation_reason_generated', False))
    stashed = getattr(form, 'stashed_uploads', None) or {}
    if has_file and generated:
        attrs['data-limitation-generated'] = 'true'
    elif has_file or stashed.get('limitation_reason_file'):
        attrs['data-has-uploaded-file'] = 'true'
    field.widget.attrs.update(attrs)


def validate_limitation_reason_or_file(form, cleaned_data, *, required, required_message):
    text = (cleaned_data.get('limitation_reason') or '').strip()
    cleaned_data['limitation_reason'] = text
    file_value = cleaned_data.get('limitation_reason_file')

    if is_new_limitation_file(file_value):
        try:
            validate_upload(
                file_value,
                allowed_extensions=PDF_EXT,
                require_magic=True,
            )
        except forms.ValidationError as exc:
            form.add_error('limitation_reason_file', exc.messages[0])
            return
        has_file = True
    elif file_value is False:
        has_file = False
    else:
        instance = getattr(form, 'instance', None)
        existing = (
            getattr(instance, 'limitation_reason_file', None)
            if instance and getattr(instance, 'pk', None)
            else None
        )
        has_existing = bool(existing and getattr(existing, 'name', ''))
        generated = bool(getattr(instance, 'limitation_reason_generated', False)) if instance else False
        if has_existing and generated:
            has_file = bool(text)
        else:
            has_file = has_existing

    if required and not text and not has_file:
        form.add_error('limitation_reason', required_message)


def validate_recruitment_dynamic_rules(form, cleaned_data, *, is_creation, files=None):
    job = cleaned_data.get('job')
    if not job:
        form.add_error('job', 'Please select a job.')

    rules = get_effective_rules_for_job(job)
    until_rule = rules.get('valid_until')
    require_end = (
        not cleaned_data.get('is_permanent')
        and is_field_required(
            until_rule, None, 'valid_until', is_creation=is_creation,
        )
        and is_field_visible(until_rule, None, field_values=cleaned_data)
    )

    validate_contract_dates(
        form,
        cleaned_data,
        require_start=True,
        require_end=require_end,
    )

    months = contract_duration_months(
        cleaned_data.get('valid_from'),
        cleaned_data.get('valid_until'),
    )
    text_fields = [
        'first_name', 'last_name', 'country_of_origin', 'place_of_birth',
        'email_private', 'street', 'house_number', 'postal_code', 'city', 'country',
    ]
    for field_name in text_fields:
        if field_name not in form.fields:
            continue
        rule = rules.get(field_name)
        if not is_field_visible(rule, months, field_values=cleaned_data):
            continue
        if not is_field_required(rule, months, field_name, is_creation=is_creation):
            continue
        require_non_empty_text(form, cleaned_data, field_name)

    files = files or {}

    for field_key, label_en, _label_de in RECRUITMENT_CONFIGURABLE_FIELDS:
        rule = rules.get(field_key)
        visible = is_field_visible(rule, months, field_values=cleaned_data)
        required = is_field_required(rule, months, field_key, is_creation=is_creation)

        if not visible:
            continue

        if field_key == 'funding_allocations':
            continue

        if field_key == 'limitation_reason':
            validate_limitation_reason_or_file(
                form,
                cleaned_data,
                required=required and not cleaned_data.get('is_permanent'),
                required_message='Limitation reason text or PDF is required.',
            )
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
        if isinstance(value, str):
            value = value.strip()
            cleaned_data[field_key] = value
        if value in (None, ''):
            form.add_error(field_key, 'This field is required.')


def validate_funding_allocations_required(formset, job, cleaned_data, *, is_creation):
    months = contract_duration_months(
        cleaned_data.get('valid_from'),
        cleaned_data.get('valid_until'),
    )
    rules = get_effective_rules_for_job(job)
    rule = rules.get('funding_allocations')
    required = is_field_required(rule, months, 'funding_allocations', is_creation=is_creation)
    if not required:
        return

    active_forms = [
        item_form for item_form in formset.forms
        if item_form.cleaned_data
        and not item_form.cleaned_data.get('DELETE', False)
        and item_form.cleaned_data.get('funding_source')
    ]
    if not active_forms:
        raise forms.ValidationError('At least one funding allocation is required.')


def apply_single_row_workhours_default(formset):
    """One funding row: default percentage to 100. Several rows: require a value."""
    from decimal import Decimal

    active = [
        item_form for item_form in formset.forms
        if item_form.cleaned_data
        and not item_form.cleaned_data.get('DELETE', False)
        and item_form.cleaned_data.get('funding_source')
    ]
    if len(active) == 1:
        percentage = active[0].cleaned_data.get('workhours_percentage')
        if percentage in (None, ''):
            active[0].cleaned_data['workhours_percentage'] = Decimal('100')
            if hasattr(active[0], 'instance'):
                active[0].instance.workhours_percentage = Decimal('100')
        return
    if len(active) > 1:
        for item_form in active:
            percentage = item_form.cleaned_data.get('workhours_percentage')
            if percentage in (None, ''):
                item_form.add_error('workhours_percentage', 'Percentage of workhours is required.')


def parse_post_date(value):
    return parse_german_date(value)


def build_recruitment_template_context():
    from apps.finances.models import PayScale
    from apps.tasks.recruitment_config import (
        RECRUITMENT_CONFIGURABLE_FIELDS,
        serialize_all_job_rules,
        serialize_limitation_reasons,
    )

    field_keys = {field_key: True for field_key, _, _ in RECRUITMENT_CONFIGURABLE_FIELDS}
    job_payscale = {}
    current_payscales = PayScale.get_current()
    for job in visible_recruitment_jobs().select_related('salary_table').prefetch_related(
        'salary_table__instances__rows',
    ):
        inherited = inherited_job_payscale(job)
        salary = None
        if inherited['pay_scale_group'] and inherited['experience_level'] is not None:
            salary = (
                current_payscales.filter(
                    pay_scale_group=inherited['pay_scale_group'],
                    experience_level=inherited['experience_level'],
                )
                .values_list('monthly_salary', flat=True)
                .first()
            )
        if salary is None:
            salary = inherited['estimated_monthly_salary']
        job_payscale[str(job.pk)] = {
            'pay_scale_group': inherited['pay_scale_group'] or '',
            'experience_level': inherited['experience_level'],
            'estimated_salary': str(salary) if salary is not None else None,
            'has_fixed_estimate': inherited['has_fixed_estimate'],
            'salary_table_id': inherited.get('salary_table_id'),
            'occupation_weekly_hours': inherited.get('occupation_weekly_hours') or '',
            'help_text': inherited_job_text(job, 'help_text'),
            'dropdown_help_text': inherited_job_text(job, 'dropdown_help_text'),
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

    from apps.core.models import GlobalSetting
    from apps.core.occupation_salary import all_tables_payload

    # Python objects for template json_script (not pre-serialized strings).
    return {
        'recruitment_job_rules_json': serialize_all_job_rules(),
        'limitation_reasons_json': serialize_limitation_reasons(),
        'recruitment_field_keys_json': field_keys,
        'recruitment_job_payscale_json': job_payscale,
        'recruitment_payscale_data_json': payscale_data,
        'occupation_tables_json': all_tables_payload(),
        'true_cost_multiplicator': GlobalSetting.get_true_cost_multiplicator(),
        'default_weekly_hours': GlobalSetting.get_default_weekly_hours(),
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

    default_visibility = (
        VisibilityMode.ALWAYS if getattr(job, 'is_standard', False) else VisibilityMode.INHERIT
    )
    default_required = (
        RequiredMode.NEVER if getattr(job, 'is_standard', False) else RequiredMode.INHERIT
    )

    for field_key, _, _ in RECRUITMENT_CONFIGURABLE_FIELDS:
        visibility_mode = post_data.get(f'rule_{field_key}_visibility_mode', default_visibility)
        required_mode = post_data.get(f'rule_{field_key}_required_mode', default_required)
        if getattr(job, 'is_standard', False):
            if visibility_mode == VisibilityMode.INHERIT:
                visibility_mode = VisibilityMode.ALWAYS
            if required_mode == RequiredMode.INHERIT:
                required_mode = default_required

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
        rule.visibility_trigger_field = post_data.get(
            f'rule_{field_key}_visibility_trigger_field', '',
        ) or ''
        rule.required_mode = required_mode
        rule.required_duration_operator = post_data.get(
            f'rule_{field_key}_required_operator', '',
        ) or DurationOperator.LT
        rule.required_duration_months = required_months
        rule.help_text = (post_data.get(f'rule_{field_key}_help_text') or '').strip()
        rule.save()


def get_field_rule_context(job):
    from apps.tasks.recruitment_config import DurationOperator, RequiredMode, VisibilityMode

    existing = {rule.field_key: rule for rule in job.field_rules.all()} if job and job.pk else {}
    is_standard = bool(job and getattr(job, 'is_standard', False))
    default_visibility = VisibilityMode.ALWAYS if is_standard else VisibilityMode.INHERIT
    default_required = RequiredMode.NEVER if is_standard else RequiredMode.INHERIT
    rows = []
    for field_key, label_en, label_de in RECRUITMENT_CONFIGURABLE_FIELDS:
        rule = existing.get(field_key)
        rows.append({
            'field_key': field_key,
            'label_en': label_en,
            'label_de': label_de,
            'visibility_mode': getattr(rule, 'visibility_mode', default_visibility),
            'visibility_duration_operator': getattr(rule, 'visibility_duration_operator', DurationOperator.LT),
            'visibility_duration_months': getattr(rule, 'visibility_duration_months', ''),
            'visibility_trigger_field': getattr(rule, 'visibility_trigger_field', ''),
            'required_mode': getattr(rule, 'required_mode', default_required),
            'required_duration_operator': getattr(rule, 'required_duration_operator', DurationOperator.LT),
            'required_duration_months': getattr(rule, 'required_duration_months', ''),
            'help_text': getattr(rule, 'help_text', '') or '',
        })
    return rows