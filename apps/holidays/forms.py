from django import forms

from apps.holidays.models import HolidayCustomDay, HolidayProfile, HolidayYearEntitlement


class HolidayProfileForm(forms.ModelForm):
    class Meta:
        model = HolidayProfile
        fields = [
            'works_monday', 'works_tuesday', 'works_wednesday',
            'works_thursday', 'works_friday',
            'share_with_institute', 'signature',
        ]
        widgets = {
            'share_with_institute': forms.CheckboxInput(),
        }


class HolidayEntitlementForm(forms.Form):
    this_year = forms.DecimalField(
        max_digits=6, decimal_places=1, min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5'}),
    )
    next_year = forms.DecimalField(
        max_digits=6, decimal_places=1, min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5'}),
    )


class HolidayCustomDayForm(forms.ModelForm):
    year = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
    )
    day = forms.DateField(
        required=False,
        input_formats=['%d.%m.%Y', '%Y-%m-%d'],
        widget=forms.DateInput(attrs={'class': 'form-control date-picker', 'placeholder': 'DD.MM.YYYY'}),
    )

    class Meta:
        model = HolidayCustomDay
        fields = ['year', 'day', 'name', 'mode']
        widgets = {
            'year': forms.NumberInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'mode': forms.Select(attrs={'class': 'form-select'}),
        }

    def has_changed(self):
        data = self.data if hasattr(self, 'data') and self.data is not None else {}
        prefix = self.prefix + '-' if self.prefix else ''
        return bool(
            (data.get(prefix + 'year') or '').strip()
            or (data.get(prefix + 'day') or '').strip()
            or (data.get(prefix + 'name') or '').strip()
        )

    def clean(self):
        cleaned = super().clean()
        if self.cleaned_data.get('DELETE'):
            return cleaned
        year = cleaned.get('year')
        day = cleaned.get('day')
        name = cleaned.get('name')
        if not year and not day and not name:
            return cleaned
        if not day or not name:
            raise forms.ValidationError('Year, date and name are required for a custom day.')
        cleaned['year'] = day.year
        return cleaned


HolidayCustomDayFormSet = forms.modelformset_factory(
    HolidayCustomDay,
    form=HolidayCustomDayForm,
    extra=2,
    can_delete=True,
)


def save_entitlements(employee, this_year_value, next_year_value):
    from datetime import date
    year = date.today().year
    for target_year, value in ((year, this_year_value), (year + 1, next_year_value)):
        HolidayYearEntitlement.objects.update_or_create(
            employee=employee,
            year=target_year,
            defaults={'days': value},
        )
