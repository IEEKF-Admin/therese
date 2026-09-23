from django import forms

from apps.holidays.models import HolidayCustomDay, HolidayProfile, HolidayYearEntitlement


class HolidayProfileForm(forms.ModelForm):
    class Meta:
        model = HolidayProfile
        fields = [
            'works_monday', 'works_tuesday', 'works_wednesday',
            'works_thursday', 'works_friday',
            'share_with_institute',
        ]
        widgets = {
            'share_with_institute': forms.CheckboxInput(),
        }


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


def _parse_entitlement_decimal(raw):
    from decimal import Decimal, InvalidOperation
    from apps.tasks.form_validation import parse_loose_decimal

    text = str(raw or '').strip()
    if not text:
        return Decimal('0')
    try:
        value = Decimal(str(parse_loose_decimal(text)))
    except (InvalidOperation, ValueError, TypeError):
        raise forms.ValidationError('Enter a valid number of days.')
    if value < 0:
        raise forms.ValidationError('Days cannot be negative.')
    return value


def save_entitlements_from_post(employee, post):
    from datetime import date as date_cls

    from apps.holidays.services import suggested_entitlement

    today_year = date_cls.today().year
    allowed = {today_year, today_year + 1}
    years = post.getlist('ent_year')
    carryovers = post.getlist('ent_carryover')
    specials = post.getlist('ent_special')
    by_year = {}
    for index, year_raw in enumerate(years):
        year_text = str(year_raw or '').strip()
        if not year_text:
            continue
        try:
            year = int(year_text)
        except (TypeError, ValueError):
            raise forms.ValidationError('Year must be a number.')
        if year not in allowed or year in by_year:
            continue
        by_year[year] = {
            'carryover': _parse_entitlement_decimal(carryovers[index] if index < len(carryovers) else '0'),
            'special_leave': _parse_entitlement_decimal(specials[index] if index < len(specials) else '0'),
        }
    for year in sorted(allowed):
        values = by_year.get(year, {})
        existing = HolidayYearEntitlement.objects.filter(employee=employee, year=year).first()
        HolidayYearEntitlement.objects.update_or_create(
            employee=employee,
            year=year,
            defaults={
                'holidays': suggested_entitlement(employee, year),
                'carryover': values.get(
                    'carryover',
                    existing.carryover if existing else 0,
                ),
                'special_leave': values.get(
                    'special_leave',
                    existing.special_leave if existing else 0,
                ),
            },
        )
