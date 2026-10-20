from django.urls import path
from . import views
from . import views_import
from . import views_grading_annuel
from . import views_modalites_gestion_analyse
from . import views_compteurs_releves
from . import views_gps_quality
from . import views_photos_planning
from apps.employees import views_import_ouvrages

app_name = 'organization'

urlpatterns = [
    # Page principale
    path('', views.organization_list, name='list'),

    # Page en cascade
    path('cascade/', views.organization_cascade, name='cascade'),


    # Import/Export Excel
    path('import-excel/<str:model_name>/', views_import.import_excel_view, name='import_excel'),
    path('excel-template/<str:model_name>/', views_import.download_excel_template, name='excel_template'),
    path('export-excel/<str:model_name>/', views_import.export_excel_data, name='export_excel'),
    path('ouvrages/export-tarifs-consolides/', views_import.export_tarifs_consolides_excel, name='export_tarifs_consolides_excel'),
    path('ouvrages/export-excel-personnalise/', views_import.export_ouvrages_custom_excel, name='export_ouvrages_custom_excel'),
    path('ouvrages/export-excel-personnalise-plus/', views_import.export_ouvrages_custom_excel_plus, name='export_ouvrages_custom_excel_plus'),
    path('ouvrages/export-excel-responsable/', views_import.export_ouvrages_responsable_excel, name='export_ouvrages_responsable_excel'),

    # Import GPS pour équipements et points d'eau
    path('import-excel-update-equipements-gps/', views_import.import_excel_update_equipements_gps, name='import_excel_update_equipements_gps'),
    path('import-excel-update-points-eau-gps/', views_import.import_excel_update_points_eau_gps, name='import_excel_update_points_eau_gps'),

    # Import mise à jour IDxls fournisseurs
    path('import-update-fournisseur-idxls/', views_import.import_update_fournisseur_idxls, name='import_update_fournisseur_idxls'),

    # Organisations
    path('organisations/', views.organisation_list, name='organisation_list'),
    path('organisations/create/', views.organisation_create, name='organisation_create'),
    path('organisations/<uuid:pk>/', views.organisation_detail, name='organisation_detail'),
    path('organisations/<uuid:pk>/update/', views.organisation_update, name='organisation_update'),
    path('organisations/<uuid:pk>/delete/', views.organisation_delete, name='organisation_delete'),
    path(
        'organisations/partenaires-affectations/',
        views.partenaire_gestionnaire_affectations,
        name='partenaire_gestionnaire_affectations'
    ),

    # Types d'ouvrages
    path('types-ouvrages/', views.type_ouvrage_list, name='type_ouvrage_list'),
    path('types-ouvrages/create/', views.type_ouvrage_create, name='type_ouvrage_create'),
    path('types-ouvrages/<uuid:pk>/', views.type_ouvrage_detail, name='type_ouvrage_detail'),
    path('types-ouvrages/<uuid:pk>/update/', views.type_ouvrage_update, name='type_ouvrage_update'),
    path('types-ouvrages/<uuid:pk>/delete/', views.type_ouvrage_delete, name='type_ouvrage_delete'),

    # Types d'équipements
    path('types-equipements/', views.type_equipement_list, name='type_equipement_list'),
    path('types-equipements/create/', views.type_equipement_create, name='type_equipement_create'),
    path('types-equipements/<uuid:pk>/', views.type_equipement_detail, name='type_equipement_detail'),
    path('types-equipements/<uuid:pk>/update/', views.type_equipement_update, name='type_equipement_update'),
    path('types-equipements/<uuid:pk>/delete/', views.type_equipement_delete, name='type_equipement_delete'),

    # URLs pour composants des types d'équipements (en cascade)
    path('types-equipements/<uuid:type_pk>/composants/', views.composants_type_equipement_list, name='composants_type_equipement_list'),
    path('types-equipements/<uuid:type_pk>/composants/nouveau/', views.composant_type_equipement_create, name='composant_type_equipement_create'),
    path('types-equipements/<uuid:type_pk>/composants/<uuid:composant_pk>/modifier/', views.composant_type_equipement_edit, name='composant_type_equipement_edit'),
    path('types-equipements/<uuid:type_pk>/composants/<uuid:composant_pk>/supprimer/', views.composant_type_equipement_delete, name='composant_type_equipement_delete'),

    # API pour gestion en cascade des composants d'équipements
    path('api/composants-type-equipement/<uuid:type_pk>/', views.api_composants_type_equipement_list, name='api_composants_type_equipement_list'),
    path('api/composants-type-equipement/<uuid:type_pk>/<uuid:composant_pk>/', views.api_composant_type_equipement_detail, name='api_composant_type_equipement_detail'),
    path('api/composants-type-equipement/<uuid:type_pk>/create/', views.api_composant_type_equipement_create, name='api_composant_type_equipement_create'),
    path('api/composants-type-equipement/<uuid:type_pk>/<uuid:composant_pk>/edit/', views.api_composant_type_equipement_edit, name='api_composant_type_equipement_edit'),
    path('api/composants-type-equipement/<uuid:type_pk>/<uuid:composant_pk>/delete/', views.api_composant_type_equipement_delete, name='api_composant_type_equipement_delete'),

    # API pour gestion des points de contrôle par composant d'équipement
    path('api/composants-type-equipement/<uuid:composant_pk>/points-controle/', views.api_points_controle_composant_equipement_list, name='api_points_controle_composant_equipement_list'),
    path('api/composants-type-equipement/<uuid:composant_pk>/points-controle/create/', views.api_point_controle_composant_equipement_create, name='api_point_controle_composant_equipement_create'),
    path('api/composants-type-equipement/<uuid:composant_pk>/points-controle/<uuid:point_controle_pk>/edit/', views.api_point_controle_composant_equipement_edit, name='api_point_controle_composant_equipement_edit'),
    path('api/composants-type-equipement/<uuid:composant_pk>/points-controle/<uuid:point_controle_pk>/delete/', views.api_point_controle_composant_equipement_delete, name='api_point_controle_composant_equipement_delete'),

    # API pour lister tous les points de contrôle (pour sélecteurs)
    path('api/points-controle/', views.api_points_controle_list, name='api_points_controle_list'),
    path('api/points-controle/<uuid:point_controle_id>/', views.api_point_controle_detail, name='api_point_controle_detail'),

    # Ouvrages
    path('ouvrages/', views.ouvrage_list, name='ouvrage_list'),
    path('ouvrages/suivi-liaisons/', views.ouvrage_suivi_liaisons, name='ouvrage_suivi_liaisons'),
    path('qualite-gps/', views_gps_quality.gps_quality_dashboard, name='gps_quality_dashboard'),
    path('qualite-gps/review/', views_gps_quality.gps_quality_review, name='gps_quality_review'),
    path('qualite-gps/coordinate/', views_gps_quality.gps_quality_coordinate_update, name='gps_quality_coordinate_update'),
    path('qualite-gps/parcelles/search/', views_gps_quality.gps_quality_parcel_search, name='gps_quality_parcel_search'),
    path('qualite-gps/point-parcelle/', views_gps_quality.gps_quality_point_parcel_update, name='gps_quality_point_parcel_update'),
    path('qualite-gps/ouvrages/<uuid:ouvrage_id>/map-data/', views_gps_quality.gps_quality_map_data, name='gps_quality_map_data'),
    path('api/ouvrages/<uuid:ouvrage_id>/dossier-technique-checklist/', views.api_ouvrage_dossier_technique_checklist, name='api_ouvrage_dossier_technique_checklist'),
    path('api/ouvrages/<uuid:ouvrage_id>/toggle-fonctionnel/', views.api_ouvrage_toggle_fonctionnel, name='api_ouvrage_toggle_fonctionnel'),
    path('api/ouvrages/<uuid:ouvrage_id>/map-coordinate/assign/', views.api_ouvrage_map_coordinate_assign, name='api_ouvrage_map_coordinate_assign'),
    path('ouvrages/grading-annuel/', views_grading_annuel.ouvrage_grading_annuel_list, name='ouvrage_grading_annuel_list'),
    path('ouvrages/grading-annuel/analyse/', views_grading_annuel.ouvrage_grading_annuel_analyse, name='ouvrage_grading_annuel_analyse'),
    path('ouvrages/grading-annuel/analyse/transition-details/', views_grading_annuel.api_ouvrage_grading_annuel_transition_details, name='api_ouvrage_grading_annuel_transition_details'),
    path('ouvrages/grading-annuel/analyse/ouvrages/<uuid:ouvrage_id>/reparations-non-terminees/', views_grading_annuel.api_ouvrage_reparations_non_terminees, name='api_ouvrage_reparations_non_terminees'),
    path('ouvrages/grading-annuel/create/', views_grading_annuel.ouvrage_grading_annuel_create, name='ouvrage_grading_annuel_create'),
    path('ouvrages/grading-annuel/<uuid:pk>/update/', views_grading_annuel.ouvrage_grading_annuel_update, name='ouvrage_grading_annuel_update'),
    path('ouvrages/grading-annuel/<uuid:pk>/delete/', views_grading_annuel.ouvrage_grading_annuel_delete, name='ouvrage_grading_annuel_delete'),
    path('ouvrages/grading-annuel/import-excel/', views_grading_annuel.ouvrage_grading_annuel_import_excel, name='ouvrage_grading_annuel_import_excel'),
    path('ouvrages/grading-annuel/export-excel/', views_grading_annuel.ouvrage_grading_annuel_export_excel, name='ouvrage_grading_annuel_export_excel'),
    path('ouvrages/grading-annuel/template-excel/', views_grading_annuel.ouvrage_grading_annuel_template_excel, name='ouvrage_grading_annuel_template_excel'),
    path('ouvrages/consolidated/', views.consolidated_ouvrages, name='consolidated_ouvrages'),
    path('ouvrages/abaque/', views.abaque_facturation, name='abaque_facturation'),
    path('ouvrages/abaque/generate/', views.generate_abaque_pdf, name='generate_abaque_pdf'),
    path('api/ouvrages/<uuid:ouvrage_id>/types-point-eau/', views.api_ouvrage_types_point_eau, name='api_ouvrage_types_point_eau'),
    path('ouvrages/create/', views.ouvrage_create, name='ouvrage_create'),
    path('ouvrages/assistant/', views.ouvrage_assistant, name='ouvrage_assistant'),
    path('api/ouvrages/assistant/context/<uuid:ouvrage_id>/', views.api_ouvrage_assistant_context, name='api_ouvrage_assistant_context'),
    path('ouvrages/detail/', views.ouvrage_detail_entry, name='ouvrage_detail_entry'),
    path('ouvrages/<uuid:pk>/', views.ouvrage_detail, name='ouvrage_detail'),
    path('ouvrages/<uuid:pk>/update/', views.ouvrage_update, name='ouvrage_update'),
    path('ouvrages/<uuid:pk>/dossiers-techniques/upload/', views.ouvrage_dossier_technique_upload, name='ouvrage_dossier_technique_upload'),
    path('api/ouvrages/photos-lot/analyser/', views.api_ouvrage_photos_lot_analyser, name='api_ouvrage_photos_lot_analyser'),
    path('api/ouvrages/photos-planning/analyser/', views_photos_planning.api_photos_planning_analyser, name='api_photos_planning_analyser'),
    path('api/ouvrages/photos-planning/preparer/', views_photos_planning.api_photos_planning_preparer, name='api_photos_planning_preparer'),
    path('api/ouvrages/photos-planning/importer/', views_photos_planning.api_photos_planning_importer, name='api_photos_planning_importer'),
    path('api/ouvrages/photos-lot/importer/', views.api_ouvrage_photo_lot_import, name='api_ouvrage_photo_lot_import'),
    path('api/ouvrages/dossiers-techniques/analyser/', views.api_ouvrage_dossiers_techniques_analyser, name='api_ouvrage_dossiers_techniques_analyser'),
    path('ouvrages/<uuid:pk>/dossiers-techniques/import-fichier/', views.api_ouvrage_dossier_technique_import_fichier, name='api_ouvrage_dossier_technique_import_fichier'),
    path('ouvrages/dossiers-techniques/<uuid:dossier_id>/preview/', views.ouvrage_dossier_technique_preview, name='ouvrage_dossier_technique_preview'),
    path('ouvrages/dossiers-techniques/<uuid:dossier_id>/delete/', views.ouvrage_dossier_technique_delete, name='ouvrage_dossier_technique_delete'),
    path('ouvrages/<uuid:pk>/delete/', views.ouvrage_delete, name='ouvrage_delete'),

    # Bases
    path('bases/', views.base_list, name='base_list'),
    path('bases/create/', views.base_create, name='base_create'),
    path('bases/<uuid:pk>/', views.base_detail, name='base_detail'),
    path('bases/<uuid:pk>/update/', views.base_update, name='base_update'),
    path('bases/<uuid:pk>/delete/', views.base_delete, name='base_delete'),

    # Pages CRUD pour les données liées aux ouvrages
    path('points-eau/', views.points_eau_list, name='points_eau_list'),
    path('points-eau/<uuid:ouvrage_id>/', views.points_eau_list, name='points_eau_list_ouvrage'),
    path('points-eau/create/<uuid:ouvrage_id>/', views.points_eau_create, name='points_eau_create'),
    path('points-eau/edit/<uuid:point_id>/', views.points_eau_edit, name='points_eau_edit'),
    path('points-eau/delete/<uuid:point_id>/', views.points_eau_delete, name='points_eau_delete'),
    # Support UUID et integers pour compatibilité
    path('points-eau/map/<uuid:point_id>/', views.point_eau_map, name='point_eau_map'),
    path('points-eau/map/<int:point_id>/', views.point_eau_map_legacy, name='point_eau_map_legacy'),

    path('equipements/', views.equipements_list, name='equipements_list'),
    path('equipements/<uuid:ouvrage_id>/', views.equipements_list, name='equipements_list_ouvrage'),
    path('api/ouvrages/<uuid:ouvrage_id>/equipements/', views.api_ouvrage_equipements, name='api_ouvrage_equipements'),
    path('equipements/create/<uuid:ouvrage_id>/', views.equipements_create, name='equipements_create'),
    path('equipements/edit/<uuid:equipement_id>/', views.equipements_edit, name='equipements_edit'),
    path('equipements/delete/<uuid:equipement_id>/', views.equipements_delete, name='equipements_delete'),

    path('compteurs/', views.compteurs_list, name='compteurs_list'),
    path('compteurs/<uuid:ouvrage_id>/', views.compteurs_list, name='compteurs_list_ouvrage'),
    path('compteurs/create/<uuid:ouvrage_id>/', views.compteurs_create, name='compteurs_create'),
    path('compteurs/edit/<uuid:compteur_id>/', views.compteurs_edit, name='compteurs_edit'),
    path('compteurs/delete/<uuid:compteur_id>/', views.compteurs_delete, name='compteurs_delete'),
    path('compteurs/releve/<uuid:compteur_id>/', views.compteurs_saisir_releve, name='compteurs_saisir_releve'),
    path('compteurs/releves/', views_compteurs_releves.compteurs_releves_list, name='compteurs_releves_list'),
    path('compteurs/releves/<uuid:ouvrage_id>/', views_compteurs_releves.compteurs_releves_list, name='compteurs_releves_list_ouvrage'),
    path('compteurs/releves/import-excel/', views_compteurs_releves.compteurs_releves_import_excel, name='compteurs_releves_import_excel'),
    path('compteurs/releves/import-excel/<uuid:ouvrage_id>/', views_compteurs_releves.compteurs_releves_import_excel, name='compteurs_releves_import_excel_ouvrage'),
    path('compteurs/releves/export-excel/', views_compteurs_releves.compteurs_releves_export_excel, name='compteurs_releves_export_excel'),
    path('compteurs/releves/export-excel/<uuid:ouvrage_id>/', views_compteurs_releves.compteurs_releves_export_excel, name='compteurs_releves_export_excel_ouvrage'),
    path('compteurs/releves/template-excel/', views_compteurs_releves.compteurs_releves_template_excel, name='compteurs_releves_template_excel'),
    path('compteurs/releves/template-excel/<uuid:ouvrage_id>/', views_compteurs_releves.compteurs_releves_template_excel, name='compteurs_releves_template_excel_ouvrage'),
    path('compteurs/releves/api/changement-compteur/', views_compteurs_releves.api_compteurs_releves_changement_compteur, name='api_compteurs_releves_changement_compteur'),
    path('compteurs/releves/api/preview/', views_compteurs_releves.api_compteurs_releves_preview, name='api_compteurs_releves_preview'),
    path('compteurs/releves/api/<uuid:releve_id>/', views_compteurs_releves.api_compteurs_releves_detail, name='api_compteurs_releves_detail'),
    path('compteurs/releves/api/create/', views_compteurs_releves.api_compteurs_releves_create, name='api_compteurs_releves_create'),
    path('compteurs/releves/api/<uuid:releve_id>/update/', views_compteurs_releves.api_compteurs_releves_update, name='api_compteurs_releves_update'),
    path('compteurs/releves/api/<uuid:releve_id>/delete/', views_compteurs_releves.api_compteurs_releves_delete, name='api_compteurs_releves_delete'),
    path('compteurs/releves/api/compteur-points/', views_compteurs_releves.api_compteurs_points_management, name='api_compteurs_points_management'),
    path('compteurs/releves/api/compteur-points/attach/', views_compteurs_releves.api_compteurs_points_attach, name='api_compteurs_points_attach'),
    path('compteurs/releves/api/compteur-points/<uuid:point_id>/detach/', views_compteurs_releves.api_compteurs_points_detach, name='api_compteurs_points_detach'),
    path('compteurs/releves/api/compteur-points/<uuid:point_id>/move/', views_compteurs_releves.api_compteurs_points_move, name='api_compteurs_points_move'),

    path('tarifs/', views.tarifs_list, name='tarifs_list'),
    path('tarifs/<uuid:ouvrage_id>/', views.tarifs_list, name='tarifs_list_ouvrage'),
    path('tarifs/create/<uuid:ouvrage_id>/', views.tarifs_create, name='tarifs_create'),
    path('tarifs/edit/<uuid:tarif_id>/', views.tarifs_edit, name='tarifs_edit'),
    path('tarifs/delete/<uuid:tarif_id>/', views.tarifs_delete, name='tarifs_delete'),
    path('tarifs/tranches/<uuid:tarif_id>/', views.tarifs_tranches_list, name='tarifs_tranches_list'),
    path('tarifs/tranches/create/<uuid:tarif_id>/', views.tarifs_tranches_create, name='tarifs_tranches_create'),
    path('tarifs/tranches/edit/<uuid:tranche_id>/', views.tarifs_tranches_edit, name='tarifs_tranches_edit'),
    path('tarifs/tranches/delete/<uuid:tranche_id>/', views.tarifs_tranches_delete, name='tarifs_tranches_delete'),

    path('modalites-gestion/', views.modalites_gestion_list, name='modalites_gestion_list'),
    path('modalites-gestion/analyse/', views_modalites_gestion_analyse.modalites_gestion_analyse, name='modalites_gestion_analyse'),
    path('modalites-gestion/<uuid:ouvrage_id>/', views.modalites_gestion_list, name='modalites_gestion_list_ouvrage'),
    path('modalites-gestion/create/<uuid:ouvrage_id>/', views.modalites_gestion_create, name='modalites_gestion_create'),
    path('modalites-gestion/edit/<uuid:modalite_id>/', views.modalites_gestion_edit, name='modalites_gestion_edit'),
    path('modalites-gestion/delete/<uuid:modalite_id>/', views.modalites_gestion_delete, name='modalites_gestion_delete'),

    path('fournisseurs/', views.fournisseurs_list, name='fournisseurs_list'),
    path('fournisseurs/<uuid:ouvrage_id>/', views.fournisseurs_list, name='fournisseurs_list_ouvrage'),
    path('fournisseurs/create/', views.fournisseurs_create, name='fournisseurs_create'),
    path('fournisseurs/edit/<uuid:fournisseur_id>/', views.fournisseurs_edit, name='fournisseurs_edit'),
    path('fournisseurs/merge/', views.fournisseurs_merge, name='fournisseurs_merge'),
    path('fournisseurs/instructions/<uuid:instruction_id>/update/', views.fournisseurs_instruction_update, name='fournisseurs_instruction_update'),
    path('fournisseurs/delete/<uuid:fournisseur_id>/', views.fournisseurs_delete, name='fournisseurs_delete'),

    path('adresses/', views.adresses_list, name='adresses_list'),
    path('adresses/<uuid:ouvrage_id>/', views.adresses_list, name='adresses_list_ouvrage'),
    path('adresses/create/<uuid:ouvrage_id>/', views.adresses_create, name='adresses_create'),
    path('adresses/edit/<uuid:adresse_id>/', views.adresses_edit, name='adresses_edit'),
    path('adresses/delete/<uuid:adresse_id>/', views.adresses_delete, name='adresses_delete'),

    path('cartes-sociales/', views.cartes_sociales_list, name='cartes_sociales_list'),
    path('cartes-sociales/<uuid:ouvrage_id>/', views.cartes_sociales_list, name='cartes_sociales_list_ouvrage'),
    path('cartes-sociales/create/<uuid:ouvrage_id>/', views.cartes_sociales_create, name='cartes_sociales_create'),
    path('cartes-sociales/edit/<uuid:carte_id>/', views.cartes_sociales_edit, name='cartes_sociales_edit'),
    path('cartes-sociales/delete/<uuid:carte_id>/', views.cartes_sociales_delete, name='cartes_sociales_delete'),

    # API pour formulaires en cascade
    path('api/organisations/', views.api_organisations, name='api_organisations'),
    path('api/all-bases/', views.api_all_bases, name='api_all_bases'),
    path('api/bases/<uuid:organisation_id>/', views.api_bases, name='api_bases'),
    path('api/natures-declaration/', views.api_natures_declaration, name='api_natures_declaration'),
    path('api/comptes/<uuid:organisation_id>/', views.api_comptes, name='api_comptes'),
    path('api/postes/<uuid:organisation_id>/', views.api_postes, name='api_postes'),
    path('api/magasins/<uuid:base_id>/', views.api_magasins, name='api_magasins'),
    path('api/journaux/<uuid:base_id>/', views.api_journaux, name='api_journaux'),
    path('api/journaux-by-organisation/<uuid:organisation_id>/', views.api_journaux_by_organisation, name='api_journaux_by_organisation'),
    path('api/employes/<uuid:base_id>/', views.api_employes, name='api_employes'),
    path('api/employe-ouvrages/<uuid:employe_id>/', views.api_employe_ouvrages, name='api_employe_ouvrages'),
    path('api/employe-ouvrages/detail/<uuid:resp_id>/', views.api_employe_ouvrages_detail, name='api_employe_ouvrages_detail'),
    path('api/employe-ouvrages/create/', views.api_employe_ouvrages_create, name='api_employe_ouvrages_create'),
    path('api/employe-ouvrages/update/', views.api_employe_ouvrages_update, name='api_employe_ouvrages_update'),
    path('api/employe-ouvrages/delete/', views.api_employe_ouvrages_delete, name='api_employe_ouvrages_delete'),
    path('api/all-ouvrages/', views.api_all_ouvrages, name='api_all_ouvrages'),
    path('api/create/', views.api_create, name='api_create'),
    path('api/update/', views.api_update, name='api_update'),
    path('api/delete/', views.api_delete, name='api_delete'),

    # Points de contrôle pour points d'eau
    path('api/points-eau/<uuid:point_id>/controles/', views.point_eau_controles_list, name='point_eau_controles_list'),
    path('api/points-eau/<uuid:point_id>/diamex-extractions/', views.api_point_eau_diamex_extractions, name='api_point_eau_diamex_extractions'),
    path('api/points-eau/<uuid:point_id>/controles/create/', views.point_eau_controle_create, name='point_eau_controle_create'),
    path('api/controles/<uuid:controle_id>/edit/', views.point_eau_controle_edit, name='point_eau_controle_edit'),
    path('api/controles/<uuid:controle_id>/delete/', views.point_eau_controle_delete, name='point_eau_controle_delete'),

    # Points de contrôle pour équipements
    path('api/equipements/<uuid:equipement_id>/controles/', views.equipement_controles_list, name='equipement_controles_list'),
    path('api/equipements/<uuid:equipement_id>/controles/create/', views.equipement_controle_create, name='equipement_controle_create'),
    path('api/equipement-controles/<uuid:controle_id>/edit/', views.equipement_controle_edit, name='equipement_controle_edit'),
    path('api/equipement-controles/<uuid:controle_id>/delete/', views.equipement_controle_delete, name='equipement_controle_delete'),

    # API pour inspection de composants (nouveau système)
    path('api/points-eau/<uuid:point_id>/composants-inspection/', views.api_point_eau_composants_inspection, name='api_point_eau_composants_inspection'),
    path('api/points-eau/<uuid:point_id>/inspection-session/create/', views.api_inspection_session_create, name='api_inspection_session_create'),
    path('api/composants/<uuid:composant_id>/inspect/', views.api_composant_inspect, name='api_composant_inspect'),

    # API pour récupérer un point d'eau par ID
    path('api/point-eau/<uuid:point_eau_id>/', views.api_get_point_eau, name='api_get_point_eau'),
    path('api/ouvrages/<uuid:ouvrage_id>/organigramme/', views.api_ouvrage_organigramme, name='api_ouvrage_organigramme'),
    path('api/ouvrages/<uuid:ouvrage_id>/liaisons/create/', views.api_ouvrage_liaison_create, name='api_ouvrage_liaison_create'),
    path('api/liaisons/<uuid:liaison_id>/delete/', views.api_ouvrage_liaison_delete, name='api_ouvrage_liaison_delete'),

    # Import/Export Relations Employés-Ouvrages
    path('import-employe-ouvrages/', views_import_ouvrages.import_employe_ouvrages_view, name='import_employe_ouvrages'),
    path('api/import-employe-ouvrages/', views_import_ouvrages.api_import_employe_ouvrages, name='api_import_employe_ouvrages'),
    path('template-excel-employe-ouvrages/', views_import_ouvrages.template_excel_employe_ouvrages, name='template_excel_employe_ouvrages'),
    path('export-employe-ouvrages/', views_import_ouvrages.export_employe_ouvrages, name='export_employe_ouvrages'),

    # Gestion des tables autorisées pour les comptes
    path('api/comptes/<uuid:compte_id>/tables/', views.api_compte_tables, name='api_compte_tables'),
    path('api/comptes/<uuid:compte_id>/tables/create/', views.api_compte_table_create, name='api_compte_table_create'),
    path('api/compte-tables/<uuid:compte_table_id>/toggle/', views.api_compte_table_toggle, name='api_compte_table_toggle'),
    path('api/compte-tables/<uuid:compte_table_id>/delete/', views.api_compte_table_delete, name='api_compte_table_delete'),
]
