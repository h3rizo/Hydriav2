"""Template tags personnalisés pour l'app planning"""
from django import template

register = template.Library()


@register.filter
def lookup(dictionary, key):
    """Permet d'accéder à un dictionnaire avec une clé variable dans les templates"""
    if dictionary is None:
        return None
    return dictionary.get(key)


@register.filter
def get_item(dictionary, key):
    """Permet d'accéder à un dictionnaire avec une clé entière ou string"""
    if dictionary is None:
        return None
    # Convertir la clé en entier si c'est possible
    try:
        key = int(key)
    except (ValueError, TypeError):
        pass
    return dictionary.get(key, 0)


@register.filter
def split(value, separator=' '):
    """Sépare une chaîne en liste selon un séparateur"""
    if value is None:
        return []
    return value.split(separator)
