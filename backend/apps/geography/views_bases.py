"""Page et API « Lieux des bases » : placer chaque base sur une carte (lieu de départ des déplacements)."""
import json
import unicodedata
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from apps.employees.models import Employe
from apps.organization.models import Base

from .models import Village
from .services import itineraire as it
from .services import lieux
from .views_coupures import _json_staff, _staff


def _norm(texte):
    return unicodedata.normalize('NFKD', texte or '').encode('ascii', 'ignore').decode().lower().strip()


def _index_villages():
    """Villages géolocalisés avec leur nom normalisé (sans accent, minuscules), chargés une seule fois."""
    villages = (Village.objects.exclude(latitude__isnull=True).exclude(longitude__isnull=True)
                .select_related('fokontany__commune'))
    return [(v, _norm(v.nom_village)) for v in villages]


def suggestions_village(nom_base, index, limite=5):
    """Villages candidats d'après le nom de la base : nom identique d'abord, sinon même premier mot.

    La comparaison se fait en Python car la recherche SQL est sensible aux accents.
    """
    nom = _norm(nom_base)
    mot = nom.split()[0] if nom else ''
    if not mot:
        return []
    exacts = [v for v, n in index if n == nom]
    debut = [v for v, n in index if n.split()[0] == mot]      # même premier MOT (pas « Tana » -> « Tanambao »)
    retenus = exacts or debut
    return [{'id': str(v.id), 'nom': v.nom_village,
             'commune': v.fokontany.commune.nom_commune if v.fokontany_id and v.fokontany.commune_id else '',
             'lon': float(v.longitude), 'lat': float(v.latitude), 'exact': v in exacts} for v in retenus[:limite]]


def _fiche_base(base, index=None):
    lieu = base.lieu_depart
    distance = None
    if lieu:
        try:
            distance = round(lieux.acces_base(base)['distance_m'])
        except it.ItineraireIntrouvable:
            distance = None
    return {
        'id': str(base.id), 'nom': base.nom_base, 'organisation': base.organisation.nom_organisation,
        'nb_employes': Employe.objects.filter(base=base, date_debauchage__isnull=True).count(),
        'lieu': {'lon': lieu[0], 'lat': lieu[1], 'libelle': lieu[2],
                 'village_id': str(base.village_depart_id) if base.village_depart_id else None} if lieu else None,
        'distance_route_m': distance,
        'suggestions': suggestions_village(base.nom_base, index if index is not None else _index_villages()),
    }


@login_required
@_staff
def page_lieux_bases(request):
    return render(request, 'geography/lieux_bases.html')


@require_GET
@_json_staff
def api_bases_liste(request):
    bases = Base.objects.select_related('organisation', 'village_depart').order_by('organisation__nom_organisation', 'nom_base')
    index = _index_villages()
    return JsonResponse({'success': True, 'bases': [_fiche_base(b, index) for b in bases]})


@require_POST
@_json_staff
def api_base_lieu(request, pk):
    base = Base.objects.select_related('organisation', 'village_depart').filter(pk=pk).first()
    if base is None:
        return JsonResponse({'success': False, 'error': 'Base introuvable.'}, status=404)
    try:
        d = json.loads(request.body or '{}')
        if d.get('effacer'):
            base.village_depart = None
            base.latitude_depart = base.longitude_depart = None
        else:
            lon, lat = float(d['lon']), float(d['lat'])
            if not lieux.dans_madagascar(lon, lat):
                return JsonResponse({'success': False, 'error': 'Cette position est hors de Madagascar.'}, status=400)
            village = Village.objects.filter(pk=d['village_id']).first() if d.get('village_id') else None
            if d.get('village_id') and village is None:
                return JsonResponse({'success': False, 'error': 'Village introuvable.'}, status=400)
            base.village_depart = village
            base.latitude_depart = Decimal(f'{lat:.7f}')
            base.longitude_depart = Decimal(f'{lon:.7f}')
    except (KeyError, TypeError, ValueError, InvalidOperation, json.JSONDecodeError):
        return JsonResponse({'success': False, 'error': 'Requête invalide.'}, status=400)
    base.save(update_fields=['village_depart', 'latitude_depart', 'longitude_depart'])
    return JsonResponse({'success': True, 'base': _fiche_base(base)})
