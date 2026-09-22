from django.urls import path

from . import views

app_name = 'holidays'

urlpatterns = [
    path('my/', views.my_holidays, name='my_holidays'),
    path('my/request/', views.create_holiday_request, name='create_request'),
    path('my/cancel/', views.cancel_holiday_days, name='cancel_days'),
    path('my/<int:pk>/delete/', views.delete_holiday_request, name='delete_request'),
    path('approve/', views.approve_list, name='approve_list'),
    path('gantt/', views.gantt, name='gantt'),
]
