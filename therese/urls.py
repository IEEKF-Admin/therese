from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),

    # Root → Tasks Dashboard
    path('', RedirectView.as_view(url='/tasks/', permanent=False), name='home'),

    # Tasks mit Namespace (wichtig für Logout + Reverse)
    path('tasks/', include('apps.tasks.urls', namespace='tasks')),

    # Accounts (Login, Logout, etc.)
    path('accounts/', include('apps.accounts.urls')),

    # HR + Finances
    path('hr/', include('apps.hr.urls')),
    path('finances/', include('apps.finances.urls')),
]