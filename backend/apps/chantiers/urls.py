from django.urls import path

from . import views
from . import views_workflow_ui

try:
    from . import views_workflow
except Exception:
    views_workflow = None

app_name = 'chantiers'

urlpatterns = [
    # UI workflow chantier (Django server-side)
    path('workflows/', views_workflow_ui.workflows_ui_list, name='workflows_ui_list'),
    path('workflows/<uuid:workflow_id>/', views_workflow_ui.workflow_ui_detail, name='workflow_ui_detail'),
    path('workflows/<uuid:workflow_id>/suivi/', views_workflow_ui.workflow_ui_update_suivi, name='workflow_ui_update_suivi'),
    path('workflows/<uuid:workflow_id>/cloturer/', views_workflow_ui.workflow_ui_cloturer, name='workflow_ui_cloturer'),
    path('workflows/<uuid:workflow_id>/selection/add/', views_workflow_ui.workflow_ui_add_selection, name='workflow_ui_add_selection'),
    path('workflows/<uuid:workflow_id>/generate-besoins/', views_workflow_ui.workflow_ui_generate_besoins, name='workflow_ui_generate_besoins'),
    path('workflows/<uuid:workflow_id>/surplus/add/', views_workflow_ui.workflow_ui_add_surplus, name='workflow_ui_add_surplus'),
    path('workflows/<uuid:workflow_id>/surplus/integrate/', views_workflow_ui.workflow_ui_integrate_surplus, name='workflow_ui_integrate_surplus'),
    path('workflows/<uuid:workflow_id>/devis/generate/', views_workflow_ui.workflow_ui_generate_devis, name='workflow_ui_generate_devis'),
    path('workflows/<uuid:workflow_id>/contrat/create/', views_workflow_ui.workflow_ui_create_contrat, name='workflow_ui_create_contrat'),
    path('workflows/<uuid:workflow_id>/avenant/create/', views_workflow_ui.workflow_ui_create_avenant, name='workflow_ui_create_avenant'),
    path('workflows/<uuid:workflow_id>/facture-tranche/create/', views_workflow_ui.workflow_ui_create_facture_tranche, name='workflow_ui_create_facture_tranche'),
    path('workflows/<uuid:workflow_id>/mouvement/add/', views_workflow_ui.workflow_ui_add_mouvement, name='workflow_ui_add_mouvement'),
    path('workflows/<uuid:workflow_id>/devis-final/generate/', views_workflow_ui.workflow_ui_generate_devis_final, name='workflow_ui_generate_devis_final'),
    path('workflows/citerne-config/', views_workflow_ui.workflow_ui_citerne_config_list, name='workflow_ui_citerne_config_list'),
    path('workflows/citerne-config/template/', views_workflow_ui.workflow_ui_citerne_config_template, name='workflow_ui_citerne_config_template'),
    path('workflows/citerne-config/import/', views_workflow_ui.workflow_ui_citerne_config_import, name='workflow_ui_citerne_config_import'),

    # Demandes de villages
    path('demandes/', views.demandes_list, name='demandes_list'),
    path('demandes/api/villages/', views.api_villages_search, name='api_villages_search'),
    path('demandes/create/', views.demande_create, name='demande_create'),
    path('demandes/<uuid:demande_id>/', views.demande_detail, name='demande_detail'),
    path('demandes/<uuid:demande_id>/update/', views.demande_update, name='demande_update'),
    path('demandes/<uuid:demande_id>/delete/', views.demande_delete, name='demande_delete'),

    # Validations de sources
    path('validations-sources/', views.validations_list, name='validations_list'),
    path('validations-sources/create/', views.validation_create, name='validation_create'),
    path('validations-sources/<uuid:validation_id>/get/', views.validation_get, name='validation_get'),
    path('validations-sources/<uuid:validation_id>/update/', views.validation_update, name='validation_update'),
    path('validations-sources/<uuid:validation_id>/delete/', views.validation_delete, name='validation_delete'),
    path('validations-sources/clear-all/', views.validation_clear_all, name='validation_clear_all'),

    # Chantiers
    path('chantiers/', views.chantiers_list, name='chantiers_list'),
    path('chantiers/kanban/', views.chantiers_kanban, name='chantiers_kanban'),
    path('chantiers/<int:chantier_id>/update-etat/', views.chantier_update_etat, name='chantier_update_etat'),

    # Export Excel
    path('demandes/export-excel/', views.export_demandes_excel, name='demandes_export_excel'),
    path('validations-sources/export-excel/', views.export_validations_excel, name='validations_export_excel'),
    path('chantiers/export-excel/', views.export_chantiers_excel, name='chantiers_export_excel'),

    # Import Excel
    path('demandes/import-excel/', views.import_demandes_excel, name='demandes_import_excel'),
    path('validations-sources/import-excel/', views.import_validations_excel, name='validations_import_excel'),
    path('chantiers/import-excel/', views.import_chantiers_excel, name='chantiers_import_excel'),

    # Templates Excel
    path('demandes/template-excel/', views.export_template_demandes, name='demandes_template_excel'),
    path('validations-sources/template-excel/', views.export_template_validations, name='validations_template_excel'),
    path('chantiers/template-excel/', views.export_template_chantiers, name='chantiers_template_excel'),

    # Tâcherons
    path('tacherons/', views.tacherons_list, name='tacherons_list'),
    path('tacherons/create/', views.tacheron_create, name='tacheron_create'),
    path('tacherons/<uuid:tacheron_id>/update/', views.tacheron_update, name='tacheron_update'),
    path('tacherons/<uuid:tacheron_id>/delete/', views.tacheron_delete, name='tacheron_delete'),
    path('tacherons/export-excel/', views.export_tacherons_excel, name='tacherons_export_excel'),
    path('tacherons/import-excel/', views.import_tacherons_excel, name='tacherons_import_excel'),
    path('tacherons/template-excel/', views.export_template_tacherons, name='tacherons_template_excel'),

    # Enquêtes ménages
    path('chantiers/<uuid:chantier_id>/menages/', views.menages_list, name='menages_list'),
    path('chantiers/<uuid:chantier_id>/menages/create/', views.menage_create, name='menage_create'),
    path('menages/<uuid:menage_id>/enquete/<str:type_enquete>/', views.enquete_form, name='enquete_form'),
    path('menages/<uuid:menage_id>/detail/', views.menage_detail, name='menage_detail'),

    # Animations
    path('chantiers/<uuid:chantier_id>/animations/', views.animations_list, name='animations_list'),
    path('chantiers/<uuid:chantier_id>/animations/create/', views.animation_create, name='animation_create'),
    path('animations/<uuid:session_id>/participants/', views.animation_participants, name='animation_participants'),
    path('animations/<uuid:session_id>/presence/', views.animation_presence, name='animation_presence'),

    # Dashboard
    path('chantiers/<uuid:chantier_id>/dashboard/', views.chantier_dashboard, name='chantier_dashboard'),

]

if views_workflow is not None:
    urlpatterns += [
        # API workflow chantier (v2)
        path('api/workflows/create/', views_workflow.workflow_create, name='workflow_create'),
        path('api/workflows/<uuid:workflow_id>/', views_workflow.workflow_detail, name='workflow_detail'),
        path('api/workflows/<uuid:workflow_id>/selections/add/', views_workflow.workflow_add_selection, name='workflow_add_selection'),
        path('api/workflows/<uuid:workflow_id>/generate-besoins/', views_workflow.workflow_generate_besoins, name='workflow_generate_besoins'),
        path('api/workflows/<uuid:workflow_id>/besoins/', views_workflow.workflow_besoins, name='workflow_besoins'),
        path('api/workflows/<uuid:workflow_id>/surplus/add/', views_workflow.workflow_surplus_add, name='workflow_surplus_add'),
        path('api/workflows/<uuid:workflow_id>/surplus/', views_workflow.workflow_surplus_list, name='workflow_surplus_list'),
        path('api/workflows/<uuid:workflow_id>/surplus/integrate/', views_workflow.workflow_surplus_integrate, name='workflow_surplus_integrate'),
        path('api/workflows/<uuid:workflow_id>/devis/generate/', views_workflow.workflow_generate_devis, name='workflow_generate_devis'),
        path('api/workflows/<uuid:workflow_id>/documents/', views_workflow.workflow_documents_list, name='workflow_documents_list'),
        path('api/workflows/<uuid:workflow_id>/contrat/create/', views_workflow.workflow_create_contrat, name='workflow_create_contrat'),
        path('api/workflows/<uuid:workflow_id>/avenant/create/', views_workflow.workflow_create_avenant, name='workflow_create_avenant'),
        path('api/workflows/<uuid:workflow_id>/facture-tranche/create/', views_workflow.workflow_create_facture_tranche, name='workflow_create_facture_tranche'),
        path('api/workflows/<uuid:workflow_id>/documents/<uuid:document_id>/statut/', views_workflow.workflow_update_document_statut, name='workflow_update_document_statut'),
        path('api/workflows/<uuid:workflow_id>/contrat/suivi/', views_workflow.workflow_contrat_suivi, name='workflow_contrat_suivi'),
        path('api/workflows/<uuid:workflow_id>/mouvements/add/', views_workflow.workflow_add_mouvement, name='workflow_add_mouvement'),
        path('api/workflows/<uuid:workflow_id>/mouvements/', views_workflow.workflow_mouvements_list, name='workflow_mouvements_list'),
        path('api/workflows/<uuid:workflow_id>/recollement/synthese/', views_workflow.workflow_recollement_synthese, name='workflow_recollement_synthese'),
        path('api/workflows/<uuid:workflow_id>/devis-final/generate/', views_workflow.workflow_generate_devis_final, name='workflow_generate_devis_final'),
    ]
