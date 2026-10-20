from django.urls import path, include
from . import views_tournee_routiere, views_terrain_points
from . import views, views_simple, views_livraisons, views_forfaitaire, views_reparations, views_reparations_print, views_reparations_apis, views_reparations_filters, views_reparations_import, views_reparations_temp_cloture, views_terrain, views_volumetrique, views_volumetrique_matriciel, views_volumetrique_global, views_analyse_consommation, views_analyse_par_point_eau, views_tableau_points_eau, views_analyse_cartes_sociales, views_analyse_meteo, views_indemnites, views_analyse_pieces, views_analyse_pieces_geo, views_annulation_repos, views_conso_cartes_sociales, views_evaluation_objectifs, views_modal_bienvenue, views_planning_auto, views_visites, views_preparation_tournee, views_fusion_activites, views_pointage, views_couts_types
from apps.core import views_impression

app_name = 'planning'

urlpatterns = [
    # Vues traditionnelles
    path('', views.planning_dashboard, name='dashboard'),
    path('pointage/rapport/', views_pointage.rapport_pointage_mensuel, name='rapport_pointage'),
    path('pointage/fiche-indemnite/', views_pointage.fiche_indemnite_pointage, name='rapport_pointage_fiche'),
    path('pointage/rapport/export/', views_pointage.rapport_pointage_mensuel_export, name='rapport_pointage_export'),
    path('liste/', views.planning_list, name='list'),
    path('planning-automatique/', views.planning_automatique, name='planning_automatique'),
    path('automatique/', views.planning_automatique, name='planning_automatique_alias'),
    path('workflow-terrain/', views.workflow_terrain, name='workflow_terrain'),
    path('consolide/', views.planning_consolide, name='consolide'),
    path('calendrier/', views.planning_calendar, name='calendar'),
    path('agenda/', views.planning_agenda, name='agenda'),
    path('cloture-mensuelle/', views.planning_cloture_mensuelle_page, name='cloture_mensuelle_page'),
    path('cloture/<uuid:planning_id>/', views.planning_cloture_page, name='cloture_page'),
    path('validation/<str:planning_id>/', views.planning_validation_page, name='validation_page'),
    path('nouveau/', views.planning_create, name='create'),

    # CRITICAL: Suivi des réparations - DOIT être AVANT les patterns génériques <uuid:pk>/
    # car sinon Django match '<uuid:pk>/modifier/' avant 'reparations/api/<uuid>/modifier/'
    path('reparations/', views_reparations.suivi_reparations, name='suivi_reparations'),
    # TEMPORAIRE : rattrapage clôtures/captages, à retirer une fois terminé (voir
    # apps/planning/views_reparations_temp_cloture.py)
    path('reparations/temp-cloture-captage/', views_reparations_temp_cloture.temp_cloture_captage, name='temp_cloture_captage'),
    path('reparations/kanban/', views_reparations.suivi_reparations_kanban, name='suivi_reparations_kanban'),
    path('reparations/imprimer/', views_reparations_print.reparations_imprimer, name='reparations_imprimer'),
    path('reparations/api/stats/', views_reparations_apis.api_stats_reparations, name='api_stats_reparations'),
    path('reparations/api/stats-grading/', views_reparations_apis.api_stats_grading, name='api_stats_grading'),
    path('reparations/api/communes/', views_reparations_apis.api_communes_reparations_summary, name='api_communes_reparations_summary'),
    path('reparations/api/ouvrages/', views_reparations_apis.api_ouvrages_avec_modalites, name='api_ouvrages_avec_modalites'),
    path('reparations/api/export-excel/', views_reparations_apis.api_export_reparations_excel, name='api_export_reparations_excel'),
    path('reparations/api/filter-options/', views_reparations_filters.api_get_filter_options, name='api_reparations_filter_options'),
    path('reparations/api/composants/', views_reparations_apis.api_composants_cible_reparation, name='api_composants_cible_reparation'),
    path('reparations/fusion-activites/', views_fusion_activites.page_fusion_activites, name='fusion_activites'),
    path('reparations/fusion-activites/api/groupes/', views_fusion_activites.api_fusion_groupes, name='api_fusion_groupes'),
    path('reparations/fusion-activites/api/apercu/', views_fusion_activites.api_fusion_apercu, name='api_fusion_apercu'),
    path('reparations/fusion-activites/api/appliquer/', views_fusion_activites.api_fusion_appliquer, name='api_fusion_appliquer'),
    path('reparations/fusion-activites/api/annuler/', views_fusion_activites.api_fusion_annuler, name='api_fusion_annuler'),
    path('reparations/api/list/', views_reparations_apis.api_reparations_list, name='api_reparations_list'),
    path('reparations/api/bulk-update/', views_reparations_apis.api_reparations_bulk_update, name='api_reparations_bulk_update'),
    path('reparations/api/composants-selection/', views_reparations_apis.api_reparations_composants_selection, name='api_reparations_composants_selection'),
    path('reparations/api/bulk-composants/', views_reparations_apis.api_reparations_bulk_composants, name='api_reparations_bulk_composants'),
    path('reparations/api/bulk-delete/', views_reparations_apis.api_reparations_bulk_delete, name='api_reparations_bulk_delete'),
    path('reparations/api/<uuid:planning_id>/marquer-terminee/', views_reparations_apis.api_marquer_reparation_terminee, name='api_marquer_reparation_terminee'),
    path('reparations/api/<uuid:planning_id>/marquer-non-terminee/', views_reparations_apis.api_marquer_reparation_non_terminee, name='api_marquer_reparation_non_terminee'),
    path('reparations/api/<uuid:planning_id>/livrer/', views_reparations_apis.api_livrer_reparation, name='api_livrer_reparation'),
    path('reparations/api/<uuid:planning_id>/utiliser-pieces-transferees/', views_reparations_apis.api_utiliser_pieces_transferees_reparation, name='api_utiliser_pieces_transferees_reparation'),
    path('reparations/api/<uuid:planning_id>/supprimer/', views_reparations_apis.api_supprimer_reparation, name='api_supprimer_reparation'),
    path('reparations/api/<uuid:planning_id>/modifier/', views_reparations_apis.api_modifier_reparation, name='api_modifier_reparation'),
    path('reparations/import/modele/', views_reparations_import.api_reparations_import_template, name='api_reparations_import_template'),
    path('reparations/api/import/apercu/', views_reparations_import.api_reparations_import_preview, name='api_reparations_import_preview'),
    path('reparations/api/import/confirmer/', views_reparations_import.api_reparations_import_confirm, name='api_reparations_import_confirm'),

    # Patterns génériques CRUD - DOIVENT être APRÈS les routes spécifiques
    path('<uuid:pk>/', views.planning_detail, name='detail'),
    path('<uuid:pk>/modifier/', views.planning_update, name='update'),
    path('<uuid:pk>/supprimer/', views.planning_delete, name='delete'),

    # Indemnités journalières
    path('indemnites/', views_indemnites.indemnites_list, name='indemnites'),
    path('indemnites/hors-zone/', views_indemnites.indemnites_hors_zone, name='indemnites_hors_zone'),
    path('indemnites/retour/', views_indemnites.retour_indemnites, name='retour_indemnites'),
    path('indemnites/api/list/', views_indemnites.api_indemnites_list, name='api_indemnites_list'),
    path('indemnites/hors-zone/api/list/', views_indemnites.api_indemnites_hors_zone_list, name='api_indemnites_hors_zone_list'),
    path('indemnites/hors-zone/api/imprimer/', views_indemnites.api_imprimer_facture_indemnite_hors_zone, name='api_imprimer_facture_indemnite_hors_zone'),
    path('indemnites/api/generer/', views_indemnites.api_generer_indemnites, name='api_generer_indemnites'),
    path('indemnites/api/annuler/', views_indemnites.api_annuler_indemnites, name='api_annuler_indemnites'),
    path('indemnites/api/marquer-avancees/', views_indemnites.api_marquer_avancees, name='api_marquer_avancees'),
    path('indemnites/api/confirmer/', views_indemnites.api_confirmer_indemnites, name='api_confirmer_indemnites'),
    path('indemnites/api/a-confirmer/', views_indemnites.api_indemnites_a_confirmer, name='api_indemnites_a_confirmer'),
    path('indemnites/api/imprimer-facture/', views_indemnites.api_imprimer_facture_indemnite, name='api_imprimer_facture_indemnite'),
    path('indemnites/api/export-diamex/', views_indemnites.api_export_diamex_indemnites, name='api_export_diamex_indemnites'),
    path('indemnites/export/', views_indemnites.export_excel_indemnites, name='export_excel_indemnites'),
    path('indemnites/template/', views_indemnites.template_excel_indemnites, name='template_excel_indemnites'),
    path('indemnites/import/', views_indemnites.import_excel_indemnites, name='import_excel_indemnites'),

    # API REST (simplifiées pour les données existantes)
    path('api/data/', views_simple.planning_data_api_simple, name='data_api'),
    path('api/stats/', views.planning_stats_api, name='stats_api'),
    path('api/details/<str:planning_id>/', views_simple.planning_details_api_simple, name='details_api'),
    path('api/validate/<str:planning_id>/', views_simple.planning_validate_api_simple, name='validate_api'),
    path('api/unvalidate/<str:id>/', views_simple.planning_unvalidate_api, name='unvalidate_api'),
    path('api/employees/', views_simple.employees_api_plain, name='employees_api'),
    path('api/ouvrages/', views_simple.ouvrages_api_plain, name='ouvrages_api'),
    path('api/ouvrages-inspectables/', views_simple.ouvrages_inspectables_api, name='ouvrages_inspectables_api'),
    path('api/types-activites/', views_simple.types_activites_api_simple, name='types_activites_api'),
    path('api/activites-postes/', views_simple.activites_postes_api_simple, name='activites_postes_api'),
    path('api/months/', views_simple.available_months_api_simple, name='months_api'),
    path('api/create/', views_simple.planning_create_api_simple, name='create_api'),
    path('api/update/<uuid:id>/', views_simple.planning_update_api_simple, name='update_api'),
    path('api/delete/<uuid:id>/', views_simple.planning_delete_api_simple, name='delete_api'),
    path('api/merge-duplicates/', views.api_merge_planning_duplicates, name='merge_duplicates_api'),
    path('api/bulk-update/', views.api_planning_bulk_update, name='bulk_update_api'),
    path('api/frequence-check/', views.api_frequence_check, name='frequence_check_api'),
    path('api/update-date/<str:planning_id>/', views_simple.planning_update_date_api, name='update_date_api'),
    path('api/update-fast/<uuid:planning_id>/', views.api_planning_fast_update, name='fast_update_api'),
    path('api/activites/', views_simple.activites_api_simple, name='activites_api'),
    path('api/create-from-inspection/', views_simple.create_planning_from_inspection_dev, name='create_from_inspection_api'),
    path('api/planning-automatique/employes/', views_planning_auto.api_employes_ouvrages_planning_auto, name='api_planning_auto_employes'),
    path('api/planning-automatique/contre-visites/', views_planning_auto.generer_contre_visites, name='api_planning_auto_contre_visites'),
    path('api/planning-automatique/recouvrement/', views_planning_auto.generer_recouvrement, name='api_planning_auto_recouvrement'),
    path('api/planning-automatique/repos-feries/', views_planning_auto.generer_repos_jours_feries, name='api_planning_auto_repos_feries'),

    # Formulaire complet en page (nouveau et modification avec détails en cascade)
    path('form/nouveau/', views_simple.planning_form_page, name='form_create'),
    path('form/<str:planning_id>/modifier/', views_simple.planning_form_page, name='form_update'),
    path('form/<str:planning_id>/controler-doublons/', views_simple.planning_merge_current_duplicates, name='form_merge_duplicates'),

    # APIs pour le formulaire de planning (filtrage dynamique)
    path('api/equipements-by-ouvrage/', views_simple.api_equipements_by_ouvrage, name='api_equipements_by_ouvrage'),
    path('api/points-eau-by-ouvrage/', views_simple.api_points_eau_by_ouvrage, name='api_points_eau_by_ouvrage'),
    path('api/designations-by-activite/', views_simple.api_designations_by_activite, name='api_designations_by_activite'),
    path('api/comptes-by-designation/', views_simple.api_comptes_by_designation, name='api_comptes_by_designation'),
    path('api/form/employee-month-preview/', views_simple.api_employee_month_preview, name='api_employee_month_preview'),

    # Gestion des livraisons
    path('livraisons/', views_livraisons.gestion_livraisons, name='gestion_livraisons'),
    path('livraisons/equipements-employes/', views_livraisons.gestion_equipements_employes, name='gestion_equipements_employes'),
    path('livraisons/traiter/', views_livraisons.traiter_livraisons, name='traiter_livraisons'),
    path('livraisons/api/details/', views_livraisons.api_details_livraisons, name='api_details_livraisons'),
    path('livraisons/api/verifier-stock/', views_livraisons.api_verifier_stock_livraisons, name='api_verifier_stock_livraisons'),

    # Gestion des avances
    path('avances/', views_livraisons.gestion_avances, name='gestion_avances'),
    path('recettes-forfaitaires/', views_livraisons.gestion_recettes_forfaitaires, name='gestion_recettes_forfaitaires'),
    path('recettes-forfaitaires/changer-employe/', views_livraisons.api_changer_employe_recette_forfaitaire, name='api_changer_employe_recette_forfaitaire'),
    path('recettes-forfaitaires/impression-recap/', views_livraisons.imprimer_recap_factures_forfaitaires, name='imprimer_recap_factures_forfaitaires'),
    path('avances/traiter/', views_livraisons.traiter_avances, name='traiter_avances'),
    path('avances/api/supprimer-source/', views_livraisons.api_delete_avance_source, name='api_delete_avance_source'),
    path('avances/imprimer-tickets-recettes/', views_livraisons.imprimer_tickets_recettes, name='imprimer_tickets_recettes'),

    path('stock/', views_livraisons.fiche_stock, name='fiche_stock'),

    # Gestion forfaitaire
    path('forfaitaire/', views_forfaitaire.gestion_forfaitaire, name='gestion_forfaitaire'),
    path('forfaitaire/api/details/', views_forfaitaire.detail_forfaitaire_modal, name='api_detail_forfaitaire'),
    path('forfaitaire/api/update-detail/', views_forfaitaire.update_detail_point_eau, name='api_update_detail_forfaitaire'),
    path('forfaitaire/api/delete-detail/', views_forfaitaire.delete_detail_forfaitaire, name='api_delete_detail_forfaitaire'),
    path('forfaitaire/api/update-tarif/', views_forfaitaire.update_point_eau_tarif, name='api_update_tarif_forfaitaire'),
    path('forfaitaire/api/points-eau/', views_forfaitaire.api_points_eau_forfaitaire, name='api_points_eau_forfaitaire'),
    path('forfaitaire/api/get-detail/<uuid:detail_id>/', views_forfaitaire.get_detail_forfaitaire, name='api_get_detail_forfaitaire'),
    path('forfaitaire/api/update-quantity-prix/', views_forfaitaire.update_quantity_prix, name='api_update_quantity_prix'),

    # Gestion volumétrique (paiements au volume)
    path('volumetrique/', views_volumetrique_matriciel.suivi_paiements_matriciel, name='gestion_volumetrique'),
    path('volumetrique/global/', views_volumetrique_global.suivi_paiements_global, name='suivi_paiements_global'),
    path('volumetrique/details/', views_volumetrique.gestion_volumetrique, name='gestion_volumetrique_details'),
    path('volumetrique/impression/', views_impression.impression_gestion_volumetrique, name='impression_gestion_volumetrique'),
    path('volumetrique/analyse-consommation/', views_analyse_consommation.analyse_consommation, name='analyse_consommation'),
    path('volumetrique/kiosques-a-reclasser/', views_analyse_consommation.kiosques_a_reclasser, name='kiosques_a_reclasser'),
    path('volumetrique/api/changer-type-point-eau/', views_analyse_consommation.api_changer_type_point_eau, name='api_changer_type_point_eau'),
    path('volumetrique/analyse-consommation-comparatif/', views_analyse_consommation.analyse_consommation_comparatif, name='analyse_consommation_comparatif'),
    path('volumetrique/analyse-par-point-eau/', views_analyse_par_point_eau.analyse_par_point_eau, name='analyse_par_point_eau'),
    path('volumetrique/tableau-points-eau/', views_tableau_points_eau.tableau_points_eau, name='tableau_points_eau'),
    path('volumetrique/api/ouvrages-filtre-cascade/', views_analyse_consommation.api_ouvrages_filtre_cascade, name='api_ouvrages_filtre_cascade'),
    path('volumetrique/api/filtres-cascade/', views_analyse_consommation.api_filtres_cascade_consommation, name='api_filtres_cascade_consommation'),
    path('volumetrique/api/details-points-eau-mois/', views_analyse_consommation.api_details_points_eau_mois, name='api_details_points_eau_mois'),
    path('volumetrique/api/donnees-meteo/', views_analyse_consommation.api_donnees_meteo_filtrees, name='api_donnees_meteo'),
    path('volumetrique/api/points-eau-par-mois/', views_analyse_consommation.api_points_eau_par_mois, name='api_points_eau_par_mois'),
    path('cartes-sociales/analyse/', views_analyse_cartes_sociales.analyse_cartes_sociales, name='analyse_cartes_sociales'),
    path('cartes-sociales/analyse/comparaison-ouvrages/', views_analyse_cartes_sociales.comparaison_ouvrages_cartes_sociales, name='comparaison_ouvrages_cartes_sociales'),
    path('meteo/analyse/', views_analyse_meteo.analyse_meteo, name='analyse_meteo'),
    path('volumetrique/api/ouvrages-autocomplete/', views_volumetrique_matriciel.api_ouvrages_autocomplete, name='api_ouvrages_autocomplete'),
    path('volumetrique/api/releve/<uuid:releve_id>/update-diamex/', views_volumetrique.api_update_releve_diamex, name='api_update_releve_diamex'),

    # Gestion consommations cartes sociales
    path('conso-cartes-sociales/global/', views_conso_cartes_sociales.gestion_conso_cartes_sociales_global, name='conso_cartes_sociales_global'),
    path('conso-cartes-sociales/', views_conso_cartes_sociales.gestion_conso_cartes_sociales, name='conso_cartes_sociales'),
    path('conso-cartes-sociales/impression/', views_conso_cartes_sociales.impression_conso_cartes_sociales, name='impression_conso_cartes_sociales'),
    path('conso-cartes-sociales/api/data/', views_conso_cartes_sociales.api_conso_cartes_sociales_data, name='api_conso_cartes_sociales_data'),
    path('conso-cartes-sociales/api/commune/<uuid:commune_id>/', views_conso_cartes_sociales.api_commune_details, name='api_commune_details'),

    # Analyse des pièces de rechange
    path('analyse-pieces/', views_analyse_pieces.analyse_pieces_rechange, name='analyse_pieces_rechange'),
    path('analyse-pieces/api/piece/<uuid:designation_id>/', views_analyse_pieces.api_detail_piece, name='api_detail_piece'),
    path('analyse-pieces/api/ouvrage/<uuid:ouvrage_id>/', views_analyse_pieces.api_detail_ouvrage, name='api_detail_ouvrage'),
    path('analyse-pieces/par-commune/', views_analyse_pieces_geo.analyse_pieces_par_commune, name='analyse_pieces_par_commune'),
    path('analyse-pieces/par-district/', views_analyse_pieces_geo.analyse_pieces_par_district, name='analyse_pieces_par_district'),

    # Impression PDF planning agent
    path('imprimer-planning-agent/', views_livraisons.imprimer_planning_agent, name='imprimer_planning_agent'),

    # Impression PDF planning mensuel
    path('api/employes/', views_simple.employees_api_plain, name='api_employes_list'),
    path('print-pdf/', views.print_planning_pdf, name='print_planning_pdf'),
    path('print-fiche-temps/', views.print_fiche_temps, name='print_fiche_temps'),

    # Export / Import Excel
    path('export/plannings/', views.export_excel_plannings, name='export_excel_plannings'),
    path('export/details/', views.export_excel_details, name='export_excel_details'),
    path('export/bons-livraison/', views.export_excel_bons_livraison, name='export_excel_bons_livraison'),
    path('export/paiements-forfaitaires/', views.export_excel_paiements_forfaitaires, name='export_excel_paiements_forfaitaires'),
    path('export/participants/', views.export_excel_participants, name='export_excel_participants'),
    path('template/plannings/', views.template_excel_plannings, name='template_excel_plannings'),
    path('template/details/', views.template_excel_details, name='template_excel_details'),
    path('template/bons-livraison/', views.template_excel_bons_livraison, name='template_excel_bons_livraison'),
    path('template/paiements-forfaitaires/', views.template_excel_paiements_forfaitaires, name='template_excel_paiements_forfaitaires'),
    path('template/participants/', views.template_excel_participants, name='template_excel_participants'),
    path('import/plannings/', views.import_excel_plannings, name='import_excel_plannings'),
    path('import/details/', views.import_excel_details, name='import_excel_details'),
    path('import/bons-livraison/', views.import_excel_bons_livraison, name='import_excel_bons_livraison'),
    path('import/paiements-forfaitaires/', views.import_excel_paiements_forfaitaires, name='import_excel_paiements_forfaitaires'),
    path('import/participants/', views.import_excel_participants, name='import_excel_participants'),
    path('clear-all/', views.planning_clear_all, name='clear_all_planning'),

    # Gestion des déplacements
    path('deplacements/', views.deplacements_list, name='deplacements_list'),
    path('couts-types/api/apercu/', views_couts_types.api_cout_type_apercu, name='api_cout_type_apercu'),
    path('api/<uuid:planning_id>/appliquer-cout-type/', views_couts_types.api_planning_appliquer_cout_type, name='api_planning_appliquer_cout_type'),
    path('deplacements/create/', views.deplacement_create, name='deplacement_create'),
    path('deplacements/<uuid:deplacement_id>/update/', views.deplacement_update, name='deplacement_update'),
    path('deplacements/<uuid:deplacement_id>/delete/', views.deplacement_delete, name='deplacement_delete'),
    path('deplacements/export/', views.export_excel_deplacements, name='export_excel_deplacements'),
    path('deplacements/template/', views.template_excel_deplacements, name='template_excel_deplacements'),
    path('deplacements/import/', views.import_excel_deplacements, name='import_excel_deplacements'),

    # Workflow terrain (agents)
    path('terrain/traiter/<uuid:planning_id>/', views_terrain.traiter_activite, name='traiter_activite'),
    path('terrain/livraisons/utiliser/', views_terrain.marquer_utilise_livraisons, name='marquer_utilise_livraisons'),
    path('terrain/livraison/<uuid:detail_id>/utiliser/', views_terrain.marquer_utilise_livraison, name='marquer_utilise_livraison'),
    path('terrain/avances/utiliser/', views_terrain.marquer_utilise_avances, name='marquer_utilise_avances'),
    path('terrain/avance/<uuid:detail_id>/traiter/', views_terrain.traiter_avance, name='traiter_avance'),
    path('terrain/paiement/<uuid:detail_id>/traiter/', views_terrain.traiter_paiement_forfaitaire, name='traiter_paiement_forfaitaire'),
    path('terrain/facture/generer/', views_terrain.generer_facture_ticket, name='generer_facture_ticket'),
    path('terrain/fournisseurs/rechercher/', views_terrain.rechercher_fournisseurs, name='rechercher_fournisseurs'),
    path('terrain/qrcode/verifier/', views_terrain.verifier_bon_qrcode, name='verifier_bon_qrcode'),
    path('terrain/api/comptes-par-designation/', views_terrain.api_comptes_par_designation, name='api_comptes_par_designation'),

    # API pour filtres en cascade dans le formulaire
    path('api/activites-par-poste/', views.api_activites_par_poste, name='api_activites_par_poste'),
    path('api/equipements-par-ouvrage/', views.api_equipements_par_ouvrage, name='api_equipements_par_ouvrage'),
    path('api/pointseaus-par-ouvrage/', views.api_pointseaus_par_ouvrage, name='api_pointseaus_par_ouvrage'),
    path('api/designations-par-type-activite/', views.api_designations_par_type_activite, name='api_designations_par_type_activite'),
    path('api/compte-par-designation/', views.api_compte_par_designation, name='api_compte_par_designation'),
    path('api/prix-deplacement/', views.api_prix_deplacement, name='api_prix_deplacement'),
    path('api/villages-deplacement/', views.api_villages_deplacement, name='api_villages_deplacement'),
    path('api/planning/create/', views.create_planning, name='create_planning'),

    # API Annulation Repos/Jour férié
    path('api/<uuid:planning_id>/annuler-repos-ferie/', views_annulation_repos.api_annuler_repos_ferie, name='api_annuler_repos_ferie'),

    # Évaluation des objectifs du planning par poste
    path('evaluation-objectifs/', views_evaluation_objectifs.evaluation_objectifs_planning, name='evaluation_objectifs'),
    path('evaluation-objectifs/api/', views_evaluation_objectifs.api_evaluation_objectifs, name='api_evaluation_objectifs'),
    path('evaluation-objectifs/api/ouvrages-employe/<uuid:employe_id>/', views_evaluation_objectifs.api_ouvrages_employe, name='api_ouvrages_employe'),

    # Comptage des visites par ouvrage
    path('visites/', views_visites.visites_par_ouvrage, name='visites_par_ouvrage'),
    path('visites/global/', views_visites.visites_global, name='visites_global'),
    path('visites/api/', views_visites.api_visites_par_ouvrage, name='api_visites_par_ouvrage'),
    path('visites/api/export-excel/', views_visites.api_export_visites_excel, name='api_export_visites_excel'),
    path('visites/api/<uuid:ouvrage_id>/', views_visites.api_detail_visites_ouvrage, name='api_detail_visites_ouvrage'),
    path('debits-source/', views.debit_source_page, name='debit_source'),
    path('debits-source/export-excel/', views.export_excel_debits_source, name='export_excel_debits_source'),
    path('debits-source/export-pdf/', views.export_pdf_debits_source, name='export_pdf_debits_source'),
    path('debits-source/import-excel/', views.import_excel_debits_source, name='import_excel_debits_source'),
    path('debits-source/template-excel/', views.template_excel_debits_source, name='template_excel_debits_source'),
    path('debits-source/api/filter-options/', views.api_debit_source_filter_options, name='api_debit_source_filter_options'),
    path('debits-source/api/alert-count/', views.api_debits_source_alert_count, name='api_debits_source_alert_count'),

    # Modal de bienvenue
    path('api/planning-7-jours/', views_modal_bienvenue.api_planning_7_jours, name='api_planning_7_jours'),
    path('api/situations-attention-employe/', views_modal_bienvenue.api_situations_attention_employe, name='api_situations_attention_employe'),
    path('api/trajet-suggere/', views_tournee_routiere.api_trajet_suggere, name='api_trajet_suggere'),
    path('tournee/', views_tournee_routiere.page_tournee, name='tournee_routiere'),
    path('api/tournee/', views_tournee_routiere.api_tournee, name='api_tournee'),
    path('api/agents-du-jour/', views_tournee_routiere.api_agents_du_jour, name='api_agents_du_jour'),
    path('api/positions-gps/', views_tournee_routiere.api_positions_gps, name='api_positions_gps'),
    path('api/preparer-tournee/', views_preparation_tournee.api_preparer_tournee, name='api_preparer_tournee'),
    path('api/mobile/terrain/sync-item/', views_preparation_tournee.api_sync_terrain_item, name='api_sync_terrain_item'),
    path('api/mobile/reparation/enregistrer/', views_preparation_tournee.api_enregistrer_reparation_mobile, name='api_enregistrer_reparation_mobile'),
    path('api/mobile/reparation/<uuid:planning_id>/photo/', views_preparation_tournee.api_photo_reparation_mobile, name='api_photo_reparation_mobile'),
    path('api/mobile/planning/enregistrer/', views_preparation_tournee.api_enregistrer_planning_mobile, name='api_enregistrer_planning_mobile'),
    path('api/mobile/terrain/classement/', views_terrain_points.api_classement_terrain_mobile, name='api_classement_terrain_mobile'),
    path('api/mobile/ouvrage/<uuid:ouvrage_id>/debits/', views_preparation_tournee.api_debits_ouvrage_mobile, name='api_debits_ouvrage_mobile'),
    path('api/mobile/point-eau/<uuid:point_eau_id>/factures/', views_preparation_tournee.api_factures_point_eau_mobile, name='api_factures_point_eau_mobile'),

    # Pages de test / debug retirées (gabarits absents, erreur 500 en production) :
    # test-buttons/, debug/, test-grid/

    # CRUD en cascade
    path('', include('apps.planning.urls_crud')),
    path('livraisons/maintenance/', views_livraisons.maintenance_livraisons, name='maintenance_livraisons'),
    path('avances/maintenance/', views_livraisons.maintenance_avances, name='maintenance_avances'),
]
