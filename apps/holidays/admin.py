from django.contrib import admin

from apps.holidays.models import (
    HolidayCustomDay,
    HolidayEntitlementRate,
    HolidayProfile,
    HolidayRequest,
    HolidayYearEntitlement,
)


@admin.register(HolidayProfile)
class HolidayProfileAdmin(admin.ModelAdmin):
    list_display = ('employee', 'workdays_per_week', 'share_with_institute')


@admin.register(HolidayYearEntitlement)
class HolidayYearEntitlementAdmin(admin.ModelAdmin):
    list_display = ('employee', 'year', 'days')


@admin.register(HolidayCustomDay)
class HolidayCustomDayAdmin(admin.ModelAdmin):
    list_display = ('day', 'name', 'mode', 'year')


@admin.register(HolidayEntitlementRate)
class HolidayEntitlementRateAdmin(admin.ModelAdmin):
    list_display = ('weekdays', 'contract_months', 'days')


@admin.register(HolidayRequest)
class HolidayRequestAdmin(admin.ModelAdmin):
    list_display = ('employee', 'start_date', 'end_date', 'day_count', 'status')
    list_filter = ('status',)
