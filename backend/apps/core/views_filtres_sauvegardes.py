"""API générique de gestion des filtres sauvegardés (nommés) pour les pages de
rapports. Un filtre est identifié par (page_key, nom) et stocke un dict JSON de
paramètres GET (valeurs simples ou listes pour les multi-select).
"""
import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .models import FiltreSauvegarde


def _serialize(filtre):
    return {
        'id': str(filtre.id),
        'nom': filtre.nom,
        'parametres': filtre.parametres,
    }


@login_required
@require_http_methods(['GET'])
def api_filtres_sauvegardes_list(request):
    page_key = (request.GET.get('page_key') or '').strip()
    if not page_key:
        return JsonResponse({'success': False, 'error': "Paramètre 'page_key' requis."}, status=400)

    filtres = FiltreSauvegarde.objects.filter(page_key=page_key).order_by('nom')
    return JsonResponse({
        'success': True,
        'filtres': [_serialize(f) for f in filtres],
    })


@login_required
@require_http_methods(['POST'])
def api_filtres_sauvegardes_create(request):
    try:
        payload = json.loads(request.body or '{}')
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'JSON invalide.'}, status=400)

    page_key = (payload.get('page_key') or '').strip()
    nom = (payload.get('nom') or '').strip()
    parametres = payload.get('parametres')

    if not page_key or not nom:
        return JsonResponse({'success': False, 'error': "Les champs 'page_key' et 'nom' sont requis."}, status=400)
    if not isinstance(parametres, dict):
        return JsonResponse({'success': False, 'error': "Le champ 'parametres' doit être un objet."}, status=400)

    filtre, created = FiltreSauvegarde.objects.update_or_create(
        page_key=page_key,
        nom=nom,
        defaults={
            'parametres': parametres,
            'cree_par': request.user if request.user.is_authenticated else None,
        },
    )
    return JsonResponse({'success': True, 'created': created, 'filtre': _serialize(filtre)})


@login_required
@require_http_methods(['POST'])
def api_filtres_sauvegardes_delete(request, filtre_id):
    try:
        filtre = FiltreSauvegarde.objects.get(id=filtre_id)
    except FiltreSauvegarde.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Filtre introuvable.'}, status=404)

    filtre.delete()
    return JsonResponse({'success': True})
