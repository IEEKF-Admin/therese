"""Personnel reallocation and contract extension task forms."""
from decimal import Decimal

from django import forms
from django.forms.models import BaseInlineFormSet, inlineformset_factory

from apps.finances.funding_sources import FundingSourceFormMixin
from apps.hr.models import Employee
from apps.tasks.form_validation import require_non_empty_text, validate_contract_dates
from apps.tasks.forms.common import _configure_personnel_assignee_field, add_initial_message_field
from apps.tasks.models import (
    PERSONNEL_STATUSES,
    PersonnelContractExtensionTask,
    PersonnelReallocationTask,
    ReallocationFundingAllocation,
)
from apps.tasks.recruitment_form_helpers import (
    add_limitation_reason_template_field,
    strip_limitation_reason_template,
)


# ---------------------------------------------------------------------------
# Reallocation funding allocations (inline formset)
# ---------------------------------------------------------------------------
class ReallocationFundingAllocationForm(FundingSourceFormMixin, forms.ModelForm):
    """One PSP/cost-center + percentage row for reallocation funding."""

    INTERNAL_FIELDS = {'id', 'reallocation_task', 'DELETE'}

    class Meta:
        model = ReallocationFundingAllocation
        fields = ['workhours_percentage', 'plan_position_number', 'notes']
        widgets = {
            'workhours_percentage': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
            }),
            'plan_position_number': forms.TextInput(attrs={'class': 'form-control'}),
            'notes': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.empty_permitted = True
        if 'workhours_percentage' in self.fields:
            self.fields['workhours_percentage'].label = 'Percentage of Workhours'
        if 'plan_position_number' in self.fields:
            self.fields['plan_position_number'].label = 'Plan Position Number'
            self.fields['plan_position_number'].required = False
        if 'notes' in self.fields:
            self.fields['notes'].required = False
        for field_name, field in self.fields.items():
            if field_name in self.INTERNAL_FIELDS or field_name in (
                'plan_position_number',
                'notes',
            ):
                field.required = False
            else:
                field.required = True

    def _is_empty_row(self, cleaned_data=None):
        if cleaned_data is not None:
            if not cleaned_data:
                return True
            for field_name, value in cleaned_data.items():
                if field_name in self.INTERNAL_FIELDS or field_name in (
                    'plan_position_number',
                    'notes',
                ):
                    continue
                if value not in (None, ''):
                    return False
            return True
        if not self.is_bound:
            return not (self.instance and self.instance.pk)
        source = self.data.get(self.add_prefix('funding_source'), '').strip()
        percentage = self.data.get(self.add_prefix('workhours_percentage'), '').strip()
        return not source and not percentage

    def full_clean(self):
        if self._is_empty_row():
            self.cleaned_data = {}
            self._errors = {}
            return
        super().full_clean()

    def clean(self):
        cleaned_data = super().clean()
        if self._is_empty_row(cleaned_data):
            if cleaned_data is not None:
                cleaned_data['DELETE'] = True
            return cleaned_data
        if not cleaned_data.get('funding_source'):
            self.add_error('funding_source', 'PSP element or cost center is required.')
        percentage = cleaned_data.get('workhours_percentage')
        if percentage in (None, ''):
            self.add_error('workhours_percentage', 'Percentage of workhours is required.')
        else:
            try:
                percentage_value = Decimal(str(percentage))
            except Exception:
                self.add_error('workhours_percentage', 'Enter a valid percentage.')
            else:
                if percentage_value <= 0:
                    self.add_error('workhours_percentage', 'Percentage must be greater than 0.')
                else:
                    cleaned_data['workhours_percentage'] = percentage_value
        return cleaned_data


class BaseReallocationFundingFormSet(BaseInlineFormSet):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for form in self.forms:
            form.empty_permitted = True

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        active = [
            form for form in self.forms
            if form.cleaned_data
            and not form.cleaned_data.get('DELETE', False)
            and form.cleaned_data.get('funding_source')
        ]
        if not active:
            raise forms.ValidationError('At least one funding allocation is required.')


ReallocationFundingFormSet = inlineformset_factory(
    PersonnelReallocationTask,
    ReallocationFundingAllocation,
    form=ReallocationFundingAllocationForm,
    formset=BaseReallocationFundingFormSet,
    extra=1,
    can_delete=True,
    min_num=0,
    validate_min=False,
)


# ---------------------------------------------------------------------------
# Personnel reallocation task
# ---------------------------------------------------------------------------
class PersonnelReallocationTaskForm(forms.ModelForm):
    """
    Form for Personnel Reallocation tasks.
    Funding targets live on ReallocationFundingAllocation (inline formset).
    """

    class Meta:
        model = PersonnelReallocationTask
        fields = ['employee', 'valid_from', 'valid_until', 'assignee', 'status']
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

        if 'status' in self.fields:
            self.fields['status'].choices = PERSONNEL_STATUSES
            if self.is_creation:
                self.fields['status'].widget = forms.HiddenInput()
                self.fields['status'].initial = 'not_yet_processed'
                self.fields['status'].required = True
                if self.data:
                    self.data = self.data.copy()
                    self.data['status'] = 'not_yet_processed'

        if 'employee' in self.fields:
            self.fields['employee'].widget.attrs.update({'class': 'form-control'})
            self.fields['employee'].required = True
            self.fields['employee'].queryset = Employee.objects.order_by('last_name', 'first_name')
            self.fields['employee'].empty_label = "— Select employee —"

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

        _configure_personnel_assignee_field(self)

    def clean(self):
        cleaned_data = super().clean()
        strip_limitation_reason_template(cleaned_data)
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

        if 'status' in self.fields:
            self.fields['status'].choices = PERSONNEL_STATUSES
            if self.is_creation:
                self.fields['status'].widget = forms.HiddenInput()
                self.fields['status'].initial = 'not_yet_processed'
                self.fields['status'].required = True
                if self.data:
                    self.data = self.data.copy()
                    self.data['status'] = 'not_yet_processed'

        for field_name in ['employee', 'plan_position_number']:
            if field_name in self.fields:
                self.fields[field_name].widget.attrs.update({'class': 'form-control'})
                self.fields[field_name].required = True

        if 'valid_from' in self.fields:
            self.fields['valid_from'].widget.attrs.update({'class': 'form-control'})
            self.fields['valid_from'].required = True

        if self.is_creation:
            add_initial_message_field(
                self,
                rows=6,
                placeholder='Add any additional notes or context for this contract extension...',
            )

        if 'limitation_reason' in self.fields:
            self.fields['limitation_reason'].widget.attrs.update({'class': 'form-control'})

        if 'employee' in self.fields:
            self.fields['employee'].queryset = Employee.objects.order_by('last_name', 'first_name')
            self.fields['employee'].empty_label = "— Select employee —"

        if 'is_limited' in self.fields and self.is_creation:
            self.fields['is_limited'].initial = True
            self.fields['is_limited'].label = ""

        for fname in ['plan_position_number', 'priority', 'assignee', 'employee']:
            if fname in self.fields:
                self.fields[fname].widget.attrs.update({'class': 'form-control'})

        for fname in ['valid_from', 'due_date', 'limitation_reason']:
            if fname in self.fields:
                self.fields[fname].widget.attrs.update({'class': 'form-control'})

        _configure_personnel_assignee_field(self)
        add_limitation_reason_template_field(self, include_all_reasons=True)

        if 'limitation_reason' in self.fields:
            self.fields['limitation_reason'].widget = forms.Textarea(attrs={
                'class': 'form-control limitation-reason-text',
                'rows': 3,
                'data-limitation-text': 'true',
            })

    def clean(self):
        cleaned_data = super().clean()
        strip_limitation_reason_template(cleaned_data)
        require_non_empty_text(self, cleaned_data, 'plan_position_number')
        validate_contract_dates(
            self,
            cleaned_data,
            require_start=True,
        )
        if cleaned_data.get('is_limited'):
            require_non_empty_text(
                self,
                cleaned_data,
                'limitation_reason',
                message='Limitation reason is required for limited contracts.',
            )
        return cleaned_data
