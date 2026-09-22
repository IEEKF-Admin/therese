from django.contrib import admin

from therese.admin import therese_admin
from .models import InventoryIssuance, InventoryItem, InventoryItemType


@admin.register(InventoryItemType, site=therese_admin)
class InventoryItemTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'prefix', 'next_number', 'updated_at']
    search_fields = ['name', 'prefix']


@admin.register(InventoryItem, site=therese_admin)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'item_type', 'current_holder', 'purchase_date']
    list_filter = ['item_type']
    search_fields = ['code', 'name', 'description']
    raw_id_fields = ['current_holder']


@admin.register(InventoryIssuance, site=therese_admin)
class InventoryIssuanceAdmin(admin.ModelAdmin):
    list_display = ['item', 'employee', 'issued_at', 'returned_at']
    list_filter = ['returned_at']
    raw_id_fields = ['item', 'employee', 'issued_by', 'returned_by']
