"""
apps/hr/views/employee_form_helpers.py

Project: THERESE - Transparent HR Employee Resource Evaluation System Enhanced
Realized functionalities:
- All inline formsets for Employee form
- Helper functions for form handling
"""

from django.forms.models import inlineformset_factory
from ..models import (
    Employee, Contract, FundingAllocation,
    SalarySupplement, Workgroup
)
from ..forms import (
    ContractForm, FundingAllocationForm
)


def make_contract_formset(extra=0):
    """Build a Contract formset; extra>0 used when pre-filling from recruitment."""
    return inlineformset_factory(
        Employee, Contract, form=ContractForm,
        extra=extra, can_delete=True, min_num=0,
    )


def make_funding_formset(extra=0):
    """Build a Funding formset; extra>0 used when pre-filling from recruitment."""
    return inlineformset_factory(
        Employee, FundingAllocation, form=FundingAllocationForm,
        extra=extra, can_delete=True, min_num=0,
    )


# Default formsets: no empty rows on open (user clicks “Add another”).
ContractFormSet = make_contract_formset(extra=0)
FundingFormSet = make_funding_formset(extra=0)

SalaryFormSet = inlineformset_factory(
    Employee, SalarySupplement,
    fields=['percentage', 'comment'],
    extra=0, can_delete=True,
)

WorkgroupFormSet = inlineformset_factory(
    Employee, Workgroup.members.through,
    fields=('workgroup',),
    extra=0, can_delete=True
)
