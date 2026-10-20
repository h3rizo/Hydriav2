"""
URL configuration for hydria project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from django.shortcuts import render
from django.views.generic import RedirectView
from importlib.util import find_spec
from . import views
from . import views_structure
from apps.recrutement import views as recrutement_views

def health_check(request):
    """Point de contrôle de santé pour Render"""
    return JsonResponse({
        'status': 'healthy',
        'version': '1.0.0',
        'service': 'hydria-backend'
    })

def api_root(request):
    """Point d'entrée API avec informations sur les endpoints disponibles"""
    return JsonResponse({
        'message': 'Hydria API v1.0',
        'endpoints': {
            'admin': '/admin/',
            'inspections': '/inspections/',
            'billing': '/facturation/',
            'planning': '/plannings/',
            'health': '/health/'
        },
        'docs': '/api/docs/' if settings.DEBUG else None
    })

def offline_page(request):
    """Page affichée quand l'utilisateur est hors ligne"""
    return render(request, 'offline.html')


def _module_exists(module_path):
    try:
        return find_spec(module_path) is not None
    except ModuleNotFoundError:
        return False

urlpatterns = [
    path(
        'favicon.ico',
        RedirectView.as_view(
            url=settings.STATIC_URL + 'images/icons/icons8-vase-94.png',
            permanent=False
        ),
    ),
    path('admin/', admin.site.urls),
    path('health/', health_check, name='health_check'),
    path('api/', api_root, name='api_root'),
    path('offline/', offline_page, name='offline_page'),

    # Apps spécifiques AVANT core (qui capture tout avec '')
    path('plannings/', include('apps.planning.urls')),
    path('facturation/', include('apps.billing.urls')),
    path('stocks/', include('apps.inventory.urls')),
    path('fichiers/', include('apps.filemanager.urls')),
    path('inspections/', include('apps.inspections.urls')),
    path('chantiers/', include(('apps.chantiers.urls', 'chantiers'), namespace='chantiers')),
    path('conversations/', include('apps.messaging.urls')),
    path('feed/', include('apps.feed.urls')),
    path('comptabilite/', include('apps.accounting.urls')),
    path('systeme/', include('apps.system.urls')),
    path('navigation-terrain/', include('apps.navigation_terrain.urls')),
    # Alias global pour compatibilite ancienne: 'profil' sans namespace
    # Permet de resoudre reverse('profil') -> vue profil candidat (accessible via /profil/)
    path('profil/', recrutement_views.profil_candidat, name='profil'),
    # Alias global legacy pour resoudre reverse('fiches_poste_list')
    path('fiches-poste/', RedirectView.as_view(pattern_name='planning:fiche_poste_table', permanent=False), name='fiches_poste_list'),
    # Alias global legacy pour resoudre reverse('workflows_ui_list') sans namespace
    path(
        'workflows-chantier/',
        RedirectView.as_view(pattern_name='chantiers:workflows_ui_list', permanent=False),
        name='workflows_ui_list'
    ),
    # Alias global legacy pour resoudre reverse('representants_avis_evolution_dashboard') sans namespace
    path(
        'representants-avis-evolution/',
        RedirectView.as_view(pattern_name='usagers:representants_avis_evolution_dashboard', permanent=False),
        name='representants_avis_evolution_dashboard'
    ),
    path('usagers/', include('apps.usagers.urls')),
    path('recrutement/', include(('apps.recrutement.urls', 'recrutement'), namespace='recrutement')),

    # Apps géographiques et organisations
    path('geography/', include('apps.geography.urls')),
    path('organisations/', include('apps.organization.urls')),
    path('ouvrages/', include('apps.ouvrages.urls')),  # Temporaire pour les APIs

    # Apps employees avec pattern vide pour ses URLs
    path('', include('apps.employees.urls')),

    # Apps infrastructure avec pattern vide pour ses APIs
    path('', include('apps.infrastructure.urls')),

    # Page d'accueil avec launcher d'applications
    path('accueil/', views.home_launcher, name='home_launcher'),
    # Ancien lien « Saisie compta » (page d'accueil compta en cache) : la page reelle est celle du module comptabilite.
    path('saisie/', RedirectView.as_view(url='/comptabilite/saisie-workflow/', query_string=True, permanent=False)),
    path('client/', views.client_home, name='client_home'),

    # Dashboard principal avec nouveau design
    path('dashboard-principal/', views.home, name='dashboard_principal'),

    # Test chatbot
    path('test-chatbot/', lambda request: render(request, 'test_chatbot.html'), name='test_chatbot'),

    # Dashboard API
    path('api/dashboard/', views.dashboard_api, name='dashboard_api'),
    path('api/dashboard/continuite/', views.dashboard_continuite_api, name='dashboard_continuite_api'),
    path('api/dashboard/structure/', views_structure.dashboard_structure_api, name='dashboard_structure_api'),
    path('api/dashboard/structure/details/', views_structure.dashboard_structure_details_api, name='dashboard_structure_details_api'),
    path('api/dashboard/stats-par-commune/', views.dashboard_stats_par_commune_api, name='dashboard_stats_par_commune_api'),
    path('api/dashboard/export/stats-par-commune/', views.dashboard_export_stats_par_commune_excel, name='dashboard_export_stats_par_commune_excel'),
    path('api/dashboard/details/<str:detail_type>/', views.dashboard_details_api, name='dashboard_details_api'),
    path('api/dashboard/communes/<uuid:commune_id>/ouvrages-stats/', views.dashboard_commune_ouvrages_stats_api, name='dashboard_commune_ouvrages_stats_api'),
    path('api/dashboard/modalites-chart/', views.modalites_payment_chart_api, name='modalites_payment_chart_api'),
    path('api/dashboard/ouvrages-par-annee/', views.ouvrages_par_annee_api, name='ouvrages_par_annee_api'),
    path('api/dashboard/points-eau-par-annee/', views.points_eau_par_annee_api, name='points_eau_par_annee_api'),
    path('api/districts/', views.get_districts_by_region, name='get_districts_by_region'),
    path('api/communes/', views.get_communes_by_district, name='get_communes_by_district'),
    path('api/fokontany/', views.get_fokontany_by_commune, name='get_fokontany_by_commune'),
    path('api/villages/', views.get_villages_by_fokontany, name='get_villages_by_fokontany'),

    # Core EN DERNIER car il capture tout avec le pattern ''
    path('', include('apps.core.urls')),

    # Assistant IA / conversations
    path('assistant/', include('chatbot.urls')),

    # TEMPORAIREMENT COMMENTÉ - Apps non réactivées
    path('api/auth/', include('authentication.urls')),
    # path('', include('apps.planning.urls_hierarchical')),

    # Test direct sans include
    path('test-fichiers/', lambda request: JsonResponse({'status': 'Test direct réussi', 'debug': settings.DEBUG})),

    # Login personnalisé (redirige les clients vers leur point d'eau)
    path('accounts/login/visiteur/', views.visitor_email_login, name='visitor_email_login'),
    path('accounts/login/', views.CustomLoginView.as_view(), name='login'),

    # Authentication URLs (Django de base)
    path('accounts/', include('django.contrib.auth.urls')),
]

# Endpoints mobiles v1 — montés seulement si le module est présent, pour ne pas
# casser tout l'URLconf quand un fichier n'a pas encore été déployé (drift VPS).
if _module_exists('apps.core.urls_mobile_v1'):
    urlpatterns.insert(4, path('api/mobile/v1/', include('apps.core.urls_mobile_v1')))
if _module_exists('apps.accounting.urls_mobile_v1'):
    # Inséré après (donc AVANT dans la liste) le préfixe 'api/mobile/v1/'
    # pour ne pas être masqué par lui.
    urlpatterns.insert(4, path('api/mobile/v1/compta/', include('apps.accounting.urls_mobile_v1')))
if _module_exists('apps.usagers.urls_mobile_v1'):
    # Meme raison : insere avant le prefixe generique 'api/mobile/v1/'.
    urlpatterns.insert(4, path('api/mobile/v1/reunions/', include('apps.usagers.urls_mobile_v1')))
if _module_exists('apps.messaging.urls_mobile_v1'):
    # Meme raison : insere avant le prefixe generique 'api/mobile/v1/'.
    urlpatterns.insert(4, path('api/mobile/v1/messaging/', include('apps.messaging.urls_mobile_v1')))

if _module_exists('apps.planning.urls_mobile_pointage'):
    # Meme raison : insere avant le prefixe generique 'api/mobile/v1/'.
    urlpatterns.insert(4, path('api/mobile/v1/pointage/', include('apps.planning.urls_mobile_pointage')))

if _module_exists('apps.serious_game.urls'):
    urlpatterns.insert(
        24,
        path('serious-game/', include(('apps.serious_game.urls', 'serious_game'), namespace='serious_game'))
    )

if 'notes' in settings.INSTALLED_APPS and _module_exists('notes.urls'):
    urlpatterns.insert(
        34,
        path('notes/', include('notes.urls'))
    )

# Servir les fichiers statiques et media en développement
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
