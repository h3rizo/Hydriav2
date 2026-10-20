from django.urls import path
from django.views.generic import RedirectView
from . import views
from . import views_import
from . import views_import_ouvrages
from . import views_config_salaire
from . import views_grille_salaire
from . import views_fiches_impression
from . import views_famille
from . import views_verification_paiements
from . import views_verification_paiements_print
from . import views_verification_croisee
from . import views_irsa
from . import views_irsa_impression
from . import views_cnaps_fmfp
from . import views_cnaps_fmfp_export
from . import views_mutuelle
from . import views_mutuelle_export
from . import views_mutuelle_facture
from . import views_iri
from . import views_iri_facture
from . import views_conges
from . import views_conges_matriciel
from . import views_recuperations
from . import views_fiches_poste
from . import views_evaluations
from . import views_evaluations_resultats
from . import views_gardiens
from . import views_bases_diamex
from . import views_contrats_travail
from . import views_grilles_salariales
from . import views_grilles_salariales_cartographie
from . import views_autonomie
from . import views_revalorisation

app_name = 'employees'

urlpatterns = [
    # Page principale
    path('employes/', views.employees_list, name='list'),

    # Import/Export Excel
    path('import-excel/<str:model_name>/', views_import.import_excel_view, name='import_excel'),
    path('excel-template/<str:model_name>/', views_import.download_excel_template, name='excel_template'),
    path('export-excel/<str:model_name>/', views_import.export_excel_data, name='export_excel'),

    # Postes
    path('postes/', views.poste_list, name='poste_list'),
    path('postes/create/', views.poste_create, name='poste_create'),
    path('postes/<uuid:pk>/', views.poste_detail, name='poste_detail'),
    path('postes/<uuid:pk>/update/', views.poste_update, name='poste_update'),
    path('postes/<uuid:pk>/delete/', views.poste_delete, name='poste_delete'),

    # Employés
    path('employes/list/', views.employe_list, name='employe_list'),
    path('employes/organigramme/', views.organigramme_employes, name='organigramme'),
    path('employes/organigramme/fiche/<uuid:pk>/', views.organigramme_employe_fiche_print, name='organigramme_employe_fiche_print'),
    path('employes/organigramme/export-mpikojakoja/', views.export_organigramme_mpikojakoja_excel, name='export_organigramme_mpikojakoja_excel'),
    path('employes/<uuid:pk>/organigramme-ouvrages-modal/', views.organigramme_employe_ouvrages_modal, name='organigramme_employe_ouvrages_modal'),
    path('employes/create/', views.employe_create, name='employe_create'),
    path('employes/<uuid:pk>/', views.employe_detail, name='employe_detail'),
    path('employes/<uuid:pk>/update/', views.employe_update, name='employe_update'),
    path('employes/<uuid:pk>/delete/', views.employe_delete, name='employe_delete'),

    # Hiérarchie
    path('employes/<uuid:employe_id>/hierarchie/create/', views.hierarchie_create, name='hierarchie_create'),
    path('hierarchie/<uuid:pk>/update-dates/', views.hierarchie_update_dates, name='hierarchie_update_dates'),
    path('hierarchie/<uuid:pk>/delete/', views.hierarchie_delete, name='hierarchie_delete'),

    # Ouvrages responsables
    path('employes/<uuid:employe_id>/ouvrages/create/', views.employe_ouvrage_create, name='employe_ouvrage_create'),
    path('employes/<uuid:employe_id>/ouvrages/delete-selected/', views.employe_ouvrages_delete_selected, name='employe_ouvrages_delete_selected'),
    path('employes/<uuid:employe_id>/ouvrages/delete-all/', views.employe_ouvrages_delete_all, name='employe_ouvrages_delete_all'),
    path('ouvrages-responsables/<uuid:pk>/update-dates/', views.employe_ouvrage_update_dates, name='employe_ouvrage_update_dates'),
    path('ouvrages-responsables/<uuid:pk>/delete/', views.employe_ouvrage_delete, name='employe_ouvrage_delete'),

    # Contrats
    path('contrats/', views.contrat_list, name='contrat_list'),
    path('contrats/create/', views.contrat_create, name='contrat_create'),
    path('contrats/<uuid:pk>/', views.contrat_detail, name='contrat_detail'),
    path('contrats/<uuid:pk>/update/', views.contrat_update, name='contrat_update'),
    path('contrats/<uuid:pk>/delete/', views.contrat_delete, name='contrat_delete'),

    # Workflow contrats de travail et avenants
    path('contrats-travail/', views_contrats_travail.contrat_travail_list, name='contrat_travail_list'),
    path('contrats-travail/create/', views_contrats_travail.contrat_travail_create, name='contrat_travail_create'),
    path('contrats-travail/open/<uuid:contrat_id>/', views_contrats_travail.contrat_travail_open_for_contrat, name='contrat_travail_open_for_contrat'),
    path('contrats-travail/modeles-articles/', views_contrats_travail.contrat_article_modele_list, name='contrat_article_modele_list'),
    path('contrats-travail/modeles-articles/<uuid:article_id>/edit/', views_contrats_travail.contrat_article_modele_update, name='contrat_article_modele_update'),
    path('contrats-travail/modeles-articles/<uuid:article_id>/delete/', views_contrats_travail.contrat_article_modele_delete, name='contrat_article_modele_delete'),
    path('contrats-travail/<uuid:contrat_travail_id>/', views_contrats_travail.contrat_travail_detail, name='contrat_travail_detail'),
    path('contrats-travail/<uuid:contrat_travail_id>/print/', views_contrats_travail.contrat_travail_print, name='contrat_travail_print'),
    path('contrats-travail/<uuid:contrat_travail_id>/avenant/create/', views_contrats_travail.avenant_create, name='avenant_create'),
    path('contrats-travail/avenants/<uuid:avenant_id>/', views_contrats_travail.avenant_detail, name='avenant_detail'),
    path('contrats-travail/avenants/<uuid:avenant_id>/print/', views_contrats_travail.avenant_print, name='avenant_print'),

    # NOTE: Grilles de salaire routes moved to views_grille_salaire section below (lines 93-100)
    # Old routes from views.py removed to avoid conflicts

    # Gestion en cascade générale
    path('employes-cascade/', views.employees_cascade, name='employes_cascade'),

    # Positions GPS
    path('positions-gps/', views.positions_gps_list, name='positions_gps_list'),
    path('positions-gps/carte/', views.positions_gps_map, name='positions_gps_map'),
    path('test-gps/', views.test_gps_page, name='test_gps'),
    path('api/capture-gps/', views.capture_gps_position, name='capture_gps_position'),

    # API pour formulaires en cascade
    path('api/postes/', views.api_postes, name='api_postes'),
    path('api/create/', views.api_create, name='api_create'),
    path('api/update/', views.api_update, name='api_update'),
    path('api/delete/', views.api_delete, name='api_delete'),
    path('api/employes/', views.api_employes, name='api_employes'),
    path('api/contrats/<uuid:employe_id>/', views.api_contrats, name='api_contrats'),
    path('api/grilles-salaire/<uuid:contrat_id>/', views.api_grilles_salaire, name='api_grilles_salaire'),
    path('api/calculer-grille-preview/', views.api_calculer_grille_preview, name='api_calculer_grille_preview'),
    path('api/calculer-brut-depuis-net/', views.api_calculer_brut_depuis_net, name='api_calculer_brut_depuis_net'),
    path('api/salaires/<uuid:grille_id>/', views.api_salaires, name='api_salaires'),

    # API pour modales d'édition
    path('api/employes/<uuid:pk>/form/', views.employe_form_api, name='employe_form_api'),
    path('api/employes/<uuid:pk>/update/', views.employe_update_api, name='employe_update_api'),
    path('api/employes/<uuid:pk>/delete/', views.employe_delete_api, name='employe_delete_api'),

    # API pour import local DiameX - liste des fichiers à importer (DOIT être avant les routes avec paramètres)
    path('api/bases-diamex/', views_bases_diamex.api_bases_diamex, name='api_bases_diamex_list'),

    # Bases DiameX (en cascade sous employé)
    path('api/bases-diamex/<uuid:employe_id>/', views.api_bases_diamex, name='api_bases_diamex'),
    path('api/bases-diamex/create/', views.api_base_diamex_create, name='api_base_diamex_create'),
    path('api/bases-diamex/<uuid:pk>/update/', views.api_base_diamex_update, name='api_base_diamex_update'),
    path('api/bases-diamex/<uuid:pk>/delete/', views.api_base_diamex_delete, name='api_base_diamex_delete'),

    # Import/Export Relations Employés-Ouvrages
    path('import-employe-ouvrages/', views_import_ouvrages.import_employe_ouvrages_view, name='import_employe_ouvrages'),
    path('api/import-employe-ouvrages/', views_import_ouvrages.api_import_employe_ouvrages, name='api_import_employe_ouvrages'),
    path('template-excel-employe-ouvrages/', views_import_ouvrages.template_excel_employe_ouvrages, name='template_excel_employe_ouvrages'),
    path('export-employe-ouvrages/', views_import_ouvrages.export_employe_ouvrages, name='export_employe_ouvrages'),

    # Configuration Salaires et IRSA
    path('config/salaire/', views_config_salaire.config_salaire_view, name='config_salaire'),
    path('config/salaire/api/update/', views_config_salaire.api_update_config_salaire, name='api_update_config_salaire'),
    path('config/tranches-irsa/', views_config_salaire.config_tranches_irsa_view, name='config_tranches_irsa'),
    path('config/tranches-irsa/api/list/', views_config_salaire.api_list_tranches_irsa, name='api_list_tranches_irsa'),
    path('config/tranches-irsa/api/create/', views_config_salaire.api_create_tranche_irsa, name='api_create_tranche_irsa'),
    path('config/tranches-irsa/api/<uuid:tranche_id>/update/', views_config_salaire.api_update_tranche_irsa, name='api_update_tranche_irsa'),
    path('config/tranches-irsa/api/<uuid:tranche_id>/delete/', views_config_salaire.api_delete_tranche_irsa, name='api_delete_tranche_irsa'),
    path('config/tranches-irsa/api/test-calcul/', views_config_salaire.api_calculer_irsa_test, name='api_calculer_irsa_test'),
    path('config/tranches-irsa/api/simuler-salaire/', views_config_salaire.api_simuler_salaire_depuis_net, name='api_simuler_salaire_depuis_net'),

    # Grilles de salaire
    path('grilles-salaire/', views_grille_salaire.grille_salaire_list, name='grille_salaire_list'),
    path('grilles-salaire/api/list/', views_grille_salaire.grille_salaire_list, name='api_grille_salaire_list'),
    path('grilles-salaire/api/create/', views_grille_salaire.api_grille_salaire_create, name='api_grille_salaire_create'),
    path('grilles-salaire/api/<uuid:grille_id>/detail/', views_grille_salaire.api_grille_salaire_detail, name='api_grille_salaire_detail'),
    path('grilles-salaire/api/<uuid:grille_id>/update/', views_grille_salaire.api_grille_salaire_update, name='api_grille_salaire_update'),
    path('grilles-salaire/api/<uuid:grille_id>/delete/', views_grille_salaire.api_grille_salaire_delete, name='api_grille_salaire_delete'),
    path('grilles-salaire/api/contrats-actifs/', views_grille_salaire.api_contrats_actifs, name='api_contrats_actifs'),
    path('grilles-salaire/api/calculer-brut/', views_grille_salaire.api_calculer_salaire_brut, name='api_calculer_salaire_brut'),

    # Fiche de paie
    path('fiche-paie/<uuid:salaire_id>/', views.fiche_paie, name='fiche_paie'),
    path('fiche-indemnite-herizo/<uuid:salaire_id>/', views.fiche_indemnite_herizo, name='fiche_indemnite_herizo'),
    path('fiche-indemnite-herizo/grille/<uuid:grille_id>/', views.fiche_indemnite_herizo_depuis_grille, name='fiche_indemnite_herizo_depuis_grille'),
    path('fiches-paie-mensuelles/', views.fiches_paie_mensuelles, name='fiches_paie_mensuelles'),
    path('api/salaires-mensuels/', views.api_salaires_mensuels, name='api_salaires_mensuels'),
    path('api/grille-salaire-detail/<uuid:grille_id>/', views.api_grille_salaire_detail, name='api_grille_salaire_detail'),
    path('api/grilles-employe-mois/<uuid:employe_id>/', views.api_grilles_employe_mois, name='api_grilles_employe_mois'),
    path('api/creer-salaire-depuis-grille/', views.api_creer_salaire_depuis_grille, name='api_creer_salaire_depuis_grille'),
    path('api/salaires/<uuid:salaire_id>/remettre-a-traiter/', views.api_remettre_salaire_a_traiter, name='api_remettre_salaire_a_traiter'),
    path('fiches-paie-impression/', views.fiches_paie_impression, name='fiches_paie_impression'),

    # Impression et export vers DiameX
    path('api/marquer-fiches-imprimees/', views_fiches_impression.api_marquer_fiches_imprimees, name='api_marquer_fiches_imprimees'),

    # Paiements IRSA
    path('paiements-irsa/', views_irsa.paiements_irsa_list, name='paiements_irsa_list'),
    path('api/paiements-irsa-list/', views_irsa.api_paiements_irsa_list, name='api_paiements_irsa_list'),
    path('api/employes-irsa/', views_irsa.api_employes_irsa, name='api_employes_irsa'),
    path('api/creer-paiement-irsa/', views_irsa.api_creer_paiement_irsa, name='api_creer_paiement_irsa'),
    path('api/paiement-irsa/<uuid:paiement_id>/valider/', views_irsa.api_valider_paiement_irsa, name='api_valider_paiement_irsa'),
    path('api/paiement-irsa/<uuid:paiement_id>/supprimer/', views_irsa.api_supprimer_paiement_irsa, name='api_supprimer_paiement_irsa'),
    path('api/paiement-irsa/<uuid:paiement_id>/detail/', views_irsa.api_detail_paiement_irsa, name='api_detail_paiement_irsa'),
    path('paiement-irsa/<uuid:paiement_id>/facture/', views_irsa.generer_facture_irsa, name='generer_facture_irsa'),
    path('api/marquer-irsa-imprime/', views_irsa_impression.api_marquer_irsa_imprime, name='api_marquer_irsa_imprime'),


    # Paiements CNaPS/FMFP
    path('paiements-cnaps-fmfp/', views_cnaps_fmfp.paiements_cnaps_fmfp_list, name='paiements_cnaps_fmfp_list'),
    path('api/paiements-cnaps-fmfp-list/', views_cnaps_fmfp.api_paiements_cnaps_fmfp_list, name='api_paiements_cnaps_fmfp_list'),
    path('api/employes-cnaps-fmfp/', views_cnaps_fmfp.api_employes_cnaps_fmfp, name='api_employes_cnaps_fmfp'),
    path('api/creer-paiement-cnaps-fmfp/', views_cnaps_fmfp.api_creer_paiement_cnaps_fmfp, name='api_creer_paiement_cnaps_fmfp'),
    path('api/paiement-cnaps-fmfp/<uuid:paiement_id>/valider/', views_cnaps_fmfp.api_valider_paiement_cnaps_fmfp, name='api_valider_paiement_cnaps_fmfp'),
    path('api/paiement-cnaps-fmfp/<uuid:paiement_id>/supprimer/', views_cnaps_fmfp.api_supprimer_paiement_cnaps_fmfp, name='api_supprimer_paiement_cnaps_fmfp'),
    path('api/paiement-cnaps-fmfp/<uuid:paiement_id>/detail/', views_cnaps_fmfp.api_detail_paiement_cnaps_fmfp, name='api_detail_paiement_cnaps_fmfp'),
    path('paiement-cnaps-fmfp/<uuid:paiement_id>/facture/', views_cnaps_fmfp.generer_facture_cnaps_fmfp, name='generer_facture_cnaps_fmfp'),
    path('api/paiement-cnaps-fmfp/<uuid:paiement_id>/marquer-imprime/', views_cnaps_fmfp_export.api_marquer_cnaps_fmfp_imprime, name='api_marquer_cnaps_fmfp_imprime'),

    # Paiements Mutuelle Santé (AMIT/OSIEFSoVa)
    path('paiements-mutuelle-sante/', views_mutuelle.paiements_mutuelle_liste, name='paiements_mutuelle_liste'),
    path('api/paiements-mutuelle-sante/', views_mutuelle.api_paiements_mutuelle_list, name='api_paiements_mutuelle_list'),
    path('api/paiements-mutuelle-sante/generer/', views_mutuelle.api_generer_paiement_mutuelle, name='api_generer_paiement_mutuelle'),
    path('api/paiement-mutuelle-sante/<uuid:paiement_id>/detail/', views_mutuelle.api_detail_paiement_mutuelle, name='api_detail_paiement_mutuelle'),
    path('api/paiement-mutuelle-sante/<uuid:paiement_id>/valider/', views_mutuelle.api_valider_paiement_mutuelle, name='api_valider_paiement_mutuelle'),
    path('api/paiement-mutuelle-sante/<uuid:paiement_id>/supprimer/', views_mutuelle.api_supprimer_paiement_mutuelle, name='api_supprimer_paiement_mutuelle'),
    path('paiement-mutuelle-sante/<uuid:paiement_id>/facture/', views_mutuelle.generer_facture_mutuelle, name='generer_facture_mutuelle'),
    path('api/paiement-mutuelle-sante/<uuid:paiement_id>/generer-facture/', views_mutuelle_facture.generer_facture_mutuelle_sante, name='api_generer_facture_mutuelle_sante'),
    path('api/paiement-mutuelle-sante/<uuid:paiement_id>/telecharger/<str:mutuelle_type>/', views_mutuelle_facture.telecharger_facture_mutuelle, name='telecharger_facture_mutuelle'),
    path('api/paiement-mutuelle-sante/<uuid:paiement_id>/exporter-diamex/', views_mutuelle_export.api_exporter_mutuelle_diamex, name='api_exporter_mutuelle_diamex'),
    path('api/paiement-mutuelle-sante/<uuid:paiement_id>/enregistrer-diamex/', views_mutuelle_export.api_enregistrer_diamex_mutuelle, name='api_enregistrer_diamex_mutuelle'),

    # Paiements IRI (Impôt sur les Revenus Intermittents)
    path('paiements-iri/', views_iri.paiements_iri_liste, name='paiements_iri_liste'),
    path('api/paiements-iri/', views_iri.api_paiements_iri_list, name='api_paiements_iri_list'),
    path('api/generer-paiement-iri/', views_iri.api_generer_paiement_iri, name='api_generer_paiement_iri'),
    path('api/paiement-iri/<uuid:paiement_id>/detail/', views_iri.api_paiement_iri_detail, name='api_paiement_iri_detail'),
    path('api/paiement-iri/<uuid:paiement_id>/valider/', views_iri.api_valider_paiement_iri, name='api_valider_paiement_iri'),
    path('api/paiement-iri/<uuid:paiement_id>/supprimer/', views_iri.api_supprimer_paiement_iri, name='api_supprimer_paiement_iri'),
    path('api/paiement-iri/<uuid:paiement_id>/generer-facture/', views_iri_facture.generer_facture_iri, name='api_generer_facture_iri'),
    path('api/paiement-iri/<uuid:paiement_id>/telecharger-facture/', views_iri_facture.telecharger_facture_iri, name='telecharger_facture_iri'),

    # Frais médicaux
    path('frais-medicaux/', views_famille.frais_medicaux_workflow, name='frais_medicaux_workflow'),
    path('frais-medicaux/liste/', views_famille.liste_frais_medicaux, name='liste_frais_medicaux'),
    path('frais-medicaux/api/liste/', views_famille.api_liste_frais_medicaux, name='api_liste_frais_medicaux'),
    path('frais-medicaux/api/calculer/', views_famille.api_calculer_frais_medicaux, name='api_calculer_frais_medicaux'),
    path('frais-medicaux/api/enregistrer/', views_famille.api_enregistrer_frais_medicaux, name='api_enregistrer_frais_medicaux'),
    path('frais-medicaux/api/imprimer/', views_famille.api_imprimer_frais_medicaux, name='api_imprimer_frais_medicaux'),
    path('frais-medicaux/api/definir-montant/', views_famille.api_definir_montant_frais_medicaux, name='api_definir_montant_frais_medicaux'),
    path('frais-medicaux/api/facture/<uuid:frais_id>/', views_famille.api_facture_frais_medicaux, name='api_facture_frais_medicaux'),

    # Frais de scolarité
    path('frais-scolarite/', views_famille.frais_scolarite_workflow, name='frais_scolarite_workflow'),
    path('frais-scolarite/liste/', views_famille.liste_frais_scolarite, name='liste_frais_scolarite'),
    path('frais-scolarite/api/liste/', views_famille.api_liste_frais_scolarite, name='api_liste_frais_scolarite'),
    path('frais-scolarite/api/calculer/', views_famille.api_calculer_frais_scolarite, name='api_calculer_frais_scolarite'),
    path('frais-scolarite/api/enregistrer/', views_famille.api_enregistrer_frais_scolarite, name='api_enregistrer_frais_scolarite'),
    path('frais-scolarite/api/imprimer/', views_famille.api_imprimer_frais_scolarite, name='api_imprimer_frais_scolarite'),

    # Famille employé
    path('api/famille/<uuid:employe_id>/', views_famille.api_famille_employe, name='api_famille_employe'),
    path('api/famille/ajouter/', views_famille.api_ajouter_membre_famille, name='api_ajouter_membre_famille'),
    path('api/famille/<uuid:membre_id>/modifier/', views_famille.api_modifier_membre_famille, name='api_modifier_membre_famille'),
    path('api/famille/<uuid:membre_id>/supprimer/', views_famille.api_supprimer_membre_famille, name='api_supprimer_membre_famille'),

    # Vérification paiements employés
    path('verification-paiements/', views_verification_paiements.verification_paiements_employes, name='verification_paiements'),
    path('verification-paiements/print/', views_verification_paiements_print.verification_paiements_print, name='verification_paiements_print'),
    path('verification-paiements/api/', views_verification_paiements.api_verification_paiements_employes, name='api_verification_paiements'),
    path('verification-paiements/api/modifier/', views_verification_paiements.api_modifier_description_diamex, name='api_modifier_description_diamex'),
    path('verification-paiements/api/base-access-info/', views_verification_paiements.api_get_base_access_info, name='api_base_access_info'),
    path('verification-paiements/api/suggerer-compte/', views_verification_paiements.api_suggerer_compte_cat, name='api_suggerer_compte_cat'),
    path('verification-paiements/api/comptes-employes/', views_verification_paiements.api_comptes_employes, name='api_comptes_employes'),

    # Analyse croisée paiements employés (matrice Employés × Mois × Types)
    path('verification-paiements-croisee/', views_verification_croisee.verification_paiements_croisee, name='verification_paiements_croisee'),
    path('api/verification-paiements-croisee/', views_verification_croisee.api_verification_paiements_croisee, name='api_verification_paiements_croisee'),
    path('api/details-paiements-mois/', views_verification_croisee.api_details_paiements_mois, name='api_details_paiements_mois'),

    # Gestion des congés et permissions
    # Types de permissions (CRUD)
    path('types-permissions/', views_conges.types_permissions_list, name='types_permissions_list'),
    path('api/types-permissions/list/', views_conges.api_types_permissions_list, name='api_types_permissions_list'),
    path('api/types-permissions/create/', views_conges.api_type_permission_create, name='api_type_permission_create'),
    path('api/types-permissions/<uuid:type_id>/update/', views_conges.api_type_permission_update, name='api_type_permission_update'),
    path('api/types-permissions/<uuid:type_id>/delete/', views_conges.api_type_permission_delete, name='api_type_permission_delete'),
    path('jours-feries/', views_conges.jours_feries_list, name='jours_feries_list'),
    path('api/jours-feries/list/', views_conges.api_jours_feries_list, name='api_jours_feries_list'),
    path('api/jours-feries/create/', views_conges.api_jour_ferie_create, name='api_jour_ferie_create'),
    path('api/jours-feries/<uuid:jour_ferie_id>/update/', views_conges.api_jour_ferie_update, name='api_jour_ferie_update'),
    path('api/jours-feries/<uuid:jour_ferie_id>/delete/', views_conges.api_jour_ferie_delete, name='api_jour_ferie_delete'),

    # Demandes de congés (workflow)
    path('demandes-conges/', views_conges.demandes_conges_list, name='demandes_conges_list'),
    path('api/demandes-conges/list/', views_conges.api_demandes_conges_list, name='api_demandes_conges_list'),
    path('api/demandes-conges/jours-feries-planning/', views_conges.api_jours_feries_planning_employe, name='api_jours_feries_planning_employe'),
    path('api/demandes-conges/create/', views_conges.api_demande_conge_create, name='api_demande_conge_create'),
    path('api/demandes-conges/<uuid:demande_id>/detail/', views_conges.api_demande_conge_detail, name='api_demande_conge_detail'),
    path('api/demandes-conges/<uuid:demande_id>/soumettre/', views_conges.api_demande_conge_soumettre, name='api_demande_conge_soumettre'),
    path('api/demandes-conges/<uuid:demande_id>/valider-chef/', views_conges.api_demande_conge_valider_chef, name='api_demande_conge_valider_chef'),
    path('api/demandes-conges/<uuid:demande_id>/valider-directeur/', views_conges.api_demande_conge_valider_directeur, name='api_demande_conge_valider_directeur'),
    path('api/demandes-conges/<uuid:demande_id>/refuser/', views_conges.api_demande_conge_refuser, name='api_demande_conge_refuser'),
    path('api/demandes-conges/<uuid:demande_id>/inscrire-planning/', views_conges.api_demande_conge_inscrire_planning, name='api_demande_conge_inscrire_planning'),
    path('api/demandes-conges/<uuid:demande_id>/annuler/', views_conges.api_demande_conge_annuler, name='api_demande_conge_annuler'),
    path('api/demandes-conges/<uuid:demande_id>/reporter/', views_conges.api_demande_conge_reporter, name='api_demande_conge_reporter'),

    # Suivi des congés
    path('suivi-conges/', views_conges.suivi_conges, name='suivi_conges'),
    path('api/suivi-conges/', views_conges.api_suivi_conges, name='api_suivi_conges'),
    path('suivi-conges-matriciel/', views_conges_matriciel.suivi_conges_matriciel, name='suivi_conges_matriciel'),
    path('api/conges-matriciel/', views_conges_matriciel.api_conges_matriciel, name='api_conges_matriciel'),

    # APIs pour gestion interactive des congés depuis le calendrier matriciel
    path('api/creer-demande-conge-rapide/', views_conges_matriciel.api_creer_demande_conge_rapide, name='api_creer_demande_conge_rapide'),
    path('api/modifier-conge-matriciel/', views_conges_matriciel.api_modifier_conge_matriciel, name='api_modifier_conge_matriciel'),
    path('api/supprimer-conge-matriciel/', views_conges_matriciel.api_supprimer_conge_matriciel, name='api_supprimer_conge_matriciel'),
    path('api/details-planning/<uuid:employe_id>/<str:date_str>/', views_conges_matriciel.api_details_planning, name='api_details_planning'),

    # Paiement congés non pris (exceptionnel)
    path('api/payer-conges-non-pris/', views_conges.api_payer_conges_non_pris, name='api_payer_conges_non_pris'),

    # Gestion des récupérations
    path('recuperations/', views_recuperations.liste_recuperations, name='liste_recuperations'),
    path('api/recuperations/list/', views_recuperations.api_recuperations_list, name='api_recuperations_list'),
    path('api/recuperations/<uuid:employe_id>/dates-recuperables/', views_recuperations.api_dates_recuperables, name='api_dates_recuperables'),
    path('api/recuperations/creer/', views_recuperations.api_creer_recuperation, name='api_creer_recuperation'),
    path('api/recuperations/<uuid:recuperation_id>/demander/', views_recuperations.api_demander_recuperation, name='api_demander_recuperation'),
    path('api/recuperations/<uuid:recuperation_id>/valider/', views_recuperations.api_valider_recuperation, name='api_valider_recuperation'),
    path('api/recuperations/<uuid:employe_id>/solde/', views_recuperations.api_solde_recuperations, name='api_solde_recuperations'),

    # Gestion des gardiens (rotations et congés spéciaux)
    path('gardiens/', views_gardiens.gestion_gardiens, name='gestion_gardiens'),
    path('gardiens/impression/', views_gardiens.impression_calendrier_gardiens, name='impression_calendrier_gardiens'),
    path('api/gardiens/generer-rotations/', views_gardiens.api_generer_rotations, name='api_gardiens_generer_rotations'),
    path('api/gardiens/creer-conge/', views_gardiens.api_conge_gardien, name='api_gardiens_creer_conge'),
    path('api/gardiens/recalculer-mois/', views_gardiens.api_recalculer_mois_gardiens, name='api_gardiens_recalculer_mois'),
    path('api/gardiens/rotations/', views_gardiens.api_rotations_liste, name='api_gardiens_rotations_liste'),
    path('api/gardiens/heures-supplementaires/', views_gardiens.api_heures_supplementaires, name='api_gardiens_heures_supplementaires'),

    # Gestion des fiches de poste
    path('fiches-poste/', RedirectView.as_view(pattern_name='planning:fiche_poste_table', permanent=False), name='fiches_poste_redirect'),
    # Alias legacy pour compatibilite templates existants
    path('fiches-poste/', RedirectView.as_view(pattern_name='planning:fiche_poste_table', permanent=False), name='fiches_poste_list'),
    path('api/fiches-poste/', views_fiches_poste.api_fiches_poste_list, name='api_fiches_poste_list'),
    path('api/fiches-poste/<uuid:poste_id>/', views_fiches_poste.api_fiches_poste_by_poste, name='api_fiches_poste_by_poste'),
    path('api/fiches-poste/create/', views_fiches_poste.api_fiche_poste_create, name='api_fiche_poste_create'),
    path('api/fiches-poste/<uuid:fiche_id>/update/', views_fiches_poste.api_fiche_poste_update, name='api_fiche_poste_update'),
    path('api/fiches-poste/<uuid:fiche_id>/delete/', views_fiches_poste.api_fiche_poste_delete, name='api_fiche_poste_delete'),

    # Workflow d'évaluation des employés
    path('employes/evaluations/', views_evaluations.evaluations_list, name='evaluations_list'),
    path('employes/evaluations/rapport/', views_evaluations.evaluation_rapport, name='evaluation_rapport'),
    path('employes/evaluations/creer/', views_evaluations.evaluation_creer, name='evaluation_creer'),
    path('employes/evaluations/<uuid:evaluation_id>/', views_evaluations.evaluation_detail, name='evaluation_detail'),
    path('employes/api/evaluations/list/', views_evaluations.api_evaluations_list, name='api_evaluations_list'),
    path('employes/api/evaluations/rapport/', views_evaluations.api_evaluation_rapport_data, name='api_evaluation_rapport_data'),
    path('employes/api/evaluations/<uuid:evaluation_id>/detail/', views_evaluations.api_evaluation_detail, name='api_evaluation_detail'),
    path('employes/api/evaluations/create/', views_evaluations.api_evaluation_create, name='api_evaluation_create'),
    path('employes/api/evaluations/detail/<uuid:detail_id>/update/', views_evaluations.api_evaluation_update_detail, name='api_evaluation_update_detail'),
    path('employes/api/evaluations/detail/<uuid:detail_id>/delete/', views_evaluations.api_evaluation_delete_detail, name='api_evaluation_delete_detail'),
    path('employes/api/evaluations/<uuid:evaluation_id>/priorites/', views_evaluations.api_evaluation_update_priorites, name='api_evaluation_update_priorites'),
    path('employes/api/evaluations/<uuid:evaluation_id>/developpement/', views_evaluations.api_evaluation_update_developpement, name='api_evaluation_update_developpement'),
    path('employes/api/evaluations/<uuid:evaluation_id>/terminer/', views_evaluations.api_evaluation_terminer, name='api_evaluation_terminer'),
    path('employes/api/evaluations/<uuid:evaluation_id>/delete/', views_evaluations.api_evaluation_delete, name='api_evaluation_delete'),
    path('employes/api/evaluations/<uuid:employe_id>/historique/', views_evaluations.api_evaluations_historique, name='api_evaluations_historique'),

    # Évaluation par résultats des employés
    path('employes/evaluations-resultats/', views_evaluations_resultats.evaluations_resultats_list, name='evaluations_resultats_list'),
    path('employes/api/evaluations-resultats/', views_evaluations_resultats.api_evaluations_resultats_list, name='api_evaluations_resultats_list'),
    path('employes/api/evaluations-resultats/create/', views_evaluations_resultats.api_evaluation_resultats_create, name='api_evaluation_resultats_create'),
    path('employes/api/evaluations-resultats/<uuid:evaluation_id>/', views_evaluations_resultats.api_evaluation_resultats_detail, name='api_evaluation_resultats_detail'),
    path('employes/api/evaluations-resultats/<uuid:evaluation_id>/update/', views_evaluations_resultats.api_evaluation_resultats_update, name='api_evaluation_resultats_update'),
    path('employes/api/evaluations-resultats/<uuid:evaluation_id>/delete/', views_evaluations_resultats.api_evaluation_resultats_delete, name='api_evaluation_resultats_delete'),
    # Alias de compatibilité pour les essais déjà faits sans préfixe /employes
    path('evaluations-resultats/', views_evaluations_resultats.evaluations_resultats_list),
    path('api/evaluations-resultats/', views_evaluations_resultats.api_evaluations_resultats_list),
    path('api/evaluations-resultats/create/', views_evaluations_resultats.api_evaluation_resultats_create),
    path('api/evaluations-resultats/<uuid:evaluation_id>/', views_evaluations_resultats.api_evaluation_resultats_detail),
    path('api/evaluations-resultats/<uuid:evaluation_id>/update/', views_evaluations_resultats.api_evaluation_resultats_update),
    path('api/evaluations-resultats/<uuid:evaluation_id>/delete/', views_evaluations_resultats.api_evaluation_resultats_delete),

    # Grilles salariales de reference
    path('employes/grilles-salariales/', views_grilles_salariales.grilles_salariales_list, name='grilles_salariales_list'),
    path('employes/api/grilles-salariales/list/', views_grilles_salariales.api_grilles_salariales_list, name='api_grilles_salariales_list'),
    path('employes/api/grilles-salariales/create/', views_grilles_salariales.api_grilles_salariales_create, name='api_grilles_salariales_create'),
    path('employes/api/grilles-salariales/<uuid:grille_id>/update/', views_grilles_salariales.api_grilles_salariales_update, name='api_grilles_salariales_update'),
    path('employes/api/grilles-salariales/<uuid:grille_id>/delete/', views_grilles_salariales.api_grilles_salariales_delete, name='api_grilles_salariales_delete'),
    path('employes/grilles-salariales/export/', views_grilles_salariales.export_grilles_salariales_excel, name='export_grilles_salariales_excel'),
    path('employes/grilles-salariales/template/', views_grilles_salariales.export_grilles_salariales_template_excel, name='export_grilles_salariales_template_excel'),
    path('employes/api/grilles-salariales/import/', views_grilles_salariales.import_grilles_salariales_excel, name='import_grilles_salariales_excel'),
    path('employes/api/grilles-salariales/cartographie/', views_grilles_salariales_cartographie.api_grilles_salariales_cartographie, name='api_grilles_salariales_cartographie'),
    path('employes/api/grilles-salariales/<uuid:grille_id>/fourchette/', views_grilles_salariales_cartographie.api_grille_modifier_fourchette, name='api_grille_modifier_fourchette'),
    path('employes/api/employes/<uuid:employe_id>/quotite/', views_grilles_salariales_cartographie.api_employe_quotite, name='api_employe_quotite'),
    path('employes/api/employes/<uuid:employe_id>/date-sortie-junior/', views_grilles_salariales_cartographie.api_employe_date_sortie_junior, name='api_employe_date_sortie_junior'),
    # Templates de grilles salariales
    path('employes/api/templates/list/', views_grilles_salariales.api_templates_list, name='api_templates_list'),
    path('employes/api/templates/create/', views_grilles_salariales.api_templates_create, name='api_templates_create'),
    path('employes/templates/export/', views_grilles_salariales.export_templates_excel, name='export_templates_excel'),
    path('employes/api/templates/import/', views_grilles_salariales.import_templates_excel, name='import_templates_excel'),

    # Grille salariale par stade d'autonomie
    path('employes/grilles-autonomie/', views_autonomie.grilles_autonomie_home, name='grilles_autonomie_home'),
    # Stades d'autonomie
    path('employes/api/stades-autonomie/list/', views_autonomie.api_stades_list, name='api_stades_autonomie_list'),
    path('employes/api/stades-autonomie/create/', views_autonomie.api_stades_create, name='api_stades_autonomie_create'),
    path('employes/api/stades-autonomie/<uuid:stade_id>/update/', views_autonomie.api_stades_update, name='api_stades_autonomie_update'),
    path('employes/api/stades-autonomie/<uuid:stade_id>/delete/', views_autonomie.api_stades_delete, name='api_stades_autonomie_delete'),
    path('employes/api/stades-autonomie/reorder/', views_autonomie.api_stades_reorder, name='api_stades_autonomie_reorder'),
    # Grilles par autonomie
    path('employes/api/grilles-autonomie/list/', views_autonomie.api_grilles_autonomie_list, name='api_grilles_autonomie_list'),
    path('employes/api/grilles-autonomie/create/', views_autonomie.api_grilles_autonomie_create, name='api_grilles_autonomie_create'),
    path('employes/api/grilles-autonomie/<uuid:grille_id>/update/', views_autonomie.api_grilles_autonomie_update, name='api_grilles_autonomie_update'),
    path('employes/api/grilles-autonomie/<uuid:grille_id>/delete/', views_autonomie.api_grilles_autonomie_delete, name='api_grilles_autonomie_delete'),
    path('employes/api/grilles-autonomie/<uuid:grille_id>/soumettre/', views_autonomie.api_grilles_autonomie_soumettre, name='api_grilles_autonomie_soumettre'),
    path('employes/api/grilles-autonomie/<uuid:grille_id>/valider/', views_autonomie.api_grilles_autonomie_valider, name='api_grilles_autonomie_valider'),
    path('employes/api/grilles-autonomie/<uuid:grille_id>/rejeter/', views_autonomie.api_grilles_autonomie_rejeter, name='api_grilles_autonomie_rejeter'),
    path('employes/api/grilles-autonomie/<uuid:grille_id>/appliquer/', views_autonomie.api_grilles_autonomie_appliquer, name='api_grilles_autonomie_appliquer'),
    path('employes/api/grilles-autonomie/soumettre-lot/', views_autonomie.api_grilles_autonomie_soumettre_lot, name='api_grilles_autonomie_soumettre_lot'),
    # Vue graphique
    path('employes/api/grilles-autonomie/graphique/', views_autonomie.api_graphique_donnees, name='api_graphique_autonomie_donnees'),
    path('employes/api/grilles-autonomie/positionnement/', views_autonomie.api_positionnement_employes, name='api_positionnement_employes_autonomie'),
    path('employes/api/grilles-autonomie/graphique/save/', views_autonomie.api_graphique_save, name='api_graphique_autonomie_save'),
    # Regles de primes
    path('employes/api/regles-primes/list/', views_autonomie.api_regles_primes_list, name='api_regles_primes_list'),
    path('employes/api/regles-primes/create/', views_autonomie.api_regles_primes_create, name='api_regles_primes_create'),
    path('employes/api/regles-primes/<uuid:regle_id>/update/', views_autonomie.api_regles_primes_update, name='api_regles_primes_update'),
    path('employes/api/regles-primes/<uuid:regle_id>/delete/', views_autonomie.api_regles_primes_delete, name='api_regles_primes_delete'),
    path('employes/api/regles-primes/<uuid:regle_id>/soumettre/', views_autonomie.api_regles_primes_soumettre, name='api_regles_primes_soumettre'),
    path('employes/api/regles-primes/<uuid:regle_id>/valider/', views_autonomie.api_regles_primes_valider, name='api_regles_primes_valider'),
    path('employes/api/regles-primes/<uuid:regle_id>/rejeter/', views_autonomie.api_regles_primes_rejeter, name='api_regles_primes_rejeter'),
    # Majorations territoriales
    path('employes/api/majorations-territoriales/list/', views_autonomie.api_majorations_list, name='api_majorations_territoriales_list'),
    path('employes/api/majorations-territoriales/create/', views_autonomie.api_majorations_create, name='api_majorations_territoriales_create'),
    path('employes/api/majorations-territoriales/<uuid:majoration_id>/update/', views_autonomie.api_majorations_update, name='api_majorations_territoriales_update'),
    path('employes/api/majorations-territoriales/<uuid:majoration_id>/delete/', views_autonomie.api_majorations_delete, name='api_majorations_territoriales_delete'),
    # Controles de coherence
    path('employes/api/grilles-autonomie/controles-coherence/', views_autonomie.api_controles_coherence, name='api_controles_coherence'),
    # Simulateur de remuneration
    path('employes/api/simulateur-remuneration/donnees-employe/<uuid:employe_id>/', views_autonomie.api_simulateur_donnees_employe, name='api_simulateur_donnees_employe'),
    path('employes/api/simulateur-remuneration/calculer/', views_autonomie.api_simulateur_calculer, name='api_simulateur_calculer'),
    path('employes/api/simulateur-remuneration/sauvegarder/', views_autonomie.api_simulateur_sauvegarder, name='api_simulateur_sauvegarder'),

    # Revalorisations salariales
    path('employes/revalorisations/', views_revalorisation.revalorisations_list, name='revalorisations_list'),
    path('employes/api/revalorisations/list/', views_revalorisation.api_revalorisations_list, name='api_revalorisations_list'),
    path('employes/api/revalorisations/save/', views_revalorisation.api_revalorisation_save, name='api_revalorisation_save'),
    path('employes/api/revalorisations/update-employe/', views_revalorisation.api_revalorisation_update_employe, name='api_revalorisation_update_employe'),
    path('employes/api/revalorisations/<uuid:reval_id>/<str:action>/', views_revalorisation.api_revalorisation_action, name='api_revalorisation_action'),
    path('employes/api/revalorisations/history/<uuid:employe_id>/', views_revalorisation.api_revalorisation_history, name='api_revalorisation_history'),
]
