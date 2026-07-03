"""
apps/hr/urls.py
"""
from django.urls import path
from .views.employee import (
    employee_list, EmployeeCreateView, EmployeeUpdateView, MyProfileView,
    WorkgroupListView, WorkgroupCreateView, WorkgroupUpdateView, WorkgroupDeleteView, LocationManagementView,
    BuildingCreateView, BuildingUpdateView,
    RoomCreateView, RoomUpdateView,
    PhoneNumberCreateView, PhoneNumberUpdateView,
    BuildingDeleteView, RoomDeleteView, PhoneNumberDeleteView,
)
from .views.ajax import ajax_rooms_by_building, ajax_phonenumbers_by_room
from .views.documents import employee_document_download, employee_document_delete
from apps.finances import views as finance_views

app_name = 'hr'

urlpatterns = [
    # Employee Management
    path('employees/', employee_list, name='employee_list'),
    path('employees/new/', EmployeeCreateView.as_view(), name='employee_create'),
    path('employees/<int:pk>/edit/', EmployeeUpdateView.as_view(), name='employee_update'),
    path('employees/<int:employee_pk>/documents/<int:version_pk>/download/', employee_document_download, name='employee_document_download'),
    path('employees/<int:employee_pk>/documents/<int:version_pk>/delete/', employee_document_delete, name='employee_document_delete'),
    path('my-profile/', MyProfileView.as_view(), name='my_profile'),
    
    # AJAX Cascading Dropdowns
    path('ajax/rooms-by-building/', ajax_rooms_by_building, name='ajax_rooms_by_building'),
    path('ajax/phonenumbers-by-room/', ajax_phonenumbers_by_room, name='ajax_phonenumbers_by_room'),
    
    # Import (aus Finances)
    path('import-wbs-elements/', finance_views.import_wbs_elements, name='import_wbs_elements'),

    # Assisting Admins dedicated views
    path('workgroups/', WorkgroupListView.as_view(), name='workgroup_list'),
    path('workgroups/new/', WorkgroupCreateView.as_view(), name='workgroup_create'),
    path('workgroups/<int:pk>/edit/', WorkgroupUpdateView.as_view(), name='workgroup_update'),
    path('workgroups/<int:pk>/delete/', WorkgroupDeleteView.as_view(), name='workgroup_delete'),

    # Buildings, Rooms, Phones management (dedicated non-admin views)
    path('locations/', LocationManagementView.as_view(), name='location_management'),
    # Building CRUD
    path('locations/buildings/new/', BuildingCreateView.as_view(), name='building_create'),
    path('locations/buildings/<int:pk>/edit/', BuildingUpdateView.as_view(), name='building_update'),
    path('locations/buildings/<int:pk>/delete/', BuildingDeleteView.as_view(), name='building_delete'),
    # Room CRUD
    path('locations/rooms/new/', RoomCreateView.as_view(), name='room_create'),
    path('locations/rooms/<int:pk>/edit/', RoomUpdateView.as_view(), name='room_update'),
    path('locations/rooms/<int:pk>/delete/', RoomDeleteView.as_view(), name='room_delete'),
    # PhoneNumber CRUD
    path('locations/phones/new/', PhoneNumberCreateView.as_view(), name='phone_create'),
    path('locations/phones/<int:pk>/edit/', PhoneNumberUpdateView.as_view(), name='phone_update'),
    path('locations/phones/<int:pk>/delete/', PhoneNumberDeleteView.as_view(), name='phone_delete'),
]

