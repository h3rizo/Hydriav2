"""
Moteur de calcul des primes de resultat pour la grille salariale par autonomie.

Service pur (aucune dependance HTTP/vues) : appelable a la fois par les vues API
(apps.employees.views_autonomie) et par le simulateur de remuneration, sans
duplication de logique.
"""
import calendar
import datetime
from decimal import Decimal

from .models_autonomie import GrilleAutonomie, RegleDePrime, ResultatIndicateur


def resoudre_periode(periodicite, date_reference=None):
    """
    Calcule les bornes (debut, fin) de la periode calendaire correspondant a une
    periodicite donnee, pour une date de reference. Isole la notion de
    periodicite de la logique de calcul de prime (agnostique des dates).
    """
    if date_reference is None:
        date_reference = datetime.date.today()

    annee = date_reference.year
    mois = date_reference.month

    if periodicite == 'mensuelle':
        debut = datetime.date(annee, mois, 1)
        fin = datetime.date(annee, mois, calendar.monthrange(annee, mois)[1])
    elif periodicite == 'trimestrielle':
        trimestre = (mois - 1) // 3
        mois_debut = trimestre * 3 + 1
        mois_fin = mois_debut + 2
        debut = datetime.date(annee, mois_debut, 1)
        fin = datetime.date(annee, mois_fin, calendar.monthrange(annee, mois_fin)[1])
    elif periodicite == 'semestrielle':
        if mois <= 6:
            debut = datetime.date(annee, 1, 1)
            fin = datetime.date(annee, 6, 30)
        else:
            debut = datetime.date(annee, 7, 1)
            fin = datetime.date(annee, 12, 31)
    elif periodicite == 'annuelle':
        debut = datetime.date(annee, 1, 1)
        fin = datetime.date(annee, 12, 31)
    else:
        raise ValueError(f"Periodicite inconnue: {periodicite}")

    return debut, fin


def _resoudre_valeur_indicateur(employe, indicateur, periode_debut, periode_fin, resultats_override=None):
    """Retourne la valeur realisee d'un indicateur (override prioritaire, sinon ResultatIndicateur en base)."""
    if resultats_override and str(indicateur.id) in resultats_override:
        valeur = resultats_override[str(indicateur.id)]
        return Decimal(str(valeur)) if valeur is not None else None

    resultat = ResultatIndicateur.objects.filter(
        employe=employe,
        indicateur=indicateur,
        periode_debut=periode_debut,
        periode_fin=periode_fin,
    ).first()

    return resultat.valeur_realisee if resultat else None


def _resoudre_palier(indicateur, taux_realisation_pct):
    """Trouve le palier applicable pour un taux de realisation donne."""
    paliers = indicateur.paliers.all().order_by('taux_realisation_min')
    for palier in paliers:
        borne_max = palier.taux_realisation_max
        if palier.taux_realisation_min <= taux_realisation_pct and (borne_max is None or taux_realisation_pct < borne_max):
            return palier
    return None


def calculer_prime_acquise(employe, regle: RegleDePrime, periode_debut, periode_fin,
                            base_montant: Decimal, resultats_override=None):
    """
    Calcule le montant de prime acquise pour un employe sur une regle et une periode
    donnees.

    Args:
        employe: instance Employe
        regle: instance RegleDePrime
        periode_debut/periode_fin: bornes de la periode (date)
        base_montant: montant theorique de reference (ex: GrilleAutonomie.prime_cible
            ou .prime_maximale, ou montant custom du simulateur) - decouple le moteur
            de la source du montant
        resultats_override: dict optionnel {str(indicateur_id): Decimal} pour tester
            des hypotheses sans lire/persister ResultatIndicateur (mode simulation)

    Returns:
        dict avec 'montant_prime', 'plafonne', 'montant_avant_plafond', 'details_indicateurs'
    """
    base_montant = Decimal(str(base_montant)) if base_montant is not None else Decimal('0')

    if regle.type_calcul == 'montant_fixe':
        montant = regle.montant_fixe or Decimal('0')
        return {
            'montant_prime': montant,
            'plafonne': False,
            'montant_avant_plafond': montant,
            'details_indicateurs': [],
        }

    if regle.type_calcul == 'pourcentage_salaire':
        grille = GrilleAutonomie.get_grille_for_poste_and_stade(regle.poste, employe.stade_autonomie_actuel)
        salaire_net_fixe = grille.salaire_net_fixe if grille else Decimal('0')
        pourcentage = regle.pourcentage_salaire or Decimal('0')
        montant = (pourcentage / Decimal('100')) * salaire_net_fixe
        return {
            'montant_prime': montant,
            'plafonne': False,
            'montant_avant_plafond': montant,
            'details_indicateurs': [],
        }

    # type_calcul == 'paliers_resultats'
    details_indicateurs = []
    montant_total = Decimal('0')

    for indicateur in regle.indicateurs.all().order_by('ordre'):
        valeur_realisee = _resoudre_valeur_indicateur(employe, indicateur, periode_debut, periode_fin, resultats_override)

        detail = {
            'indicateur': indicateur,
            'valeur_realisee': valeur_realisee,
            'taux_realisation_pct': None,
            'sous_seuil': False,
            'palier_applique': None,
            'montant_part_indicateur': Decimal('0'),
        }

        if valeur_realisee is None:
            detail['sous_seuil'] = True
            details_indicateurs.append(detail)
            continue

        objectif = indicateur.objectif or Decimal('0')
        taux_realisation_pct = (valeur_realisee / objectif * Decimal('100')) if objectif else Decimal('0')
        detail['taux_realisation_pct'] = taux_realisation_pct

        if indicateur.seuil_minimum is not None and valeur_realisee < indicateur.seuil_minimum:
            detail['sous_seuil'] = True
            details_indicateurs.append(detail)
            continue

        palier = _resoudre_palier(indicateur, taux_realisation_pct)
        detail['palier_applique'] = palier

        if palier is not None:
            ponderation = indicateur.ponderation or Decimal('0')
            taux_prime = palier.taux_prime or Decimal('0')
            part = (ponderation / Decimal('100')) * (taux_prime / Decimal('100')) * base_montant
            detail['montant_part_indicateur'] = part
            montant_total += part

        details_indicateurs.append(detail)

    montant_avant_plafond = montant_total
    plafonne = False
    montant_final = montant_avant_plafond

    if regle.plafond is not None and montant_avant_plafond > regle.plafond:
        montant_final = regle.plafond
        plafonne = True

    return {
        'montant_prime': montant_final,
        'plafonne': plafonne,
        'montant_avant_plafond': montant_avant_plafond,
        'details_indicateurs': details_indicateurs,
    }


def _regles_applicables(poste, stade):
    """
    Resout les RegleDePrime applicables a un poste+stade : priorite aux regles
    specifiques (poste+stade precis), puis fallback sur les regles generiques
    (poste seul, stade=None), sans doublonner un meme nom de regle entre les deux.
    """
    regles_specifiques = list(RegleDePrime.objects.filter(
        poste=poste, stade=stade, actif=True, statut='appliquee',
    ))
    regles_generiques = list(RegleDePrime.objects.filter(
        poste=poste, stade__isnull=True, actif=True, statut='appliquee',
    ))
    return regles_specifiques + regles_generiques


def calculer_toutes_primes_employe(employe, date_reference=None, resultats_override=None,
                                    base_montant_mode='cible'):
    """
    Calcule toutes les primes applicables a un employe (poste + stade d'autonomie
    actuel), pour chaque RegleDePrime active correspondante. Point d'entree
    reutilise par le simulateur de remuneration.

    Args:
        base_montant_mode: 'cible' ou 'maximale' - determine si on calcule sur la
            base de GrilleAutonomie.prime_cible ou .prime_maximale.

    Returns:
        list[dict] - un dict de resultat calculer_prime_acquise() par regle, enrichi
        de la cle 'regle'.
    """
    if not employe.poste_id or not employe.stade_autonomie_actuel_id:
        return []

    grille = GrilleAutonomie.get_grille_for_poste_and_stade(
        employe.poste, employe.stade_autonomie_actuel, date_reference,
    )
    if grille is None:
        base_montant_defaut = Decimal('0')
    else:
        base_montant_defaut = grille.prime_maximale if base_montant_mode == 'maximale' else grille.prime_cible

    resultats = []
    for regle in _regles_applicables(employe.poste, employe.stade_autonomie_actuel):
        periode_debut, periode_fin = resoudre_periode(regle.periodicite, date_reference)
        resultat = calculer_prime_acquise(
            employe, regle, periode_debut, periode_fin,
            base_montant=base_montant_defaut,
            resultats_override=resultats_override,
        )
        resultat['regle'] = regle
        resultat['periode_debut'] = periode_debut
        resultat['periode_fin'] = periode_fin
        resultats.append(resultat)

    return resultats
