from django import template
from django.core.cache import cache
from django.db.models import Max

register = template.Library()

CACHE_KEY = 'accounting:diamex_last_import'
CACHE_SECONDS = 60


def get_last_diamex_import():
    """Date (aware) de la dernière importation DiameX, ou None.

    Même source que « Dernier import » de la page d'import : Max(BaseDiameX.date_import),
    renseigné à la création des lignes importées. Mis en cache 60 s (4 pages l'affichent).
    """
    value = cache.get(CACHE_KEY)
    if value is None:
        from apps.accounting.models import BaseDiameX
        value = BaseDiameX.objects.aggregate(last=Max('date_import'))['last']
        if value is not None:
            cache.set(CACHE_KEY, value, CACHE_SECONDS)
    return value


@register.inclusion_tag('accounting/includes/diamex_last_import.html')
def diamex_last_import():
    return {'last_import': get_last_diamex_import()}


@register.inclusion_tag('accounting/includes/diamex_last_import_navbar.html')
def diamex_last_import_navbar():
    return {'last_import': get_last_diamex_import()}
