from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import include, path
from django.views.generic import RedirectView

from . import views


def health_check(request):
    return JsonResponse({
        'status': 'healthy',
        'version': '1.0.0',
        'service': 'hydria-planning',
    })


@login_required
def planning_home(request):
    return render(request, 'planning/planning_home.html')


urlpatterns = [
    path('favicon.ico', RedirectView.as_view(
        url='/static/images/icons/icons8-vase-94.png',
        permanent=False,
    )),
    path('admin/', admin.site.urls),
    path('health/', health_check, name='health_check'),
    path(
        'accounts/login/',
        views.CustomLoginView.as_view(),
        name='login',
    ),
    path('accounts/login/visiteur/', views.visitor_email_login, name='visitor_email_login'),
    path('accounts/', include('django.contrib.auth.urls')),
    path('', RedirectView.as_view(pattern_name='home_launcher', permanent=False), name='root_redirect'),
    path('accueil/', planning_home, name='home_launcher'),
    path('plannings/', include('apps.planning.urls')),
    path('facturation/', include('apps.billing.urls')),
    path('comptabilite/', include(('apps.accounting.urls', 'accounting'), namespace='accounting')),
    path('chantiers/', include(('apps.chantiers.urls', 'chantiers'), namespace='chantiers')),
    path('conversations/', include('apps.messaging.urls')),
    path('systeme/', include('apps.system.urls')),
    path('usagers/', include(('apps.usagers.urls', 'usagers'), namespace='usagers')),
    path('geography/', include(('apps.geography.urls', 'geography'), namespace='geography')),
    path('organisations/', include(('apps.organization.urls', 'organization'), namespace='organization')),
    path('ouvrages/', include(('apps.ouvrages.urls', 'ouvrages'), namespace='ouvrages')),
    path('', include(('apps.infrastructure.urls', 'infrastructure'), namespace='infrastructure')),
    path('assistant/', include(('chatbot.urls', 'chatbot'), namespace='chatbot')),
    # Hydria Academy (quiz + jeu de plateforme 3D) : servi sur planning.hydria.mg,
    # l'ancienne adresse www.hydria.mg/serious-game/ y est redirigee par le middleware.
    path('serious-game/', include(('apps.serious_game.urls', 'serious_game'), namespace='serious_game')),
    path('academy/', RedirectView.as_view(url='/serious-game/', permanent=False), name='academy_shortcut'),
    path('', include(('apps.core.urls', 'core'), namespace='core')),
    path('', include(('apps.employees.urls', 'employees'), namespace='employees')),
]
