from django.urls import path
from . import views, views_couts_types
from apps.planning import views_couts_types as planning_couts_types
from .views_adresses import api_adresses, api_cartes_sociales

app_name = 'ouvrages'

urlpatterns = [
    # Page d'accueil des ouvrages
    path('', views.ouvrages_home, name='home'),

    # Tableau de bord avec vue d'ensemble et données en cascade
    path('dashboard/', views.ouvrages_dashboard, name='dashboard'),

    # Page CRUD en cascade
    path('cascade/', views.ouvrages_cascade, name='cascade'),

    # Gestion complète avec formulaires en cascade
    path('gestion-complete/', views.ouvrages_gestion_complete, name='gestion_complete'),

    # Coûts types par activité (barème de désignations par activité / cible / composant)
    path('couts-types/', views_couts_types.couts_types_page, name='couts_types'),
    path('couts-types/api/liste/', planning_couts_types.api_couts_types_liste, name='api_couts_types_liste'),
    path('couts-types/api/historique/', planning_couts_types.api_cout_type_historique, name='api_cout_type_historique'),
    path('couts-types/api/sauvegarder/', planning_couts_types.api_cout_type_sauvegarder, name='api_cout_type_sauvegarder'),
    path('couts-types/api/<uuid:cout_type_id>/supprimer/', planning_couts_types.api_cout_type_supprimer, name='api_cout_type_supprimer'),

    # Types d'ouvrages
    path('types/', views.type_ouvrage_list, name='type_ouvrage_list'),
    path('types/create/', views.type_ouvrage_create, name='type_ouvrage_create'),
    path('types/<uuid:pk>/', views.type_ouvrage_detail, name='type_ouvrage_detail'),
    path('types/<uuid:pk>/update/', views.type_ouvrage_update, name='type_ouvrage_update'),
    path('types/<uuid:pk>/delete/', views.type_ouvrage_delete, name='type_ouvrage_delete'),

    # Ouvrages
    path('liste/', views.ouvrage_list, name='ouvrage_list'),
    path('points-eau/<uuid:pk>/problematique/', views.point_eau_problematique_update, name='point_eau_problematique_update'),
    path('equipements/<uuid:pk>/maintenance/', views.equipement_maintenance_update, name='equipement_maintenance_update'),
    path('create/', views.ouvrage_create, name='ouvrage_create'),
    path('<uuid:pk>/', views.ouvrage_detail, name='ouvrage_detail'),
    path('<uuid:pk>/update/', views.ouvrage_update, name='ouvrage_update'),
    path('<uuid:pk>/delete/', views.ouvrage_delete, name='ouvrage_delete'),

    # API pour les données en cascade
    path('api/type-stats/', views.api_type_stats, name='api_type_stats'),
    path('api/adresses/', api_adresses, name='api_adresses'),
    path('api/cartes-sociales/', api_cartes_sociales, name='api_cartes_sociales'),
    path('api/ouvrages/', views.api_ouvrages, name='api_ouvrages'),
    path('api/pointseaus/', views.api_points_eau, name='api_points_eau'),
    path('api/points-eau/', views.api_points_eau, name='api_points_eau_alt'),
    path('api/equipements/', views.api_equipements, name='api_equipements'),
    path('api/compteurs/', views.api_compteurs_tete, name='api_compteurs_tete'),
    path('api/compteurs-tete/', views.api_compteurs_tete, name='api_compteurs_tete_alt'),
    path('api/fournisseurs/', views.api_fournisseurs, name='api_fournisseurs'),
    path('api/tarifs/', views.api_tarifs_volumetriques, name='api_tarifs_volumetriques'),
    path('api/tarifs-volumetriques/', views.api_tarifs_volumetriques, name='api_tarifs_volumetriques_alt'),
    path('api/modalites/', views.api_modalites_gestion, name='api_modalites_gestion'),
    path('api/modalites-gestion/', views.api_modalites_gestion, name='api_modalites_gestion_alt'),

    # API pour les opérations CRUD
    path('api/create/', views.api_create, name='api_create'),
    path('api/update/', views.api_update, name='api_update'),
    path('api/delete/', views.api_delete, name='api_delete'),

    # API pour les formulaires en cascade géographiques
    path('api/regions/', views.api_regions, name='api_regions'),
    path('api/districts/', views.api_districts, name='api_districts'),
    path('api/communes/', views.api_communes, name='api_communes'),
    path('api/fokontanys/', views.api_fokontanys, name='api_fokontanys'),
    path('api/villages/', views.api_villages, name='api_villages'),
    path('api/parcelles/', views.api_parcelles, name='api_parcelles'),

    # Import/Export Excel pour tarifs volumétriques
    path('tarifs/import-export/', views.tarifs_import_export_page, name='tarifs_import_export'),
    path('tarifs/export/', views.export_tarifs_excel, name='export_tarifs_excel'),
    path('tarifs/import/', views.import_tarifs_excel, name='import_tarifs_excel'),
    path('tarifs/tranches/import/', views.import_tranches_only, name='import_tranches_only'),
    path('tarifs/tranches/template/', views.export_template_tranches, name='export_template_tranches'),
]
