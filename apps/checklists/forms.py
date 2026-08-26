from django import forms
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.utils.text import slugify

from apps.checklists.models import (
    ChecklistTemplate,
    ChecklistTemplateNode,
    ChecklistTemplateVersion,
)
from apps.core.html_sanitize import sanitize_html
from apps.documents.forms import DualListSelect
from apps.hr.models import Employee

_BOOL_DEFAULTS_TRUE = (
    'editable_by_subject',
    'editable_by_coordinators',
    'visible_to_subject',
)
_UNCHANGED = '__unchanged__'
_YES_NO_UNCHANGED = [
    (_UNCHANGED, '— Unchanged —'),
    ('1', 'Yes'),
    ('0', 'No'),
]


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
            'editable_by_groups',
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
            'editable_by_employees': DualListSelect(attrs={'class': 'form-select', 'size': 8}),
            'editable_by_groups': DualListSelect(attrs={'class': 'form-select', 'size': 8}),
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
        self.fields['parent'].widget.attrs['data-parent-select'] = '1'
        self.fields['parent'].label_from_instance = lambda obj: obj.parent_choice_label
        self.fields['field_type'].required = False
        self.fields['choice_key'].required = False
        self.fields['file_target'].required = False
        self.fields['employee_document_type'].required = False
        self.fields['editable_by_employees'].required = False
        self.fields['editable_by_employees'].queryset = Employee.objects.order_by(
            'last_name', 'first_name',
        )
        self.fields['editable_by_groups'].required = False
        self.fields['editable_by_groups'].queryset = Group.objects.order_by('name')
        if version:
            self._set_parent_queryset()
        self._apply_node_kind_field_state()

    def _apply_node_kind_field_state(self):
        node_kind = self.data.get('node_kind') or (
            self.instance.node_kind if self.instance.pk else ChecklistTemplateNode.NodeKind.SECTION
        )
        if node_kind == ChecklistTemplateNode.NodeKind.SECTION:
            self.fields['label_en'].label = 'Name (EN)'
            self.fields['label_de'].label = 'Name (DE)'
        else:
            self.fields['label_en'].label = 'Label (EN)'
            self.fields['label_de'].label = 'Label (DE)'
        is_html = node_kind == ChecklistTemplateNode.NodeKind.HTML
        if is_html:
            self.fields['help_en'].label = 'Content (EN)'
            self.fields['help_de'].label = 'Content (DE)'
            self.fields['help_en'].widget = forms.Textarea(
                attrs={'class': 'form-control wysiwyg-editor', 'rows': 12},
            )
            self.fields['help_de'].widget = forms.Textarea(
                attrs={'class': 'form-control wysiwyg-editor', 'rows': 12},
            )
        elif node_kind == ChecklistTemplateNode.NodeKind.FIELD:
            self.fields['help_en'].label = 'Help (EN)'
            self.fields['help_de'].label = 'Help (DE)'

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
        elif node_kind in (
            ChecklistTemplateNode.NodeKind.FIELD,
            ChecklistTemplateNode.NodeKind.HTML,
        ):
            qs = qs.filter(node_kind=ChecklistTemplateNode.NodeKind.SECTION)
        else:
            qs = qs.filter(node_kind=ChecklistTemplateNode.NodeKind.SECTION)
        self.fields['parent'].queryset = qs.select_related('parent').order_by('sort_order', 'pk')

    def clean(self):
        cleaned = super().clean()
        node_kind = cleaned.get('node_kind')
        parent = cleaned.get('parent')
        field_type = cleaned.get('field_type') or ''

        if node_kind == ChecklistTemplateNode.NodeKind.SECTION:
            cleaned['field_type'] = ''
            if not (cleaned.get('label_en') or '').strip() and not (cleaned.get('label_de') or '').strip():
                raise ValidationError('Name (EN or DE) is required for sections.')
            if parent and parent.node_kind != ChecklistTemplateNode.NodeKind.SECTION:
                raise ValidationError('Sections can only be nested under other sections.')
        elif node_kind == ChecklistTemplateNode.NodeKind.FIELD:
            if not field_type:
                raise ValidationError('Field type is required for field nodes.')
            if parent and parent.node_kind != ChecklistTemplateNode.NodeKind.SECTION:
                raise ValidationError('Fields must be placed under a section.')
        elif node_kind == ChecklistTemplateNode.NodeKind.RADIO_OPTION:
            cleaned['field_type'] = ''
            if not parent:
                raise ValidationError('Radio options must belong to a radio group field.')
            if parent.field_type != ChecklistTemplateNode.FieldType.RADIO_GROUP:
                raise ValidationError('Radio options must belong to a radio group field.')
            if not (cleaned.get('choice_key') or '').strip():
                raise ValidationError('Choice key is required for radio options.')
        elif node_kind == ChecklistTemplateNode.NodeKind.HTML:
            cleaned['field_type'] = ''
            cleaned['required_for_completion'] = False
            cleaned['allow_not_applicable'] = False
            if not (cleaned.get('help_en') or '').strip() and not (cleaned.get('help_de') or '').strip():
                raise ValidationError('Content (EN or DE) is required for HTML nodes.')
            if parent and parent.node_kind != ChecklistTemplateNode.NodeKind.SECTION:
                raise ValidationError('HTML blocks must be placed under a section.')

        if parent and self.version and parent.version_id != self.version.pk:
            raise ValidationError('Parent node must belong to this version.')

        if not self.instance.pk:
            for name in _BOOL_DEFAULTS_TRUE:
                if name not in self.data:
                    cleaned[name] = True

        # HTML nodes store rich content in help_*; field help may contain markup too.
        if cleaned.get('help_en') is not None:
            cleaned['help_en'] = sanitize_html(cleaned.get('help_en'))
        if cleaned.get('help_de') is not None:
            cleaned['help_de'] = sanitize_html(cleaned.get('help_de'))
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.version = self.version
        if commit:
            instance.save()
            self.save_m2m()
        return instance


def _employee_choice_label(employee):
    return f'{employee.get_full_name()} ({employee.employee_number})'


class ChecklistAssignForm(forms.Form):
    template_version = forms.ModelChoiceField(
        queryset=ChecklistTemplateVersion.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Published version',
    )
    employees = forms.ModelMultipleChoiceField(
        queryset=Employee.objects.none(),
        widget=DualListSelect(
            attrs={'class': 'form-select', 'size': 12},
            available_heading='Not selected',
            selected_heading='Selected',
        ),
        label='Employees',
        required=True,
    )

    def __init__(self, *args, published_versions=None, lock_version=None, **kwargs):
        super().__init__(*args, **kwargs)
        versions = published_versions if published_versions is not None else (
            ChecklistTemplateVersion.objects.filter(
                status=ChecklistTemplateVersion.Status.PUBLISHED,
            ).select_related('template')
        )
        self.fields['template_version'].queryset = versions
        self.fields['template_version'].label_from_instance = (
            lambda v: f'{v.template.name_en} ({v.version_label})'
        )
        self.fields['employees'].queryset = Employee.objects.order_by(
            'last_name', 'first_name',
        )
        self.fields['employees'].label_from_instance = _employee_choice_label
        self.lock_version = lock_version
        if lock_version:
            self.fields['template_version'].initial = lock_version.pk
            self.fields['template_version'].widget = forms.HiddenInput()


class ChecklistNodeBulkForm(forms.Form):
    parent = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Parent',
    )
    required_for_completion = forms.ChoiceField(
        choices=_YES_NO_UNCHANGED, required=False, widget=forms.Select(attrs={'class': 'form-select'}),
        label='Required for completion',
    )
    allow_not_applicable = forms.ChoiceField(
        choices=_YES_NO_UNCHANGED, required=False, widget=forms.Select(attrs={'class': 'form-select'}),
        label='Allow N/A',
    )
    editable_by_subject = forms.ChoiceField(
        choices=_YES_NO_UNCHANGED, required=False, widget=forms.Select(attrs={'class': 'form-select'}),
        label='Editable by subject',
    )
    editable_by_coordinators = forms.ChoiceField(
        choices=_YES_NO_UNCHANGED, required=False, widget=forms.Select(attrs={'class': 'form-select'}),
        label='Editable by coordinators',
    )
    visible_to_subject = forms.ChoiceField(
        choices=_YES_NO_UNCHANGED, required=False, widget=forms.Select(attrs={'class': 'form-select'}),
        label='Visible to subject',
    )

    def __init__(self, *args, version=None, nodes=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.version = version
        self.nodes = list(nodes or [])
        kinds = {n.node_kind for n in self.nodes}
        NodeKind = ChecklistTemplateNode.NodeKind
        self.show_required = kinds == {NodeKind.FIELD}
        self.show_na = kinds == {NodeKind.FIELD}
        self.show_editable = kinds == {NodeKind.FIELD}
        self.show_visible = kinds <= {NodeKind.FIELD, NodeKind.HTML} and bool(kinds)
        self.show_parent = bool(kinds) and (
            kinds == {NodeKind.RADIO_OPTION} or NodeKind.RADIO_OPTION not in kinds
        )
        if not self.show_required:
            self.fields.pop('required_for_completion')
        if not self.show_na:
            self.fields.pop('allow_not_applicable')
        if not self.show_editable:
            self.fields.pop('editable_by_subject')
            self.fields.pop('editable_by_coordinators')
        if not self.show_visible:
            self.fields.pop('visible_to_subject')
        if self.show_parent and version:
            choices = [(_UNCHANGED, '— Unchanged —')]
            if NodeKind.RADIO_OPTION not in kinds:
                choices.append(('', '— Top level —'))
            if kinds == {NodeKind.RADIO_OPTION}:
                parents = version.nodes.filter(
                    node_kind=NodeKind.FIELD,
                    field_type=ChecklistTemplateNode.FieldType.RADIO_GROUP,
                )
            else:
                parents = version.nodes.filter(node_kind=NodeKind.SECTION)
            exclude_pks = {n.pk for n in self.nodes if n.node_kind == NodeKind.SECTION}
            for parent in parents.order_by('sort_order', 'pk'):
                if parent.pk in exclude_pks:
                    continue
                choices.append((str(parent.pk), parent.parent_choice_label))
            self.fields['parent'].choices = choices
        else:
            self.fields.pop('parent', None)

    def has_shared_fields(self):
        return bool(self.fields)

    def apply(self):
        cleaned = self.cleaned_data
        bool_map = {
            'required_for_completion': cleaned.get('required_for_completion'),
            'allow_not_applicable': cleaned.get('allow_not_applicable'),
            'editable_by_subject': cleaned.get('editable_by_subject'),
            'editable_by_coordinators': cleaned.get('editable_by_coordinators'),
            'visible_to_subject': cleaned.get('visible_to_subject'),
        }
        parent_choice = cleaned.get('parent', _UNCHANGED)
        updated = 0
        for node in self.nodes:
            fields = []
            if parent_choice and parent_choice != _UNCHANGED:
                node.parent_id = int(parent_choice) if parent_choice else None
                fields.append('parent')
            elif parent_choice == '':
                node.parent_id = None
                fields.append('parent')
            for name, value in bool_map.items():
                if value == '1':
                    setattr(node, name, True)
                    fields.append(name)
                elif value == '0':
                    setattr(node, name, False)
                    fields.append(name)
            if fields:
                fields.append('updated_at')
                node.save(update_fields=fields)
                updated += 1
        return updated
