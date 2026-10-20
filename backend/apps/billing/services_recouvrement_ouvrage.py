"""Calcul du montant déjà collecté (recouvrement réel) par ouvrage.

Un paiement (forfaitaire ou relevé volumétrique) est considéré réellement
collecté quand il est pointé en comptabilité DiameX, c'est-à-dire quand
``numeroDiameX`` ET ``baseDiameX`` sont renseignés (même critère que la
propriété ``est_paye`` de ces modèles).
"""
from decimal import Decimal

from django.db.models import Q, Sum


def montant_collecte_par_ouvrage(ouvrage_ids):
    """Retourne {ouvrage_id: Decimal(montant collecté)} en sommant les paiements
    forfaitaires et les relevés volumétriques réellement pointés en comptabilité
    pour chaque ouvrage de ``ouvrage_ids``.
    """
    from .models import PaiementForfaitaire, Releve

    ouvrage_ids = [oid for oid in ouvrage_ids if oid]
    resultats = {oid: Decimal('0') for oid in ouvrage_ids}
    if not ouvrage_ids:
        return resultats

    pointe_diamex = (
        Q(numeroDiameX__isnull=False) & ~Q(numeroDiameX='')
        & Q(baseDiameX__isnull=False) & ~Q(baseDiameX='')
    )

    forfaitaires = (
        PaiementForfaitaire.objects
        .filter(point_eau__ouvrage_id__in=ouvrage_ids)
        .filter(pointe_diamex)
        .values('point_eau__ouvrage_id')
        .annotate(total=Sum('montant'))
    )
    for row in forfaitaires:
        oid = row['point_eau__ouvrage_id']
        resultats[oid] = resultats.get(oid, Decimal('0')) + (row['total'] or Decimal('0'))

    volumetriques = (
        Releve.objects
        .filter(point_eau__ouvrage_id__in=ouvrage_ids)
        .filter(pointe_diamex)
        .values('point_eau__ouvrage_id')
        .annotate(total=Sum('montant'))
    )
    for row in volumetriques:
        oid = row['point_eau__ouvrage_id']
        resultats[oid] = resultats.get(oid, Decimal('0')) + (row['total'] or Decimal('0'))

    return resultats
