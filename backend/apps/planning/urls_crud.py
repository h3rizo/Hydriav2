from django.urls import path
from . import views_crud, views_crud_designation, views_import

urlpatterns = [
    # ===== PAGES TABLEAUX (Style organisation/géographie) =====
    path('crud/types-activites/table/', views_crud.type_activite_table, name='type_activite_table'),
    path('crud/types-designations/table/', views_crud_designation.type_designation_table, name='type_designation_table'),
    path('crud/designations/consolide/', views_crud_designation.designation_consolidated, name='designation_consolidated'),
    path('crud/fiches-poste/table/', views_crud.fiche_poste_table, name='fiche_poste_table'),
    path('crud/fiches-poste/table/par-fiche/', views_crud.fiche_poste_table_classique, name='fiche_poste_table_classique'),

    # ===== CRUD TypeActivite =====
    path('crud/types-activites/', views_crud.type_activite_list, name='type_activite_list'),
    path('crud/api/groupes-types-activites/', views_crud.groupe_type_activite_api, name='groupe_type_activite_api'),
    path('crud/api/groupes-types-activites/create/', views_crud.groupe_type_activite_create, name='groupe_type_activite_create'),
    path('crud/api/groupes-types-activites/<uuid:groupe_id>/update/', views_crud.groupe_type_activite_update, name='groupe_type_activite_update'),
    path('crud/api/groupes-types-activites/<uuid:groupe_id>/delete/', views_crud.groupe_type_activite_delete, name='groupe_type_activite_delete'),
    path('crud/api/types-activites/', views_crud.type_activite_api, name='type_activite_api'),
    # URLs spécifiques AVANT les URLs avec paramètres variables
    path('crud/api/types-activites/create/', views_crud.type_activite_create, name='type_activite_create'),
    path('crud/api/types-activites/<str:type_id>/', views_crud.type_activite_detail, name='type_activite_detail'),
    path('crud/api/types-activites/<str:type_id>/update/', views_crud.type_activite_update, name='type_activite_update'),
    path('crud/api/types-activites/<str:type_id>/delete/', views_crud.type_activite_delete, name='type_activite_delete'),

    # ===== CRUD Activite =====
    path('crud/activites/', views_crud.activite_list, name='activite_list'),
    path('crud/activites/type/<str:type_activite_id>/', views_crud.activite_list, name='activite_list_by_type'),
    path('crud/api/activites/', views_crud.activite_api, name='activite_api'),
    path('crud/api/activites/type/<str:type_activite_id>/', views_crud.activite_api, name='activite_api_by_type'),
    # URLs spécifiques AVANT les URLs avec paramètres variables
    path('crud/api/activites/create/', views_crud.activite_create, name='activite_create'),
    path('crud/api/activites/<str:activite_id>/', views_crud.activite_detail, name='activite_detail'),
    path('crud/api/activites/<str:activite_id>/update/', views_crud.activite_update, name='activite_update'),
    path('crud/api/activites/<str:activite_id>/delete/', views_crud.activite_delete, name='activite_delete'),

    # ===== CRUD ActivitePoste =====
    path('crud/activites-postes/', views_crud.activite_poste_list, name='activite_poste_list'),
    path('crud/activites-postes/activite/<str:activite_id>/', views_crud.activite_poste_list, name='activite_poste_list_by_activite'),
    path('crud/api/activites-postes/', views_crud.activite_poste_api, name='activite_poste_api'),
    path('crud/api/activites-postes/activite/<str:activite_id>/', views_crud.activite_poste_api, name='activite_poste_api_by_activite'),
    path('crud/api/activites-postes/fiche/<uuid:fiche_id>/', views_crud.activite_poste_api, name='activite_poste_api_by_fiche'),
    # URLs spécifiques AVANT les URLs avec paramètres variables
    path('crud/api/activites-postes/create/', views_crud.activite_poste_create, name='activite_poste_create'),
    path('crud/api/activites-postes/<str:poste_id>/', views_crud.activite_poste_detail, name='activite_poste_detail'),
    path('crud/api/activites-postes/<str:poste_id>/update/', views_crud.activite_poste_update, name='activite_poste_update'),
    path('crud/api/activites-postes/<str:poste_id>/delete/', views_crud.activite_poste_delete, name='activite_poste_delete'),

    # ===== CRUD TypeDesignation =====
    path('crud/types-designations/', views_crud_designation.type_designation_list, name='type_designation_list'),
    path('crud/api/types-designations/', views_crud_designation.type_designation_api, name='type_designation_api'),
    path('crud/api/types-designations/create/', views_crud_designation.type_designation_create, name='type_designation_create'),
    path('crud/api/types-designations/<str:type_id>/', views_crud_designation.type_designation_detail, name='type_designation_detail'),
    path('crud/api/types-designations/<str:type_id>/update/', views_crud_designation.type_designation_update, name='type_designation_update'),
    path('crud/api/types-designations/<str:type_id>/delete/', views_crud_designation.type_designation_delete, name='type_designation_delete'),

    # ===== CRUD Designation =====
    path('crud/designations/', views_crud_designation.designation_list, name='designation_list'),
    path('crud/designations/type/<str:type_designation_id>/', views_crud_designation.designation_list, name='designation_list_by_type'),
    path('crud/api/designations/', views_crud_designation.designation_api, name='designation_api'),
    path('crud/api/designations/type/<str:type_designation_id>/', views_crud_designation.designation_api, name='designation_api_by_type'),
    # URLs spécifiques AVANT les URLs avec paramètres variables
    path('crud/api/designations/create/', views_crud_designation.designation_create, name='designation_create'),
    path('crud/api/designations/<uuid:designation_id>/', views_crud_designation.designation_detail, name='designation_detail'),
    path('crud/api/designations/<uuid:designation_id>/delete-info/', views_crud_designation.designation_delete_info, name='designation_delete_info'),
    path('crud/api/designations/<uuid:designation_id>/merge/', views_crud_designation.designation_merge, name='designation_merge'),
    path('crud/api/designations/<uuid:designation_id>/update/', views_crud_designation.designation_update, name='designation_update'),
    path('crud/api/designations/<uuid:designation_id>/delete/', views_crud_designation.designation_delete, name='designation_delete'),

    # ===== CRUD DesignationCompte =====
    path('crud/designations-comptes/', views_crud_designation.designation_compte_list, name='designation_compte_list'),
    path('crud/designations-comptes/designation/<uuid:designation_id>/', views_crud_designation.designation_compte_list, name='designation_compte_list_by_designation'),
    path('crud/api/designations-comptes/', views_crud_designation.designation_compte_api, name='designation_compte_api'),
    path('crud/api/designations-comptes/designation/<uuid:designation_id>/', views_crud_designation.designation_compte_api, name='designation_compte_api_by_designation'),
    path('crud/api/designations-comptes/create/', views_crud_designation.designation_compte_create, name='designation_compte_create'),
    path('crud/api/designations-comptes/<str:compte_id>/', views_crud_designation.designation_compte_detail, name='designation_compte_detail'),
    path('crud/api/designations-comptes/<str:compte_id>/update/', views_crud_designation.designation_compte_update, name='designation_compte_update'),
    path('crud/api/designations-comptes/<str:compte_id>/delete/', views_crud_designation.designation_compte_delete, name='designation_compte_delete'),

    # ===== API pour les comptes et postes disponibles =====
    path('crud/api/comptes-disponibles/', views_crud_designation.comptes_disponibles_api, name='comptes_disponibles_api'),
    path('crud/api/postes-disponibles/', views_crud_designation.postes_disponibles_api, name='postes_disponibles_api'),

    # ===== CRUD DesignationTypeActivite =====
    path('crud/api/designations/<uuid:designation_id>/types-activites/', views_crud_designation.designation_types_activites_list, name='designation_types_activites_list'),
    path('crud/api/types-activites-disponibles/', views_crud_designation.types_activites_disponibles, name='types_activites_disponibles'),
    path('crud/api/designation-type-activites/create/', views_crud_designation.designation_type_activite_create, name='designation_type_activite_create'),
    path('crud/api/designation-type-activites/<str:liaison_id>/', views_crud_designation.designation_type_activite_detail, name='designation_type_activite_detail'),
    path('crud/api/designation-type-activites/<str:liaison_id>/update/', views_crud_designation.designation_type_activite_update, name='designation_type_activite_update'),
    path('crud/api/designation-type-activites/<str:liaison_id>/delete/', views_crud_designation.designation_type_activite_delete, name='designation_type_activite_delete'),

    # ===== API pour les postes =====
    path('crud/api/postes/', views_crud.postes_api, name='postes_api'),
    path('crud/api/postes/<uuid:poste_id>/fiches/', views_crud.poste_fiches_api, name='poste_fiches_api'),

    # ===== CRUD FichePoste =====
    path('crud/api/fiches-poste/orphelines/', views_crud.fiche_poste_orphelines, name='fiche_poste_orphelines'),
    path('crud/api/fiches-poste/', views_crud.fiche_poste_api, name='fiche_poste_api'),
    path('crud/api/fiches-poste/type/<str:type_id>/', views_crud.fiche_poste_api, name='fiche_poste_api_by_type'),
    path('crud/api/fiches-poste/create/', views_crud.fiche_poste_create, name='fiche_poste_create'),
    path('crud/api/fiches-poste/<uuid:fiche_id>/', views_crud.fiche_poste_detail, name='fiche_poste_detail'),
    path('crud/api/fiches-poste/<uuid:fiche_id>/update/', views_crud.fiche_poste_update, name='fiche_poste_update'),
    path('crud/api/fiches-poste/<uuid:fiche_id>/delete/', views_crud.fiche_poste_delete, name='fiche_poste_delete'),

    # ===== IMPORT/EXPORT EXCEL =====
    path('crud/import-excel/<str:model_name>/', views_import.import_excel_view, name='import_excel'),
    path('crud/excel-template/<str:model_name>/', views_import.download_excel_template, name='excel_template'),
    path('crud/export-excel/<str:model_name>/', views_import.export_excel_data, name='export_excel'),
]
