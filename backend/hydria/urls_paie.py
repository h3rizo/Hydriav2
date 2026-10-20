from django.contrib import admin
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import include, path
from django.views.generic import RedirectView

from . import views
from apps.employees.permissions import has_paie_home_access


def health_check(request):
    return JsonResponse({
        'status': 'healthy',
        'version': '1.0.0',
        'service': 'hydria-payroll',
    })


@login_required
def paie_home(request):
    if not has_paie_home_access(request.user):
        messages.error(
            request,
            "Acces reserve aux postes autorises sur le volet paie et RH."
        )
        return render(
            request,
            'payroll/paie_forbidden.html',
            status=403,
        )

    return render(request, 'payroll/paie_home.html')


urlpatterns = [
    path('favicon.ico', RedirectView.as_view(
        url='/static/images/icons/compta-icon.png',
        permanent=False,
    )),
    path('admin/', admin.site.urls),
    path('health/', health_check, name='health_check'),
    path(
        'accounts/login/',
        views.CustomLoginView.as_view(template_name='registration/login_compta.html'),
        name='login',
    ),
    path('accounts/login/visiteur/', views.visitor_email_login, name='visitor_email_login'),
    path('accounts/', include('django.contrib.auth.urls')),
    path('', RedirectView.as_view(pattern_name='home_launcher', permanent=False), name='root_redirect'),
    path('accueil/', paie_home, name='home_launcher'),
    path('', include(('apps.core.urls', 'core'), namespace='core')),
    path('', include(('apps.employees.urls', 'employees'), namespace='employees')),
    path('organisations/', include(('apps.organization.urls', 'organization'), namespace='organization')),
]
