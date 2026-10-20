"""
API mobile — module Conversations (messagerie temps réel, app Android
HydriaRéunions). Montée sous /api/mobile/v1/messaging/. Réutilise le jeton
scope='mobile' émis par /mobile/api/login/ (même décorateur que les autres
modules mobiles, cf. apps/accounting/mobile_api_v1.py et
apps/usagers/mobile_api_v1.py).

L'envoi de message en temps réel passe normalement par le WebSocket
(apps.messaging.consumers) ; l'endpoint REST 'messages/send' ici n'est qu'un
repli si la connexion WebSocket n'est pas disponible — les deux chemins
partagent la même logique (apps.messaging.services.creer_message) pour ne
jamais diverger.

Note : Conversation/Message/Participant utilisent des identifiants entiers
auto-incrémentés (pas des UUID, contrairement aux modèles de apps.usagers).
"""
import functools
import json
import logging
import traceback
from datetime import datetime

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.core.auth_tokens import token_or_session_required
from apps.core.models import WidgetAuthToken
from apps.employees.models import Employe

from .models import Conversation, DeviceToken, Message, Participant
from .services import creer_message, marquer_lu, message_json

logger = logging.getLogger(__name__)
mobile_required = token_or_session_required(scope=WidgetAuthToken.SCOPE_MOBILE)

BOOTSTRAP_MAX_CONVERSATIONS = 200
BOOTSTRAP_MESSAGES_PER_CONVERSATION = 50


def _json_errors(view):
    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.exception("messaging mobile %s a échoué", view.__name__)
            return JsonResponse(
                {'code': 'SERVER_ERROR', 'message': str(exc), 'where': view.__name__,
                 'trace': traceback.format_exc().splitlines()[-6:]},
                status=500,
            )
    return wrapper


def _employe(request):
    return getattr(request.user, 'employe', None)


def _conversation_json(conv, employe):
    participant = next((p for p in conv.participants.all() if p.employe_id == employe.id), None)
    dernier = conv.dernier_message
    return {
        'id': str(conv.id),
        'type': conv.type,
        'nom_groupe': conv.nom_groupe or '',
        'description': conv.description or '',
        'photo_groupe_url': conv.photo_groupe.url if conv.photo_groupe else None,
        'nom_affiche': str(conv),
        'nombre_participants': conv.nombre_participants,
        'participants': [
            {
                'employe_id': str(p.employe_id),
                'nom': p.employe.surnom or p.employe.nom_employe,
                'est_admin': p.est_admin,
            }
            for p in conv.participants.select_related('employe').all()
        ],
        'dernier_message': message_json(dernier) if dernier else None,
        'messages_non_lus': participant.messages_non_lus if participant else 0,
        'notifications_activees': participant.notifications_activees if participant else True,
        'derniere_activite': conv.derniere_activite.isoformat(),
        'created_at': conv.date_creation.isoformat(),
    }


# --------------------------------------------------------------------------- #
#  bootstrap
# --------------------------------------------------------------------------- #

@require_GET
@mobile_required
@_json_errors
def bootstrap(request):
    employe = _employe(request)
    if employe is None:
        return JsonResponse({'code': 'NO_EMPLOYE', 'message': "Aucune fiche employé rattachée."}, status=403)

    conversations_qs = list(
        Conversation.objects.filter(participants__employe=employe, archivee=False)
        .distinct().order_by('-derniere_activite')[:BOOTSTRAP_MAX_CONVERSATIONS]
    )
    conversations = [_conversation_json(c, employe) for c in conversations_qs]

    messages_par_conversation = {}
    for conv in conversations_qs:
        messages_qs = conv.messages.filter(supprime=False).select_related('expediteur').order_by(
            '-date_envoi'
        )[:BOOTSTRAP_MESSAGES_PER_CONVERSATION]
        messages_par_conversation[str(conv.id)] = [message_json(m) for m in reversed(list(messages_qs))]

    employes_annuaire = [
        {'id': str(e.id), 'nom': e.surnom or e.nom_employe}
        for e in Employe.objects.filter(date_debauchage__isnull=True).order_by('nom_employe')
    ]

    now = timezone.now().isoformat()
    return JsonResponse({
        'cursor': now,
        'server_time': now,
        'payload': {
            'employe_id': str(employe.id),
            'conversations': conversations,
            'messages': messages_par_conversation,
            'employes_annuaire': employes_annuaire,
        },
    })


# --------------------------------------------------------------------------- #
#  changes
# --------------------------------------------------------------------------- #

@require_GET
@mobile_required
@_json_errors
def changes(request):
    employe = _employe(request)
    if employe is None:
        return JsonResponse({'code': 'NO_EMPLOYE', 'message': "Aucune fiche employé rattachée."}, status=403)

    since_raw = (request.GET.get('since') or '').strip()
    try:
        since = datetime.fromisoformat(since_raw) if since_raw else None
    except ValueError:
        since = None
    if since is None:
        return JsonResponse({
            'cursor': timezone.now().isoformat(), 'has_more': False,
            'full_refresh_required': True, 'reason': 'MISSING_OR_INVALID_SINCE', 'changes': {},
        })

    conversations_qs = Conversation.objects.filter(
        participants__employe=employe, derniere_activite__gt=since,
    ).distinct()
    nouveaux_messages = Message.objects.filter(
        conversation__participants__employe=employe, date_envoi__gt=since,
    ).distinct().select_related('expediteur').order_by('date_envoi')

    return JsonResponse({
        'cursor': timezone.now().isoformat(),
        'has_more': False,
        'full_refresh_required': False,
        'changes': {
            'conversations': [_conversation_json(c, employe) for c in conversations_qs],
            'messages': [message_json(m) for m in nouveaux_messages],
        },
    })


# --------------------------------------------------------------------------- #
#  conversations / messages / lu
# --------------------------------------------------------------------------- #

@csrf_exempt
@require_POST
@mobile_required
@_json_errors
def conversation_create(request):
    employe = _employe(request)
    if employe is None:
        return JsonResponse({'success': False, 'error': 'Aucune fiche employé rattachée.'}, status=403)

    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'error': 'Corps JSON invalide.'}, status=400)

    participant_ids = [str(pid).strip() for pid in body.get('participant_ids') or [] if str(pid).strip()]
    type_conv = body.get('type') or 'direct'
    if type_conv not in dict(Conversation.TYPE_CHOICES):
        return JsonResponse({'success': False, 'error': 'Type de conversation invalide.'}, status=400)

    if type_conv == 'direct':
        if len(participant_ids) != 1:
            return JsonResponse(
                {'success': False, 'error': 'Une conversation directe nécessite exactement un autre participant.'},
                status=400,
            )
        autre_id = participant_ids[0]
        existante = Conversation.objects.filter(
            type='direct', participants__employe_id=employe.id,
        ).filter(participants__employe_id=autre_id).first()
        if existante:
            return JsonResponse({'success': True, 'conversation_id': str(existante.id)})

    conversation = Conversation.objects.create(
        type=type_conv,
        nom_groupe=(body.get('nom_groupe') or '').strip() or None,
        description=(body.get('description') or '').strip() or None,
        createur=employe,
    )
    Participant.objects.create(conversation=conversation, employe=employe, est_admin=True)
    for pid in participant_ids:
        if pid != str(employe.id):
            Participant.objects.get_or_create(conversation=conversation, employe_id=pid)

    return JsonResponse({'success': True, 'conversation_id': str(conversation.id)})


@csrf_exempt
@require_POST
@mobile_required
@_json_errors
def messages_send(request):
    employe = _employe(request)
    if employe is None:
        return JsonResponse({'success': False, 'error': 'Aucune fiche employé rattachée.'}, status=403)

    try:
        body = json.loads(request.body.decode('utf-8') or '{}')
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'error': 'Corps JSON invalide.'}, status=400)

    conversation_id = body.get('conversation_id')
    contenu = (body.get('contenu') or '').strip()
    if not conversation_id or not contenu:
        return JsonResponse({'success': False, 'error': 'conversation_id et contenu sont obligatoires.'}, status=400)

    message = creer_message(
        conversation_id=conversation_id, employe=employe, contenu=contenu,
        type_message=body.get('type') or 'text', message_repondu_id=body.get('message_repondu_id'),
    )
    if message is None:
        return JsonResponse(
            {'success': False, 'error': "Vous n'êtes pas participant de cette conversation."}, status=403,
        )
    return JsonResponse({'success': True, 'message': message_json(message)})


@csrf_exempt
@require_POST
@mobile_required
@_json_errors
def messages_read(request, conversation_id):
    employe = _employe(request)
    if employe is None:
        return JsonResponse({'success': False, 'error': 'Aucune fiche employé rattachée.'}, status=403)
    ok = marquer_lu(conversation_id, employe)
    return JsonResponse({'success': ok})


# --------------------------------------------------------------------------- #
#  jetons push (FCM)
# --------------------------------------------------------------------------- #

@csrf_exempt
@require_POST
@mobile_required
@_json_errors
def register_device(request):
    employe = _employe(request)
    if employe is None:
        return JsonResponse({'success': False, 'error': 'Aucune fiche employé rattachée.'}, status=403)

    token = (request.POST.get('token') or '').strip()
    if not token:
        return JsonResponse({'success': False, 'error': 'Jeton FCM requis.'}, status=400)

    DeviceToken.objects.update_or_create(
        token=token,
        defaults={
            'employe': employe,
            'plateforme': request.POST.get('plateforme') or DeviceToken.PLATFORM_ANDROID,
            'device_label': (request.POST.get('device_label') or '').strip() or None,
            'actif': True,
        },
    )
    return JsonResponse({'success': True})


@csrf_exempt
@require_POST
@mobile_required
@_json_errors
def unregister_device(request):
    token = (request.POST.get('token') or '').strip()
    if token:
        DeviceToken.objects.filter(token=token).update(actif=False)
    return JsonResponse({'success': True})
