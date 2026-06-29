"""
apps/hr/urls.py
"""
from django.urls import path
from .views.employee import employee_list, EmployeeCreateView, EmployeeUpdateView
from .views.ajax import ajax_rooms_by_building, ajax_phonenumbers_by_room
from apps.finances import views as finance_views

app_name = 'hr'

urlpatterns = [
    # Employee Management
    path('employees/', employee_list, name='employee_list'),
    path('employees/new/', EmployeeCreateView.as_view(), name='employee_create'),
    path('employees/<int:pk>/edit/', EmployeeUpdateView.as_view(), name='employee_update'),
    
    # AJAX Cascading Dropdowns
    path('ajax/rooms-by-building/', ajax_rooms_by_building, name='ajax_rooms_by_building'),
    path('ajax/phonenumbers-by-room/', ajax_phonenumbers_by_room, name='ajax_phonenumbers_by_room'),
    
    # Import (aus Finances)
    path('import-wbs-elements/', finance_views.import_wbs_elements, name='import_wbs_elements'),
]