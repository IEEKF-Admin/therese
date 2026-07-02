from django.urls import path
from . import views as finance_views
from .views import PSPListView, PSPCreateView, PSPUpdateView, PSPDeleteView

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
    
    # Falls du später noch weitere Views hinzufügst, kommen sie hier rein
]

