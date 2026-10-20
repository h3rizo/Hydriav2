from django.urls import path
from . import views
from . import views_manuel

app_name = 'system'

urlpatterns = [
    # Pages principales
    path('users/', views.users_management, name='users_management'),
    path('parameters/', views.system_parameters, name='system_parameters'),
    path('backup/download/', views.download_data_backup, name='download_data_backup'),
    path('backup/postgres/download/', views.download_postgres_backup, name='download_postgres_backup'),
    path('logs/', views.logs_monitoring, name='logs_monitoring'),
    path('stockage/', views.storage_monitoring, name='storage_monitoring'),
    path('manuel/', views_manuel.manuel_utilisateur, name='manuel_utilisateur'),
    path('manuel/telecharger/', views_manuel.telecharger_manuel, name='telecharger_manuel'),

    # APIs Gestion Utilisateurs
    path('api/users/', views.api_users_list, name='api_users_list'),
    path('api/users/create/', views.api_user_create, name='api_user_create'),
    path('api/users/<int:user_id>/update/', views.api_user_update, name='api_user_update'),
    path('api/users/<int:user_id>/delete/', views.api_user_delete, name='api_user_delete'),

    # APIs Parametres Systeme
    path('api/parameters/', views.api_parameters_list, name='api_parameters_list'),
    path('api/parameters/<uuid:param_id>/update/', views.api_parameter_update, name='api_parameter_update'),
    
    # Password management
    path('password-reset/', views.password_reset_request, name='password_reset_request'),
    path('password-reset/verify/', views.password_reset_verify, name='password_reset_verify'),
    path('password-change/', views.password_change, name='password_change'),

    # APIs Logs & Monitoring
    path('api/logs/', views.api_logs_list, name='api_logs_list'),
    path('api/logs/stats/', views.api_logs_stats, name='api_logs_stats'),
    
    # Presence API
    path('api/presence/update/', views.api_presence_update, name='api_presence_update'),

    # Rappel mensuel factures non pointees (paiements seuls - conserve par
    # URL directe pour diagnostic isole, retire du menu de navigation)
    path('relances-factures/', views.preview_relances_factures, name='preview_relances_factures'),
    path('relances-factures/detail/<uuid:employe_id>/', views.preview_relance_detail, name='preview_relance_detail'),
    path('relances-factures/test/', views.envoyer_relances_test, name='envoyer_relances_test'),
    path('relances-factures/envoyer/', views.envoyer_relances_reelles, name='envoyer_relances_reelles'),

    # Rappel combine (paiements non pointes + reparations echues, regroupe par ouvrage)
    path('situations-attention/', views.preview_situations_attention, name='preview_situations_attention'),
    path('situations-attention/detail/<uuid:employe_id>/', views.preview_situation_detail, name='preview_situation_detail'),
    path('situations-attention/test/', views.envoyer_situations_attention_test, name='envoyer_situations_attention_test'),
    path('situations-attention/envoyer/', views.envoyer_situations_attention_reelles, name='envoyer_situations_attention_reelles'),
]
