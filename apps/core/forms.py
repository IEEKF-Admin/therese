from django import forms

from apps.core.models import GlobalSetting
from apps.holidays.public_holidays import FEDERAL_STATES


class GlobalSettingForm(forms.ModelForm):
    holiday_federal_state = forms.ChoiceField(
        required=False,
        choices=[('', 'Nationwide only')] + list(FEDERAL_STATES),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Federal state (public holidays)',
    )

    class Meta:
        model = GlobalSetting
        fields = [
            'default_weekly_hours',
            'true_cost_multiplicator',
            'personnel_import_tolerance',
            'chemical_hazard_threshold',
            'show_add_employee_on_reallocation',
            'irresponsible',
            'holidays_enabled',
            'holidays_planning_enabled',
            'holidays_approval_enabled',
            'holidays_gantt_enabled',
            'holiday_federal_state',
            'holiday_half_day_rounding',
            'holiday_advance_deadline',
            'holiday_email_recipients',
            'holiday_email_subject',
            'holiday_email_html',
        ]
        widgets = {
            'default_weekly_hours': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.01', 'min': '0'},
            ),
            'true_cost_multiplicator': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.001', 'min': '0'},
            ),
            'personnel_import_tolerance': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.0001', 'min': '0'},
            ),
            'chemical_hazard_threshold': forms.Select(attrs={'class': 'form-select'}),
            'holiday_half_day_rounding': forms.Select(attrs={'class': 'form-select'}),
            'holiday_advance_deadline': forms.DateInput(
                attrs={'class': 'form-control date-picker', 'placeholder': 'DD.MM.YYYY'},
            ),
            'holiday_email_recipients': forms.TextInput(attrs={'class': 'form-control'}),
            'holiday_email_subject': forms.TextInput(attrs={'class': 'form-control'}),
            'holiday_email_html': forms.Textarea(attrs={'class': 'form-control', 'rows': 6}),
        }
