"""
Conversion remuneration nette -> brut pour la grille salariale par autonomie.

GrilleAutonomie est exprimee exclusivement en NET. La conversion vers un brut
n'a de sens qu'au moment de la generation effective d'un bulletin de paie
(GrilleSalaire), jamais au niveau de la configuration de la grille elle-meme.

Aucune nouvelle logique de calcul brut/retenues n'est introduite ici : on
reutilise GrilleSalaire.calculer_salaire_brut_depuis_net(), qui resout deja ce
probleme par dichotomie en tenant compte de CNaPS, mutuelle sante et IRSA
progressif (sensible a la charge de famille via Contrat/Employe).
"""
from decimal import Decimal

from django.utils import timezone

from .views_grilles_salariales import _build_reference_preview_instance


def resoudre_brut_pour_remuneration_nette_cible(poste, remuneration_nette_cible, date_salaire=None):
    """
    Calcule le salaire brut necessaire pour atteindre une remuneration nette
    cible (ex: salaire_garanti + prime acquise du mois), pour un poste donne.

    Construit une instance GrilleSalaire non persistee (pattern deja utilise
    par _build_gross_preview_for_poste dans views_grilles_salariales.py) et
    delegue le calcul iteratif a calculer_salaire_brut_depuis_net().

    Args:
        poste: instance Poste
        remuneration_nette_cible: Decimal - montant net vise
        date_salaire: date optionnelle de reference (defaut: aujourd'hui)

    Returns:
        Decimal: salaire brut correspondant
    """
    remuneration_nette_cible = Decimal(str(remuneration_nette_cible or 0))

    preview, _reference_label = _build_reference_preview_instance(poste)
    if date_salaire:
        preview.date_salaire = date_salaire
    else:
        preview.date_salaire = timezone.now().date()

    preview.salaire_brut_base = preview.calculer_salaire_brut_depuis_net(remuneration_nette_cible)
    preview.calculer_tous_les_champs()

    return preview.salaire_brut_base


def detail_brut_pour_remuneration_nette_cible(poste, remuneration_nette_cible, date_salaire=None):
    """
    Variante qui retourne, en plus du brut, le detail complet des retenues
    (CNaPS, IRSA, mutuelle sante) tel que calcule par GrilleSalaire, pour
    affichage transparent (ex: simulateur, Phase 6).
    """
    remuneration_nette_cible = Decimal(str(remuneration_nette_cible or 0))

    preview, _reference_label = _build_reference_preview_instance(poste)
    preview.date_salaire = date_salaire or timezone.now().date()
    preview.salaire_brut_base = preview.calculer_salaire_brut_depuis_net(remuneration_nette_cible)
    preview.calculer_tous_les_champs()

    return {
        'salaire_brut_base': preview.salaire_brut_base,
        'salaire_brut_total': preview.salaire_brut_total,
        'charge_cnaps_employe': preview.charge_cnaps_employe,
        'mutuelle_sante': preview.mutuelle_sante,
        'base_imposable': preview.base_imposable,
        'irsa': preview.irsa,
        'salaire_net': preview.salaire_net,
    }
