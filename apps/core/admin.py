from django.contrib import admin
from .models import GlobalSetting

@admin.register(GlobalSetting)
class GlobalSettingAdmin(admin.ModelAdmin):
    list_display = ['default_weekly_hours', 'updated_at']
    readonly_fields = ['updated_at']
