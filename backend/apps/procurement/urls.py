from django.urls import path

from . import views, views_import_export

app_name = 'procurement'

urlpatterns = [
    path('demandes/', views.demande_achat_list, name='demande_achat_list'),
    path('demandes/creer/', views.demande_achat_create, name='demande_achat_create'),
    path('demandes/template-excel/', views_import_export.template_excel_demandes, name='template_excel_demandes'),
    path('demandes/import-excel/', views_import_export.import_excel_demandes, name='import_excel_demandes'),
    path('demandes/<uuid:demande_id>/', views.demande_achat_detail, name='demande_achat_detail'),
    path('demandes/<uuid:demande_id>/modifier/', views.demande_achat_edit, name='demande_achat_edit'),

    path('demandes/<uuid:demande_id>/proformas/creer/', views.proforma_create, name='proforma_create'),
    path('proformas/<uuid:proforma_id>/modifier/', views.proforma_edit, name='proforma_edit'),
    path(
        'demandes/<uuid:demande_id>/proformas/template-excel/',
        views_import_export.template_excel_proformas,
        name='template_excel_proformas',
    ),
    path(
        'demandes/<uuid:demande_id>/proformas/import-excel/',
        views_import_export.import_excel_proformas,
        name='import_excel_proformas',
    ),

    path('demandes/<uuid:demande_id>/comparatif/', views.comparatif, name='comparatif'),
    path(
        'demandes/<uuid:demande_id>/comparatif/enregistrer/',
        views.comparatif_enregistrer_selection,
        name='comparatif_enregistrer_selection',
    ),

    path('demandes/<uuid:demande_id>/generation-bc/', views.generation_bc, name='generation_bc'),
    path('demandes/<uuid:demande_id>/generation-bc/valider/', views.generation_bc_valider, name='generation_bc_valider'),
    path('bons-commande/<uuid:bon_id>/', views.bon_commande_detail, name='bon_commande_detail'),
]
