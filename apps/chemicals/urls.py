from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = 'chemicals'

urlpatterns = [
    path('', views.chemical_item_list, name='chemical_item_list'),
    path('substances/', views.chemical_list, name='chemical_list'),
    path('substances/new/', views.chemical_create, name='chemical_create'),
    path('substances/<int:pk>/edit/', views.chemical_edit, name='chemical_edit'),
    path('items/', views.chemical_item_list, name='chemical_item_list_alt'),
    path('items/<int:pk>/edit/', views.chemical_item_edit, name='chemical_item_edit'),
    # Legacy URL → /orders/undelivered/
    path(
        'undelivered/',
        RedirectView.as_view(pattern_name='orders:undelivered_items', permanent=False),
        name='undelivered_items',
    ),
    path('api/cas-check/', views.cas_check, name='cas_check'),
]
