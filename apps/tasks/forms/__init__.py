"""
apps/tasks/forms/

Django ModelForms and inline formsets for task creation and editing.

Submodules:
- purchase: Purchase order header and line-item formset
- personnel: Reallocation and contract extension forms
- recruitment: Recruitment task, funding formset, job/limitation catalog
- generic: General text requests
- standard: Standard purchase catalog items
- common: Shared personnel helpers (assignee, gender)

Public imports are re-exported here so existing code can use
``from apps.tasks.forms import PurchaseOrderTaskForm`` unchanged.

Do not remove any existing requirements from this package without explicit instruction.
"""
from apps.tasks.forms.common import (
    _configure_gender_field,
    _configure_personnel_assignee_field,
    _user_can_set_personnel_assignee,
)
from apps.tasks.forms.generic import GenericTextTaskForm
from apps.tasks.forms.personnel import (
    PersonnelContractExtensionTaskForm,
    PersonnelReallocationTaskForm,
)
from apps.tasks.forms.purchase import (
    BasePurchaseItemFormSet,
    PurchaseItemForm,
    PurchaseItemFormSet,
    PurchaseOrderQuoteReplaceForm,
    PurchaseOrderTaskForm,
)
from apps.tasks.forms.recruitment import (
    BaseRecruitmentFundingFormSet,
    LimitationReasonForm,
    PersonnelRecruitmentTaskForm,
    RecruitmentFundingAllocationForm,
    RecruitmentFundingFormSet,
    RecruitmentJobForm,
)
from apps.tasks.forms.standard import (
    MAX_STANDARD_IMAGE_SIZE_MB,
    THUMBNAIL_SIZE,
    StandardPurchaseItemForm,
)

__all__ = [
    'PurchaseOrderTaskForm',
    'PurchaseOrderQuoteReplaceForm',
    'PurchaseItemForm',
    'BasePurchaseItemFormSet',
    'PurchaseItemFormSet',
    'PersonnelReallocationTaskForm',
    'PersonnelContractExtensionTaskForm',
    'RecruitmentFundingAllocationForm',
    'BaseRecruitmentFundingFormSet',
    'RecruitmentFundingFormSet',
    'PersonnelRecruitmentTaskForm',
    'RecruitmentJobForm',
    'LimitationReasonForm',
    'GenericTextTaskForm',
    'StandardPurchaseItemForm',
    'MAX_STANDARD_IMAGE_SIZE_MB',
    'THUMBNAIL_SIZE',
    '_configure_gender_field',
    '_user_can_set_personnel_assignee',
    '_configure_personnel_assignee_field',
]
