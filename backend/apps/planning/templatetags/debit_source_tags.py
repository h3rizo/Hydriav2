"""Badges et bandeaux "debit de source critique" reutilisables dans toutes les pages.

Usage :
    {% load debit_source_tags %}
    {% debit_critique_badge ouvrage.id %}
    {% debits_critiques_banner ouvrages %}   {# ids, objets Ouvrage ou dicts avec ouvrage_id #}
"""
from django import template
from django.db.models import QuerySet
from django.urls import reverse

from apps.planning.services_debit_critique import get_etat_debit, resumer_debits

register = template.Library()


def _extraire_ids(source):
    if source is None:
        return []
    if isinstance(source, dict):
        # dict {cle: [lignes]} (ex. recouvrement_par_district)
        ids = []
        for valeur in source.values():
            ids.extend(_extraire_ids(valeur) if isinstance(valeur, (list, tuple, dict, QuerySet)) else [])
        return ids
    if isinstance(source, QuerySet):
        if source.model.__name__ == 'Ouvrage':
            return list(source.values_list('id', flat=True))
        source = list(source)
    ids = []
    for item in source:
        if isinstance(item, dict):
            oid = item.get('ouvrage_id') or item.get('id')
        elif isinstance(item, (str,)) or item.__class__.__name__ == 'UUID':
            oid = item
        else:
            oid = getattr(item, 'ouvrage_id', None) or getattr(item, 'id', None)
        if oid:
            ids.append(oid)
    return ids


def _url_historique(etat):
    return f"{reverse('planning:debit_source')}?ouvrage={etat['source_ouvrage_id']}"


@register.inclusion_tag('components/debit_critique_badge.html')
def debit_critique_badge(ouvrage_id, compact=False):
    etat = get_etat_debit(ouvrage_id)
    return {
        'etat': etat,
        'compact': compact,
        'url': _url_historique(etat) if etat else '',
    }


@register.simple_tag
def debit_critique_texte(ouvrage_id):
    """Libelle court pour <option> ou texte brut ("" si pas d'alerte)."""
    etat = get_etat_debit(ouvrage_id)
    if not etat:
        return ''
    return ' ⚠ debit critique' if etat['niveau'] == 'critique' else ' • debit en vigilance'


@register.inclusion_tag('components/debits_critiques_banner.html')
def debits_critiques_banner(source, filtre_url=''):
    resume = resumer_debits(_extraire_ids(source))
    for etat in resume['items']:
        etat['url'] = _url_historique(etat)
    return {'resume': resume, 'filtre_url': filtre_url}
