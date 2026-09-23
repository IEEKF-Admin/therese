from django import forms

from apps.core.models import GlobalSetting
from apps.holidays.public_holidays import FEDERAL_STATES
from apps.tasks.form_validation import DecimalCommaField


SETTINGS_TAB_FIELDS = {
    'general': [
        'default_weekly_hours',
        'show_add_employee_on_reallocation',
        'irresponsible',
    ],
    'personnel': [
        'true_cost_multiplicator',
        'personnel_import_tolerance',
        'employee_expiring_soon_days',
        'limitation_pdf_letterhead',
    ],
    'chemicals': [
        'chemicals_enabled',
        'chemical_hazard_threshold',
    ],
    'inventory': [
        'inventory_enabled',
    ],
    'holidays': [
        'holidays_enabled',
        'holidays_planning_enabled',
        'holidays_approval_enabled',
        'holidays_gantt_enabled',
        'holiday_federal_state',
        'holiday_half_day_rounding',
        'holiday_advance_deadline',
        'holiday_email_recipients',
        'holiday_request_email_subject',
        'holiday_request_email_html',
        'holiday_cancel_email_subject',
        'holiday_cancel_email_html',
    ],
}

SETTINGS_TAB_ACTIONS = {f'save_{tab}': tab for tab in SETTINGS_TAB_FIELDS}


class GlobalSettingForm(forms.ModelForm):
    default_weekly_hours = DecimalCommaField(
        max_digits=5,
        decimal_places=2,
        min_value=0,
        label='Default Weekly Working Hours',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
    )
    true_cost_multiplicator = DecimalCommaField(
        max_digits=5,
        decimal_places=3,
        min_value=0,
        label='True-Cost Multiplicator',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001', 'min': '0'}),
    )
    personnel_import_tolerance = DecimalCommaField(
        max_digits=5,
        decimal_places=4,
        min_value=0,
        label='Personnel import amount tolerance',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.0001', 'min': '0'}),
    )
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
            'chemicals_enabled',
            'chemical_hazard_threshold',
            'inventory_enabled',
            'show_add_employee_on_reallocation',
            'employee_expiring_soon_days',
            'limitation_pdf_letterhead',
            'irresponsible',
            'holidays_enabled',
            'holidays_planning_enabled',
            'holidays_approval_enabled',
            'holidays_gantt_enabled',
            'holiday_federal_state',
            'holiday_half_day_rounding',
            'holiday_advance_deadline',
            'holiday_email_recipients',
            'holiday_request_email_subject',
            'holiday_request_email_html',
            'holiday_cancel_email_subject',
            'holiday_cancel_email_html',
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
            'employee_expiring_soon_days': forms.NumberInput(
                attrs={'class': 'form-control', 'min': '1', 'step': '1'},
            ),
            'chemical_hazard_threshold': forms.Select(attrs={'class': 'form-select'}),
            'holiday_half_day_rounding': forms.Select(attrs={'class': 'form-select'}),
            'holiday_advance_deadline': forms.DateInput(
                attrs={'class': 'form-control date-picker', 'placeholder': 'DD.MM.YYYY'},
            ),
            'holiday_email_recipients': forms.TextInput(attrs={'class': 'form-control'}),
            'holiday_request_email_subject': forms.TextInput(attrs={'class': 'form-control'}),
            'holiday_request_email_html': forms.Textarea(attrs={
                'class': 'form-control wysiwyg-editor',
                'rows': 8,
                'data-wysiwyg-height': '220',
            }),
            'holiday_cancel_email_subject': forms.TextInput(attrs={'class': 'form-control'}),
            'holiday_cancel_email_html': forms.Textarea(attrs={
                'class': 'form-control wysiwyg-editor',
                'rows': 8,
                'data-wysiwyg-height': '220',
            }),
            'limitation_pdf_letterhead': forms.Textarea(attrs={
                'class': 'form-control wysiwyg-editor',
                'rows': 8,
                'data-wysiwyg-height': '240',
            }),
        }

    def clean_limitation_pdf_letterhead(self):
        from apps.core.html_sanitize import sanitize_html

        return sanitize_html(self.cleaned_data.get('limitation_pdf_letterhead'))

    def clean_holiday_request_email_html(self):
        from apps.core.html_sanitize import sanitize_html

        return sanitize_html(self.cleaned_data.get('holiday_request_email_html'))

    def clean_holiday_cancel_email_html(self):
        from apps.core.html_sanitize import sanitize_html

        return sanitize_html(self.cleaned_data.get('holiday_cancel_email_html'))


def global_setting_form_class(tab):
    tab_fields = list(SETTINGS_TAB_FIELDS[tab])

    class TabForm(GlobalSettingForm):
        class Meta(GlobalSettingForm.Meta):
            fields = tab_fields

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            allowed = set(tab_fields)
            for name in list(self.fields):
                if name not in allowed:
                    self.fields.pop(name)

    TabForm.__name__ = f'GlobalSetting{tab.title()}Form'
    return TabForm
