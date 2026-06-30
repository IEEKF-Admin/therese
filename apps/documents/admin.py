from django.contrib import admin
from therese.admin import therese_admin
from .models import Document, DocumentVersion, DocumentTag, DocumentShare, UserDocumentArchive


@admin.register(Document, site=therese_admin)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'created_by', 'created_at')
    search_fields = ('title', 'description')
    filter_horizontal = ('tags',)


@admin.register(DocumentVersion, site=therese_admin)
class DocumentVersionAdmin(admin.ModelAdmin):
    list_display = ('document', 'version_number', 'uploaded_by', 'uploaded_at')
    list_filter = ('uploaded_at',)


@admin.register(DocumentTag, site=therese_admin)
class DocumentTagAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_by')


@admin.register(DocumentShare, site=therese_admin)
class DocumentShareAdmin(admin.ModelAdmin):
    list_display = ('document', 'share_type', 'permission', 'shared_at')


@admin.register(UserDocumentArchive, site=therese_admin)
class UserDocumentArchiveAdmin(admin.ModelAdmin):
    list_display = ('user', 'document', 'archived_at')

