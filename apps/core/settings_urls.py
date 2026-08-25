from django.urls import path

from . import views

app_name = 'core_settings'

urlpatterns = [
    path('email-environment/', views.email_environment, name='email_environment'),
]
