from django.urls import path
from . import views

app_name = 'filemanager'

urlpatterns = [
    path('', views.file_list, name='file_list'),
    path('upload/', views.file_upload, name='file_upload'),
    path('download/<uuid:file_id>/', views.file_download, name='file_download'),
    path('delete/<uuid:file_id>/', views.file_delete, name='file_delete'),
    path('api/search/', views.api_search_files, name='api_search_files'),
    path('api/tags/', views.api_tags, name='api_tags'),
]