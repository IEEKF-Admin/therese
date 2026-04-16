from django.contrib import admin
from .models import PSPElement, PSPBudgetHistory

@admin.register(PSPElement)
class PSPElementAdmin(admin.ModelAdmin):
    list_display = ['title', 'responsible', 'current_secured_amount']
    search_fields = ['title', 'comments']
    list_filter = ['responsible']

@admin.register(PSPBudgetHistory)
class PSPBudgetHistoryAdmin(admin.ModelAdmin):
    list_display = ['psp_element', 'effective_date', 'secured_amount', 'changed_by', 'created_at']
    list_filter = ['effective_date', 'changed_by']
    search_fields = ['psp_element__title', 'comment']
    date_hierarchy = 'effective_date'
