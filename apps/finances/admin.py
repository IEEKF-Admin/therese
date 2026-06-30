"""
apps/finances/admin.py
Project: THERESE â€“ Transparent HR Employee Resource Evaluation System Enhanced
"""

from django.contrib import admin
from .models import (
    CostCenter, 
    CostCenterInitialBalance, 
    WBSElement, 
    WBSElementInitialBalance, 
    PayScale
)


@admin.register(PayScale)
class PayScaleAdmin(admin.ModelAdmin):
    list_display = ('pay_scale_group', 'experience_level', 'monthly_salary', 'effective_as_of')
    list_filter = ('pay_scale_group', 'effective_as_of')
    search_fields = ('pay_scale_group',)
    ordering = ('pay_scale_group', 'experience_level')


@admin.register(CostCenter)
class CostCenterAdmin(admin.ModelAdmin):
    list_display = ('cost_center', 'comments')
    search_fields = ('cost_center', 'comments')


@admin.register(CostCenterInitialBalance)
class CostCenterInitialBalanceAdmin(admin.ModelAdmin):
    list_display = ('cost_center', 'year', 'initial_balance')
    list_filter = ('year',)


@admin.register(WBSElement)
class WBSElementAdmin(admin.ModelAdmin):
    list_display = ('wbs_code', 'title', 'responsible_person', 'comment')
    list_filter = ('responsible_person',)
    search_fields = ('wbs_code', 'title', 'comment')
    ordering = ('wbs_code',)


@admin.register(WBSElementInitialBalance)
class WBSElementInitialBalanceAdmin(admin.ModelAdmin):
    list_display = ('wbs_element', 'year', 'initial_balance')
    list_filter = ('year',)

