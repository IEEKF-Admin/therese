"""
Inline formsets and helpers for the Employee create/edit form.

Contracts own Funding Allocations (nested formsets, one card per contract).
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db.models import F
from django.forms.models import BaseInlineFormSet, inlineformset_factory

from ..forms import ContractForm, FundingAllocationForm
from ..models import (
    Contract,
    Employee,
    FundingAllocation,
    SalarySupplement,
    Workgroup,
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

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        active = 0
        for form in self.forms:
            if not hasattr(form, 'cleaned_data') or not form.cleaned_data:
                continue
            if form.cleaned_data.get('DELETE'):
                continue
            if form.cleaned_data.get('is_active', True):
                active += 1
        if active > 1:
            raise ValidationError(
                'Only one active contract is allowed per employee. '
                'Please archive (deactivate) the others.'
            )


class ChronologicalContractFundingFormSet(BaseInlineFormSet):
    """Funding allocations for one contract, chronological."""

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.order_by(
            'start_date',
            F('end_date').asc(nulls_last=True),
            'pk',
        )


def make_contract_formset(extra=0):
    return inlineformset_factory(
        Employee,
        Contract,
        form=ContractForm,
        formset=ChronologicalContractFormSet,
        extra=extra,
        can_delete=True,
        min_num=0,
    )


def make_contract_funding_formset(extra=0):
    """Funding formset parented on Contract (not Employee)."""
    return inlineformset_factory(
        Contract,
        FundingAllocation,
        form=FundingAllocationForm,
        formset=ChronologicalContractFundingFormSet,
        fk_name='contract',
        extra=extra,
        can_delete=True,
        min_num=0,
    )


ContractFormSet = make_contract_formset(extra=0)
ContractFundingFormSet = make_contract_funding_formset(extra=0)

# Legacy name used in older imports — employee-level FA formset removed.
FundingFormSet = ContractFundingFormSet


def funding_prefix_for_existing(contract_pk: int) -> str:
    return f'fa_c{contract_pk}'


def funding_prefix_for_new(contract_form_index: int) -> str:
    return f'fa_n{contract_form_index}'


def build_contract_cards(
    employee,
    data=None,
    *,
    contract_extra=0,
    contract_initial=None,
    funding_initial_by_index=None,
):
    """
    Build contract formset + nested funding formsets for template/save.

    ``funding_initial_by_index``: optional dict form_index -> list of FA initial dicts
    (used when creating from recruitment on the first new contract).
    """
    funding_initial_by_index = funding_initial_by_index or {}
    ContractFS = make_contract_formset(extra=contract_extra)
    kwargs = {'instance': employee}
    if data is not None:
        contract_fs = ContractFS(data, **kwargs)
    else:
        if contract_initial:
            kwargs['initial'] = contract_initial
        contract_fs = ContractFS(**kwargs)

    cards = []
    for index, cform in enumerate(contract_fs.forms):
        contract = cform.instance
        is_existing = bool(getattr(contract, 'pk', None))
        if is_existing:
            prefix = funding_prefix_for_existing(contract.pk)
            FundingFSLocal = make_contract_funding_formset(extra=0)
            fa_fs = FundingFSLocal(data, instance=contract, prefix=prefix) if data is not None else FundingFSLocal(
                instance=contract, prefix=prefix
            )
        else:
            prefix = funding_prefix_for_new(index)
            initials = funding_initial_by_index.get(index) or []
            fa_extra = len(initials)
            FundingFSLocal = make_contract_funding_formset(extra=max(fa_extra, 0))
            shell = Contract(employee=employee) if employee is not None else Contract()
            if data is not None:
                fa_fs = FundingFSLocal(data, instance=shell, prefix=prefix)
            else:
                fa_fs = FundingFSLocal(
                    instance=shell,
                    prefix=prefix,
                    initial=initials or None,
                )

        cards.append({
            'index': index,
            'form': cform,
            'funding_formset': fa_fs,
            'prefix': prefix,
            'is_existing': is_existing,
            'is_active': bool(getattr(contract, 'is_active', True)) if is_existing else True,
            'contract_pk': contract.pk if is_existing else None,
        })

    # Empty templates for JS "Add contract" / "Add funding" (__prefix__)
    empty_contract_fs = make_contract_formset(extra=0)(instance=employee)
    empty_contract_form = empty_contract_fs.empty_form
    empty_fa_fs = make_contract_funding_formset(extra=0)(
        instance=Contract(employee=employee) if employee is not None else Contract(),
        prefix='fa_tpl',
    )
    empty_fa_form = empty_fa_fs.empty_form

    return {
        'contract_formset': contract_fs,
        'contract_cards': cards,
        'empty_contract_form': empty_contract_form,
        'empty_funding_form': empty_fa_form,
        'empty_funding_management': empty_fa_fs.management_form,
    }


def collect_funding_formsets_from_post(employee, contract_formset, data):
    """Build nested funding formsets for each contract form index from POST data."""
    formsets = []
    for index, cform in enumerate(contract_formset.forms):
        contract = cform.instance
        if getattr(contract, 'pk', None):
            prefix = funding_prefix_for_existing(contract.pk)
            parent = contract
        else:
            prefix = funding_prefix_for_new(index)
            parent = Contract(employee=employee)
        # Only bind if management form present for this prefix
        total_key = f'{prefix}-TOTAL_FORMS'
        if total_key not in data and f'{prefix}-TOTAL_FORMS' not in getattr(data, 'keys', lambda: [])():
            # QueryDict always has keys
            pass
        if data is not None and total_key not in data:
            # No FA block submitted for this card — treat as empty formset
            FS = make_contract_funding_formset(extra=0)
            formsets.append((index, cform, FS(instance=parent, prefix=prefix)))
            continue
        FS = make_contract_funding_formset(extra=0)
        formsets.append((index, cform, FS(data, instance=parent, prefix=prefix)))
    return formsets


def _q2(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def validate_active_contract_funding_totals(contract_formset, nested_funding) -> list[str]:
    """
    Active contract's non-deleted active FAs must sum to exactly 100%.

    ``nested_funding``: list of (index, contract_form, funding_formset)
    """
    errors = []
    for index, cform, fa_fs in nested_funding:
        if not hasattr(cform, 'cleaned_data') or not cform.cleaned_data:
            continue
        if cform.cleaned_data.get('DELETE'):
            continue
        if not cform.cleaned_data.get('is_active', True):
            continue
        if not fa_fs.is_valid():
            continue
        total = Decimal('0.00')
        active_fa_count = 0
        for fform in fa_fs.forms:
            if not hasattr(fform, 'cleaned_data') or not fform.cleaned_data:
                continue
            if fform.cleaned_data.get('DELETE'):
                continue
            if not fform.cleaned_data.get('is_active', True):
                continue
            pct = fform.cleaned_data.get('workhours_percentage')
            if pct is None:
                continue
            total += Decimal(pct)
            active_fa_count += 1
        total = _q2(total)
        if total != Decimal('100.00'):
            label = cform.cleaned_data.get('valid_from') or f'#{index + 1}'
            errors.append(
                f'Active funding allocations on the active contract ({label}) '
                f'must sum to exactly 100% (currently {total}%, '
                f'{active_fa_count} active allocation(s)).'
            )
    return errors


SalaryFormSet = inlineformset_factory(
    Employee,
    SalarySupplement,
    fields=['percentage', 'comment'],
    extra=0,
    can_delete=True,
)

WorkgroupFormSet = inlineformset_factory(
    Employee,
    Workgroup.members.through,
    fields=('workgroup',),
    extra=0,
    can_delete=True,
)
