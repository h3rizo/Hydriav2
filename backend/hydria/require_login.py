"""
Connexion obligatoire sur tout le site (domaine principal et sous-domaines), sauf liste blanche.

Contexte : un grand nombre de vues n'ont aucun décorateur d'authentification et répondaient
200 à un visiteur anonyme (exports Excel, API JSON, listes). Cette règle unique ferme l'accès par
défaut ; une vue qui oublie son décorateur n'est plus publique.

Modes (réglage REQUIRE_LOGIN_MODE, variable d'environnement du même nom) :
  - off     : désactivé
  - log     : n'empêche rien ; journalise chaque accès anonyme qui serait bloqué (défaut)
  - enforce : redirige vers la connexion (pages) ou répond 401 JSON (API / AJAX)

Passent toujours : utilisateur connecté, requêtes OPTIONS, requêtes portant un en-tête
Authorization (les vues par jeton - widgets, apps mobiles - valident elles-mêmes le jeton),
et les chemins de la liste blanche ci-dessous.
"""
import logging

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils.http import urlencode

logger = logging.getLogger('hydria.require_login')

# Chemins publics par conception (connexion, ressources statiques, santé, PWA, webhooks).
PUBLIC_PREFIXES = (
    '/static/',
    '/accounts/',            # connexion, connexion visiteur, déconnexion
    '/admin/',               # l'admin Django gère sa propre connexion
    '/api/auth/',            # csrf / statut de session
    '/api/set-language/',    # bascule de langue depuis la page de connexion
    '/i18n/',
    '/widget/api/login/',    # échange identifiant -> jeton pour les widgets
    '/widget/api/ping/',
    '/facturation/api/paiement/mvola/callback/',  # webhook MVola (appelé par MVola, sans session)
    '/api/mobile/v1/auth/',  # connexion / rafraîchissement du jeton des applications mobiles
    '/mobile/api/login/',    # ancienne connexion mobile (échange identifiant -> jeton)
    '/recrutement/inscription/',  # inscription des candidats (pas encore de compte)
    '/usagers/reseau/magic/',     # lien de connexion magique (le jeton est vérifié par la vue)
)
PUBLIC_EXACT = frozenset({
    '/health/', '/offline/', '/favicon.ico', '/robots.txt',
    '/widget/manifest.json', '/widget/sw.js', '/manifest.json', '/sw.js',
})


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    return (forwarded.split(',')[0].strip() if forwarded else request.META.get('REMOTE_ADDR', '')) or '-'


def _expects_json(request):
    return (
        request.path.startswith('/api/')
        or '/api/' in request.path
        or 'application/json' in request.headers.get('Accept', '')
        or request.headers.get('X-Requested-With', '') == 'XMLHttpRequest'
    )


class RequireLoginMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.mode = str(getattr(settings, 'REQUIRE_LOGIN_MODE', 'log') or 'log').strip().lower()

    def _is_exempt(self, request):
        if request.method == 'OPTIONS':
            return True
        path = request.path
        if path in PUBLIC_EXACT or path.startswith(PUBLIC_PREFIXES):
            return True
        # Page d'accueil publique du sous-domaine recrutement (posé par SubdomainUrlRoutingMiddleware)
        if path == '/' and getattr(request, 'is_recruitment_subdomain', False):
            return True
        # Les vues par jeton valident elles-mêmes l'en-tête Authorization (401 si invalide).
        return bool(request.headers.get('Authorization'))

    def __call__(self, request):
        if self.mode == 'off':
            return self.get_response(request)
        user = getattr(request, 'user', None)
        if (user is not None and user.is_authenticated) or self._is_exempt(request):
            return self.get_response(request)

        # Jamais la query string : elle peut contenir des jetons ou des données personnelles.
        logger.warning(
            '[REQUIRE_LOGIN] mode=%s host=%s method=%s path=%s ip=%s ua=%s',
            self.mode, request.get_host(), request.method, request.path,
            _client_ip(request), (request.META.get('HTTP_USER_AGENT', '') or '-')[:60],
        )
        if self.mode != 'enforce':
            return self.get_response(request)

        if _expects_json(request):
            return JsonResponse({'success': False, 'error': 'Authentification requise'}, status=401)
        login_url = getattr(settings, 'LOGIN_URL', '/accounts/login/')
        return redirect(f"{login_url}?{urlencode({'next': request.get_full_path()})}")
