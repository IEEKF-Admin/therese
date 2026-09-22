from django import forms

from apps.hr.models import Employee
from apps.inventory.models import InventoryItem, InventoryItemType
from apps.tasks.form_validation import DecimalCommaField


class InventoryItemForm(forms.ModelForm):
    purchase_date = forms.DateField(
        required=False,
        input_formats=['%d.%m.%Y', '%Y-%m-%d'],
        widget=forms.DateInput(attrs={
            'type': 'text',
            'class': 'form-control date-picker',
            'placeholder': 'TT.MM.JJJJ',
        }),
        label='Purchase date',
    )
    purchase_price = DecimalCommaField(
        required=False,
        max_digits=12,
        decimal_places=2,
        min_value=0,
        label='Purchase price',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'inputmode': 'decimal',
            'placeholder': 'e.g. 29,90',
        }),
    )

    class Meta:
        model = InventoryItem
        fields = [
            'item_type', 'name', 'purchase_date', 'purchase_price',
            'description', 'current_holder',
        ]
        widgets = {
            'item_type': forms.Select(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'current_holder': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['item_type'].queryset = InventoryItemType.objects.order_by('name')
        self.fields['item_type'].empty_label = '— Select type —'
        self.fields['current_holder'].queryset = Employee.objects.visible().order_by(
            'last_name', 'first_name',
        )
        self.fields['current_holder'].required = False
        self.fields['current_holder'].empty_label = '— In stock —'
        self.fields['name'].required = True
        if self.instance and self.instance.pk:
            self.fields['item_type'].disabled = True
