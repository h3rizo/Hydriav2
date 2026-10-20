"""
Vue d'echec CSRF (settings.CSRF_FAILURE_VIEW).

Un jeton CSRF perime (page restee ouverte pendant une connexion dans un autre
onglet, page servie hors ligne par le service worker...) donnait la page brute
« Interdit (403) », sans issue pour l'utilisateur. Selon le type de requete :
  - formulaire de connexion -> redirection vers la page de connexion
    (GET = jeton neuf) avec un message expliquant qu'il faut reessayer ;
  - appel fetch/API -> 403 JSON exploitable par le JavaScript ;
  - sinon -> page 403 standard de Django.
"""
import logging

from django.contrib import messages
from django.http import HttpResponseRedirect, JsonResponse
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.csrf import csrf_failure as django_csrf_failure

logger = logging.getLogger('django.security.csrf')

MESSAGE_SESSION_EXPIREE = (
    "Votre session a expiré ou la page était trop ancienne. "
    "Merci de réessayer."
)


def _est_appel_api(request):
    """Appel fetch/XHR ou endpoint JSON : ne jamais rediriger vers du HTML."""
    return (
        request.path.startswith('/api/')
        or '/api/' in request.path
        or request.headers.get('x-requested-with') == 'XMLHttpRequest'
        or 'application/json' in request.headers.get('accept', '')
        or request.content_type == 'application/json'
    )


def _doit_rediriger(request):
    """
    Decide si un echec CSRF sur une requete de formulaire navigateur doit
    rediriger (GET de la meme page, jeton neuf, message) plutot qu'afficher
    la page 403 standard.

    Liste blanche : pages de connexion uniquement (2-3 champs, rien a perdre).
    Ailleurs, la page 403 standard laisse le bouton « Retour » du navigateur
    qui conserve la saisie d'un long formulaire.
    """
    return request.method == 'POST' and request.path in (
        reverse('login'),
        reverse('visitor_email_login'),
    )


def _cible_redirection(request):
    """Le formulaire visiteur poste sur sa propre URL : on revient a la page de connexion."""
    if request.path == reverse('visitor_email_login'):
        return reverse('login')
    return request.get_full_path()  # conserve ?next=...


def csrf_failure(request, reason=""):
    logger.warning(
        "Echec CSRF (%s) : %s %s", reason, request.method, request.get_full_path()
    )

    if _est_appel_api(request):
        return JsonResponse(
            {'success': False, 'error': 'csrf', 'message': MESSAGE_SESSION_EXPIREE},
            status=403,
        )

    if _doit_rediriger(request):
        cible = _cible_redirection(request)
        if url_has_allowed_host_and_scheme(cible, allowed_hosts={request.get_host()}):
            messages.warning(request, MESSAGE_SESSION_EXPIREE)
            return HttpResponseRedirect(cible)

    return django_csrf_failure(request, reason)
