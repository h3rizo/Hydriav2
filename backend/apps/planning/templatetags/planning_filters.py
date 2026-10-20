
from django.contrib.humanize.templatetags.humanize import intcomma
from django import template

register = template.Library()

@register.filter
def kar(value):
    """Convertit un montant en milliers d'Ariary avec séparateur de milliers"""
    try:
        montant_k = round(float(value) / 1000)
        return f"{intcomma(montant_k)} K Ar"
    except (ValueError, TypeError):
        return "0 K Ar"


@register.filter
def lookup(dictionary, key):
    """Permet d'accéder à un dictionnaire avec une clé variable dans un template"""
    if dictionary is None:
        return None
    return dictionary.get(key)