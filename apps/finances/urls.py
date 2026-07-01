from django.urls import path
from . import views as finance_views

app_name = 'finances'

urlpatterns = [
    # Import Views
    path('import-cost-centers/', finance_views.import_cost_centers, name='import_cost_centers'),
    path('import-wbs-elements/', finance_views.import_wbs_elements, name='import_wbs_elements'),
    path('import-pay-scales/', finance_views.import_pay_scales, name='import_pay_scales'),
    path('psp-elements/', finance_views.psp_elements, name='psp_elements'),
    
    # Falls du später noch weitere Views hinzufügst, kommen sie hier rein
]

