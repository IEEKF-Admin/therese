"""Personnel reallocation and contract extension task forms."""
from django import forms

from apps.finances.models import WBSElement
from apps.hr.models import Employee
from apps.tasks.form_validation import require_non_empty_text, validate_contract_dates
from apps.tasks.forms.common import _configure_personnel_assignee_field, add_initial_message_field
from apps.tasks.models import (
    PERSONNEL_STATUSES,
    PersonnelContractExtensionTask,
    PersonnelReallocationTask,
)
from apps.tasks.recruitment_form_helpers import (
    add_limitation_reason_template_field,
    strip_limitation_reason_template,
)


# ---------------------------------------------------------------------------
# Personnel reallocation task
# ---------------------------------------------------------------------------
class PersonnelReallocationTaskForm(forms.ModelForm):
    """
    Form for Personnel Reallocation tasks.
    No title (auto-generated), no assignee/priority/due_date at creation time.
    The entire "Assignment & Priority" card is omitted in the template.
    Comment/Notes gets full width.
    """
    class Meta:
        model = PersonnelReallocationTask
        fields = ['employee', 'target_wbs', 'valid_from', 'valid_until',
                  'plan_position_number', 'assignee', 'status']
        widgets = {
            'valid_from': forms.DateInput(attrs={
                'type': 'text',
                'class': 'form-control date-picker',
                'placeholder': 'TT.MM.JJJJ'
            }),
            'valid_until': forms.DateInput(attrs={
                'type': 'text',
                'class': 'form-control date-picker',
                'placeholder': 'TT.MM.JJJJ'
            }),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.is_creation = kwargs.pop('is_creation', False)
        super().__init__(*args, **kwargs)

        # --- Status ---
        # Hidden on creation with initial not_yet_processed; shown on detail per template.
        if 'status' in self.fields:
            self.fields['status'].choices = PERSONNEL_STATUSES
            if self.is_creation:
                self.fields['status'].widget = forms.HiddenInput()
                self.fields['status'].initial = 'not_yet_processed'
                self.fields['status'].required = True
                if self.data:
                    self.data = self.data.copy()
                    self.data['status'] = 'not_yet_processed'

        # --- Core reallocation fields ---
        for field_name in ['employee', 'target_wbs', 'plan_position_number']:
            if field_name in self.fields:
                self.fields[field_name].widget.attrs.update({'class': 'form-control'})
                self.fields[field_name].required = True

        for field_name in ['valid_from', 'valid_until']:
            if field_name in self.fields:
                self.fields[field_name].widget.attrs.update({'class': 'form-control'})
                if field_name == 'valid_from':
                    self.fields[field_name].required = True

        if self.is_creation:
            add_initial_message_field(
                self,
                rows=6,
                placeholder='Add any additional notes or context for this reallocation...',
            )

        # Employee dropdown (all employees)
        if 'employee' in self.fields:
            self.fields['employee'].queryset = Employee.objects.order_by('last_name', 'first_name')
            self.fields['employee'].empty_label = "— Select employee —"

        # Target WBS (reasonable WBS elements)
        if 'target_wbs' in self.fields:
            self.fields['target_wbs'].queryset = WBSElement.objects.active().order_by('wbs_code')
            self.fields['target_wbs'].empty_label = "— Select target WBS —"

        # --- Assignee (coordinator / creator-fallback only) ---
        _configure_personnel_assignee_field(self)

    def clean(self):
        cleaned_data = super().clean()
        strip_limitation_reason_template(cleaned_data)
        require_non_empty_text(self, cleaned_data, 'plan_position_number')
        validate_contract_dates(
            self,
            cleaned_data,
            require_start=True,
        )
        return cleaned_data


# ---------------------------------------------------------------------------
# Personnel contract extension task
# ---------------------------------------------------------------------------
class PersonnelContractExtensionTaskForm(forms.ModelForm):
    """
    Form for Personnel Contract Extension tasks.
    No title (auto-generated), no assignee/priority/due_date at creation time.
    The entire "Assignment & Priority" card is omitted in the template.
    Comment/Notes gets full width.
    """
    class Meta:
        model = PersonnelContractExtensionTask
        fields = ['employee', 'plan_position_number', 'valid_from', 'valid_until',
                  'is_limited', 'limitation_reason', 'assignee', 'status']
        widgets = {
            'valid_from': forms.DateInput(attrs={
                'type': 'text',
                'class': 'form-control date-picker',
                'placeholder': 'TT.MM.JJJJ'
            }),
            'valid_until': forms.DateInput(attrs={
                'type': 'text',
                'class': 'form-control date-picker',
                'placeholder': 'TT.MM.JJJJ'
            }),
            'limitation_reason': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.is_creation = kwargs.pop('is_creation', False)
        super().__init__(*args, **kwargs)

        # --- Status ---
        # Hidden on creation with initial not_yet_processed.
        if 'status' in self.fields:
            self.fields['status'].choices = PERSONNEL_STATUSES
            if self.is_creation:
                self.fields['status'].widget = forms.HiddenInput()
                self.fields['status'].initial = 'not_yet_processed'
                self.fields['status'].required = True
                if self.data:
                    self.data = self.data.copy()
                    self.data['status'] = 'not_yet_processed'

        # --- Employee and plan position ---
        for field_name in ['employee', 'plan_position_number']:
            if field_name in self.fields:
                self.fields[field_name].widget.attrs.update({'class': 'form-control'})
                self.fields[field_name].required = True

        if 'valid_from' in self.fields:
            self.fields['valid_from'].widget.attrs.update({'class': 'form-control'})

        if self.is_creation:
            add_initial_message_field(
                self,
                rows=6,
                placeholder='Add any additional notes or context for this contract extension...',
            )

        if 'limitation_reason' in self.fields:
            self.fields['limitation_reason'].widget.attrs.update({'class': 'form-control'})

        # Employee dropdown (all employees)
        if 'employee' in self.fields:
            self.fields['employee'].queryset = Employee.objects.order_by('last_name', 'first_name')
            self.fields['employee'].empty_label = "— Select employee —"

        # is_limited default True for new limited contracts
        if 'is_limited' in self.fields and self.is_creation:
            self.fields['is_limited'].initial = True
            self.fields['is_limited'].label = ""  # label rendered manually in template for nicer checkbox UX
        if 'status' in self.fields:
            self.fields['status'].choices = PERSONNEL_STATUSES
            if self.is_creation:
                self.fields['status'].widget = forms.HiddenInput()
                self.fields['status'].initial = 'not_yet_processed'
                self.fields['status'].required = True

        # Styling
        for fname in ['plan_position_number', 'priority', 'assignee', 'employee']:
            if fname in self.fields:
                self.fields[fname].widget.attrs.update({'class': 'form-control'})

        for fname in ['valid_from', 'due_date', 'limitation_reason']:
            if fname in self.fields:
                self.fields[fname].widget.attrs.update({'class': 'form-control'})

        if 'employee' in self.fields:
            self.fields['employee'].queryset = Employee.objects.order_by('last_name', 'first_name')

        # --- Assignee (coordinator / creator-fallback only) ---
        _configure_personnel_assignee_field(self)
        add_limitation_reason_template_field(self, include_all_reasons=True)

        if 'limitation_reason' in self.fields:
            self.fields['limitation_reason'].widget = forms.Textarea(attrs={
                'class': 'form-control limitation-reason-text',
                'rows': 3,
                'data-limitation-text': 'true',
            })

        if 'valid_from' in self.fields:
            self.fields['valid_from'].required = True

    def clean(self):
        cleaned_data = super().clean()
        strip_limitation_reason_template(cleaned_data)
        require_non_empty_text(self, cleaned_data, 'plan_position_number')
        validate_contract_dates(
            self,
            cleaned_data,
            require_start=True,
        )
        # Limited contracts require a free-text limitation reason.
        if cleaned_data.get('is_limited'):
            require_non_empty_text(
                self,
                cleaned_data,
                'limitation_reason',
                message='Limitation reason is required for limited contracts.',
            )
        return cleaned_data
