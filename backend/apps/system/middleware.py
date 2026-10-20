import json
from django.utils import timezone
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import reverse
from apps.system.models import PageVisit, UserPresence
from apps.system.request_context import set_current_user, clear_current_user
from apps.employees.permissions import is_visiteur

class TrackingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        from hydria.middleware import MockUser
        from apps.core.contributions import definir_auteur
        if not user or not getattr(user, 'is_authenticated', False) or isinstance(user, MockUser):
            set_current_user(None)
            definir_auteur(None)
        else:
            set_current_user(user)
            definir_auteur(user, 'web')  # remplace par 'mobile' si l'authentification se fait par jeton

        try:
            response = self.get_response(request)
        finally:
            clear_current_user()
            definir_auteur(None)
        
        # On ne logue que les requêtes GET réussies
        # On exclut les assets statiques, les médias, l'admin et les appels API de tracking eux-mêmes
        if request.method == 'GET' and response.status_code == 200:
            path = request.path
            
            # Liste des préfixes à exclure
            excluded_prefixes = [
                '/static/', 
                '/media/', 
                '/admin/', 
                '/api/system/presence/',
                '/__debug__/',
                '/favicon.ico'
            ]
            
            if not any(path.startswith(prefix) for prefix in excluded_prefixes):
                # On ne logue pas si c'est une requête AJAX/Fetch pour éviter de polluer les visites avec des appels de données
                # Sauf si on veut vraiment tout traquer. Le user a demandé "visites des pages".
                # En Nuxt, les changements de pages sont souvent des appels API + navigation côté client.
                # Si c'est du Nuxt, on devrait peut-être traquer côté frontend via un plugin.
                # Mais le user demande une table qui enregistre les visites.
                
                is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', '')
                
                # Pour Nuxt, on va préférer un log explicite via API ou alors on logue tout ce qui n'est pas un asset
                if not is_ajax:
                    self.log_visit(request)
        
        return response

    def log_visit(self, request):
        user = request.user if hasattr(request, 'user') and request.user.is_authenticated else None
        
        # On ignore le MockUser qui n'est pas en base de données
        from hydria.middleware import MockUser
        if isinstance(user, MockUser):
            user = None

        employe = None
        if user:
            try:
                from apps.employees.models import Employe
                employe = Employe.objects.filter(user=user).first()
            except Exception:
                pass

        try:
            PageVisit.objects.create(
                user=user,
                employe=employe,
                path=request.path,
                query_params=json.dumps(request.GET.dict()),
                ip_address=self.get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                referer=request.META.get('HTTP_REFERER', '')
            )
        except Exception as e:
            # On ne veut pas bloquer la requête si le logging échoue
            print(f"Error logging visit: {e}")

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip


class ReadOnlyVisitorMiddleware:
    """
    Les visiteurs sont limites a la lecture:
    - bloque POST/PUT/PATCH/DELETE
    - sauf endpoints techniques necessaires (GPS, presence, logout, langue)
    """

    SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS'}
    ALLOWED_UNSAFE_PATH_PREFIXES = (
        '/api/capture-gps/',
        '/systeme/api/presence/update/',
        '/accounts/logout/',
        '/i18n/setlang/',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method in self.SAFE_METHODS:
            return self.get_response(request)

        user = getattr(request, 'user', None)
        if not user or not getattr(user, 'is_authenticated', False):
            return self.get_response(request)

        if not is_visiteur(user):
            return self.get_response(request)

        path = request.path or '/'
        if any(path.startswith(prefix) for prefix in self.ALLOWED_UNSAFE_PATH_PREFIXES):
            return self.get_response(request)

        accepts = request.headers.get('Accept', '')
        is_api = path.startswith('/api/') or '/api/' in path
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
        wants_json = 'application/json' in accepts

        if is_api or is_ajax or wants_json:
            return JsonResponse({
                'success': False,
                'error': 'Compte visiteur en lecture seule.'
            }, status=403)

        return HttpResponseForbidden('Compte visiteur en lecture seule.')


class CompletedCandidateAccessMiddleware:
    """
    Limite un candidat ayant deja termine son test a la page de resultats.

    Le compte peut rester authentifie pour consulter ses resultats, mais ne doit
    plus naviguer dans Hydria ni relancer le parcours de test.
    """

    ALLOWED_PATH_PREFIXES = (
        '/static/',
        '/media/',
        '/accounts/logout/',
        '/recrutement/resultats/',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if not user or not getattr(user, 'is_authenticated', False):
            return self.get_response(request)

        try:
            candidat = user.candidat
        except Exception:
            candidat = None

        if not candidat or candidat.statut != 'test_termine':
            return self.get_response(request)

        path = request.path or '/'
        if any(path.startswith(prefix) for prefix in self.ALLOWED_PATH_PREFIXES):
            return self.get_response(request)

        latest_session = (
            candidat.sessions_test
            .filter(statut__in=['termine', 'expire'])
            .order_by('-date_fin', '-date_debut', '-created_at')
            .first()
        )
        if not latest_session:
            return self.get_response(request)

        resultats_url = reverse('recrutement:resultats', kwargs={'session_id': latest_session.id})
        accepts = request.headers.get('Accept', '')
        is_api = path.startswith('/api/') or '/api/' in path
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
        wants_json = 'application/json' in accepts

        if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} or is_api or is_ajax or wants_json:
            return JsonResponse({
                'success': False,
                'error': 'Acces desactive: ce candidat a deja complete son test.',
                'redirect_url': resultats_url,
            }, status=403)

        return redirect(resultats_url)
