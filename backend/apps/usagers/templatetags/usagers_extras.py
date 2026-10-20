from django import template

register = template.Library()


@register.filter(name='get_item')
def get_item(dictionary, key):
    """Recupere une valeur d'un dictionnaire avec une cle variable dans un template."""
    if not isinstance(dictionary, dict):
        return None
    return dictionary.get(key)
