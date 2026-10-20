"""Statut de branchement d'un point d'eau — règle unique partagée par les pages
Points d'eau consolidés, points d'eau d'un ouvrage, liste des ouvrages, dashboard
et widget.

- actif      : date de branchement renseignée, pas de date d'arrêt → seul statut
               compté comme point d'eau existant ;
- coupe      : date de branchement ET date d'arrêt de branchement depuis moins
               d'un an → compté à part ;
- abandonne  : coupé depuis ``ABANDON_JOURS`` jours ou plus (sans remise en eau)
               → considéré comme abandonné, compté à part des coupés ;
- sans_date  : pas de date de branchement → mis à part, jamais compté comme
               existant (même s'il a une date d'arrêt).

Même seuil (365 jours) que la règle de ``CoupureEau.sync_specific_point_eau``
qui retire le tarif forfaitaire d'un point coupé depuis plus d'un an.
"""
from datetime import datetime, timedelta

from django.db.models import Case, CharField, Count, Q, Value, When
from django.utils import timezone

STATUT_ACTIF = 'actif'
STATUT_COUPE = 'coupe'
STATUT_ABANDONNE = 'abandonne'
STATUT_SANS_DATE = 'sans_date'

ABANDON_JOURS = 365

STATUT_LABELS = {
    STATUT_ACTIF: 'Actif',
    STATUT_COUPE: 'Coupé',
    STATUT_ABANDONNE: 'Abandonné (coupé depuis plus d\'un an)',
    STATUT_SANS_DATE: 'Sans date de branchement',
}


def date_limite_abandon(reference=None):
    """Jour limite : une coupure à cette date ou avant = point abandonné.

    ``reference`` (date) permet de raisonner « à la date de » (ex. fin d'année
    d'un filtre du dashboard) ; par défaut aujourd'hui.
    """
    reference = reference or timezone.localdate()
    return reference - timedelta(days=ABANDON_JOURS)


def _limite_datetime(reference=None):
    """Limite en datetime aware, pour comparer à ``datearretbranchement`` (DateTimeField).

    Les coupures du jour limite (inclus) comptent comme abandonnées : on compare
    donc strictement au lendemain de la limite, à minuit.
    """
    limite = date_limite_abandon(reference) + timedelta(days=1)
    return timezone.make_aware(datetime.combine(limite, datetime.min.time()))


def est_abandonne_depuis(date_arret, reference=None):
    """True si une date d'arrêt (date ou datetime) est assez ancienne."""
    if not date_arret:
        return False
    if isinstance(date_arret, datetime):
        date_arret = timezone.localtime(date_arret).date() if timezone.is_aware(date_arret) else date_arret.date()
    return date_arret <= date_limite_abandon(reference)


def q_actif(prefix=''):
    return Q(**{f'{prefix}datebranchement__isnull': False, f'{prefix}datearretbranchement__isnull': True})


def q_coupe(prefix=''):
    """Coupé récemment (moins d'un an) ; au-delà : voir ``q_abandonne``."""
    return Q(**{
        f'{prefix}datebranchement__isnull': False,
        f'{prefix}datearretbranchement__isnull': False,
        f'{prefix}datearretbranchement__gte': _limite_datetime(),
    })


def q_abandonne(prefix=''):
    """Coupé depuis ``ABANDON_JOURS`` jours ou plus."""
    return Q(**{
        f'{prefix}datebranchement__isnull': False,
        f'{prefix}datearretbranchement__isnull': False,
        f'{prefix}datearretbranchement__lt': _limite_datetime(),
    })


def q_sans_date(prefix=''):
    return Q(**{f'{prefix}datebranchement__isnull': True})


def statut_expression():
    """Expression ORM à annoter : ``.annotate(statut_branchement=statut_expression())``."""
    return Case(
        When(datebranchement__isnull=True, then=Value(STATUT_SANS_DATE)),
        When(datearretbranchement__isnull=True, then=Value(STATUT_ACTIF)),
        When(datearretbranchement__lt=_limite_datetime(), then=Value(STATUT_ABANDONNE)),
        default=Value(STATUT_COUPE),
        output_field=CharField(),
    )


def statut_of(point):
    """Statut d'une instance PointEau déjà chargée."""
    if not point.datebranchement:
        return STATUT_SANS_DATE
    if point.datearretbranchement:
        if est_abandonne_depuis(point.datearretbranchement):
            return STATUT_ABANDONNE
        return STATUT_COUPE
    return STATUT_ACTIF


def filtrer_points_annee(points_eau_qs, annee_int):
    """Périmètre des points d'eau pour un filtre « année » cumulatif (situation au 31/12).

    Garde les points branchés en ``annee_int`` ou avant, QUEL QUE SOIT leur état de coupure :
    coupés et abandonnés à cette date sont classés à part (historique CoupureEau), ils ne
    doivent pas disparaître du périmètre. Les points sans date de branchement sont gardés
    pour être comptés à part ; ils ne sont jamais comptés comme points d'eau.
    """
    from django.db.models.functions import ExtractYear

    return points_eau_qs.annotate(
        annee_branchement=ExtractYear('datebranchement'),
    ).filter(Q(datebranchement__isnull=True) | Q(annee_branchement__lte=annee_int))


def compter_statuts(points_eau_qs):
    """{'actifs', 'coupes', 'abandonnes', 'sans_date'} en une seule requête."""
    return points_eau_qs.order_by().aggregate(
        actifs=Count('id', filter=q_actif()),
        coupes=Count('id', filter=q_coupe()),
        abandonnes=Count('id', filter=q_abandonne()),
        sans_date=Count('id', filter=q_sans_date()),
    )
