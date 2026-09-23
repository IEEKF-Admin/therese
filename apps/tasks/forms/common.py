"""Shared personnel form helpers (assignee visibility, gender field)."""
from django import forms


def add_initial_message_field(form, *, required=False, rows=4, placeholder='', label='Message'):
    """Optional or required initial chat message on task creation forms."""
    form.fields['initial_message'] = forms.CharField(
        required=required,
        label=label,
        widget=forms.Textarea(attrs={
            'rows': rows,
            'class': 'form-control full-width-textarea',
            'placeholder': placeholder,
        }),
    )

from apps.hr.models import Employee, Gender
from apps.hr.validity import contract_validity_defaults
from apps.tasks.utils import personnel_approver_employees
from apps.tasks.workflow_config import creator_has_coordinator_fallback


def _form_employee(form):
    instance = getattr(form, 'instance', None)
    if instance is not None and getattr(instance, 'employee_id', None):
        return instance.employee
    emp_id = None
    if form.is_bound:
        emp_id = form.data.get(form.add_prefix('employee'))
    else:
        emp_id = form.initial.get('employee')
    if emp_id in (None, ''):
        return None
    try:
        return Employee.objects.filter(pk=int(emp_id)).first()
    except (TypeError, ValueError):
        return None


def add_permanent_contract_field(form, *, enforce_max=False):
    """Form-only Permanent Contract checkbox; empty valid_until means open-ended."""
    form.fields['is_permanent'] = forms.BooleanField(
        required=False,
        label='Permanent Contract',
        widget=forms.CheckboxInput(attrs={'class': 'permanent-contract-flag'}),
    )
    if 'valid_until' in form.fields:
        form.fields['valid_until'].widget.attrs['data-permanent-until'] = 'true'
        if enforce_max:
            form.fields['valid_until'].widget.attrs['data-enforce-max'] = 'true'

    defaults = contract_validity_defaults(_form_employee(form))
    instance = getattr(form, 'instance', None)
    existing = bool(instance and getattr(instance, 'pk', None))

    if existing:
        form.fields['is_permanent'].initial = instance.valid_until is None
    elif not form.is_bound:
        form.fields['is_permanent'].initial = defaults['is_permanent']
        if defaults['valid_until'] and not form.initial.get('valid_until'):
            form.initial['valid_until'] = defaults['valid_until']

    if enforce_max and defaults.get('max_until') and 'valid_until' in form.fields:
        form.fields['valid_until'].widget.attrs['data-max-until'] = defaults['max_until_de']


def apply_permanent_contract_clean(
    form, cleaned_data, *, enforce_max=False, sync_limited=False,
):
    if cleaned_data.get('is_permanent'):
        cleaned_data['valid_until'] = None
        if sync_limited:
            cleaned_data['is_limited'] = False
        return cleaned_data
    if not enforce_max:
        return cleaned_data
    until = cleaned_data.get('valid_until')
    employee = cleaned_data.get('employee') or getattr(form.instance, 'employee', None)
    if employee is None or until is None:
        return cleaned_data
    max_until = contract_validity_defaults(employee).get('max_until')
    if max_until and until > max_until:
        form.add_error(
            'valid_until',
            'Valid until cannot be after the end of the contract.',
        )
    return cleaned_data

# ---------------------------------------------------------------------------
# Personnel form helpers (shared assignee / gender configuration)
# ---------------------------------------------------------------------------
def _configure_gender_field(form, required=True):
    """Match the Gender dropdown used on the Employee form."""
    form.fields['gender'] = forms.ChoiceField(
        label=Employee._meta.get_field('gender').verbose_name,
        choices=Gender.choices,
        required=required,
        widget=forms.Select(attrs={'class': 'form-control'}),
    )


def _user_can_set_personnel_assignee(form):
    """
    Personnel coordinators (and creator fallback on existing tasks) may set assignee.
    Approvers and plain creators cannot change assignee through the form.
    """
    if not form.user:
        return False
    if form.user.is_superuser or form.user.has_perm('tasks.view_all_personnel_tasks'):
        return True
    if form.instance and form.instance.pk:
        return creator_has_coordinator_fallback(form.user, form.instance)
    return False


def _configure_personnel_assignee_field(form):
    """
    Assignee visible only to personnel coordinators (and creator fallback).
    Dropdown candidates are personnel approvers; others get a hidden field.
    """
    if 'assignee' not in form.fields:
        return

    form.fields['assignee'].queryset = personnel_approver_employees()
    form.fields['assignee'].empty_label = "— Select assignee —"

    if _user_can_set_personnel_assignee(form):
        form.fields['assignee'].widget.attrs.update({'class': 'form-control'})
    else:
        form.fields['assignee'].widget = forms.HiddenInput()
        form.fields['assignee'].required = False
