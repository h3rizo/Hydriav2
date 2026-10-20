from django import template

from apps.employees import post_classification as pc

register = template.Library()


@register.filter
def type_poste_label(type_code):
    return pc.type_label(type_code)


@register.filter
def niveau_poste_label(niveau_code):
    return pc.niveau_label(niveau_code)


@register.filter
def type_poste_badge_class(type_code):
    return pc.type_badge_class(type_code)


@register.simple_tag
def niveau_poste_badge_class(type_code, niveau_code):
    return pc.niveau_badge_class(type_code, niveau_code)


@register.filter
def type_poste_text_class(type_code):
    return pc.text_class(type_code)
