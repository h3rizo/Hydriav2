"""Authentification du client de synchronisation (décision Q5).

On réutilise le mécanisme de ``/api/mobile/v1/`` (``WidgetAuthToken`` d'accès court + ``MobileRefreshToken``
rotatif), mais avec un **scope dédié** ``sync`` : un jeton de synchronisation n'ouvre jamais les endpoints
mobiles/widget, et inversement. Aucun changement de modèle ni de migration dans ``apps.core``
(``scope`` est un simple CharField ; ``choices`` n'est pas appliqué en base).

Les pages Hydria (navigateur) utilisent la session Django, avec contrôle CSRF assuré par DRF.
"""
from datetime import timedelta

from django.utils import timezone
from rest_framework import authentication, exceptions, permissions

from apps.core.models import MobileRefreshToken, WidgetAuthToken

from . import acces

SCOPE_SYNC = 'sync'
PREFIXE_APPAREIL = 'sync:'
DUREE_ACCES = timedelta(hours=1)
DUREE_RENOUVELLEMENT = timedelta(days=30)


class JetonSynchronisation(authentication.BaseAuthentication):
    """``Authorization: Bearer <clé>`` portée par un WidgetAuthToken de scope ``sync``."""

    mots_cles = ('Bearer ', 'Token ')

    def authenticate(self, request):
        entete = request.headers.get('Authorization', '')
        mot_cle = next((m for m in self.mots_cles if entete.startswith(m)), None)
        if mot_cle is None:
            return None  # laisse la main à l'authentification par session
        cle = entete[len(mot_cle):].strip()
        jeton = WidgetAuthToken.objects.select_related('user').filter(key=cle, scope=SCOPE_SYNC).first()
        if jeton is None:
            raise exceptions.AuthenticationFailed("Jeton invalide.")
        if not jeton.is_usable or not jeton.user.is_active:
            raise exceptions.AuthenticationFailed("Jeton expiré ou révoqué.")
        jeton.last_used_at = timezone.now()
        jeton.save(update_fields=['last_used_at'])
        return jeton.user, jeton

    def authenticate_header(self, request):
        return 'Bearer'


class PeutSynchroniser(permissions.BasePermission):
    message = "Votre compte n'est pas autorisé à utiliser la synchronisation de fichiers."

    def has_permission(self, request, view):
        return acces.utilisateur_sync_autorise(request.user)


def creer_paire_jetons(user, device_id, libelle=''):
    maintenant = timezone.now()
    libelle = (libelle or 'Ordinateur')[:100]
    acces_jeton = WidgetAuthToken.objects.create(
        user=user, scope=SCOPE_SYNC, device_label=libelle, expires_at=maintenant + DUREE_ACCES,
    )
    renouvellement = MobileRefreshToken.objects.create(
        user=user, device_id=device_id, device_label=f'{PREFIXE_APPAREIL}{libelle}',
        expires_at=maintenant + DUREE_RENOUVELLEMENT,
    )
    return {
        'access_token': acces_jeton.key,
        'refresh_token': renouvellement.key,
        'token_type': 'Bearer',
        'expires_in': int(DUREE_ACCES.total_seconds()),
    }
