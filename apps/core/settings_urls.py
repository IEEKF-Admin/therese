from django.urls import path
from django.views.generic import RedirectView

from apps.accounts.views import messaging

app_name = 'core_settings'

urlpatterns = [
    path('messaging/', messaging, name='messaging'),
    path(
        'email-environment/',
        RedirectView.as_view(pattern_name='core_settings:messaging', permanent=False),
        name='email_environment',
    ),
]
