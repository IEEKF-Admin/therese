from django.urls import path
from django.views.generic import RedirectView

from apps.accounts.views import messaging
from apps.core import views as core_views

app_name = 'core_settings'

urlpatterns = [
    path('global/', core_views.global_settings, name='global_settings'),
    path('messaging/', messaging, name='messaging'),
    path(
        'email-environment/',
        RedirectView.as_view(pattern_name='core_settings:messaging', permanent=False),
        name='email_environment',
    ),
]
