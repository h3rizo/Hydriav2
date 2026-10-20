"""
URLs pour l'app usagers
"""

from django.urls import path
from . import views, views_reseau, views_reunions, views_autorites_tiers

app_name = 'usagers'

urlpatterns = [
    path('reseau/', views_reseau.reseau_entry_index, name='reseau_entry_index'),
    path('reseau/<slug:session_slug>/', views_reseau.reseau_entry, name='reseau_entry'),
    path('reseau/<slug:session_slug>/acces/', views_reseau.reseau_request_magic_link, name='reseau_request_magic_link'),
    path('reseau/magic/<str:token>/', views_reseau.reseau_magic_login, name='reseau_magic_login'),
    path('reseau/<slug:session_slug>/calendrier/', views_reseau.reseau_portal, name='reseau_portal'),
    path('reseau/<slug:session_slug>/rendez-vous/', views_reseau.reseau_meetings_overview, name='reseau_meetings_overview'),
    path('reseau/<slug:session_slug>/calendrier/disponibilites/', views_reseau.reseau_update_availability, name='reseau_update_availability'),
    path('reseau/<slug:session_slug>/calendrier/indisponibilites/', views_reseau.reseau_add_unavailability, name='reseau_add_unavailability'),
    path('reseau/<slug:session_slug>/calendrier/indisponibilites/<uuid:unavailability_id>/supprimer/', views_reseau.reseau_remove_unavailability, name='reseau_remove_unavailability'),
    path('reseau/<slug:session_slug>/calendrier/reunion/', views_reseau.reseau_create_meeting, name='reseau_create_meeting'),
    path('reseau/<slug:session_slug>/rendez-vous/<uuid:meeting_id>/confirmer/', views_reseau.reseau_confirm_meeting, name='reseau_confirm_meeting'),
    path('reseau/<slug:session_slug>/rendez-vous/<uuid:meeting_id>/terminer/', views_reseau.reseau_complete_meeting, name='reseau_complete_meeting'),
    path('reseau/<slug:session_slug>/rendez-vous/<uuid:meeting_id>/supprimer/', views_reseau.reseau_delete_meeting, name='reseau_delete_meeting'),
    path('reseau/<slug:session_slug>/calendrier/confirmer/<uuid:slot_id>/', views_reseau.reseau_confirm_slot, name='reseau_confirm_slot'),
    path('reseau/<slug:session_slug>/logout/', views_reseau.reseau_logout, name='reseau_logout'),

    # Page principale
    path('representants/', views.representants_list, name='representants_list'),
    path('representants-reparations/', views.representants_reparations_dashboard, name='representants_reparations_dashboard'),
    path('representants-evolution/', views.representants_avis_evolution_dashboard, name='representants_avis_evolution_dashboard'),

    # CRUD Représentants
    path('representants/create/', views.representant_create, name='representant_create'),
    path('representants/<uuid:representant_id>/update/', views.representant_update, name='representant_update'),
    path('representants/<uuid:representant_id>/delete/', views.representant_delete, name='representant_delete'),

    # CRUD Avis
    path('representants/<uuid:representant_id>/avis/', views.avis_list_json, name='avis_list_json'),
    path('representants/<uuid:representant_id>/avis/create/', views.avis_create, name='avis_create'),
    path('avis/<uuid:avis_id>/update/', views.avis_update, name='avis_update'),
    path('avis/<uuid:avis_id>/delete/', views.avis_delete, name='avis_delete'),
    path('avis/non-rattaches/recherche/', views_reunions.avis_unlinked_search_json, name='avis_unlinked_search'),
    path('avis/<uuid:avis_id>/lier-reunion/', views_reunions.avis_link_reunion, name='avis_link_reunion'),
    path('reunions/<uuid:reunion_id>/avis-candidats/', views_reunions.avis_candidats_reunion_json, name='avis_candidats_reunion'),
    path('reunions/<uuid:reunion_id>/avis-lier-batch/', views_reunions.avis_link_reunion_batch, name='avis_link_reunion_batch'),

    # Export/Import Représentants
    path('representants/export/', views.export_representants_excel, name='export_representants_excel'),
    path('representants/template/', views.template_representants_excel, name='template_representants_excel'),
    path('representants/import/', views.import_representants_excel, name='import_representants_excel'),
    path('representants/template-dates-debut/', views.template_representants_dates_debut_excel, name='template_representants_dates_debut_excel'),
    path('representants/import-dates-debut/', views.import_representants_dates_debut_excel, name='import_representants_dates_debut_excel'),

    # Export/Import Avis
    path('avis/export/', views.export_avis_excel, name='export_avis_excel'),
    path('avis/template/', views.template_avis_excel, name='template_avis_excel'),
    path('avis/import/', views.import_avis_excel, name='import_avis_excel'),

    # Reunions
    path('reunions/', views_reunions.reunions_list, name='reunions_list'),
    path('reunions/ouvrages-geres/detail/', views_reunions.ouvrages_geres_detail_json, name='ouvrages_geres_detail_json'),
    path('reunions/create/', views_reunions.reunion_create, name='reunion_create'),
    path('reunions/<uuid:reunion_id>/update/', views_reunions.reunion_update, name='reunion_update'),
    path('reunions/<uuid:reunion_id>/delete/', views_reunions.reunion_delete, name='reunion_delete'),
    path('reunions/<uuid:reunion_id>/detail/', views_reunions.reunion_detail_json, name='reunion_detail_json'),
    path('reunions/<uuid:reunion_id>/fusionnables/', views_reunions.reunions_fusionnables_json, name='reunions_fusionnables_json'),
    path('reunions/<uuid:reunion_id>/fusionner/', views_reunions.reunion_fusionner, name='reunion_fusionner'),
    path('reunions/<uuid:reunion_id>/attendus/update/', views_reunions.attendu_update, name='reunion_attendu_update'),
    path('reunions/export/', views_reunions.export_reunions_excel, name='export_reunions_excel'),

    # Participants de reunion
    path('reunions/<uuid:reunion_id>/participants/create/', views_reunions.participant_create, name='reunion_participant_create'),
    path('reunions/participants/<uuid:participant_id>/delete/', views_reunions.participant_delete, name='reunion_participant_delete'),
    path('reunions/participants/recherche/', views_reunions.participant_search_json, name='reunion_participant_search'),

    # Decisions de reunion
    path('reunions/<uuid:reunion_id>/decisions/create/', views_reunions.decision_create, name='reunion_decision_create'),
    path('reunions/decisions/<uuid:decision_id>/statut/', views_reunions.decision_update_statut, name='reunion_decision_update_statut'),
    path('reunions/decisions/<uuid:decision_id>/delete/', views_reunions.decision_delete, name='reunion_decision_delete'),
    path('reunions/decisions-suivi/', views_reunions.decisions_suivi_dashboard, name='decisions_suivi_dashboard'),

    # Pieces jointes de reunion
    path('reunions/<uuid:reunion_id>/pieces-jointes/create/', views_reunions.piece_jointe_create, name='reunion_piece_jointe_create'),
    path('reunions/pieces-jointes/<uuid:piece_id>/delete/', views_reunions.piece_jointe_delete, name='reunion_piece_jointe_delete'),

    # Autorites (referentiel)
    path('autorites/', views_reunions.autorites_list_json, name='autorites_list_json'),
    path('autorites/create/', views_reunions.autorite_create, name='autorite_create'),

    # Tiers (referentiel)
    path('tiers/create/', views_reunions.tiers_create, name='tiers_create'),

    # Creation rapide Representant / Employe, depuis le modal d'ajout de participant a une reunion
    path('representants/create-rapide/', views_reunions.representant_create_quick, name='representant_create_quick'),
    path('employes/create-rapide/', views_reunions.employe_create_quick, name='employe_create_quick'),
    path('employes/bases-postes/', views_reunions.employe_bases_postes_json, name='employe_bases_postes_json'),

    # Gestion Autorites & Tiers (page dediee, CRUD complet)
    path('autorites-tiers/', views_autorites_tiers.autorites_tiers_list, name='autorites_tiers_list'),

    path('autorites-tiers/autorites/', views_autorites_tiers.autorite_gestion_list_json, name='autorite_gestion_list_json'),
    path('autorites-tiers/autorites/create/', views_autorites_tiers.autorite_gestion_create, name='autorite_gestion_create'),
    path('autorites-tiers/autorites/<uuid:autorite_id>/update/', views_autorites_tiers.autorite_gestion_update, name='autorite_gestion_update'),
    path('autorites-tiers/autorites/<uuid:autorite_id>/delete/', views_autorites_tiers.autorite_gestion_delete, name='autorite_gestion_delete'),

    path('autorites-tiers/tiers/', views_autorites_tiers.tiers_gestion_list_json, name='tiers_gestion_list_json'),
    path('autorites-tiers/tiers/create/', views_autorites_tiers.tiers_gestion_create, name='tiers_gestion_create'),
    path('autorites-tiers/tiers/<uuid:tiers_id>/update/', views_autorites_tiers.tiers_gestion_update, name='tiers_gestion_update'),
    path('autorites-tiers/tiers/<uuid:tiers_id>/delete/', views_autorites_tiers.tiers_gestion_delete, name='tiers_gestion_delete'),

    # Gestion des types d'autorite (referentiel dynamique)
    path('autorites-tiers/types-autorite/', views_autorites_tiers.type_autorite_list_json, name='type_autorite_list_json'),
    path('autorites-tiers/types-autorite/create/', views_autorites_tiers.type_autorite_create, name='type_autorite_create'),
    path('autorites-tiers/types-autorite/<uuid:type_id>/update/', views_autorites_tiers.type_autorite_update, name='type_autorite_update'),
    path('autorites-tiers/types-autorite/<uuid:type_id>/delete/', views_autorites_tiers.type_autorite_delete, name='type_autorite_delete'),

    # Pointage DiameX <-> Reunion
    path('reunions/pointage-diamex/', views_reunions.pointage_diamex_list, name='pointage_diamex_list'),
    path('reunions/pointage-diamex/create/', views_reunions.pointage_diamex_create, name='pointage_diamex_create'),
    path('reunions/pointage-diamex/<uuid:pointage_id>/reassigner/', views_reunions.pointage_diamex_reassigner, name='pointage_diamex_reassigner'),
    path('reunions/pointage-diamex/<uuid:pointage_id>/delete/', views_reunions.pointage_diamex_delete, name='pointage_diamex_delete'),
    path('reunions/pointage-diamex/ignorer/', views_reunions.pointage_diamex_ignorer, name='pointage_diamex_ignorer'),
    path('reunions/pointage-diamex/reactiver/', views_reunions.pointage_diamex_reactiver, name='pointage_diamex_reactiver'),
]
