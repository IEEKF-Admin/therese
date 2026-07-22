from django import forms
from django.core.exceptions import ValidationError
from django.utils.html import conditional_escape, format_html, format_html_join
from django.utils.safestring import mark_safe

from apps.accounts.models import CustomUser
from apps.core.html_sanitize import sanitize_html
from apps.core.upload_validation import DOC_ATTACHMENT_EXT, MAX_DEFAULT_UPLOAD_BYTES, validate_upload

from .category_utils import build_category_tree_rows, get_descendant_ids
from .models import Document, DocumentAttachment, DocumentCategory, DocumentVersion


class DocumentCategoryForm(forms.ModelForm):
    class Meta:
        model = DocumentCategory
        fields = ['name', 'parent']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'parent': forms.Select(attrs={'class': 'form-select'}),
        }
        labels = {
            'parent': 'Parent category',
        }
        help_texts = {
            'parent': 'Leave empty for a top-level category.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['parent'].required = False
        self.fields['parent'].empty_label = '— Top level —'

        queryset = DocumentCategory.objects.select_related('parent').order_by('name')
        if self.instance.pk:
            exclude_ids = {self.instance.pk} | get_descendant_ids(self.instance)
            queryset = queryset.exclude(pk__in=exclude_ids)
        self.fields['parent'].queryset = queryset

    def clean(self):
        cleaned = super().clean()
        parent = cleaned.get('parent')
        name = cleaned.get('name')
        if not name:
            return cleaned

        duplicate_qs = DocumentCategory.objects.filter(name=name, parent=parent)
        if self.instance.pk:
            duplicate_qs = duplicate_qs.exclude(pk=self.instance.pk)
        if duplicate_qs.exists():
            raise ValidationError('A category with this name already exists at the same level.')

        if parent and self.instance.pk and parent.pk == self.instance.pk:
            raise ValidationError('A category cannot be its own parent.')

        current = parent
        while current is not None:
            if self.instance.pk and current.pk == self.instance.pk:
                raise ValidationError('Circular parent reference is not allowed.')
            current = current.parent
        return cleaned


class TreeSelect(forms.Select):
    def __init__(self, *args, tree_rows=(), **kwargs):
        self.tree_rows = tree_rows
        super().__init__(*args, **kwargs)

    def optgroups(self, name, value, attrs=None):
        # Django passes selected values as a list; never str() the whole list.
        if value is None:
            selected_values = set()
        elif isinstance(value, (list, tuple)):
            selected_values = {str(v) for v in value if v not in (None, '')}
        else:
            selected_values = {str(value)}

        options = []
        for row in self.tree_rows:
            category = row['category']
            option_value = str(category.pk)
            indent = '— ' * row['depth']
            label = f'{indent}{category.name}' if row['depth'] else category.name
            is_selected = option_value in selected_values
            options.append(self.create_option(
                name,
                option_value,
                label,
                is_selected,
                index=len(options),
            ))

        return [(None, options, 0)]


class DualListSelect(forms.SelectMultiple):
    """
    Two multi-select lists: available vs selected.

    Empty selection is allowed (all items can be moved back to Available).
    """

    def render(self, name, value, attrs=None, renderer=None):
        if value is None:
            value = []
        final_attrs = self.build_attrs(self.attrs, attrs)
        final_attrs['name'] = name
        final_attrs['multiple'] = True
        final_attrs.setdefault('class', 'form-select dual-list-selected')
        final_attrs.setdefault('size', '8')
        selected_values = {str(v) for v in value}

        available_opts = []
        selected_opts = []
        for option_value, option_label in self.choices:
            if option_value in (None, ''):
                continue
            opt_val = str(option_value)
            label = conditional_escape(str(option_label))
            html = format_html('<option value="{}">{}</option>', opt_val, mark_safe(label))
            if opt_val in selected_values:
                selected_opts.append(
                    format_html('<option value="{}" selected>{}</option>', opt_val, mark_safe(label))
                )
            else:
                available_opts.append(html)

        available_html = mark_safe('\n'.join(available_opts))
        selected_html = mark_safe('\n'.join(selected_opts))
        selected_attrs = forms.widgets.flatatt(final_attrs)

        return format_html(
            '<div class="dual-list-widget" data-dual-list>'
            '<div class="dual-list-panel">'
            '<div class="dual-list-heading">Available</div>'
            '<select multiple class="form-select dual-list-available" size="8" '
            'aria-label="Available {name}">{available}</select>'
            '</div>'
            '<div class="dual-list-actions">'
            '<button type="button" class="btn-secondary dual-list-add" '
            'title="Add selected" aria-label="Add selected">&rarr;</button>'
            '<button type="button" class="btn-secondary dual-list-remove" '
            'title="Remove selected" aria-label="Remove selected">&larr;</button>'
            '<button type="button" class="btn-subtle dual-list-add-all" '
            'title="Add all" aria-label="Add all">&raquo;</button>'
            '<button type="button" class="btn-subtle dual-list-remove-all" '
            'title="Remove all" aria-label="Remove all">&laquo;</button>'
            '</div>'
            '<div class="dual-list-panel">'
            '<div class="dual-list-heading">Selected</div>'
            '<select{selected_attrs} multiple size="8" '
            'aria-label="Selected {name}">{selected}</select>'
            '</div>'
            '</div>',
            name=name,
            available=available_html,
            selected_attrs=selected_attrs,
            selected=selected_html,
        )


class DocumentVersionDraftForm(forms.ModelForm):
    class Meta:
        model = DocumentVersion
        fields = ['content_html', 'change_summary']
        widgets = {
            'content_html': forms.Textarea(attrs={'class': 'form-control wysiwyg-editor', 'rows': 20}),
            'change_summary': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Optional summary of changes',
            }),
        }
        labels = {
            'content_html': 'Content',
            'change_summary': 'Change summary',
        }

    def clean_content_html(self):
        return sanitize_html(self.cleaned_data.get('content_html'))


class DocumentMetaForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = [
            'title',
            'category',
            'requires_read_acknowledgement',
            'audience_match_mode',
            'target_users',
            'target_workgroups',
            'target_groups',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'requires_read_acknowledgement': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'audience_match_mode': forms.Select(attrs={'class': 'form-select'}),
            'target_users': DualListSelect(attrs={'class': 'form-select', 'size': 8}),
            'target_workgroups': DualListSelect(attrs={'class': 'form-select', 'size': 8}),
            'target_groups': DualListSelect(attrs={'class': 'form-select', 'size': 8}),
        }
        labels = {
            'requires_read_acknowledgement': 'Requires read acknowledgement',
            'audience_match_mode': 'Combine targets with',
            'target_users': 'Target users',
            'target_workgroups': 'Target work groups',
            'target_groups': 'Target Django groups',
        }
        help_texts = {
            'target_users': 'Leave all three target lists empty to show the document to everyone with view permission.',
            'target_workgroups': 'Move items between Available and Selected. Selected may be empty.',
            'target_groups': 'Move items between Available and Selected. Selected may be empty.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        categories = DocumentCategory.objects.select_related('parent').all()
        tree_rows = build_category_tree_rows(categories)
        self.fields['category'].widget = TreeSelect(
            attrs={'class': 'form-select'},
            tree_rows=tree_rows,
        )
        self.fields['category'].queryset = categories
        # Ensure current category is selected when editing (TreeSelect must see pk)
        if self.instance and self.instance.pk and self.instance.category_id:
            self.fields['category'].initial = self.instance.category_id
        self.fields['target_users'].queryset = CustomUser.objects.filter(
            is_active=True
        ).order_by('last_name', 'first_name', 'username')
        self.fields['target_users'].required = False
        self.fields['target_workgroups'].required = False
        self.fields['target_groups'].required = False
        self.fields['target_users'].help_text = (
            'Leave Available/Selected empty (nothing selected) to show to everyone with view permission.'
        )


class DocumentAttachmentForm(forms.ModelForm):
    class Meta:
        model = DocumentAttachment
        fields = ['label', 'file']
        widgets = {
            'label': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'file': forms.ClearableFileInput(attrs={'class': 'form-control form-control-sm'}),
        }

    def clean_file(self):
        uploaded = self.cleaned_data.get('file')
        if uploaded and hasattr(uploaded, 'read'):
            validate_upload(
                uploaded,
                allowed_extensions=DOC_ATTACHMENT_EXT,
                max_bytes=MAX_DEFAULT_UPLOAD_BYTES,
                require_magic=False,  # Office docs lack simple magic in all cases
            )
        return uploaded


DocumentAttachmentFormSet = forms.inlineformset_factory(
    DocumentVersion,
    DocumentAttachment,
    form=DocumentAttachmentForm,
    extra=1,
    can_delete=False,
)