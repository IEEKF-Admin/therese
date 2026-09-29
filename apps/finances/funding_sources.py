"""Shared PSP / cost center choices for funding allocation forms."""

from django import forms
from django.core.exceptions import ValidationError

from apps.finances.models import CostCenter, WBSElement

WBS_PREFIX = 'wbs'
CC_PREFIX = 'cc'


def build_funding_source_choices():
    from apps.hr.extern import EXTERN_WORKGROUP_SHORT_NAME, workgroup_is_extern

    choices = [('', '— Select PSP element or cost center —')]
    intern_psp = []
    extern_psp = []
    for obj in WBSElement.objects.active().select_related('work_group').order_by('wbs_code'):
        option = (f'{WBS_PREFIX}:{obj.pk}', str(obj))
        if workgroup_is_extern(obj.work_group):
            extern_psp.append(option)
        else:
            intern_psp.append(option)
    cost_center_options = [
        (f'{CC_PREFIX}:{obj.pk}', str(obj))
        for obj in CostCenter.objects.order_by('cost_center')
    ]
    if intern_psp:
        choices.append(('PSP Elements', intern_psp))
    if cost_center_options:
        choices.append(('Cost Centers', cost_center_options))
    if extern_psp:
        choices.append((EXTERN_WORKGROUP_SHORT_NAME, extern_psp))
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
        # Do not hit the DB at import/class-definition time; choices are
        # refreshed in FundingSourceFormMixin.__init__.
        kwargs.setdefault(
            'choices',
            [('', '— Select PSP element or cost center —')],
        )
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


def form_posted_delete(form) -> bool:
    """True when the formset DELETE flag is present in raw POST data."""
    if not getattr(form, 'is_bound', False):
        return False
    data = getattr(form, 'data', None)
    if data is None:
        return False
    raw = data.get(form.add_prefix('DELETE'))
    if raw in (True, 1):
        return True
    return str(raw or '').strip().lower() in {'on', 'true', '1', 'yes'}


class FundingSourceFormMixin:
    """Replace wbs_element-only selection with PSP + cost center dropdown."""

    # Hidden/incomplete deleted rows must still POST; HTML5 required would block.
    use_required_attribute = False

    def _posted_for_delete(self):
        return form_posted_delete(self)

    def apply_posted_delete(self):
        """Skip field validation when the row is marked for deletion."""
        if not self._posted_for_delete():
            return False
        from django.forms.utils import ErrorDict
        self._errors = ErrorDict()
        self.cleaned_data = {'DELETE': True}
        if getattr(self.instance, 'pk', None):
            self.cleaned_data['id'] = self.instance
        return True

    def full_clean(self):
        if self.apply_posted_delete():
            return
        super().full_clean()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Prefer a class-level field (so admin inlines see it in base_fields),
        # but still inject one if a form only relies on the mixin.
        if 'funding_source' not in self.fields:
            self.fields['funding_source'] = FundingSourceField()
        self.fields['funding_source'].choices = build_funding_source_choices()
        self.fields['funding_source'].widget.attrs.setdefault('class', 'form-control')
        # Hide raw FK fields when present (admin default ModelForm would show them).
        self.fields.pop('wbs_element', None)
        self.fields.pop('cost_center', None)
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