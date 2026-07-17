from django import forms
from django.core.exceptions import ValidationError

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
        value = str(value) if value is not None else None
        selected = {value} if value is not None else set()

        options = []
        for row in self.tree_rows:
            category = row['category']
            option_value = str(category.pk)
            indent = '— ' * row['depth']
            label = f'{indent}{category.name}' if row['depth'] else category.name
            options.append(self.create_option(
                name,
                option_value,
                label,
                selected,
                index=len(options),
            ))

        return [(None, options, 0)]


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
            'target_users': forms.SelectMultiple(attrs={'class': 'form-select', 'size': 6}),
            'target_workgroups': forms.SelectMultiple(attrs={'class': 'form-select', 'size': 6}),
            'target_groups': forms.SelectMultiple(attrs={'class': 'form-select', 'size': 6}),
        }
        labels = {
            'requires_read_acknowledgement': 'Requires read acknowledgement',
            'audience_match_mode': 'Combine targets with',
        }
        help_texts = {
            'target_users': 'Leave all empty to show the document to everyone with view permission.',
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
        self.fields['target_users'].queryset = CustomUser.objects.filter(
            is_active=True
        ).order_by('last_name', 'first_name', 'username')
        self.fields['target_users'].required = False
        self.fields['target_workgroups'].required = False
        self.fields['target_groups'].required = False


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