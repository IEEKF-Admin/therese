"""
apps/tasks/urls.py

URL routing for the tasks application (dashboard, create, detail router, admin).

Do not remove any existing requirements from this module without explicit instruction.
"""
from django.urls import path

from .views.dashboard import my_tasks
from .views.create import TaskCreateView, choose_task_type
from .views.delete import task_delete
from .views.router import task_detail
from .views.personnel_documents import (
    personnel_task_document_download,
    personnel_task_documents_zip,
)
from .views.purchase_quote import (
    purchase_order_quote_download,
    purchase_order_quote_replace,
)

# Standard Orders views (from the dedicated submodule)
from .views.workflow_admin import (
    TaskWorkflowConfigListView,
    TaskWorkflowConfigUpdateView,
)
from .views.recruitment_admin import (
    LimitationReasonCreateView,
    LimitationReasonDeleteView,
    LimitationReasonListView,
    LimitationReasonUpdateView,
    RecruitmentJobCreateView,
    RecruitmentJobDeleteView,
    RecruitmentJobListView,
    RecruitmentJobUpdateView,
)
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
    path('<int:pk>/quote/download/', purchase_order_quote_download, name='purchase_order_quote_download'),
    path('<int:pk>/quote/replace/', purchase_order_quote_replace, name='purchase_order_quote_replace'),
    path('<int:pk>/', task_detail, name='task_detail'),
    path('<int:pk>/documents/download-all/', personnel_task_documents_zip, name='personnel_task_documents_zip'),
    path('<int:pk>/documents/<slug:doc_key>/', personnel_task_document_download, name='personnel_task_document_download'),
    path('<int:pk>/delete/', task_delete, name='task_delete'),

    # Standard Purchase Items (Catalog / Standard Orders)
    path('standard-orders/', standard_orders_list, name='standard_orders_list'),
    path('standard-orders/new/', standard_order_create, name='standard_order_create'),
    path('standard-orders/<int:pk>/edit/', standard_order_edit, name='standard_order_edit'),
    path('standard-orders/<int:pk>/delete/', standard_order_delete, name='standard_order_delete'),
    path('standard-orders/select/', standard_order_select, name='standard_order_select'),
    path('standard-orders/image/<int:pk>/', standard_item_thumbnail, name='standard_item_thumbnail'),
    path('<int:pk>/standardize/', save_standard_checkboxes, name='save_standard_checkboxes'),

    # Task workflow administration (HR Superassistant)
    path('admin/workflow/', TaskWorkflowConfigListView.as_view(), name='workflow_config_manage'),
    path('admin/workflow/<int:pk>/', TaskWorkflowConfigUpdateView.as_view(), name='workflow_config_update'),

    # Recruitment administration (HR Superassistant)
    path('admin/jobs/', RecruitmentJobListView.as_view(), name='recruitment_job_manage'),
    path('admin/jobs/new/', RecruitmentJobCreateView.as_view(), name='recruitment_job_create'),
    path('admin/jobs/<int:pk>/edit/', RecruitmentJobUpdateView.as_view(), name='recruitment_job_update'),
    path('admin/jobs/<int:pk>/delete/', RecruitmentJobDeleteView.as_view(), name='recruitment_job_delete'),
    path('admin/limitation-reasons/', LimitationReasonListView.as_view(), name='limitation_reason_manage'),
    path('admin/limitation-reasons/new/', LimitationReasonCreateView.as_view(), name='limitation_reason_create'),
    path('admin/limitation-reasons/<int:pk>/edit/', LimitationReasonUpdateView.as_view(), name='limitation_reason_update'),
    path('admin/limitation-reasons/<int:pk>/delete/', LimitationReasonDeleteView.as_view(), name='limitation_reason_delete'),
]

app_name = 'tasks'

