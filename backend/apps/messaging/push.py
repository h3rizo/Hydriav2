"""
Envoi de notifications push (Firebase Cloud Messaging) quand un message de
messagerie est créé et qu'un participant n'a pas de connexion WebSocket
active. Reste totalement inerte (no-op silencieux, loggé en debug) tant que
Firebase n'est pas configuré : la création/diffusion des messages ne doit
JAMAIS échouer à cause du push.

Prérequis pour l'activer (cf. plan HydriaRéunions, Phase B/D) :
- Un projet Firebase (console.firebase.google.com) avec Cloud Messaging activé.
- Une clé de compte de service JSON téléchargée, référencée par la variable
  d'environnement FIREBASE_CREDENTIALS_PATH (chemin absolu sur le serveur).
- Le paquet firebase-admin installé (ajouté à requirements.txt).
- Côté Android : google-services.json dans le module HydriaReunions.
"""
import logging
from functools import lru_cache

from django.conf import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _firebase_app():
    credentials_path = getattr(settings, 'FIREBASE_CREDENTIALS_PATH', None)
    if not credentials_path:
        logger.debug("FIREBASE_CREDENTIALS_PATH non défini : push désactivé.")
        return None
    try:
        import firebase_admin
        from firebase_admin import credentials
    except ImportError:
        logger.warning("Paquet firebase-admin non installé : push désactivé.")
        return None
    try:
        return firebase_admin.initialize_app(credentials.Certificate(credentials_path))
    except Exception:
        logger.exception("Échec d'initialisation Firebase : push désactivé.")
        return None


def send_push_to_employe(employe, title, body, data=None):
    app = _firebase_app()
    if app is None or employe is None:
        return

    from .models import DeviceToken

    tokens = list(DeviceToken.objects.filter(employe=employe, actif=True).values_list('token', flat=True))
    if not tokens:
        return

    from firebase_admin import messaging

    fcm_message = messaging.MulticastMessage(
        tokens=tokens,
        notification=messaging.Notification(title=title, body=body),
        data={k: str(v) for k, v in (data or {}).items()},
    )
    try:
        response = messaging.send_multicast(fcm_message, app=app)
    except Exception:
        logger.exception("Échec d'envoi push FCM pour employe=%s", employe.id)
        return

    if response.failure_count:
        _desactiver_tokens_invalides(tokens, response)


def _desactiver_tokens_invalides(tokens, response):
    from .models import DeviceToken

    invalides = [
        tokens[i] for i, result in enumerate(response.responses)
        if not result.success and getattr(result.exception, 'code', '') in ('UNREGISTERED', 'INVALID_ARGUMENT')
    ]
    if invalides:
        DeviceToken.objects.filter(token__in=invalides).update(actif=False)
