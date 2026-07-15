from django.urls import path

from . import views

app_name = 'checklists'

urlpatterns = [
    path('my/', views.my_list, name='my_list'),
    path('my/<int:pk>/', views.instance_fill, name='instance_fill'),
    path('manage/', views.manage_template_list, name='manage_template_list'),
    path('manage/templates/<int:pk>/', views.manage_template_detail, name='manage_template_detail'),
    path('manage/assign/', views.manage_assign, name='manage_assign'),
    path('progress/workgroup/', views.progress_workgroup, name='progress_workgroup'),
    path('progress/institute/', views.progress_institute, name='progress_institute'),
    path('instances/<int:pk>/view/', views.instance_view, name='instance_view'),
    path('instances/<int:pk>/file/<int:response_pk>/', views.instance_file_download, name='instance_file_download'),
    path('instances/<int:pk>/complete/', views.instance_complete, name='instance_complete'),
]
