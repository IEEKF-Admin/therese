from datetime import date

from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from apps.finances.models import (
    CostCenter,
    CostCenterYearEstimate,
    WBSElement,
    WBSElementYearEstimate,
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
            'third_party_funding_commitment': 'Drittmittelzusage',
            'third_party_funder_identifier': 'Kennzeichen des Drittmittelgebers',
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
        # FileField model max_length=100 applies to the *storage path*. Client
        # filenames may be longer; DatabaseStorage renames them to a short UUID.
        # Allow realistic original names through form validation.
        if 'third_party_funding_commitment' in self.fields:
            self.fields['third_party_funding_commitment'].max_length = 255

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
            'funding',
            'consumables_estimate',
            'travel_estimate',
            'animal_costs_estimate',
        ]
        widgets = {
            'year': forms.NumberInput(attrs={
                'class': 'form-control form-control-sm',
                'min': 1900,
                'max': 2100,
                'placeholder': 'YYYY',
            }),
            'funding': forms.NumberInput(attrs={
                'class': 'form-control form-control-sm',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00',
            }),
            'consumables_estimate': forms.NumberInput(attrs={
                'class': 'form-control form-control-sm',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00',
            }),
            'travel_estimate': forms.NumberInput(attrs={
                'class': 'form-control form-control-sm',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00',
            }),
            'animal_costs_estimate': forms.NumberInput(attrs={
                'class': 'form-control form-control-sm',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00',
            }),
        }
        labels = {
            'year': 'Year / period',
            'funding': 'Funding',
            'consumables_estimate': 'Consumables estimate',
            'travel_estimate': 'Travel estimate',
            'animal_costs_estimate': 'Animal costs estimate',
        }
        help_texts = {
            'year': 'Calendar year for this estimate row.',
            'funding': 'Funding amount (EUR). Replaces former initial balance.',
            'consumables_estimate': 'Estimated consumables (EUR).',
            'travel_estimate': 'Estimated travel costs (EUR).',
            'animal_costs_estimate': 'Estimated animal costs (EUR).',
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('DELETE'):
            return cleaned
        year = cleaned.get('year')
        if year is None and not any(
            cleaned.get(f) for f in (
                'funding',
                'consumables_estimate',
                'travel_estimate',
                'animal_costs_estimate',
            )
        ):
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


class CostCenterForm(forms.ModelForm):
    class Meta:
        model = CostCenter
        fields = [
            'cost_center',
            'comments',
            'third_party_funding_commitment',
            'third_party_funder_identifier',
        ]
        widgets = {
            'cost_center': forms.TextInput(attrs={'class': 'form-control'}),
            'comments': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'third_party_funding_commitment': forms.ClearableFileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.jpg,.jpeg,.png,.gif,.webp',
            }),
            'third_party_funder_identifier': forms.TextInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'cost_center': 'Cost center',
            'comments': 'Comments',
            'third_party_funding_commitment': 'Drittmittelzusage',
            'third_party_funder_identifier': 'Kennzeichen des Drittmittelgebers',
        }
        help_texts = {
            'cost_center': 'Unique cost center identifier (e.g. 4711/2026).',
            'comments': 'Optional notes.',
            'third_party_funding_commitment': 'PDF or image file (optional).',
            'third_party_funder_identifier': 'Identifier of the third-party funder (optional).',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Same as WBSElementForm: client filename may exceed FileField path max_length.
        if 'third_party_funding_commitment' in self.fields:
            self.fields['third_party_funding_commitment'].max_length = 255


class CostCenterYearEstimateForm(forms.ModelForm):
    class Meta:
        model = CostCenterYearEstimate
        fields = [
            'year',
            'lomv',
            'consumables_estimate',
            'travel_estimate',
            'animal_costs_estimate',
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
            'consumables_estimate': forms.NumberInput(attrs={
                'class': 'form-control form-control-sm',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00',
            }),
            'travel_estimate': forms.NumberInput(attrs={
                'class': 'form-control form-control-sm',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00',
            }),
            'animal_costs_estimate': forms.NumberInput(attrs={
                'class': 'form-control form-control-sm',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00',
            }),
        }
        labels = {
            'year': 'Year / period',
            'lomv': 'Lomv',
            'consumables_estimate': 'Consumables estimate',
            'travel_estimate': 'Travel estimate',
            'animal_costs_estimate': 'Animal costs estimate',
        }
        help_texts = {
            'year': 'Calendar year for this estimate row.',
            'lomv': 'Lomv amount (EUR). Replaces former initial balance.',
            'consumables_estimate': 'Estimated consumables (EUR).',
            'travel_estimate': 'Estimated travel costs (EUR).',
            'animal_costs_estimate': 'Estimated animal costs (EUR).',
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('DELETE'):
            return cleaned
        year = cleaned.get('year')
        if year is None and not any(
            cleaned.get(f) for f in (
                'lomv',
                'consumables_estimate',
                'travel_estimate',
                'animal_costs_estimate',
            )
        ):
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