from django.urls import path
from django.views.generic import RedirectView
from . import (
    views,
    views_rapports,
    views_impression,
    views_documentation,
    views_document_extraction,
    views_qualite_donnees,
    views_search,
    views_language,
    views_villages_desserte,
    views_ouvrage_interventions,
    views_geographic_filters,
    views_personnes,
    views_widget,
    views_mobile_auth,
    views_mobile_search,
    views_mobile_salary,
    views_search_evolved,
    views_filtres_sauvegardes,
    views_contributions,
)
from hydria.views import home as main_dashboard
from apps.billing import views_depenses_services

app_name = 'core'

urlpatterns = [
    # Page d'accueil redirige vers le fil d'actualité
    path('', RedirectView.as_view(pattern_name='home_launcher', permanent=False), name='home'),

    # Dashboard principal
    path('dashboard/', main_dashboard, name='dashboard'),

    # API Changement de langue
    path('api/set-language/', views_language.set_language, name='set_language'),

    # API Recherche globale
    path('api/search/global/', views_search.api_search_global, name='api_search_global'),

    # Métadonnées communes pour le regroupement des filtres géographiques
    path(
        'api/geographic-filter-hierarchy/',
        views_geographic_filters.geographic_filter_hierarchy,
        name='geographic_filter_hierarchy',
    ),

    # Documentation
    path('documentation/', views_documentation.documentation_protocols_home, name='documentation_protocols_home'),
    path('documentation/modules/', views_documentation.documentation_module_list, name='documentation_module_list'),
    path('documentation/modules/<slug:slug>/', views_documentation.documentation_module_detail, name='documentation_module_detail'),
    path('documentation/tests/', views_documentation.test_protocol_list, name='test_protocol_list'),
    path('documentation/tests/<str:code>/', views_documentation.test_protocol_detail, name='test_protocol_detail'),
    path('documentation/architecture/', views_documentation.architecture_documentation, name='architecture_documentation'),
    path('documentation/workflow/planning/', views_documentation.planning_workflow_documentation, name='planning_workflow_documentation'),
    path('documentation/workflow/facturation/', views_documentation.facturation_workflow_documentation, name='facturation_workflow_documentation'),
    path('documentation/workflow/reparations/', views_documentation.reparations_workflow_documentation, name='reparations_workflow_documentation'),
    path('documentation/workflow/fiches-paie/', views_documentation.fiches_paie_workflow_documentation, name='fiches_paie_workflow_documentation'),
    path('documentation/workflow/inventory/', views_documentation.inventory_workflow_documentation, name='inventory_workflow_documentation'),
    path('documentation/workflow/paiements-irsa/', views_documentation.paiements_irsa_workflow_documentation, name='paiements_irsa_workflow_documentation'),
    path('documentation/workflow/caissiere/', views_documentation.caissiere_workflow_documentation, name='caissiere_workflow_documentation'),
    path('documentation/workflow/cartes-sociales/', views_documentation.cartes_sociales_workflow_documentation, name='cartes_sociales_workflow_documentation'),
    path('documentation/workflow/terrain/', views_documentation.workflow_terrain_documentation, name='workflow_terrain_documentation'),
    path('documentation/workflow/analyses-eau/', views_documentation.analyses_eau_workflow_documentation, name='analyses_eau_workflow_documentation'),
    path('documentation/workflow/recherche-ouvrages/', views_documentation.recherche_ouvrages_workflow_documentation, name='recherche_ouvrages_workflow_documentation'),

    # Dashboards spécialisés
    path('dashboard/paiements-forfaitaires/', views.dashboard_payments_flat, name='dashboard_payments_flat'),
    path('dashboard/paiements-forfaitaires/kanban/', views.dashboard_payments_flat_kanban, name='dashboard_payments_flat_kanban'),
    path('dashboard/paiements-forfaitaires/impression/', views_impression.impression_paiements_forfaitaires, name='impression_paiements_forfaitaires'),
    path('dashboard/paiements-volume/', views.dashboard_payments_volume, name='dashboard_payments_volume'),
    path('dashboard/expenses', views_depenses_services.depenses_services_workflow),
    path('dashboard/expenses/', views_depenses_services.depenses_services_workflow, name='dashboard_expenses_services'),
    path('dashboard/depenses/', views.dashboard_expenses, name='dashboard_expenses'),
    path('dashboard/infrastructures/', views.dashboard_infrastructure, name='dashboard_infrastructure'),
    path('dashboard/carte/', views.dashboard_map, name='dashboard_map'),

    # Autres pages
    path('rapports/', views.rapports, name='rapports'),
    path('rapports/partenaires-trimestriel/', views_rapports.rapport_partenaires_trimestriel, name='rapport_partenaires_trimestriel'),
    path(
        'rapports/analyse-villages-desserte/',
        views_villages_desserte.analyse_villages_desserte,
        name='analyse_villages_desserte',
    ),
    path(
        'rapports/analyse-villages-desserte/export-excel/',
        views_villages_desserte.analyse_villages_desserte_export_excel,
        name='analyse_villages_desserte_export_excel',
    ),
    path(
        'rapports/analyse-villages-desserte/geo-options/',
        views_villages_desserte.analyse_villages_desserte_geo_options,
        name='analyse_villages_desserte_geo_options',
    ),
    path(
        'rapports/analyse-villages-desserte/json/',
        views_villages_desserte.analyse_villages_desserte_json,
        name='analyse_villages_desserte_json',
    ),
    path(
        'rapports/analyse-villages-desserte/flux-json/',
        views_villages_desserte.analyse_villages_desserte_flux_json,
        name='analyse_villages_desserte_flux_json',
    ),

    path('contributions/classement/', views_contributions.classement_contributions, name='classement_contributions'),

    # Filtres sauvegardés (génériques, réutilisables par page via page_key)
    path(
        'api/filtres-sauvegardes/',
        views_filtres_sauvegardes.api_filtres_sauvegardes_list,
        name='api_filtres_sauvegardes_list',
    ),
    path(
        'api/filtres-sauvegardes/create/',
        views_filtres_sauvegardes.api_filtres_sauvegardes_create,
        name='api_filtres_sauvegardes_create',
    ),
    path(
        'api/filtres-sauvegardes/<uuid:filtre_id>/delete/',
        views_filtres_sauvegardes.api_filtres_sauvegardes_delete,
        name='api_filtres_sauvegardes_delete',
    ),
    path(
        'rapports/partenaires-trimestriel/archives/generer/',
        views_rapports.generate_partner_report_archives_now,
        name='generate_partner_report_archives_now',
    ),
    path(
        'rapports/partenaires-trimestriel/archives/<uuid:archive_id>/document/',
        views_rapports.download_partner_report_archive,
        name='download_partner_report_archive',
    ),
    path(
        'rapports/partenaires-trimestriel/archives/<uuid:archive_id>/html/',
        views_rapports.view_partner_report_archive_html,
        name='view_partner_report_archive_html',
    ),
    path(
        'rapports/partenaires-trimestriel/archives/<uuid:archive_id>/html/editer/',
        views_rapports.edit_partner_report_archive_html,
        name='edit_partner_report_archive_html',
    ),
    path(
        'rapports/partenaires-trimestriel/archives/<uuid:archive_id>/upload/',
        views_rapports.upload_partner_report_archive,
        name='upload_partner_report_archive',
    ),
    path(
        'rapports/partenaires-trimestriel/archives/<uuid:archive_id>/delete/',
        views_rapports.delete_partner_report_archive,
        name='delete_partner_report_archive',
    ),
    path('rapports/activites-par-employe/', views_rapports.activites_par_employe, name='activites_par_employe'),
    path('rapports/performance-bases/', views_rapports.performance_bases, name='performance_bases'),
    path('rapports/indicateurs-diamex/', views_rapports.indicateurs_diamex, name='indicateurs_diamex'),
    path('cartes-sociales/', views.cartes_sociales, name='cartes_sociales'),
    path('recherche/', views.search_global, name='search'),
    path('recherche/api/mobile/search/', views_mobile_search.mobile_global_search, name='mobile_global_search'),
    path('recherche/api/mobile/personnes/', views_mobile_search.mobile_people, name='mobile_people'),
    path('recherche/api/mobile/personnes/<str:type_key>/<uuid:entity_id>/', views_mobile_search.mobile_person_detail, name='mobile_person_detail'),
    path('recherche/api/mobile/personnes/<str:type_key>/<uuid:entity_id>/modifier/', views_mobile_search.mobile_person_update, name='mobile_person_update'),
    path('recherche/api/mobile/ouvrages/', views_mobile_search.mobile_works, name='mobile_works'),
    path('recherche/api/mobile/ouvrages/filtres/', views_mobile_search.mobile_work_filters, name='mobile_work_filters'),
    path('recherche/api/mobile/interventions/', views_mobile_search.mobile_interventions, name='mobile_interventions'),
    path('recherche/api/mobile/interventions/<uuid:planning_id>/reporter/', views_mobile_search.mobile_intervention_postpone, name='mobile_intervention_postpone'),
    path('recherche/api/mobile/interventions/<uuid:planning_id>/supprimer/', views_mobile_search.mobile_intervention_delete, name='mobile_intervention_delete'),
    path('recherche/api/mobile/details/<str:entity_type>/<str:entity_id>/', views_mobile_search.mobile_detail, name='mobile_detail'),
    path('recherche/personnes/', views_personnes.personnes_annuaire, name='personnes_annuaire'),
    path('recherche/personnes/api/', views_personnes.personnes_annuaire_json, name='personnes_annuaire_json'),
    path('recherche/personnes/<str:type_key>/<uuid:entity_id>/modifier/', views_personnes.personne_update_champs, name='personne_update_champs'),
    path('recherche/personnes/<str:type_key>/<uuid:entity_id>/details/', views_personnes.personne_details_json, name='personne_details_json'),
    path('recherche/ouvrages/', views_ouvrage_interventions.recherche_ouvrages_rapide, name='recherche_ouvrages_rapide'),
    path('recherche/ouvrages/activites-equipements/', views_ouvrage_interventions.repair_activity_equipment_permissions, name='repair_activity_equipment_permissions'),
    path('recherche/ouvrages/interventions/recentes/', views_ouvrage_interventions.interventions_recentes, name='interventions_recentes'),
    path('recherche/ouvrages/<uuid:ouvrage_id>/details-echus/', views_ouvrage_interventions.details_montant_echu_ouvrage, name='details_montant_echu_ouvrage'),
    path('recherche/ouvrages/<uuid:ouvrage_id>/indemnites-rbf/', views_ouvrage_interventions.details_indemnites_rbf_ouvrage, name='details_indemnites_rbf_ouvrage'),
    path('recherche/ouvrages/<uuid:ouvrage_id>/indemnites-rbf/explication/', views_ouvrage_interventions.enregistrer_explication_indemnite_ouvrage, name='enregistrer_explication_indemnite_ouvrage'),
    path('recherche/details/<str:entity_type>/<str:entity_id>/', views.search_detail, name='search_detail'),
    path('recherche/ouvrages/<uuid:ouvrage_id>/interventions/ajouter/', views_ouvrage_interventions.ajouter_intervention_ouvrage, name='ajouter_intervention_ouvrage'),
    path('recherche/ouvrages/<uuid:ouvrage_id>/interventions/options/', views_ouvrage_interventions.options_intervention_ouvrage, name='options_intervention_ouvrage'),
    path('recherche/ouvrages/<uuid:ouvrage_id>/interventions/historique/', views_ouvrage_interventions.historique_interventions_ouvrage, name='historique_interventions_ouvrage'),
    path('recherche/ouvrages/<uuid:ouvrage_id>/interventions/<uuid:planning_id>/modifier/', views_ouvrage_interventions.modifier_intervention_ouvrage, name='modifier_intervention_ouvrage'),
    path('recherche/ouvrages/<uuid:ouvrage_id>/interventions/<uuid:planning_id>/supprimer/', views_ouvrage_interventions.supprimer_intervention_ouvrage, name='supprimer_intervention_ouvrage'),
    path('recherche/ouvrages/<uuid:ouvrage_id>/interventions/<uuid:planning_id>/photos/<int:photo_index>/', views_ouvrage_interventions.photo_intervention_ouvrage, name='photo_intervention_ouvrage'),
    path('recherche/point-eau/<str:point_id>/signaler-reparation/', views.signaler_reparation_point_eau, name='signaler_reparation_point_eau'),

    # API Chatbot
    path('api/chatbot/', views.chatbot_query, name='chatbot_query'),

    # API Recherche
    path('api/search/', views_search_evolved.search_api_evolved, name='search_api'),

    # API Assistant IA (prototypes) retirées : api/stats/, api/plannings/week/, api/invoices/unpaid/
    # Champs inexistants (erreur 500) et factures simulées ; aucun appelant actif.

    # API Modalités de paiement
    path('api/ouvrages/by-modalite/', views.api_ouvrages_by_modalite, name='api_ouvrages_by_modalite'),
    path('api/points-eau/by-modalite/', views.api_points_eau_by_modalite, name='api_points_eau_by_modalite'),

    # Qualité des données
    path('qualite-donnees/', views_qualite_donnees.rapport_qualite_donnees, name='rapport_qualite_donnees'),
    path('qualite-donnees/api/update-village-gps/', views_qualite_donnees.api_update_village_gps, name='api_update_village_gps'),
    path('qualite-donnees/api/update-parcelle/', views_qualite_donnees.api_update_parcelle, name='api_update_parcelle'),
    path('qualite-donnees/api/update-point-eau/', views_qualite_donnees.api_update_point_eau, name='api_update_point_eau'),
    path('qualite-donnees/api/update-equipement/', views_qualite_donnees.api_update_equipement, name='api_update_equipement'),
    path('qualite-donnees/api/update-carte-sociale/', views_qualite_donnees.api_update_carte_sociale, name='api_update_carte_sociale'),
    path('documents/images-extraites/', views_document_extraction.extracted_document_images_list, name='extracted_document_images_list'),

    # Widget météo (PWA installable, mobile + desktop)
    path('widget/', views_widget.widget_meteo, name='widget_meteo'),
    path('widget/manifest.json', views_widget.widget_manifest, name='widget_manifest'),
    path('widget/sw.js', views_widget.widget_service_worker, name='widget_service_worker'),
    path('widget/api/login/', views_widget.api_widget_login, name='api_widget_login'),
    path('widget/api/ping/', views_widget.api_widget_ping, name='api_widget_ping'),
    path('widget/api/stats/', views_widget.api_widget_stats, name='api_widget_stats'),
    path('widget/api/realisations/', views_widget.api_widget_realisations, name='api_widget_realisations'),
    path('widget/diagramme/', views_widget.widget_diagramme_page, name='widget_diagramme'),
    path('widget/api/diagramme/', views_widget.api_widget_diagramme, name='api_widget_diagramme'),
    path('widget/api/compteurs-tete/', views_widget.api_widget_compteurs_tete, name='api_widget_compteurs_tete'),
    path('widget/api/debits-source/', views_widget.api_widget_debits_source, name='api_widget_debits_source'),
    path('widget/api/analyse-consommation/', views_widget.api_widget_analyse_consommation, name='api_widget_analyse_consommation'),
    path('widget/api/filtres/', views_widget.api_widget_filtres, name='api_widget_filtres'),
    path('widget/api/details/<str:stat_type>/', views_widget.api_widget_details, name='api_widget_details'),
    path('widget/rbf/', views_widget.widget_rbf_dashboard, name='widget_rbf_dashboard'),
    path('widget/rbf/avances/', views_widget.widget_rbf_avances_lot, name='widget_rbf_avances_lot'),
    path('widget/liste/<str:stat_type>/', views_widget.widget_liste_page, name='widget_liste'),
    path('widget/explication/<str:stat_type>/<uuid:point_id>/', views_widget.widget_explication_rbf_page, name='widget_explication_rbf'),
    path('widget/api/rbf/avance/<uuid:point_id>/controle/', views_widget.api_widget_rbf_avance_controle, name='api_widget_rbf_avance_controle'),
    path('widget/api/rbf/avance/<uuid:point_id>/demander/', views_widget.api_widget_rbf_avance_demander, name='api_widget_rbf_avance_demander'),
    path('widget/api/rbf/entree/<int:entry_id>/libelle/', views_widget.api_widget_rbf_modifier_libelle, name='api_widget_rbf_modifier_libelle'),
    path('widget/api/ouvrages/<uuid:ouvrage_id>/', views_widget.api_widget_ouvrage_detail, name='api_widget_ouvrage_detail'),
    path('widget/api/groupes/<str:stat_type>/', views_widget.api_widget_groupes, name='api_widget_groupes'),
    path('widget/api/interventions/', views_widget.api_widget_interventions, name='api_widget_interventions'),
    path('widget/api/interventions/vue/', views_widget.api_widget_intervention_mark_seen, name='api_widget_intervention_mark_seen'),
    path('widget/api/interventions/<uuid:planning_id>/photos/<int:photo_index>/', views_widget.api_widget_intervention_photo, name='api_widget_intervention_photo'),
    path('widget/api/planning/filtres/', views_widget.api_widget_planning_filtres, name='api_widget_planning_filtres'),
    path('widget/api/planning/activites/', views_widget.api_widget_planning_activites, name='api_widget_planning_activites'),
    path('widget/api/planning/activites/<uuid:planning_id>/', views_widget.api_widget_planning_activite_update, name='api_widget_planning_activite_update'),

    # Authentification app terrain Android (scope 'mobile', cloisonné du
    # widget desktop malgré le même mécanisme sous-jacent — voir
    # apps.core.auth_tokens.token_or_session_required)
    path('mobile/api/login/', views_mobile_auth.api_mobile_login, name='api_mobile_login'),
    path('mobile/api/salary-calculation-config/', views_mobile_salary.mobile_salary_calculation_config, name='mobile_salary_calculation_config'),
]
