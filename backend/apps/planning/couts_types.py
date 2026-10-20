"""
Recherche et application des coûts types (voir models_couts_types).

Un planning de réparation / installation / réhabilitation porte une activité
(fiche_poste), une cible (équipement OU point d'eau) et des composants. Le coût
type correspondant pré-remplit ses PlanningDetail, que l'on ajuste ensuite.
"""
from decimal import Decimal

from django.db import transaction

from apps.planning.models import PlanningDetail
from apps.planning.models_couts_types import CoutTypeActivite


def cible_du_planning(planning):
    """(equipement, point_eau, composants) de la cible du planning."""
    if planning.cible_equipement_id:
        return planning.cible_equipement, None, list(planning.composants_equipement.all())
    if planning.cible_point_eau_id:
        return None, planning.cible_point_eau, list(planning.composants_point_eau.all())
    return None, None, []


def trouver_couts_types_cible(fiche_id, equipement, point_eau, composants):
    """
    Coûts types applicables à une activité sur une cible, du plus précis au plus général.

    Un coût type par composant indiqué s'il en existe (un composant sans barème propre
    est simplement ignoré) ; à défaut, le coût type de l'activité et du type de cible
    sans composant.
    """
    if not fiche_id or not (equipement or point_eau):
        return []
    base = CoutTypeActivite.objects.filter(fiche_poste_id=fiche_id, actif=True)
    if equipement:
        if not equipement.type_equipement_id:
            return []
        base = base.filter(type_equipement_id=equipement.type_equipement_id)
        champ_composant = 'composant_equipement'
    else:
        if not point_eau.type_point_eau_id:
            return []
        base = base.filter(type_point_eau_id=point_eau.type_point_eau_id)
        champ_composant = 'composant_point_eau'
    base = base.prefetch_related('lignes__designation')

    if composants:
        par_composant = list(base.filter(**{f'{champ_composant}__in': composants}))
        if par_composant:
            return par_composant
    return list(base.filter(**{f'{champ_composant}__isnull': True}))


def trouver_couts_types(planning):
    """Coûts types applicables à un planning (activité, cible et composants enregistrés)."""
    equipement, point_eau, composants = cible_du_planning(planning)
    return trouver_couts_types_cible(planning.fiche_poste_id, equipement, point_eau, composants)


def fusionner_lignes(couts_types):
    """
    Fusionne les lignes de plusieurs coûts types en une liste unique de désignations.

    Retourne une liste de dicts {'designation': Designation, 'quantite': Decimal, 'pu': Decimal}.
    Plusieurs coûts types arrivent quand le planning concerne plusieurs composants ;
    une même désignation (ex. « Ciment ») peut alors figurer dans plusieurs barèmes.
    """
    # Une désignation présente dans plusieurs coûts types : les quantités s'additionnent
    # (chaque composant correspond à des travaux distincts) ; le PU de la première
    # occurrence est conservé.
    fusion = {}
    for cout_type in couts_types:
        for ligne in cout_type.lignes.all():
            existante = fusion.get(ligne.designation_id)
            if existante:
                existante['quantite'] += ligne.quantite
            else:
                fusion[ligne.designation_id] = {
                    'designation': ligne.designation,
                    'quantite': ligne.quantite,
                    'pu': ligne.pu_effectif,
                }
    return list(fusion.values())


def est_designation_avance(designation):
    """Vrai pour une désignation saisie en « détail (avance) » ; les bons de livraison sont à part."""
    return 'avance' in (designation.type_avance_caissiere or '').lower()


@transaction.atomic
def appliquer_couts_types(planning, remplacer=False):
    """
    Crée les PlanningDetail (avances) issus du coût type.
    Retourne (lignes_creees, deja_presentes, non_reprises).

    - Les désignations déjà présentes dans le planning ne sont jamais écrasées
      (elles ont pu être ajustées selon la réalité) ; remplacer=True supprime d'abord
      les lignes non encore utilisées / retournées.
    - Seules les avances deviennent des PlanningDetail : les bons de livraison (objets
      distincts, avec magasin) et les autres désignations sont renvoyés dans non_reprises.
    """
    lignes = fusionner_lignes(trouver_couts_types(planning))
    if remplacer:
        planning.details.filter(utilise=False, retour=False).delete()
    existantes = set(planning.details.values_list('designation_id', flat=True))

    creees, deja_presentes, non_reprises = [], [], []
    for ligne in lignes:
        designation = ligne['designation']
        if not est_designation_avance(designation):
            non_reprises.append(designation)
            continue
        if designation.id in existantes:
            deja_presentes.append(designation)
            continue
        detail = PlanningDetail(
            planning=planning,
            designation=designation,
            quantity=float(ligne['quantite']),
            pu=Decimal(ligne['pu']),
            equipement_constitutif=planning.cible_equipement,
            point_eau=planning.cible_point_eau,
        )
        detail.save()  # recalcule le montant
        creees.append(detail)
    return creees, deja_presentes, non_reprises
