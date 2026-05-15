"""
apps/tasks/urls.py
"""
from django.urls import path

# Direkte Imports
from .views.dashboard import my_tasks
from .views.create import TaskCreateView, choose_task_type
from .views.delete import task_delete

# Router importieren (jetzt über die neue Datei)
from .views.router import task_detail

urlpatterns = [
    path('', my_tasks, name='my_tasks'),
    path('create/', choose_task_type, name='choose_task_type'),
    path('create/new/', TaskCreateView.as_view(), name='task_create'),
    path('<int:pk>/', task_detail, name='task_detail'),
    path('<int:pk>/delete/', task_delete, name='task_delete'),
]

app_name = 'tasks'