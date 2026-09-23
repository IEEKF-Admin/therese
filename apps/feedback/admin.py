from django.contrib import admin

from therese.admin import therese_admin
from .models import FeedbackComment, FeedbackItem, FeedbackVote


@admin.register(FeedbackItem, site=therese_admin)
class FeedbackItemAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'kind', 'title', 'status', 'created_by', 'target_date', 'merged_into',
    ]
    list_filter = ['kind', 'status']
    search_fields = ['title', 'description', 'page_url']
    raw_id_fields = ['created_by', 'merged_into']


@admin.register(FeedbackComment, site=therese_admin)
class FeedbackCommentAdmin(admin.ModelAdmin):
    list_display = ['id', 'item', 'author', 'created_at']
    raw_id_fields = ['item', 'author']


@admin.register(FeedbackVote, site=therese_admin)
class FeedbackVoteAdmin(admin.ModelAdmin):
    list_display = ['item', 'employee', 'created_at']
    raw_id_fields = ['item', 'employee']
