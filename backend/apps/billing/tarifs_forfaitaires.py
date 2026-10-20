"""Tarifs forfaitaires : tarif plein par type de point d'eau (ConfigTarifForfaitaire) x
pourcentage porté par chaque point d'eau (PointEau.pourcentage_tarif).

``PointEau.tarifforfaitaire`` reste le montant appliqué (en Ar) lu par les nombreuses pages
existantes ; il est maintenu à jour ici à partir du pourcentage.
"""
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone


def _config_model():
    from .models import ConfigTarifForfaitaire
    return ConfigTarifForfaitaire


def tarif_plein(type_point_eau_id, date=None):
    """Tarif plein (Decimal) du type à la date donnée, ou None si aucun tarif configuré."""
    if not type_point_eau_id:
        return None
    date = date or timezone.localdate()
    config = (
        _config_model().objects
        .filter(type_point_eau_id=type_point_eau_id, date_debut__lte=date)
        .filter(Q(date_fin__isnull=True) | Q(date_fin__gte=date))
        .order_by('-date_debut')
        .first()
    )
    return config.tarif if config else None


def calculer_tarif(plein, pourcentage):
    """Montant (float, arrondi à l'Ar) = tarif plein x pourcentage / 100."""
    if plein is None or pourcentage is None:
        return None
    return float(round(Decimal(str(plein)) * Decimal(str(pourcentage)) / Decimal('100')))


def calculer_pourcentage(plein, tarif):
    """Pourcentage (Decimal, 4 décimales) correspondant à un montant ; None si impossible."""
    if plein is None or tarif is None or not Decimal(str(plein)):
        return None
    return (Decimal(str(tarif)) * Decimal('100') / Decimal(str(plein))).quantize(Decimal('0.0001'))


def synchroniser_tarif_point(point_eau):
    """Rend cohérents montant et pourcentage d'un point d'eau avant sauvegarde.

    - montant modifié directement (ancien code, import) : le pourcentage en est déduit ;
    - sinon, pourcentage renseigné : le montant est recalculé (tarif plein en vigueur) ;
    - champs différés (``only()``) : on ne touche à rien.
    Sans tarif plein configuré pour le type, rien n'est modifié.
    """
    donnees = point_eau.__dict__
    if not {'tarifforfaitaire', 'pourcentage_tarif', 'type_point_eau_id'} <= donnees.keys():
        return

    tarif = donnees['tarifforfaitaire']
    pourcentage = donnees['pourcentage_tarif']
    tarif_modifie = tarif != getattr(point_eau, '_tarif_initial', tarif)

    if tarif is None and tarif_modifie:
        point_eau.pourcentage_tarif = None  # montant vidé : le pourcentage l'est aussi
        return
    if tarif is None and pourcentage is None:
        return

    plein = tarif_plein(point_eau.type_point_eau_id)
    if plein is None:
        return

    if tarif is not None and (tarif_modifie or pourcentage is None):
        point_eau.pourcentage_tarif = calculer_pourcentage(plein, tarif)
    else:
        point_eau.tarifforfaitaire = calculer_tarif(plein, pourcentage)


def appliquer_tarifs_forfaitaires(date=None, dry_run=False):
    """Recalcule ``tarifforfaitaire`` de tous les points ayant un pourcentage.

    À lancer après tout changement de ``ConfigTarifForfaitaire`` et chaque jour (un tarif peut
    entrer en vigueur à une date future). Idempotent. Retourne le nombre de points modifiés.
    """
    from .models import PointEau

    date = date or timezone.localdate()
    modifies = 0
    couples = (
        PointEau.objects.filter(pourcentage_tarif__isnull=False, type_point_eau__isnull=False)
        .values_list('type_point_eau_id', 'pourcentage_tarif').distinct()
    )
    plein_par_type = {}
    for type_id, pourcentage in couples:
        if type_id not in plein_par_type:
            plein_par_type[type_id] = tarif_plein(type_id, date)
        plein = plein_par_type[type_id]
        if plein is None:
            continue
        nouveau = calculer_tarif(plein, pourcentage)
        a_modifier = PointEau.objects.filter(
            type_point_eau_id=type_id, pourcentage_tarif=pourcentage
        ).exclude(tarifforfaitaire=nouveau)
        modifies += a_modifier.count() if dry_run else a_modifier.update(tarifforfaitaire=nouveau)
    return modifies


def champs_tarif_depuis_post(post):
    """Champs de tarif à appliquer depuis un formulaire.

    Le formulaire envoie ``pourcentage_tarif`` (vide = tarif supprimé) ; l'ancien champ
    ``tarifforfaitaire`` (montant) reste accepté pour les formulaires non migrés.
    Renvoie un dict utilisable en kwargs (création) ou avec setattr (modification)."""
    if 'pourcentage_tarif' in post:
        brut = (post.get('pourcentage_tarif') or '').strip().replace(',', '.')
        if not brut:
            return {'tarifforfaitaire': None, 'pourcentage_tarif': None}
        try:
            pourcentage = Decimal(brut)
        except ArithmeticError:
            return {}
        if pourcentage < 0:
            return {}
        return {'pourcentage_tarif': pourcentage.quantize(Decimal('0.0001'))}
    brut = (post.get('tarifforfaitaire') or '').strip()
    try:
        return {'tarifforfaitaire': float(brut) if brut else None}
    except ValueError:
        return {}


# --- Historique : tarif d'un point d'eau pour une année donnée -----------------------------
import datetime as _dt
import time as _time

_CACHE_PLEIN = {}
_CACHE_TTL = 60  # secondes : un changement de ConfigTarifForfaitaire est vu partout en 1 min


def _tarif_plein_en_cache(type_point_eau_id, date):
    cle = (type_point_eau_id, date)
    entree = _CACHE_PLEIN.get(cle)
    maintenant = _time.monotonic()
    if entree and maintenant - entree[0] < _CACHE_TTL:
        return entree[1]
    plein = tarif_plein(type_point_eau_id, date)
    _CACHE_PLEIN[cle] = (maintenant, plein)
    return plein


def date_reference_annee(annee):
    """Date à laquelle on lit le tarif d'une année : fin d'année, bornée à aujourd'hui.

    Année en cours (ou future) = aujourd'hui ; année passée = 31 décembre, ce qui fige les
    montants prévus des années closes quand le tarif plein change ensuite."""
    aujourdhui = timezone.localdate()
    try:
        fin = _dt.date(int(annee), 12, 31)
    except (TypeError, ValueError):
        return aujourdhui
    return min(fin, aujourdhui)


def tarif_depuis_valeurs(type_point_eau_id, pourcentage, montant_actuel, annee=None):
    """Version de ``tarif_pour_annee`` pour des lignes ``values()`` (sans instance PointEau)."""
    if pourcentage is not None and type_point_eau_id:
        plein = _tarif_plein_en_cache(type_point_eau_id, date_reference_annee(annee))
        if plein is not None:
            return Decimal(str(calculer_tarif(plein, pourcentage)))
    return Decimal(str(montant_actuel)) if montant_actuel else Decimal('0.00')


def tarif_pour_annee(point_eau, annee=None):
    """Tarif forfaitaire (Decimal) d'un point d'eau pour l'année donnée.

    = tarif plein du type à la date de référence de l'année x pourcentage du point.
    Repli sur le montant stocké (``tarifforfaitaire``) si le point n'a pas de pourcentage ou si
    aucun tarif plein n'est configuré à cette date (aucun changement de comportement alors).
    Le pourcentage actuel est appliqué à toutes les années (son historique n'est pas suivi).
    """
    return tarif_depuis_valeurs(
        point_eau.type_point_eau_id, point_eau.pourcentage_tarif, point_eau.tarifforfaitaire, annee
    )
