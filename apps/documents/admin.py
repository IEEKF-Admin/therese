from therese.admin import therese_admin
from .models import Document, DocumentVersion, DocumentTag, DocumentShare, UserDocumentArchive


@therese_admin.register(Document)
class DocumentAdmin(therese_admin.ModelAdmin):
    list_display = ('title', 'created_by', 'created_at')
    search_fields = ('title', 'description')
    filter_horizontal = ('tags',)


@therese_admin.register(DocumentVersion)
class DocumentVersionAdmin(therese_admin.ModelAdmin):
    list_display = ('document', 'version_number', 'uploaded_by', 'uploaded_at')
    list_filter = ('uploaded_at',)


@therese_admin.register(DocumentTag)
class DocumentTagAdmin(therese_admin.ModelAdmin):
    list_display = ('name', 'created_by')


@therese_admin.register(DocumentShare)
class DocumentShareAdmin(therese_admin.ModelAdmin):
    list_display = ('document', 'share_type', 'permission', 'shared_at')


@therese_admin.register(UserDocumentArchive)
class UserDocumentArchiveAdmin(therese_admin.ModelAdmin):
    list_display = ('user', 'document', 'archived_at')

