"""
apps/tasks/admin.py
Project: THERESE â€“ Transparent HR Employee Resource Evaluation System Enhanced
Admin configuration for Tasks (angepasst an Bestellung-WÃ¼nsche)
"""

from django.contrib import admin
from therese.admin import therese_admin
from django import forms
from .models import (
    Task, TaskComment, TaskAttachment,
    PurchaseOrderTask, PurchaseItem,
    PersonnelReallocationTask, PersonnelContractExtensionTask, GenericTextTask
)
from .forms import PurchaseOrderTaskForm   # â† Diese Zeile hinzufÃ¼gen!
from apps.hr.models import Employee
from apps.accounts.permissions import GroupNames


# = Inlines =
class PurchaseItemInline(admin.TabularInline):
    model = PurchaseItem
    extra = 1
    verbose_name_plural = "Bestellpositionen"
    fields = ['product_name', 'product_description', 'link_to_product', 'order_number', 'unit_price', 'quantity']


class TaskCommentInline(admin.TabularInline):
    model = TaskComment
    extra = 1
    readonly_fields = ['author', 'created_at']


class TaskAttachmentInline(admin.TabularInline):
    model = TaskAttachment
    extra = 1
    readonly_fields = ['uploaded_by', 'created_at']


# = Admin Classes =
@admin.register(PurchaseOrderTask, site=therese_admin)
class PurchaseOrderTaskAdmin(admin.ModelAdmin):
    form = PurchaseOrderTaskForm
    inlines = [PurchaseItemInline, TaskCommentInline, TaskAttachmentInline]
    
    list_display = ['supplier', 'wbs_element', 'status', 'priority', 'assignee', 'created_at']
    list_filter = ['status', 'priority', 'created_at']
    search_fields = ['supplier', 'wbs_element__wbs_code']
    readonly_fields = ['creator', 'last_status_change', 'last_changed_by']

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        # WBS Element nur fÃ¼r Order Manager sichtbar
        if not request.user.groups.filter(name=GroupNames.ORDER_MANAGER).exists():
            form.base_fields['wbs_element'].widget = forms.HiddenInput()
            form.base_fields['wbs_element'].required = False
        return form


@admin.register(PersonnelReallocationTask, site=therese_admin)
class PersonnelReallocationTaskAdmin(admin.ModelAdmin):
    inlines = [TaskCommentInline, TaskAttachmentInline]
    list_display = ['title', 'employee', 'target_wbs', 'status', 'valid_from', 'assignee']
    list_filter = ['status', 'valid_from']


@admin.register(PersonnelContractExtensionTask, site=therese_admin)
class PersonnelContractExtensionTaskAdmin(admin.ModelAdmin):
    inlines = [TaskCommentInline, TaskAttachmentInline]
    list_display = ['title', 'employee', 'valid_from', 'is_limited', 'status', 'assignee']
    list_filter = ['status', 'is_limited']


@admin.register(GenericTextTask, site=therese_admin)
class GenericTextTaskAdmin(admin.ModelAdmin):
    inlines = [TaskCommentInline, TaskAttachmentInline]
    list_display = ['title', 'recipient', 'status', 'assignee']
    list_filter = ['status']


# Base Task (read-only overview)
@admin.register(Task, site=therese_admin)
class TaskAdmin(admin.ModelAdmin):
    list_display = ['task_type', 'title', 'creator', 'assignee', 'status', 'priority', 'created_at']
    list_filter = ['task_type', 'status', 'priority']
    search_fields = ['title']
    readonly_fields = ['task_type', 'creator', 'last_status_change', 'last_changed_by']

