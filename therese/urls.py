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
    path('documents/', include('apps.documents.urls', namespace='documents')),
    path('finances/', include('apps.finances.urls')),
<<<<<<< HEAD
]
=======
]


# ============================================================
# CUSTOM ADMIN PERMISSION CHECK
# ============================================================
# By default Django admin requires is_staff=True.
# For fresh installations it is useful if a pure superuser
# (created via createsuperuser) can also access /admin/ .
# We therefore also grant access to active superusers.
from django.contrib import admin as _admin

_original_has_permission = _admin.site.has_permission

def _has_permission(self, request):
    return _original_has_permission(self, request) or (
        request.user.is_active and getattr(request.user, "is_superuser", False)
    )

_admin.site.has_permission = _has_permission.__get__(_admin.site, _admin.AdminSite)
>>>>>>> new-main
