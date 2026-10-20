from django.urls import path
from . import views, views_commandes, views_vehicles, views_stocks_excel, views_transferts, views_purchases, views_transferts_excel, views_stock_summary, views_photos

app_name = 'inventory'

urlpatterns = [
    path('', views.stock_dashboard, name='dashboard'),
    path('produits/', views.products_list, name='products'),
    path('stocks/', views.stocks_list, name='stocks'),
    path('stocks/grand-livre-articles/', views.grand_livre_articles, name='grand_livre_articles'),
    path('stocks/api/inventaires-history/', views.api_stock_inventory_history, name='api_stock_inventory_history'),

    # Export / Import Stocks
    path('stocks/export/', views_stocks_excel.export_stocks_excel, name='export_stocks'),
    path('stocks/template/', views_stocks_excel.template_stocks_excel, name='template_stocks'),
    path('stocks/import/', views_stocks_excel.import_stocks_excel, name='import_stocks'),

    path('achats/', views_purchases.purchases_list, name='purchases'),
    path('achats/consolide/', views.purchases_consolidated, name='purchases_consolidated'),
    path('achats/api/designations-autocomplete/', views.api_designations_autocomplete, name='api_designations_autocomplete'),
    path('achats/api/comptes-by-magasin/<uuid:magasin_id>/', views.api_comptes_by_magasin, name='api_comptes_by_magasin'),
    path('achats/create/', views.purchase_create, name='purchase_create'),
    path('achats/<uuid:purchase_id>/', views.purchase_detail, name='purchase_detail'),
    path('achats/<uuid:purchase_id>/update/', views.purchase_update, name='purchase_update'),
    path('achats/<uuid:purchase_id>/delete/', views.purchase_delete, name='purchase_delete'),
    path('achats/<uuid:purchase_id>/receive/', views.purchase_receive, name='purchase_receive'),

    # Export / Import Excel
    path('achats/export/simple/', views.export_purchases_excel, name='export_purchases'),
    path('achats/export/details/', views.export_purchases_details_excel, name='export_purchases_details'),
    path('achats/template/', views.template_purchases_excel, name='template_purchases'),
    path('achats/import/', views.import_purchases_excel, name='import_purchases'),
    path('achats/details/template/', views.template_purchase_details_excel, name='template_purchase_details'),
    path('achats/details/import/', views.import_purchase_details_excel, name='import_purchase_details'),

    path('mouvements/', views.stock_movements, name='movements'),
    path('api/adjust-stock/<uuid:stock_id>/', views.api_adjust_stock, name='api_adjust_stock'),

    # Workflow calcul commandes
    path('commandes/', views_commandes.calcul_commandes, name='calcul_commandes'),
    path('commandes/api/calculer/', views_commandes.api_calculer_quantites, name='api_calculer_quantites'),
    path('commandes/api/export-excel/', views_commandes.api_export_calcul_excel, name='api_export_calcul_excel'),
    path('commandes/api/generer-bon/', views_commandes.api_generer_bon_commande, name='api_generer_bon'),
    path('commandes/demandes-devis/', views_commandes.demande_devis_list, name='demande_devis_list'),
    path('commandes/demandes-devis/<uuid:demande_id>/', views_commandes.demande_devis_detail, name='demande_devis_detail'),
    path('commandes/demandes-devis/<uuid:demande_id>/export/', views_commandes.export_demande_devis_excel, name='export_demande_devis_excel'),
    path('commandes/demandes-devis/<uuid:demande_id>/delete/', views_commandes.demande_devis_delete, name='demande_devis_delete'),

    # Fiches de stock
    path('fiches-stock/', views.fiche_stock_list, name='fiche_stock_list'),
    path('fiches-stock/<uuid:fiche_id>/delete/', views.fiche_stock_delete, name='fiche_stock_delete'),
    path('fiches-stock/api/inventaire/', views.api_create_inventaire, name='api_fiche_stock_inventaire'),
    path('fiches-stock/api/rapproche/', views.api_mark_rapproche, name='api_fiche_stock_rapproche'),
    path('fiches-stock/api/ouvrages/', views.api_fiche_stock_ouvrages, name='api_fiche_stock_ouvrages'),
    path('fiches-stock/api/ouvrages/<uuid:ouvrage_id>/plannings/', views.api_fiche_stock_plannings_for_ouvrage, name='api_fiche_stock_plannings_for_ouvrage'),
    path('fiches-stock/api/bon-livraison/', views.api_fiche_stock_bon_livraison_save, name='api_fiche_stock_bon_livraison_save'),
    path('fiches-stock/api/retour-terrain/', views.api_fiche_stock_retour_terrain_save, name='api_fiche_stock_retour_terrain_save'),
    path('fiches-stock/api/bon-livraison/<uuid:bon_id>/', views.api_fiche_stock_bon_livraison_detail, name='api_fiche_stock_bon_livraison_detail'),
    path('fiches-stock/api/bon-livraison/<uuid:bon_id>/delete/', views.api_fiche_stock_bon_livraison_delete, name='api_fiche_stock_bon_livraison_delete'),
    path('stock/resume/', views.stock_summary, name='stock_summary'),
    path('stock/resume/api/en-attente/<uuid:designation_id>/', views_stock_summary.api_planning_details_en_attente, name='api_planning_details_en_attente'),
    path('stock/resume/api/livrer/<uuid:detail_id>/', views_stock_summary.api_livrer_planning_detail, name='api_livrer_planning_detail'),
    path('stock/resume/api/photos/search/<uuid:designation_id>/', views_photos.api_search_photos, name='api_search_photos'),
    path('stock/resume/api/photos/save/<uuid:designation_id>/', views_photos.api_save_photo, name='api_save_photo'),
    path('stock/resume/api/photos/upload/<uuid:designation_id>/', views_photos.api_upload_photo, name='api_upload_photo'),
    path('stock/resume/api/photos/clear/<uuid:designation_id>/', views_photos.api_clear_photo, name='api_clear_photo'),
    path('fiche/<uuid:equipement_id>/', views.fiche_stock_equipement, name='fiche_stock_equipement'),

    # Gestion du parc automobile
    path('vehicules/', views_vehicles.gestion_vehicules, name='gestion_vehicules'),
    path('vehicules/carnets-scans/', views_vehicles.vehicules_carnets_scans, name='vehicules_carnets_scans'),
    path('vehicules/carnets-suivi/', views_vehicles.vehicules_carnets_suivi, name='vehicules_carnets_suivi'),
    path('vehicules/<uuid:vehicule_id>/', views_vehicles.details_vehicule, name='details_vehicule'),
    path('vehicules/reparations/<uuid:reparation_id>/', views_vehicles.reparation_planifiee_detail, name='reparation_planifiee_detail'),
    path('vehicules/recap-mensuel/', views_vehicles.recap_mensuel_carburant, name='recap_mensuel_carburant'),
    path('vehicules/carburant/extraction-controle/', views_vehicles.vehicules_carburant_extraction_controle, name='vehicules_carburant_extraction_controle'),
    path('vehicules/pieces/analyses/', views_vehicles.pieces_utilisation_analytics, name='pieces_utilisation_analytics'),

    # APIs véhicules
    path('vehicules/api/create/', views_vehicles.api_vehicule_create, name='api_vehicule_create'),
    path('vehicules/api/<uuid:vehicule_id>/update/', views_vehicles.api_vehicule_update, name='api_vehicule_update'),
    path('vehicules/api/<uuid:vehicule_id>/delete/', views_vehicles.api_vehicule_delete, name='api_vehicule_delete'),
    path('vehicules/api/affectation/create/', views_vehicles.api_affectation_create, name='api_affectation_create'),
    path('vehicules/api/affectation/<uuid:affectation_id>/terminer/', views_vehicles.api_affectation_terminer, name='api_affectation_terminer'),
    path('vehicules/api/affectation/<uuid:affectation_id>/delete/', views_vehicles.api_affectation_delete, name='api_affectation_delete'),
    path('vehicules/api/releve/create/', views_vehicles.api_releve_create, name='api_releve_create'),
    path('vehicules/api/releves/<uuid:releve_id>/delete/', views_vehicles.api_releve_delete, name='api_releve_delete'),
    path('vehicules/api/reparation/create/', views_vehicles.api_reparation_create, name='api_reparation_create'),
    path('vehicules/api/reparations/<uuid:reparation_id>/delete/', views_vehicles.api_reparation_delete, name='api_reparation_delete'),
    path('vehicules/api/reparations/<uuid:reparation_id>/detail/', views_vehicles.api_reparation_planifiee_detail, name='api_reparation_planifiee_detail'),
    path('vehicules/api/pieces/achats/<uuid:purchase_item_id>/delete/', views_vehicles.api_achat_piece_delete, name='api_achat_piece_delete'),
    path('vehicules/api/pieces/utilisations/<uuid:utilisation_id>/delete/', views_vehicles.api_utilisation_piece_delete, name='api_utilisation_piece_delete'),
    path('vehicules/api/pieces/utiliser/', views_vehicles.api_utilisation_piece_create, name='api_utilisation_piece_create'),
    path('vehicules/api/carburant/<uuid:usage_id>/pointer-compta/', views_vehicles.api_carburant_pointer_compta, name='api_carburant_pointer_compta'),
    path('vehicules/api/carburant/cloturer/', views_vehicles.api_cloturer_carburant_mois, name='api_cloturer_carburant_mois'),
    path('vehicules/api/utilisation-perso/create/', views_vehicles.api_utilisation_perso_create, name='api_utilisation_perso_create'),
    path('vehicules/api/utilisation-perso/<uuid:usage_id>/decision/', views_vehicles.api_utilisation_perso_decision, name='api_utilisation_perso_decision'),
    path('vehicules/api/utilisation-perso/<uuid:usage_id>/carburant-avant/', views_vehicles.api_utilisation_perso_carburant_avant, name='api_utilisation_perso_carburant_avant'),
    path('vehicules/api/utilisation-perso/<uuid:usage_id>/retour/', views_vehicles.api_utilisation_perso_retour, name='api_utilisation_perso_retour'),
    path('vehicules/api/utilisation-perso/<uuid:usage_id>/valider-retour/', views_vehicles.api_utilisation_perso_valider_retour, name='api_utilisation_perso_valider_retour'),
    path('vehicules/utilisations-perso/<uuid:usage_id>/pdf/', views_vehicles.utilisation_perso_pdf, name='utilisation_perso_pdf'),

    # Transferts de stock
    path('transferts/', views_transferts.transferts_list, name='transferts_list'),
    path('transferts/api/list/', views_transferts.api_transferts_list, name='api_transferts_list'),
    path('transferts/api/verifier-stock/', views_transferts.api_verifier_stock_transfert, name='api_verifier_stock_transfert'),
    path('transferts/api/create/', views_transferts.api_create_transfert, name='api_create_transfert'),
    path('transferts/api/<uuid:transfert_id>/detail/', views_transferts.api_transfert_detail, name='api_transfert_detail'),
    path('transferts/api/<uuid:transfert_id>/update-status/', views_transferts.api_update_transfert_status, name='api_update_transfert_status'),
    path('transferts/api/<uuid:transfert_id>/delete/', views_transferts.api_delete_transfert, name='api_delete_transfert'),
    path('transferts/<uuid:transfert_id>/bon-livraison/', views_transferts.print_bon_livraison, name='print_bon_livraison'),

    # Export/Import Transferts
    path('transferts/export/', views_transferts_excel.export_transferts_excel, name='export_transferts'),
    path('transferts/export/details/', views_transferts_excel.export_transferts_details_excel, name='export_transferts_details'),
    path('transferts/template/', views_transferts_excel.template_transferts_excel, name='template_transferts'),
    path('transferts/template/items/', views_transferts_excel.template_transferts_items_excel, name='template_transferts_items'),
    path('transferts/import/', views_transferts_excel.import_transferts_excel, name='import_transferts'),
    path('transferts/import/items/', views_transferts_excel.import_transferts_items_excel, name='import_transferts_items'),

    # Bons de commande (nouvelle interface)
    path('purchases/', views_purchases.purchases_list, name='purchases_list'),
    path('purchases/api/list/', views_purchases.api_purchases_list, name='api_purchases_list'),
    path('purchases/api/create/', views_purchases.api_create_purchase, name='api_create_purchase'),
    path('purchases/api/<uuid:purchase_id>/detail/', views_purchases.api_purchase_detail, name='api_purchase_detail'),
    path('purchases/api/<uuid:purchase_id>/update-status/', views_purchases.api_update_purchase_status, name='api_update_purchase_status'),
    path('purchases/api/<uuid:purchase_id>/delete/', views_purchases.api_delete_purchase, name='api_delete_purchase'),
]
