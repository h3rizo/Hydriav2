from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render
from django.urls import include, path
from django.views.generic import RedirectView

from . import views
from apps.employees.permissions import has_admin_access


@login_required
def admin_home(request):
    if not has_admin_access(request.user):
        messages.error(
            request,
            "Acces reserve aux utilisateurs d'administration."
        )
        return render(
            request,
            'admin/forbidden.html',
            status=403,
        )
    return render(request, 'admin/home.html')


urlpatterns = [
    path('favicon.ico', RedirectView.as_view(
        url='/static/images/icons/icons8-vase-94.png',
        permanent=False,
    )),
    path('admin/', admin.site.urls),
    path('accounts/login/visiteur/', views.visitor_email_login, name='visitor_email_login'),
    path(
        'accounts/login/',
        views.CustomLoginView.as_view(template_name='registration/login_admin.html'),
        name='login',
    ),
    path('accounts/', include('django.contrib.auth.urls')),
    path('', RedirectView.as_view(pattern_name='home_launcher', permanent=False), name='root_redirect'),
    path('accueil/', admin_home, name='home_launcher'),
    path('', include(('apps.core.urls', 'core'), namespace='core')),
    path('comptabilite/', include(('apps.accounting.urls', 'accounting'), namespace='accounting')),
    path('', include(('apps.billing.urls', 'billing'), namespace='billing')),
    path('chantiers/', include(('apps.chantiers.urls', 'chantiers'), namespace='chantiers')),
    path('conversations/', include(('apps.messaging.urls', 'messaging'), namespace='messaging')),
    path('geography/', include(('apps.geography.urls', 'geography'), namespace='geography')),
    path('', include(('apps.infrastructure.urls', 'infrastructure'), namespace='infrastructure')),
    path('', include(('apps.inventory.urls', 'inventory'), namespace='inventory')),
    path('recrutement/', include(('apps.recrutement.urls', 'recrutement'), namespace='recrutement')),
    path('', include(('apps.employees.urls', 'employees'), namespace='employees')),
    path('plannings/', include(('apps.planning.urls', 'planning'), namespace='planning')),
    path('plannings/', include('apps.planning.urls_crud')),
    path('inspections/', include(('apps.inspections.urls', 'inspections'), namespace='inspections')),
    path('system/', include(('apps.system.urls', 'system'), namespace='system')),
    path('', include(('apps.organization.urls', 'organization'), namespace='organization')),
    path('', include(('apps.usagers.urls', 'usagers'), namespace='usagers')),
    path('ouvrages/', include(('apps.ouvrages.urls', 'ouvrages'), namespace='ouvrages')),
    path('assistant/', include(('chatbot.urls', 'chatbot'), namespace='chatbot')),
]
