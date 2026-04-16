from django.contrib import admin
from .models import FundingAllocation

@admin.register(FundingAllocation)
class FundingAllocationAdmin(admin.ModelAdmin):
    list_display = ['employee', 'psp_element', 'weekly_hours_allocated', 'start_date', 'end_date']
    list_filter = ['start_date', 'end_date']
    search_fields = ['employee__first_name', 'employee__last_name', 'psp_element__title']
