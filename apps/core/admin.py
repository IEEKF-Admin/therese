"""
apps/core/admin.py

Project: THERESE - Transparent HR Employee Resource Evaluation System Enhanced

Features / Requirements:
- Admin interface for GlobalSetting
- All user-facing text must be in English
- Header block must be maintained and only extended when new requirements are explicitly added

Do not remove any existing requirements from this header without explicit instruction.
"""

from django.contrib import admin
from .models import GlobalSetting


@admin.register(GlobalSetting)
class GlobalSettingAdmin(admin.ModelAdmin):
    list_display = ['default_weekly_hours', 'updated_at']
    readonly_fields = ['updated_at']
