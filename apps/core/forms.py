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
    'smtp': [
        'smtp_host',
        'smtp_port',
        'smtp_use_ssl',
        'smtp_use_tls',
        'smtp_user',
        'smtp_password',
        'smtp_from_email',
    ],
    'integrations': [
        'google_calendar_enabled',
        'google_calendar_id',
        'google_service_account_json',
        'sympa_enabled',
        'sympa_robot',
        'sympa_institute_list',
        'wordpress_positions',
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
            'google_calendar_enabled',
            'google_calendar_id',
            'google_service_account_json',
            'smtp_host',
            'smtp_port',
            'smtp_use_ssl',
            'smtp_use_tls',
            'smtp_user',
            'smtp_password',
            'smtp_from_email',
            'sympa_enabled',
            'sympa_robot',
            'sympa_institute_list',
            'wordpress_positions',
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
            'google_calendar_id': forms.TextInput(attrs={'class': 'form-control'}),
            'google_service_account_json': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 6,
                'autocomplete': 'off',
                'placeholder': 'Paste the JSON key. Leave blank to keep the saved key.',
            }),
            'smtp_host': forms.TextInput(attrs={'class': 'form-control'}),
            'smtp_port': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'step': '1'}),
            'smtp_user': forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'off'}),
            'smtp_password': forms.PasswordInput(attrs={
                'class': 'form-control',
                'autocomplete': 'new-password',
                'placeholder': 'Leave blank to keep the saved password.',
                'render_value': False,
            }, render_value=False),
            'smtp_from_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'sympa_robot': forms.EmailInput(attrs={'class': 'form-control'}),
            'sympa_institute_list': forms.EmailInput(attrs={'class': 'form-control'}),
            'wordpress_positions': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'One position per line',
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields.get('google_service_account_json')
        if field is not None:
            field.required = False
            self.initial['google_service_account_json'] = ''
        password = self.fields.get('smtp_password')
        if password is not None:
            password.required = False
            self.initial['smtp_password'] = ''

    def clean(self):
        from apps.core.mail import smtp_security

        cleaned = super().clean()
        if 'smtp_port' not in self.fields:
            return cleaned
        try:
            port = int(cleaned.get('smtp_port') or 0)
        except (TypeError, ValueError):
            port = 0
        use_ssl, use_tls = smtp_security(
            port, cleaned.get('smtp_use_ssl'), cleaned.get('smtp_use_tls'),
        )
        if port not in (25, 465, 587) and cleaned.get('smtp_use_ssl') and cleaned.get('smtp_use_tls'):
            raise forms.ValidationError(
                'SMTP SSL and STARTTLS cannot both be on. Use SSL for port 465 '
                'or STARTTLS for port 587.'
            )
        cleaned['smtp_use_ssl'] = use_ssl
        cleaned['smtp_use_tls'] = use_tls
        return cleaned

    def clean_smtp_password(self):
        value = self.cleaned_data.get('smtp_password')
        if value in (None, ''):
            return self.instance.smtp_password
        return value

    def clean_google_service_account_json(self):
        from apps.core.google_calendar import GoogleCalendarError, parse_service_account_json

        value = (self.cleaned_data.get('google_service_account_json') or '').strip()
        if not value:
            return self.instance.google_service_account_json
        try:
            data = parse_service_account_json(value)
        except GoogleCalendarError as exc:
            raise forms.ValidationError(str(exc)) from exc
        self.instance.google_service_account_email = (data.get('client_email') or '').strip()
        return value


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
