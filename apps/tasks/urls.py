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

# Standard Orders views (from the dedicated submodule)
from .views.standard_orders import (
    standard_orders_list,
    standard_order_create,
    standard_order_edit,
    standard_order_delete,
    standard_order_select,
    standard_item_thumbnail,
    save_standard_checkboxes,
)

urlpatterns = [
    path('', my_tasks, name='my_tasks'),
    path('create/', choose_task_type, name='choose_task_type'),
    path('create/new/', TaskCreateView.as_view(), name='task_create'),
    path('<int:pk>/', task_detail, name='task_detail'),
    path('<int:pk>/delete/', task_delete, name='task_delete'),

    # Standard Purchase Items (Catalog / Standard Orders)
    path('standard-orders/', standard_orders_list, name='standard_orders_list'),
    path('standard-orders/new/', standard_order_create, name='standard_order_create'),
    path('standard-orders/<int:pk>/edit/', standard_order_edit, name='standard_order_edit'),
    path('standard-orders/<int:pk>/delete/', standard_order_delete, name='standard_order_delete'),
    path('standard-orders/select/', standard_order_select, name='standard_order_select'),
    path('standard-orders/image/<int:pk>/', standard_item_thumbnail, name='standard_item_thumbnail'),
    path('<int:pk>/standardize/', save_standard_checkboxes, name='save_standard_checkboxes'),
]

app_name = 'tasks'