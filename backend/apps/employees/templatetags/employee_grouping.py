from collections.abc import Mapping

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe


register = template.Library()


def _value(item, name, default=None):
    if isinstance(item, Mapping):
        return item.get(name, default)
    return getattr(item, name, default)


def _related_label(item, relation_name, field_name, fallback):
    direct_value = _value(item, f'{relation_name}_name')
    if direct_value:
        return str(direct_value).strip()

    related = _value(item, relation_name)
    related_value = _value(related, field_name) if related else None
    return str(related_value).strip() if related_value else fallback


def _employee_label(employee):
    for field_name in ('display_name', 'nom_affichage', 'surnom', 'nom_complet', 'nom_employe'):
        field_value = _value(employee, field_name)
        if field_value:
            return str(field_value).strip()

    prenom = str(_value(employee, 'prenom', '') or '').strip()
    nom = str(_value(employee, 'nom', '') or '').strip()
    return f'{prenom} {nom}'.strip() or str(_value(employee, 'id', '') or '')


@register.simple_tag
def grouped_employee_options(
    employees,
    selected_value='',
    empty_label='Tous les employes',
    empty_value='',
):
    """Render employee options grouped by Base, then by Poste."""
    selected = str(selected_value or '')
    normalized = []

    for employee in employees or []:
        employee_id = str(_value(employee, 'id', '') or '')
        if not employee_id:
            continue

        base = _value(employee, 'base')
        base_id = str(_value(employee, 'base_id', '') or _value(base, 'id', '') or '')
        normalized.append({
            'id': employee_id,
            'label': _employee_label(employee),
            'base_id': base_id,
            'base_name': _related_label(employee, 'base', 'nom_base', 'Sans base'),
            'poste_name': _related_label(employee, 'poste', 'nom_poste', 'Sans poste'),
        })

    normalized.sort(key=lambda item: (
        item['base_name'].casefold(),
        item['poste_name'].casefold(),
        item['label'].casefold(),
        item['id'],
    ))

    selected_attribute = mark_safe(' selected')
    parts = [format_html(
        '<option value="{}"{}>{}</option>',
        empty_value,
        selected_attribute if selected == str(empty_value) else '',
        empty_label,
    )]

    current_base = None
    current_poste = None
    for employee in normalized:
        if employee['base_name'] != current_base:
            if current_base is not None:
                parts.append(mark_safe('</optgroup>'))
            parts.append(format_html('<optgroup label="Base : {}">', employee['base_name']))
            current_base = employee['base_name']
            current_poste = None

        if employee['poste_name'] != current_poste:
            parts.append(format_html(
                '<option value="" disabled>-- {} --</option>',
                employee['poste_name'],
            ))
            current_poste = employee['poste_name']

        parts.append(format_html(
            '<option value="{}" data-base-id="{}"{}>\u00a0\u00a0{}</option>',
            employee['id'],
            employee['base_id'],
            selected_attribute if selected == employee['id'] else '',
            employee['label'],
        ))

    if current_base is not None:
        parts.append(mark_safe('</optgroup>'))

    return mark_safe(''.join(str(part) for part in parts))
