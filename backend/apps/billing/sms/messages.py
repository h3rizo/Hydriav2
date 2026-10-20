"""Construction des SMS de rappel (GSM-7, 160 caracteres maximum par SMS)."""
from decimal import Decimal

from .config import reglage
from .gateway import LIMITE_SMS_GSM7, vers_gsm7


def format_montant(montant):
    return f"{int(round(Decimal(montant))):,}".replace(',', ' ') + ' Ar'


def format_date(d):
    return d.strftime('%d/%m/%Y')


def motif_mvola(type_nom, idxls, nom_abonne):
    """
    Motif du paiement MVola : [type de point d'eau][IDXls][Nom abonne], tout attache
    (MVola n'accepte pas les espaces). Le nom est en fin de motif : c'est lui qui est
    tronque si le SMS est trop long (voir `_partie_paiement`).
    """
    brut = f"{type_nom or ''}{idxls or ''}{nom_abonne or ''}"
    return ''.join(vers_gsm7(brut).split())


def _pluriel(n, mot):
    return f"{n} {mot}{'s' if n > 1 else ''}"


def _ref_mg(reference):
    """Le repli « mois MM/AAAA » du numero de facture manquant devient « volana MM/AAAA »."""
    return reference.replace('mois ', 'volana ', 1)


def _partie_facture_mg(plan, complete=True):
    courantes, anterieures = plan.courantes, plan.anterieures
    montant_courant = sum(f.montant for f in courantes)
    date_txt = format_date(plan.date_echeance)
    if len(courantes) == 1 and complete:
        texte = (f"SOAKOJA: Faktiran'ny rano {_ref_mg(courantes[0].reference)}: "
                 f"{format_montant(montant_courant)}. Aloavy alohan'ny {date_txt}.")
    else:
        texte = (f"SOAKOJA: Faktira {len(courantes)} momba ny rano: "
                 f"{format_montant(montant_courant)}. Aloavy alohan'ny {date_txt}.")
    if anterieures:
        montant_ant = sum(f.montant for f in anterieures)
        texte += (f" Trosa taloha: faktira {len(anterieures)} ({format_montant(montant_ant)})."
                  f" REHETRA: {format_montant(montant_courant + montant_ant)}.")
    return vers_gsm7(texte)


def _partie_facture(plan, complete=True, langue='fr'):
    """SMS 1 : facture(s), montant, date limite, et cumul des impayees anterieures."""
    if langue == 'mg':
        return _partie_facture_mg(plan, complete)
    courantes, anterieures = plan.courantes, plan.anterieures
    montant_courant = sum(f.montant for f in courantes)
    date_txt = format_date(plan.date_echeance)
    if len(courantes) == 1 and complete:
        texte = (f"SOAKOJA: Facture eau {courantes[0].reference} de "
                 f"{format_montant(montant_courant)}, a payer avant le {date_txt}.")
    else:
        texte = (f"SOAKOJA: {_pluriel(len(courantes), 'facture')} eau de "
                 f"{format_montant(montant_courant)}, a payer avant le {date_txt}.")
    if anterieures:
        montant_ant = sum(f.montant for f in anterieures)
        texte += (f" Plus {_pluriel(len(anterieures), 'facture')} anterieure"
                  f"{'s' if len(anterieures) > 1 else ''} impayee"
                  f"{'s' if len(anterieures) > 1 else ''}: {format_montant(montant_ant)}."
                  f" TOTAL: {format_montant(montant_courant + montant_ant)}.")
    return vers_gsm7(texte)


def _partie_paiement(numero_mvola, motif, limite=LIMITE_SMS_GSM7, langue='fr'):
    """SMS 2 : consigne de paiement MVola. Le nom est tronque en dernier recours."""
    if langue == 'mg':
        debut, fin = f"Alefaso amin'ny MVola: {numero_mvola}, antony: ", ". Misaotra."
    else:
        debut, fin = f"Payez par MVola au {numero_mvola}, motif: ", ". Merci."
    place = limite - len(debut) - len(fin)
    return vers_gsm7(f"{debut}{motif[:max(place, 0)]}{fin}")


def construire_messages(plan, numero_mvola, langue=None):
    """
    Retourne la liste des SMS d'un rappel : 1 seul si tout tient en 160 caracteres,
    sinon 2 (facture, puis consigne de paiement MVola). Chaque SMS tient en 160 caracteres.
    `langue` : 'mg' (malgache, defaut) ou 'fr' ; par defaut le reglage SMS_LANGUE.
    """
    langue = langue or reglage('SMS_LANGUE')
    motif = motif_mvola(plan.abonne.type_nom, plan.abonne.idxls, plan.abonne.nom)
    facture = _partie_facture(plan, langue=langue)
    paiement = _partie_paiement(numero_mvola, motif, langue=langue)
    unique = f"{facture} {paiement}"
    if len(unique) <= LIMITE_SMS_GSM7:
        return [unique]
    if len(facture) > LIMITE_SMS_GSM7:
        facture = _partie_facture(plan, complete=False, langue=langue)
    return [facture[:LIMITE_SMS_GSM7], paiement[:LIMITE_SMS_GSM7]]
