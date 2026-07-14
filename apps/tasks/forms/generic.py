"""General request (generic_text) task form."""
from django import forms

from apps.hr.models import Employee
from apps.tasks.form_validation import require_non_empty_text
from apps.tasks.models import GENERIC_STATUSES, GenericTextTask


# ---------------------------------------------------------------------------
# Generic text task (general requests)
# ---------------------------------------------------------------------------
class GenericTextTaskForm(forms.ModelForm):
    """
    Form for general text requests (generic_text tasks).

    Uses recipient instead of assignee. Creation forces status 'seen' and
    default priority; detail views expose status radio buttons.
    """
    class Meta:
        model = GenericTextTask
        fields = ['title', 'recipient', 'priority', 'due_date', 'status', 'comment']
        widgets = {
            'comment': forms.Textarea(attrs={
                'rows': 12,
                'placeholder': 'Describe your request in detail...',
                'style': 'min-height: 200px;'
            }),
            'due_date': forms.DateInput(attrs={
                'type': 'text',
                'class': 'form-control date-picker',
                'placeholder': 'TT.MM.JJJJ'
            }),
            'status': forms.RadioSelect(attrs={'class': 'status-radio'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.is_creation = kwargs.pop('is_creation', False)
        super().__init__(*args, **kwargs)

        # --- Status ---
        # Creation: hidden with initial 'seen'. Detail: radio buttons (GENERIC_STATUSES).
        if 'status' in self.fields:
            self.fields['status'].choices = GENERIC_STATUSES

            if self.is_creation:
                self.fields['status'].widget = forms.HiddenInput()
                self.fields['status'].initial = 'seen'
                self.fields['status'].required = True
                if self.data:
                    self.data = self.data.copy()
                    self.data['status'] = 'seen'

        # --- Visible fields (creation and detail) ---
        for field_name in ['title', 'priority', 'recipient']:
            if field_name in self.fields:
                self.fields[field_name].widget.attrs.update({'class': 'form-control'})

        if 'due_date' in self.fields:
            self.fields['due_date'].widget.attrs.update({'class': 'form-control'})

        if 'comment' in self.fields:
            self.fields['comment'].widget.attrs.update({'class': 'form-control'})

        if 'recipient' in self.fields:
            self.fields['recipient'].queryset = Employee.objects.order_by('last_name', 'first_name')
            self.fields['recipient'].empty_label = "— Please select a recipient —"
            self.fields['recipient'].required = True

            # Display name without internal employee number
            def recipient_label_from_instance(employee):
                prefix = f"{employee.prefix} " if employee.prefix else ""
                return f"{prefix}{employee.first_name} {employee.last_name}"

            self.fields['recipient'].label_from_instance = recipient_label_from_instance

        # --- Creation-only defaults ---
        if self.is_creation:
            if 'title' in self.fields:
                self.fields['title'].required = True
            if 'priority' in self.fields:
                self.fields['priority'].required = False
                self.fields['priority'].initial = 'medium'

    def clean(self):
        cleaned_data = super().clean()
        # Creation requires title, recipient, and non-empty comment; priority defaults to medium.
        if self.is_creation:
            if not cleaned_data.get('priority'):
                cleaned_data['priority'] = 'medium'
            require_non_empty_text(self, cleaned_data, 'title')
            require_non_empty_text(self, cleaned_data, 'recipient')
            comment = cleaned_data.get('comment')
            if isinstance(comment, str):
                comment = comment.strip()
                cleaned_data['comment'] = comment
            if not comment:
                self.add_error(
                    'comment',
                    'Please describe your request in the description field.',
                )
        return cleaned_data
