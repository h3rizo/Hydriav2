"""
ASGI config for hydria project.

Sert le routage WebSocket de la messagerie temps réel (apps.messaging,
Conversations façon WhatsApp de l'app Android HydriaRéunions). En production,
Gunicorn/WSGI continue de servir tout le trafic HTTP habituel ; seul le
chemin /ws/ est redirigé vers Daphne par Nginx (cf. notes de déploiement du
plan HydriaReunions, Phase B) — ce fichier n'a donc besoin d'exposer
proprement que 'http' (fallback/local) et 'websocket'.

Pas d'AuthMiddlewareStack ici : les clients mobiles n'utilisent pas de
session/cookie Django, l'authentification par jeton mobile (WidgetAuthToken)
est gérée directement par ChatConsumer._authenticate().

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')

django_asgi_app = get_asgi_application()

# Importé après get_asgi_application() : apps.messaging.routing importe des
# modèles Django, qui exigent que la registry des apps soit déjà chargée.
from apps.messaging.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': URLRouter(websocket_urlpatterns),
})
