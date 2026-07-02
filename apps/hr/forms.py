"""
apps/hr/forms.py
Project: THERESE - Transparent HR Employee Resource Evaluation System Enhanced
Realized functionalities in this file:
- EmployeeForm with full cascading dropdowns (Building → Room → PhoneNumber)
- Dynamic queryset filtering for Room and PhoneNumber based on POST or instance
- Proper ModelChoiceField handling for phone_number with forced choices on render
- Inline form support for all related models
- Extensive debugging output to console + timestamped log files
- clean_room() and full clean() with cross-field validation
- English-only user-facing strings and logs
Constraints:
- Must work for both CreateView and UpdateView
- Must preserve all existing form fields and validation
- Phone pre-filling on edit must work reliably
"""

from pathlib import Path
from datetime import datetime
from django import forms
from django.forms.models import inlineformset_factory

from .models import (
    Employee, Building, Room, PhoneNumber, Contract,
    FundingAllocation, SalarySupplement, Workgroup
)
from apps.finances.models import PayScale


def get_log_dir():
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    return log_dir


def log_form_init(form_name: str, data=None, instance=None, errors=None):
    """Excessive debugging"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = get_log_dir() / f"{form_name}_{timestamp}.txt"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"THERESE - {form_name} DEBUG LOG\n")
        f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("="*80 + "\n\n")
        if instance and instance.pk:
            f.write(f"INSTANCE: {instance} (PK: {instance.pk})\n")
            f.write(f" Building: {instance.room.building if instance.room else None}\n")
            f.write(f" Room: {instance.room}\n")
            f.write(f" Phone: {instance.phone_number}\n\n")
        if data:
            f.write("BOUND DATA (excerpt):\n")
            for k, v in list(data.items())[:50]:
                f.write(f" {k}: {v}\n")
    print(f"📝 {form_name} debug log: {log_path.name}")


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
        fields = '__all__'
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

        print("\n" + "="*150)
        print("🔥🔥🔥 EXTREM EXZESSIVES DEBUGGING - EmployeeForm.__init__ 🔥🔥🔥")
        print(f"Is bound (POST): {self.is_bound}")
        print(f"Has instance (Edit-Modus): {bool(instance and instance.pk)}")
        print(f"Instance PK: {instance.pk if instance else None}")
        print(f"Instance room: {instance.room if instance else None}")
        print(f"Instance phone_number: {instance.phone_number if instance else None}")

        log_form_init("EmployeeForm", data=self.data if self.is_bound else None, instance=instance)

        # BUILDING
        print("\n--- BUILDING FIELD ---")
        building_field = self.fields['building']
        building_field.widget.attrs.update({'class': 'building-select form-control', 'id': 'id_building'})
        print(f"Building queryset count: {building_field.queryset.count()}")
        if instance and instance.room and instance.room.building:
            building_field.initial = instance.room.building.pk
            print(f"✅ Building initial SET to: {building_field.initial} ({instance.room.building.number} - {instance.room.building.name})")
        else:
            print("⚠️  No building initial set")

        # ROOM
        print("\n--- ROOM FIELD ---")
        room_field = self.fields['room']
        room_field.empty_label = "— Select Building first —"
        room_field.widget.attrs.update({'class': 'room-select form-control', 'id': 'id_room'})

        if self.is_bound and self.data.get('building'):
            room_field.queryset = Room.objects.filter(building_id=self.data['building']).order_by('room_number')
            print(f"POST mode → Room queryset filtered by building_id={self.data['building']} → {room_field.queryset.count()} rooms")
        elif instance and instance.room:
            room_field.queryset = Room.objects.filter(building=instance.room.building).order_by('room_number')
            room_field.initial = instance.room.pk
            print(f"✅ EDIT mode → Room queryset set for building {instance.room.building}")
            print(f"✅ Room initial SET to: {room_field.initial} ({instance.room.room_number} - {instance.room.colloquial_name})")
        else:
            room_field.queryset = Room.objects.none()
            print("⚠️  Room queryset = empty")

        # PHONE
        print("\n--- PHONE FIELD ---")
        phone_field = self.fields['phone_number']
        phone_field.widget.attrs.update({'class': 'phone-select form-control', 'id': 'id_phone_number'})

        # Determine the phone value we want to preserve (POST or instance)
        phone_to_preserve = None
        if self.is_bound and self.data.get('phone_number'):
            phone_to_preserve = self.data.get('phone_number')
        elif instance and instance.phone_number:
            phone_to_preserve = instance.phone_number

        if self.is_bound and self.data.get('room'):
            phone_field.queryset = PhoneNumber.objects.filter(room_id=self.data['room'])
            print(f"POST mode → Phone queryset for room_id={self.data['room']} → {phone_field.queryset.count()} phones")
            if phone_to_preserve:
                phone_field.initial = phone_to_preserve
                print(f"POST mode → Phone initial set to: {phone_field.initial}")
        elif instance and instance.phone_number:
            phone_field.queryset = PhoneNumber.objects.filter(phone_number=instance.phone_number)
            phone_field.initial = instance.phone_number
            print(f"✅ EDIT mode → Phone queryset filtered for '{instance.phone_number}' → {phone_field.queryset.count()} phones")
            print(f"✅ Phone initial SET to: '{phone_field.initial}'")
        else:
            phone_field.queryset = PhoneNumber.objects.none()
            print("⚠️  Phone queryset = empty")

        # Ensure the preserved phone is always in the queryset (for validation when room filter excludes it)
        if phone_to_preserve and phone_field.queryset is not None:
            if not phone_field.queryset.filter(phone_number=phone_to_preserve).exists():
                preserved_qs = PhoneNumber.objects.filter(phone_number=phone_to_preserve)
                phone_field.queryset = (phone_field.queryset | preserved_qs).distinct()
                print(f"  → Added preserved phone '{phone_to_preserve}' to queryset for validation")

        print("\n=== FORM __INIT__ END - EXTREM EXZESSIVES DEBUGGING ===\n")

        # Styling
        for field in self.fields.values():
            if 'form-control' not in field.widget.attrs.get('class', ''):
                field.widget.attrs['class'] = 'form-control'

    def clean_room(self):
        room = self.cleaned_data.get('room')
        print(f"DEBUG clean_room() → Final value: {room}")
        return room

    def clean(self):
        cleaned_data = super().clean()
        print("=== FINAL CLEAN() IN MAIN FORM ===")
        room = cleaned_data.get('room')
        building = cleaned_data.get('building')
        if room and building and room.building != building:
            self.add_error('room', "Room does not belong to selected building")
        print("=== END OF clean() ===\n")
        return cleaned_data

    def clean_phone_number(self):
        phone = self.cleaned_data.get('phone_number')
        if phone is None:
            if self.instance and self.instance.pk and self.instance.phone_number:
                return self.instance.phone_number
            return ''
        # Ensure it's a string
        return str(phone) if phone else ''


# = INLINE FORMS =
class ContractForm(forms.ModelForm):
    class Meta:
        model = Contract
        fields = ['pay_scale_group', 'experience_level', 'job_number', 'weekly_hours', 'valid_from', 'valid_until', 'comments']
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
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        print("ContractForm __init__ called for inline")

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

        # Re-apply form-control to any remaining fields
        for field in self.fields.values():
            if 'form-control' not in field.widget.attrs.get('class', ''):
                field.widget.attrs['class'] = 'form-control'


class FundingAllocationForm(forms.ModelForm):
    class Meta:
        model = FundingAllocation
        fields = ['wbs_element', 'weekly_hours_allocated', 'start_date', 'end_date', 'comments']
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
ContractFormSet = inlineformset_factory(Employee, Contract, form=ContractForm, extra=1, can_delete=True, min_num=1)
FundingFormSet = inlineformset_factory(Employee, FundingAllocation, form=FundingAllocationForm, extra=1, can_delete=True, min_num=1)
SalaryFormSet = inlineformset_factory(Employee, SalarySupplement, fields='__all__', extra=0, can_delete=True)
WorkgroupFormSet = inlineformset_factory(Employee, Workgroup.members.through, fields=('workgroup',), extra=0, can_delete=True)


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

