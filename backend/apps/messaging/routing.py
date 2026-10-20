"""Routage WebSocket de l'app messaging (chat temps reel). Branche dans
hydria/asgi.py — seul le prefixe /ws/ est redirige vers Daphne par Nginx en
production, tout le reste du trafic HTTP continue sur Gunicorn/WSGI."""
from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(
        r'^ws/messaging/conversations/(?P<conversation_id>\d+)/$',
        consumers.ChatConsumer.as_asgi(),
    ),
]
