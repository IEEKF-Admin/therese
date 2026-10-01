from datetime import date

from django import forms

from apps.core.dates import EuropeanDateField
from apps.core.html_sanitize import sanitize_html
from apps.courses.models import Course
from apps.documents.forms import DualListSelect
from apps.hr.models import Employee, Workgroup


class CourseForm(forms.ModelForm):
    workgroups = forms.ModelMultipleChoiceField(
        queryset=Workgroup.objects.order_by('short_name'),
        required=False,
        widget=DualListSelect(
            attrs={'class': 'form-select', 'size': 8},
            available_heading='Workgroups',
            selected_heading='Required workgroups',
        ),
    )
    extra_employees = forms.ModelMultipleChoiceField(
        queryset=Employee.objects.visible().order_by('last_name', 'first_name'),
        required=False,
        widget=DualListSelect(
            attrs={'class': 'form-select', 'size': 8},
            available_heading='Employees',
            selected_heading='Extra required',
        ),
    )

    class Meta:
        model = Course
        fields = [
            'name',
            'description',
            'interval_months',
            'evidence_type',
            'warn_weeks',
            'is_active',
            'all_institute',
            'workgroups',
            'extra_employees',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(
                attrs={'class': 'form-control wysiwyg-editor', 'rows': 8, 'data-wysiwyg-height': '280'},
            ),
            'interval_months': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'evidence_type': forms.Select(attrs={'class': 'form-select'}),
            'warn_weeks': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'}),
            'is_active': forms.CheckboxInput(),
            'all_institute': forms.CheckboxInput(),
        }

    def clean_description(self):
        return sanitize_html(self.cleaned_data.get('description'))

    def clean_interval_months(self):
        value = self.cleaned_data.get('interval_months')
        return value or None

    def clean_warn_weeks(self):
        value = self.cleaned_data.get('warn_weeks')
        return value or None


class CompletionForm(forms.Form):
    completed_on = EuropeanDateField(
        label='Completed on',
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )
    certificate = forms.FileField(required=False, label='Certificate (PDF)')
    employee_id = forms.IntegerField(required=False, widget=forms.HiddenInput)

    def clean_completed_on(self):
        value = self.cleaned_data.get('completed_on')
        if value and value > date.today():
            raise forms.ValidationError('Date cannot be in the future.')
        return value
