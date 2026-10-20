from __future__ import annotations

import unicodedata

from apps.billing.models import Releve, TypePointEau


MODALITE_KEYS = (
    'forfaitaire',
    'au_volume',
    'mixte',
    'cotisation_annuelle',
    'sans_modalite',
)

POINT_USAGE_KEYS = (
    'prive',
    'public',
)

POINT_USAGE_MODALITY_KEYS = (
    'prives_au_volume',
    'prives_forfaitaire',
    'prives_sans_modalite',
    'publics_au_volume',
    'publics_forfaitaire',
    'publics_sans_modalite',
)


def _normalize_ascii_upper(value):
    normalized = unicodedata.normalize('NFKD', str(value or ''))
    return normalized.encode('ascii', 'ignore').decode('ascii').upper()


def is_private_point_type_name(type_name, est_institutionnel=False):
    """Un point est privé s'il est de type BP (ou « privé ») et n'est pas un branchement
    institutionnel : l'ancien type « BI volume » est désormais BP + institutionnel et reste
    public."""
    if est_institutionnel:
        return False

    normalized = _normalize_ascii_upper(type_name)
    compact = ''.join(normalized.split())
    if not compact:
        return False

    return compact == 'BP' or 'PRIVE' in normalized


def private_point_type_ids():
    """IDs des types de point d'eau privés (même règle que ``is_private_point_type_name``),
    utilisables dans un filtre ORM ``type_point_eau_id__in``.

    Les branchements institutionnels sont à exclure en plus :
    ``Q(type_point_eau_id__in=ids, estbranchementinstitutionnel=False)``."""
    return [
        type_id
        for type_id, type_name in TypePointEau.objects.values_list('id', 'nom_type')
        if is_private_point_type_name(type_name)
    ]


def build_payment_modality_scope(points_eau_qs, annee=None):
    points_scope_qs = points_eau_qs.filter(ouvrage_id__isnull=False).distinct()
    point_ids_qs = points_scope_qs.values_list('id', flat=True)

    releves_qs = Releve.objects.filter(
        point_eau_id__in=point_ids_qs,
        montant__gt=0,
    )
    if annee:
        try:
            releves_qs = releves_qs.filter(datereleve__year__lte=int(annee))
        except (TypeError, ValueError):
            pass

    volume_releve_point_ids = set(releves_qs.values_list('point_eau_id', flat=True).distinct())

    # Un seul passage sur le périmètre (au lieu de six requêtes) : classement point par point
    volume_point_ids = set()
    forfait_point_ids = set()
    sans_modalite_point_ids = set()
    volume_ouvrage_ids = set()
    forfait_ouvrage_ids = set()
    ouvrage_by_sans_modalite_point = {}
    for point_id, ouvrage_id, tarif in points_scope_qs.order_by().values_list(
        'id', 'ouvrage_id', 'tarifforfaitaire'
    ).distinct():
        if point_id in volume_releve_point_ids:
            volume_point_ids.add(point_id)
            volume_ouvrage_ids.add(ouvrage_id)
        elif tarif is not None and tarif > 0:
            forfait_point_ids.add(point_id)
            forfait_ouvrage_ids.add(ouvrage_id)
        else:
            sans_modalite_point_ids.add(point_id)
            ouvrage_by_sans_modalite_point[point_id] = ouvrage_id

    volume_ouvrage_ids.discard(None)
    forfait_ouvrage_ids.discard(None)

    mixte_ouvrage_ids = forfait_ouvrage_ids & volume_ouvrage_ids
    sans_modalite_ouvrage_ids = {
        ouvrage_id for ouvrage_id in ouvrage_by_sans_modalite_point.values()
        if ouvrage_id not in forfait_ouvrage_ids and ouvrage_id not in volume_ouvrage_ids
    }
    sans_modalite_ouvrage_ids.discard(None)

    return {
        'point_ids': {
            'forfaitaire': forfait_point_ids,
            'au_volume': volume_point_ids,
            'mixte': set(),
            'cotisation_annuelle': set(),
            'sans_modalite': sans_modalite_point_ids,
        },
        'ouvrage_ids': {
            'forfaitaire': forfait_ouvrage_ids - mixte_ouvrage_ids,
            'au_volume': volume_ouvrage_ids - mixte_ouvrage_ids,
            'mixte': mixte_ouvrage_ids,
            'cotisation_annuelle': set(),
            'sans_modalite': sans_modalite_ouvrage_ids,
        },
    }


def build_point_usage_modality_breakdown(points_eau_qs, annee=None):
    payment_scope = build_payment_modality_scope(points_eau_qs, annee=annee)

    point_ids_by_modality = payment_scope['point_ids']
    scoped_point_ids = set()
    for point_ids in point_ids_by_modality.values():
        scoped_point_ids.update(point_ids)

    private_point_ids = set()
    if scoped_point_ids:
        for point_id, type_name, est_inst in points_eau_qs.filter(
            id__in=scoped_point_ids
        ).values_list('id', 'type_point_eau__nom_type', 'estbranchementinstitutionnel'):
            if is_private_point_type_name(type_name, est_inst):
                private_point_ids.add(point_id)

    public_point_ids = scoped_point_ids - private_point_ids

    category_point_ids = {
        'prives_au_volume': private_point_ids & point_ids_by_modality['au_volume'],
        'prives_forfaitaire': private_point_ids & point_ids_by_modality['forfaitaire'],
        'prives_sans_modalite': private_point_ids & point_ids_by_modality['sans_modalite'],
        'publics_au_volume': public_point_ids & point_ids_by_modality['au_volume'],
        'publics_forfaitaire': public_point_ids & point_ids_by_modality['forfaitaire'],
        'publics_sans_modalite': public_point_ids & point_ids_by_modality['sans_modalite'],
    }

    return {
        'payment_scope': payment_scope,
        'usage_point_ids': {
            'prive': private_point_ids,
            'public': public_point_ids,
        },
        'category_point_ids': category_point_ids,
        'counts': {
            key: len(point_ids)
            for key, point_ids in category_point_ids.items()
        },
    }
