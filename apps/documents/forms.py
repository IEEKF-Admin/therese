from django import forms
from django.contrib.auth.models import Group

from apps.hr.models import Employee
from .models import DocumentTag


class DocumentUploadForm(forms.Form):
    title = forms.CharField(
        max_length=255,
        label="Title",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    description = forms.CharField(
        required=False,
        label="Description",
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3})
    )
    file = forms.FileField(
        label="File (PDF, JPG, PNG)",
        widget=forms.ClearableFileInput(attrs={'class': 'form-control'})
    )
    tags = forms.CharField(
        required=False,
        label="Tags (comma separated)",
        help_text="e.g. Contract, 2025, HR",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Contract, Certificate, 2025'
        })
    )

    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            allowed_types = [
                'application/pdf',
                'image/jpeg', 'image/jpg', 'image/pjpeg', 'image/pjp',
                'image/png'
            ]
            if file.content_type not in allowed_types:
                raise forms.ValidationError(
                    f"Only PDF, JPG and PNG files are allowed. "
                    f"Detected type: {file.content_type}"
                )
            if file.size > 20 * 1024 * 1024:  # 20 MB Limit
                raise forms.ValidationError("The file may not exceed 20 MB.")
        return file

    def clean_tags(self):
        tags = self.cleaned_data.get('tags', '')
        if tags:
            tag_list = [t.strip() for t in tags.split(',') if t.strip()]
            if len(tag_list) > 10:
                raise forms.ValidationError("Maximal 10 Tags erlaubt.")
            return tag_list
        return []


class DocumentEditForm(forms.Form):
    """Formular zum Bearbeiten der Metadaten eines Dokuments."""
    title = forms.CharField(
        max_length=255,
        label="Title",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    description = forms.CharField(
        required=False,
        label="Description",
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4})
    )
    tags = forms.CharField(
        required=False,
        label="Tags (comma separated)",
        help_text="e.g. Contract, 2025, HR",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Contract, Certificate, 2025'
        })
    )

    def clean_tags(self):
        tags = self.cleaned_data.get('tags', '')
        if tags:
            tag_list = [t.strip() for t in tags.split(',') if t.strip()]
            if len(tag_list) > 10:
                raise forms.ValidationError("Maximal 10 Tags erlaubt.")
            return tag_list
        return []


class DocumentVersionUploadForm(forms.Form):
    """Form zum Hochladen einer neuen Version eines bestehenden Dokuments."""
    file = forms.FileField(
        label="Neue Datei (PDF, JPG, PNG)",
        widget=forms.ClearableFileInput(attrs={'class': 'form-control'})
    )
    comment = forms.CharField(
        required=False,
        label="Kommentar zur Version (optional)",
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'z. B. Korrigierte Version nach Feedback'
        })
    )

    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            allowed_types = ['application/pdf', 'image/jpeg', 'image/png']
            if file.content_type not in allowed_types:
                raise forms.ValidationError("Nur PDF, JPG und PNG Dateien sind erlaubt.")
            if file.size > 20 * 1024 * 1024:
                raise forms.ValidationError("Die Datei darf maximal 20 MB groÃŸ sein.")
        return file


class ShareWithUsersForm(forms.Form):
    """Form to share a document with one or more users."""

    users = forms.ModelMultipleChoiceField(
        label="Users",
        queryset=Employee.objects.all().order_by('last_name', 'first_name'),
        widget=forms.SelectMultiple(attrs={'class': 'form-control', 'size': '8'}),
        help_text="Hold Ctrl (Windows) or Cmd (Mac) to select multiple users."
    )

    permission = forms.ChoiceField(
        label="Permission Level",
        choices=[
            ('viewer', 'Viewer (view + download)'),
            ('editor', 'Editor (upload new versions + edit metadata)'),
            ('manager', 'Manager (manage shares as well)'),
        ],
        initial='viewer',
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    SIGNATURE_CHOICES = [
        ('', 'No signature required'),
        ('signature', 'Signature (prompt on open)'),
        ('ask_for_signature', 'Ask for signature (popup on login)'),
    ]

    signature_requirement = forms.ChoiceField(
        label="Signature Requirement",
        choices=SIGNATURE_CHOICES,
        initial='',
        required=False,
        widget=forms.RadioSelect,
        help_text="Choose whether recipients must confirm they have seen this document."
    )


class ShareWithGroupsForm(forms.Form):
    """Form to share a document with one or more groups."""

    groups = forms.ModelMultipleChoiceField(
        label="Groups",
        queryset=Group.objects.all().order_by('name'),
        widget=forms.SelectMultiple(attrs={'class': 'form-control', 'size': '6'}),
        help_text="Hold Ctrl (Windows) or Cmd (Mac) to select multiple groups."
    )

    permission = forms.ChoiceField(
        label="Permission Level",
        choices=[
            ('viewer', 'Viewer (view + download)'),
            ('editor', 'Editor (upload new versions + edit metadata)'),
            ('manager', 'Manager (manage shares as well)'),
        ],
        initial='viewer',
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    SIGNATURE_CHOICES = [
        ('', 'No signature required'),
        ('signature', 'Signature (prompt on open)'),
        ('ask_for_signature', 'Ask for signature (popup on login)'),
    ]

    signature_requirement = forms.ChoiceField(
        label="Signature Requirement",
        choices=SIGNATURE_CHOICES,
        initial='',
        required=False,
        widget=forms.RadioSelect,
        help_text="Choose whether recipients must confirm they have seen this document."
    )



