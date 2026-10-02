from django.contrib import admin

from therese.admin import therese_admin
from .models import Course, CourseCompletion, CourseManager


class CourseManagerInline(admin.TabularInline):
    model = CourseManager
    extra = 0
    raw_id_fields = ['employee']


@admin.register(Course, site=therese_admin)
class CourseAdmin(admin.ModelAdmin):
    list_display = ['name', 'repeat_label', 'evidence_type', 'is_active', 'all_institute']
    list_filter = ['is_active', 'evidence_type', 'all_institute']
    search_fields = ['name']
    filter_horizontal = ['workgroups', 'extra_employees', 'substitutes_for']
    inlines = [CourseManagerInline]


@admin.register(CourseCompletion, site=therese_admin)
class CourseCompletionAdmin(admin.ModelAdmin):
    list_display = ['course', 'employee', 'completed_on', 'checked']
    list_filter = ['course']
    raw_id_fields = ['course', 'employee', 'recorded_by']
