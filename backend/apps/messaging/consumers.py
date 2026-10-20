"""
Consumer WebSocket pour la messagerie temps réel (Conversations façon
WhatsApp, app Android HydriaRéunions).

Authentification : même jeton mobile que le reste de l'app
(WidgetAuthToken, scope='mobile', émis par /mobile/api/login/) — accepté en
query string (?token=<clé>) ou en header Authorization au handshake, pour
rester compatible avec les clients WebSocket qui ne posent pas toujours de
header custom.

Groupe de diffusion : un groupe par conversation ('conversation_<id>'). La
création/diffusion effective d'un message est déléguée à
apps.messaging.services pour rester identique, que le message arrive par
WebSocket ou par l'API REST de secours.
"""
import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from apps.core.models import WidgetAuthToken


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.employe = await self._authenticate()
        if self.employe is None:
            await self.close(code=4401)
            return

        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        if not await self._est_participant():
            await self.close(code=4403)
            return

        self.group_name = f'conversation_{self.conversation_id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except (TypeError, json.JSONDecodeError):
            return

        action = data.get('action')
        if action == 'message.send':
            await self._creer_message(data)
        elif action == 'typing':
            await self.channel_layer.group_send(self.group_name, {
                'type': 'chat.typing',
                'employe_id': str(self.employe.id),
                'employe_nom': self.employe.surnom or self.employe.nom_employe,
            })
        elif action == 'message.read':
            await self._marquer_lu()

    # --- Handlers de groupe -> client WebSocket ---

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({'action': 'message.new', 'message': event['message']}))

    async def chat_typing(self, event):
        if event['employe_id'] != str(self.employe.id):
            await self.send(text_data=json.dumps({
                'action': 'typing', 'employe_id': event['employe_id'], 'employe_nom': event['employe_nom'],
            }))

    async def chat_read(self, event):
        await self.send(text_data=json.dumps({'action': 'message.read', 'employe_id': event['employe_id']}))

    # --- Accès DB (sync -> async) ---

    @database_sync_to_async
    def _authenticate(self):
        query_string = self.scope.get('query_string', b'').decode()
        params = dict(p.split('=', 1) for p in query_string.split('&') if '=' in p)
        token_key = params.get('token', '')

        if not token_key:
            headers = dict(self.scope.get('headers') or [])
            auth_header = headers.get(b'authorization', b'').decode()
            if auth_header.startswith('Token '):
                token_key = auth_header[len('Token '):]

        if not token_key:
            return None
        try:
            token = WidgetAuthToken.objects.select_related('user__employe').get(
                key=token_key, scope=WidgetAuthToken.SCOPE_MOBILE,
            )
        except WidgetAuthToken.DoesNotExist:
            return None
        if not token.is_usable or not token.user.is_active:
            return None
        return getattr(token.user, 'employe', None)

    @database_sync_to_async
    def _est_participant(self):
        from .models import Participant
        return Participant.objects.filter(
            conversation_id=self.conversation_id, employe_id=self.employe.id,
        ).exists()

    @database_sync_to_async
    def _creer_message(self, data):
        from .services import creer_message
        creer_message(
            conversation_id=self.conversation_id,
            employe=self.employe,
            contenu=data.get('contenu', ''),
            type_message=data.get('type') or 'text',
            message_repondu_id=data.get('message_repondu_id'),
        )

    @database_sync_to_async
    def _marquer_lu(self):
        from .services import marquer_lu
        marquer_lu(self.conversation_id, self.employe)
