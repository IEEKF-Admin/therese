"""
apps/tasks/forms.py
Project: THERESE – Transparent HR Resource System Enhanced
"""
from django import forms
from .models import (
    PurchaseOrderTask,
    PurchaseItem,
    PersonnelReallocationTask,
    PersonnelContractExtensionTask,
    GenericTextTask,
    StandardPurchaseItem,
    PURCHASE_STATUSES,
    GENERIC_STATUSES,
    PERSONNEL_STATUSES,
)
from apps.finances.models import WBSElement
from apps.hr.models import Employee
from apps.accounts.permissions import GroupNames


class PurchaseOrderTaskForm(forms.ModelForm):
    """
    Formular für Purchase Orders mit Radio-Buttons für Status.
    """
    class Meta:
        model = PurchaseOrderTask
        fields = ['supplier', 'wbs_element', 'priority', 'assignee', 'status', 'comment', 'at_beleg_nummer']
        widgets = {
            'comment': forms.Textarea(attrs={'rows': 4}),
            'status': forms.RadioSelect(attrs={'class': 'status-radio'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.is_creation = kwargs.pop('is_creation', False)
        super().__init__(*args, **kwargs)

        # ==================== Supplier ====================
        if 'supplier' in self.fields:
            if not self.is_creation and self.user and self.user.groups.filter(name=GroupNames.PROCUREMENT_COORDINATOR).exists():
                self.fields['supplier'].widget = forms.HiddenInput()
                if self.instance and self.instance.pk:
                    self.fields['supplier'].initial = self.instance.supplier
                self.fields['supplier'].required = True
            else:
                self.fields['supplier'].widget.attrs.update({'class': 'form-control'})

        # ==================== Assignee ====================
        if 'assignee' in self.fields:
            # Purchase Requesters und PIs sollen das Assignee-Dropdown niemals sehen
            if self.user and (
                self.user.groups.filter(name=GroupNames.PROCUREMENT_REQUESTER).exists() or
                self.user.groups.filter(name=GroupNames.PI).exists()
            ):
                self.fields['assignee'].widget = forms.HiddenInput()
                self.fields['assignee'].required = False
                if self.is_creation:
                    self.fields['assignee'].initial = None  # bleibt unassigned, bis Coordinator/Approver es setzt

            else:
                # Coordinator und andere (z.B. Approver) können Assignee aus Approvers wählen
                approvers = Employee.objects.filter(user__groups__name=GroupNames.PROCUREMENT_APPROVER)
                self.fields['assignee'].queryset = approvers.order_by('last_name', 'first_name')
                self.fields['assignee'].widget.attrs.update({'class': 'form-control'})
                self.fields['assignee'].empty_label = "— Unassigned —"

        # ==================== AT - Beleg Nummer ====================
        if 'at_beleg_nummer' in self.fields:
            if self.is_creation:
                self.fields['at_beleg_nummer'].widget = forms.HiddenInput()
                self.fields['at_beleg_nummer'].required = False
            elif self.user and not (
                self.user.groups.filter(name=GroupNames.PROCUREMENT_COORDINATOR).exists() or
                self.user.groups.filter(name=GroupNames.PROCUREMENT_APPROVER).exists()
            ):
                self.fields['at_beleg_nummer'].widget = forms.HiddenInput()
                self.fields['at_beleg_nummer'].required = False
            else:
                self.fields['at_beleg_nummer'].widget.attrs.update({'class': 'form-control'})

        # ==================== Status ====================
        if 'status' in self.fields:
            self.fields['status'].choices = PURCHASE_STATUSES

            if self.is_creation:
                self.fields['status'].widget = forms.HiddenInput()
                self.fields['status'].initial = 'not_yet_processed'
                self.fields['status'].required = True
                if self.data:
                    self.data = self.data.copy()
                    self.data['status'] = 'not_yet_processed'
            # else: Radio Buttons bleiben (wird im Template manuell gerendert)

        # ==================== WBS Element ====================
        if 'wbs_element' in self.fields:
            self.fields['wbs_element'].queryset = WBSElement.objects.filter(
                wbs_code__regex=r'.*-\d+\.\d+\.1$'
            ).order_by('wbs_code')
            self.fields['wbs_element'].empty_label = "---------"

            if not self.is_creation and self.user and self.user.groups.filter(name=GroupNames.PROCUREMENT_COORDINATOR).exists():
                # Coordinator darf WBS ändern (bleibt Select)
                pass
            elif self.is_creation:
                self.fields['wbs_element'].widget = forms.HiddenInput()
                self.fields['wbs_element'].required = False

    def clean(self):
        cleaned_data = super().clean()
        wbs_element = cleaned_data.get('wbs_element')

        if self.user and self.user.groups.filter(name='Procurement Coordinator').exists():
            if not wbs_element:
                self.add_error('wbs_element', "WBS Element is required for Procurement Coordinators.")

        return cleaned_data


# ====================== Weitere Formulare ======================
class PurchaseItemForm(forms.ModelForm):
    class Meta:
        model = PurchaseItem
        fields = ['product_name', 'product_description', 'link_to_product', 'order_number', 'unit_price', 'quantity']
        widgets = {
            'product_description': forms.Textarea(attrs={'rows': 2}),
            'link_to_product': forms.URLInput(attrs={'placeholder': 'https://...'}),
            'order_number': forms.TextInput(attrs={'placeholder': 'z.B. 4711'}),
            'quantity': forms.NumberInput(attrs={'min': 1, 'step': 1}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'order_number' in self.fields:
            self.fields['order_number'].required = False
            self.fields['order_number'].widget.attrs['placeholder'] = 'z.B. 4711'
        if 'quantity' in self.fields:
            self.fields['quantity'].widget.attrs['min'] = 1
            self.fields['quantity'].widget.attrs['step'] = 1


class PersonnelReallocationTaskForm(forms.ModelForm):
    """
    Form for Personnel Reallocation tasks.
    No title (auto-generated), no assignee/priority/due_date at creation time.
    The entire "Assignment & Priority" card is omitted in the template.
    Comment/Notes gets full width.
    """
    class Meta:
        model = PersonnelReallocationTask
        fields = ['employee', 'target_wbs', 'valid_from', 'valid_until',
                  'plan_position_number', 'comment']
        widgets = {
            'comment': forms.Textarea(attrs={'rows': 6, 'placeholder': 'Add any additional notes or context for this reallocation...'}),
            'valid_from': forms.DateInput(attrs={
                'type': 'text',
                'class': 'form-control date-picker',
                'placeholder': 'TT.MM.JJJJ'
            }),
            'valid_until': forms.DateInput(attrs={
                'type': 'text',
                'class': 'form-control date-picker',
                'placeholder': 'TT.MM.JJJJ'
            }),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.is_creation = kwargs.pop('is_creation', False)
        super().__init__(*args, **kwargs)

        # Status is always hidden for personnel tasks (set at creation)
        if 'status' in self.fields:
            self.fields['status'].choices = PERSONNEL_STATUSES
            if self.is_creation:
                self.fields['status'].widget = forms.HiddenInput()
                self.fields['status'].initial = 'noch nicht bearbeitet'
                self.fields['status'].required = True
                if self.data:
                    self.data = self.data.copy()
                    self.data['status'] = 'noch nicht bearbeitet'

        # Style inputs
        for field_name in ['employee', 'target_wbs', 'plan_position_number']:
            if field_name in self.fields:
                self.fields[field_name].widget.attrs.update({'class': 'form-control'})
                self.fields[field_name].required = True

        for field_name in ['valid_from', 'valid_until']:
            if field_name in self.fields:
                self.fields[field_name].widget.attrs.update({'class': 'form-control'})

        if 'comment' in self.fields:
            self.fields['comment'].widget.attrs.update({'class': 'form-control'})

        # Employee dropdown (all employees)
        if 'employee' in self.fields:
            self.fields['employee'].queryset = Employee.objects.order_by('last_name', 'first_name')
            self.fields['employee'].empty_label = "— Select employee —"

        # Target WBS (reasonable WBS elements)
        if 'target_wbs' in self.fields:
            self.fields['target_wbs'].queryset = WBSElement.objects.all().order_by('wbs_code')
            self.fields['target_wbs'].empty_label = "— Select target WBS —"


class PersonnelContractExtensionTaskForm(forms.ModelForm):
    """
    Form for Personnel Contract Extension tasks.
    No title (auto-generated), no assignee/priority/due_date at creation time.
    The entire "Assignment & Priority" card is omitted in the template.
    Comment/Notes gets full width.
    """
    class Meta:
        model = PersonnelContractExtensionTask
        fields = ['employee', 'plan_position_number', 'valid_from', 'valid_until',
                  'is_limited', 'limitation_reason', 'comment']
        widgets = {
            'comment': forms.Textarea(attrs={'rows': 6, 'placeholder': 'Add any additional notes or context for this contract extension...'}),
            'valid_from': forms.DateInput(attrs={
                'type': 'text',
                'class': 'form-control date-picker',
                'placeholder': 'TT.MM.JJJJ'
            }),
            'valid_until': forms.DateInput(attrs={
                'type': 'text',
                'class': 'form-control date-picker',
                'placeholder': 'TT.MM.JJJJ'
            }),
            'limitation_reason': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.is_creation = kwargs.pop('is_creation', False)
        super().__init__(*args, **kwargs)

        # Status is always hidden for personnel tasks (set at creation)
        if 'status' in self.fields:
            self.fields['status'].choices = PERSONNEL_STATUSES
            if self.is_creation:
                self.fields['status'].widget = forms.HiddenInput()
                self.fields['status'].initial = 'noch nicht bearbeitet'
                self.fields['status'].required = True
                if self.data:
                    self.data = self.data.copy()
                    self.data['status'] = 'noch nicht bearbeitet'

        # Style inputs
        for field_name in ['employee', 'plan_position_number']:
            if field_name in self.fields:
                self.fields[field_name].widget.attrs.update({'class': 'form-control'})
                self.fields[field_name].required = True

        if 'valid_from' in self.fields:
            self.fields['valid_from'].widget.attrs.update({'class': 'form-control'})

        if 'comment' in self.fields:
            self.fields['comment'].widget.attrs.update({'class': 'form-control'})

        if 'limitation_reason' in self.fields:
            self.fields['limitation_reason'].widget.attrs.update({'class': 'form-control'})

        # Employee dropdown (all employees)
        if 'employee' in self.fields:
            self.fields['employee'].queryset = Employee.objects.order_by('last_name', 'first_name')
            self.fields['employee'].empty_label = "— Select employee —"

        # is_limited default True for new limited contracts
        if 'is_limited' in self.fields and self.is_creation:
            self.fields['is_limited'].initial = True
            self.fields['is_limited'].label = ""  # label rendered manually in template for nicer checkbox UX
        if 'status' in self.fields:
            self.fields['status'].choices = PERSONNEL_STATUSES
            if self.is_creation:
                self.fields['status'].widget = forms.HiddenInput()
                self.fields['status'].initial = 'not_yet_processed'
                self.fields['status'].required = True

        # Styling
        for fname in ['plan_position_number', 'priority', 'assignee', 'employee']:
            if fname in self.fields:
                self.fields[fname].widget.attrs.update({'class': 'form-control'})

        for fname in ['valid_from', 'due_date', 'comment', 'limitation_reason']:
            if fname in self.fields:
                self.fields[fname].widget.attrs.update({'class': 'form-control'})

        if 'employee' in self.fields:
            self.fields['employee'].queryset = Employee.objects.order_by('last_name', 'first_name')
        if 'assignee' in self.fields:
            # Nur Mitglieder der Gruppe "Personnel Fulfiller" dürfen zugewiesen werden
            fulfullers = Employee.objects.filter(user__groups__name=GroupNames.PERSONNEL_FULFILLER)
            self.fields['assignee'].queryset = fulfullers.order_by('last_name', 'first_name')
            self.fields['assignee'].empty_label = "— Unassigned —"


class GenericTextTaskForm(forms.ModelForm):
    """
    Form for General Requests (generic_text tasks).
    Keeps Recipient (addressed to) and removes Assignee (we use Recipient instead).
    """
    class Meta:
        model = GenericTextTask
        fields = ['title', 'recipient', 'priority', 'due_date', 'status', 'comment']
        widgets = {
            'comment': forms.Textarea(attrs={
                'rows': 12,
                'placeholder': 'Describe your request in detail...',
                'style': 'min-height: 200px;'
            }),
            'due_date': forms.DateInput(attrs={
                'type': 'text',
                'class': 'form-control date-picker',
                'placeholder': 'TT.MM.JJJJ'
            }),
            'status': forms.RadioSelect(attrs={'class': 'status-radio'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.is_creation = kwargs.pop('is_creation', False)
        super().__init__(*args, **kwargs)

        # Status handling for generic tasks (new English statuses)
        if 'status' in self.fields:
            self.fields['status'].choices = GENERIC_STATUSES

            if self.is_creation:
                self.fields['status'].widget = forms.HiddenInput()
                self.fields['status'].initial = 'seen'
                self.fields['status'].required = True
                if self.data:
                    self.data = self.data.copy()
                    self.data['status'] = 'seen'

        # Style fields
        for field_name in ['title', 'priority', 'recipient']:
            if field_name in self.fields:
                self.fields[field_name].widget.attrs.update({'class': 'form-control'})

        if 'due_date' in self.fields:
            self.fields['due_date'].widget.attrs.update({'class': 'form-control'})

        if 'comment' in self.fields:
            self.fields['comment'].widget.attrs.update({'class': 'form-control'})

        if 'recipient' in self.fields:
            self.fields['recipient'].queryset = Employee.objects.order_by('last_name', 'first_name')
            self.fields['recipient'].empty_label = "— Please select a recipient —"
            self.fields['recipient'].required = True

            # Custom label without employee number (Personnelnummer)
            def recipient_label_from_instance(employee):
                prefix = f"{employee.prefix} " if employee.prefix else ""
                return f"{prefix}{employee.first_name} {employee.last_name}"

            self.fields['recipient'].label_from_instance = recipient_label_from_instance


# =============================================================================
# Standard Purchase Items (Catalog)
# =============================================================================

from django.core.exceptions import ValidationError
from PIL import Image as PILImage
import io

MAX_STANDARD_IMAGE_SIZE_MB = 5
THUMBNAIL_SIZE = (120, 120)


class StandardPurchaseItemForm(forms.ModelForm):
    """Form for creating/editing StandardPurchaseItem with optional image upload."""

    image = forms.FileField(
        label="Product Image (optional)",
        required=False,
        widget=forms.ClearableFileInput(attrs={'class': 'form-control'}),
        help_text=f"Max {MAX_STANDARD_IMAGE_SIZE_MB} MB. Will be shown as small thumbnail in selection lists."
    )

    class Meta:
        model = StandardPurchaseItem
        fields = [
            'supplier', 'product_name', 'product_description',
            'link_to_product', 'order_number', 'unit_price'
        ]
        widgets = {
            'product_description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'link_to_product': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            if field != 'image' and hasattr(self.fields[field].widget, 'attrs'):
                self.fields[field].widget.attrs.setdefault('class', 'form-control')

        # Make some fields required for usability
        self.fields['supplier'].required = True
        self.fields['product_name'].required = True
        self.fields['unit_price'].required = True

    def clean_image(self):
        uploaded_file = self.cleaned_data.get('image')
        if not uploaded_file:
            return None

        # Size check
        max_bytes = MAX_STANDARD_IMAGE_SIZE_MB * 1024 * 1024
        if uploaded_file.size > max_bytes:
            raise ValidationError(f"Image too large. Maximum allowed size is {MAX_STANDARD_IMAGE_SIZE_MB} MB.")

        # Basic image validation + thumbnail generation
        try:
            img = PILImage.open(uploaded_file)
            img.verify()  # Check it's a valid image
            uploaded_file.seek(0)  # Reset after verify

            # Create thumbnail
            img = PILImage.open(uploaded_file)
            img.thumbnail(THUMBNAIL_SIZE, PILImage.LANCZOS)

            # Convert to RGB if necessary (for PNG with alpha etc.)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            thumb_io = io.BytesIO()
            img.save(thumb_io, format='JPEG', quality=85, optimize=True)
            thumb_io.seek(0)

            self.cleaned_data['thumbnail_data'] = thumb_io.getvalue()
            self.cleaned_data['image_content_type'] = uploaded_file.content_type or 'image/jpeg'

            # Reset original file pointer for later reading
            uploaded_file.seek(0)
            return uploaded_file

        except Exception as e:
            raise ValidationError(f"Invalid image file: {str(e)}")

    def save(self, commit=True):
        instance = super().save(commit=False)

        uploaded_file = self.cleaned_data.get('image')
        if uploaded_file:
            instance.image = uploaded_file.read()
            instance.image_filename = uploaded_file.name
            instance.image_content_type = self.cleaned_data.get('image_content_type', 'image/jpeg')
            instance.thumbnail = self.cleaned_data.get('thumbnail_data')

        if commit:
            instance.save()
        return instance