from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render
from django.urls import include, path
from django.views.generic import RedirectView

from . import views
from apps.employees.permissions import has_admin_access


def recrutement_home(request):
    return render(request, 'recrutement/home.html')


@login_required
def recrutement_admin_redirect(request):
    if not has_admin_access(request.user):
        messages.error(
            request,
            "Acces reserve aux utilisateurs d'administration du recrutement."
        )
        return render(
            request,
            'admin/forbidden.html',
            status=403,
        )
    return RedirectView.as_view(
        url='/recrutement/gestion/candidats/',
        permanent=False,
    )(request)


urlpatterns = [
    path('favicon.ico', RedirectView.as_view(
        url='/static/images/icons/icons8-vase-94.png',
        permanent=False,
    )),
    path('accounts/login/visiteur/', views.visitor_email_login, name='visitor_email_login'),
    path(
        'accounts/login/',
        views.CustomLoginView.as_view(template_name='registration/login_recrutement.html'),
        name='login',
    ),
    path('accounts/', include('django.contrib.auth.urls')),
    path('', recrutement_home, name='home_launcher'),
    path('accueil/', recrutement_home, name='recrutement_home'),
    path('admin/', recrutement_admin_redirect, name='recrutement_admin_redirect'),
    path('recrutement/', include(('apps.recrutement.urls', 'recrutement'), namespace='recrutement')),
]
