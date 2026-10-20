from django.urls import path

from . import views


app_name = 'notes'


urlpatterns = [
    path('', views.workspace, name='workspace'),
    path('create/', views.create_note, name='create_note'),
    path('<uuid:note_id>/update/', views.update_note, name='update_note'),
    path('versions/<uuid:version_id>/restore/', views.restore_version, name='restore_version'),
    path('<uuid:note_id>/favorite/', views.toggle_favorite, name='toggle_favorite'),
    path('<uuid:note_id>/archive/', views.archive_note, name='archive_note'),
    path('<uuid:note_id>/comments/create/', views.create_comment, name='create_comment'),
    path('<uuid:note_id>/tasks/create/', views.create_task, name='create_task'),
    path('tasks/<uuid:task_id>/status/', views.update_task_status, name='update_task_status'),
    path('attachments/<uuid:attachment_id>/delete/', views.delete_attachment, name='delete_attachment'),
    path('<uuid:note_id>/decisions/create/', views.create_decision, name='create_decision'),
    path('templates/<uuid:template_id>/use/', views.create_from_template, name='create_from_template'),
    path('api/entity/<str:entity_type>/<str:entity_id>/', views.entity_notes_json, name='entity_notes_json'),
    path('api/entity/create/', views.entity_quick_create, name='entity_quick_create'),
]
