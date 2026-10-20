from django import template
from django.http import QueryDict

register = template.Library()

@register.simple_tag(takes_context=True)
def query_string(context, **kwargs):
    """
    Construit une query string en preservant les parametres GET existants
    et en excluant les valeurs vides
    """
    request = context['request']
    query_dict = request.GET.copy()

    # Mettre a jour avec les nouveaux parametres
    for key, value in kwargs.items():
        if value is not None:
            query_dict[key] = value
        elif key in query_dict:
            del query_dict[key]

    # Filtrer les parametres vides
    filtered_dict = QueryDict('', mutable=True)
    for key, value in query_dict.items():
        if value:  # Exclure les chaines vides
            filtered_dict[key] = value

    query_string = filtered_dict.urlencode()
    return f'?{query_string}' if query_string else '?'
