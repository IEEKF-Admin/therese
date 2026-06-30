"""
apps/finances/admin.py
Project: THERESE â€“ Transparent HR Employee Resource Evaluation System Enhanced
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


@therese_admin.register(PayScale)
class PayScaleAdmin(admin.ModelAdmin):
    list_display = ('pay_scale_group', 'experience_level', 'monthly_salary', 'effective_as_of')
    list_filter = ('pay_scale_group', 'effective_as_of')
    search_fields = ('pay_scale_group',)
    ordering = ('pay_scale_group', 'experience_level')


@therese_admin.register(CostCenter)
class CostCenterAdmin(admin.ModelAdmin):
    list_display = ('cost_center', 'comments')
    search_fields = ('cost_center', 'comments')


@therese_admin.register(CostCenterInitialBalance)
class CostCenterInitialBalanceAdmin(admin.ModelAdmin):
    list_display = ('cost_center', 'year', 'initial_balance')
    list_filter = ('year',)


@therese_admin.register(WBSElement)
class WBSElementAdmin(admin.ModelAdmin):
    list_display = ('wbs_code', 'title', 'responsible_person', 'comment')
    list_filter = ('responsible_person',)
    search_fields = ('wbs_code', 'title', 'comment')
    ordering = ('wbs_code',)


@therese_admin.register(WBSElementInitialBalance)
class WBSElementInitialBalanceAdmin(admin.ModelAdmin):
    list_display = ('wbs_element', 'year', 'initial_balance')
    list_filter = ('year',)

