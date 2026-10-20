import unicodedata

from django import template


register = template.Library()


def _normalized(value):
    text = str(value or '').strip().lower()
    return ''.join(
        character
        for character in unicodedata.normalize('NFKD', text)
        if not unicodedata.combining(character)
    )


def _contains_any(value, needles):
    return any(needle in value for needle in needles)


@register.filter
def point_eau_icon(value):
    """Font Awesome icon aligned with the readings workflow."""
    name = _normalized(value)
    if 'kiosque' in name:
        return 'fa-store'
    if _contains_any(name, ('borne', ' bi ', 'bi volume')) or name == 'bi' or name.startswith('bi '):
        return 'fa-faucet'
    if _contains_any(name, ('branchement', 'prive')) or name == 'bp' or name.startswith('bp '):
        return 'fa-home'
    return 'fa-tint'


@register.filter
def point_eau_icon_tone(value):
    name = _normalized(value)
    if 'kiosque' in name:
        return 'text-info'
    if _contains_any(name, ('borne', ' bi ', 'bi volume')) or name == 'bi' or name.startswith('bi '):
        return 'text-primary'
    if _contains_any(name, ('branchement', 'prive')) or name == 'bp' or name.startswith('bp '):
        return 'text-success'
    return 'text-base-content/50'


@register.filter
def equipment_icon(value):
    """Stable, semantic icons shared by equipment lists and their type catalog."""
    name = _normalized(value)
    mappings = (
        (('citerne', 'reservoir', 'bache', 'chateau'), 'fa-database'),
        (('compteur', 'debitmetre', 'manometre'), 'fa-tachometer-alt'),
        (('vanne', 'robinet', 'clapet'), 'fa-sliders-h'),
        (('filtre', 'traitement', 'chloration', 'chlorateur'), 'fa-filter'),
        (('pompe', 'surpresseur', 'motopompe'), 'fa-cogs'),
        (('conduite', 'canalisation', 'tuyau', 'collecteur'), 'fa-project-diagram'),
        (('solaire', 'panneau'), 'fa-solar-panel'),
        (('groupe', 'generateur', 'electrique'), 'fa-bolt'),
        (('captage', 'source', 'forage', 'puits'), 'fa-water'),
    )
    for needles, icon in mappings:
        if _contains_any(name, needles):
            return icon
    return 'fa-cog'


@register.filter
def equipment_icon_tone(value):
    name = _normalized(value)
    if _contains_any(name, ('citerne', 'reservoir', 'bache', 'chateau')):
        return 'text-info'
    if _contains_any(name, ('vanne', 'robinet', 'clapet', 'compteur', 'debitmetre', 'manometre')):
        return 'text-primary'
    if _contains_any(name, ('filtre', 'traitement', 'chloration', 'chlorateur', 'solaire', 'panneau')):
        return 'text-success'
    if _contains_any(name, ('groupe', 'generateur', 'electrique')):
        return 'text-warning'
    if _contains_any(name, ('captage', 'source', 'forage', 'puits')):
        return 'text-info'
    return 'text-base-content/60'


@register.filter
def ouvrage_icon(value):
    """Semantic icon for an ouvrage type, shared across Hydria domains."""
    name = _normalized(value)
    if _contains_any(name, ('suspendu', 'suspend')):
        return 'fa-pause'
    if 'potentiel' in name:
        return 'fa-lightbulb'
    if _contains_any(name, ('travaux', 'chantier')):
        return 'fa-person-digging'
    if 'bureau' in name:
        return 'fa-building'
    if 'terrain' in name:
        return 'fa-map-location-dot'
    if _contains_any(name, ('forage', 'puits', 'pmh')):
        return 'fa-water'
    if _contains_any(name, ('eau vive', 'traditionnelle')):
        return 'fa-wave-square'
    if 'aepp' in name:
        return 'fa-faucet-drip'
    if _contains_any(name, ('aepg', 'ranontsika', 'sam')):
        return 'fa-droplet'
    return 'fa-water'


@register.filter
def ouvrage_icon_tone(value):
    name = _normalized(value)
    if _contains_any(name, ('suspendu', 'suspend')):
        return 'text-error'
    if 'potentiel' in name:
        return 'text-warning'
    if _contains_any(name, ('travaux', 'chantier')):
        return 'text-warning'
    if _contains_any(name, ('bureau', 'terrain')):
        return 'text-base-content/60'
    if _contains_any(name, ('forage', 'puits', 'pmh', 'eau vive', 'traditionnelle')):
        return 'text-info'
    return 'text-primary'
