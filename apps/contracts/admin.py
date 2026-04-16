from django.contrib import admin
from .models import Contract

@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ['employee', 'pay_scale_group', 'experience_level', 'weekly_hours', 'valid_from', 'valid_until', 'is_current']
    list_filter = ['valid_from', 'pay_scale_group']
    search_fields = ['employee__first_name', 'employee__last_name']
    date_hierarchy = 'valid_from'
