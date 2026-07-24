from django import forms
from django.utils import timezone

from apps.hr.models import Room, RoomStorageItem

from .lookup import looks_like_cas, normalize_cas
from .models import Chemical, ChemicalItem


class ChemicalCASLookupForm(forms.Form):
    """Step 1: enter a CAS number and look up free PubChem data."""

    cas_number = forms.CharField(
        max_length=32,
        label='CAS number',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. 50-00-0',
            'autocomplete': 'off',
            'autofocus': True,
        }),
        help_text='Enter a CAS number to look up name, formula and GHS data (PubChem).',
    )

    def clean_cas_number(self):
        raw = (self.cleaned_data.get('cas_number') or '').strip()
        if not looks_like_cas(raw):
            raise forms.ValidationError(
                'Please enter a valid CAS number (format: digits-digits-digit, e.g. 50-00-0).'
            )
        return normalize_cas(raw)


class ChemicalForm(forms.ModelForm):
    class Meta:
        model = Chemical
        fields = [
            'cas_number', 'name', 'iupac_name', 'molecular_formula',
            'ghs_signal_word', 'ghs_hazard_codes', 'ghs_pictograms',
            'is_hazardous', 'hazard_classification_notes',
            'shelf_life_months',
            'safety_data_sheet', 'sds_source_url',
        ]
        widgets = {
            'cas_number': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'iupac_name': forms.TextInput(attrs={'class': 'form-control'}),
            'molecular_formula': forms.TextInput(attrs={'class': 'form-control'}),
            'ghs_signal_word': forms.TextInput(attrs={'class': 'form-control'}),
            'ghs_hazard_codes': forms.TextInput(attrs={'class': 'form-control'}),
            'ghs_pictograms': forms.TextInput(attrs={'class': 'form-control'}),
            'is_hazardous': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'hazard_classification_notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'shelf_life_months': forms.NumberInput(attrs={
                'class': 'form-control', 'min': 1, 'step': 1, 'placeholder': 'e.g. 24',
            }),
            'sds_source_url': forms.URLInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        self.lock_cas = kwargs.pop('lock_cas', False)
        super().__init__(*args, **kwargs)
        if self.lock_cas and self.instance and self.instance.pk:
            self.fields['cas_number'].disabled = True
            self.fields['cas_number'].help_text = 'CAS number cannot be changed after creation.'

    def clean_cas_number(self):
        if self.lock_cas and self.instance and self.instance.pk:
            return self.instance.cas_number
        raw = (self.cleaned_data.get('cas_number') or '').strip()
        if not looks_like_cas(raw):
            raise forms.ValidationError('Invalid CAS number format (e.g. 50-00-0).')
        cas = normalize_cas(raw)
        qs = Chemical.objects.filter(cas_number=cas)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f'A chemical with CAS {cas} already exists.')
        return cas

    def save(self, commit=True):
        chemical = super().save(commit=False)
        # Preserve lookup metadata if provided via form extras on create
        if commit:
            chemical.save()
            self.save_m2m()
            if chemical.shelf_life_months:
                for item in chemical.items.filter(mhd__isnull=True).iterator():
                    if item.apply_auto_mhd():
                        item.save(update_fields=['mhd', 'updated_at'])
        return chemical


def chemical_form_initial_from_pubchem(cas: str) -> tuple[dict, dict]:
    """
    Build ChemicalForm initial data + meta from free PubChem lookup.

    Returns (initial_dict, meta) where meta has keys:
      error, pubchem_cid, lookup_error, sds_source_url, found
    """
    from apps.chemicals.lookup import evaluate_is_hazardous, fetch_pubchem_by_cas

    cas_n = normalize_cas(cas) or cas
    data = fetch_pubchem_by_cas(cas_n)
    hazard_codes = data.get('ghs_hazard_codes') or []
    pictograms = data.get('ghs_pictograms') or []
    signal = data.get('ghs_signal_word') or ''
    is_hazardous = evaluate_is_hazardous(
        signal_word=signal,
        hazard_codes=hazard_codes,
        pictograms=pictograms,
    )
    initial = {
        'cas_number': cas_n,
        'name': data.get('name') or '',
        'iupac_name': data.get('iupac_name') or '',
        'molecular_formula': data.get('molecular_formula') or '',
        'ghs_signal_word': signal,
        'ghs_hazard_codes': ','.join(hazard_codes),
        'ghs_pictograms': ','.join(pictograms),
        'is_hazardous': is_hazardous,
        'sds_source_url': data.get('sds_source_url') or '',
    }
    meta = {
        'error': data.get('error') or '',
        'pubchem_cid': data.get('pubchem_cid'),
        'raw': data.get('raw') or {},
        'found': bool(data.get('pubchem_cid') or data.get('name')),
    }
    return initial, meta


def apply_lookup_meta_to_chemical(chemical: Chemical, meta: dict):
    """Store PubChem metadata that is not on the form fields."""
    if meta.get('pubchem_cid'):
        chemical.pubchem_cid = meta['pubchem_cid']
    if meta.get('raw') is not None:
        chemical.pubchem_raw = meta['raw']
    chemical.lookup_error = meta.get('error') or ''
    chemical.last_lookup_at = timezone.now()
    chemical.save(update_fields=[
        'pubchem_cid', 'pubchem_raw', 'lookup_error', 'last_lookup_at', 'updated_at',
    ])


class ChemicalItemForm(forms.ModelForm):
    class Meta:
        model = ChemicalItem
        fields = [
            'product_name', 'quantity_range', 'work_area',
            'storage_room', 'storage_item', 'mhd', 'notes', 'status',
        ]
        widgets = {
            'product_name': forms.TextInput(attrs={'class': 'form-control'}),
            'quantity_range': forms.Select(attrs={'class': 'form-select'}),
            'work_area': forms.Select(attrs={'class': 'form-select'}),
            'storage_room': forms.Select(attrs={'class': 'form-select chem-storage-room'}),
            'storage_item': forms.Select(attrs={'class': 'form-select'}),
            'mhd': forms.DateInput(attrs={'class': 'form-control date-picker', 'placeholder': 'DD.MM.YYYY'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Work area: only rooms flagged as chemical work areas
        work_qs = Room.chemical_work_area_qs()
        # Keep current selection visible even if flag was later cleared
        if self.instance and self.instance.work_area_id:
            work_qs = (work_qs | Room.objects.filter(pk=self.instance.work_area_id)).distinct()
        self.fields['work_area'].queryset = work_qs
        self.fields['work_area'].required = False
        self.fields['work_area'].empty_label = '— Select work area room —'
        self.fields['work_area'].label_from_instance = lambda obj: str(obj)

        # Storage room: only rooms that have at least one storage location
        storage_qs = Room.with_storage_qs()
        if self.instance and self.instance.storage_room_id:
            storage_qs = (
                storage_qs | Room.objects.filter(pk=self.instance.storage_room_id)
            ).distinct().select_related('building').order_by(
                'building__number', 'room_number',
            )
        self.fields['storage_room'].queryset = storage_qs
        self.fields['storage_room'].required = False
        self.fields['storage_room'].empty_label = '— Select storage room —'
        self.fields['storage_room'].label_from_instance = lambda obj: str(obj)

        self.fields['storage_item'].required = False
        self.fields['mhd'].required = False
        room_id = None
        if self.data.get('storage_room'):
            room_id = self.data.get('storage_room')
        elif self.instance and self.instance.storage_room_id:
            room_id = self.instance.storage_room_id
        if room_id:
            self.fields['storage_item'].queryset = RoomStorageItem.objects.filter(
                room_id=room_id
            ).order_by('name')
        else:
            self.fields['storage_item'].queryset = RoomStorageItem.objects.none()

        # Active is set when the purchase line is marked delivered — not manually from draft.
        current = getattr(self.instance, 'status', None) or ChemicalItem.Status.DRAFT
        if current == ChemicalItem.Status.DRAFT:
            self.fields['status'].choices = [
                (ChemicalItem.Status.DRAFT, 'Draft (ordered, not delivered)'),
                (ChemicalItem.Status.ARCHIVED, 'Archived'),
            ]
        elif current == ChemicalItem.Status.ACTIVE:
            self.fields['status'].choices = [
                (ChemicalItem.Status.ACTIVE, 'Active (delivered / in inventory)'),
                (ChemicalItem.Status.ARCHIVED, 'Archived'),
            ]

        # Prefill empty MHD from shelf life for display (not forced until save)
        if self.instance and self.instance.pk and not self.instance.mhd and not self.data:
            suggested = self.instance.compute_mhd_from_shelf_life()
            if suggested:
                self.fields['mhd'].initial = suggested
                self.fields['mhd'].help_text = (
                    f'Suggested from shelf life ({self.instance.chemical.shelf_life_months} months). '
                    'Leave empty to auto-apply on save, or set manually.'
                )

    def save(self, commit=True):
        item = super().save(commit=False)
        # If user left MHD blank, auto-fill from chemical shelf life
        if not item.mhd:
            item.apply_auto_mhd()
        if commit:
            item.save()
        return item


class ChemicalItemInlineForm(forms.ModelForm):
    """Minimal inline on PO: only fields that cannot be auto-filled."""

    class Meta:
        model = ChemicalItem
        fields = ['quantity_range', 'work_area', 'storage_room', 'storage_item', 'notes']
        widgets = {
            'quantity_range': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'work_area': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'storage_room': forms.Select(attrs={'class': 'form-select form-select-sm chem-storage-room'}),
            'storage_item': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'notes': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['work_area'].queryset = Room.chemical_work_area_qs()
        self.fields['work_area'].required = False
        self.fields['work_area'].empty_label = '— Work area —'
        self.fields['storage_room'].queryset = Room.with_storage_qs()
        self.fields['storage_room'].required = False
        self.fields['storage_room'].empty_label = '— Storage room —'
        self.fields['storage_item'].required = False
        self.fields['quantity_range'].required = False
        room_id = self.data.get(self.add_prefix('storage_room')) if self.data else None
        if not room_id and self.instance and self.instance.storage_room_id:
            room_id = self.instance.storage_room_id
        if room_id:
            self.fields['storage_item'].queryset = RoomStorageItem.objects.filter(room_id=room_id)
        else:
            self.fields['storage_item'].queryset = RoomStorageItem.objects.none()
