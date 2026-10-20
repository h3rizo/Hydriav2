"""
Logique métier partagée entre le consumer WebSocket (apps.messaging.consumers)
et l'API REST mobile (apps.messaging.mobile_api_v1), pour ne jamais dupliquer
la création/diffusion d'un message selon le chemin d'entrée (WebSocket ou
appel REST de secours quand la connexion temps réel n'est pas disponible).
"""
import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone

logger = logging.getLogger(__name__)


def _group_send(group_name, payload):
    """Diffuse sur le channel layer (Redis) sans jamais faire echouer l'appelant :
    tant que Redis n'est pas deploye/joignable sur le serveur (cf. Phase B, encore en
    cours de deploiement), l'envoi REST d'un message doit rester fonctionnel meme si
    la diffusion temps reel echoue -- seuls les clients WebSocket connectes la perdent,
    ce qui n'est de toute facon personne tant que Daphne n'est pas en place."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    try:
        async_to_sync(channel_layer.group_send)(group_name, payload)
    except Exception:
        logger.warning(
            "Diffusion temps reel impossible (channel layer/Redis injoignable) - "
            "message deja enregistre en base, seule la diffusion WebSocket est perdue.",
            exc_info=True,
        )


def message_json(message, expediteur=None):
    expediteur = expediteur or message.expediteur
    return {
        'id': str(message.id),
        'conversation_id': str(message.conversation_id),
        'expediteur_id': str(expediteur.id) if expediteur else None,
        'expediteur_nom': (expediteur.surnom or expediteur.nom_employe) if expediteur else None,
        'type': message.type,
        'contenu': message.contenu,
        'fichier_url': message.fichier.url if message.fichier else None,
        'date_envoi': message.date_envoi.isoformat(),
        'message_repondu_id': str(message.message_repondu_id) if message.message_repondu_id else None,
        'supprime': message.supprime,
    }


def diffuser_message(message):
    """Publie le message sur le groupe WebSocket de la conversation (les
    clients connectés le reçoivent immédiatement), quel que soit le canal
    d'entrée (WS ou REST), puis notifie les participants absents par push."""
    _group_send(
        f'conversation_{message.conversation_id}',
        {'type': 'chat.message', 'message': message_json(message)},
    )
    _notifier_push(message)


def creer_message(conversation_id, employe, contenu, type_message='text', message_repondu_id=None, fichier=None):
    from .models import Conversation, Message, Participant

    contenu = (contenu or '').strip()
    if not contenu and not fichier:
        return None
    if not Participant.objects.filter(conversation_id=conversation_id, employe=employe).exists():
        return None

    message = Message.objects.create(
        conversation_id=conversation_id,
        expediteur=employe,
        type=type_message or 'text',
        contenu=contenu,
        fichier=fichier,
        message_repondu_id=message_repondu_id or None,
    )
    Conversation.objects.filter(id=conversation_id).update(derniere_activite=message.date_envoi)
    diffuser_message(message)
    return message


def marquer_lu(conversation_id, employe):
    from .models import Participant

    updated = Participant.objects.filter(
        conversation_id=conversation_id, employe=employe,
    ).update(date_derniere_lecture=timezone.now())
    if updated:
        _group_send(
            f'conversation_{conversation_id}',
            {'type': 'chat.read', 'employe_id': str(employe.id)},
        )
    return bool(updated)


def _notifier_push(message):
    from .models import Participant
    from .push import send_push_to_employe  # import tardif : cout nul tant que le push n'est pas configure

    participants = Participant.objects.filter(
        conversation_id=message.conversation_id, notifications_activees=True,
    ).exclude(employe_id=message.expediteur_id).select_related('employe')

    expediteur = message.expediteur
    titre = (expediteur.surnom or expediteur.nom_employe) if expediteur else 'Hydria Réunions'
    corps = message.contenu[:120] if message.type == 'text' else f"[{message.get_type_display()}]"
    for participant in participants:
        send_push_to_employe(
            participant.employe,
            title=titre,
            body=corps,
            data={'conversation_id': str(message.conversation_id), 'message_id': str(message.id)},
        )
