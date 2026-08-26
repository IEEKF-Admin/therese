from django import forms

from apps.core.models import GlobalSetting


class GlobalSettingForm(forms.ModelForm):
    class Meta:
        model = GlobalSetting
        fields = [
            'default_weekly_hours',
            'true_cost_multiplicator',
            'personnel_import_tolerance',
            'chemical_hazard_threshold',
            'show_add_employee_on_reallocation',
            'irresponsible',
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
        }
