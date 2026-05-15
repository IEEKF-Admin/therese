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
    PURCHASE_STATUSES,
)
from apps.finances.models import WBSElement
from apps.hr.models import Employee


class PurchaseOrderTaskForm(forms.ModelForm):
    """
    Formular für Purchase Orders mit Radio-Buttons für Status.
    """
    class Meta:
        model = PurchaseOrderTask
        fields = ['supplier', 'wbs_element', 'priority', 'assignee', 'status', 'comment']
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
            if not self.is_creation and self.user and self.user.groups.filter(name='Procurement Coordinator').exists():
                self.fields['supplier'].widget = forms.HiddenInput()
                if self.instance and self.instance.pk:
                    self.fields['supplier'].initial = self.instance.supplier
                self.fields['supplier'].required = True
            else:
                self.fields['supplier'].widget.attrs.update({'class': 'form-control'})

        # ==================== Assignee (NEU + WICHTIG) ====================
        if 'assignee' in self.fields:
            # Coordinators dürfen Assignee nicht ändern → Hidden + Wert erhalten
            if not self.is_creation and self.user and self.user.groups.filter(name='Procurement Coordinator').exists():
                self.fields['assignee'].widget = forms.HiddenInput()
                if self.instance and self.instance.assignee:
                    self.fields['assignee'].initial = self.instance.assignee.pk
                self.fields['assignee'].required = False
            else:
                # Normale Nutzer (Requester) können auswählen (ohne Coordinators)
                coordinators = Employee.objects.filter(user__groups__name='Procurement Coordinator')
                self.fields['assignee'].queryset = Employee.objects.exclude(
                    id__in=coordinators.values_list('id', flat=True)
                ).order_by('last_name', 'first_name')
                self.fields['assignee'].widget.attrs.update({'class': 'form-control'})

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

            if not self.is_creation and self.user and self.user.groups.filter(name='Procurement Coordinator').exists():
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
        fields = ['product_name', 'product_description', 'link_to_product', 'unit_price', 'quantity']
        widgets = {
            'product_description': forms.Textarea(attrs={'rows': 2}),
            'link_to_product': forms.URLInput(attrs={'placeholder': 'https://...'}),
        }


class PersonnelReallocationTaskForm(forms.ModelForm):
    class Meta:
        model = PersonnelReallocationTask
        fields = ['title', 'employee', 'target_wbs', 'valid_from', 'valid_until',
                  'plan_position_number', 'comment']


class PersonnelContractExtensionTaskForm(forms.ModelForm):
    class Meta:
        model = PersonnelContractExtensionTask
        fields = ['title', 'employee', 'plan_position_number', 'valid_from',
                  'is_limited', 'limitation_reason', 'comment']


class GenericTextTaskForm(forms.ModelForm):
    class Meta:
        model = GenericTextTask
        fields = ['title', 'recipient', 'comment']