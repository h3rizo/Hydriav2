from django.urls import path
from . import views
from . import views_capture
from . import views_contours
from . import views_liaisons_api
from . import views_coupures
from . import views_trace_libre
from . import views_bases

app_name = 'geography'

urlpatterns = [
    # Page principale
    path('', views.geography_list, name='list'),

    # Workflow de capture de données terrain
    path('capture-donnees/', views_capture.capture_donnees_home, name='capture_donnees_home'),
    path('api/villages-proximite/', views_capture.api_villages_proximite, name='api_villages_proximite'),
    path('api/champs-vides/', views_capture.api_champs_vides, name='api_champs_vides'),
    path('api/update-champ/', views_capture.api_update_champ, name='api_update_champ'),

    # Tableau de bord géographique
    path('dashboard/', views.dashboard_geography, name='dashboard'),
    path('consolidated/', views.geography_consolidated, name='consolidated'),
    path('api/dashboard-chart-data/', views.api_dashboard_chart_data, name='dashboard_chart_data'),
    path('api/all-communes/', views.api_all_communes, name='all_communes'),
    path('api/all-districts/', views.api_all_districts, name='all_districts'),
    path('api/all-villages/', views.api_all_villages, name='all_villages'),

    # Import/Export Excel
    path('import-excel/<str:model_name>/', views.import_excel, name='import_excel'),
    path('import-excel-update-villages-gps/', views.import_excel_update_villages_gps, name='import_excel_update_villages_gps'),
    path('import-excel-update-villages-accessibilite/', views.import_excel_update_villages_accessibilite, name='import_excel_update_villages_accessibilite'),
    path('excel-template/<str:model_name>/', views.excel_template, name='excel_template'),
    path('export-excel/<str:model_name>/', views.export_excel, name='export_excel'),

    # Régions
    path('regions/', views.region_list, name='region_list'),
    path('regions/create/', views.region_create, name='region_create'),
    path('regions/<uuid:pk>/', views.region_detail, name='region_detail'),
    path('regions/<uuid:pk>/update/', views.region_update, name='region_update'),
    path('regions/<uuid:pk>/delete/', views.region_delete, name='region_delete'),

    # Districts
    path('districts/', views.district_list, name='district_list'),
    path('districts/create/', views.district_create, name='district_create'),
    path('districts/<uuid:pk>/', views.district_detail, name='district_detail'),
    path('districts/<uuid:pk>/update/', views.district_update, name='district_update'),
    path('districts/<uuid:pk>/delete/', views.district_delete, name='district_delete'),

    # Communes
    path('communes/', views.commune_list, name='commune_list'),
    path('communes/create/', views.commune_create, name='commune_create'),
    path('communes/<uuid:pk>/', views.commune_detail, name='commune_detail'),
    path('communes/<uuid:pk>/update/', views.commune_update, name='commune_update'),
    path('communes/<uuid:pk>/delete/', views.commune_delete, name='commune_delete'),

    # Villages
    path('villages/', views.village_list, name='village_list'),
    path('villages/create/', views.village_create, name='village_create'),
    path('villages/<uuid:pk>/', views.village_detail, name='village_detail'),
    path('villages/<uuid:pk>/liaisons/create/', views.village_liaison_create, name='village_liaison_create'),
    path('villages/<uuid:pk>/liaisons/autofill/', views.village_liaisons_autofill, name='village_liaisons_autofill'),
    path('villages/liaisons/autofill-global/', views.village_liaisons_autofill_global, name='village_liaisons_autofill_global'),
    path('villages/liaisons/<uuid:liaison_id>/update/', views.village_liaison_update, name='village_liaison_update'),
    path('villages/<uuid:pk>/update/', views.village_update, name='village_update'),
    path('villages/<uuid:pk>/delete/', views.village_delete, name='village_delete'),
    path('villages/liaisons/<uuid:liaison_id>/delete/', views.village_liaison_delete, name='village_liaison_delete'),

    # Parcelles
    path('parcelles/', views.parcelle_list, name='parcelle_list'),
    path('parcelles/create/', views.parcelle_create, name='parcelle_create'),
    path('parcelles/<uuid:pk>/', views.parcelle_detail, name='parcelle_detail'),
    path('parcelles/<uuid:pk>/update/', views.parcelle_update, name='parcelle_update'),
    path('parcelles/<uuid:pk>/delete/', views.parcelle_delete, name='parcelle_delete'),

    # API pour CRUD en cascade
    path('api/exprovinces/', views.api_exprovinces, name='api_exprovinces'),
    path('api/regions/', views.api_regions, name='api_regions'),
    path('api/districts/<uuid:region_id>/', views.api_districts, name='api_districts'),
    path('api/communes/<uuid:district_id>/', views.api_communes, name='api_communes'),
    path('api/fokontanys/<uuid:commune_id>/', views.api_fokontanys, name='api_fokontanys'),
    path('api/villages/detail/<uuid:village_id>/', views.api_village_detail, name='api_village_detail'),
    path('api/communes/<uuid:commune_id>/villages/', views.api_villages_commune, name='api_villages_commune'),
    path('api/autorites/<str:zone_type>/<uuid:zone_id>/', views.api_autorites_zone, name='api_autorites_zone'),
    path('api/villages/<uuid:fokontany_id>/', views.api_villages, name='api_villages'),
    path('api/parcelles/<uuid:village_id>/', views.api_parcelles, name='api_parcelles'),
    path('api/pointeaus/<uuid:parcelle_id>/', views.api_pointeaus, name='api_pointeaus'),
    path('api/create/', views.api_create, name='api_create'),
    path('api/update/', views.api_update, name='api_update'),
    path('api/delete/', views.api_delete, name='api_delete'),

    # APIs CRUD pour parcelles (page consolidée)
    path('api/parcelles/<uuid:parcelle_id>/update/', views.update_parcelle_api, name='update_parcelle_api'),
    path('api/parcelles/<uuid:parcelle_id>/delete/', views.delete_parcelle_api, name='delete_parcelle_api'),

    # API pour mise à jour GPS des villages
    path('api/villages/<uuid:village_id>/update-gps/', views.update_village_gps_api, name='update_village_gps_api'),

    # APIs spécifiques pour les points d'eau
    path('api/types-point-eau/', views.api_types_point_eau, name='api_types_point_eau'),
    path('api/pointeau-detail/<uuid:pointeau_id>/', views.api_pointeau_detail, name='api_pointeau_detail'),
    path('api/pointeau-create/', views.api_pointeau_create, name='api_pointeau_create'),
    path('api/pointeau-update/<uuid:pointeau_id>/', views.api_pointeau_update, name='api_pointeau_update'),

    # Page carte géographique interactive
    path('map/', views.geography_map, name='map'),
    path('map/liaisons/', views.geography_liaisons_map, name='liaisons_map'),

    # APIs GeoJSON pour la carte
    path('api/geojson/regions/', views.api_geojson_regions, name='api_geojson_regions'),
    path('api/geojson/districts/', views.api_geojson_districts, name='api_geojson_districts'),
    path('api/geojson/communes/', views.api_geojson_communes, name='api_geojson_communes'),
    path('api/geojson/fokontany/', views.api_geojson_fokontany, name='api_geojson_fokontany'),
    path('api/geojson/villages/', views.api_geojson_villages, name='api_geojson_villages'),
    # Réseau routier : réparation des coupures (raccords assistés)
    path('routes/coupures/', views_coupures.page_coupures, name='coupures_routes'),
    path('routes/bases/', views_bases.page_lieux_bases, name='lieux_bases'),
    path('api/routes/bases/', views_bases.api_bases_liste, name='api_bases_liste'),
    path('api/routes/bases/<uuid:pk>/lieu/', views_bases.api_base_lieu, name='api_base_lieu'),
    path('routes/trace-libre/', views_trace_libre.page_trace_libre, name='trace_libre'),
    path('api/routes/trace-libre/', views_trace_libre.api_trace_libre_liste, name='api_trace_libre_liste'),
    path('api/routes/trace-libre/contexte/', views_trace_libre.api_trace_libre_contexte, name='api_trace_libre_contexte'),
    path('api/routes/trace-libre/creer/', views_trace_libre.api_trace_libre_creer, name='api_trace_libre_creer'),
    path('api/routes/trace-libre/ligne/', views_trace_libre.api_trace_libre_ligne, name='api_trace_libre_ligne'),
    path('api/routes/villages/lieu/', views_trace_libre.api_village_lieu, name='api_village_lieu'),
    path('api/routes/villages/liste/', views_trace_libre.api_village_liste, name='api_village_liste'),
    path('api/routes/villages/creer/', views_trace_libre.api_village_creer, name='api_village_creer'),
    path('api/routes/villages/zone/', views_trace_libre.api_villages_zone, name='api_villages_zone'),
    path('api/routes/villages/recherche/', views_trace_libre.api_village_recherche, name='api_village_recherche'),
    path('api/routes/villages/<uuid:village_id>/', views_trace_libre.api_village_detail, name='api_village_detail'),
    path('api/routes/villages/<uuid:village_id>/modifier/', views_trace_libre.api_village_modifier, name='api_village_modifier'),
    path('api/routes/troncons/<uuid:troncon_id>/', views_trace_libre.api_troncon_detail, name='api_troncon_detail'),
    path('api/routes/troncons/<uuid:troncon_id>/modifier/', views_trace_libre.api_troncon_modifier, name='api_troncon_modifier'),
    path('routes/jonctions/', views_coupures.page_jonctions, name='jonctions_routes'),
    path('api/routes/jonctions/', views_coupures.api_jonctions_liste, name='api_jonctions_liste'),
    path('api/routes/jonctions/contexte/', views_coupures.api_jonctions_contexte, name='api_jonctions_contexte'),
    path('api/routes/jonctions/relier/', views_coupures.api_jonction_relier, name='api_jonction_relier'),
    path('api/routes/itineraire/', views_coupures.api_itineraire, name='api_itineraire'),
    path('api/routes/coupures/', views_coupures.api_coupures_liste, name='api_coupures_liste'),
    path('api/routes/coupures/raccorder/', views_coupures.api_coupure_raccorder, name='api_coupure_raccorder'),
    path('api/routes/coupures/<str:cid>/', views_coupures.api_coupure_detail, name='api_coupure_detail'),

    path('api/geojson/liaisons-villages/', views.api_geojson_liaisons_villages, name='api_geojson_liaisons_villages'),
    path('api/geojson/contours/', views_contours.api_geojson_contours, name='api_geojson_contours'),
    path('api/geojson/routes-reseau/', views.api_geojson_routes_reseau, name='api_geojson_routes_reseau'),
    path('api/geojson/bases/', views.api_geojson_bases, name='api_geojson_bases'),
    path('api/geojson/villages-non-relies/', views.api_geojson_villages_non_relies, name='api_geojson_villages_non_relies'),
    path('api/liaisons/create/', views_liaisons_api.api_liaison_create, name='api_liaison_create'),
    path('api/liaisons/<uuid:liaison_id>/update/', views_liaisons_api.api_liaison_update, name='api_liaison_update'),
    path('api/liaisons/<uuid:liaison_id>/delete/', views_liaisons_api.api_liaison_delete, name='api_liaison_delete'),
    path('api/search-zones/', views.api_search_zones, name='api_search_zones'),
    path('api/zone-bounds/<str:zone_type>/<uuid:zone_id>/', views.api_zone_bounds, name='api_zone_bounds'),
]
