from datetime import date

from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from apps.finances.models import (
    ContactPerson,
    CostCenter,
    CostCenterYearEstimate,
    WBSElement,
    WBSElementYearEstimate,
)
from apps.finances.psp_cost_types import (
    PSP_COST_TYPE_AMOUNT_FIELDS,
    PSP_COST_TYPE_FLAG_FIELDS,
    PSP_COST_TYPES,
    bilingual_cost_type_labels,
)


class MonthYearField(forms.Field):
    """Single month/year picker (no day); stored as the first day of the month."""

    widget = forms.DateInput(attrs={
        'type': 'month',
        'class': 'form-control',
    })

    def prepare_value(self, value):
        if isinstance(value, date):
            return value.strftime('%Y-%m')
        return value or ''

    def to_python(self, value):
        if value in (None, ''):
            return None
        if isinstance(value, date):
            return date(value.year, value.month, 1)
        try:
            year_str, month_str = str(value).split('-', 1)
            return date(int(year_str), int(month_str), 1)
        except (TypeError, ValueError, AttributeError):
            raise ValidationError('Enter a valid month and year.')


_AMOUNT_NUMBER_WIDGET = forms.NumberInput(attrs={
    'class': 'form-control form-control-sm',
    'step': '0.01',
    'min': '0',
    'placeholder': '0.00',
})


class WBSElementForm(forms.ModelForm):
    period_start = MonthYearField(
        required=False,
        label='Period start',
        help_text='Start month/year (no day).',
    )
    period_end = MonthYearField(
        required=False,
        label='Period end',
        help_text='End month/year (no day).',
    )

    class Meta:
        model = WBSElement
        fields = [
            'wbs_code',
            'title',
            'work_group',
            'responsible_person',
            'cost_center',
            'period_start',
            'period_end',
            'subject_to_annual_recurrence',
            'is_inactive',
            'comment',
            *PSP_COST_TYPE_FLAG_FIELDS,
            'third_party_funding_commitment',
            'third_party_funder_identifier',
        ]
        widgets = {
            'wbs_code': forms.TextInput(attrs={'class': 'form-control'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'work_group': forms.Select(attrs={'class': 'form-select'}),
            'responsible_person': forms.Select(attrs={'class': 'form-select'}),
            'cost_center': forms.Select(attrs={'class': 'form-select'}),
            'subject_to_annual_recurrence': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_inactive': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'comment': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'third_party_funding_commitment': forms.ClearableFileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.jpg,.jpeg,.png,.gif,.webp',
            }),
            'third_party_funder_identifier': forms.TextInput(attrs={'class': 'form-control'}),
            **{
                flag: forms.CheckboxInput(attrs={
                    'class': 'form-check-input cost-type-flag',
                    'data-cost-type': amount,
                })
                for flag, amount, *_rest in PSP_COST_TYPES
            },
        }
        labels = {
            'wbs_code': 'PSP code',
            'title': 'Title',
            'work_group': 'Work group',
            'responsible_person': 'Responsible person',
            'cost_center': 'Cost center',
            'subject_to_annual_recurrence': 'Subject to annual recurrence',
            'is_inactive': 'Inactive',
            'comment': 'Comment',
            'third_party_funding_commitment': 'Third-party funding commitment',
            'third_party_funder_identifier': 'Third-party funder identifier',
            **bilingual_cost_type_labels(),
        }
        help_texts = {
            'wbs_code': 'Unique PSP identifier.',
            'title': 'Short description of the PSP element.',
            'work_group': 'Assigned work group.',
            'responsible_person': 'Person responsible for this PSP element.',
            'cost_center': 'Exactly one cost center (required).',
            'subject_to_annual_recurrence': 'Whether this PSP element repeats annually.',
            'is_inactive': 'Inactive PSP elements are hidden from selection dropdowns.',
            'comment': 'Optional notes.',
            'third_party_funding_commitment': 'PDF or image file (optional).',
            'third_party_funder_identifier': 'Identifier of the third-party funder (optional).',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cost_center'].queryset = CostCenter.objects.all().order_by('cost_center')
        self.fields['cost_center'].required = True
        self.fields['cost_center'].empty_label = '— Select cost center —'
        # Manual create/edit requires a work group (orphan PSPs only via bulk import).
        self.fields['work_group'].required = True
        self.fields['work_group'].empty_label = '— Select work group —'
        # FileField model max_length applies to the *storage path*. Client
        # filenames may be longer; DatabaseStorage renames them to a short UUID.
        if 'third_party_funding_commitment' in self.fields:
            self.fields['third_party_funding_commitment'].max_length = 255
        for flag in PSP_COST_TYPE_FLAG_FIELDS:
            self.fields[flag].required = False

    def clean_cost_center(self):
        cost_center = self.cleaned_data.get('cost_center')
        if not cost_center:
            raise ValidationError('Cost center is required.')
        return cost_center

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('period_start')
        end = cleaned.get('period_end')
        if start and end and end < start:
            raise ValidationError('Period end must not be before period start.')
        return cleaned


class WBSElementYearEstimateForm(forms.ModelForm):
    class Meta:
        model = WBSElementYearEstimate
        fields = [
            'year',
            *PSP_COST_TYPE_AMOUNT_FIELDS,
        ]
        widgets = {
            'year': forms.NumberInput(attrs={
                'class': 'form-control form-control-sm',
                'min': 1900,
                'max': 2100,
                'placeholder': 'YYYY',
            }),
            **{amount: _AMOUNT_NUMBER_WIDGET for amount in PSP_COST_TYPE_AMOUNT_FIELDS},
        }
        labels = {
            'year': 'Year / period',
            **{
                amount: f'.{code} - {de}'
                for _flag, amount, code, de, _en in PSP_COST_TYPES
            },
        }
        help_texts = {
            'year': 'Calendar year for this estimate row.',
            **{
                amount: f'Estimated {en.lower()} (EUR).'
                for _flag, amount, _code, _de, en in PSP_COST_TYPES
            },
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('DELETE'):
            return cleaned
        year = cleaned.get('year')
        if year is None and not any(cleaned.get(f) for f in PSP_COST_TYPE_AMOUNT_FIELDS):
            cleaned['DELETE'] = True
        return cleaned


class BaseWBSElementYearEstimateFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        years_seen = set()
        for form in self.forms:
            if not hasattr(form, 'cleaned_data') or not form.cleaned_data:
                continue
            if form.cleaned_data.get('DELETE'):
                continue
            year = form.cleaned_data.get('year')
            if year is None:
                continue
            if year in years_seen:
                raise ValidationError(
                    f'Year {year} appears more than once. Each year may only be entered once per PSP element.'
                )
            years_seen.add(year)


WBSElementYearEstimateFormSet = inlineformset_factory(
    WBSElement,
    WBSElementYearEstimate,
    form=WBSElementYearEstimateForm,
    formset=BaseWBSElementYearEstimateFormSet,
    extra=1,
    can_delete=True,
)


class ContactPersonForm(forms.ModelForm):
    class Meta:
        model = ContactPerson
        fields = [
            'last_name',
            'first_name',
            'business_area',
            'phone',
            'email',
            'comments',
        ]
        widgets = {
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'business_area': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'comments': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'maxlength': 400,
            }),
        }
        labels = {
            'last_name': 'Last name',
            'first_name': 'First name',
            'business_area': 'Business area',
            'phone': 'Phone',
            'email': 'Email',
            'comments': 'Comments',
        }
        help_texts = {
            'last_name': 'Required. Together with first name this identifies the contact.',
            'first_name': 'Optional given name.',
            'business_area': 'Organizational unit or business area (optional).',
            'phone': 'Phone number (optional).',
            'email': 'Email address (optional).',
            'comments': 'Optional notes (max. 400 characters).',
        }

    def clean_last_name(self):
        value = (self.cleaned_data.get('last_name') or '').strip()
        if not value:
            raise ValidationError('Last name is required.')
        return value

    def clean_first_name(self):
        return (self.cleaned_data.get('first_name') or '').strip()

    def clean_comments(self):
        return (self.cleaned_data.get('comments') or '').strip()

    def clean(self):
        cleaned = super().clean()
        last_name = cleaned.get('last_name') or ''
        first_name = cleaned.get('first_name') or ''
        qs = ContactPerson.objects.filter(
            last_name__iexact=last_name,
            first_name__iexact=first_name,
        )
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(
                'A contact person with this last name and first name already exists.'
            )
        return cleaned


class CostCenterForm(forms.ModelForm):
    class Meta:
        model = CostCenter
        fields = [
            'cost_center',
            'comments',
            *PSP_COST_TYPE_FLAG_FIELDS,
        ]
        widgets = {
            'cost_center': forms.TextInput(attrs={'class': 'form-control'}),
            'comments': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            **{
                flag: forms.CheckboxInput(attrs={
                    'class': 'form-check-input cost-type-flag',
                    'data-cost-type': amount,
                })
                for flag, amount, *_rest in PSP_COST_TYPES
            },
        }
        labels = {
            'cost_center': 'Cost center',
            'comments': 'Comments',
            # Cost centers: no leading .1 / .2 numbers on checkbox labels.
            **bilingual_cost_type_labels(include_code=False),
        }
        help_texts = {
            'cost_center': 'Unique cost center identifier (e.g. 4711/2026).',
            'comments': 'Optional notes.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for flag in PSP_COST_TYPE_FLAG_FIELDS:
            self.fields[flag].required = False


class CostCenterYearEstimateForm(forms.ModelForm):
    class Meta:
        model = CostCenterYearEstimate
        fields = [
            'year',
            'lomv',
            *PSP_COST_TYPE_AMOUNT_FIELDS,
        ]
        widgets = {
            'year': forms.NumberInput(attrs={
                'class': 'form-control form-control-sm',
                'min': 1900,
                'max': 2100,
                'placeholder': 'YYYY',
            }),
            'lomv': forms.NumberInput(attrs={
                'class': 'form-control form-control-sm',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00',
            }),
            **{amount: _AMOUNT_NUMBER_WIDGET for amount in PSP_COST_TYPE_AMOUNT_FIELDS},
        }
        labels = {
            'year': 'Year / period',
            'lomv': 'Lomv',
            **{
                amount: de
                for _flag, amount, _code, de, _en in PSP_COST_TYPES
            },
        }
        help_texts = {
            'year': 'Calendar year for this estimate row.',
            'lomv': 'Lomv amount (EUR). Always available (not tied to cost-type checkboxes).',
            **{
                amount: f'Estimated {en.lower()} (EUR).'
                for _flag, amount, _code, _de, en in PSP_COST_TYPES
            },
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('DELETE'):
            return cleaned
        year = cleaned.get('year')
        amount_keys = ('lomv',) + PSP_COST_TYPE_AMOUNT_FIELDS
        if year is None and not any(cleaned.get(f) for f in amount_keys):
            cleaned['DELETE'] = True
        return cleaned


class BaseCostCenterYearEstimateFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        years_seen = set()
        for form in self.forms:
            if not hasattr(form, 'cleaned_data') or not form.cleaned_data:
                continue
            if form.cleaned_data.get('DELETE'):
                continue
            year = form.cleaned_data.get('year')
            if year is None:
                continue
            if year in years_seen:
                raise ValidationError(
                    f'Year {year} appears more than once. Each year may only be entered once per cost center.'
                )
            years_seen.add(year)


CostCenterYearEstimateFormSet = inlineformset_factory(
    CostCenter,
    CostCenterYearEstimate,
    form=CostCenterYearEstimateForm,
    formset=BaseCostCenterYearEstimateFormSet,
    extra=1,
    can_delete=True,
)
