from django.urls import path
from . import views_config_tarif_forfaitaire
from . import views, views_caissiere, views_releves, views_bp, views_bp_import, views_bp_workflow, views_facturation, views_encaissement, views_cartes_sociales, views_frais_deplacement, views_paiement_forfaitaire, views_suivi_forfaitaire, views_previsions, views_coupures_volumetrique, views_fournisseurs, views_encaissement_forfaitaire, views_mvola, views_frais_mvola
from . import views_depenses_services
from . import views_mobile_volume
from . import views_sms
from apps.core import views_photos

app_name = 'billing'

urlpatterns = [
    path('api/mobile/volume/bootstrap/', views_mobile_volume.bootstrap, name='mobile_volume_bootstrap'),
    # Rappels SMS de paiement
    path('sms/historique/', views_sms.historique, name='sms_historique'),
    path('sms/relancer/<uuid:pk>/', views_sms.relancer, name='sms_relancer'),
    path('sms/lancer/', views_sms.lancer, name='sms_lancer'),
    path('api/mobile/volume/sync/', views_mobile_volume.sync_operation, name='mobile_volume_sync'),
    path('', views.billing_dashboard, name='dashboard'),
    path('clients/', views.clients_list, name='clients'),
    # Les clients sont des PointEau (clé UUID) : <int:pk> rendait la liste en erreur 500 (NoReverseMatch)
    path('clients/<uuid:pk>/', views.client_detail, name='client_detail'),
    path('compteurs/', views.compteurs_list, name='compteurs'),

    # Workflow des relevés (remplace l'ancienne page)
    path('releves/', views_releves.releves_workflow, name='releves'),
    path('releves/consommations-cartes-sociales/', views_releves.gestion_consos_cartes_sociales, name='gestion_consos_cartes_sociales'),
    path('api/points-eau-par-ouvrage/<uuid:ouvrage_id>/', views_releves.api_points_eau_par_ouvrage, name='api_points_eau_par_ouvrage'),
    path('api/ouvrages-campagne/', views_releves.api_ouvrages_campagne, name='api_ouvrages_campagne'),
    path('api/point-eau-details/<uuid:point_eau_id>/', views_releves.api_point_eau_details, name='api_point_eau_details'),
    path('api/changement-compteur-abonne/', views_releves.api_changement_compteur_abonne, name='api_changement_compteur_abonne'),
    path('api/releve-reference/<uuid:point_eau_id>/', views_releves.api_releve_reference, name='api_releve_reference'),
    path('api/cartes-sociales/<uuid:point_eau_id>/', views_releves.api_cartes_sociales, name='api_cartes_sociales'),
    path('api/save-releve/', views_releves.api_save_releve, name='api_save_releve'),
    path('api/releve-terrain/', views_releves.api_releve_terrain, name='api_releve_terrain'),
    path('api/template-releves/', views_releves.api_template_releves, name='api_template_releves'),
    path('api/template-cartes-sociales/', views_releves.api_template_cartes_sociales, name='api_template_cartes_sociales'),
    path('api/export-releves/', views_releves.api_export_releves, name='api_export_releves'),
    path('api/import-releves/', views_releves.api_import_releves, name='api_import_releves'),
    path('api/import-releves-streaming/', views_releves.api_import_releves_streaming, name='api_import_releves_streaming'),
    path('api/supprimer-releve/', views_releves.api_supprimer_releve, name='api_supprimer_releve'),
    path('api/modifier-releve/', views_releves.api_modifier_releve, name='api_modifier_releve'),
    path('api/imprimer-facture-releve/<uuid:releve_id>/', views_releves.api_imprimer_facture_releve, name='api_imprimer_facture_releve'),
    path('api/create-beneficiaire/', views_releves.api_create_beneficiaire, name='api_create_beneficiaire'),
    path('api/save-cartes-sociales-brouillon/', views_releves.api_save_cartes_sociales_brouillon, name='api_save_cartes_sociales_brouillon'),

    # APIs Coupures/Remises volumétriques
    path('coupures-eau/', views_coupures_volumetrique.gestion_coupures_eau, name='gestion_coupures_eau'),
    path('coupures-eau/historique/', views_coupures_volumetrique.historique_coupures_eau, name='historique_coupures_eau'),
    path('coupures-eau/historique/export/', views_coupures_volumetrique.export_historique_coupures_eau_excel, name='export_historique_coupures_eau_excel'),
    path('api/points-eau-actifs/', views_coupures_volumetrique.api_points_eau_actifs, name='api_points_eau_actifs'),
    path('api/couper-point-eau/', views_coupures_volumetrique.api_couper_point_eau, name='api_couper_point_eau'),
    path('api/remettre-point-eau/', views_coupures_volumetrique.api_remettre_point_eau, name='api_remettre_point_eau'),
    path('api/points-eau-coupes/', views_coupures_volumetrique.api_points_eau_coupes, name='api_points_eau_coupes'),
    path('api/historique-coupures/', views_coupures_volumetrique.api_historique_coupures, name='api_historique_coupures'),
    path('api/historique-coupures/modifier/', views_coupures_volumetrique.api_modifier_historique_coupure, name='api_modifier_historique_coupure'),
    path('api/historique-coupures/supprimer/', views_coupures_volumetrique.api_supprimer_historique_coupure, name='api_supprimer_historique_coupure'),
    path('api/historique-coupures/supprimer-lot/', views_coupures_volumetrique.api_supprimer_historique_coupures_bulk, name='api_supprimer_historique_coupures_bulk'),
    path('api/points-eau/tarif-forfaitaire/modifier/', views_coupures_volumetrique.api_modifier_tarif_forfaitaire_point_eau, name='api_modifier_tarif_forfaitaire_point_eau'),

    path('factures/', views.factures_list, name='factures'),
    path('paiements/', views.paiements_list, name='paiements'),

    # URLs pour TypePointEau
    path('types-points-eau/', views.typepointeau_list, name='typepointeau_list'),
    path('types-points-eau/nouveau/', views.typepointeau_create, name='typepointeau_create'),
    path('types-points-eau/<uuid:pk>/', views.typepointeau_detail, name='typepointeau_detail'),
    path('types-points-eau/<uuid:pk>/modifier/', views.typepointeau_edit, name='typepointeau_edit'),
    path('types-points-eau/<uuid:pk>/supprimer/', views.typepointeau_delete, name='typepointeau_delete'),

    # URLs pour composants des types de points d'eau (en cascade)
    path('types-points-eau/<uuid:type_pk>/composants/', views.composants_type_point_eau_list, name='composants_type_point_eau_list'),
    path('types-points-eau/<uuid:type_pk>/composants/nouveau/', views.composant_type_point_eau_create, name='composant_type_point_eau_create'),
    path('types-points-eau/<uuid:type_pk>/composants/<uuid:composant_pk>/modifier/', views.composant_type_point_eau_edit, name='composant_type_point_eau_edit'),
    path('types-points-eau/<uuid:type_pk>/composants/<uuid:composant_pk>/supprimer/', views.composant_type_point_eau_delete, name='composant_type_point_eau_delete'),

    # API pour gestion en cascade des composants
    path('api/composants-type-point-eau/<uuid:type_pk>/', views.api_composants_type_point_eau_list, name='api_composants_type_point_eau_list'),
    path('api/composants-type-point-eau/<uuid:type_pk>/<uuid:composant_pk>/', views.api_composant_type_point_eau_detail, name='api_composant_type_point_eau_detail'),
    path('api/composants-type-point-eau/<uuid:type_pk>/create/', views.api_composant_type_point_eau_create, name='api_composant_type_point_eau_create'),
    path('api/composants-type-point-eau/<uuid:type_pk>/<uuid:composant_pk>/edit/', views.api_composant_type_point_eau_edit, name='api_composant_type_point_eau_edit'),
    path('api/composants-type-point-eau/<uuid:type_pk>/<uuid:composant_pk>/delete/', views.api_composant_type_point_eau_delete, name='api_composant_type_point_eau_delete'),

    # API pour gestion des points de controle par composant
    path('api/composants-type-point-eau/<uuid:composant_pk>/points-controle/', views.api_points_controle_composant_list, name='api_points_controle_composant_list'),
    path('api/composants-type-point-eau/<uuid:composant_pk>/points-controle/create/', views.api_point_controle_composant_create, name='api_point_controle_composant_create'),
    path('api/composants-type-point-eau/<uuid:composant_pk>/points-controle/<uuid:point_controle_pk>/edit/', views.api_point_controle_composant_edit, name='api_point_controle_composant_edit'),
    path('api/composants-type-point-eau/<uuid:composant_pk>/points-controle/<uuid:point_controle_pk>/delete/', views.api_point_controle_composant_delete, name='api_point_controle_composant_delete'),

    # API pour lister tous les points de controle (pour sélecteurs)
    path('api/points-controle/', views.api_points_controle_list, name='api_points_controle_list'),

    # API pour recherche de points d'eau
    path('api/points-eau/search/', views.api_points_eau_search, name='api_points_eau_search'),

    # Page consolidée des points d'eau
    path('consolidated-points-eau/', views.consolidated_points_eau, name='consolidated_points_eau'),

    # API pour mise à jour point d'eau
    path('api/point-eau/<uuid:point_eau_id>/update/', views.update_point_eau_api, name='update_point_eau_api'),
    # Modification du seul type de point d'eau / type d'abonné (modal du dashboard)
    path('api/point-eau/<uuid:point_eau_id>/type/', views.update_point_eau_type_api, name='update_point_eau_type_api'),

    # API pour récupérer détails complets d'un point d'eau
    path('api/point-eau/<uuid:point_eau_id>/details/', views.point_eau_details_api, name='point_eau_details_api'),

    # APIs pour parcelle (autocomplétion modal points d'eau)
    path('api/point-eau/<uuid:point_eau_id>/parcelle-info/', views.api_point_eau_parcelle_info, name='api_point_eau_parcelle_info'),
    path('api/parcelles/search/', views.api_parcelles_search, name='api_parcelles_search'),

    # Module caissière - Traitement des retours de tickets
    path('caissiere/retours/', views_caissiere.traitement_retours_caissiere, name='traitement_retours_caissiere'),
    path('caissiere/api/scanner-ticket/', views_caissiere.api_scanner_ticket, name='api_scanner_ticket'),
    path('caissiere/api/valider-retour/', views_caissiere.api_valider_retour_ticket, name='api_valider_retour_ticket'),
    path('caissiere/api/liste-lignes-diamex/', views_caissiere.api_liste_lignes_diamex, name='api_liste_lignes_diamex'),
    path('caissiere/api/details-en-attente/', views_caissiere.api_details_en_attente_retour, name='api_details_en_attente_retour'),
    path('caissiere/api/derniers-tickets/', views_caissiere.api_derniers_tickets_traites, name='api_derniers_tickets_traites'),
    path('caissiere/api/annuler-tickets/', views_caissiere.api_annuler_tickets_date, name='api_annuler_tickets_date'),

    # APIs pour listes déroulantes du modal d'édition
    path('caissiere/api/journaux/', views_caissiere.api_get_journaux, name='api_get_journaux'),
    path('caissiere/api/fournisseurs/', views_caissiere.api_get_fournisseurs, name='api_get_fournisseurs'),
    path('caissiere/api/bases/', views_caissiere.api_get_bases, name='api_get_bases'),
    path('caissiere/api/comptes-designation/', views_caissiere.api_get_comptes_par_designation, name='api_get_comptes_par_designation'),

    # Module Demandes de Branchements Privés (BP)
    path('demandes-bp/', views_bp.demandes_bp_list, name='demandes_bp'),
    path('demandes-bp/api/list/', views_bp.api_demandes_bp_list, name='api_demandes_bp_list'),
    path('demandes-bp/api/create/', views_bp.api_demande_bp_create, name='api_demande_bp_create'),
    path('demandes-bp/api/<uuid:demande_id>/update/', views_bp.api_demande_bp_update, name='api_demande_bp_update'),
    path('demandes-bp/api/<uuid:demande_id>/exporter/', views_bp.api_demande_bp_exporter, name='api_demande_bp_exporter'),
    path('demandes-bp/api/lignes-diamex/', views_bp.api_lignes_diamex_list, name='api_lignes_diamex_list'),

    # Import des paiements BP (mise à jour uniquement des 8 colonnes de paiements)
    path('demandes-bp/import/', views_bp_import.import_paiements_bp_page, name='import_paiements_bp'),
    path('demandes-bp/api/import/', views_bp_import.api_import_paiements_bp, name='api_import_paiements_bp'),
    path('demandes-bp/api/template/', views_bp_import.api_template_paiements_bp, name='api_template_paiements_bp'),

    # Workflow paiements BP (demande, devis, branchement)
    path('demandes-bp/api/<uuid:point_eau_id>/calculer-montant-demande/', views_bp_workflow.api_calculer_montant_demande, name='api_calculer_montant_demande'),
    path('demandes-bp/api/<uuid:point_eau_id>/calculer-montant-devis/', views_bp_workflow.api_calculer_montant_devis, name='api_calculer_montant_devis'),
    path('demandes-bp/api/<uuid:point_eau_id>/paiement-demande/', views_bp_workflow.api_paiement_demande, name='api_paiement_demande'),
    path('demandes-bp/api/<uuid:point_eau_id>/paiement-devis/', views_bp_workflow.api_paiement_devis, name='api_paiement_devis'),
    path('demandes-bp/api/<uuid:point_eau_id>/enregistrer-branchement/', views_bp_workflow.api_enregistrer_branchement, name='api_enregistrer_branchement'),
    path('demandes-bp/api/<uuid:point_eau_id>/details-pointage/', views_bp.api_details_pointage_demande_bp, name='api_details_pointage_demande_bp'),
    path('demandes-bp/api/<uuid:point_eau_id>/pointer/', views_bp.api_pointer_demande_bp, name='api_pointer_demande_bp'),

    # Module Facturation volumétrique
    path('facturation/', views_facturation.workflow_facturation, name='workflow_facturation'),
    path('facturation/api/calculer-factures/', views_facturation.api_calculer_factures, name='api_calculer_factures'),
    path('facturation/api/valider-factures/', views_facturation.api_valider_factures, name='api_valider_factures'),
    path('facturation/api/marquer-imprimees/', views_facturation.api_marquer_factures_imprimees, name='api_marquer_factures_imprimees'),

    # APIs Workflow Terrain
    path('api/point-eau-by-code/<str:code>/', views_releves.api_point_eau_by_code, name='api_point_eau_by_code'),
    path('api/calculer-facture-terrain/', views_releves.api_calculer_facture_terrain, name='api_calculer_facture_terrain'),
    path('api/save-releve-terrain/', views_releves.api_save_releve_terrain, name='api_save_releve_terrain'),
    path('api/rechercher-ouvrages/', views_releves.api_rechercher_ouvrages, name='api_rechercher_ouvrages'),
    path('api/points-eau-by-ouvrage/<uuid:ouvrage_id>/', views_releves.api_points_eau_by_ouvrage, name='api_points_eau_by_ouvrage'),
    path('api/points-eau-by-gps/', views_releves.api_points_eau_by_gps, name='api_points_eau_by_gps'),

    # Encaissement des factures (Caissière)
    path('encaissement/', views_encaissement.encaissement_factures, name='encaissement_factures'),
    path('encaissement/api/factures/', views_encaissement.api_factures_a_encaisser, name='api_factures_a_encaisser'),
    path('encaissement/api/resoudre-qr/', views_encaissement.api_resoudre_facture_qr, name='api_resoudre_facture_qr'),
    path('encaissement/api/valider/', views_encaissement.api_valider_encaissement_groupe, name='api_valider_encaissement_groupe'),
    path('encaissement/api/ouvrages/', views_encaissement.api_liste_ouvrages, name='api_liste_ouvrages_encaissement'),
    path('encaissement/api/journaux/', views_encaissement.api_liste_journaux, name='api_liste_journaux'),
    path('encaissement/api/derniers/', views_encaissement.api_derniers_encaissements, name='api_derniers_encaissements'),
    path('encaissement/api/idxls-deja-pointes/', views_encaissement.api_idxls_deja_pointes, name='api_idxls_deja_pointes'),
    path('encaissement/api/annuler/', views_encaissement.api_annuler_encaissement, name='api_annuler_encaissement'),

    # Workflow Cartes Sociales
    path('cartes-sociales/', views_cartes_sociales.cartes_sociales_workflow, name='cartes_sociales_workflow'),
    path('cartes-sociales/api/list/', views_cartes_sociales.api_cartes_list, name='api_cartes_list'),
    path('cartes-sociales/api/supprimer/', views_cartes_sociales.api_supprimer_carte, name='api_supprimer_carte'),
    path('cartes-sociales/api/imprimer/', views_cartes_sociales.api_imprimer_ticket, name='api_imprimer_ticket'),
    path('cartes-sociales/encaissement/', views_cartes_sociales.cartes_sociales_encaissement, name='cartes_sociales_encaissement'),
    path('cartes-sociales/api/consos/', views_cartes_sociales.api_consos_a_encaisser, name='api_consos_a_encaisser'),
    path('cartes-sociales/api/ouvrages/', views_cartes_sociales.api_liste_ouvrages_cartes_sociales, name='api_liste_ouvrages_cartes_sociales'),
    path('cartes-sociales/api/valider/', views_cartes_sociales.api_valider_encaissement_cartes_sociales, name='api_valider_encaissement_cartes_sociales'),
    path('cartes-sociales/api/derniers/', views_cartes_sociales.api_derniers_encaissements_cartes_sociales, name='api_derniers_encaissements_cartes_sociales'),
    path('cartes-sociales/api/export-diamex/', views_cartes_sociales.api_export_diamex, name='api_export_diamex'),
    path('cartes-sociales/api/sync-diamex/', views_cartes_sociales.api_sync_diamex, name='api_sync_diamex'),

    # Excel import/export pour cartes sociales
    path('cartes-sociales/api/export-excel/', views_cartes_sociales.api_export_consos_excel, name='api_export_consos_excel'),
    path('cartes-sociales/api/template-excel/', views_cartes_sociales.api_template_consos_excel, name='api_template_consos_excel'),
    path('cartes-sociales/api/import-excel/', views_cartes_sociales.api_import_consos_excel, name='api_import_consos_excel'),

    # Module Retour frais de déplacement
    path('frais-deplacement/retours/', views_frais_deplacement.retour_frais_deplacement, name='retour_frais_deplacement'),
    path('frais-deplacement/retours/print/', views_frais_deplacement.retour_frais_deplacement_print, name='retour_frais_deplacement_print'),
    path('frais-deplacement/api/liste/', views_frais_deplacement.api_frais_deplacement_employe, name='api_frais_deplacement_employe'),
    path('frais-deplacement/api/imprimer/', views_frais_deplacement.api_imprimer_frais_deplacement, name='api_imprimer_frais_deplacement'),
    path('frais-deplacement/api/update-montant/', views_frais_deplacement.api_update_montant_frais, name='api_update_montant_frais'),

    # Workflow des dépenses de services (hors planningdetails)
    path('depenses-services/workflow/', views_depenses_services.depenses_services_workflow, name='depenses_services_workflow'),
    path('depenses-services/list/', views_depenses_services.api_depenses_services_list, name='api_depenses_services_list'),
    path('depenses-services/create/', views_depenses_services.api_depenses_services_create, name='api_depenses_services_create'),
    path('depenses-services/<uuid:depense_id>/update/', views_depenses_services.api_depenses_services_update, name='api_depenses_services_update'),
    path('depenses-services/<uuid:depense_id>/delete/', views_depenses_services.api_depenses_services_delete, name='api_depenses_services_delete'),
    path('depenses-services/<uuid:depense_id>/signer/', views_depenses_services.api_depenses_services_signer, name='api_depenses_services_signer'),
    path('depenses-services/total-lettres/', views_depenses_services.api_depenses_services_total_lettres, name='api_depenses_services_total_lettres'),

    # Configuration des tarifs forfaitaires pleins par type de point d'eau
    path('config-tarifs-forfaitaires/', views_config_tarif_forfaitaire.config_tarifs_forfaitaires, name='config_tarifs_forfaitaires'),
    path('config-tarifs-forfaitaires/api/creer/', views_config_tarif_forfaitaire.api_config_tarif_creer, name='api_config_tarif_creer'),
    path('config-tarifs-forfaitaires/api/<uuid:config_id>/modifier/', views_config_tarif_forfaitaire.api_config_tarif_modifier, name='api_config_tarif_modifier'),
    path('config-tarifs-forfaitaires/api/<uuid:config_id>/supprimer/', views_config_tarif_forfaitaire.api_config_tarif_supprimer, name='api_config_tarif_supprimer'),

    # Workflow Paiements Forfaitaires
    path('paiements-forfaitaires/', views_paiement_forfaitaire.workflow_paiement_forfaitaire, name='workflow_paiement_forfaitaire'),
    path('paiements-forfaitaires/api/points-eau/', views_paiement_forfaitaire.api_points_eau_forfaitaires, name='api_points_eau_forfaitaires'),
    path('paiements-forfaitaires/api/enregistrer/', views_paiement_forfaitaire.api_enregistrer_paiements, name='api_enregistrer_paiements'),
    path('paiements-forfaitaires/api/list/', views_encaissement_forfaitaire.api_liste_paiements_forfaitaires, name='api_liste_paiements_forfaitaires'),
    path('paiements-forfaitaires/api/encaisser/', views_encaissement_forfaitaire.api_encaisser_paiements, name='api_encaisser_paiements_forfaitaires'),
    path('paiements-forfaitaires/api/annuler-encaissement/', views_encaissement_forfaitaire.api_annuler_encaissement, name='api_annuler_encaissement_forfaitaire'),
    path('paiements-forfaitaires/api/derniers-encaissements/', views_encaissement_forfaitaire.api_derniers_encaissements, name='api_derniers_encaissements_forfaitaires'),
    path('paiements-forfaitaires/encaissement-groupe/', views_encaissement_forfaitaire.encaissement_groupe, name='encaissement_groupe'),
    path('encaissement-forfaitaire/', views_encaissement_forfaitaire.encaissement_groupe, name='encaissement_forfaitaire'),
    path('paiements-forfaitaires/template/', views_paiement_forfaitaire.template_excel_paiements_forfaitaires, name='template_excel_paiements_forfaitaires'),
    path('paiements-forfaitaires/export/', views_paiement_forfaitaire.export_excel_paiements_forfaitaires, name='export_excel_paiements_forfaitaires'),
    path('paiements-forfaitaires/import/', views_paiement_forfaitaire.import_excel_paiements_forfaitaires, name='import_excel_paiements_forfaitaires'),

    # Suivi Paiements Forfaitaires (par ouvrage)
    path('suivi-forfaitaires/', views_suivi_forfaitaire.suivi_paiements_forfaitaires, name='suivi_paiements_forfaitaires'),
    path('suivi-forfaitaires/api/ouvrages/', views_suivi_forfaitaire.api_ouvrages_forfaitaires, name='api_ouvrages_forfaitaires'),
    path('suivi-forfaitaires/api/coupure/create/', views_suivi_forfaitaire.api_create_coupure, name='api_create_coupure'),
    path('suivi-forfaitaires/api/coupure/<uuid:coupure_id>/update/', views_suivi_forfaitaire.api_update_coupure, name='api_update_coupure'),
    path('suivi-forfaitaires/api/coupure/<uuid:coupure_id>/delete/', views_suivi_forfaitaire.api_delete_coupure, name='api_delete_coupure'),
    path('suivi-forfaitaires/api/paiement/create/', views_suivi_forfaitaire.api_create_paiement, name='api_create_paiement'),
    path('suivi-forfaitaires/api/paiement/<uuid:paiement_id>/delete/', views_suivi_forfaitaire.api_delete_paiement, name='api_delete_paiement'),
    path('suivi-forfaitaires/api/paiement/valider/', views_suivi_forfaitaire.api_valider_paiement, name='api_valider_paiement'),
    path('suivi-forfaitaires/export-excel/', views_suivi_forfaitaire.export_excel_paiements, name='export_excel_paiements'),

    # Import/Export Coupures d'eau
    path('suivi-forfaitaires/coupures/export-excel/', views_suivi_forfaitaire.export_excel_coupures, name='export_excel_coupures'),
    path('suivi-forfaitaires/coupures/template/', views_suivi_forfaitaire.template_excel_coupures, name='template_excel_coupures'),
    path('suivi-forfaitaires/coupures/import/', views_suivi_forfaitaire.import_excel_coupures, name='import_excel_coupures'),

    # Module Prévisions Budgétaires
    path('previsions/', views_previsions.previsions_budget_page, name='previsions_budget'),
    path('previsions/recap/', views_previsions.recap_previsions_budget, name='recap_previsions_budget'),
    path('previsions/api/list/', views_previsions.api_previsions_list, name='api_previsions_list'),
    path('previsions/api/recap/', views_previsions.api_recap_previsions, name='api_recap_previsions'),
    path('previsions/api/recalculer/', views_previsions.api_recalculer_previsions, name='api_recalculer_previsions'),
    path('previsions/api/resume/', views_previsions.api_resume_previsions, name='api_resume_previsions'),
    path('previsions/api/configuration/', views_previsions.api_update_configuration, name='api_update_configuration'),
    path('previsions/api/<uuid:prevision_id>/delete/', views_previsions.api_delete_prevision, name='api_delete_prevision'),
    path('previsions/api/communes/', views_previsions.api_communes_by_district, name='api_communes_by_district'),
    path('previsions/api/ouvrages/', views_previsions.api_ouvrages_by_commune, name='api_ouvrages_by_commune'),
    path('previsions/export-excel/', views_previsions.export_previsions_excel, name='export_previsions_excel'),

    # Gestion dépenses récurrentes
    path('previsions/depenses-recurrentes/', views_previsions.depenses_recurrentes_page, name='depenses_recurrentes_management'),
    path('previsions/api/depenses-recurrentes/list/', views_previsions.api_depenses_recurrentes_list, name='api_depenses_recurrentes_list'),
    path('previsions/api/depenses-recurrentes/delete/', views_previsions.api_supprimer_depense_recurrente, name='api_supprimer_depense_recurrente'),
    path('previsions/api/depenses-recurrentes/delete-batch/', views_previsions.api_supprimer_depenses_recurrentes_batch, name='api_supprimer_depenses_recurrentes_batch'),

    # Upload photos Points d'Eau
    path('api/point-eau/<uuid:point_eau_id>/upload-photos/', views_photos.upload_point_eau_photos, name='upload_point_eau_photos'),

    # Fournisseurs CRUD
    path('fournisseurs/', views_fournisseurs.fournisseurs_list, name='fournisseurs_list'),
    path('fournisseurs/doublons/', views_fournisseurs.fournisseurs_duplicates, name='fournisseurs_duplicates'),
    path('fournisseurs/adresses-districts/', views_fournisseurs.fournisseurs_adresses_districts, name='fournisseurs_adresses_districts'),
    path('api/fournisseurs/code-tiers-disponible/', views_fournisseurs.fournisseur_code_tiers_disponible_api, name='fournisseur_code_tiers_disponible_api'),
    path('api/fournisseurs/adresses-districts/create/', views_fournisseurs.fournisseur_adresse_create_api, name='fournisseur_adresse_create_api'),
    path('api/fournisseurs/adresses-districts/detail/', views_fournisseurs.fournisseur_adresse_detail_api, name='fournisseur_adresse_detail_api'),
    path('api/fournisseurs/adresses-districts/merge/', views_fournisseurs.fournisseur_adresse_merge_api, name='fournisseur_adresse_merge_api'),
    path('api/fournisseurs/adresses-districts/upsert/', views_fournisseurs.fournisseur_adresse_mapping_upsert_api, name='fournisseur_adresse_mapping_upsert_api'),
    path('api/fournisseurs/adresses-districts/update/', views_fournisseurs.fournisseur_adresse_update_api, name='fournisseur_adresse_update_api'),
    path('api/fournisseurs/<uuid:pk>/compta-details/', views_fournisseurs.fournisseur_compta_details_api, name='fournisseur_compta_details_api'),
    path('api/fournisseurs/<uuid:pk>/', views_fournisseurs.fournisseur_detail_api, name='fournisseur_detail_api'),
    path('api/fournisseurs/create/', views_fournisseurs.fournisseur_create_api, name='fournisseur_create_api'),
    path('api/fournisseurs/merge/', views_fournisseurs.fournisseur_merge_api, name='fournisseur_merge_api'),
    path('api/fournisseurs/merge-instructions/<uuid:instruction_id>/update/', views_fournisseurs.fournisseur_merge_instruction_update_api, name='fournisseur_merge_instruction_update_api'),
    path('api/fournisseurs/duplicate-suggestions/ignore/', views_fournisseurs.fournisseur_duplicate_ignore_api, name='fournisseur_duplicate_ignore_api'),
    path('api/fournisseurs/duplicate-suggestions/ignore-batch/', views_fournisseurs.fournisseur_duplicate_ignore_batch_api, name='fournisseur_duplicate_ignore_batch_api'),
    path('api/fournisseurs/<uuid:pk>/update/', views_fournisseurs.fournisseur_update_api, name='fournisseur_update_api'),
    path('api/fournisseurs/<uuid:pk>/delete/', views_fournisseurs.fournisseur_delete_api, name='fournisseur_delete_api'),

    # APIs Paiements Forfaitaires (pour recoupement)
    path('api/paiements-forfaitaires/point-eau/<uuid:pe_id>/', views_paiement_forfaitaire.api_get_paiements_point_eau, name='api_get_paiements_point_eau'),
    path('api/paiements-forfaitaires/ouvrage/<uuid:ouvrage_id>/', views_paiement_forfaitaire.api_get_paiements_ouvrage, name='api_get_paiements_ouvrage'),
    path('api/paiements-forfaitaires-par-diamex/', views_paiement_forfaitaire.api_paiements_par_diamex, name='api_paiements_par_diamex'),
    path('api/paiement-forfaitaire/<uuid:paiement_id>/', views_paiement_forfaitaire.api_paiement_detail, name='api_paiement_detail'),
    path('api/paiement-forfaitaire/<uuid:paiement_id>/update/', views_paiement_forfaitaire.api_paiement_update, name='api_paiement_update'),
    path('api/paiement-forfaitaire/<uuid:paiement_id>/supprimer/', views_paiement_forfaitaire.supprimer_paiement_forfaitaire, name='supprimer_paiement_forfaitaire'),
    path('api/paiement-forfaitaire/create/', views_paiement_forfaitaire.api_paiement_create, name='api_paiement_create'),
    path('api/points-eau-par-diamex/', views_paiement_forfaitaire.api_points_eau_par_numero_base_diamex, name='api_points_eau_par_diamex'),
    path('api/paiements-non-payes-par-ouvrage/', views_paiement_forfaitaire.api_paiements_non_payes_par_ouvrage, name='api_paiements_non_payes_par_ouvrage'),
    path('api/points-eau-par-ouvrage/', views_paiement_forfaitaire.api_points_eau_par_ouvrage, name='api_points_eau_par_ouvrage_forfaitaire'),

    # APIs MVola (paiement mobile money)
    path('api/paiement/mvola/initier/', views_mvola.initier_paiement_mvola, name='initier_paiement_mvola'),
    path('api/paiement/mvola/callback/', views_mvola.callback_mvola, name='callback_mvola'),

    # Gestion des frais de transfert MVola
    path('frais-mvola/', views_frais_mvola.frais_mvola_list, name='frais_mvola_list'),
    path('api/frais-mvola/calculer/', views_frais_mvola.frais_mvola_calculer_api, name='frais_mvola_calculer_api'),
    path('api/frais-mvola/create/', views_frais_mvola.frais_mvola_create_api, name='frais_mvola_create_api'),
    path('api/frais-mvola/<uuid:pk>/update/', views_frais_mvola.frais_mvola_update_api, name='frais_mvola_update_api'),
    path('api/frais-mvola/<uuid:pk>/delete/', views_frais_mvola.frais_mvola_delete_api, name='frais_mvola_delete_api'),
]
