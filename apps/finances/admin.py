"""
apps/finances/admin.py
Project: THERESE – Transparent HR Employee Resource Evaluation System Enhanced
"""

from django.contrib import admin
from therese.admin import therese_admin
from .models import (
    ContactPerson,
    CostCenter,
    CostCenterObligo,
    CostCenterTrueYearlySpending,
    CostCenterYearEstimate,
    WBSElement,
    WBSElementObligo,
    WBSElementTrueYearlySpending,
    WBSElementYearEstimate,
    PayScale,
)
from .psp_cost_types import PSP_COST_TYPE_AMOUNT_FIELDS, PSP_COST_TYPE_FLAG_FIELDS


@admin.register(ContactPerson, site=therese_admin)
class ContactPersonAdmin(admin.ModelAdmin):
    list_display = ('last_name', 'first_name', 'business_area', 'phone', 'email', 'comments')
    search_fields = ('last_name', 'first_name', 'email', 'business_area', 'phone', 'comments')
    ordering = ('last_name', 'first_name')


class WBSElementYearEstimateInline(admin.TabularInline):
    model = WBSElementYearEstimate
    extra = 1
    fields = (
        'year',
        *PSP_COST_TYPE_AMOUNT_FIELDS,
    )


class CostCenterYearEstimateInline(admin.TabularInline):
    model = CostCenterYearEstimate
    extra = 1
    fields = (
        'year',
        'lomv',
        *PSP_COST_TYPE_AMOUNT_FIELDS,
    )


# True yearly spending and Obligo are intentionally NOT inlines on
# WBSElementAdmin / CostCenterAdmin — they must not appear in the editor UI.


@admin.register(PayScale, site=therese_admin)
class PayScaleAdmin(admin.ModelAdmin):
    list_display = ('pay_scale_group', 'experience_level', 'monthly_salary', 'effective_as_of')
    list_filter = ('pay_scale_group', 'effective_as_of')
    search_fields = ('pay_scale_group',)
    ordering = ('pay_scale_group', 'experience_level')


@admin.register(CostCenter, site=therese_admin)
class CostCenterAdmin(admin.ModelAdmin):
    list_display = ('cost_center', 'contact_person', 'comments')
    search_fields = ('cost_center', 'comments')
    list_filter = PSP_COST_TYPE_FLAG_FIELDS
    autocomplete_fields = ['contact_person']
    inlines = [CostCenterYearEstimateInline]
    fieldsets = (
        (None, {
            'fields': (
                'cost_center',
                'contact_person',
                'comments',
            ),
        }),
        ('Cost types', {
            'fields': PSP_COST_TYPE_FLAG_FIELDS,
        }),
    )


@admin.register(CostCenterYearEstimate, site=therese_admin)
class CostCenterYearEstimateAdmin(admin.ModelAdmin):
    list_display = (
        'cost_center',
        'year',
        'lomv',
        *PSP_COST_TYPE_AMOUNT_FIELDS,
    )
    list_filter = ('year',)
    search_fields = ('cost_center__cost_center',)
    autocomplete_fields = ['cost_center']
    ordering = ('cost_center__cost_center', 'year')
    fields = (
        'cost_center',
        'year',
        'lomv',
        *PSP_COST_TYPE_AMOUNT_FIELDS,
    )


@admin.register(CostCenterTrueYearlySpending, site=therese_admin)
class CostCenterTrueYearlySpendingAdmin(admin.ModelAdmin):
    """Standalone admin for actual cost-center costs; not part of the editor form."""
    list_display = (
        'cost_center',
        'date_of_update',
        *PSP_COST_TYPE_AMOUNT_FIELDS,
    )
    list_filter = ('date_of_update',)
    search_fields = ('cost_center__cost_center',)
    autocomplete_fields = ['cost_center']
    ordering = ('cost_center__cost_center', '-date_of_update')
    date_hierarchy = 'date_of_update'
    fields = (
        'cost_center',
        'date_of_update',
        *PSP_COST_TYPE_AMOUNT_FIELDS,
    )


@admin.register(CostCenterObligo, site=therese_admin)
class CostCenterObligoAdmin(admin.ModelAdmin):
    """Standalone admin for cost-center obligo; not part of the editor form."""
    list_display = (
        'cost_center',
        'date_of_update',
        'personal',
        *PSP_COST_TYPE_AMOUNT_FIELDS,
    )
    list_filter = ('date_of_update',)
    search_fields = ('cost_center__cost_center',)
    autocomplete_fields = ['cost_center']
    ordering = ('cost_center__cost_center', '-date_of_update')
    date_hierarchy = 'date_of_update'
    fields = (
        'cost_center',
        'date_of_update',
        'personal',
        *PSP_COST_TYPE_AMOUNT_FIELDS,
    )


@admin.register(WBSElement, site=therese_admin)
class WBSElementAdmin(admin.ModelAdmin):
    list_display = (
        'wbs_code',
        'title',
        'cost_center',
        'contact_person',
        'work_group',
        'responsible_person',
        'is_inactive',
    )
    list_filter = (
        'work_group',
        'responsible_person',
        'is_inactive',
        'subject_to_annual_recurrence',
        *PSP_COST_TYPE_FLAG_FIELDS,
    )
    search_fields = ('wbs_code', 'title', 'comment', 'work_group__short_name')
    ordering = ('wbs_code',)
    autocomplete_fields = ['work_group', 'contact_person', 'cost_center']
    inlines = [WBSElementYearEstimateInline]
    fieldsets = (
        (None, {
            'fields': (
                'wbs_code',
                'title',
                'cost_center',
                'contact_person',
                'work_group',
                'responsible_person',
                'comment',
            ),
        }),
        ('Cost types', {
            'fields': PSP_COST_TYPE_FLAG_FIELDS,
        }),
        ('Third-party funding', {
            'fields': (
                'third_party_funding_commitment',
                'third_party_funder_identifier',
            ),
        }),
        ('Period & status', {
            'fields': (
                'period_start',
                'period_end',
                'subject_to_annual_recurrence',
                'is_inactive',
            ),
        }),
    )


@admin.register(WBSElementYearEstimate, site=therese_admin)
class WBSElementYearEstimateAdmin(admin.ModelAdmin):
    list_display = (
        'wbs_element',
        'year',
        *PSP_COST_TYPE_AMOUNT_FIELDS,
    )
    list_filter = ('year', 'wbs_element__work_group')
    search_fields = ('wbs_element__wbs_code', 'wbs_element__title')
    autocomplete_fields = ['wbs_element']
    ordering = ('wbs_element__wbs_code', 'year')
    fields = (
        'wbs_element',
        'year',
        *PSP_COST_TYPE_AMOUNT_FIELDS,
    )


@admin.register(WBSElementTrueYearlySpending, site=therese_admin)
class WBSElementTrueYearlySpendingAdmin(admin.ModelAdmin):
    """Standalone admin for actual costs; not part of the PSP element form."""
    list_display = (
        'wbs_element',
        'date_of_update',
        *PSP_COST_TYPE_AMOUNT_FIELDS,
    )
    list_filter = ('date_of_update', 'wbs_element__work_group')
    search_fields = ('wbs_element__wbs_code', 'wbs_element__title')
    autocomplete_fields = ['wbs_element']
    ordering = ('wbs_element__wbs_code', '-date_of_update')
    date_hierarchy = 'date_of_update'
    fields = (
        'wbs_element',
        'date_of_update',
        *PSP_COST_TYPE_AMOUNT_FIELDS,
    )


@admin.register(WBSElementObligo, site=therese_admin)
class WBSElementObligoAdmin(admin.ModelAdmin):
    """Standalone admin for PSP obligo; not part of the PSP element form."""
    list_display = (
        'wbs_element',
        'date_of_update',
        'personal',
        *PSP_COST_TYPE_AMOUNT_FIELDS,
    )
    list_filter = ('date_of_update', 'wbs_element__work_group')
    search_fields = ('wbs_element__wbs_code', 'wbs_element__title')
    autocomplete_fields = ['wbs_element']
    ordering = ('wbs_element__wbs_code', '-date_of_update')
    date_hierarchy = 'date_of_update'
    fields = (
        'wbs_element',
        'date_of_update',
        'personal',
        *PSP_COST_TYPE_AMOUNT_FIELDS,
    )
