"""Tournée routière d'un agent : ordre optimal des visites du jour et itinéraire réel entre chaque étape.

Les étapes viennent des plannings de l'agent pour la date choisie : chaque planning est localisé par
son point d'eau cible, sinon par la première implantation connue de son ouvrage (même règle que la
préparation de tournée mobile). Le calcul lui-même est dans apps.geography.services.tournees.
"""
from datetime import datetime, time, timedelta

import pytz
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.billing.models import PointEau
from apps.employees.models import Employe
from apps.geography.models import Village
from apps.geography.services import tournees
from apps.geography.services.voies_config import PROFIL_DEFAUT, PROFILS_LIBELLES
from apps.organization.scoping import get_active_subordinate_employe_ids

from .models import Planning
from .views_preparation_tournee import _mobile_plannings_queryset, _nom_employe
from .views_simple import _get_planning_scope

TZ_MADAGASCAR = pytz.timezone('Indian/Antananarivo')
GEO = 'parcelle__village__fokontany__commune'


def _nom(employe):
    """Nom affichable (surnom, prénom ou nom) ; libellé de repli quand la fiche est incomplète."""
    return _nom_employe(employe) or 'Agent sans nom'


def _employes_visibles(user):
    """Employés actifs dont l'utilisateur peut consulter la tournée (même périmètre que les plannings)."""
    scope = _get_planning_scope(user)
    qs = Employe.objects.filter(date_debauchage__isnull=True).select_related('base')
    moi = getattr(user, 'employe', None)
    if scope == 'all':
        return qs
    if scope == 'none' or not moi:
        return qs.none()
    if scope == 'organisation':
        organisation_id = getattr(getattr(moi, 'base', None), 'organisation_id', None)
        return qs.filter(base__organisation_id=organisation_id) if organisation_id else qs.filter(pk=moi.pk)
    return qs.filter(pk__in=set(get_active_subordinate_employe_ids(moi.id)) | {moi.id})


def _village_du_point(point):
    parcelle = getattr(point, 'parcelle', None)
    return getattr(parcelle, 'village', None)


def villages_des_plannings(plannings):
    """{planning.id: Village | None} : point d'eau cible, sinon première implantation de l'ouvrage."""
    pe_ids = {p.cible_point_eau_id for p in plannings if p.cible_point_eau_id}
    ouvrage_ids = {p.ouvrage_id for p in plannings if p.ouvrage_id}
    par_point = {}
    if pe_ids:
        for pt in PointEau.objects.filter(id__in=pe_ids).select_related(GEO):
            if _village_du_point(pt):
                par_point[pt.id] = pt.parcelle.village
    par_ouvrage = {}
    if ouvrage_ids:
        for pt in PointEau.objects.filter(ouvrage_id__in=ouvrage_ids).select_related(GEO).order_by('ouvrage_id', 'id'):
            if pt.ouvrage_id not in par_ouvrage and _village_du_point(pt):
                par_ouvrage[pt.ouvrage_id] = pt.parcelle.village
    return {p.id: par_point.get(p.cible_point_eau_id) or par_ouvrage.get(p.ouvrage_id) for p in plannings}


def village_de_ouvrage(ouvrage_id):
    """Première implantation (village) connue d'un ouvrage, ou None."""
    pt = (PointEau.objects.filter(ouvrage_id=ouvrage_id).select_related(GEO).order_by('id').first())
    return _village_du_point(pt) if pt else None


def _village_base(employe):
    base = getattr(employe, 'base', None)
    ouvrage_id = getattr(base, 'ouvrage_id', None)
    if not ouvrage_id:
        return None
    pt = (PointEau.objects.filter(ouvrage_id=ouvrage_id).select_related(GEO).order_by('id').first())
    return _village_du_point(pt) if pt else None


def _jour_mg(texte):
    try:
        return datetime.strptime(texte, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _creneaux(planning):
    return [nom for nom, actif in (('matin', planning.prevu_matinee), ('après-midi', planning.prevu_apres_midi),
                                   ('nuit', planning.prevu_nuitee)) if actif]


def _fiche_village(v):
    commune = v.fokontany.commune.nom_commune if v.fokontany_id and v.fokontany.commune_id else ''
    return {'id': str(v.id), 'nom': v.nom_village, 'commune': commune,
            'lon': float(v.longitude) if v.longitude is not None else None,
            'lat': float(v.latitude) if v.latitude is not None else None}


@login_required
def page_tournee(request):
    employes = [{'id': str(e.id), 'nom': _nom(e)} for e in _employes_visibles(request.user).order_by('nom_employe')]
    moi = getattr(request.user, 'employe', None)
    return render(request, 'planning/tournee_routiere.html', {
        'employes': employes, 'employe_defaut': str(moi.id) if moi else '',
        'profils': list(PROFILS_LIBELLES.items()), 'profil_defaut': PROFIL_DEFAUT,
        'aujourd_hui': datetime.now(TZ_MADAGASCAR).strftime('%Y-%m-%d'),
    })


@require_GET
def api_tournee(request):
    """?employe=<uuid>&date=YYYY-MM-DD[&depart=<village uuid>][&retour=0|1][&critere=temps|distance][&profil=moto|voiture|pied]"""
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Authentification requise.'}, status=401)
    moi = getattr(request.user, 'employe', None)
    employe_id = request.GET.get('employe') or (str(moi.id) if moi else '')
    jour = _jour_mg(request.GET.get('date')) or datetime.now(TZ_MADAGASCAR).date()
    retour = request.GET.get('retour', '1') not in ('0', 'false')
    critere = request.GET.get('critere', 'temps')
    profil = request.GET.get('profil', PROFIL_DEFAUT)

    visibles = _employes_visibles(request.user)
    try:
        employe = visibles.filter(pk=employe_id).first()
    except Exception:  # identifiant malformé
        return JsonResponse({'success': False, 'error': 'Employé invalide.'}, status=400)
    if employe is None:
        return JsonResponse({'success': False, 'error': 'Employé introuvable ou hors de ton périmètre.'}, status=403)

    debut = TZ_MADAGASCAR.localize(datetime.combine(jour, time.min))
    plannings = list(_mobile_plannings_queryset(request.user)
                     .filter(Q(employe_id=employe.id) | Q(planning_employees__employee_id=employe.id),
                             date__gte=debut, date__lt=debut + timedelta(days=1))
                     .select_related('ouvrage', 'fiche_poste', 'type_activite').distinct().order_by('date', 'created_at'))
    par_planning = villages_des_plannings(plannings)

    # Étapes dans l'ordre du planning (référence pour mesurer le gain de l'optimisation).
    villages, groupes, sans_lieu = {}, {}, []
    for p in plannings:
        v = par_planning.get(p.id)
        entree = {'id': str(p.id), 'activite': p.activite_display or '', 'ouvrage': p.ouvrage.nom_ouvrage if p.ouvrage else '',
                  'creneaux': _creneaux(p), 'statut': p.get_statut_display() if p.statut else ''}
        if v is None or v.latitude is None or v.longitude is None:
            sans_lieu.append(entree)
            continue
        villages[v.id] = v
        groupes.setdefault(v.id, []).append(entree)
    ordre_planning = list(groupes)

    depart_param = request.GET.get('depart')
    depart, origine = None, ''
    if depart_param:
        depart = Village.objects.filter(pk=depart_param).select_related('fokontany__commune').first()
        origine = 'choisi'
    if depart is None:
        depart = _village_base(employe)
        origine = 'base'
    if depart is None and ordre_planning:
        depart, origine = villages[ordre_planning[0]], 'premier arrêt'
    reponse = {'success': True, 'employe': {'id': str(employe.id), 'nom': _nom(employe)},
               'date': jour.strftime('%Y-%m-%d'), 'sans_lieu': sans_lieu, 'nb_plannings': len(plannings)}
    if depart is None or not ordre_planning:
        reponse.update({'etapes': [], 'legs': [], 'depart': _fiche_village(depart) if depart else None})
        return JsonResponse(reponse)

    try:
        t = tournees.calculer(depart.id, ordre_planning, retour=retour, critere=critere, profil=profil)
    except tournees.TourneeInvalide as exc:
        return JsonResponse({**reponse, 'success': False, 'error': str(exc)}, status=422)

    fiche = {vid: _fiche_village(v) for vid, v in villages.items()}
    fiche[depart.id] = _fiche_village(depart)
    legs_par_arrivee = {}
    legs = []
    for rang, leg in enumerate(t['legs'], start=1):
        item = {'rang': rang, 'de': fiche[leg['de']]['nom'], 'vers': fiche[leg['vers']]['nom'],
                'vers_id': str(leg['vers']), 'distance_km': round(leg['distance_m'] / 1000, 2),
                'duree_min': round(leg['duree_s'] / 60),
                'repartition_km': {k: round(m / 1000, 2) for k, m in leg['repartition_m'].items()},
                'geometrie': {'type': 'LineString', 'coordinates': leg['geometrie']}}
        legs.append(item)
        legs_par_arrivee.setdefault(leg['vers'], item)
    reponse.update({
        # Les activités prévues au village de départ lui-même sont affichées avec le départ (ce n'est pas une étape).
        'depart': {**fiche[depart.id], 'origine': origine, 'plannings': groupes.get(depart.id, [])},
        'etapes': [{'rang': i, 'village': fiche[vid], 'plannings': groupes[vid],
                    'trajet': {k: legs_par_arrivee[vid][k] for k in ('distance_km', 'duree_min')}}
                   for i, vid in enumerate(t['ordre'], start=1)],
        'legs': legs, 'retour': retour, 'critere': critere, 'profil': profil,
        'distance_km': round(t['distance_m'] / 1000, 1), 'duree_min': round(t['duree_s'] / 60),
        'reference': {'distance_km': round(t['reference']['distance_m'] / 1000, 1),
                      'duree_min': round(t['reference']['duree_s'] / 60)},
        'gain_distance_km': round(t['gain_distance_m'] / 1000, 1), 'gain_duree_min': round(t['gain_duree_s'] / 60),
        'inaccessibles': [fiche[vid] | {'plannings': groupes[vid]} for vid in t['inaccessibles'] if vid in groupes],
        'departs_possibles': [fiche[vid] for vid in ordre_planning] + ([fiche[depart.id]] if depart.id not in groupes else []),
    })
    return JsonResponse(reponse)


@require_GET
def api_agents_du_jour(request):
    """Agents (de ton périmètre) ayant des plannings à la date donnée : ?date=YYYY-MM-DD.

    Sert à la carte des trajets : pour chaque agent, nombre de plannings et de villages localisés
    (la tournée détaillée se demande ensuite agent par agent via `api_tournee`).
    """
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Authentification requise.'}, status=401)
    jour = _jour_mg(request.GET.get('date')) or datetime.now(TZ_MADAGASCAR).date()
    visibles = {e.id: e for e in _employes_visibles(request.user)}
    debut = TZ_MADAGASCAR.localize(datetime.combine(jour, time.min))
    plannings = list(_mobile_plannings_queryset(request.user)
                     .filter(Q(employe_id__in=visibles) | Q(planning_employees__employee_id__in=visibles),
                             date__gte=debut, date__lt=debut + timedelta(days=1))
                     .prefetch_related('planning_employees').distinct())
    par_planning = villages_des_plannings(plannings)
    agents = {}
    for p in plannings:
        v = par_planning.get(p.id)
        localise = v is not None and v.latitude is not None and v.longitude is not None
        ids = {p.employe_id} | {pe.employee_id for pe in p.planning_employees.all()}
        for eid in ids & visibles.keys():
            fiche = agents.setdefault(eid, {'id': str(eid), 'nom': _nom(visibles[eid]), 'nb_plannings': 0, 'villages': set()})
            fiche['nb_plannings'] += 1
            if localise:
                fiche['villages'].add(v.id)
    liste = sorted(({'id': a['id'], 'nom': a['nom'], 'nb_plannings': a['nb_plannings'], 'nb_villages': len(a['villages'])}
                    for a in agents.values()), key=lambda a: a['nom'].lower())
    return JsonResponse({'success': True, 'date': jour.strftime('%Y-%m-%d'), 'agents': liste})


POSITIONS_GPS_MAX = 3000


@require_GET
def api_positions_gps(request):
    """Positions GPS réellement enregistrées par les agents (de ton périmètre) un jour donné.

    ?date=YYYY-MM-DD&precision_max=<mètres> (défaut 500 ; 0 = toutes). Plus de 37 % des positions ont une précision
    supérieure à 1 km (localisation par réseau) : elles sont écartées par défaut et comptées dans `nb_ecartees`.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Authentification requise.'}, status=401)
    from apps.employees.models import PositionGPSEmploye

    try:
        precision_max = max(0.0, float(request.GET.get('precision_max', 500)))
    except ValueError:
        return JsonResponse({'success': False, 'error': 'precision_max invalide.'}, status=400)
    jour = _jour_mg(request.GET.get('date')) or datetime.now(TZ_MADAGASCAR).date()
    debut = TZ_MADAGASCAR.localize(datetime.combine(jour, time.min))
    visibles = {e.id: e for e in _employes_visibles(request.user)}

    du_jour = PositionGPSEmploye.objects.filter(
        employe_id__in=visibles, date_enregistrement__gte=debut, date_enregistrement__lt=debut + timedelta(days=1),
        latitude__isnull=False, longitude__isnull=False)
    totaux = {r['employe_id']: r['n'] for r in du_jour.values('employe_id').annotate(n=Count('id'))}
    retenues = du_jour.filter(precision__lte=precision_max) if precision_max else du_jour
    retenues = retenues.select_related('village_proche').order_by('employe_id', 'date_enregistrement')[:POSITIONS_GPS_MAX]

    agents = {}
    for pos in retenues:
        a = agents.setdefault(pos.employe_id, [])
        a.append([float(pos.longitude), float(pos.latitude),
                  pos.date_enregistrement.astimezone(TZ_MADAGASCAR).strftime('%H:%M'),
                  round(float(pos.precision)) if pos.precision is not None else None,
                  pos.village_proche.nom_village if pos.village_proche_id else None])
    liste = [{'id': str(eid), 'nom': _nom(visibles[eid]), 'nb_total': total, 'nb': len(agents.get(eid, [])),
              'points': agents.get(eid, [])} for eid, total in totaux.items()]
    liste.sort(key=lambda a: a['nom'].lower())
    return JsonResponse({'success': True, 'date': jour.strftime('%Y-%m-%d'), 'precision_max': precision_max,
                         'agents': liste, 'tronque': len(retenues) >= POSITIONS_GPS_MAX})


@require_GET
def api_trajet_suggere(request):
    """Aide à la saisie d'un déplacement : village de l'ouvrage du planning et village de départ de la base de l'agent.

    ?ouvrage_id=<uuid>&employe_id=<uuid>
    """
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Authentification requise.'}, status=401)
    from django.core.exceptions import ValidationError
    ouvrage_id, employe_id = request.GET.get('ouvrage_id'), request.GET.get('employe_id')
    try:
        arrivee = village_de_ouvrage(ouvrage_id) if ouvrage_id else None
        employe = Employe.objects.select_related('base__village_depart').filter(pk=employe_id).first() if employe_id else None
    except (ValidationError, ValueError):
        return JsonResponse({'success': False, 'error': 'Identifiant invalide.'}, status=400)
    base = getattr(employe, 'base', None)
    depart_base = None
    if base is not None:
        village = base.village_depart if base.village_depart_id else None
        depart_base = {'nom': base.nom_base, 'localisee': base.lieu_depart is not None,
                       'village': _fiche_village(village) if village is not None and village.latitude is not None else None}
    return JsonResponse({'success': True, 'arrivee': _fiche_village(arrivee) if arrivee is not None else None,
                         'depart_base': depart_base})
