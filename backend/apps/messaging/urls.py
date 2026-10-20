from django.urls import path
from . import views

app_name = 'messaging'

urlpatterns = [
    # Conversations
    path('', views.conversations_list, name='conversations_list'),
    path('conversation/<int:conversation_id>/', views.conversation_detail, name='conversation_detail'),
    path('conversation/create/', views.conversation_create, name='conversation_create'),

    # Messages
    path('conversation/<int:conversation_id>/send/', views.message_send, name='message_send'),
    path('message/<int:message_id>/delete/', views.message_delete, name='message_delete'),
    path('conversation/<int:conversation_id>/messages/', views.messages_api, name='messages_api'),
    path('unread-count/', views.unread_count_api, name='unread_count_api'),

    # Appels
    path('conversation/<int:conversation_id>/call/start/', views.call_start, name='call_start'),
    path('call/<int:call_id>/end/', views.call_end, name='call_end'),

    # Rappel mensuel factures non pointees - formulaire de commentaires
    path(
        'rappels/<int:annee>/<int:mois>/<uuid:employe_id>/',
        views.commentaire_relance,
        name='commentaire_relance',
    ),
]
