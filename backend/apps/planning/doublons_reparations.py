"""
Compteur de doublons pour les réparations / réhabilitations / maçonnerie.

Pour une activité donnée, on compte les interventions DÉJÀ RÉALISÉES qui portent sur la même cible
(équipement ou point d'eau) avec la même activité, et on signale si la plus récente date de moins
de SEUIL_MOIS mois (par rapport à la date de l'activité affichée).

Règles (à ajuster ici uniquement) :
  - périmètre  : types d'activité dont le nom contient un des TYPES_MOTS_CLES ;
  - réalisée   : estvalide=True ou statut='termine' (et pas 'annule') ;
  - même cible : cible_equipement / cible_point_eau, sinon l'unique cible des lignes de matériel ;
  - même activité : même fiche de poste ; si les deux interventions précisent des composants,
    elles doivent en partager au moins un ;
  - une intervention n'est jamais son propre doublon, et seules celles datées au plus tard de
    l'activité affichée comptent (« déjà réalisées »).
"""
import logging

import pytz
from dateutil.relativedelta import relativedelta
from django.db.models import Prefetch, Q
from django.utils import timezone

from apps.planning.models import Planning, PlanningDetail, TypeActivite
from apps.planning.repair_classification import normalize_repair_text

logger = logging.getLogger(__name__)
TZ_MADAGASCAR = pytz.timezone('Indian/Antananarivo')
SEUIL_MOIS = 3
TYPES_MOTS_CLES = ('reparation', 'rehabilitation', 'maconnerie')


def type_eligible(type_name):
    """Vrai pour « Réparation », « Réhabilitation », « Réparation maçonnerie »… (pas « Préparation »)."""
    text = normalize_repair_text(type_name)
    if not text or 'preparation' in text:
        return False
    return any(keyword in text for keyword in TYPES_MOTS_CLES)


def eligible_type_ids():
    return [t.id for t in TypeActivite.objects.all() if type_eligible(t.nomtype)]


def local_date(value):
    if value is None:
        return None
    if timezone.is_aware(value):
        value = value.astimezone(TZ_MADAGASCAR)
    return value.date()


def resolve_target(planning):
    """('eq'|'pe', id) ou None ; le planning doit avoir ses `details` préchargés."""
    if planning.cible_equipement_id:
        return 'eq', planning.cible_equipement_id
    if planning.cible_point_eau_id:
        return 'pe', planning.cible_point_eau_id
    equipements, points = set(), set()
    for detail in planning.details.all():
        if detail.equipement_constitutif_id:
            equipements.add(detail.equipement_constitutif_id)
        if detail.point_eau_id:
            points.add(detail.point_eau_id)
    if len(equipements) == 1 and not points:
        return 'eq', next(iter(equipements))
    if len(points) == 1 and not equipements:
        return 'pe', next(iter(points))
    return None


def composant_ids(planning):
    return (
        {str(c.pk) for c in planning.composants_equipement.all()}
        | {str(c.pk) for c in planning.composants_point_eau.all()}
    )


def is_recent(dernier, reference, mois=SEUIL_MOIS):
    """La dernière intervention date de moins de `mois` mois avant `reference`."""
    return bool(dernier and reference and dernier > reference - relativedelta(months=mois))


def summarize(own_date, matches, own_composants=()):
    """
    matches : [(date, composants:set)] des interventions réalisées sur la même cible et activité,
    déjà exclues celles postérieures à own_date et l'intervention elle-même.
    """
    own = set(own_composants)
    kept = [d for d, comps in matches if not own or not comps or own & comps]
    dernier = max(kept) if kept else None
    return {
        'nb': len(kept),
        'dernier_date': dernier.isoformat() if dernier else None,
        'dernier_display': dernier.strftime('%d/%m/%Y') if dernier else '',
        'recent': is_recent(dernier, own_date),
        'seuil_mois': SEUIL_MOIS,
    }


def _with_related(queryset):
    return queryset.select_related('fiche_poste', 'type_activite').prefetch_related(
        Prefetch('details', queryset=PlanningDetail.objects.only(
            'id', 'planning_id', 'equipement_constitutif_id', 'point_eau_id')),
        'composants_equipement', 'composants_point_eau',
    )


def calculer_doublons(planning_ids):
    """
    {planning_id (str): {'nb', 'dernier_date', 'dernier_display', 'recent', 'seuil_mois'}}
    uniquement pour les activités du périmètre dont on connaît la cible.
    """
    ids = [i for i in dict.fromkeys(planning_ids) if i]
    type_ids = eligible_type_ids() if ids else []
    if not ids or not type_ids:
        return {}

    own = []
    for planning in _with_related(Planning.objects.filter(id__in=ids).filter(
            Q(fiche_poste__type_activites_id__in=type_ids)
            | Q(fiche_poste__isnull=True, type_activite_id__in=type_ids))):
        target = resolve_target(planning)
        own_date = local_date(planning.date)
        if planning.fiche_poste_id and target and own_date:
            own.append((planning, target, own_date))
    if not own:
        return {}

    fiche_ids = {p.fiche_poste_id for p, _, _ in own}
    equipements = {t[1] for _, t, _ in own if t[0] == 'eq'}
    points = {t[1] for _, t, _ in own if t[0] == 'pe'}
    realisees = _with_related(
        Planning.objects.filter(fiche_poste_id__in=fiche_ids)
        .filter(Q(estvalide=True) | Q(statut='termine'))
        .exclude(statut='annule')
        .filter(
            Q(cible_equipement_id__in=equipements) | Q(cible_point_eau_id__in=points)
            | Q(details__equipement_constitutif_id__in=equipements)
            | Q(details__point_eau_id__in=points)
        ).distinct()
    )
    index = {}
    for planning in realisees:
        target = resolve_target(planning)
        date_ = local_date(planning.date)
        if target and date_:
            index.setdefault((planning.fiche_poste_id, target), []).append(
                (planning.id, date_, composant_ids(planning)))

    result = {}
    for planning, target, own_date in own:
        matches = [
            (date_, comps) for pid, date_, comps in index.get((planning.fiche_poste_id, target), [])
            if pid != planning.id and date_ <= own_date
        ]
        result[str(planning.id)] = summarize(own_date, matches, composant_ids(planning))
    return result


def calculer_doublons_securise(planning_ids):
    """Comme calculer_doublons, mais une panne du compteur ne doit jamais casser la page appelante."""
    try:
        return calculer_doublons(list(planning_ids))
    except Exception:  # noqa: BLE001 - fonctionnalité secondaire, on journalise et on continue
        logger.exception("Calcul du compteur de doublons impossible")
        return {}
