from django.urls import path
from . import views as finance_views

app_name = 'finances'

urlpatterns = [
    # Import Views
    path('import-cost-centers/', finance_views.import_cost_centers, name='import_cost_centers'),
    path('import-wbs-elements/', finance_views.import_wbs_elements, name='import_wbs_elements'),
    
    # Falls du spÃ¤ter noch weitere Views hinzufÃ¼gst, kommen sie hier rein
]

