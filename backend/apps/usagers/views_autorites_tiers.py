"""
Vues pour la page de gestion du referentiel Autorites & Tiers (CRUD complet),
distinctes des vues legacy de views_reunions.py (autorites_list_json, autorite_create,
tiers_create) qui restent utilisees telles quelles par le module Reunions et dont le
contrat JSON ne doit pas changer.
"""

import json

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.defaultfilters import slugify
from django.views.decorators.http import require_http_methods

from apps.geography.models import Commune, District, Fokontany, Region

from .models import Autorite, TiersParticipant, TypeAutorite


@login_required
def autorites_tiers_list(request):
    """Page de gestion du referentiel Autorites & Tiers (2 onglets DaisyUI).

    Les listes de contexte servent uniquement a peupler les selects de filtre/formulaire ;
    le tableau lui-meme est rempli en JS via fetch (loadAutorites/loadTiers) au chargement.
    """
    communes = Commune.objects.order_by('nom_commune')
    districts = District.objects.select_related('region').order_by('nom_district')
    regions = Region.objects.order_by('nom_region')

    context = {
        'title': 'Autorites & Tiers',
        'communes': communes,
        'districts': districts,
        'regions': regions,
        'autorite_type_choices': Autorite.get_type_choices(),
        'tiers_type_choices': TiersParticipant.TYPE_CHOICES,
    }
    return render(request, 'usagers/autorites_tiers_list.html', context)


# ---------------------------------------------------------------------------
# Autorites - CRUD gestion
# ---------------------------------------------------------------------------

def _serialize_autorite(a):
    return {
        'id': str(a.id),
        'nom': a.nom,
        'type_autorite': a.type_autorite or '',
        'type_autorite_display': a.get_type_autorite_display() if a.type_autorite else '',
        'fonction': a.fonction or '',
        'fokontany_id': str(a.fokontany_id) if a.fokontany_id else '',
        'fokontany_nom': a.fokontany.nom_fokontany if a.fokontany_id and a.fokontany else '',
        'commune_id': str(a.commune_id) if a.commune_id else '',
        'commune_nom': a.commune.nom_commune if a.commune_id and a.commune else '',
        'district_id': str(a.district_id) if a.district_id else '',
        'district_nom': a.district.nom_district if a.district_id and a.district else '',
        'region_id': str(a.region_id) if a.region_id else '',
        'region_nom': a.region.nom_region if a.region_id and a.region else '',
        'zone_affichee': a.zone_affichee,
        'email': a.email or '',
        'contact': a.contact or '',
        'actif': a.actif,
        'observation': a.observation or '',
    }


@login_required
def autorite_gestion_list_json(request):
    search = (request.GET.get('search') or '').strip()
    type_autorite = (request.GET.get('type_autorite') or '').strip()
    commune_id = (request.GET.get('commune') or '').strip()
    statut = (request.GET.get('statut') or '').strip()  # 'actif' | 'inactif' | ''

    qs = Autorite.objects.select_related('fokontany', 'commune', 'district', 'region')
    if search:
        qs = qs.filter(Q(nom__icontains=search) | Q(fonction__icontains=search) | Q(contact__icontains=search))
    if type_autorite:
        qs = qs.filter(type_autorite=type_autorite)
    if commune_id:
        qs = qs.filter(commune_id=commune_id)
    if statut == 'actif':
        qs = qs.filter(actif=True)
    elif statut == 'inactif':
        qs = qs.filter(actif=False)

    qs = qs.order_by('nom')
    return JsonResponse({'success': True, 'autorites': [_serialize_autorite(a) for a in qs]})


def _validate_autorite_payload(data):
    """Retourne (champs_valides_dict, erreur|None). Ne fait pas le create/update lui-meme."""
    nom = (data.get('nom') or '').strip()
    if not nom:
        return None, 'Le nom est obligatoire.'

    type_autorite = (data.get('type_autorite') or '').strip()
    if type_autorite and type_autorite not in dict(Autorite.get_type_choices()):
        return None, "Type d'autorite invalide."

    fokontany = Fokontany.objects.filter(id=data['fokontany_id']).first() if data.get('fokontany_id') else None
    commune = Commune.objects.filter(id=data['commune_id']).first() if data.get('commune_id') else None
    district = District.objects.filter(id=data['district_id']).first() if data.get('district_id') else None
    region = Region.objects.filter(id=data['region_id']).first() if data.get('region_id') else None

    return {
        'nom': nom,
        'type_autorite': type_autorite,
        'fonction': (data.get('fonction') or '').strip() or None,
        'fokontany': fokontany,
        'commune': commune,
        'district': district,
        'region': region,
        'email': (data.get('email') or '').strip() or None,
        'contact': (data.get('contact') or '').strip() or None,
        'actif': bool(data.get('actif', True)),
        'observation': (data.get('observation') or '').strip() or None,
    }, None


@login_required
@require_http_methods(["POST"])
def autorite_gestion_create(request):
    try:
        data = json.loads(request.body)
        fields, error = _validate_autorite_payload(data)
        if error:
            return JsonResponse({'success': False, 'error': error}, status=400)
        autorite = Autorite.objects.create(**fields)
        return JsonResponse({'success': True, 'autorite': _serialize_autorite(autorite)})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def autorite_gestion_update(request, autorite_id):
    try:
        autorite = get_object_or_404(Autorite, id=autorite_id)
        data = json.loads(request.body)
        fields, error = _validate_autorite_payload(data)
        if error:
            return JsonResponse({'success': False, 'error': error}, status=400)
        for key, value in fields.items():
            setattr(autorite, key, value)
        autorite.save()
        return JsonResponse({'success': True, 'autorite': _serialize_autorite(autorite)})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def autorite_gestion_delete(request, autorite_id):
    try:
        autorite = get_object_or_404(Autorite, id=autorite_id)
        # on_delete=SET_NULL sur ParticipantReunion.autorite : la suppression ne casse pas
        # l'historique des reunions, mais fait perdre le lien vers la fiche (nom_affiche
        # retombe alors sur nom_libre / 'Participant').
        autorite.delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ---------------------------------------------------------------------------
# Tiers - CRUD gestion
# ---------------------------------------------------------------------------

def _serialize_tiers(t):
    return {
        'id': str(t.id),
        'nom': t.nom,
        'type_tiers': t.type_tiers or '',
        'type_tiers_display': t.get_type_tiers_display() if t.type_tiers else '',
        'organisme': t.organisme or '',
        'fonction': t.fonction or '',
        'email': t.email or '',
        'contact': t.contact or '',
        'actif': t.actif,
        'observation': t.observation or '',
    }


@login_required
def tiers_gestion_list_json(request):
    search = (request.GET.get('search') or '').strip()
    type_tiers = (request.GET.get('type_tiers') or '').strip()
    statut = (request.GET.get('statut') or '').strip()

    qs = TiersParticipant.objects.all()
    if search:
        qs = qs.filter(
            Q(nom__icontains=search) | Q(organisme__icontains=search) |
            Q(fonction__icontains=search) | Q(contact__icontains=search)
        )
    if type_tiers:
        qs = qs.filter(type_tiers=type_tiers)
    if statut == 'actif':
        qs = qs.filter(actif=True)
    elif statut == 'inactif':
        qs = qs.filter(actif=False)

    qs = qs.order_by('nom')
    return JsonResponse({'success': True, 'tiers': [_serialize_tiers(t) for t in qs]})


def _validate_tiers_payload(data):
    nom = (data.get('nom') or '').strip()
    if not nom:
        return None, 'Le nom est obligatoire.'

    type_tiers = (data.get('type_tiers') or '').strip()
    if type_tiers and type_tiers not in dict(TiersParticipant.TYPE_CHOICES):
        return None, 'Type de tiers invalide.'

    return {
        'nom': nom,
        'type_tiers': type_tiers,
        'organisme': (data.get('organisme') or '').strip() or None,
        'fonction': (data.get('fonction') or '').strip() or None,
        'email': (data.get('email') or '').strip() or None,
        'contact': (data.get('contact') or '').strip() or None,
        'actif': bool(data.get('actif', True)),
        'observation': (data.get('observation') or '').strip() or None,
    }, None


@login_required
@require_http_methods(["POST"])
def tiers_gestion_create(request):
    try:
        data = json.loads(request.body)
        fields, error = _validate_tiers_payload(data)
        if error:
            return JsonResponse({'success': False, 'error': error}, status=400)
        tiers = TiersParticipant.objects.create(**fields)
        return JsonResponse({'success': True, 'tiers': _serialize_tiers(tiers)})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def tiers_gestion_update(request, tiers_id):
    try:
        tiers = get_object_or_404(TiersParticipant, id=tiers_id)
        data = json.loads(request.body)
        fields, error = _validate_tiers_payload(data)
        if error:
            return JsonResponse({'success': False, 'error': error}, status=400)
        for key, value in fields.items():
            setattr(tiers, key, value)
        tiers.save()
        return JsonResponse({'success': True, 'tiers': _serialize_tiers(tiers)})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def tiers_gestion_delete(request, tiers_id):
    try:
        tiers = get_object_or_404(TiersParticipant, id=tiers_id)
        tiers.delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ---------------------------------------------------------------------------
# Types d'autorite - CRUD gestion (referentiel utilise par Autorite.type_autorite)
# ---------------------------------------------------------------------------

def _serialize_type_autorite(t, nb_autorites=None):
    return {
        'id': str(t.id),
        'slug': t.slug,
        'nom': t.nom,
        'ordre': t.ordre,
        'actif': t.actif,
        'nb_autorites': nb_autorites if nb_autorites is not None else Autorite.objects.filter(type_autorite=t.slug).count(),
    }


@login_required
def type_autorite_list_json(request):
    qs = TypeAutorite.objects.order_by('ordre', 'nom')
    # Nombre de fiches Autorite par slug, en une seule requete (type_autorite est un CharField,
    # pas une FK : pas de possibilite de select_related/annotate direct depuis TypeAutorite).
    comptages = dict(
        Autorite.objects.exclude(type_autorite='')
        .values_list('type_autorite')
        .annotate(total=Count('id'))
        .values_list('type_autorite', 'total')
    )
    types = [_serialize_type_autorite(t, comptages.get(t.slug, 0)) for t in qs]
    return JsonResponse({'success': True, 'types': types})


def _validate_type_autorite_payload(data, current_id=None):
    """Retourne (champs_valides_dict, erreur|None). Ne fait pas le create/update lui-meme."""
    nom = (data.get('nom') or '').strip()
    if not nom:
        return None, 'Le nom est obligatoire.'

    slug = (data.get('slug') or '').strip() or slugify(nom)
    slug = slug[:30]
    if not slug:
        return None, "Impossible de generer un code a partir de ce nom, precisez un code manuellement."

    qs_conflit = TypeAutorite.objects.filter(slug=slug)
    if current_id:
        qs_conflit = qs_conflit.exclude(id=current_id)
    if qs_conflit.exists():
        return None, f"Le code '{slug}' est deja utilise par un autre type."

    ordre = data.get('ordre')
    try:
        ordre = int(ordre) if ordre not in (None, '') else 0
    except (TypeError, ValueError):
        return None, "L'ordre doit etre un nombre."

    return {
        'slug': slug,
        'nom': nom,
        'ordre': ordre,
        'actif': bool(data.get('actif', True)),
    }, None


@login_required
@require_http_methods(["POST"])
def type_autorite_create(request):
    try:
        data = json.loads(request.body)
        fields, error = _validate_type_autorite_payload(data)
        if error:
            return JsonResponse({'success': False, 'error': error}, status=400)
        type_autorite = TypeAutorite.objects.create(**fields)
        return JsonResponse({'success': True, 'type': _serialize_type_autorite(type_autorite, 0)})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def type_autorite_update(request, type_id):
    try:
        type_autorite = get_object_or_404(TypeAutorite, id=type_id)
        data = json.loads(request.body)
        fields, error = _validate_type_autorite_payload(data, current_id=type_autorite.id)
        if error:
            return JsonResponse({'success': False, 'error': error}, status=400)

        ancien_slug = type_autorite.slug
        for key, value in fields.items():
            setattr(type_autorite, key, value)
        type_autorite.save()

        # Le slug identifie le type sur les fiches Autorite (CharField, pas de FK) : s'il change,
        # repercuter le changement sur toutes les fiches deja qualifiees avec l'ancien slug pour
        # eviter de les rendre orphelines silencieusement.
        if fields['slug'] != ancien_slug:
            Autorite.objects.filter(type_autorite=ancien_slug).update(type_autorite=fields['slug'])

        return JsonResponse({'success': True, 'type': _serialize_type_autorite(type_autorite)})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def type_autorite_delete(request, type_id):
    try:
        type_autorite = get_object_or_404(TypeAutorite, id=type_id)
        nb_utilisations = Autorite.objects.filter(type_autorite=type_autorite.slug).count()
        if nb_utilisations:
            return JsonResponse({
                'success': False,
                'error': f"Impossible de supprimer : {nb_utilisations} autorite(s) utilisent ce type. Desactivez-le plutot.",
            }, status=400)
        type_autorite.delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
