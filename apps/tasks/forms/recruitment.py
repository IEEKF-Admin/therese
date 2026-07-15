"""Recruitment task, funding formset, and catalog admin forms."""
from decimal import Decimal

from django import forms
from django.forms.models import BaseInlineFormSet, inlineformset_factory

from apps.finances.funding_sources import FundingSourceFormMixin
from apps.finances.models import PayScale
from apps.tasks.forms.common import (
    _configure_gender_field,
    _configure_personnel_assignee_field,
    add_initial_message_field,
)
from apps.tasks.models import (
    LimitationReason,
    PersonnelRecruitmentTask,
    RECRUITMENT_STATUSES,
    RECRUITMENT_STATUS_ORDER,
    RecruitmentFundingAllocation,
    RecruitmentJob,
)
from apps.tasks.recruitment_form_helpers import (
    add_limitation_reason_template_field,
    apply_recruitment_field_defaults,
    configure_recruitment_job_field,
    configure_recruitment_payscale_fields,
    strip_limitation_reason_template,
    validate_recruitment_dynamic_rules,
)
from apps.tasks.recruitment_upload_cache import apply_stashed_uploads
from apps.tasks.utils import (
    get_recruitment_status_choices,
    is_personnel_approver,
    is_personnel_coordinator,
)
from apps.tasks.workflow_config import creator_has_coordinator_fallback


# ---------------------------------------------------------------------------
# Recruitment funding allocations (inline formset)
# ---------------------------------------------------------------------------
class RecruitmentFundingAllocationForm(FundingSourceFormMixin, forms.ModelForm):
    """
    One WBS + weekly-hours row for recruitment funding.

    Blank rows are treated as empty via INTERNAL_FIELDS and _is_empty_row();
    empty cleaned rows are marked DELETE so they are not persisted.
    """
    INTERNAL_FIELDS = {'id', 'recruitment_task', 'DELETE'}

    class Meta:
        model = RecruitmentFundingAllocation
        fields = ['weekly_hours_allocated']
        widgets = {
            'weekly_hours_allocated': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.empty_permitted = True
        # INTERNAL_FIELDS must not block empty placeholder rows in the formset.
        for field_name, field in self.fields.items():
            if field_name in self.INTERNAL_FIELDS:
                field.required = False
            else:
                field.required = True

    def _is_empty_row(self, cleaned_data=None):
        """True when both WBS and weekly hours are unset on this inline row."""
        if cleaned_data is not None:
            if not cleaned_data:
                return True
            for field_name, value in cleaned_data.items():
                if field_name in self.INTERNAL_FIELDS:
                    continue
                if value not in (None, ''):
                    return False
            return True
        if not self.is_bound:
            return not (self.instance and self.instance.pk)
        source = self.data.get(self.add_prefix('funding_source'), '').strip()
        hours = self.data.get(self.add_prefix('weekly_hours_allocated'), '').strip()
        return not source and not hours

    def full_clean(self):
        # Blank extra rows skip validation (same pattern as PurchaseItemForm).
        if self._is_empty_row():
            self.cleaned_data = {}
            self._errors = {}
            return
        super().full_clean()

    def clean(self):
        cleaned_data = super().clean()
        # Empty row: mark DELETE so the formset does not save a stub allocation.
        if self._is_empty_row(cleaned_data):
            if cleaned_data is not None:
                cleaned_data['DELETE'] = True
            return cleaned_data
        if not cleaned_data.get('funding_source'):
            self.add_error('funding_source', 'PSP element or cost center is required.')
        hours = cleaned_data.get('weekly_hours_allocated')
        if hours in (None, ''):
            self.add_error('weekly_hours_allocated', 'Weekly working hours are required.')
        else:
            try:
                hours_value = Decimal(str(hours))
            except Exception:
                self.add_error('weekly_hours_allocated', 'Enter a valid number of hours.')
            else:
                if hours_value <= 0:
                    self.add_error('weekly_hours_allocated', 'Weekly hours must be greater than 0.')
                elif hours_value > Decimal('168'):
                    self.add_error('weekly_hours_allocated', 'Weekly hours cannot exceed 168.')
                else:
                    cleaned_data['weekly_hours_allocated'] = hours_value
        return cleaned_data


class BaseRecruitmentFundingFormSet(BaseInlineFormSet):
    """Validates that funding allocations cover the selected job and contract dates."""

    def __init__(self, *args, job=None, contract_dates=None, is_creation=True, **kwargs):
        self.job = job
        self.contract_dates = contract_dates or {}
        self.is_creation = is_creation
        super().__init__(*args, **kwargs)
        for form in self.forms:
            form.empty_permitted = True

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        # Delegate cross-row totals and job/contract coverage to shared helper.
        from apps.tasks.recruitment_form_helpers import validate_funding_allocations_required

        validate_funding_allocations_required(
            self,
            self.job,
            self.contract_dates,
            is_creation=self.is_creation,
        )


RecruitmentFundingFormSet = inlineformset_factory(
    PersonnelRecruitmentTask,
    RecruitmentFundingAllocation,
    form=RecruitmentFundingAllocationForm,
    formset=BaseRecruitmentFundingFormSet,
    extra=1,
    can_delete=True,
    min_num=0,
    validate_min=False,
)


# ---------------------------------------------------------------------------
# Personnel recruitment task
# ---------------------------------------------------------------------------
class PersonnelRecruitmentTaskForm(forms.ModelForm):
    """
    Full recruitment application form with uploads, job-driven fields,
    and role-based status transitions on detail views.
    """
    class Meta:
        model = PersonnelRecruitmentTask
        fields = [
            'prefix', 'first_name', 'last_name', 'gender', 'date_of_birth',
            'country_of_origin', 'place_of_birth', 'email_private',
            'private_phone_number', 'street', 'house_number', 'postal_code',
            'city', 'country', 'job', 'working_as', 'pay_scale_group',
            'experience_level', 'monthly_salary', 'plan_position_number',
            'valid_from', 'valid_until', 'limitation_reason',
            'cv_file', 'latest_degree_certificate_file',
            'assignee', 'status',
        ]
        widgets = {
            'valid_from': forms.DateInput(attrs={
                'type': 'text',
                'class': 'form-control date-picker',
                'placeholder': 'TT.MM.JJJJ',
                'data-contract-date': 'true',
            }),
            'valid_until': forms.DateInput(attrs={
                'type': 'text',
                'class': 'form-control date-picker',
                'placeholder': 'TT.MM.JJJJ',
                'data-contract-date': 'true',
            }),
            'date_of_birth': forms.DateInput(attrs={
                'type': 'text',
                'class': 'form-control date-picker',
                'placeholder': 'TT.MM.JJJJ',
            }),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.is_creation = kwargs.pop('is_creation', False)
        self.stashed_uploads = kwargs.pop('stashed_uploads', None) or {}
        super().__init__(*args, **kwargs)

        # Job field and defaults depend on creation vs detail and selected job.
        configure_recruitment_job_field(self)
        configure_recruitment_payscale_fields(self)
        apply_recruitment_field_defaults(self, is_creation=self.is_creation)

        for field_name, field in self.fields.items():
            if field_name not in ('status', 'gender', 'job', 'pay_scale_group', 'experience_level', 'monthly_salary'):
                field.widget.attrs.setdefault('class', 'form-control')
            if field_name not in ('status', 'assignee', 'job'):
                field.widget.attrs.setdefault('data-recruitment-field', field_name)

        _configure_gender_field(self, required=False)

        if self.is_creation:
            add_initial_message_field(self, rows=6)

        # --- Status ---
        # Creation: hidden, not_yet_processed. Detail: choices filtered by role;
        # read-only users get a hidden status field.
        if 'status' in self.fields:
            if self.is_creation:
                self.fields['status'].choices = RECRUITMENT_STATUSES
                self.fields['status'].widget = forms.HiddenInput()
                self.fields['status'].initial = 'not_yet_processed'
                self.fields['status'].required = True
                if self.data:
                    self.data = self.data.copy()
                    self.data['status'] = 'not_yet_processed'
            elif self.instance and self.instance.pk:
                allowed = get_recruitment_status_choices(self.user, self.instance)
                self.fields['status'].choices = allowed or RECRUITMENT_STATUSES
                can_change_status = (
                    self.user
                    and (
                        self.user.is_superuser
                        or is_personnel_coordinator(self.user)
                        or creator_has_coordinator_fallback(self.user, self.instance)
                        or (
                            is_personnel_approver(self.user)
                            and getattr(self.user, 'employee', None) == self.instance.assignee
                        )
                    )
                )
                if not can_change_status:
                    self.fields['status'].widget = forms.HiddenInput()

        for file_field in ('cv_file', 'latest_degree_certificate_file'):
            if file_field in self.fields:
                self.fields[file_field].widget.attrs['data-recruitment-field'] = file_field

        job_id = None
        if self.data.get('job'):
            job_id = self.data.get('job')
        elif self.instance and self.instance.job_id:
            job_id = self.instance.job_id
        add_limitation_reason_template_field(
            self,
            job_id=job_id if not self.is_creation else None,
            include_all_reasons=self.is_creation,
        )

        # --- Assignee (coordinator / creator-fallback only) ---
        _configure_personnel_assignee_field(self)

        if 'monthly_salary' in self.fields:
            self.fields['monthly_salary'].widget.attrs.update({
                'data-recruitment-monthly-salary': 'true',
                'step': '0.01',
                'min': '0',
            })

    def clean_experience_level(self):
        value = self.cleaned_data.get('experience_level')
        if value in (None, ''):
            return None
        return int(value)

    def clean_monthly_salary(self):
        value = self.cleaned_data.get('monthly_salary')
        if value in (None, ''):
            return None
        return value

    def clean(self):
        cleaned_data = super().clean()
        apply_stashed_uploads(cleaned_data, self.stashed_uploads)
        strip_limitation_reason_template(cleaned_data)
        pay_scale_group = cleaned_data.get('pay_scale_group')
        experience_level = cleaned_data.get('experience_level')
        has_group = bool(pay_scale_group)
        has_level = experience_level is not None
        if has_group != has_level:
            message = 'Please select both Entgeltstufe and Erfahrungsstufe, or leave both empty.'
            if not has_group:
                self.add_error('pay_scale_group', message)
            if not has_level:
                self.add_error('experience_level', message)
        elif has_group and has_level:
            salary = (
                PayScale.get_current()
                .filter(
                    pay_scale_group=pay_scale_group,
                    experience_level=experience_level,
                )
                .values_list('monthly_salary', flat=True)
                .first()
            )
            if salary is not None:
                cleaned_data['monthly_salary'] = salary
        elif not cleaned_data.get('monthly_salary'):
            cleaned_data['pay_scale_group'] = ''
            cleaned_data['experience_level'] = None
        # Job, contract dates, uploads, and funding rules validated dynamically.
        validate_recruitment_dynamic_rules(
            self,
            cleaned_data,
            is_creation=self.is_creation,
            files=getattr(self, 'files', None),
        )

        # Assigned approvers may only advance status forward, not revert.
        new_status = cleaned_data.get('status')
        if (
            new_status
            and self.instance
            and self.instance.pk
            and self.user
            and is_personnel_approver(self.user)
            and not is_personnel_coordinator(self.user)
            and getattr(self.user, 'employee', None) == self.instance.assignee
        ):
            try:
                current_index = RECRUITMENT_STATUS_ORDER.index(self.instance.status)
                new_index = RECRUITMENT_STATUS_ORDER.index(new_status)
            except ValueError:
                pass
            else:
                if new_index <= current_index:
                    self.add_error('status', 'Approvers may only move the status forward.')

        return cleaned_data


# ---------------------------------------------------------------------------
# Recruitment catalog (jobs and limitation reasons)
# ---------------------------------------------------------------------------
class RecruitmentJobForm(forms.ModelForm):
    """Admin form for recruitment job catalog entries (pay scale + experience level)."""

    class Meta:
        model = RecruitmentJob
        fields = ['name', 'pay_scale_group', 'experience_level', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'name': 'Job name',
            'pay_scale_group': 'Pay scale group',
            'experience_level': 'Experience level',
            'is_active': 'Active',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current = PayScale.get_current()
        groups = (
            current.values_list('pay_scale_group', flat=True)
            .distinct()
            .order_by('pay_scale_group')
        )
        pay_scale_choices = [('', '— Select pay scale group —')] + [(g, g) for g in groups]
        level_choices = [('', '— Select group first —')] + [(str(i), str(i)) for i in range(1, 7)]

        self.fields['pay_scale_group'] = forms.ChoiceField(
            choices=pay_scale_choices,
            required=False,
            widget=forms.Select(attrs={'class': 'form-control', 'id': 'job-pay-scale-group'}),
        )
        self.fields['experience_level'] = forms.ChoiceField(
            choices=level_choices,
            required=False,
            widget=forms.Select(attrs={'class': 'form-control', 'id': 'job-experience-level'}),
        )
        if self.instance and self.instance.pk:
            if self.instance.pay_scale_group:
                self.fields['pay_scale_group'].initial = self.instance.pay_scale_group
            if self.instance.experience_level is not None:
                self.fields['experience_level'].initial = str(self.instance.experience_level)

    def clean_experience_level(self):
        value = self.cleaned_data.get('experience_level')
        if value in (None, ''):
            return None
        return int(value)


class LimitationReasonForm(forms.ModelForm):
    """Template text for contract limitation reasons, optionally scoped to jobs."""

    class Meta:
        model = LimitationReason
        fields = ['title', 'text', 'applies_to_all_jobs', 'jobs', 'is_active']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'text': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'applies_to_all_jobs': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'jobs': forms.SelectMultiple(attrs={'class': 'form-control', 'size': 8}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'title': 'Title',
            'text': 'Limitation reason text',
            'applies_to_all_jobs': 'Applies to all jobs',
            'jobs': 'Associated jobs',
            'is_active': 'Active',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['jobs'].queryset = RecruitmentJob.objects.filter(is_active=True).order_by('name')
        self.fields['jobs'].required = False
