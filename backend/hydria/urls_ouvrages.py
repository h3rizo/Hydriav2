from django.contrib import admin
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import include, path
from django.views.generic import RedirectView

from . import views
from apps.ouvrages.views import ouvrages_workspace_home


@login_required
def ouvrages_home(request):
    if hasattr(request.user, 'client') and request.user.client:
        messages.error(
            request,
            "Acces reserve aux utilisateurs internes."
        )
        return render(
            request,
            'ouvrages/forbidden.html',
            status=403,
        )
    return ouvrages_workspace_home(request)


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
    path('', ouvrages_home, name='home_launcher'),
    path('accueil/', ouvrages_home, name='ouvrages_home_launcher'),
    path('', include(('apps.ouvrages.urls', 'ouvrages'), namespace='ouvrages')),
    path('', include(('apps.core.urls', 'core'), namespace='core')),
]
