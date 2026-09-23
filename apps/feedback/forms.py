from django import forms
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.html import strip_tags

from apps.core.html_sanitize import sanitize_html
from apps.core.upload_validation import IMAGE_EXT, validate_upload
from apps.feedback.models import FeedbackItem


def _html_is_blank(value):
    text = strip_tags(value or '').replace('\xa0', ' ').replace('&nbsp;', ' ').strip()
    if text:
        return False
    return '<img' not in (value or '').lower()


class FeedbackItemForm(forms.ModelForm):
    class Meta:
        model = FeedbackItem
        fields = ['kind', 'title', 'description', 'page_url', 'screenshot']
        widgets = {
            'kind': forms.RadioSelect(),
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Short summary',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control wysiwyg-editor',
                'rows': 8,
                'data-wysiwyg-height': '280',
            }),
            'page_url': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. /tasks/ or https://…',
            }),
            'screenshot': forms.ClearableFileInput(attrs={
                'class': 'form-control',
                'accept': '.jpg,.jpeg,.png,.gif,.webp,image/jpeg,image/png,image/gif,image/webp',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['kind'].required = True
        self.fields['kind'].choices = list(FeedbackItem.Kind.choices)
        self.fields['kind'].widget.choices = self.fields['kind'].choices
        self.fields['title'].required = True
        self.fields['description'].required = True
        self.fields['page_url'].required = False
        self.fields['screenshot'].required = False
        if not self.is_bound and not (self.instance and self.instance.pk):
            self.fields['kind'].initial = FeedbackItem.Kind.BUG

    def clean_title(self):
        value = (self.cleaned_data.get('title') or '').strip()
        if not value:
            raise forms.ValidationError('Please enter a title.')
        return value

    def clean_description(self):
        value = sanitize_html(self.cleaned_data.get('description') or '')
        if _html_is_blank(value):
            raise forms.ValidationError('Please describe the bug or feature.')
        return value

    def clean_page_url(self):
        return (self.cleaned_data.get('page_url') or '').strip()

    def clean_screenshot(self):
        uploaded = self.cleaned_data.get('screenshot')
        if not uploaded or uploaded is False:
            return uploaded
        if hasattr(uploaded, 'read'):
            try:
                validate_upload(
                    uploaded,
                    allowed_extensions=IMAGE_EXT,
                    require_magic=True,
                )
            except DjangoValidationError as exc:
                raise forms.ValidationError(
                    exc.messages[0] if getattr(exc, 'messages', None) else str(exc)
                ) from exc
        return uploaded

    def clean(self):
        cleaned = super().clean()
        kind = cleaned.get('kind')
        url = cleaned.get('page_url') or ''
        if kind == FeedbackItem.Kind.FEATURE:
            cleaned['page_url'] = ''
        elif kind == FeedbackItem.Kind.BUG and not url:
            self.add_error(
                'page_url',
                'Please enter the page URL where the bug occurs.',
            )
        return cleaned


class FeedbackCommentForm(forms.Form):
    body = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Add a comment…',
        }),
    )

    def clean_body(self):
        value = (self.cleaned_data.get('body') or '').strip()
        if not value:
            raise forms.ValidationError('Please enter a comment.')
        return value


class FeedbackAdminForm(forms.Form):
    status = forms.ChoiceField(
        choices=FeedbackItem.Status.choices,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label='Status',
    )
    target_date = forms.DateField(
        required=False,
        input_formats=['%d.%m.%Y', '%Y-%m-%d'],
        widget=forms.DateInput(attrs={
            'type': 'text',
            'class': 'form-control date-picker',
            'placeholder': 'TT.MM.JJJJ',
        }),
        label='Target date',
    )


class FeedbackMergeForm(forms.Form):
    target = forms.ModelChoiceField(
        queryset=FeedbackItem.objects.none(),
        empty_label='— Select report —',
        widget=forms.Select(attrs={'class': 'form-control'}),
        label='Merge this report into',
    )

    def __init__(self, *args, item=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = FeedbackItem.objects.filter(merged_into__isnull=True)
        if item is not None:
            qs = qs.filter(kind=item.kind).exclude(pk=item.pk)
        self.fields['target'].queryset = qs.order_by('-created_at', '-pk')
