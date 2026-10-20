from django.urls import path
from . import views

app_name = 'chatbot'

urlpatterns = [
    # Interface principale
    path('', views.chat_interface, name='chat_interface'),
    
    # API endpoints
    path('api/send-message/', views.send_message, name='send_message'),
    path('api/sessions/', views.list_sessions, name='list_sessions'),
    path('api/session/<int:session_id>/', views.get_session, name='get_session'),
    path('api/session/<int:session_id>/messages/', views.get_messages, name='get_messages'),
    path('api/create-session/', views.create_session, name='create_session'),
    path('api/delete-session/<int:session_id>/', views.delete_session, name='delete_session'),
    
    # Export endpoints
    path('api/export/pdf/<int:session_id>/', views.export_session_pdf, name='export_pdf'),
    path('api/export/excel/<int:session_id>/', views.export_session_excel, name='export_excel'),
    path('api/generate-report/', views.generate_report, name='generate_report'),
    
    # Recherche
    path('api/search/', views.search_sessions, name='search_sessions'),
    
    # Téléchargement de rapports
    path('download/<str:filename>/', views.download_report, name='download_report'),
    
    # =============================================================================
    # URLS POUR LES CONVERSATIONS ENTRE UTILISATEURS
    # =============================================================================
    
    # Menu principal du chat
    path('menu/', views.chat_menu, name='chat_menu'),
    
    # Interface conversations
    path('conversations/', views.conversations_list, name='conversations_list'),
    path('conversations/<uuid:conversation_id>/', views.conversation_detail, name='conversation_detail'),
    
    # API conversations
    path('api/conversations/', views.api_conversations_list, name='api_conversations_list'),
    path('api/conversations/create/', views.api_create_conversation, name='api_create_conversation'),
    path('api/conversations/<uuid:conversation_id>/messages/', views.api_conversation_messages, name='api_conversation_messages'),
    path('api/conversations/<uuid:conversation_id>/send/', views.api_send_conversation_message, name='api_send_conversation_message'),
    
    # API réactions et utilisateurs
    path('api/messages/<uuid:message_id>/reaction/', views.api_add_reaction, name='api_add_reaction'),
    path('api/search-users/', views.api_search_users, name='api_search_users'),
    
    # API gestion des groupes
    path('api/conversations/<uuid:conversation_id>/participants/', views.api_conversation_participants, name='api_conversation_participants'),
    path('api/conversations/<uuid:conversation_id>/participants/add/', views.api_add_participant, name='api_add_participant'),
    path('api/conversations/<uuid:conversation_id>/participants/<int:user_id>/remove/', views.api_remove_participant, name='api_remove_participant'),
]