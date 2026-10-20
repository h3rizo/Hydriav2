"""
Reglages des rappels SMS.

Lus dans django.conf.settings s'ils y sont definis, sinon directement dans le .env : aucune
modification de settings.py n'est requise sur le serveur. Sans configuration, le mode
simulation (SMS_DRY_RUN=True) reste actif : aucun SMS reel ne peut partir par accident.
"""
from decouple import config
from django.conf import settings

_DEFAUTS = {
    'SMS_DRY_RUN': (True, bool),
    'SMS_GATEWAY_URL': ('https://api.sms-gate.app/3rdparty/v1/message', str),
    'SMS_GATEWAY_USER': ('', str),
    'SMS_GATEWAY_PASS': ('', str),
    'SMS_NUMERO_MVOLA': ('', str),
    'SMS_RAPPEL_JOURS': ('3,1', str),
    'SMS_DELAI_SECONDES': (4.0, float),
    'SMS_LANGUE': ('mg', str),   # 'mg' (malgache) ou 'fr'
}


def reglage(nom):
    if hasattr(settings, nom):
        return getattr(settings, nom)
    defaut, type_ = _DEFAUTS[nom]
    return config(nom, default=defaut, cast=type_)
