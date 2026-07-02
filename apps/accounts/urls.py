from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'accounts'

urlpatterns = [
    # Login
    path('login/', views.ThereseLoginView.as_view(), name='login'),

    # Logout
    path('logout/', auth_views.LogoutView.as_view(
        template_name='registration/logged_out.html',
        next_page='tasks:my_tasks',          # ← Hier korrigiert (mit Namespace)
    ), name='logout'),

    # Force Password Change
    path('force-password-change/', 
     views.ForcePasswordChangeView.as_view(), 
     name='force_password_change'),

    # Login Popup Settings (for staff)
    path('settings/login-popups/', views.login_popup_settings, name='login_popup_settings'),
]

