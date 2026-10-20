"""Date limite de paiement d'une facture (regles validees avec le metier)."""
import unicodedata
from datetime import date

JOUR_LIMITE_KIOSQUE = 5
JOUR_LIMITE_BP_BI_VOLUME = 15


def _nom_normalise(nom_type):
    texte = unicodedata.normalize('NFD', str(nom_type or '')).lower().strip()
    return ''.join(c for c in texte if not unicodedata.combining(c))


def jour_limite_pour_type(nom_type):
    """
    Jour du mois de la date limite de paiement selon le type de point d'eau.

    Retourne None quand le type n'a pas de regle : aucun rappel SMS n'est alors envoye
    pour ce point d'eau (choix le plus sur tant qu'aucune regle n'est definie).
    """
    nom = _nom_normalise(nom_type)
    if nom == 'kiosque':
        return JOUR_LIMITE_KIOSQUE
    if nom in ('bp', 'bi volume'):
        return JOUR_LIMITE_BP_BI_VOLUME
    # TODO(human): que faire pour les autres types presents en base (BF, PMH, BI, Puits, ...) ?
    # Retourner un jour (1-28) pour leur envoyer aussi des rappels, ou None pour les ignorer.
    return None


def prochaine_date_limite(a_partir_du, jour):
    """Premiere date au quantieme `jour` (1-28), a partir de `a_partir_du` inclus."""
    if a_partir_du.day <= jour:
        return date(a_partir_du.year, a_partir_du.month, jour)
    if a_partir_du.month == 12:
        return date(a_partir_du.year + 1, 1, jour)
    return date(a_partir_du.year, a_partir_du.month + 1, jour)


def mois_facture_releve(date_releve):
    """Mois de facture d'un releve = mois suivant celui du releve (regle du widget Hydria)."""
    from apps.core.views_widget import _billing_month_start
    return _billing_month_start(date_releve)
