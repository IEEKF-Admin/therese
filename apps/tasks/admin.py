"""
apps/tasks/admin.py
Project: THERESE – Transparent HR Employee Resource Evaluation System Enhanced
Admin configuration for Tasks (purchase orders, personnel, recruitment, generic)
"""

from django.contrib import admin
from therese.admin import therese_admin
from django import forms
from .models import (
    Task, TaskComment, TaskAttachment,
    PurchaseOrderTask, PurchaseItem,
    PersonnelReallocationTask, PersonnelContractExtensionTask,
    PersonnelRecruitmentTask, RecruitmentFundingAllocation,
    ReallocationFundingAllocation, RecruitmentJob,
    RecruitmentJobFieldRule, LimitationReason, GenericTextTask,
)
from .forms import (
    RecruitmentFundingAllocationForm,
    ReallocationFundingAllocationForm,
)
from apps.hr.models import Employee
# GroupNames removed (old groups deleted)


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


class PurchaseOrderTaskAdminForm(forms.ModelForm):
    """
    Admin-only form for purchase orders.

    Do not reuse the frontend PurchaseOrderTaskForm here — that form pops
    fields (e.g. quote_file) based on role/creation mode and breaks admin
    fieldsets with KeyError.
    """

    class Meta:
        model = PurchaseOrderTask
        fields = [
            'title',
            'creator',
            'supplier',
            'is_quote_order',
            'quote_file',
            'wbs_element',
            'at_beleg_nummer',
            'kostenart',
            'referenzbeleg_nr',
            'einkaufsbeleg_nr',
            'v_kurztext',
            'v_buchungsdatum',
            'v_belegdatum',
            'v_istkosten',
            'import_completed',
            'priority',
            'status',
            'assignee',
        ]
        widgets = {
            'quote_file': forms.ClearableFileInput(attrs={'accept': '.pdf,application/pdf'}),
        }


# = Admin Classes =
@admin.register(PurchaseOrderTask, site=therese_admin)
class PurchaseOrderTaskAdmin(admin.ModelAdmin):
    form = PurchaseOrderTaskAdminForm
    inlines = [PurchaseItemInline, TaskCommentInline, TaskAttachmentInline]

    list_display = [
        'supplier',
        'is_quote_order',
        'wbs_element',
        'status',
        'priority',
        'assignee',
        'kostenart',
        'einkaufsbeleg_nr',
        'import_completed',
        'created_at',
    ]
    list_filter = [
        'status', 'priority', 'is_quote_order', 'import_completed', 'created_at', 'kostenart',
    ]
    search_fields = [
        'supplier',
        'wbs_element__wbs_code',
        'at_beleg_nummer',
        'referenzbeleg_nr',
        'einkaufsbeleg_nr',
        'v_kurztext',
    ]
    readonly_fields = [
        'task_number',
        'last_status_change',
        'last_changed_by',
        'created_at',
        'updated_at',
    ]
    autocomplete_fields = ['wbs_element', 'assignee', 'creator']
    fieldsets = (
        (None, {
            'fields': (
                'title',
                'task_number',
                'creator',
                'supplier',
                'is_quote_order',
                'quote_file',
                'wbs_element',
                'priority',
                'status',
                'assignee',
            ),
        }),
        ('Document numbers', {
            'fields': (
                'at_beleg_nummer',
                'referenzbeleg_nr',
                'einkaufsbeleg_nr',
            ),
        }),
        ('SAP / posting', {
            'fields': (
                'kostenart',
                'v_kurztext',
                'v_buchungsdatum',
                'v_belegdatum',
                'v_istkosten',
            ),
        }),
        ('Import status', {
            'fields': ('import_completed',),
            'description': (
                'Set when imported data confirms the administration process '
                'for this purchase order is complete.'
            ),
        }),
        ('Audit', {
            'fields': (
                'last_status_change',
                'last_changed_by',
                'created_at',
                'updated_at',
            ),
        }),
    )

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        # Hide WBS field unless user has change_wbs_on_purchase_order permission
        if 'wbs_element' in form.base_fields and not (
            request.user.is_superuser
            or request.user.has_perm('tasks.change_wbs_on_purchase_order')
        ):
            form.base_fields['wbs_element'].widget = forms.HiddenInput()
            form.base_fields['wbs_element'].required = False
        return form

    def save_model(self, request, obj, form, change):
        if not obj.task_type:
            obj.task_type = 'purchase_order'
        super().save_model(request, obj, form, change)


class ReallocationFundingInline(admin.TabularInline):
    model = ReallocationFundingAllocation
    form = ReallocationFundingAllocationForm
    extra = 1


@admin.register(PersonnelReallocationTask, site=therese_admin)
class PersonnelReallocationTaskAdmin(admin.ModelAdmin):
    inlines = [ReallocationFundingInline, TaskCommentInline, TaskAttachmentInline]
    list_display = ['title', 'employee', 'status', 'valid_from', 'assignee']
    list_filter = ['status', 'valid_from']


@admin.register(PersonnelContractExtensionTask, site=therese_admin)
class PersonnelContractExtensionTaskAdmin(admin.ModelAdmin):
    inlines = [TaskCommentInline, TaskAttachmentInline]
    list_display = ['title', 'employee', 'valid_from', 'is_limited', 'status', 'assignee']
    list_filter = ['status', 'is_limited']


class RecruitmentFundingInline(admin.TabularInline):
    model = RecruitmentFundingAllocation
    form = RecruitmentFundingAllocationForm
    extra = 1


@admin.register(RecruitmentJob, site=therese_admin)
class RecruitmentJobAdmin(admin.ModelAdmin):
    list_display = ('name', 'pay_scale_group', 'experience_level', 'is_active')
    search_fields = ('name', 'pay_scale_group')


@admin.register(LimitationReason, site=therese_admin)
class LimitationReasonAdmin(admin.ModelAdmin):
    list_display = ('title', 'applies_to_all_jobs', 'is_active')
    filter_horizontal = ('jobs',)


@admin.register(PersonnelRecruitmentTask, site=therese_admin)
class PersonnelRecruitmentTaskAdmin(admin.ModelAdmin):
    inlines = [RecruitmentFundingInline, TaskCommentInline, TaskAttachmentInline]
    list_display = ['task_number', 'last_name', 'first_name', 'status', 'assignee']
    list_filter = ['status']


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

