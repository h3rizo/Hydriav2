from django.urls import path
from .views_pointage import pointage_mensuel
from . import views
from . import views_temporaire
from . import views_entry_pointage
from . import views_export_access
from . import views_documentation
from . import views_verification_scans
from . import views_verification_scans_export
from . import views_ocr
from . import views_recoupement_salaires
from . import views_reconstitution_diamex
from . import views_recoupement_indemnites
from . import views_recoupement_indemnites_pe
from . import views_recoupement_frais
from . import views_recoupement_intelligent
from . import views_verification_fournisseurs
from . import views_verification_fournisseurs_print
from . import views_verification_autres
from . import views_verification_autres_print
from . import views_verification_ouvrages
from . import views_verification_unifiee
from . import views_evaluation_saisie
from . import views_soldes_reels
from . import views_demandes_fonds
from . import views_recoupement_forfaitaires
from . import views_controle_conversion
from . import views_conversion_partie_double
from . import views_export_partie_double
from . import views_declaration_communication
from . import views_declaration_export_templates
from . import views_natures_declaration
from . import views_taxe_communale
from . import views_download_package
from . import views_dashboard_forfaitaire
from . import views_dashboard_frequence_forfaitaire
from . import views_dashboard_periode
from . import views_dashboard_recettes
from . import views_ouvrage_aliases
from . import views_analyse_couts_ouvrages
from . import views_grand_livre_impression
try:
    from . import views_saisie_workflow
    from . import views_restes_livrer
except Exception:
    views_saisie_workflow = None
    views_restes_livrer = None
try:
    from . import views_ai_prefill
except Exception:
    views_ai_prefill = None
try:
    from . import views_regles_saisie
except Exception:
    views_regles_saisie = None
from .views_documentation_delete import api_delete_document

app_name = 'accounting'

urlpatterns = [
    path('pointage-mensuel/', pointage_mensuel, name='pointage_mensuel'),
    path('import/', views.import_diamex_home, name='import_home'),
    path('import/from-access/', views.import_from_access, name='import_from_access'),
    path('import/from-bases/', views.import_from_bases, name='import_from_bases'),
    path('import/progress/<str:session_id>/', views.api_import_progress, name='api_import_progress'),
    path('import/clear/', views.clear_all_data, name='clear_all'),
    path('import/delete-file/', views.delete_file_data, name='delete_file_data'),
    # API pour import LOCAL depuis Windows
    path('api/import-from-access/', views.import_from_access, name='api_import_from_access'),
    path('api/imported-scans-status/', views.imported_scans_status, name='api_imported_scans_status'),
    path('api/upload-imported-scans/', views.upload_imported_scans, name='api_upload_imported_scans'),
    # Téléchargement du package portable
    path('import/telecharger-package/', views_download_package.telecharger_package_portable, name='telecharger_package_portable'),
    path('dashboard/', views.dashboard_comptabilite, name='dashboard_comptabilite'),
    path('dashboard/analyse-salaires/', views.analyse_categorie_salaires, name='analyse_categorie_salaires'),
    path('entries/', views.entries_list, name='entries_list'),
    path('entries/avances-pers/', views.detail_avances_pers, name='detail_avances_pers'),
    # Grand livre imprimable (financement + période choisis) : document sans habillage.
    path('entries/grand-livre/impression/', views_grand_livre_impression.entries_grand_livre_impression,
         name='entries_grand_livre_impression'),
    path('entries/<int:entry_id>/pointage/', views_entry_pointage.entry_pointage_detail, name='entry_pointage_detail'),
    path('entries/<int:entry_id>/explication-indemnite/', views_entry_pointage.entry_explication_indemnite, name='entry_explication_indemnite'),
    path('workflow/pointage-tiers/', views.workflow_pointage_tiers, name='workflow_pointage_tiers'),
    path('workflow/pointage-tiers/api/valider/', views.api_workflow_pointage_tiers, name='api_workflow_pointage_tiers'),
    path('workflow/pointage-tiers/api/annuler/', views.api_workflow_depointage_tiers, name='api_workflow_depointage_tiers'),
    path('soldes-reels-workflow/', views.workflow_soldes_reels, name='workflow_soldes_reels'),
    path('soldes-reels-workflow/api/save/', views.api_workflow_soldes_reels_save, name='api_workflow_soldes_reels_save'),
    # path('verification/', views.verification_comptabilite, name='verification_comptabilite'),  # ✅ Page supprimée (doublon avec entries)
    path('verification-transferts/', views.verification_transferts, name='verification_transferts'),
    path('diagnostic/soldes/', views.diagnostic_soldes, name='diagnostic_soldes'),
    path('scan/<int:entry_id>/', views.serve_scan_file, name='serve_scan'),
    path('recoupement/planning/', views.recoupement_planning, name='recoupement_planning'),
    path('recoupement/salaires/', views_recoupement_salaires.recoupement_salaires, name='recoupement_salaires'),
    path('recoupement/releves/', views.recoupement_releves, name='recoupement_releves'),
    path('recoupement/forfaitaires/', views_recoupement_forfaitaires.recoupement_paiements_forfaitaires, name='recoupement_forfaitaires'),

    # Reconstitution DiameX Salaires
    path('reconstitution/salaires/', views_reconstitution_diamex.reconstitution_diamex_salaires, name='reconstitution_diamex_salaires'),
    path('reconstitution/api/rechercher-correspondances/', views_reconstitution_diamex.api_rechercher_correspondances, name='api_rechercher_correspondances'),
    path('reconstitution/api/appliquer-correspondances/', views_reconstitution_diamex.api_appliquer_correspondances, name='api_appliquer_correspondances'),
    path('reconstitution/api/batch/', views_reconstitution_diamex.api_reconstitution_batch, name='api_reconstitution_batch'),
    path('recoupement/releves/api/get-releves/', views.api_get_releves_ouvrage_mois, name='api_get_releves_ouvrage_mois'),
    path('recoupement/releves/api/update-releve/', views.api_update_releve_diamex, name='api_update_releve_diamex'),
    path('recoupement/releves/api/details-3e/', views.api_details_recoupement_3e, name='api_details_recoupement_3e'),
    path('dashboard-paiements-volume/api/remarque/', views.api_save_remarque_recouvrement_volume, name='api_save_remarque_recouvrement_volume'),
    path('recoupement/demandes-bp/', views.recoupement_demandes_bp, name='recoupement_demandes_bp'),
    path('recoupement/demandes-bp/api/get-points-eau/', views.api_get_points_eau_demande_bp, name='api_get_points_eau_demande_bp'),
    path('recoupement/demandes-bp/api/update-point-eau/', views.api_update_point_eau_demande_bp, name='api_update_point_eau_demande_bp'),
    path('recoupement/devis-bp/', views.recoupement_devis_bp, name='recoupement_devis_bp'),
    path('recoupement/devis-bp/api/get-points-eau/', views.api_get_points_eau_devis_bp, name='api_get_points_eau_devis_bp'),
    path('recoupement/devis-bp/api/update-point-eau/', views.api_update_point_eau_devis_bp, name='api_update_point_eau_devis_bp'),
    path('recoupement/cartes-sociales/', views.recoupement_cartes_sociales, name='recoupement_cartes_sociales'),
    path('recoupement/achats/', views.recoupement_achats, name='recoupement_achats'),

    # Recoupement Indemnités Employés
    path('recoupement/indemnites/', views_recoupement_indemnites.recoupement_indemnites, name='recoupement_indemnites'),
    path('recoupement/indemnites/api/appliquer/', views_recoupement_indemnites.api_appliquer_diamex_indemnites, name='api_appliquer_diamex_indemnites'),
    path('recoupement/indemnites/api/rechercher/', views_recoupement_indemnites.api_rechercher_correspondance_indemnite, name='api_rechercher_correspondance_indemnite'),
    path('recoupement/indemnites/api/batch/', views_recoupement_indemnites.api_recoupement_batch_indemnites, name='api_recoupement_batch_indemnites'),

    # Recoupement Indemnités Points d'Eau (compte 621102)
    path('recoupement/indemnites-pe/', views_recoupement_indemnites_pe.recoupement_indemnites_pe, name='recoupement_indemnites_pe'),
    path('entry/<int:entry_id>/update/', views.update_entry, name='update_entry'),
    path('file/open/', views.open_file_windows, name='open_file_windows'),
    path('api/verifier-scans/', views.api_verifier_scans, name='api_verifier_scans'),

    # Vérification scans - Récapitulatif
    path('verification-scans/', views_verification_scans.verification_scans_recap, name='verification_scans_recap'),
    path('verification-scans/api/detail/', views_verification_scans.api_detail_scans, name='api_detail_scans'),
    path('verification-scans/export-excel/', views_verification_scans_export.export_excel_scans, name='export_excel_scans'),
    path('verification-scans/impression/', views_verification_scans_export.impression_scans, name='impression_scans'),

    # Soldes réels - Gestion CRUD (corrections manuelles uniquement, import depuis Access)
    path('soldes-reels/', views_soldes_reels.soldes_reels_list, name='soldes_reels_list'),
    path('soldes-reels/api/list/', views_soldes_reels.api_soldes_reels_list, name='api_soldes_reels_list'),
    path('soldes-reels/api/create/', views_soldes_reels.api_solde_reel_create, name='api_solde_reel_create'),
    path('soldes-reels/api/<int:solde_id>/update/', views_soldes_reels.api_solde_reel_update, name='api_solde_reel_update'),
    path('soldes-reels/api/<int:solde_id>/delete/', views_soldes_reels.api_solde_reel_delete, name='api_solde_reel_delete'),

    # Comparaison soldes (existant)
    path('comparaison-soldes/', views.comparaison_soldes, name='comparaison_soldes'),
    path('api/details-solde/', views.api_details_solde, name='api_details_solde'),
    path('api/update-solde-reel/', views.api_update_solde_reel, name='api_update_solde_reel'),

    # Transactions temporaires DiameX
    path('temporaire/', views_temporaire.transactions_temporaires_list, name='transactions_temporaires_list'),
    path('temporaire/salaires/', views_temporaire.transactions_temporaires_salaires_list, name='transactions_temporaires_salaires_list'),
    path('temporaire/<int:transaction_id>/get/', views_temporaire.transaction_temporaire_get, name='transaction_temporaire_get'),
    path('temporaire/<int:transaction_id>/update/', views_temporaire.transaction_temporaire_update, name='transaction_temporaire_update'),
    path('temporaire/change-status/', views_temporaire.transaction_temporaire_change_status, name='transaction_temporaire_change_status'),
    path('temporaire/delete/', views_temporaire.transaction_temporaire_delete, name='transaction_temporaire_delete'),
    path('temporaire/export/', views_temporaire.export_transactions_csv, name='export_transactions_csv'),
    path('temporaire/export-access/', views_export_access.export_to_access, name='export_to_access'),
    path('temporaire/export-access/prepare/', views_export_access.export_to_access_prepare, name='export_to_access_prepare'),
    path('temporaire/export-access/finalize/', views_export_access.export_to_access_finalize, name='export_to_access_finalize'),
    path('temporaire/api/update-ids-diamex/', views_temporaire.api_update_ids_diamex, name='api_update_ids_diamex'),

    # Documentation comptable justificative
    path('documentation/saisie/', views_documentation.documentation_saisie, name='documentation_saisie'),
    path('documentation/rapport/', views_documentation.documentation_rapport, name='documentation_rapport'),
    path('documentation/<uuid:doc_id>/update/', views_documentation.api_update_document, name='api_update_document'),
    path('documentation/<uuid:doc_id>/delete/', api_delete_document, name='api_delete_document'),
    path('documentation/verifier/', views_documentation.api_verifier_documents, name='api_verifier_documents'),
    path('documentation/api/grand-livre/', views_documentation.api_generer_grand_livre, name='api_generer_grand_livre'),
    path('documentation/api/rapprochement-solde/', views_documentation.api_rapprochement_solde, name='api_rapprochement_solde'),
    path('documentation/api/compte-tiers/', views_documentation.api_compte_tiers, name='api_compte_tiers'),
    path('documentation/api/comptage-caisse/', views_documentation.api_comptage_caisse, name='api_comptage_caisse'),
    path('documentation/api/releve-bancaire/', views_documentation.api_releve_bancaire, name='api_releve_bancaire'),

    # OCR Vérification
    path('documentation/api/ocr-verification/', views_ocr.api_ocr_verification, name='api_ocr_verification'),
    path('documentation/api/serve-scan/', views_ocr.serve_scan_image, name='serve_scan_image'),

    # Recoupement Frais Médicaux
    path('recoupement/frais-medicaux/', views_recoupement_frais.recoupement_frais_medicaux, name='recoupement_frais_medicaux'),
    path('recoupement/frais-medicaux/api/liste/', views_recoupement_frais.api_frais_medicaux_a_recouper, name='api_frais_medicaux_a_recouper'),
    path('recoupement/frais-medicaux/api/rechercher/', views_recoupement_frais.api_rechercher_diamex_frais_medical, name='api_rechercher_diamex_frais_medical'),
    path('recoupement/frais-medicaux/api/appliquer/', views_recoupement_frais.api_appliquer_diamex_frais_medical, name='api_appliquer_diamex_frais_medical'),

    # Recoupement Frais Scolarité
    path('recoupement/frais-scolarite/', views_recoupement_frais.recoupement_frais_scolarite, name='recoupement_frais_scolarite'),
    path('recoupement/frais-scolarite/api/liste/', views_recoupement_frais.api_frais_scolarite_a_recouper, name='api_frais_scolarite_a_recouper'),
    path('recoupement/frais-scolarite/api/rechercher/', views_recoupement_frais.api_rechercher_diamex_frais_scolarite, name='api_rechercher_diamex_frais_scolarite'),
    path('recoupement/frais-scolarite/api/appliquer/', views_recoupement_frais.api_appliquer_diamex_frais_scolarite, name='api_appliquer_diamex_frais_scolarite'),

    # Recoupement intelligent DiameX <-> Relevés
    path('recoupement/api/rechercher-releves-candidats/', views_recoupement_intelligent.api_rechercher_releves_candidats, name='api_rechercher_releves_candidats'),
    path('recoupement/api/associer-releves-diamex/', views_recoupement_intelligent.api_associer_releves_diamex, name='api_associer_releves_diamex'),

    # Vérification Fournisseurs
    path('verification-fournisseurs/', views_verification_fournisseurs.verification_depenses_fournisseurs, name='verification_fournisseurs'),
    path('verification-fournisseurs/print/', views_verification_fournisseurs_print.verification_fournisseurs_print, name='verification_fournisseurs_print'),
    path('verification-fournisseurs/api/', views_verification_fournisseurs.api_verification_depenses_fournisseurs, name='api_verification_fournisseurs'),
    path('verification-fournisseurs/api/modifier/', views_verification_fournisseurs.api_modifier_description_fournisseur, name='api_modifier_description_fournisseur'),
    path('verification-fournisseurs/api/modifier-lot/', views_verification_fournisseurs.api_modifier_fournisseur_lot, name='api_modifier_fournisseur_lot'),
    path('verification-fournisseurs/api/ajouter-fournisseur/', views_verification_fournisseurs.api_ajouter_fournisseur, name='api_ajouter_fournisseur'),

    # Vérification Autres Comptes
    path('verification-autres/', views_verification_autres.verification_autres_comptes, name='verification_autres'),
    path('verification-autres/print/', views_verification_autres_print.verification_autres_print, name='verification_autres_print'),
    path('verification-autres/api/', views_verification_autres.api_verification_autres_comptes, name='api_verification_autres'),
    path('verification-autres/api/modifier/', views_verification_autres.api_modifier_entry_autre, name='api_modifier_entry_autre'),

    # Nouvelles pages de vérification séparées par ouvrage
    path('verification-avec-ouvrage/', views_verification_ouvrages.verification_avec_ouvrage, name='verification_avec_ouvrage'),
    path('verification-ouvrages/aliases/', views_ouvrage_aliases.gestion_aliases_ouvrages, name='gestion_aliases_ouvrages'),
    path('verification-sans-ouvrage/', views_verification_ouvrages.verification_sans_ouvrage, name='verification_sans_ouvrage'),
    path('verification-ouvrage/api/', views_verification_ouvrages.api_verification_list, name='api_verification_ouvrage'),
    path('verification-ouvrage/print/', views_verification_ouvrages.verification_ouvrage_print, name='verification_ouvrage_print'),
    path('verification-ouvrage/api/integrer-nom-abonne/', views_verification_ouvrages.api_integrer_nom_abonne_point_eau, name='api_integrer_nom_abonne_point_eau'),
    path('verification-ouvrage/api/peupler-noms-abonnes/', views_verification_ouvrages.api_peupler_noms_abonnes, name='api_peupler_noms_abonnes'),
    path('verification-ouvrage/api/peupler-noms-abonnes/stream/', views_verification_ouvrages.api_peupler_noms_abonnes_stream, name='api_peupler_noms_abonnes_stream'),
    path('verification-ouvrage/api/renseigner-telephone/', views_verification_ouvrages.api_renseigner_telephone_point_eau, name='api_renseigner_telephone_point_eau'),
    path('verification-ouvrage/api/point-eau/<uuid:point_eau_id>/extractions/', views_verification_ouvrages.api_extractions_point_eau, name='api_extractions_point_eau'),

    # Vérification Unifiée (combine les 4 workflows)
    path('verification-unifiee/', views_verification_unifiee.verification_unifiee, name='verification_unifiee'),

    # Évaluation de la saisie comptable
    path('evaluation-saisie/', views_evaluation_saisie.evaluation_saisie, name='evaluation_saisie'),
    path('api/evaluation-saisie/stats-globales/', views_evaluation_saisie.api_stats_saisie_globales, name='api_stats_saisie_globales'),
    path('api/evaluation-saisie/par-jour/', views_evaluation_saisie.api_saisie_par_jour, name='api_saisie_par_jour'),
    path('api/evaluation-saisie/par-mois-compta/', views_evaluation_saisie.api_saisie_par_mois_compta, name='api_saisie_par_mois_compta'),
    path('api/evaluation-saisie/delai/', views_evaluation_saisie.api_delai_saisie, name='api_delai_saisie'),
    path('api/evaluation-saisie/fichiers-sources/', views_evaluation_saisie.api_fichiers_sources, name='api_fichiers_sources'),
    path('api/evaluation-saisie/top-jours/', views_evaluation_saisie.api_top_jours_productifs, name='api_top_jours_productifs'),
    path('api/evaluation-saisie/decalage-mois/', views_evaluation_saisie.api_decalage_par_mois, name='api_decalage_par_mois'),
    path('api/evaluation-saisie/calendrier/', views_evaluation_saisie.api_calendrier_saisie, name='api_calendrier_saisie'),
    path('api/evaluation-saisie/employe/', views_evaluation_saisie.api_evaluation_saisie_employe, name='api_evaluation_saisie_employe'),
    path('api/evaluation-recouvrement/employe/', views_evaluation_saisie.api_evaluation_recouvrement_employe, name='api_evaluation_recouvrement_employe'),

    # Demandes de fonds - Budget et workflow
    path('budgets/', views_demandes_fonds.budgets_list, name='budgets_list'),
    path('budgets/api/list/', views_demandes_fonds.api_budgets_list, name='api_budgets_list'),
    path('budgets/api/create/', views_demandes_fonds.api_budget_create, name='api_budget_create'),
    path('budgets/api/salary/employees/', views_demandes_fonds.api_budget_salary_employees, name='api_budget_salary_employees'),
    path('budgets/api/salary/preview/', views_demandes_fonds.api_budget_salary_preview, name='api_budget_salary_preview'),
    path('budgets/api/salary/create/', views_demandes_fonds.api_budget_create_salary, name='api_budget_create_salary'),
    path('budgets/api/employee-benefits/employees/', views_demandes_fonds.api_budget_employee_benefits_employees, name='api_budget_employee_benefits_employees'),
    path('budgets/api/employee-benefits/preview/', views_demandes_fonds.api_budget_employee_benefits_preview, name='api_budget_employee_benefits_preview'),
    path('budgets/api/employee-benefits/create/', views_demandes_fonds.api_budget_create_employee_benefits, name='api_budget_create_employee_benefits'),
    path('budgets/api/other-accounts/rows/', views_demandes_fonds.api_budget_other_accounts_rows, name='api_budget_other_accounts_rows'),
    path('budgets/api/full-workflow/preview/', views_demandes_fonds.api_budget_full_workflow_preview, name='api_budget_full_workflow_preview'),
    path('budgets/api/full-workflow/create/', views_demandes_fonds.api_budget_create_full_workflow, name='api_budget_create_full_workflow'),
    path('budgets/api/other-accounts/preview/', views_demandes_fonds.api_budget_other_accounts_preview, name='api_budget_other_accounts_preview'),
    path('budgets/api/other-accounts/create/', views_demandes_fonds.api_budget_create_other_accounts, name='api_budget_create_other_accounts'),
    path('budgets/api/import-excel/', views_demandes_fonds.api_budget_import_excel, name='api_budget_import_excel'),
    path('budgets/api/import-excel/template/', views_demandes_fonds.api_budget_import_excel_template, name='api_budget_import_excel_template'),
    path('budgets/api/creer-depuis-previsions/', views_demandes_fonds.api_budget_creer_depuis_previsions, name='api_budget_creer_depuis_previsions'),
    path('budgets/<uuid:budget_id>/', views_demandes_fonds.budget_detail, name='budget_detail'),
    path('budgets/<uuid:budget_id>/api/lignes/', views_demandes_fonds.api_budget_lignes, name='api_budget_lignes'),
    path('budgets/<uuid:budget_id>/api/ligne/save/', views_demandes_fonds.api_budget_ligne_save, name='api_budget_ligne_save'),
    path('budgets/<uuid:budget_id>/api/valider/', views_demandes_fonds.api_budget_valider, name='api_budget_valider'),

    # Demandes de fonds
    path('demandes-fonds/', views_demandes_fonds.demandes_fonds_list, name='demandes_fonds_list'),
    path('demandes-fonds/api/list/', views_demandes_fonds.api_demandes_fonds_list, name='api_demandes_fonds_list'),
    path('demandes-fonds/api/preview/', views_demandes_fonds.api_demande_fonds_preview, name='api_demande_fonds_preview'),
    path('demandes-fonds/api/create/', views_demandes_fonds.api_demande_fonds_create, name='api_demande_fonds_create'),
    path('demandes-fonds/<uuid:demande_id>/', views_demandes_fonds.demande_fonds_detail, name='demande_fonds_detail'),
    path('demandes-fonds/<uuid:demande_id>/api/lignes/', views_demandes_fonds.api_demande_fonds_lignes, name='api_demande_fonds_lignes'),
    path('demandes-fonds/ligne/<uuid:ligne_id>/api/explication/', views_demandes_fonds.api_demande_fonds_update_explication, name='api_demande_fonds_update_explication'),
    path('demandes-fonds/<uuid:demande_id>/api/valider/', views_demandes_fonds.api_demande_fonds_valider, name='api_demande_fonds_valider'),

    # Contrôle conversion partie double
    path('controle-conversion/', views_controle_conversion.controle_conversion_page, name='controle_conversion'),
    path('controle-conversion/api/', views_controle_conversion.api_controle_conversion, name='api_controle_conversion'),

    # Conversion en partie double
    path('conversion-partie-double/', views_conversion_partie_double.conversion_partie_double_page, name='conversion_partie_double'),
    path('conversion-partie-double/api/stats/', views_conversion_partie_double.api_stats_conversion, name='api_stats_conversion'),
    path('conversion-partie-double/api/convertir/', views_conversion_partie_double.api_convertir_entrees, name='api_convertir_entrees'),
    path('conversion-partie-double/api/analyser-erreurs-pers/', views_conversion_partie_double.api_analyser_erreurs_pers, name='api_analyser_erreurs_pers'),
    path('conversion-partie-double/api/ecritures/', views_conversion_partie_double.api_ecritures_partie_double_list, name='api_ecritures_partie_double_list'),
    path('conversion-partie-double/api/export-excel/', views_export_partie_double.api_export_partie_double_excel, name='api_export_partie_double_excel'),
    path('conversion-partie-double/api/export-progress/', views_export_partie_double.api_export_partie_double_progress, name='api_export_partie_double_progress'),
    path('conversion-partie-double/api/export-scans-mois/', views_export_partie_double.api_export_scans_mois, name='api_export_scans_mois'),

    # Déclaration de communication aux impôts
    path('declaration-communication/', views_declaration_communication.declaration_communication, name='declaration_communication'),
    path('declaration-communication/api/generer/', views_declaration_communication.api_generer_declaration, name='api_generer_declaration'),
    path('declaration-communication/api/export-excel/', views_declaration_communication.api_export_declaration_excel, name='api_export_declaration_excel'),
    path('declaration-communication/api/export-templates/', views_declaration_export_templates.api_export_declaration_templates, name='api_export_declaration_templates'),

    # Gestion des natures de déclaration
    path('natures-declaration/', views_natures_declaration.natures_declaration_list, name='natures_declaration_list'),
    path('natures-declaration/api/list/', views_natures_declaration.api_natures_declaration_list, name='api_natures_declaration_list'),
    path('natures-declaration/api/create/', views_natures_declaration.api_nature_declaration_create, name='api_nature_declaration_create'),
    path('natures-declaration/api/<uuid:nature_id>/update/', views_natures_declaration.api_nature_declaration_update, name='api_nature_declaration_update'),
    path('natures-declaration/api/<uuid:nature_id>/delete/', views_natures_declaration.api_nature_declaration_delete, name='api_nature_declaration_delete'),

    # Dashboard paiements au volume
    path('dashboard-paiements-volume/', views.dashboard_paiements_volume, name='dashboard_paiements_volume'),
    path('dashboard-paiements-cartes-sociales/', views.dashboard_paiements_cartes_sociales, name='dashboard_paiements_cartes_sociales'),
    path('dashboard-paiements-volume/impression/', views.dashboard_paiements_volume_impression, name='dashboard_paiements_volume_impression'),
    path('dashboard-paiements-volume/api/communes/', views.api_paiements_volume_communes_summary, name='api_paiements_volume_communes_summary'),
    path('dashboard-paiements-volume/api/pointage-releves/', views.api_pointage_releves_diamex, name='api_pointage_releves_diamex'),
    path('dashboard-paiements-volume/api/pointage-releves/annuler/', views.api_annuler_pointage_releves_diamex, name='api_annuler_pointage_releves_diamex'),
    path('dashboard-paiements-volume/api/releve/delete/', views.api_delete_releve_pointage, name='api_delete_releve_pointage'),
    path('dashboard-paiements-volume/api/ouvrage/<uuid:ouvrage_id>/ecart-detail/', views.api_ouvrage_ecart_detail, name='api_ouvrage_ecart_detail'),
    path('dashboard-paiements-volume/ouvrage/<uuid:ouvrage_id>/ecart-impression/', views.dashboard_paiements_volume_ecart_impression, name='dashboard_paiements_volume_ecart_impression'),
    path('dashboard-paiements-cartes-sociales/api/details/', views.api_details_paiements_cartes_sociales, name='api_details_paiements_cartes_sociales'),
    path('dashboard-paiements-cartes-sociales/api/pointage/', views.api_pointage_consos_cartes_sociales, name='api_pointage_consos_cartes_sociales'),
    path('dashboard-paiements-cartes-sociales/api/conso/delete-zero/', views.api_delete_conso_carte_sociale_zero, name='api_delete_conso_carte_sociale_zero'),
    path('dashboard-paiements-cartes-sociales/api/conso/annuler-pointage/', views.api_annuler_pointage_conso_carte_sociale, name='api_annuler_pointage_conso_carte_sociale'),
    path('api/delais-paiement-details/', views.api_delais_paiement_details, name='api_delais_paiement_details'),

    # Dashboard paiements forfaitaires
    path('dashboard-paiements-forfaitaire/', views_dashboard_forfaitaire.dashboard_paiements_forfaitaire, name='dashboard_paiements_forfaitaire'),
    path('dashboard-paiements-volume/periode/', views_dashboard_periode.dashboard_paiements_volume_periode, name='dashboard_paiements_volume_periode'),
    path('dashboard-paiements-volume/periode/export/', views_dashboard_periode.dashboard_paiements_volume_periode_export, name='dashboard_paiements_volume_periode_export'),
    path('dashboard-paiements-forfaitaire/periode/', views_dashboard_periode.dashboard_paiements_forfaitaire_periode, name='dashboard_paiements_forfaitaire_periode'),
    path('dashboard-paiements-forfaitaire/periode/export/', views_dashboard_periode.dashboard_paiements_forfaitaire_periode_export, name='dashboard_paiements_forfaitaire_periode_export'),
    path('dashboard-paiements-forfaitaire/calendrier/', views_dashboard_forfaitaire.dashboard_paiements_forfaitaire_calendrier, name='dashboard_paiements_forfaitaire_calendrier'),
    path('dashboard-paiements-forfaitaire/calendrier/impression/', views_dashboard_forfaitaire.dashboard_paiements_forfaitaire_calendrier_impression, name='dashboard_paiements_forfaitaire_calendrier_impression'),
    path('dashboard-frequence-paiements-forfaitaire/', views_dashboard_frequence_forfaitaire.dashboard_frequence_paiements_forfaitaire, name='dashboard_frequence_paiements_forfaitaire'),
    path('dashboard-frequence-paiements-forfaitaire/export/', views_dashboard_frequence_forfaitaire.export_frequence_paiements_forfaitaire_excel, name='export_frequence_paiements_forfaitaire_excel'),
    path('dashboard-recettes-globales/', views_dashboard_recettes.dashboard_recettes_globales, name='dashboard_recettes_globales'),
    path('analyse-couts-ouvrages/', views_analyse_couts_ouvrages.analyse_couts_ouvrages, name='analyse_couts_ouvrages'),
    path('analyse-couts-ouvrages/api/', views_analyse_couts_ouvrages.api_analyse_couts_ouvrages, name='api_analyse_couts_ouvrages'),
    path('analyse-couts-ouvrages/api/detail/', views_analyse_couts_ouvrages.api_analyse_couts_ouvrages_detail, name='api_analyse_couts_ouvrages_detail'),
    path('analyse-couts-communes/', views_analyse_couts_ouvrages.analyse_couts_communes, name='analyse_couts_communes'),
    path('analyse-couts-communes/api/', views_analyse_couts_ouvrages.api_analyse_couts_communes, name='api_analyse_couts_communes'),
    path('analyse-couts-communes/api/detail/', views_analyse_couts_ouvrages.api_analyse_couts_communes_detail, name='api_analyse_couts_communes_detail'),
    path('dashboard-paiements-forfaitaire/impression/', views_dashboard_forfaitaire.dashboard_paiements_forfaitaire_impression, name='dashboard_paiements_forfaitaire_impression'),
    path('dashboard-paiements-forfaitaire/api/communes/', views_dashboard_forfaitaire.api_paiements_forfaitaire_communes_summary, name='api_paiements_forfaitaire_communes_summary'),
    path('api/forfaitaire/explication/', views_dashboard_forfaitaire.api_save_explication_forfaitaire, name='api_save_explication_forfaitaire'),
    path('api/forfaitaire/details/<uuid:ouvrage_id>/', views_dashboard_forfaitaire.api_details_ouvrage_forfaitaire, name='api_details_ouvrage_forfaitaire'),
    path('api/forfaitaire/calendrier/deplacer/', views_dashboard_forfaitaire.api_deplacer_paiements_forfaitaires_calendrier, name='api_deplacer_paiements_forfaitaires_calendrier'),
    path('api/forfaitaire/pointage/', views_dashboard_forfaitaire.api_pointage_paiements_forfaitaires, name='api_pointage_paiements_forfaitaires'),
    path('api/forfaitaire/pointage/annuler/', views_dashboard_forfaitaire.api_annuler_pointage_paiements_forfaitaires, name='api_annuler_pointage_paiements_forfaitaires'),

    # Taxes Communales
    path('etat-taxes-communales/', views_taxe_communale.etat_taxes_communales, name='etat_taxes_communales'),
    path('etat-impot-synthetique/', views_taxe_communale.etat_impot_synthetique, name='etat_impot_synthetique'),
]

if views_saisie_workflow is not None:
    urlpatterns += [
        path('saisie-workflow/', views_saisie_workflow.saisie_comptable_workflow, name='saisie_comptable_workflow'),
        path('saisie-workflow/api/valider/', views_saisie_workflow.api_saisie_comptable_validate, name='api_saisie_comptable_validate'),
        path('saisie-workflow/api/enregistrer/', views_saisie_workflow.api_saisie_comptable_save, name='api_saisie_comptable_save'),
        path('saisie-workflow/api/recents/', views_saisie_workflow.api_saisie_comptable_recent, name='api_saisie_comptable_recent'),
        path('saisie-workflow/api/en-attente/', views_saisie_workflow.api_saisie_comptable_pending, name='api_saisie_comptable_pending'),
        path('saisie-workflow/api/approuver/', views_saisie_workflow.api_saisie_comptable_approve, name='api_saisie_comptable_approve'),
        path('saisie-workflow/api/articles/designations/', views_saisie_workflow.api_saisie_articles_designations, name='api_saisie_articles_designations'),
        path('saisie-workflow/api/articles/destinations/', views_saisie_workflow.api_saisie_articles_destinations, name='api_saisie_articles_destinations'),
        path('saisie-workflow/restes-a-livrer/', views_restes_livrer.restes_a_livrer, name='restes_a_livrer'),
        path('saisie-workflow/restes-a-livrer/api/', views_restes_livrer.api_restes_a_livrer, name='api_restes_a_livrer'),
        path('saisie-workflow/restes-a-livrer/api/livraison/', views_restes_livrer.api_livraison_creer, name='api_livraison_creer'),
        path('saisie-workflow/restes-a-livrer/api/annuler/', views_restes_livrer.api_livraison_annuler, name='api_livraison_annuler'),
    ]

if views_ai_prefill is not None:
    urlpatterns += [
        # Phase 4 - pre-remplissage IA a partir d'un justificatif (scan ou texte)
        path('justificatifs/scan/', views_ai_prefill.justificatif_scan, name='justificatif_scan_prefill'),
    ]

if views_regles_saisie is not None:
    v = views_regles_saisie
    urlpatterns += [
        path('regles-saisie/', v.regles_saisie_list, name='regles_saisie_list'),
        path('regles-saisie/api/list/', v.api_regles_list, name='api_regles_saisie_list'),
        path('regles-saisie/api/fournisseurs-search/', v.api_fournisseurs_search, name='api_regles_saisie_fournisseurs_search'),
        path('regles-saisie/api/creer-pour-compte/', v.api_regle_creer_pour_compte, name='api_regle_saisie_creer_pour_compte'),
        path('regles-saisie/api/peupler-fournisseurs/', v.api_regle_peupler_fournisseurs, name='api_regle_saisie_peupler_fournisseurs'),
        path('regles-saisie/<uuid:regle_id>/', v.regle_saisie_edit, name='regle_saisie_edit'),
        path('regles-saisie/api/<uuid:regle_id>/', v.api_regle_detail, name='api_regle_saisie_detail'),
        path('regles-saisie/api/<uuid:regle_id>/update/', v.api_regle_update, name='api_regle_saisie_update'),
        path('regles-saisie/api/<uuid:regle_id>/preview/', v.api_regle_preview, name='api_regle_saisie_preview'),
        path('regles-saisie/api/<uuid:regle_id>/fournisseurs/', v.api_regle_fournisseurs, name='api_regle_saisie_fournisseurs'),
        # Phase C - integration au formulaire de saisie
        path('regles-saisie/api/pour-compte/', v.api_regle_pour_compte, name='api_regle_saisie_pour_compte'),
        path('regles-saisie/api/composer/', v.api_composer_compte, name='api_regle_saisie_composer'),
        path('regles-saisie/api/autocomplete/', v.api_ac, name='api_regle_saisie_ac'),
    ]
