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
from therese.admin import therese_admin
from .models import DataImportLog, GlobalSetting, StoredFile


@admin.register(GlobalSetting, site=therese_admin)
class GlobalSettingAdmin(admin.ModelAdmin):
    list_display = ['default_weekly_hours', 'true_cost_multiplicator', 'updated_at']
    fields = ['default_weekly_hours', 'true_cost_multiplicator', 'updated_at']
    readonly_fields = ['updated_at']


@admin.register(StoredFile, site=therese_admin)
class StoredFileAdmin(admin.ModelAdmin):
    list_display = ['original_filename', 'name', 'content_type', 'size', 'created_at']
    search_fields = ['name', 'original_filename']
    readonly_fields = ['name', 'original_filename', 'content_type', 'size', 'created_at', 'updated_at']


@admin.register(DataImportLog, site=therese_admin)
class DataImportLogAdmin(admin.ModelAdmin):
    list_display = (
        'created_at',
        'kind',
        'status',
        'original_filename',
        'uploaded_by',
        'file_size',
        'file_created_at',
        'report_created_on',
        'beleg_from',
        'beleg_to',
    )
    list_filter = ('kind', 'status', 'created_at')
    search_fields = (
        'original_filename',
        'file_sha256',
        'summary',
        'uploaded_by__username',
        'uploaded_by__email',
    )
    readonly_fields = (
        'kind',
        'uploaded_by',
        'original_filename',
        'file_sha256',
        'file_size',
        'file_created_at',
        'file_modified_at',
        'report_created_on',
        'beleg_from',
        'beleg_to',
        'status',
        'summary',
        'created_at',
        'updated_at',
    )
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'


