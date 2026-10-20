import functools
import hmac

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone

from apps.core.models import WidgetAuthToken


def diamex_agent_required(view_func):
    """
    Session Django, ou en-tête 'Authorization: Token <DIAMEX_AGENT_TOKEN>' envoyé par
    l'agent local d'import DiameX (qui n'a pas de session navigateur).
    """
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated:
            return view_func(request, *args, **kwargs)

        expected = getattr(settings, 'DIAMEX_AGENT_TOKEN', '') or ''
        header = request.headers.get('Authorization', '')
        if expected and header.startswith('Token '):
            provided = header[len('Token '):].strip()
            if hmac.compare_digest(provided.encode(), expected.encode()):
                return view_func(request, *args, **kwargs)
            return JsonResponse({'success': False, 'error': 'Token invalide'}, status=401)

        return JsonResponse({'success': False, 'error': 'Authentification requise'}, status=401)

    return wrapper


def token_or_session_required(scope):
    """
    Authentifie soit via la session Django classique (déjà connecté dans un
    navigateur), soit via un header 'Authorization: Token <clé>' porté par
    un WidgetAuthToken dont le `scope` correspond exactement à celui exigé
    ici — un token 'mobile' ne passe jamais sur une vue exigeant 'widget',
    et réciproquement, même si la clé est valide.

    Usage :
        @token_or_session_required(scope=WidgetAuthToken.SCOPE_MOBILE)
        def ma_vue(request): ...
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if request.user.is_authenticated:
                return view_func(request, *args, **kwargs)

            auth_header = request.headers.get('Authorization', '')
            auth_prefix = next(
                (prefix for prefix in ('Token ', 'Bearer ') if auth_header.startswith(prefix)),
                None,
            )
            if auth_prefix:
                key = auth_header[len(auth_prefix):].strip()
                try:
                    token = WidgetAuthToken.objects.select_related('user').get(key=key, scope=scope)
                except WidgetAuthToken.DoesNotExist:
                    return JsonResponse({'success': False, 'error': 'Token invalide'}, status=401)

                if not token.is_usable or not token.user.is_active:
                    return JsonResponse({'success': False, 'error': 'Token expiré ou révoqué'}, status=401)

                token.last_used_at = timezone.now()
                token.save(update_fields=['last_used_at'])
                request.user = token.user
                from apps.core.contributions import definir_auteur
                definir_auteur(token.user, 'mobile')
                return view_func(request, *args, **kwargs)

            return JsonResponse({'success': False, 'error': 'Authentification requise'}, status=401)

        return wrapper

    return decorator
