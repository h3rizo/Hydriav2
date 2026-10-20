"""API mobile — pointage GPS (app Android Hydria Terrain). Montée sous /api/mobile/v1/pointage/.

Authentification : jeton scope='mobile' émis par /mobile/api/login/.
Codes : 200 = pointage valide ; 422 = refus métier définitif (ne pas rejouer) ;
les erreurs réseau/serveur (5xx) sont à rejouer côté application.
"""
import json
import uuid
from datetime import date, datetime, timedelta, timezone as dt_timezone

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.core.auth_tokens import token_or_session_required
from apps.core.models import WidgetAuthToken

from . import services_pointage as svc
from .models import Planning

mobile_required = token_or_session_required(scope=WidgetAuthToken.SCOPE_MOBILE)


def _employe(request):
    return getattr(request.user, 'employe', None)


def _sans_employe():
    return JsonResponse({'success': False, 'error': "Aucun employé lié à ce compte."}, status=403)


def _payload(request):
    if request.content_type and 'json' in request.content_type:
        try:
            return json.loads(request.body or b'{}')
        except ValueError:
            return {}
    return request.POST


def _bool(v):
    return str(v).strip().lower() in ('1', 'true', 'oui', 'yes', 'on')


def _float(v):
    try:
        return float(v) if v not in (None, '') else None
    except (TypeError, ValueError):
        return None


def _parse_capture(data):
    """Horodatage de capture hors ligne : `captured_at` ISO 8601 ou `captured_at_ms` (epoch)."""
    ms = data.get('captured_at_ms')
    if ms not in (None, ''):
        try:
            return datetime.fromtimestamp(int(ms) / 1000, tz=dt_timezone.utc)
        except (TypeError, ValueError, OverflowError, OSError):
            return None
    iso = data.get('captured_at')
    if iso:
        try:
            dt = datetime.fromisoformat(str(iso).replace('Z', '+00:00'))
        except ValueError:
            return None
        return dt if dt.tzinfo else svc.tz_madagascar.localize(dt)
    return None


def _config():
    return {
        'distance_max_m': svc.DISTANCE_MAX_M,
        'precision_max_m': svc.PRECISION_MAX_M,
        'creneaux': [
            {'type': t, 'label': label, 'debut': f"{d:%H:%M}", 'fin': f"{f:%H:%M}"}
            for t, d, f, _c, label in svc.CRENEAUX
        ],
    }


@csrf_exempt
@require_GET
@mobile_required
def aujourdhui(request):
    employe = _employe(request)
    if employe is None:
        return _sans_employe()
    jour = timezone.now().astimezone(svc.tz_madagascar).date()
    return JsonResponse({
        'success': True,
        'surnom': svc._nom(employe),
        'employe_id': str(employe.id),
        'date': jour.isoformat(),
        'plannings': svc.synthese_employe_jour(employe, jour),
        # 8 jours de créneaux prévus : le téléphone y programme ses rappels locaux.
        'calendrier': svc.calendrier_prevus(employe, jour),
        'est_superieur': bool(svc.subordonnes_ids(employe, jour)),
        'config': _config(),
    })


@csrf_exempt
@require_POST
@mobile_required
def pointer(request):
    employe = _employe(request)
    if employe is None:
        return _sans_employe()
    data = _payload(request)

    local_uuid = None
    if data.get('local_uuid'):
        try:
            local_uuid = uuid.UUID(str(data['local_uuid']))
        except ValueError:
            return JsonResponse({'success': False, 'error': "local_uuid invalide."}, status=400)

    res = svc.enregistrer_pointage(
        employe,
        latitude=data.get('latitude'),
        longitude=data.get('longitude'),
        precision_m=_float(data.get('precision_m')),
        position_simulee=_bool(data.get('position_simulee', False)),
        captured_at=_parse_capture(data),
        local_uuid=local_uuid,
    )
    body = {
        'success': res.ok,
        'code': res.code,
        'message': res.message,
        'error': None if res.ok else res.message,
        'deja_pointe': res.deja_pointe,
        'distance_m': round(res.distance_m) if res.distance_m is not None else None,
        'type': res.pointage.type_pointage,
        'pointage_id': str(res.pointage.id),
        # Planning retenu automatiquement par le serveur (mis en évidence dans l'app).
        'planning_id': str(res.pointage.planning_id) if res.pointage.planning_id else None,
    }
    return JsonResponse(body, status=200 if res.ok else 422)


@csrf_exempt
@require_POST
@mobile_required
def declarer(request):
    """L'employé déclare à l'avance ses créneaux prévus sur un de SES plannings."""
    employe = _employe(request)
    if employe is None:
        return _sans_employe()
    data = _payload(request)
    try:
        planning = Planning.objects.get(id=data.get('planning_id'), employe=employe)
    except (Planning.DoesNotExist, ValueError, TypeError):
        return JsonResponse({'success': False, 'error': "Planning introuvable."}, status=404)
    if not svc.pointage_applicable(planning):
        return JsonResponse({'success': False, 'error': "Pas de pointage pour ce type d'ouvrage."}, status=422)

    champs = []
    for champ in ('prevu_matinee', 'prevu_apres_midi', 'prevu_nuitee'):
        if champ in data:
            setattr(planning, champ, _bool(data[champ]))
            champs.append(champ)
    if champs:
        planning.save(update_fields=champs + ['updated_at'])
    return JsonResponse({'success': True, 'planning_id': str(planning.id),
                         **{c: getattr(planning, c) for c in ('prevu_matinee', 'prevu_apres_midi', 'prevu_nuitee')}})


@csrf_exempt
@require_GET
@mobile_required
def equipe(request):
    """Mon pointage + celui de tous mes subordonnés (directs et indirects) pour un jour."""
    employe = _employe(request)
    if employe is None:
        return _sans_employe()
    try:
        jour = date.fromisoformat(request.GET['date']) if request.GET.get('date') \
            else timezone.now().astimezone(svc.tz_madagascar).date()
    except ValueError:
        return JsonResponse({'success': False, 'error': "Date invalide (AAAA-MM-JJ)."}, status=400)
    lignes = svc.synthese_equipe_jour(employe, jour)
    return JsonResponse({
        'success': True,
        'date': jour.isoformat(),
        'actualise_a': timezone.now().astimezone(svc.tz_madagascar).strftime('%H:%M:%S'),
        'employes': lignes,
        'total_manques': sum(l['nb_manques'] for l in lignes),
    })
