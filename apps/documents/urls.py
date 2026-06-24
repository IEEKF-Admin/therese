from django.urls import path
from . import views

app_name = 'documents'

urlpatterns = [
    path('', views.document_list, name='document_list'),
    path('upload/', views.document_upload, name='document_upload'),
    path('<int:pk>/', views.document_detail, name='document_detail'),
    path('<int:pk>/edit/', views.document_edit, name='document_edit'),
    path('<int:pk>/upload-version/', views.document_upload_version, name='document_upload_version'),
    path('<int:pk>/shares/', views.document_manage_shares, name='document_manage_shares'),
    path('download/<int:version_pk>/', views.document_download, name='document_download'),
    path('preview/<int:version_pk>/', views.document_preview, name='document_preview'),
]