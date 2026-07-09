from django.urls import path
from . import views as finance_views
from .views import (
    CostCenterCreateView,
    CostCenterDeleteView,
    CostCenterListView,
    CostCenterUpdateView,
    PSPListView,
    PSPCreateView,
    PSPUpdateView,
    PSPDeleteView,
)

app_name = 'finances'

urlpatterns = [
    # Import Views
    path('import-cost-centers/', finance_views.import_cost_centers, name='import_cost_centers'),
    path('import-wbs-elements/', finance_views.import_wbs_elements, name='import_wbs_elements'),
    path('import-pay-scales/', finance_views.import_pay_scales, name='import_pay_scales'),
    path('psp-elements/', finance_views.psp_elements, name='psp_elements'),

    # Assisting Admins - PSP Elements (WBS) CRUD
    path('psp/manage/', PSPListView.as_view(), name='psp_manage'),
    path('psp/manage/new/', PSPCreateView.as_view(), name='psp_create'),
    path('psp/manage/<int:pk>/edit/', PSPUpdateView.as_view(), name='psp_update'),
    path('psp/manage/<int:pk>/delete/', PSPDeleteView.as_view(), name='psp_delete'),

    # Assisting Admins - Cost Centers CRUD
    path('cost-centers/manage/', CostCenterListView.as_view(), name='cost_center_manage'),
    path('cost-centers/manage/new/', CostCenterCreateView.as_view(), name='cost_center_create'),
    path('cost-centers/manage/<int:pk>/edit/', CostCenterUpdateView.as_view(), name='cost_center_update'),
    path('cost-centers/manage/<int:pk>/delete/', CostCenterDeleteView.as_view(), name='cost_center_delete'),
]

