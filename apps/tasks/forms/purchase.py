"""Purchase order task and line-item inline formset forms."""
from decimal import Decimal

from django import forms
from django.forms.models import BaseInlineFormSet, inlineformset_factory

from apps.finances.models import WBSElement
from apps.tasks.form_validation import (
    require_non_empty_text,
    strip_cleaned_text,
    validate_pdf_upload,
    validate_positive_decimal,
    validate_positive_integer,
    validate_url_field,
)
from apps.tasks.forms.common import add_initial_message_field
from apps.tasks.models import PURCHASE_STATUSES, PurchaseItem, PurchaseOrderTask
from apps.tasks.utils import procurement_approver_employees
from apps.tasks.workflow_config import creator_has_coordinator_fallback



# ---------------------------------------------------------------------------
# Purchase order task (header form)
# ---------------------------------------------------------------------------
class PurchaseOrderTaskForm(forms.ModelForm):
    """
    Header form for purchase orders.

    Field visibility depends on role and whether the form is used for creation
    or detail editing. See __init__ and _has_po_coordination_access().
    """
    class Meta:
        model = PurchaseOrderTask
        fields = [
            'supplier', 'wbs_element', 'priority', 'assignee', 'status',
            'at_beleg_nummer', 'quote_file',
        ]
        widgets = {
            'status': forms.RadioSelect(attrs={'class': 'status-radio'}),
            'quote_file': forms.ClearableFileInput(attrs={'accept': '.pdf,application/pdf'}),
        }

    def _has_po_coordination_access(self):
        """
        True for procurement coordinators and equivalent users.

        Grants full PO coordination UI (assignee picker, WBS on detail, etc.).
        On existing tasks, task creators may also qualify via
        creator_has_coordinator_fallback when no coordinator is assigned yet.
        Fulfillers and plain creators without fallback see a reduced field set.
        """
        user = self.user
        if not user:
            return False
        if (
            user.is_superuser
            or user.has_perm('tasks.view_all_purchase_orders')
            or user.has_perm('tasks.change_wbs_on_purchase_order')
        ):
            return True
        if not self.is_creation and self.instance and self.instance.pk:
            return creator_has_coordinator_fallback(user, self.instance)
        return False

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.is_creation = kwargs.pop('is_creation', False)
        self.quote_order_mode = kwargs.pop('quote_order_mode', False)
        super().__init__(*args, **kwargs)

        has_coordination_access = self._has_po_coordination_access()
        is_quote_order = bool(
            self.quote_order_mode
            or (self.instance and self.instance.pk and self.instance.is_quote_order)
        )

        if self.is_creation and self.quote_order_mode:
            for field_name in (
                'supplier', 'wbs_element', 'priority', 'assignee',
                'status', 'at_beleg_nummer',
            ):
                if field_name in self.fields:
                    self.fields[field_name].widget = forms.HiddenInput()
                    self.fields[field_name].required = False
            if 'supplier' in self.fields:
                self.fields['supplier'].initial = ''
            if 'status' in self.fields:
                self.fields['status'].initial = 'not_yet_processed'
            if 'quote_file' in self.fields:
                self.fields['quote_file'].required = True
                self.fields['quote_file'].label = 'Quote'
        elif not self.is_creation:
            self.fields.pop('quote_file', None)
        elif 'quote_file' in self.fields:
            self.fields['quote_file'].required = False
            self.fields['quote_file'].label = 'Quote (optional)'

        # --- Supplier ---
        # Coordinators on detail: supplier is fixed (hidden, value preserved),
        # except for quote orders where the coordinator may enter the supplier.
        # Creators and fulfillers: visible text input; required on standard creation.
        if 'supplier' in self.fields:
            if not self.is_creation and has_coordination_access and not is_quote_order:
                self.fields['supplier'].widget = forms.HiddenInput()
                if self.instance and self.instance.pk:
                    self.fields['supplier'].initial = self.instance.supplier
                self.fields['supplier'].required = True
            elif not self.is_creation and has_coordination_access and is_quote_order:
                self.fields['supplier'].widget.attrs.update({'class': 'form-control'})
                self.fields['supplier'].required = True
            elif not (self.is_creation and self.quote_order_mode):
                self.fields['supplier'].widget.attrs.update({'class': 'form-control'})
                if self.is_creation:
                    self.fields['supplier'].required = True

        if self.is_creation and self.quote_order_mode:
            return

        # --- Priority (optional on creation) ---
        if 'priority' in self.fields:
            self.fields['priority'].required = False
            self.fields['priority'].widget.attrs.update({'class': 'form-control'})

        if self.is_creation:
            add_initial_message_field(
                self,
                placeholder='Optional message for coordinators…',
            )

        # --- Assignee ---
        # Coordinator / creator-with-fallback: dropdown of procurement approvers.
        # Fulfiller and plain creator: hidden; stays unassigned until coordinator sets it.
        if 'assignee' in self.fields:
            if self.user and not has_coordination_access:
                self.fields['assignee'].widget = forms.HiddenInput()
                self.fields['assignee'].required = False
                if self.is_creation:
                    self.fields['assignee'].initial = None  # stays unassigned until coordinator/approver sets it

            else:
                # Coordinators select assignee from procurement approvers
                self.fields['assignee'].queryset = procurement_approver_employees()
                self.fields['assignee'].widget.attrs.update({'class': 'form-control'})
                self.fields['assignee'].empty_label = "— Select assignee —"
                if self.is_creation:
                    self.fields['assignee'].required = True

        # --- AT document number (at_beleg_nummer) ---
        # Hidden on creation. On detail: visible for coordinators and users with
        # manage_standard_order; hidden for fulfillers without that permission.
        if 'at_beleg_nummer' in self.fields:
            if self.is_creation:
                self.fields['at_beleg_nummer'].widget = forms.HiddenInput()
                self.fields['at_beleg_nummer'].required = False
            elif self.user and not (
                has_coordination_access or
                self.user.has_perm('tasks.manage_standard_order')
            ):
                self.fields['at_beleg_nummer'].widget = forms.HiddenInput()
                self.fields['at_beleg_nummer'].required = False
            else:
                self.fields['at_beleg_nummer'].widget.attrs.update({'class': 'form-control'})

        # --- Status ---
        # Creation: forced to not_yet_processed (hidden). Detail: radio buttons
        # remain available (rendered manually in the template).
        if 'status' in self.fields:
            self.fields['status'].choices = PURCHASE_STATUSES

            if self.is_creation:
                self.fields['status'].widget = forms.HiddenInput()
                self.fields['status'].initial = 'not_yet_processed'
                self.fields['status'].required = True
                if self.data:
                    self.data = self.data.copy()
                    self.data['status'] = 'not_yet_processed'

        # --- WBS element ---
        # Coordinators on detail: active PSPs with material costs (.1) enabled.
        # Creation: hidden (coordinator assigns WBS after submission).
        if 'wbs_element' in self.fields:
            self.fields['wbs_element'].queryset = WBSElement.objects.active().filter(
                has_material_costs=True,
            ).order_by('wbs_code')
            self.fields['wbs_element'].empty_label = "---------"

            if not self.is_creation and has_coordination_access:
                pass
            elif self.is_creation:
                self.fields['wbs_element'].widget = forms.HiddenInput()
                self.fields['wbs_element'].required = False

    def clean(self):
        cleaned_data = super().clean()
        wbs_element = cleaned_data.get('wbs_element')
        quote_file = cleaned_data.get('quote_file')

        if self.is_creation and self.quote_order_mode:
            cleaned_data['supplier'] = ''
            cleaned_data['status'] = 'not_yet_processed'
            validate_pdf_upload(self, quote_file, 'quote_file', required=True)
            return cleaned_data

        if self.is_creation and quote_file:
            validate_pdf_upload(self, quote_file, 'quote_file', required=False)

        # Supplier is required on standard orders (including coordinator detail saves).
        if not (self.is_creation and self.quote_order_mode):
            require_non_empty_text(self, cleaned_data, 'supplier')

        # Coordinators creating on behalf of others must pick an assignee.
        if self.is_creation and self._has_po_coordination_access() and not self.quote_order_mode:
            if not cleaned_data.get('assignee'):
                self.add_error('assignee', 'Please select an assignee.')

        # Coordinators editing an existing PO must set WBS before fulfillment proceeds.
        if not self.is_creation and self._has_po_coordination_access():
            if not wbs_element:
                self.add_error('wbs_element', "WBS Element is required for users with full purchase order access.")

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.is_creation and self.quote_order_mode:
            instance.is_quote_order = True
            instance.supplier = ''
        if commit:
            instance.save()
        return instance


class PurchaseOrderQuoteReplaceForm(forms.ModelForm):
    """Allow the task creator to replace the quote PDF on an existing order."""

    class Meta:
        model = PurchaseOrderTask
        fields = ['quote_file']
        widgets = {
            'quote_file': forms.ClearableFileInput(attrs={'accept': '.pdf,application/pdf'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['quote_file'].label = 'Quote'
        self.fields['quote_file'].required = True

    def clean_quote_file(self):
        quote_file = self.cleaned_data.get('quote_file')
        validate_pdf_upload(self, quote_file, 'quote_file', required=True)
        return quote_file


# ---------------------------------------------------------------------------
# Purchase order line items (inline formset)
# ---------------------------------------------------------------------------
class PurchaseItemForm(forms.ModelForm):
    """
    Single row in the purchase-order item inline formset.

    Uses INTERNAL_FIELDS so Django-managed keys (id, FK, DELETE) never block
    empty optional rows. Blank rows are skipped in full_clean and clean.
    """
    class Meta:
        model = PurchaseItem
        fields = ['product_name', 'product_description', 'link_to_product', 'order_number', 'unit_price', 'quantity']
        widgets = {
            'product_description': forms.Textarea(attrs={'rows': 2}),
            'link_to_product': forms.URLInput(attrs={'placeholder': 'https://...'}),
            'order_number': forms.TextInput(attrs={'placeholder': 'z.B. 4711'}),
            'quantity': forms.NumberInput(attrs={'min': 1, 'step': 1}),
        }

    OPTIONAL_FIELDS = {'product_description'}
    INTERNAL_FIELDS = {'id', 'purchase_task', 'DELETE'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.empty_permitted = True
        # INTERNAL_FIELDS are never user-facing requirements on empty placeholder rows.
        for field_name, field in self.fields.items():
            if field_name in self.INTERNAL_FIELDS:
                field.required = False
            else:
                field.required = field_name not in self.OPTIONAL_FIELDS
            if field_name == 'order_number':
                field.widget.attrs['placeholder'] = 'z.B. 4711'
            if field_name == 'quantity':
                field.widget.attrs['min'] = 1
                field.widget.attrs['step'] = 1

    def _is_empty_row(self, cleaned_data=None):
        """True when the user left this inline row blank (ignoring INTERNAL_FIELDS)."""
        if cleaned_data is not None:
            if not cleaned_data:
                return True
            for field_name, value in cleaned_data.items():
                if field_name in self.OPTIONAL_FIELDS or field_name in self.INTERNAL_FIELDS:
                    continue
                if value not in (None, ''):
                    return False
            return True

        if not self.is_bound:
            return False
        for field_name in self.fields:
            if field_name in self.OPTIONAL_FIELDS or field_name in self.INTERNAL_FIELDS:
                continue
            if self.data.get(self.add_prefix(field_name), '') not in ('', None):
                return False
        return True

    def full_clean(self):
        # Skip validation entirely for blank inline rows (extra formset slot).
        if self._is_empty_row():
            self.cleaned_data = {}
            self._errors = {}
            return
        super().full_clean()

    def clean(self):
        cleaned_data = super().clean()
        if self._is_empty_row(cleaned_data):
            return cleaned_data

        # Non-empty rows: trim text and validate all visible fields.
        strip_cleaned_text(
            cleaned_data,
            'product_name', 'product_description', 'link_to_product', 'order_number',
        )
        for field_name in self.fields:
            if field_name in self.OPTIONAL_FIELDS or field_name in self.INTERNAL_FIELDS:
                continue
            if cleaned_data.get(field_name) in (None, ''):
                self.add_error(field_name, 'This field is required.')

        validate_url_field(self, cleaned_data, 'link_to_product', required=True)
        validate_positive_decimal(
            self,
            cleaned_data,
            'unit_price',
            min_value=Decimal('0'),
            allow_zero=False,
            message='Unit price must be greater than 0.',
        )
        validate_positive_integer(
            self,
            cleaned_data,
            'quantity',
            min_value=1,
            message='Quantity must be at least 1.',
        )
        return cleaned_data


class BasePurchaseItemFormSet(BaseInlineFormSet):
    """Inline formset wrapper; requires at least one non-empty, non-deleted item."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for form in self.forms:
            form.empty_permitted = True

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        active_forms = [
            form for form in self.forms
            if form.cleaned_data and not form.cleaned_data.get('DELETE', False)
            and not form._is_empty_row(form.cleaned_data)
        ]
        if not active_forms:
            raise forms.ValidationError('At least one purchase item is required.')


PurchaseItemFormSet = inlineformset_factory(
    PurchaseOrderTask,
    PurchaseItem,
    form=PurchaseItemForm,
    formset=BasePurchaseItemFormSet,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True,
    fields=(
        'product_name', 'product_description', 'link_to_product',
        'order_number', 'unit_price', 'quantity',
    ),
)
