from django import template
from decimal import Decimal
from django.urls import reverse, NoReverseMatch

register = template.Library()


@register.simple_tag
def safe_url(viewname, *args, **kwargs):
    """
    Equivalent de {% url %} mais qui n'interrompt pas le rendu si la route
    n'existe pas dans l'urlconf actif (ex: sous-domaine compta.hydria.mg
    qui utilise un urlconf reduit sans toutes les pages du site principal).
    Retourne '#' si la route est introuvable, au lieu de lever NoReverseMatch.

    Usage: <a href="{% safe_url 'accounting:dashboard_frequence_paiements_forfaitaire' %}">
    """
    try:
        return reverse(viewname, args=args, kwargs=kwargs)
    except NoReverseMatch:
        return '#'


@register.filter(name='frenchformat')
def frenchformat(value, decimals=2):
    """
    Formate un nombre avec le format français:
    - Espace comme séparateur de milliers
    - Virgule comme séparateur décimal

    Usage: {{ value|frenchformat }}
    Usage: {{ value|frenchformat:0 }} pour sans décimales
    """
    try:
        # Convertir en Decimal pour précision
        if value is None or value == '':
            return '0'

        num = Decimal(str(value))

        # Arrondir selon le nombre de décimales demandé
        if decimals == 0:
            num = round(num)
            formatted = f"{num:,.0f}"
        else:
            formatted = f"{num:,.{decimals}f}"

        # Remplacer séparateurs : point -> virgule, virgule -> espace
        formatted = formatted.replace(',', ' ').replace('.', ',')

        return formatted
    except (ValueError, TypeError, Decimal.InvalidOperation):
        return str(value)


@register.filter(name='frenchformat_int')
def frenchformat_int(value):
    """
    Formate un nombre entier avec le format français (espace comme séparateur de milliers)

    Usage: {{ value|frenchformat_int }}
    """
    return frenchformat(value, decimals=0)


@register.filter(name='sum_attr')
def sum_attr(list_of_dicts, attribute):
    """
    Somme les valeurs d'un attribut dans une liste de dictionnaires

    Usage: {{ soldes_tiers|sum_attr:'solde' }}
    """
    try:
        if not list_of_dicts:
            return Decimal('0')

        total = Decimal('0')
        for item in list_of_dicts:
            if isinstance(item, dict):
                value = item.get(attribute, 0)
            else:
                value = getattr(item, attribute, 0)

            if value is not None:
                total += Decimal(str(value))

        return total
    except (ValueError, TypeError, Decimal.InvalidOperation):
        return Decimal('0')


@register.filter(name='get_item')
def get_item(dictionary, key):
    """
    Récupère une valeur d'un dictionnaire avec une clé variable

    Usage: {{ district_counts|get_item:district_nom }}
    """
    if dictionary is None:
        return None
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None
