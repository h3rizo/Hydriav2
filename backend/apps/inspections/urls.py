from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    PointDeControleViewSet,
    ChecklistViewSet,
    VisiteViewSet,
    ResultatControleViewSet,
    OuvrageListView,
    EquipementListView,
    EmployeeListView,
    visite_detail_view,
    dashboard_view,
    dashboard_inspections,
    nouvelle_inspection_view,
    inspection_amelioree_view,
    equipment_selection_view,
    nouvelle_planification_view,
    equipment_inspection_data_api,
    existing_inspection_results_api,
    inspection_form_api,
    ouvrage_historique_api,
    checklists_management_view,
    points_controle_table_view,
    checklists_api,
    points_controle_api,
    activites_list_api,
    activites_correctives_manage_api,
    save_resultat_api,
    points_eau_api,
    # APIs pour les photos de référence
    get_equipements_ouvrage,
    get_composants_equipement,
    get_photos_references_composant,
    upload_photo_reference,
    delete_photo_reference,
    # APIs pour vérifier et mettre à jour les données GPS/photos
    check_item_data,
    update_item_data,
    check_planning_items_data,
    # Consultation des résultats
    resultats_equipements,
    resultats_points_eau,
    # API pour l'agenda des actions correctives
    employe_future_plannings_api,
    # API pour récupérer les points de contrôle selon type de visite
    api_points_controle_pour_inspection,
    # API pour gérer les points de contrôle spécifiques par équipement
    api_points_controle_specifiques,
    # API pour gérer les points de contrôle communs
    api_composants_type_equipement,
    api_create_point_controle_composant,
    api_delete_point_controle_composant,
    api_update_type_visite_point_controle_composant,
    # APIs pour gérer les composants type point d'eau
    api_composants_type_point_eau,
    api_creer_composant_type_point_eau,
    api_modifier_composant_type_point_eau,
    api_lier_point_controle_composant_pe,
    # APIs pour les points de contrôle spécifiques point d'eau
    api_points_controle_specifiques_point_eau,
    api_modifier_point_controle_specifique_point_eau,
)

from .views_express import (
    api_control_points_for_item,
    api_create_inspection_express,
    api_save_inspection_result,
    api_finish_inspection_express,
)

# Import des vues pour les non-conformités
from .views_non_conformites import (
    api_creer_non_conformite,
    api_get_non_conformite,
    api_update_non_conformite,
)

# Router pour les ViewSets
router = DefaultRouter()
router.register(r'points-controle', PointDeControleViewSet, basename='pointdecontrole')
router.register(r'checklists', ChecklistViewSet, basename='checklist')
router.register(r'visites', VisiteViewSet, basename='visite')
router.register(r'resultats', ResultatControleViewSet, basename='resultatcontrole')
router.register(r'ouvrages', OuvrageListView, basename='ouvrage')
router.register(r'equipements', EquipementListView, basename='equipement')
router.register(r'employes', EmployeeListView, basename='employe')

app_name = 'inspections'

urlpatterns = [
    # Interface utilisateur HTML
    path('', dashboard_view, name='dashboard'),
    path('visite/<uuid:visite_id>/', visite_detail_view, name='visite-detail'),
    path('nouvelle-inspection/', nouvelle_inspection_view, name='nouvelle_inspection'),
    path('inspection-amelioree/', inspection_amelioree_view, name='inspection_amelioree'),

    # Nouveau workflow d'inspection
    path('equipment-selection/', equipment_selection_view, name='equipment_selection'),
    path('nouvelle-planification/', nouvelle_planification_view, name='nouvelle_planification'),

    # API pour les données d'inspection
    path('api/equipment-inspection-data/<str:item_id>/<str:item_type>/', equipment_inspection_data_api, name='equipment_inspection_data'),
    path('api/existing-results/<str:item_id>/<str:item_type>/', existing_inspection_results_api, name='existing_inspection_results'),

    # Gestion des checklists et activités correctives
    path('gestion-checklists/', checklists_management_view, name='checklists_management'),
    path('points-controle/table/', points_controle_table_view, name='points_controle_table'),

    # Dashboard des inspections (API)
    path('api/dashboard/', dashboard_inspections, name='dashboard_api'),

    # API pour le formulaire d'inspection
    path('api/inspection-form/<int:planning_id>/', inspection_form_api, name='inspection_form_api'),

    # API pour l'historique des contrôles d'un ouvrage
    path('api/historique/<uuid:ouvrage_id>/', ouvrage_historique_api, name='ouvrage_historique_api'),

    # API pour la gestion des checklists
    path('api/checklists/', checklists_api, name='checklists_api'),
    path('api/points-controle-list/', points_controle_api, name='points_controle_api'),
    path('api/activites-list/', activites_list_api, name='activites_list_api'),
    path('api/activites-correctives-manage/', activites_correctives_manage_api, name='activites_correctives_manage_api'),

    # API pour sauvegarder les résultats d'inspection
    path('api/save-resultat/', save_resultat_api, name='save_resultat_api'),

    # API pour charger les points d'eau d'un planning
    path('api/points-eau/<int:planning_id>/', points_eau_api, name='points_eau_api'),

    # API pour les photos de référence
    path('api/equipements-ouvrage/<str:ouvrage_id>/', get_equipements_ouvrage, name='get_equipements_ouvrage'),
    path('api/composants-equipement/<str:equipement_id>/', get_composants_equipement, name='get_composants_equipement'),
    path('api/photos-references-composant/<str:composant_id>/', get_photos_references_composant, name='get_photos_references_composant'),
    path('api/upload-photo-reference/', upload_photo_reference, name='upload_photo_reference'),
    path('api/delete-photo-reference/<str:point_controle_composant_id>/', delete_photo_reference, name='delete_photo_reference'),

    # API pour vérifier et mettre à jour les données GPS/photos des équipements et points d'eau
    path('api/check-item-data/<str:item_id>/<str:item_type>/', check_item_data, name='check_item_data'),
    path('api/update-item-data/', update_item_data, name='update_item_data'),
    path('api/check-planning-items/<str:planning_id>/', check_planning_items_data, name='check_planning_items_data'),

    # Consultation des résultats
    path('resultats/equipements/', resultats_equipements, name='resultats_equipements'),
    path('resultats/points-eau/', resultats_points_eau, name='resultats_points_eau'),

    # API pour l'agenda des actions correctives
    path('api/employe-plannings/<str:employe_id>/', employe_future_plannings_api, name='employe_future_plannings'),

    # API pour récupérer les points de contrôle selon type de visite et équipement
    path('api/points-controle-inspection/', api_points_controle_pour_inspection, name='api_points_controle_inspection'),

    # API pour gérer les points de contrôle spécifiques par équipement
    path('api/points-controle-specifiques/', api_points_controle_specifiques, name='api_points_controle_specifiques'),

    # API pour gérer les points de contrôle communs (équipements)
    path('api/composants-type-equipement/<uuid:type_equipement_id>/', api_composants_type_equipement, name='api_composants_type_equipement'),
    path('api/point-controle-composant/create/', api_create_point_controle_composant, name='api_create_point_controle_composant'),
    path('api/point-controle-composant/<uuid:lien_id>/delete/', api_delete_point_controle_composant, name='api_delete_point_controle_composant'),
    path('api/point-controle-composant/<uuid:lien_id>/update-type-visite/', api_update_type_visite_point_controle_composant, name='api_update_type_visite_point_controle_composant'),

    # API pour gérer les composants type point d'eau
    path('api/composants-type-point-eau/<uuid:type_point_eau_id>/', api_composants_type_point_eau, name='api_composants_type_point_eau'),
    path('api/composant-type-point-eau/create/', api_creer_composant_type_point_eau, name='api_creer_composant_type_point_eau'),
    path('api/composant-type-point-eau/<uuid:composant_id>/', api_modifier_composant_type_point_eau, name='api_modifier_composant_type_point_eau'),
    path('api/lier-point-controle-composant-pe/', api_lier_point_controle_composant_pe, name='api_lier_point_controle_composant_pe'),

    # API pour les points de contrôle spécifiques par point d'eau
    path('api/points-controle-specifiques-pe/<uuid:point_eau_id>/', api_points_controle_specifiques_point_eau, name='api_points_controle_specifiques_point_eau'),
    path('api/point-controle-specifique-pe/<uuid:specifique_id>/', api_modifier_point_controle_specifique_point_eau, name='api_modifier_point_controle_specifique_point_eau'),

    # API pour l'inspection express
    path('api/control-points/<str:item_type>/<uuid:item_id>/', api_control_points_for_item, name='api_control_points_for_item'),
    path('api/create-inspection-express/', api_create_inspection_express, name='api_create_inspection_express'),
    path('api/save-inspection-result/', api_save_inspection_result, name='api_save_inspection_result'),
    path('api/finish-inspection-express/', api_finish_inspection_express, name='api_finish_inspection_express'),

    # API pour gérer les non-conformités
    path('api/non-conformite/creer/', api_creer_non_conformite, name='api_creer_non_conformite'),
    path('api/non-conformite/<uuid:resultat_id>/', api_get_non_conformite, name='api_get_non_conformite'),
    path('api/non-conformite/<uuid:non_conformite_id>/update/', api_update_non_conformite, name='api_update_non_conformite'),

    # API REST pour les ViewSets
    path('api/', include(router.urls)),
]

# Analyses d'eau - Import de views_analyse_eau et views_analyse_eau_excel
from .views_analyse_eau import (
    analyses_eau_list,
    analyses_eau_dashboard,
    api_analyses_eau_list,
    api_analyses_eau_dashboard,
    api_analyses_eau_stats_globales,
    api_analyse_eau_create,
    api_analyse_eau_update,
    api_analyse_eau_delete,
    api_analyse_eau_detail,
    api_analyses_eau_delete_all,
    api_ouvrages_par_commune,
    api_equipements_par_ouvrage,
    api_points_eau_par_ouvrage,
)
from .views_analyse_eau_excel import (
    export_analyses_eau_excel,
    template_import_analyses_eau,
    import_analyses_eau_excel,
)
from .views_analyse_eau_packs import (
    api_packs_analyses_stats,
    api_pack_details,
)

analyses_eau_patterns = [
    # Pages principales
    path('analyses-eau/', analyses_eau_list, name='analyses_eau_list'),
    path('analyses-eau/dashboard/', analyses_eau_dashboard, name='analyses_eau_dashboard'),

    # APIs CRUD
    path('analyses-eau/api/list/', api_analyses_eau_list, name='api_analyses_eau_list'),
    path('analyses-eau/api/dashboard/', api_analyses_eau_dashboard, name='api_analyses_eau_dashboard'),
    path('analyses-eau/api/stats-globales/', api_analyses_eau_stats_globales, name='api_analyses_eau_stats_globales'),
    path('analyses-eau/api/create/', api_analyse_eau_create, name='api_analyse_eau_create'),
    path('analyses-eau/api/<uuid:analyse_id>/', api_analyse_eau_detail, name='api_analyse_eau_detail'),
    path('analyses-eau/api/<uuid:analyse_id>/update/', api_analyse_eau_update, name='api_analyse_eau_update'),
    path('analyses-eau/api/<uuid:analyse_id>/delete/', api_analyse_eau_delete, name='api_analyse_eau_delete'),
    path('analyses-eau/api/delete-all/', api_analyses_eau_delete_all, name='api_analyses_eau_delete_all'),

    # Import/Export Excel
    path('analyses-eau/export/', export_analyses_eau_excel, name='export_analyses_eau_excel'),
    path('analyses-eau/template-import/', template_import_analyses_eau, name='template_import_analyses_eau'),
    path('analyses-eau/import/', import_analyses_eau_excel, name='import_analyses_eau_excel'),

    # APIs Packs d'analyses
    path('analyses-eau/api/packs/stats/', api_packs_analyses_stats, name='api_packs_analyses_stats'),
    path('analyses-eau/api/packs/<str:date_analyse>/', api_pack_details, name='api_pack_details'),

    # APIs pour formulaire (cascade ouvrages/équipements/points d'eau)
    path('analyses-eau/api/ouvrages/', api_ouvrages_par_commune, name='api_ouvrages_par_commune'),
    path('analyses-eau/api/equipements/', api_equipements_par_ouvrage, name='api_equipements_par_ouvrage'),
    path('analyses-eau/api/points-eau/', api_points_eau_par_ouvrage, name='api_points_eau_par_ouvrage'),
]

urlpatterns += analyses_eau_patterns
