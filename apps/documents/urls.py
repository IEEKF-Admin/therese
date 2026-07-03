from django.urls import path

from . import views

app_name = 'documents'

urlpatterns = [
    path('', views.document_list, name='list'),
    path('<int:pk>/', views.document_detail, name='detail'),
    path('<int:pk>/version/<int:version_pk>/', views.document_detail, name='detail_version'),
    path('<int:pk>/pdf/', views.document_pdf, name='pdf'),
    path('<int:pk>/version/<int:version_pk>/pdf/', views.document_pdf, name='pdf_version'),
    path('<int:pk>/ack/confirm/', views.document_ack_confirm, name='ack_confirm'),
    path('<int:pk>/ack/decline/', views.document_ack_decline, name='ack_decline'),
    path('<int:pk>/ack/reconsider/', views.document_ack_reconsider, name='ack_reconsider'),

    path('manage/', views.manage_document_list, name='manage_list'),
    path('manage/create/', views.manage_document_create, name='manage_create'),
    path('manage/upload-image/', views.upload_editor_image, name='upload_editor_image'),
    path('manage/categories/', views.manage_categories, name='manage_categories'),
    path('manage/matrix/', views.read_ack_matrix, name='read_ack_matrix'),
    path('manage/<int:pk>/', views.manage_document_detail, name='manage_detail'),
    path('manage/<int:pk>/edit/', views.manage_document_edit, name='manage_edit'),
    path(
        'manage/<int:pk>/attachments/<int:attachment_pk>/delete/',
        views.manage_attachment_delete,
        name='manage_attachment_delete',
    ),
    path('manage/<int:pk>/publish/', views.manage_document_publish, name='manage_publish'),
    path('manage/<int:pk>/new-version/', views.manage_document_new_version, name='manage_new_version'),
    path('manage/<int:pk>/archive/', views.manage_document_archive, name='manage_archive'),
]