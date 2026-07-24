from django.urls import path, include
from django.views.generic import RedirectView

from .admin import therese_admin

urlpatterns = [
    # Admin
    path('admin/', therese_admin.urls),

    # Root → Tasks Dashboard
    path('', RedirectView.as_view(url='/tasks/', permanent=False), name='home'),

    # Tasks mit Namespace (wichtig für Logout + Reverse)
    path('tasks/', include('apps.tasks.urls', namespace='tasks')),

    # Accounts (Login, Logout, etc.)
    path('accounts/', include('apps.accounts.urls')),

    # HR + Finances
    path('hr/', include('apps.hr.urls')),
    path('finances/', include('apps.finances.urls')),
    path('documents/', include('apps.documents.urls')),
    path('checklists/', include('apps.checklists.urls')),
    path('chemicals/', include('apps.chemicals.urls')),
    path('orders/', include('apps.tasks.order_urls')),

    # Uploaded files served from database (login required)
    path('media/', include('apps.core.urls', namespace='core')),
]



