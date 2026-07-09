from django.urls import path

from .views import serve_stored_file

app_name = 'core'

urlpatterns = [
    path('<path:file_path>', serve_stored_file, name='stored_file'),
]