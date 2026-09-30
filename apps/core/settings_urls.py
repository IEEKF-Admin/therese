from django.urls import path
from django.views.generic import RedirectView

from apps.accounts.views import messaging
from apps.core import google_oauth_views, sympa_views, wordpress_views
from apps.core import views as core_views

app_name = 'core_settings'

urlpatterns = [
    path('global/', core_views.global_settings, name='global_settings'),
    path(
        'google-calendar/test/',
        google_oauth_views.google_calendar_test,
        name='google_calendar_test',
    ),
    path(
        'google-calendar/sync/',
        google_oauth_views.google_calendar_sync_all,
        name='google_calendar_sync_all',
    ),
    path('sympa/test/', sympa_views.sympa_test, name='sympa_test'),
    path('sympa/sync/', sympa_views.sympa_sync_all, name='sympa_sync_all'),
    path('wordpress/<int:pk>/test/', wordpress_views.wordpress_test, name='wordpress_test'),
    path('messaging/', messaging, name='messaging'),
    path(
        'email-environment/',
        RedirectView.as_view(pattern_name='core_settings:messaging', permanent=False),
        name='email_environment',
    ),
]
