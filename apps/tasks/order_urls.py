"""URLs under /orders/ (purchase-order operations outside /tasks/)."""

from django.urls import path

from apps.tasks.views.undelivered import undelivered_purchase_items

app_name = 'orders'

urlpatterns = [
    path('undelivered/', undelivered_purchase_items, name='undelivered_items'),
]
