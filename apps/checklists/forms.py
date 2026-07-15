from django import forms
from django.core.exceptions import ValidationError
from django.utils.text import slugify

from apps.checklists.models import (
    ChecklistTemplate,
    ChecklistTemplateNode,
    ChecklistTemplateVersion,
)
from apps.hr.models import Employee


class ChecklistTemplateForm(forms.ModelForm):
    class Meta:
        model = ChecklistTemplate
        fields = [
            'slug', 'name_en', 'name_de', 'description_en', 'description_de',
        ]
        widgets = {
            'slug': forms.TextInput(attrs={'class': 'form-control'}),
            'name_en': forms.TextInput(attrs={'class': 'form-control'}),
            'name_de': forms.TextInput(attrs={'class': 'form-control'}),
            'description_en': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'description_de': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def clean_slug(self):
        slug = (self.cleaned_data.get('slug') or '').strip()
        if not slug and self.cleaned_data.get('name_en'):
            slug = slugify(self.cleaned_data['name_en'])
        if not slug:
            raise ValidationError('Slug is required.')
        qs = ChecklistTemplate.objects.filter(slug=slug)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError('A template with this slug already exists.')
        return slug


class ChecklistTemplateVersionForm(forms.ModelForm):
    class Meta:
        model = ChecklistTemplateVersion
        fields = ['completion_mode', 'anchor_node']
        widgets = {
            'completion_mode': forms.Select(attrs={'class': 'form-select'}),
            'anchor_node': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, version=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.version = version
        self.fields['anchor_node'].required = False
        self.fields['anchor_node'].empty_label = '— None —'
        if version:
            self.fields['anchor_node'].queryset = version.nodes.filter(
                node_kind=ChecklistTemplateNode.NodeKind.FIELD,
            ).order_by('sort_order', 'pk')

    def clean(self):
        cleaned = super().clean()
        mode = cleaned.get('completion_mode')
        anchor = cleaned.get('anchor_node')
        if mode == ChecklistTemplateVersion.CompletionMode.ANCHOR_FIELD and not anchor:
            raise ValidationError('Anchor field is required for anchor-field completion mode.')
        if anchor and self.version and anchor.version_id != self.version.pk:
            raise ValidationError('Anchor node must belong to this version.')
        return cleaned


class ChecklistTemplateNodeForm(forms.ModelForm):
    class Meta:
        model = ChecklistTemplateNode
        fields = [
            'parent', 'sort_order', 'node_kind', 'field_type', 'choice_key',
            'label_en', 'label_de', 'help_en', 'help_de',
            'required_for_completion', 'allow_not_applicable',
            'editable_by_subject', 'editable_by_coordinators', 'editable_by_employees',
            'visible_to_subject', 'file_target', 'employee_document_type',
            'storage_label_en', 'storage_label_de',
        ]
        widgets = {
            'parent': forms.Select(attrs={'class': 'form-select'}),
            'sort_order': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'node_kind': forms.Select(attrs={'class': 'form-select'}),
            'field_type': forms.Select(attrs={'class': 'form-select'}),
            'choice_key': forms.TextInput(attrs={'class': 'form-control'}),
            'label_en': forms.TextInput(attrs={'class': 'form-control'}),
            'label_de': forms.TextInput(attrs={'class': 'form-control'}),
            'help_en': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'help_de': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'editable_by_employees': forms.SelectMultiple(attrs={'class': 'form-select', 'size': 6}),
            'file_target': forms.Select(attrs={'class': 'form-select'}),
            'employee_document_type': forms.Select(attrs={'class': 'form-select'}),
            'storage_label_en': forms.TextInput(attrs={'class': 'form-control'}),
            'storage_label_de': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, version=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.version = version
        self.fields['parent'].required = False
        self.fields['parent'].empty_label = '— Top level —'
        self.fields['field_type'].required = False
        self.fields['choice_key'].required = False
        self.fields['file_target'].required = False
        self.fields['employee_document_type'].required = False
        self.fields['editable_by_employees'].required = False
        self.fields['editable_by_employees'].queryset = Employee.objects.order_by(
            'last_name', 'first_name',
        )
        if version:
            self._set_parent_queryset()

    def _set_parent_queryset(self):
        node_kind = self.data.get('node_kind') or (
            self.instance.node_kind if self.instance.pk else ChecklistTemplateNode.NodeKind.SECTION
        )
        qs = self.version.nodes.all()
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if node_kind == ChecklistTemplateNode.NodeKind.RADIO_OPTION:
            qs = qs.filter(
                node_kind=ChecklistTemplateNode.NodeKind.FIELD,
                field_type=ChecklistTemplateNode.FieldType.RADIO_GROUP,
            )
        elif node_kind == ChecklistTemplateNode.NodeKind.FIELD:
            qs = qs.filter(node_kind=ChecklistTemplateNode.NodeKind.SECTION)
        else:
            qs = qs.filter(node_kind=ChecklistTemplateNode.NodeKind.SECTION)
        self.fields['parent'].queryset = qs.order_by('sort_order', 'pk')

    def clean(self):
        cleaned = super().clean()
        node_kind = cleaned.get('node_kind')
        parent = cleaned.get('parent')
        field_type = cleaned.get('field_type') or ''

        if node_kind == ChecklistTemplateNode.NodeKind.SECTION:
            if parent and parent.node_kind != ChecklistTemplateNode.NodeKind.SECTION:
                raise ValidationError('Sections can only be nested under other sections.')
        elif node_kind == ChecklistTemplateNode.NodeKind.FIELD:
            if not field_type:
                raise ValidationError('Field type is required for field nodes.')
            if parent and parent.node_kind != ChecklistTemplateNode.NodeKind.SECTION:
                raise ValidationError('Fields must be placed under a section.')
        elif node_kind == ChecklistTemplateNode.NodeKind.RADIO_OPTION:
            if not parent:
                raise ValidationError('Radio options must belong to a radio group field.')
            if parent.field_type != ChecklistTemplateNode.FieldType.RADIO_GROUP:
                raise ValidationError('Radio options must belong to a radio group field.')
            if not (cleaned.get('choice_key') or '').strip():
                raise ValidationError('Choice key is required for radio options.')

        if parent and self.version and parent.version_id != self.version.pk:
            raise ValidationError('Parent node must belong to this version.')
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.version = self.version
        if commit:
            instance.save()
            self.save_m2m()
        return instance
