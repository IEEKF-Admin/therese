from django.contrib import admin

from therese.admin import therese_admin

from .models import Chemical, ChemicalItem


@admin.register(Chemical, site=therese_admin)
class ChemicalAdmin(admin.ModelAdmin):
    list_display = (
        'cas_number', 'name', 'is_hazardous', 'shelf_life_months', 'ghs_signal_word',
        'last_lookup_at', 'updated_at',
    )
    list_filter = ('is_hazardous',)
    search_fields = ('cas_number', 'name', 'iupac_name')
    readonly_fields = ('last_lookup_at', 'pubchem_raw', 'created_at', 'updated_at')


@admin.register(ChemicalItem, site=therese_admin)
class ChemicalItemAdmin(admin.ModelAdmin):
    list_display = (
        'public_id', 'chemical', 'status', 'ordered_by', 'workgroup',
        'quantity_range', 'storage_room', 'mhd', 'ordered_at',
    )
    list_filter = ('status', 'quantity_range')
    search_fields = (
        'chemical__cas_number', 'product_name',
        'work_area__room_number', 'work_area__colloquial_name',
    )
    autocomplete_fields = (
        'chemical', 'ordered_by', 'workgroup',
        'work_area', 'storage_room', 'storage_item',
    )
    readonly_fields = ('public_id', 'created_at', 'updated_at', 'delivered_at')
