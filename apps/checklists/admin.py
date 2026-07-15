from django.contrib import admin

from apps.checklists.models import (
    ChecklistAssignmentAck,
    ChecklistFieldResponse,
    ChecklistInstance,
    ChecklistTemplate,
    ChecklistTemplateNode,
    ChecklistTemplateVersion,
)
from therese.admin import therese_admin


class ChecklistTemplateNodeInline(admin.TabularInline):
    model = ChecklistTemplateNode
    extra = 0
    fields = (
        'parent', 'sort_order', 'node_kind', 'field_type', 'choice_key',
        'label_en', 'label_de', 'required_for_completion', 'visible_to_subject',
    )
    ordering = ('sort_order', 'pk')


class ChecklistTemplateVersionInline(admin.TabularInline):
    model = ChecklistTemplateVersion
    extra = 0
    fields = ('version_number', 'status', 'completion_mode', 'anchor_node', 'published_at')
    readonly_fields = ('published_at',)
    show_change_link = True


@admin.register(ChecklistTemplate, site=therese_admin)
class ChecklistTemplateAdmin(admin.ModelAdmin):
    list_display = ('slug', 'name_en', 'name_de')
    search_fields = ('slug', 'name_en', 'name_de')
    prepopulated_fields = {'slug': ('name_en',)}
    inlines = [ChecklistTemplateVersionInline]


@admin.register(ChecklistTemplateVersion, site=therese_admin)
class ChecklistTemplateVersionAdmin(admin.ModelAdmin):
    list_display = ('template', 'version_number', 'status', 'completion_mode', 'published_at')
    list_filter = ('status', 'completion_mode')
    inlines = [ChecklistTemplateNodeInline]


@admin.register(ChecklistInstance, site=therese_admin)
class ChecklistInstanceAdmin(admin.ModelAdmin):
    list_display = ('subject', 'template_version', 'status', 'assigned_at', 'completed_at')
    list_filter = ('status',)
    raw_id_fields = ('subject', 'template_version', 'assigned_by', 'completed_by')


therese_admin.register(ChecklistFieldResponse)
therese_admin.register(ChecklistAssignmentAck)
