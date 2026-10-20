from django.urls import path
from .views_pointage import pointage_mensuel

from . import views_saisie_workflow
from . import views_restes_livrer
from . import views_analyse_couts_ouvrages


urlpatterns = [
    path('pointage-mensuel/', pointage_mensuel, name='pointage_mensuel'),
    # Sur compta.hydria.mg, '/' est pris par la redirection vers /accueil/ (urls_saisie) : le lien pointe vers la page
    # servie par l'URLconf principale (apps.accounting.urls), la meme que celle des autres pages du module.
    path('comptabilite/saisie-workflow/', views_saisie_workflow.saisie_comptable_workflow, name='saisie_comptable_workflow'),
    path('pointage-tiers/', views_saisie_workflow.workflow_pointage_tiers, name='workflow_pointage_tiers'),
    path('pointage-tiers/api/valider/', views_saisie_workflow.api_workflow_pointage_tiers, name='api_workflow_pointage_tiers'),
    path('pointage-tiers/api/annuler/', views_saisie_workflow.api_workflow_depointage_tiers, name='api_workflow_depointage_tiers'),
    path('soldes-reels/', views_saisie_workflow.workflow_soldes_reels, name='workflow_soldes_reels'),
    path('soldes-reels/api/save/', views_saisie_workflow.api_workflow_soldes_reels_save, name='api_workflow_soldes_reels_save'),
    path('api/details-solde/', views_saisie_workflow.api_details_solde, name='api_details_solde'),
    path('api/valider/', views_saisie_workflow.api_saisie_comptable_validate, name='api_saisie_comptable_validate'),
    path('api/enregistrer/', views_saisie_workflow.api_saisie_comptable_save, name='api_saisie_comptable_save'),
    path('api/recents/', views_saisie_workflow.api_saisie_comptable_recent, name='api_saisie_comptable_recent'),
    path('api/en-attente/', views_saisie_workflow.api_saisie_comptable_pending, name='api_saisie_comptable_pending'),
    path('api/approuver/', views_saisie_workflow.api_saisie_comptable_approve, name='api_saisie_comptable_approve'),
    path('api/articles/designations/', views_saisie_workflow.api_saisie_articles_designations, name='api_saisie_articles_designations'),
    path('api/articles/destinations/', views_saisie_workflow.api_saisie_articles_destinations, name='api_saisie_articles_destinations'),
    path('restes-a-livrer/', views_restes_livrer.restes_a_livrer, name='restes_a_livrer'),
    path('restes-a-livrer/api/', views_restes_livrer.api_restes_a_livrer, name='api_restes_a_livrer'),
    path('restes-a-livrer/api/livraison/', views_restes_livrer.api_livraison_creer, name='api_livraison_creer'),
    path('restes-a-livrer/api/annuler/', views_restes_livrer.api_livraison_annuler, name='api_livraison_annuler'),
    path('analyse-couts-ouvrages/', views_analyse_couts_ouvrages.analyse_couts_ouvrages, name='analyse_couts_ouvrages'),
    path('analyse-couts-ouvrages/api/', views_analyse_couts_ouvrages.api_analyse_couts_ouvrages, name='api_analyse_couts_ouvrages'),
    path('analyse-couts-ouvrages/api/detail/', views_analyse_couts_ouvrages.api_analyse_couts_ouvrages_detail, name='api_analyse_couts_ouvrages_detail'),
]
