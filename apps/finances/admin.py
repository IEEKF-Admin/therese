"""
apps/finances/admin.py
Project: THERESE – Transparent HR Employee Resource Evaluation System Enhanced
"""

from django.contrib import admin
from therese.admin import therese_admin
from .models import (
    CostCenter,
    CostCenterInitialBalance,
    WBSElement,
    WBSElementYearEstimate,
    PayScale,
)


class WBSElementYearEstimateInline(admin.TabularInline):
    model = WBSElementYearEstimate
    extra = 1
    fields = (
        'year',
        'funding',
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
    list_display = ('cost_center', 'comments')
    search_fields = ('cost_center', 'comments')


@admin.register(CostCenterInitialBalance, site=therese_admin)
class CostCenterInitialBalanceAdmin(admin.ModelAdmin):
    list_display = ('cost_center', 'year', 'initial_balance')
    list_filter = ('year',)


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
    list_filter = ('work_group', 'responsible_person', 'is_inactive', 'subject_to_annual_recurrence')
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
        ('Period & status', {
            'fields': (
                'period_start',
                'period_end',
                'subject_to_annual_recurrence',
                'is_inactive',
            ),
        }),
    )