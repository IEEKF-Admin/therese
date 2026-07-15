"""Shared PSP / cost center choices for funding allocation forms."""

from django import forms
from django.core.exceptions import ValidationError

from apps.finances.models import CostCenter, WBSElement

WBS_PREFIX = 'wbs'
CC_PREFIX = 'cc'


def build_funding_source_choices():
    choices = [('', '— Select PSP element or cost center —')]
    psp_options = [
        (f'{WBS_PREFIX}:{obj.pk}', str(obj))
        for obj in WBSElement.objects.active().order_by('wbs_code')
    ]
    cost_center_options = [
        (f'{CC_PREFIX}:{obj.pk}', str(obj))
        for obj in CostCenter.objects.order_by('cost_center')
    ]
    if psp_options:
        choices.append(('PSP Elements', psp_options))
    if cost_center_options:
        choices.append(('Cost Centers', cost_center_options))
    return choices


def funding_source_value_for_instance(instance):
    if getattr(instance, 'wbs_element_id', None):
        return f'{WBS_PREFIX}:{instance.wbs_element_id}'
    if getattr(instance, 'cost_center_id', None):
        return f'{CC_PREFIX}:{instance.cost_center_id}'
    return ''


def apply_funding_source(instance, value):
    kind, pk = value.split(':', 1)
    target_pk = int(pk)
    if kind == WBS_PREFIX:
        instance.wbs_element_id = target_pk
        instance.cost_center = None
    elif kind == CC_PREFIX:
        instance.cost_center_id = target_pk
        instance.wbs_element = None
    else:
        raise ValidationError('Invalid funding source.')


def validate_funding_source_value(value):
    if not value:
        raise ValidationError('PSP element or cost center is required.')
    try:
        kind, pk = value.split(':', 1)
        target_pk = int(pk)
    except (TypeError, ValueError, AttributeError):
        raise ValidationError('Invalid funding source.') from None
    if kind == WBS_PREFIX:
        if not WBSElement.objects.active().filter(pk=target_pk).exists():
            raise ValidationError('Invalid PSP element.')
    elif kind == CC_PREFIX:
        if not CostCenter.objects.filter(pk=target_pk).exists():
            raise ValidationError('Invalid cost center.')
    else:
        raise ValidationError('Invalid funding source.')
    return value


def funding_target_display(instance):
    if getattr(instance, 'wbs_element_id', None):
        return str(instance.wbs_element)
    if getattr(instance, 'cost_center_id', None):
        return f'Cost center {instance.cost_center}'
    return '—'


class FundingSourceField(forms.ChoiceField):
    def __init__(self, **kwargs):
        kwargs.setdefault('choices', build_funding_source_choices())
        kwargs.setdefault('label', 'PSP / Cost Center')
        super().__init__(**kwargs)

    def valid_value(self, value):
        if value in (None, ''):
            return True
        try:
            validate_funding_source_value(value)
        except ValidationError:
            return False
        return True


class FundingSourceFormMixin:
    """Replace wbs_element-only selection with PSP + cost center dropdown."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['funding_source'] = FundingSourceField()
        self.fields['funding_source'].choices = build_funding_source_choices()
        self.fields['funding_source'].widget.attrs.setdefault('class', 'form-control')
        initial_value = funding_source_value_for_instance(self.instance)
        if initial_value:
            self.initial.setdefault('funding_source', initial_value)

    def clean_funding_source(self):
        return validate_funding_source_value(self.cleaned_data.get('funding_source'))

    def save(self, commit=True):
        instance = super().save(commit=False)
        apply_funding_source(instance, self.cleaned_data['funding_source'])
        if commit:
            instance.save()
            self.save_m2m()
        return instance