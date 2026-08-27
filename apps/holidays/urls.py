from django.urls import path

from . import views

app_name = 'holidays'

urlpatterns = [
    path('my/', views.my_holidays, name='my_holidays'),
    path('my/request/', views.create_holiday_request, name='create_request'),
    path('my/<int:pk>/delete/', views.delete_holiday_request, name='delete_request'),
    path('my/<int:pk>/pdf/', views.request_pdf, name='request_pdf'),
    path('approve/', views.approve_list, name='approve_list'),
    path('gantt/', views.gantt, name='gantt'),
]
