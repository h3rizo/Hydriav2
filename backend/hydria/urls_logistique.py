from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import include, path
from django.views.generic import RedirectView

from . import views
from apps.inventory import views as inventory_views


def health_check(request):
    return JsonResponse({
        'status': 'healthy',
        'version': '1.0.0',
        'service': 'hydria-logistics',
    })


@login_required
def logistique_home(request):
    return inventory_views.stock_dashboard(request)


urlpatterns = [
    path('favicon.ico', RedirectView.as_view(
        url='/static/images/icons/icons8-vase-94.png',
        permanent=False,
    )),
    path('admin/', admin.site.urls),
    path('health/', health_check, name='health_check'),
    path(
        'accounts/login/',
        views.CustomLoginView.as_view(template_name='registration/login.html'),
        name='login',
    ),
    path('accounts/login/visiteur/', views.visitor_email_login, name='visitor_email_login'),
    path('accounts/', include('django.contrib.auth.urls')),
    path('fichiers/', include('apps.filemanager.urls')),
    path('geography/', include('apps.geography.urls')),
    path('organisations/', include('apps.organization.urls')),
    path('ouvrages/', include('apps.ouvrages.urls')),
    path('plannings/', include('apps.planning.urls')),
    path('facturation/', include('apps.billing.urls')),
    path('comptabilite/', include('apps.accounting.urls')),
    path('chantiers/', include(('apps.chantiers.urls', 'chantiers'), namespace='chantiers')),
    path('approvisionnement/', include(('apps.procurement.urls', 'procurement'), namespace='procurement')),
    path('', RedirectView.as_view(pattern_name='home_launcher', permanent=False), name='root_redirect'),
    path('accueil/', logistique_home, name='home_launcher'),
    path('conversations/', include('apps.messaging.urls')),
    path('assistant/', include('chatbot.urls')),
    path('system/', include(('apps.system.urls', 'system'), namespace='system')),
    path('', include(('apps.core.urls', 'core'), namespace='core')),
    path('', include('apps.employees.urls')),
    path('', include('apps.infrastructure.urls')),
    path('', include(('apps.inventory.urls', 'inventory'), namespace='inventory')),
    path('', include(('apps.usagers.urls', 'usagers'), namespace='usagers')),
]
