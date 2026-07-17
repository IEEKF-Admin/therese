"""
apps/hr/forms.py
Project: THERESE - Transparent HR Employee Resource Evaluation System Enhanced

Realized functionalities in this file:
- EmployeeForm with cascading dropdowns (Building → Room → PhoneNumber)
- Dynamic queryset filtering for Room and PhoneNumber based on POST data or instance
- ModelChoiceField handling for phone_number with preserved choice for validation
- Inline form support for related models (Contract, FundingAllocation, etc.)
- clean_room() and clean() with cross-field validation

Cascading dropdown logic:
  Building → filters Room queryset by selected building
  Room → filters PhoneNumber queryset by selected room
  On edit, querysets and initial values are set from the instance's relations.
  On POST (validation errors), querysets follow submitted building/room values.

Constraints:
- Must work for both CreateView and UpdateView
- Must preserve all existing form fields and validation
- Phone pre-filling on edit must work reliably
"""

from django import forms
from django.forms.models import inlineformset_factory

from .models import (
    Employee, Building, Room, PhoneNumber, Contract,
    FundingAllocation, SalarySupplement, Workgroup
)
from .workgroup_groups import sync_auth_group_for_workgroup
from apps.finances.funding_sources import FundingSourceFormMixin
from apps.finances.models import PayScale


# Explicit fields only — never bind `user` via mass assignment.
EMPLOYEE_MANAGE_FIELDS = [
    'employee_number', 'prefix', 'first_name', 'last_name', 'gender',
    'date_of_birth', 'country_of_origin', 'place_of_birth',
    'email_professional', 'email_private', 'google_account', 'private_phone_number',
    'room', 'phone_number', 'street', 'house_number', 'postal_code', 'city', 'country',
    'website', 'job',
    # monthly_salary / cost_center / scan_of_contract / profile_picture intentionally omitted
]

EMPLOYEE_PROFILE_FIELDS = [
    'email_professional', 'email_private', 'google_account', 'private_phone_number',
    'room', 'phone_number', 'street', 'house_number', 'postal_code', 'city', 'country',
    'website',
]


class EmployeeForm(forms.ModelForm):
    building = forms.ModelChoiceField(
        queryset=Building.objects.all().order_by('number'),
        required=False,
        empty_label="— Select Building —",
        label="Building"
    )
    phone_number = forms.ModelChoiceField(
        queryset=PhoneNumber.objects.none(),
        required=False,
        empty_label="— Select Room first —",
        label="Office Phone",
        to_field_name='phone_number'
    )

    class Meta:
        model = Employee
        fields = EMPLOYEE_MANAGE_FIELDS
        widgets = {
            'date_of_birth': forms.DateInput(attrs={
                'type': 'text',
                'class': 'form-control date-picker',
                'placeholder': 'TT.MM.JJJJ'
            }),
            'room': forms.Select(attrs={'class': 'room-select form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = getattr(self, 'instance', None)

        # Building: all buildings; on edit, pre-select the employee's building
        building_field = self.fields['building']
        building_field.widget.attrs.update({'class': 'building-select form-control', 'id': 'id_building'})
        if instance and instance.room and instance.room.building:
            building_field.initial = instance.room.building.pk

        # Room: cascade from building — empty until a building is chosen (create),
        # or filtered to the instance building with initial room on edit
        room_field = self.fields['room']
        room_field.empty_label = "— Select Building first —"
        room_field.widget.attrs.update({'class': 'room-select form-control', 'id': 'id_room'})

        if self.is_bound and self.data.get('building'):
            # POST with validation errors: keep rooms for the submitted building
            room_field.queryset = Room.objects.filter(building_id=self.data['building']).order_by('room_number')
        elif instance and instance.room:
            # Edit mode: rooms for the employee's building, pre-select current room
            room_field.queryset = Room.objects.filter(building=instance.room.building).order_by('room_number')
            room_field.initial = instance.room.pk
        else:
            # Create mode: no building selected yet
            room_field.queryset = Room.objects.none()

        # Phone: cascade from room — empty until a room is chosen
        phone_field = self.fields['phone_number']
        phone_field.widget.attrs.update({'class': 'phone-select form-control', 'id': 'id_phone_number'})

        # Preserve phone from POST (re-render after error) or from instance (edit)
        phone_to_preserve = None
        if self.is_bound and self.data.get('phone_number'):
            phone_to_preserve = self.data.get('phone_number')
        elif instance and instance.phone_number:
            phone_to_preserve = instance.phone_number

        if self.is_bound and self.data.get('room'):
            # POST: phones for the submitted room
            phone_field.queryset = PhoneNumber.objects.filter(room_id=self.data['room'])
            if phone_to_preserve:
                phone_field.initial = phone_to_preserve
        elif instance and instance.phone_number:
            # Edit mode: include the employee's phone and pre-select it
            phone_field.queryset = PhoneNumber.objects.filter(phone_number=instance.phone_number)
            phone_field.initial = instance.phone_number
        else:
            # Create mode: no room selected yet
            phone_field.queryset = PhoneNumber.objects.none()

        # Ensure preserved phone stays in queryset when room filter would exclude it
        if phone_to_preserve and phone_field.queryset is not None:
            if not phone_field.queryset.filter(phone_number=phone_to_preserve).exists():
                preserved_qs = PhoneNumber.objects.filter(phone_number=phone_to_preserve)
                phone_field.queryset = (phone_field.queryset | preserved_qs).distinct()

        # Apply form-control styling to all fields
        for field in self.fields.values():
            if 'form-control' not in field.widget.attrs.get('class', ''):
                field.widget.attrs['class'] = 'form-control'

    def clean_room(self):
        room = self.cleaned_data.get('room')
        return room

    def clean(self):
        cleaned_data = super().clean()
        room = cleaned_data.get('room')
        building = cleaned_data.get('building')
        if room and building and room.building != building:
            self.add_error('room', "Room does not belong to selected building")
        return cleaned_data

    def clean_phone_number(self):
        phone = self.cleaned_data.get('phone_number')
        if phone is None:
            if self.instance and self.instance.pk and self.instance.phone_number:
                return self.instance.phone_number
            return ''
        # Ensure it's a string
        return str(phone) if phone else ''


class EmployeeProfileForm(EmployeeForm):
    """Self-service profile: restricted field set, no user/number rebinding."""

    class Meta(EmployeeForm.Meta):
        fields = EMPLOYEE_PROFILE_FIELDS


# = INLINE FORMS =
class ContractForm(forms.ModelForm):
    class Meta:
        model = Contract
        fields = [
            'pay_scale_group', 'experience_level', 'monthly_salary',
            'job_number', 'plan_position_number',
            'weekly_hours', 'valid_from', 'valid_until', 'comments',
        ]
        widgets = {
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
            'comments': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'monthly_salary': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Only current (latest effective_as_of) PayScales
        current = PayScale.get_current()

        # Distinct groups from current payscales
        groups = (
            current.values_list('pay_scale_group', flat=True)
            .distinct()
            .order_by('pay_scale_group')
        )
        pay_scale_choices = [('', '— Select Pay Scale Group —')] + [(g, g) for g in groups]

        # Experience levels (will be filtered by JS, but we provide a base set)
        level_choices = [('', '— Select Group first —')] + [(str(i), str(i)) for i in range(1, 7)]

        # Force proper dropdown widgets (ChoiceField + Select) so they always render as <select>
        self.fields['pay_scale_group'] = forms.ChoiceField(
            choices=pay_scale_choices,
            required=False,
            widget=forms.Select(attrs={'class': 'form-control'})
        )
        self.fields['experience_level'] = forms.ChoiceField(
            choices=level_choices,
            required=False,
            widget=forms.Select(attrs={'class': 'form-control'})
        )

        self.fields['job_number'].label = 'Job Number'
        self.fields['plan_position_number'].label = 'Plan Position Number'
        self.fields['monthly_salary'].label = 'Monthly Salary'
        self.fields['monthly_salary'].required = False
        self.fields['monthly_salary'].widget.attrs.update({
            'class': 'form-control contract-monthly-salary',
            'step': '0.01',
            'min': '0',
            'data-contract-monthly-salary': 'true',
        })

        # When payscale is set, show TV-L salary as read-only (enforced again in clean).
        instance = getattr(self, 'instance', None)
        if instance and instance.pk and instance.pay_scale_group and instance.experience_level is not None:
            salary = instance.get_monthly_salary()
            if salary is not None:
                self.fields['monthly_salary'].initial = salary
            self.fields['monthly_salary'].widget.attrs['readonly'] = True
            self.fields['monthly_salary'].widget.attrs['class'] = (
                self.fields['monthly_salary'].widget.attrs.get('class', '') + ' form-readonly'
            ).strip()

        # Re-apply form-control to any remaining fields
        for field in self.fields.values():
            if 'form-control' not in field.widget.attrs.get('class', ''):
                field.widget.attrs['class'] = 'form-control'

    def clean_experience_level(self):
        value = self.cleaned_data.get('experience_level')
        if value in (None, ''):
            return None
        return int(value)

    def clean_monthly_salary(self):
        value = self.cleaned_data.get('monthly_salary')
        if value in (None, ''):
            return None
        return value

    def clean(self):
        cleaned_data = super().clean()
        pay_scale_group = cleaned_data.get('pay_scale_group')
        experience_level = cleaned_data.get('experience_level')
        has_group = bool(pay_scale_group)
        has_level = experience_level is not None
        if has_group != has_level:
            message = 'Please select both pay scale group and experience level, or leave both empty.'
            if not has_group:
                self.add_error('pay_scale_group', message)
            if not has_level:
                self.add_error('experience_level', message)
        elif has_group and has_level:
            salary = (
                PayScale.get_current()
                .filter(
                    pay_scale_group=pay_scale_group,
                    experience_level=experience_level,
                )
                .values_list('monthly_salary', flat=True)
                .first()
            )
            if salary is not None:
                cleaned_data['monthly_salary'] = salary
        return cleaned_data


class FundingAllocationForm(FundingSourceFormMixin, forms.ModelForm):
    class Meta:
        model = FundingAllocation
        fields = ['weekly_hours_allocated', 'start_date', 'end_date', 'comments']
        widgets = {
            'start_date': forms.DateInput(attrs={
                'type': 'text',
                'class': 'form-control date-picker',
                'placeholder': 'TT.MM.JJJJ'
            }),
            'end_date': forms.DateInput(attrs={
                'type': 'text',
                'class': 'form-control date-picker',
                'placeholder': 'TT.MM.JJJJ'
            }),
            'comments': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
        }

# = FORMSETS =
# extra=0 / min_num=0: no empty inline rows on open; user adds rows explicitly.
ContractFormSet = inlineformset_factory(
    Employee, Contract, form=ContractForm, extra=0, can_delete=True, min_num=0,
)
FundingFormSet = inlineformset_factory(
    Employee, FundingAllocation, form=FundingAllocationForm, extra=0, can_delete=True, min_num=0,
)
SalaryFormSet = inlineformset_factory(
    Employee, SalarySupplement,
    fields=['percentage', 'comment'],
    extra=0, can_delete=True,
)
WorkgroupFormSet = inlineformset_factory(Employee, Workgroup.members.through, fields=('workgroup',), extra=0, can_delete=True)


class WorkgroupForm(forms.ModelForm):
    class Meta:
        model = Workgroup
        fields = ['short_name', 'long_name', 'pi', 'members']
        widgets = {
            'short_name': forms.TextInput(attrs={'class': 'form-control'}),
            'long_name': forms.TextInput(attrs={'class': 'form-control'}),
            'pi': forms.Select(attrs={'class': 'form-select'}),
            'members': forms.SelectMultiple(attrs={'class': 'form-select', 'size': 8}),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        old_short_name = None
        if instance.pk:
            old_short_name = Workgroup.objects.filter(pk=instance.pk).values_list(
                'short_name', flat=True
            ).first()
        if commit:
            instance.save()
            self.save_m2m()
            sync_auth_group_for_workgroup(instance, old_short_name=old_short_name)
        return instance


# = Location management forms for Assisting Admins (Buildings / Rooms / Phones) =

class BuildingForm(forms.ModelForm):
    class Meta:
        model = Building
        fields = ['number', 'name', 'address']
        widgets = {
            'number': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = ['building', 'room_number', 'colloquial_name', 'comment']
        widgets = {
            'building': forms.Select(attrs={'class': 'form-control'}),
            'room_number': forms.TextInput(attrs={'class': 'form-control'}),
            'colloquial_name': forms.TextInput(attrs={'class': 'form-control'}),
            'comment': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class PhoneNumberForm(forms.ModelForm):
    class Meta:
        model = PhoneNumber
        fields = ['room', 'phone_number']
        widgets = {
            'room': forms.Select(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
        }