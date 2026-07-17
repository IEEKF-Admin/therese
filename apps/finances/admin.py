"""
apps/finances/admin.py
Project: THERESE – Transparent HR Employee Resource Evaluation System Enhanced
"""

from django.contrib import admin
from therese.admin import therese_admin
from .models import (
    CostCenter,
    CostCenterYearEstimate,
    WBSElement,
    WBSElementTrueYearlySpending,
    WBSElementYearEstimate,
    PayScale,
)
from .psp_cost_types import PSP_COST_TYPE_AMOUNT_FIELDS, PSP_COST_TYPE_FLAG_FIELDS


class WBSElementYearEstimateInline(admin.TabularInline):
    model = WBSElementYearEstimate
    extra = 1
    fields = (
        'year',
        *PSP_COST_TYPE_AMOUNT_FIELDS,
    )


# True yearly spending is intentionally NOT an inline on WBSElementAdmin —
# it must not appear when editing PSP elements in admin or the public editor.


class CostCenterYearEstimateInline(admin.TabularInline):
    model = CostCenterYearEstimate
    extra = 1
    fields = (
        'year',
        'lomv',
        'consumables_estimate',
        'travel_estimate',
        'animal_costs_estimate',
    )


@admin.register(PayScale, site=therese_admin)
class PayScaleAdmin(admin.ModelAdmin):
    list_display = ('pay_scale_group', 'experience_level', 'monthly_salary', 'effective_as_of')
    list_filter = ('pay_scale_group', 'effective_as_of')
    search_fields = ('pay_scale_group',)
    ordering = ('pay_scale_group', 'experience_level')


@admin.register(CostCenter, site=therese_admin)
class CostCenterAdmin(admin.ModelAdmin):
    list_display = ('cost_center', 'third_party_funder_identifier', 'comments')
    search_fields = ('cost_center', 'comments', 'third_party_funder_identifier')
    inlines = [CostCenterYearEstimateInline]
    fieldsets = (
        (None, {
            'fields': (
                'cost_center',
                'comments',
            ),
        }),
        ('Third-party funding', {
            'fields': (
                'third_party_funding_commitment',
                'third_party_funder_identifier',
            ),
        }),
    )


@admin.register(WBSElement, site=therese_admin)
class WBSElementAdmin(admin.ModelAdmin):
    list_display = (
        'wbs_code',
        'title',
        'cost_center',
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
    autocomplete_fields = ['work_group']
    inlines = [WBSElementYearEstimateInline]
    fieldsets = (
        (None, {
            'fields': (
                'wbs_code',
                'title',
                'cost_center',
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


@admin.register(WBSElementTrueYearlySpending, site=therese_admin)
class WBSElementTrueYearlySpendingAdmin(admin.ModelAdmin):
    """Standalone admin for actual costs; not part of the PSP element form."""
    list_display = (
        'wbs_element',
        'year',
        'material_costs',
        'personnel_costs',
        'domestic_travel_costs',
        'foreign_travel_costs',
        'third_party_investments',
        'publication_costs',
        'animal_husbandry_costs',
        'transfer_to_third_parties',
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
