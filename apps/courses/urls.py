from django.urls import path

from . import views

app_name = 'courses'

urlpatterns = [
    path('', views.hub, name='hub'),
    path('my/', views.my_courses, name='my_courses'),
    path('<int:pk>/', views.course_list, name='course_list'),
    path('<int:pk>/record/', views.record, name='record'),
]
