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
    WBSElementInitialBalance, 
    PayScale
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
    list_display = ('wbs_code', 'title', 'work_group', 'responsible_person', 'comment')
    list_filter = ('work_group', 'responsible_person',)
    search_fields = ('wbs_code', 'title', 'comment', 'work_group__short_name')
    ordering = ('wbs_code',)
    autocomplete_fields = ['work_group']  # requires search in Workgroup admin if large


@admin.register(WBSElementInitialBalance, site=therese_admin)
class WBSElementInitialBalanceAdmin(admin.ModelAdmin):
    list_display = ('wbs_element', 'year', 'initial_balance')
    list_filter = ('year',)

