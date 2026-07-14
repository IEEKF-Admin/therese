"""Shared personnel form helpers (assignee visibility, gender field)."""
from django import forms

from apps.hr.models import Employee, Gender
from apps.tasks.utils import personnel_approver_employees
from apps.tasks.workflow_config import creator_has_coordinator_fallback

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
