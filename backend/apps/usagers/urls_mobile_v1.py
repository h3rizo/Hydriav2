from django.urls import path

from . import mobile_api_v1

app_name = 'usagers_mobile_v1'

urlpatterns = [
    path('bootstrap', mobile_api_v1.bootstrap, name='bootstrap'),
    path('changes', mobile_api_v1.changes, name='changes'),
    path('mutations', mobile_api_v1.mutations, name='mutations'),
    path('reunions/<uuid:reunion_id>/pieces-jointes', mobile_api_v1.piece_jointe_upload, name='piece_jointe_upload'),
    path('notes/entity/<str:entity_type>/<str:entity_id>', mobile_api_v1.notes_for_entity, name='notes_for_entity'),
    path('notes/entity/create', mobile_api_v1.notes_quick_create, name='notes_quick_create'),
    path('notes/<uuid:note_id>/tasks/create', mobile_api_v1.notes_add_task, name='notes_add_task'),
]
