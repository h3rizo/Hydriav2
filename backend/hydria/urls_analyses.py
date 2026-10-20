from importlib.util import find_spec

from django.conf import settings
from django.contrib import admin
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import include, path
from django.views.generic import RedirectView

from . import views


def _module_exists(module_path):
    try:
        return find_spec(module_path) is not None
    except ModuleNotFoundError:
        return False


@login_required
def analyses_home(request):
    if hasattr(request.user, 'client') and request.user.client:
        messages.error(
            request,
            "Acces reserve aux utilisateurs internes."
        )
        return render(
            request,
            'analyses/forbidden.html',
            status=403,
        )
    return render(request, 'analyses/home.html')


urlpatterns = [
    path('favicon.ico', RedirectView.as_view(
        url='/static/images/icons/icons8-vase-94.png',
        permanent=False,
    )),
    path('admin/', admin.site.urls),
    path('accounts/login/visiteur/', views.visitor_email_login, name='visitor_email_login'),
    path(
        'accounts/login/',
        views.CustomLoginView.as_view(template_name='registration/login_analyses.html'),
        name='login',
    ),
    path('accounts/', include('django.contrib.auth.urls')),
    path('', RedirectView.as_view(pattern_name='home_launcher', permanent=False), name='root_redirect'),
    path('accueil/', analyses_home, name='home_launcher'),
    path('geography/', include('apps.geography.urls')),

    # Memes apps et memes prefixes que le urlconf principal (hydria/urls.py),
    # car base.html (rendu sur TOUTE page, pour tout utilisateur non-client)
    # reference des dizaines de namespaces differents dans son menu. Sans ces
    # inclusions, le moindre lien de menu declenche un NoReverseMatch -> 500.
    path('plannings/', include(('apps.planning.urls', 'planning'), namespace='planning')),
    path('facturation/', include('apps.billing.urls')),
    path('stocks/', include('apps.inventory.urls')),
    path('fichiers/', include('apps.filemanager.urls')),
    path('inspections/', include('apps.inspections.urls')),
    path('chantiers/', include(('apps.chantiers.urls', 'chantiers'), namespace='chantiers')),
    path('conversations/', include('apps.messaging.urls')),
    path('feed/', include('apps.feed.urls')),
    path('comptabilite/', include(('apps.accounting.urls', 'accounting'), namespace='accounting')),
    path('systeme/', include('apps.system.urls')),
    path('usagers/', include('apps.usagers.urls')),
    path('organisations/', include(('apps.organization.urls', 'organization'), namespace='organization')),
    path('ouvrages/', include('apps.ouvrages.urls')),
    path('', include('apps.employees.urls')),
    path('', include('apps.infrastructure.urls')),
    path('assistant/', include('chatbot.urls')),
    path('', include('apps.core.urls')),
]

if 'notes' in settings.INSTALLED_APPS and _module_exists('notes.urls'):
    urlpatterns.insert(
        len(urlpatterns) - 1,
        path('notes/', include('notes.urls')),
    )
