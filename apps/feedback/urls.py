from django.urls import path

from . import views

app_name = 'feedback'

urlpatterns = [
    path('', views.item_list, name='item_list'),
    path('new/', views.item_create, name='item_create'),
    path('<int:pk>/', views.item_detail, name='item_detail'),
    path('<int:pk>/edit/', views.item_edit, name='item_edit'),
    path('<int:pk>/vote/', views.item_vote, name='item_vote'),
    path('<int:pk>/comment/', views.item_comment, name='item_comment'),
    path('<int:pk>/admin/', views.item_admin, name='item_admin'),
    path('<int:pk>/delete/', views.item_delete, name='item_delete'),
    path('<int:pk>/merge/', views.item_merge, name='item_merge'),
]
