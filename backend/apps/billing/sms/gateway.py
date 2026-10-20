"""Envoi via SMS Gateway for Android (https://sms-gate.app), mode Cloud."""
import logging
import re
import unicodedata

import requests
from .config import reglage

logger = logging.getLogger(__name__)

LIMITE_SMS_GSM7 = 160
TIMEOUT_SECONDES = 20

# Caracteres conserves : sous-ensemble du jeu GSM-7 de base coutant 1 septet.
# Les caracteres "etendus" ([ ] { } ^ ~ | \ euro) coutent 2 septets : on les retire.
_AUTORISES = re.compile(r"[^A-Za-z0-9 \n!\"#%&'()*+,\-./:;<=>?@_$]")
_SUBSTITUTIONS = str.maketrans({
    '’': "'", '‘': "'", '“': '"', '”': '"',
    '–': '-', '—': '-', ' ': ' ', ' ': ' ',
})


class ErreurPasserelle(Exception):
    """La passerelle SMS a refuse ou n'a pas pu traiter l'envoi."""


def normaliser_numero(brut):
    """
    Normalise un numero malgache au format +2613XXXXXXXX, sinon None.

    Accepte aussi les numeros saisis sans le 0 initial (ex. 347128573),
    tres frequents dans la base Hydria.
    """
    if not brut:
        return None
    n = re.sub(r'[\s.\-()]', '', str(brut))
    if n.startswith('00261'):
        n = '+' + n[2:]
    elif n.startswith('261'):
        n = '+' + n
    elif re.fullmatch(r'0\d{9}', n):
        n = '+261' + n[1:]
    elif re.fullmatch(r'3\d{8}', n):
        n = '+261' + n
    return n if re.fullmatch(r'\+2613\d{8}', n) else None


def vers_gsm7(texte):
    """Retire accents et caracteres hors GSM-7 (sinon le SMS tombe a 70 caracteres)."""
    texte = unicodedata.normalize('NFD', str(texte or '')).translate(_SUBSTITUTIONS)
    texte = ''.join(c for c in texte if not unicodedata.combining(c))
    return _AUTORISES.sub('', texte)


def envoyer_sms(telephone, texte, dry_run=None):
    """
    Envoie un SMS. Retourne {'simule': bool, 'id': str}.

    Leve ErreurPasserelle en cas d'echec. En mode `dry_run` (defaut : reglage('SMS_DRY_RUN'))
    rien n'est envoye.
    """
    message = vers_gsm7(texte)
    if dry_run is None:
        dry_run = reglage('SMS_DRY_RUN')
    if dry_run:
        logger.info('[SMS simule] %s : %s', telephone, message)
        return {'simule': True, 'id': ''}

    if not (reglage('SMS_GATEWAY_URL') and reglage('SMS_GATEWAY_USER') and reglage('SMS_GATEWAY_PASS')):
        raise ErreurPasserelle('Passerelle SMS non configuree (SMS_GATEWAY_URL / USER / PASS).')
    try:
        reponse = requests.post(
            reglage('SMS_GATEWAY_URL'),
            json={'message': message, 'phoneNumbers': [telephone]},
            auth=(reglage('SMS_GATEWAY_USER'), reglage('SMS_GATEWAY_PASS')),
            timeout=TIMEOUT_SECONDES,
        )
    except requests.RequestException as exc:
        raise ErreurPasserelle(f'Passerelle injoignable : {exc}') from exc
    if not reponse.ok:
        raise ErreurPasserelle(f'Passerelle HTTP {reponse.status_code} : {reponse.text[:300]}')
    try:
        identifiant = str(reponse.json().get('id') or '')
    except ValueError:
        identifiant = ''
    return {'simule': False, 'id': identifiant}


def etat_sms_detail(identifiant):
    """
    Etat d'un message vu par la passerelle : {'state': 'Pending|Processed|Sent|Delivered|Failed',
    'error': str}. None si la passerelle est injoignable ou ne connait pas le message.
    """
    if not identifiant:
        return None
    try:
        reponse = requests.get(
            f"{reglage('SMS_GATEWAY_URL').rstrip('/')}/{identifiant}",
            auth=(reglage('SMS_GATEWAY_USER'), reglage('SMS_GATEWAY_PASS')),
            timeout=TIMEOUT_SECONDES,
        )
        if not reponse.ok:
            return None
        donnees = reponse.json()
    except (requests.RequestException, ValueError):
        return None
    erreurs = [r.get('error') for r in donnees.get('recipients') or [] if r.get('error')]
    return {'state': donnees.get('state') or donnees.get('status') or '?', 'error': '; '.join(erreurs)}


def etat_sms(identifiant):
    """Etat lisible d'un message (pour l'affichage en ligne de commande), ou None."""
    detail = etat_sms_detail(identifiant)
    if detail is None:
        return None
    return detail['state'] + (f" ({detail['error']})" if detail['error'] else '')
