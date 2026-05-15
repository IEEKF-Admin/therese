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


ContractFormSet = inlineformset_factory(
    Employee, Contract, form=ContractForm, 
    extra=1, can_delete=True, min_num=1
)

FundingFormSet = inlineformset_factory(
    Employee, FundingAllocation, form=FundingAllocationForm, 
    extra=1, can_delete=True, min_num=1
)

SalaryFormSet = inlineformset_factory(
    Employee, SalarySupplement, fields='__all__', 
    extra=0, can_delete=True
)

WorkgroupFormSet = inlineformset_factory(
    Employee, Workgroup.members.through, 
    fields=('workgroup',), 
    extra=0, can_delete=True
)