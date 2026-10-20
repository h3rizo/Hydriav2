"""
Moteur de fusion generique pour le rappel combine paiements non pointes +
reparations echues.

Garantit qu'un destinataire concerne par les deux types de relance dans le
meme cycle recoit UN SEUL email, structure par ouvrage (jamais par type),
avec paiements et reparations d'un meme ouvrage toujours regroupes
ensemble.

Reutilise strictement les fonctions pures existantes de
monthly_billing_reminder.py (paiements) et repair_reminder.py (reparations)
comme fournisseurs de donnees - aucune des deux ne connait l'autre, la
fusion se fait entierement ici.
"""
import uuid
from datetime import date
from decimal import Decimal

from .monthly_billing_reminder import (
    calculer_periode_cible,
    compter_factures_sans_responsable,
    construire_regroupement,
    construire_regroupement_hierarchique,
    date_actuelle_madagascar,
)
from .repair_reminder import (
    compter_reparations_sans_responsable,
    construire_regroupement_hierarchique_reparations,
    construire_regroupement_reparations,
)

NIVEAUX_ORDRE = {'critique': 2, 'attention': 1, 'normal': 0}


def _fusionner_ouvrages_paiements(regroupement_combine_ouvrages, ouvrages_source):
    """Injecte les ouvrages d'une source paiements (structure
    ouvrage_id -> {'ouvrage', 'points_eau'}) dans la structure pivot
    combinee, fusionnant par ouvrage_id."""
    for ouvrage_id, ouvrage_entree in ouvrages_source.items():
        entree = regroupement_combine_ouvrages.setdefault(ouvrage_id, {
            'ouvrage': ouvrage_entree['ouvrage'],
            'points_eau': {},
            'reparations': [],
        })
        for pe_id, pe_entree in ouvrage_entree['points_eau'].items():
            entree_pe = entree['points_eau'].setdefault(pe_id, {
                'point_eau': pe_entree['point_eau'],
                'lignes': [],
            })
            entree_pe['lignes'].extend(pe_entree['lignes'])


def _fusionner_ouvrages_reparations(regroupement_combine_ouvrages, ouvrages_source):
    """Injecte les ouvrages d'une source reparations (structure
    ouvrage_id -> {'ouvrage', 'reparations'}) dans la structure pivot
    combinee, fusionnant par ouvrage_id."""
    for ouvrage_id, ouvrage_entree in ouvrages_source.items():
        entree = regroupement_combine_ouvrages.setdefault(ouvrage_id, {
            'ouvrage': ouvrage_entree['ouvrage'],
            'points_eau': {},
            'reparations': [],
        })
        entree['reparations'].extend(ouvrage_entree['reparations'])


def _fusionner_source_dans_pivot(regroupement_combine, source: dict, est_source_directe: bool, fusionner_ouvrages_fn):
    """
    Fusionne une des 4 sources (paiements-direct, paiements-hierarchie,
    reparations-direct, reparations-hierarchie) dans la structure pivot
    finale par destinataire.

    source a la forme soit {employe_id: {'employe':..., 'ouvrages': {...}}}
    (sources directes) soit {employe_id: {'employe':..., 'subordonnes':
    {sub_id: {'employe':..., 'ouvrages': {...}}}}} (sources hierarchiques).
    """
    for employe_id, entree_source in source.items():
        employe = entree_source['employe']
        entree_pivot = regroupement_combine.setdefault(employe_id, {
            'employe': employe,
            'a_ouvrage_direct': False,
            'ouvrages': {},
        })
        if est_source_directe:
            entree_pivot['a_ouvrage_direct'] = True
            fusionner_ouvrages_fn(entree_pivot['ouvrages'], entree_source['ouvrages'])
        else:
            for sub_entree in entree_source['subordonnes'].values():
                fusionner_ouvrages_fn(entree_pivot['ouvrages'], sub_entree['ouvrages'])


def calculer_niveau_ouvrage(entree_ouvrage: dict) -> str:
    """
    Niveau global d'un ouvrage = le plus critique parmi ses reparations
    presentes. Les paiements ne participent jamais au calcul de criticite
    (decision actee) - un ouvrage n'ayant que des paiements est toujours
    'normal'.
    """
    niveau_max = 'normal'
    for rep_entree in entree_ouvrage['reparations']:
        if NIVEAUX_ORDRE[rep_entree['niveau']] > NIVEAUX_ORDRE[niveau_max]:
            niveau_max = rep_entree['niveau']
    return niveau_max


def _retard_max_ouvrage(entree_ouvrage: dict) -> int:
    """Plus grand jours_retard contenu dans l'ouvrage (0 si aucune
    reparation) - critere de tri secondaire a egalite de niveau."""
    if not entree_ouvrage['reparations']:
        return 0
    return max(rep_entree['jours_retard'] for rep_entree in entree_ouvrage['reparations'])


def trier_ouvrages_par_criticite(ouvrages: dict) -> list:
    """Trie les ouvrages (dict ouvrage_id -> entree) par niveau de
    criticite decroissant, puis a egalite par jours de retard maximum
    decroissant. Retourne une liste d'entrees enrichies avec 'niveau_ouvrage'."""
    entrees = []
    for entree in ouvrages.values():
        niveau = calculer_niveau_ouvrage(entree)
        entrees.append({
            **entree,
            'niveau_ouvrage': niveau,
            '_retard_max': _retard_max_ouvrage(entree),
        })
    entrees.sort(key=lambda e: (NIVEAUX_ORDRE[e['niveau_ouvrage']], e['_retard_max']), reverse=True)
    return entrees


def construire_regroupement_combine(annee: int = None, mois: int = None,
                                     date_reference_reparations: date = None):
    """
    Point d'entree unique de construction (pas d'envoi, pas d'ecriture).

    Retourne (regroupement_combine, annee_cible, mois_cible,
    date_fin_periode, date_reference_reparations, factures_sans_responsable,
    reparations_sans_responsable).

    regroupement_combine a la forme :
    {
        employe_id: {
            'employe': Employe,
            'type_destinataire': 'responsable' | 'superieur',  # calcule
            'ouvrages': {
                ouvrage_id: {
                    'ouvrage': Ouvrage,
                    'points_eau': {pe_id: {'point_eau':..., 'lignes':[...]}},
                    'reparations': [{'reparation':..., 'jours_retard':..., 'niveau':...}],
                },
            },
        },
    }

    type_destinataire est calcule (pas assigne a priori) : 'responsable' des
    qu'au moins un ouvrage provient d'une source directe (paiement ou
    reparation), sinon 'superieur'. Un meme destinataire ne peut avoir
    qu'UNE SEULE entree dans cette structure, garantissant la dedup stricte
    (contrainte 9) meme s'il est concerne par plusieurs des 4 sources.
    """
    annee_cible, mois_cible, date_fin_periode = calculer_periode_cible(annee, mois)
    date_reference_reparations = date_reference_reparations or date_actuelle_madagascar()

    regroupement_paiements = construire_regroupement(annee_cible, mois_cible)
    regroupement_paiements_h = construire_regroupement_hierarchique(regroupement_paiements, date_fin_periode)

    regroupement_reparations = construire_regroupement_reparations(date_reference_reparations)
    regroupement_reparations_h = construire_regroupement_hierarchique_reparations(
        regroupement_reparations, date_reference_reparations,
    )

    factures_sans_responsable = compter_factures_sans_responsable(date_fin_periode)
    reparations_sans_responsable = compter_reparations_sans_responsable(date_reference_reparations)

    regroupement_combine = {}
    _fusionner_source_dans_pivot(regroupement_combine, regroupement_paiements, True, _fusionner_ouvrages_paiements)
    _fusionner_source_dans_pivot(regroupement_combine, regroupement_paiements_h, False, _fusionner_ouvrages_paiements)
    _fusionner_source_dans_pivot(regroupement_combine, regroupement_reparations, True, _fusionner_ouvrages_reparations)
    _fusionner_source_dans_pivot(regroupement_combine, regroupement_reparations_h, False, _fusionner_ouvrages_reparations)

    for entree in regroupement_combine.values():
        entree['type_destinataire'] = 'responsable' if entree['a_ouvrage_direct'] else 'superieur'
        del entree['a_ouvrage_direct']

    return (
        regroupement_combine, annee_cible, mois_cible, date_fin_periode,
        date_reference_reparations, factures_sans_responsable,
        reparations_sans_responsable,
    )
