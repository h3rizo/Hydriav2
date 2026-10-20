"""
URLs pour le module de recrutement et tests de candidats
"""
from django.urls import path
from . import views
from . import views_gestion

app_name = 'recrutement'

urlpatterns = [
    # Pages candidat
    path('inscription/', views.inscription_candidat, name='inscription'),
    path('dashboard/', views.dashboard_candidat, name='dashboard'),
    path('profil/', views.profil_candidat, name='profil'),

    # Workflow de test
    path('test/demarrer/', views.demarrer_test, name='demarrer_test'),
    path('test/<uuid:session_id>/', views.page_test, name='test'),
    path('test/<uuid:session_id>/reponse/', views.enregistrer_reponse, name='enregistrer_reponse'),
    path('test/<uuid:session_id>/soumettre/', views.soumettre_test, name='soumettre_test'),
    path('resultats/<uuid:session_id>/', views.resultats_test, name='resultats'),

    # Admin - Gestion des candidats préconfigurés
    path('gestion/candidats/', views_gestion.gestion_candidats, name='gestion_candidats'),

    # Admin - Gestion des questions de test
    path('gestion/questions/', views_gestion.gestion_questions, name='gestion_questions'),
    path('gestion/resultats/', views_gestion.gestion_resultats, name='gestion_resultats'),
    path('gestion/resultats/<uuid:candidat_id>/convocation/', views_gestion.gestion_convocation, name='gestion_convocation'),

    # APIs - Candidats préconfigurés
    path('api/candidats/', views_gestion.api_liste_candidats_v2, name='api_liste_candidats'),
    path('api/candidats/export-excel/', views_gestion.exporter_candidats_excel, name='exporter_candidats_excel'),
    path('api/candidats/import-excel/', views_gestion.importer_candidats_excel, name='importer_candidats_excel'),
    path('api/candidats/creer/', views_gestion.api_creer_candidat_preconfig_v2, name='api_creer_candidat'),
    path('api/candidats/<uuid:candidat_id>/modifier/', views_gestion.api_modifier_candidat_preconfig_v2, name='api_modifier_candidat_preconfig'),
    path('api/candidats/<uuid:candidat_id>/inviter-test/', views_gestion.api_inviter_candidat_test_v2, name='api_inviter_candidat_test'),
    path('api/candidats/<uuid:candidat_id>/supprimer/', views_gestion.api_supprimer_candidat_preconfig, name='api_supprimer_candidat'),
    path('api/candidats/envoyer-email/', views_gestion.api_envoyer_email_candidats, name='api_envoyer_email_candidats'),
    path('api/candidats/<uuid:candidat_id>/envoyer-email-entretien/', views_gestion.api_envoyer_email_entretien, name='api_envoyer_email_entretien'),
    path('api/sessions/<uuid:session_id>/resultats/', views_gestion.api_resultats_session, name='api_resultats_session'),
    path('api/candidats/<uuid:candidat_id>/reset-test/', views_gestion.api_reset_test_candidat, name='api_reset_test_candidat'),
    path('api/candidats/<uuid:candidat_id>/base/', views_gestion.api_update_candidat_base, name='api_update_candidat_base'),
    path('api/candidats/<uuid:candidat_id>/entretien/', views_gestion.api_entretien_detail, name='api_entretien_detail'),
    path('api/candidats/<uuid:candidat_id>/entretien/save/', views_gestion.api_entretien_save, name='api_entretien_save'),
    path('api/candidats/<uuid:candidat_id>/supprimer-inscrit/', views_gestion.api_supprimer_candidat_inscrit, name='api_supprimer_candidat_inscrit'),

    # APIs - Questions de test
    path('api/questions/', views_gestion.api_liste_questions, name='api_liste_questions'),
    path('api/questions/creer/', views_gestion.api_creer_question, name='api_creer_question'),
    path('api/questions/creer-serie-agent-recouvrement/', views_gestion.api_creer_serie_agent_recouvrement, name='api_creer_serie_agent_recouvrement'),
    path('api/questions/creer-serie-assistant-admin/', views_gestion.api_creer_serie_assistant_admin, name='api_creer_serie_assistant_admin'),
    path('api/questions/creer-serie-responsable-operationnel/', views_gestion.api_creer_serie_responsable_operationnel, name='api_creer_serie_responsable_operationnel'),
    path('api/questions/creer-serie-superviseur-technique/', views_gestion.api_creer_serie_superviseur_technique, name='api_creer_serie_superviseur_technique'),
    path('api/questions/creer-serie-directeur-adjoint/', views_gestion.api_creer_serie_directeur_adjoint, name='api_creer_serie_directeur_adjoint'),
    path('api/questions/<uuid:question_id>/modifier/', views_gestion.api_modifier_question, name='api_modifier_question'),
    path('api/questions/<uuid:question_id>/supprimer/', views_gestion.api_supprimer_question, name='api_supprimer_question'),
    path('api/questions-entretien/', views_gestion.api_liste_questions_entretien, name='api_liste_questions_entretien'),
    path('api/questions-entretien/creer-serie-agent-recouvrement/', views_gestion.api_creer_serie_entretien_agent_recouvrement, name='api_creer_serie_entretien_agent_recouvrement'),
    path('api/questions-entretien/creer-serie-assistant-admin/', views_gestion.api_creer_serie_entretien_assistant_admin, name='api_creer_serie_entretien_assistant_admin'),
    path('api/questions-entretien/creer-serie-responsable-operationnel/', views_gestion.api_creer_serie_entretien_responsable_operationnel, name='api_creer_serie_entretien_responsable_operationnel'),
    path('api/questions-entretien/creer-serie-superviseur-technique/', views_gestion.api_creer_serie_entretien_superviseur_technique, name='api_creer_serie_entretien_superviseur_technique'),
    path('api/questions-entretien/creer-serie-directeur-adjoint/', views_gestion.api_creer_serie_entretien_directeur_adjoint, name='api_creer_serie_entretien_directeur_adjoint'),
    path('api/questions-entretien/creer/', views_gestion.api_creer_question_entretien, name='api_creer_question_entretien'),
    path('api/questions-entretien/<uuid:question_id>/modifier/', views_gestion.api_modifier_question_entretien, name='api_modifier_question_entretien'),
    path('api/questions-entretien/<uuid:question_id>/supprimer/', views_gestion.api_supprimer_question_entretien, name='api_supprimer_question_entretien'),
]
