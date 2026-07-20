"""
apps/hr/views/employee_form_helpers.py

Project: THERESE - Transparent HR Employee Resource Evaluation System Enhanced
Realized functionalities:
- All inline formsets for Employee form
- Helper functions for form handling
"""

from django.db.models import F
from django.forms.models import BaseInlineFormSet, inlineformset_factory
from ..models import (
    Employee, Contract, FundingAllocation,
    SalarySupplement, Workgroup
)
from ..forms import (
    ContractForm, FundingAllocationForm
)


class ChronologicalContractFormSet(BaseInlineFormSet):
    """Contracts ordered by start date, then end date (open ends last)."""

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.order_by(
            'valid_from',
            F('valid_until').asc(nulls_last=True),
            'pk',
        )


class ChronologicalFundingFormSet(BaseInlineFormSet):
    """Funding allocations ordered by start date, then end date (open ends last)."""

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.order_by(
            'start_date',
            F('end_date').asc(nulls_last=True),
            'pk',
        )


def make_contract_formset(extra=0):
    """Build a Contract formset; extra>0 used when pre-filling from recruitment."""
    return inlineformset_factory(
        Employee, Contract, form=ContractForm,
        formset=ChronologicalContractFormSet,
        extra=extra, can_delete=True, min_num=0,
    )


def make_funding_formset(extra=0):
    """Build a Funding formset; extra>0 used when pre-filling from recruitment."""
    return inlineformset_factory(
        Employee, FundingAllocation, form=FundingAllocationForm,
        formset=ChronologicalFundingFormSet,
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
