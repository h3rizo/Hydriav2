"""Page et API de revue / fusion des activités de réparation en doublon."""
import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from apps.employees.permissions import is_directeur_poste
from apps.planning import services_fusion_activites as svc
from apps.planning.models import FusionFichePosteLog


def _autorise(user):
    return bool(getattr(user, 'is_superuser', False) or is_directeur_poste(user))


def _json_body(request):
    try:
        data = json.loads(request.body or '{}')
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _api(request, handler):
    """Contrôle d'accès + corps JSON + traduction des erreurs métier."""
    if not _autorise(request.user):
        return JsonResponse({'success': False, 'error': 'Accès réservé aux administrateurs'}, status=403)
    payload = _json_body(request)
    if payload is None:
        return JsonResponse({'success': False, 'error': 'Corps JSON invalide'}, status=400)
    try:
        return JsonResponse({'success': True, **handler(payload)})
    except svc.FusionError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)
    except ObjectDoesNotExist:
        return JsonResponse({'success': False, 'error': 'Élément introuvable'}, status=404)


@login_required
@require_http_methods(["GET"])
def page_fusion_activites(request):
    if not _autorise(request.user):
        return HttpResponseForbidden("Accès réservé aux administrateurs")
    return render(request, 'planning/fusion_activites.html')


@login_required
@require_http_methods(["GET"])
def api_fusion_groupes(request):
    if not _autorise(request.user):
        return JsonResponse({'success': False, 'error': 'Accès réservé aux administrateurs'}, status=403)
    historique = [
        {
            'id': str(log.id),
            'date': log.created_at.isoformat(),
            'nom_avant': log.nom_cible_avant,
            'nom_apres': log.nom_cible_apres,
            'resume': log.resume,
            'annulee': bool(log.annulee_le),
        }
        for log in FusionFichePosteLog.objects.all()[:30]
    ]
    return JsonResponse({
        'success': True,
        'groupes': svc.build_groups(),
        'fiches': svc.toutes_fiches(),
        'catalogue': [v['nom'] for v in svc.catalogue_vocab()],
        'historique': historique,
    })


@login_required
@require_http_methods(["POST"])
def api_fusion_apercu(request):
    return _api(request, svc.apercu)


@login_required
@require_http_methods(["POST"])
def api_fusion_appliquer(request):
    return _api(request, lambda payload: svc.appliquer(payload, request.user))


@login_required
@require_http_methods(["POST"])
def api_fusion_annuler(request):
    return _api(request, lambda payload: svc.annuler(str(payload.get('log_id') or ''), request.user))
