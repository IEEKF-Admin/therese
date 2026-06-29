from django.contrib import admin
from .models import Document, DocumentVersion, DocumentTag, DocumentShare, UserDocumentArchive


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'created_by', 'created_at')
    search_fields = ('title', 'description')
    filter_horizontal = ('tags',)


@admin.register(DocumentVersion)
class DocumentVersionAdmin(admin.ModelAdmin):
    list_display = ('document', 'version_number', 'uploaded_by', 'uploaded_at')
    list_filter = ('uploaded_at',)


@admin.register(DocumentTag)
class DocumentTagAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_by')


@admin.register(DocumentShare)
class DocumentShareAdmin(admin.ModelAdmin):
    list_display = ('document', 'share_type', 'permission', 'shared_at')


@admin.register(UserDocumentArchive)
class UserDocumentArchiveAdmin(admin.ModelAdmin):
    list_display = ('user', 'document', 'archived_at')