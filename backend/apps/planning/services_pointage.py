"""Pointage GPS des employés : validation temporelle + spatiale, suivi et rapport.

Règles (cf. CLAUDE.md, section timezone) : tout l'horaire est évalué en heure de
Madagascar ; le filtre par jour se fait par bornes de datetime aware, jamais par
extraction SQL de la date.
"""
import math
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Optional

import pytz
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from .models import Planning
from .models_pointage import PointageGPS

tz_madagascar = pytz.timezone('Indian/Antananarivo')

DISTANCE_MAX_M = 3000.0
PRECISION_MAX_M = 100.0
# Horodatage d'un pointage hors ligne : toléré tant qu'il est plausible.
HORS_LIGNE_MAX_AGE = timedelta(hours=72)
HORS_LIGNE_MAX_FUTUR = timedelta(minutes=5)

# (type, début, fin inclus, champ Planning déclaré à l'avance, libellé)
CRENEAUX = [
    (PointageGPS.TYPE_MATIN, time(10, 0), time(12, 0), 'prevu_matinee', 'Matinée'),
    (PointageGPS.TYPE_APREM, time(15, 0), time(18, 0), 'prevu_apres_midi', 'Après-midi'),
    (PointageGPS.TYPE_NUIT, time(19, 0), time(21, 0), 'prevu_nuitee', 'Nuitée'),
]
CRENEAU_PAR_TYPE = {c[0]: c for c in CRENEAUX}


# --------------------------------------------------------------------------- #
#  Outils purs
# --------------------------------------------------------------------------- #
def haversine_m(lat1, lng1, lat2, lng2) -> float:
    """Distance orthodromique en mètres."""
    r = 6371008.8
    p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
    dphi = p2 - p1
    dlmb = math.radians(float(lng2) - float(lng1))
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def creneau_pour(heure: time) -> Optional[str]:
    for type_, debut, fin, _champ, _label in CRENEAUX:
        if debut <= heure <= fin:
            return type_
    return None


def _formater_distance(metres: float) -> str:
    return f"{metres / 1000:.1f} km".replace('.', ',') if metres >= 1000 else f"{int(round(metres))} m"


def _nom(employe) -> str:
    return employe.surnom or employe.nom_affichage or ''


def _bornes_jour(jour):
    debut = tz_madagascar.localize(datetime.combine(jour, time.min))
    return debut, debut + timedelta(days=1)


# --------------------------------------------------------------------------- #
#  Planning / villages
# --------------------------------------------------------------------------- #
def plannings_du_jour(employe, jour):
    debut, fin = _bornes_jour(jour)
    return list(
        Planning.objects.filter(date__gte=debut, date__lt=fin)
        .filter(Q(employe=employe) | Q(planning_employees__employee=employe))
        .exclude(statut='annule')
        .select_related('ouvrage__type_ouvrage', 'fiche_poste', 'type_activite', 'cible_point_eau__parcelle')
        .distinct()
        .order_by('date', 'created_at')
    )


def pointage_applicable(planning) -> bool:
    """Le pointage GPS ne s'applique pas aux plannings sur un ouvrage dont le type
    « n'existe pas » physiquement (TypeOuvrage.existe=False : Bureau, Terrain,
    Potentiel, Suspendu, Travaux en cours…). Planning sans ouvrage : pointage possible."""
    ouvrage = getattr(planning, 'ouvrage', None)
    type_ouvrage = getattr(ouvrage, 'type_ouvrage', None) if ouvrage is not None else None
    return type_ouvrage is None or bool(type_ouvrage.existe)


def villages_du_planning(planning):
    """Villages du planning : celui du point d'eau ciblé, sinon tous ceux de l'ouvrage."""
    from apps.billing.models import PointEau
    from apps.geography.models import Village

    ids = set()
    cible = planning.cible_point_eau
    if cible is not None and cible.parcelle is not None and cible.parcelle.village_id:
        ids.add(cible.parcelle.village_id)
    elif planning.ouvrage_id:
        ids.update(
            PointEau.objects.filter(ouvrage_id=planning.ouvrage_id, parcelle__village__isnull=False)
            .values_list('parcelle__village_id', flat=True).distinct()
        )
    return list(Village.objects.filter(id__in=ids)) if ids else []


def _avec_coordonnees(villages):
    return [v for v in villages if v.latitude is not None and v.longitude is not None]


# --------------------------------------------------------------------------- #
#  Hiérarchie
# --------------------------------------------------------------------------- #
def subordonnes_ids(employe, jour=None):
    """IDs de tous les subordonnés, directs et indirects (relations actives à `jour`)."""
    from apps.employees.models import HierarchieEmploye

    jour = jour or timezone.localdate()
    vus = {employe.id}
    frontiere = [employe.id]
    resultat = []
    while frontiere:
        lignes = (
            HierarchieEmploye.objects.filter(superieur_id__in=frontiere, date_debut__lte=jour)
            .filter(Q(date_fin__isnull=True) | Q(date_fin__gte=jour))
            .values_list('employe_id', flat=True)
        )
        frontiere = []
        for eid in lignes:
            if eid not in vus:
                vus.add(eid)
                resultat.append(eid)
                frontiere.append(eid)
    return resultat


# --------------------------------------------------------------------------- #
#  Enregistrement d'un pointage
# --------------------------------------------------------------------------- #
@dataclass
class ResultatPointage:
    pointage: PointageGPS
    ok: bool
    code: str
    message: str
    distance_m: Optional[float] = None
    deja_pointe: bool = False


def _refuser(employe, statut, message, *, ts, hors_ligne, local_uuid, latitude, longitude,
             precision_m, simule, type_=None, planning=None, distance_m=None, village=None):
    p = PointageGPS.objects.create(
        employe=employe, planning=planning, village_retenu=village, timestamp=ts,
        latitude=latitude, longitude=longitude, precision_m=precision_m, distance_m=distance_m,
        type_pointage=type_, statut_validation=statut, hors_ligne=hors_ligne,
        position_simulee=simule, local_uuid=local_uuid,
    )
    return ResultatPointage(p, False, statut, message, distance_m)


def enregistrer_pointage(employe, latitude, longitude, precision_m=None, position_simulee=False,
                         captured_at=None, local_uuid=None) -> ResultatPointage:
    """Valide et enregistre un pointage. `captured_at` (aware) = capture hors ligne.

    Idempotent sur `local_uuid` : une resynchronisation renvoie le résultat déjà connu.
    Toute tentative est conservée, y compris les refus.
    """
    if local_uuid:
        existant = PointageGPS.objects.filter(local_uuid=local_uuid).first()
        if existant:
            ok = existant.statut_validation == PointageGPS.STATUT_VALIDE
            return ResultatPointage(existant, ok, existant.statut_validation,
                                    "Pointage déjà synchronisé.", existant.distance_m, deja_pointe=ok)

    maintenant = timezone.now()
    hors_ligne = captured_at is not None
    ts = captured_at if hors_ligne else maintenant
    commun = dict(ts=ts, hors_ligne=hors_ligne, local_uuid=local_uuid, latitude=latitude,
                  longitude=longitude, precision_m=precision_m, simule=position_simulee)

    # 1. Position exploitable ?
    try:
        lat, lng = float(latitude), float(longitude)
        coords_valides = -90 <= lat <= 90 and -180 <= lng <= 180
    except (TypeError, ValueError):
        coords_valides = False
    if not coords_valides:
        commun.update(latitude=None, longitude=None)
        return _refuser(employe, PointageGPS.STATUT_REFUSE_GPS, "Position GPS invalide. Réessayez.", **commun)
    if position_simulee:
        return _refuser(employe, PointageGPS.STATUT_REFUSE_GPS,
                        "Position simulée détectée : désactivez l'application de fausse position.", **commun)
    if precision_m is not None and precision_m > PRECISION_MAX_M:
        return _refuser(employe, PointageGPS.STATUT_REFUSE_GPS,
                        f"Signal GPS trop imprécis (±{int(precision_m)} m). Sortez à découvert et réessayez.", **commun)

    # 2. Créneau horaire (heure de Madagascar)
    if hors_ligne and not (maintenant - HORS_LIGNE_MAX_AGE <= ts <= maintenant + HORS_LIGNE_MAX_FUTUR):
        return _refuser(employe, PointageGPS.STATUT_REFUSE_HORAIRE,
                        "Horodatage de l'appareil incohérent : pointage hors ligne rejeté.", **commun)
    local = ts.astimezone(tz_madagascar)
    type_ = creneau_pour(local.time())
    if type_ is None:
        return _refuser(
            employe, PointageGPS.STATUT_REFUSE_HORAIRE,
            "Pointage impossible à cette heure. Créneaux : matinée 10h-12h, après-midi 15h-18h, nuitée 19h-21h.",
            **commun)
    commun['type_'] = type_

    # 3. Planning du jour
    plannings = plannings_du_jour(employe, local.date())
    if not plannings:
        return _refuser(employe, PointageGPS.STATUT_REFUSE_SANS_PLANNING,
                        "Aucun planning enregistré pour vous aujourd'hui.", **commun)
    plannings = [pl for pl in plannings if pointage_applicable(pl)]
    if not plannings:
        return _refuser(employe, PointageGPS.STATUT_REFUSE_SANS_PLANNING,
                        "Pas de pointage aujourd'hui : vos plannings sont sur des ouvrages sans pointage "
                        "(bureau, terrain, ouvrage suspendu…).", **commun)

    # 4. Distance au(x) village(s) de chaque planning
    champ_prevu = CRENEAU_PAR_TYPE[type_][3]
    candidats = []  # (planning, village, distance)
    sans_coord = None
    for pl in plannings:
        villages = _avec_coordonnees(villages_du_planning(pl))
        if not villages:
            sans_coord = sans_coord or pl
            continue
        village, dist = min(
            ((v, haversine_m(lat, lng, v.latitude, v.longitude)) for v in villages), key=lambda x: x[1])
        candidats.append((pl, village, dist))

    if not candidats:
        return _refuser(employe, PointageGPS.STATUT_REFUSE_SANS_COORD,
                        "Les coordonnées GPS du village de votre planning ne sont pas renseignées. "
                        "Votre supérieur en est informé.", planning=sans_coord, **commun)

    proches = [c for c in candidats if c[2] <= DISTANCE_MAX_M]
    if not proches:
        pl, village, dist = min(candidats, key=lambda c: c[2])
        return _refuser(employe, PointageGPS.STATUT_REFUSE_DISTANCE,
                        f"Vous êtes à {_formater_distance(dist)} du site ({village.nom_village}). "
                        f"Rapprochez-vous à moins de 3 km pour pointer.",
                        planning=pl, distance_m=dist, village=village, **commun)

    # Préfère le planning où ce créneau est déclaré, puis le plus proche.
    pl, village, dist = min(proches, key=lambda c: (not getattr(c[0], champ_prevu), c[2]))

    try:
        with transaction.atomic():
            p = PointageGPS.objects.create(
                employe=employe, planning=pl, village_retenu=village, timestamp=ts,
                latitude=latitude, longitude=longitude, precision_m=precision_m, distance_m=dist,
                type_pointage=type_, statut_validation=PointageGPS.STATUT_VALIDE,
                hors_ligne=hors_ligne, position_simulee=False, local_uuid=local_uuid,
            )
            # Pointer vaut déclaration : la case « prévu » du créneau est cochée automatiquement
            # (l'app ne demande plus de cocher avant de pointer).
            if not getattr(pl, champ_prevu):
                setattr(pl, champ_prevu, True)
                pl.save(update_fields=[champ_prevu, 'updated_at'])
    except IntegrityError:
        # Créneau déjà pointé sur ce planning (contrainte partielle) : on renvoie l'existant.
        existant = PointageGPS.objects.get(
            planning=pl, type_pointage=type_, statut_validation=PointageGPS.STATUT_VALIDE)
        return ResultatPointage(existant, True, PointageGPS.STATUT_VALIDE,
                                f"{CRENEAU_PAR_TYPE[type_][4]} déjà pointée.", existant.distance_m,
                                deja_pointe=True)

    return ResultatPointage(p, True, PointageGPS.STATUT_VALIDE,
                            f"{CRENEAU_PAR_TYPE[type_][4]} pointée ({village.nom_village}, "
                            f"à {_formater_distance(dist)}).", dist)


# --------------------------------------------------------------------------- #
#  Suivi (jour) — employé et supérieurs
# --------------------------------------------------------------------------- #
def _statut_creneau(jour, prevu, valide, debut, fin, maintenant_local):
    if valide:
        return 'ok'
    if not prevu:
        return 'non_prevu'
    if jour < maintenant_local.date():
        return 'manque'
    if jour > maintenant_local.date():
        return 'a_venir'
    heure = maintenant_local.time()
    if heure > fin:
        return 'manque'
    return 'en_cours' if heure >= debut else 'a_venir'


def synthese_employe_jour(employe, jour, maintenant=None):
    """Plannings du jour avec l'état de chaque créneau : ok / manque / en_cours / a_venir / non_prevu."""
    maintenant_local = (maintenant or timezone.now()).astimezone(tz_madagascar)
    plannings = plannings_du_jour(employe, jour)
    valides = {}
    if plannings:
        for p in PointageGPS.objects.filter(
                planning__in=plannings, statut_validation=PointageGPS.STATUT_VALIDE):
            valides[(p.planning_id, p.type_pointage)] = p

    items = []
    for pl in plannings:
        villages = villages_du_planning(pl)
        requis = pointage_applicable(pl)
        creneaux = []
        for type_, debut, fin, champ, label in CRENEAUX:
            pointage = valides.get((pl.id, type_))
            prevu = requis and bool(getattr(pl, champ))
            creneaux.append({
                'type': type_,
                'label': label,
                'prevu': prevu,
                'fenetre': f"{debut:%Hh%M}-{fin:%Hh%M}",
                'statut': (_statut_creneau(jour, prevu, pointage, debut, fin, maintenant_local)
                           if requis or pointage else 'non_requis'),
                'heure': pointage.timestamp.astimezone(tz_madagascar).strftime('%H:%M') if pointage else None,
                'hors_ligne': bool(pointage and pointage.hors_ligne),
            })
        items.append({
            'planning_id': str(pl.id),
            # Seul le propriétaire du planning peut déclarer ses créneaux prévus.
            'proprietaire': pl.employe_id == employe.id,
            # Pas de pointage sur un ouvrage de type « n'existe pas » (bureau, terrain…).
            'pointage_requis': requis,
            'type_ouvrage': (pl.ouvrage.type_ouvrage.nom_type_ouvrage
                             if pl.ouvrage_id and pl.ouvrage.type_ouvrage_id else ''),
            # Planning validé : ni annulation, ni changement d'activité ou d'ouvrage
            # (seuls la date et l'employé peuvent changer).
            'valide': bool(pl.estvalide),
            'date': pl.date.astimezone(tz_madagascar).date().isoformat(),
            'employe_id': str(pl.employe_id) if pl.employe_id else '',
            'activite': pl.activite_display,
            'ouvrage': pl.ouvrage_nom if pl.ouvrage_id else '',
            # Valeurs actuelles, pour que l'app puisse modifier le planning depuis Pointage
            # (POST /plannings/api/mobile/planning/enregistrer/ réécrit tous ces champs).
            'ouvrage_id': str(pl.ouvrage_id) if pl.ouvrage_id else '',
            'fiche_poste_id': str(pl.fiche_poste_id) if pl.fiche_poste_id else '',
            'statut': pl.statut or 'en_cours',
            'remarque': pl.remarque or '',
            'villages': [
                {'id': str(v.id), 'nom': v.nom_village,
                 'lat': float(v.latitude) if v.latitude is not None else None,
                 'lng': float(v.longitude) if v.longitude is not None else None}
                for v in villages
            ],
            'creneaux': creneaux,
        })
    return items


def synthese_equipe_jour(employe, jour, maintenant=None):
    """Synthèse de l'employé + de tous ses subordonnés (directs et indirects)."""
    from apps.employees.models import Employe

    ids = subordonnes_ids(employe, jour)
    equipe = [employe] + list(Employe.objects.filter(id__in=ids).order_by('surnom'))
    lignes = []
    for e in equipe:
        plannings = synthese_employe_jour(e, jour, maintenant)
        creneaux = [c for pl in plannings for c in pl['creneaux']]
        lignes.append({
            'employe_id': str(e.id),
            'surnom': _nom(e),
            'moi': e.id == employe.id,
            'plannings': plannings,
            'nb_prevus': sum(1 for c in creneaux if c['prevu']),
            'nb_ok': sum(1 for c in creneaux if c['statut'] == 'ok'),
            'nb_manques': sum(1 for c in creneaux if c['statut'] == 'manque'),
        })
    return lignes


def calendrier_prevus(employe, jour_debut, nb_jours=8):
    """Créneaux déclarés prévus pour les `nb_jours` jours à partir de `jour_debut`.

    Sert aux rappels locaux du téléphone : `[{'date': 'AAAA-MM-JJ', 'matin': bool, ...}]`.
    Un jour sans aucun créneau prévu est omis.
    """
    resultat = []
    for i in range(nb_jours):
        jour = jour_debut + timedelta(days=i)
        plannings = plannings_du_jour(employe, jour)
        prevus = {
            type_: any(getattr(pl, champ) for pl in plannings if pointage_applicable(pl))
            for type_, _d, _f, champ, _l in CRENEAUX
        }
        if any(prevus.values()):
            resultat.append({'date': jour.isoformat(), **prevus})
    return resultat


# --------------------------------------------------------------------------- #
#  Rapport mensuel par employé
# --------------------------------------------------------------------------- #
def _etat_rapport(prevu, pointage):
    if pointage:
        return 'OK'
    return 'Non OK' if prevu else '—'


def rapport_mensuel(employe, annee, mois):
    """Lignes du rapport : Date, Village(s), Activité, Matinée, Après-midi, Nuitée, Total validés."""
    debut = tz_madagascar.localize(datetime(annee, mois, 1))
    fin = tz_madagascar.localize(datetime(annee + (mois == 12), (mois % 12) + 1, 1))
    plannings = list(
        Planning.objects.filter(date__gte=debut, date__lt=fin)
        .filter(Q(employe=employe) | Q(planning_employees__employee=employe))
        .exclude(statut='annule')
        .select_related('ouvrage__type_ouvrage', 'fiche_poste', 'type_activite', 'cible_point_eau__parcelle')
        .distinct().order_by('date')
    )
    valides = {
        (p.planning_id, p.type_pointage): p
        for p in PointageGPS.objects.filter(
            planning__in=plannings, statut_validation=PointageGPS.STATUT_VALIDE)
    }
    lignes = []
    for pl in plannings:
        requis = pointage_applicable(pl)
        etats = {t: _etat_rapport(requis and getattr(pl, champ), valides.get((pl.id, t)))
                 for t, _d, _f, champ, _l in CRENEAUX}
        lignes.append({
            'date': pl.date.astimezone(tz_madagascar).date(),
            'villages': ', '.join(sorted(v.nom_village for v in villages_du_planning(pl))) or '—',
            'activite': pl.activite_display,
            'matin': etats[PointageGPS.TYPE_MATIN],
            'aprem': etats[PointageGPS.TYPE_APREM],
            'nuit': etats[PointageGPS.TYPE_NUIT],
            'total_valides': sum(1 for t, *_ in CRENEAUX if (pl.id, t) in valides),
        })
    return lignes


def calculer_fiche_indemnite(lignes, tarif_demi_journee, tarif_nuitee):
    """Fiche d'indemnité du mois à partir des lignes de `rapport_mensuel`.

    Seuls les pointages VALIDÉS sont indemnisés : une demi-journée par matinée ou après-midi
    validé, une nuitée par nuit validée. Les jours sans pointage validé ne figurent pas au détail.
    """
    from decimal import Decimal

    tarif_dj, tarif_nuit = Decimal(tarif_demi_journee or 0), Decimal(tarif_nuitee or 0)
    detail = []
    for l in lignes:
        demi = (l['matin'] == 'OK') + (l['aprem'] == 'OK')
        nuits = 1 if l['nuit'] == 'OK' else 0
        if not (demi or nuits):
            continue
        detail.append({
            **l, 'demi_journees': demi, 'nuitees': nuits,
            'montant': demi * tarif_dj + nuits * tarif_nuit,
        })
    nb_demi = sum(d['demi_journees'] for d in detail)
    nb_nuits = sum(d['nuitees'] for d in detail)
    prevus = sum(1 for l in lignes for k in ('matin', 'aprem', 'nuit') if l[k] in ('OK', 'Non OK'))
    valides = sum(1 for l in lignes for k in ('matin', 'aprem', 'nuit') if l[k] == 'OK')
    return {
        'detail': detail,
        'tarif_demi_journee': tarif_dj,
        'tarif_nuitee': tarif_nuit,
        'nb_demi_journees': nb_demi,
        'nb_nuitees': nb_nuits,
        'montant_demi_journees': nb_demi * tarif_dj,
        'montant_nuitees': nb_nuits * tarif_nuit,
        'montant_total': nb_demi * tarif_dj + nb_nuits * tarif_nuit,
        'creneaux_prevus': prevus,
        'creneaux_non_pointes': prevus - valides,
    }
