"""Journal des contributions terrain : qui apporte quelles données dans Hydria.

Principe : un signal pre_save compare la valeur en base à la valeur enregistrée, champ par
champ, et ajoute une ligne `ContributionTerrain` par changement. L'auteur n'est pas connu d'un
signal ; il est fourni par un `ContextVar` rempli par le middleware (session) et par le décorateur
d'authentification par jeton de l'appli mobile.

Limites connues : `QuerySet.update()`, `bulk_create` et le SQL brut ne déclenchent pas de signal
(imports en masse) ; l'historique antérieur à la mise en place n'est pas reconstituable.
"""
import contextvars
import logging

from django.db.models.signals import post_save, pre_save

logger = logging.getLogger(__name__)

_auteur = contextvars.ContextVar('contribution_auteur', default=None)
_source = contextvars.ContextVar('contribution_source', default='systeme')

# --- Barème de l'évaluation : points par intervention, selon la catégorie -------------------
# TODO(human): fixer le poids de chaque catégorie (et éventuellement par action : ajout vs
# modification). Exemple : une photo ou un GPS demandent plus d'effort qu'un nom d'abonné.
POIDS_CATEGORIES = {
    'photo': 1,
    'gps': 1,
    'telephone': 1,
    'nom_abonne': 1,
    'volume_citerne': 1,
}

# Champs suivis : modèle -> {categorie: [champs]}
SUIVI = {
    'billing.PointEau': {
        'nom_abonne': ['nomabonne'],
        'telephone': ['numeroteleph', 'contactabonne'],
        'gps': ['latitude', 'longitude'],
        'photo': ['photos'],
    },
    'infrastructure.EquipementConstitutif': {
        'gps': ['latitude', 'longitude'],
        'photo': ['photos'],
        'volume_citerne': ['volume_m3'],
    },
}
_LIBELLE_MODELE = {'billing.PointEau': 'pointeau', 'infrastructure.EquipementConstitutif': 'equipement'}


def definir_auteur(user, source='web'):
    """Appelé par le middleware et par l'authentification par jeton (mobile)."""
    _auteur.set(user if getattr(user, 'is_authenticated', False) else None)
    _source.set(source)


def _vide(v):
    return v is None or (isinstance(v, str) and not v.strip()) or v == [] or v == {}


def _norm(v):
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, float):
        return round(v, 6)
    if hasattr(v, 'quantize'):  # Decimal
        return round(float(v), 6)
    return v


def _nb_photos(v):
    return len(v) if isinstance(v, list) else 0


def _texte(v):
    return '' if v is None else str(v)[:255]


def _evenements(label, instance, anciennes):
    """Compare les anciennes valeurs (dict, ou None à la création) aux valeurs actuelles."""
    evenements = []
    for categorie, champs in SUIVI[label].items():
        if categorie == 'photo':
            avant = _nb_photos(anciennes.get('photos')) if anciennes else 0
            apres = _nb_photos(getattr(instance, 'photos', None))
            if apres > avant:
                evenements.append(dict(categorie='photo', champ='photos', action='ajout',
                                       quantite=apres - avant, ancienne_valeur=str(avant), nouvelle_valeur=str(apres)))
            elif apres < avant:
                evenements.append(dict(categorie='photo', champ='photos', action='suppression',
                                       quantite=avant - apres, ancienne_valeur=str(avant), nouvelle_valeur=str(apres)))
            continue

        anciens = {c: _norm(anciennes.get(c)) if anciennes else None for c in champs}
        nouveaux = {c: _norm(getattr(instance, c, None)) for c in champs}
        modifies = [c for c in champs if (_vide(anciens[c]) and _vide(nouveaux[c])) is False
                    and anciens[c] != nouveaux[c]]
        if not modifies:
            continue
        # Un point GPS = latitude + longitude : une seule intervention, même si les deux changent.
        if all(_vide(nouveaux[c]) for c in champs):
            action = 'suppression'
        elif all(_vide(anciens[c]) for c in modifies):
            action = 'ajout'
        else:
            action = 'modification'
        evenements.append(dict(
            categorie=categorie, champ=','.join(modifies), action=action, quantite=1,
            ancienne_valeur=' ; '.join(_texte(anciennes.get(c)) for c in champs) if anciennes else '',
            nouvelle_valeur=' ; '.join(_texte(getattr(instance, c, None)) for c in champs),
        ))
    return evenements


def _enregistrer(label, instance, anciennes):
    from apps.core.models import ContributionTerrain
    try:
        evenements = _evenements(label, instance, anciennes)
        if not evenements:
            return
        user = _auteur.get()
        employe = getattr(user, 'employe', None) if user else None
        libelle = (getattr(instance, 'nomabonne', None) or getattr(instance, 'nom_equipement', None)
                   or str(instance))[:255]
        ContributionTerrain.objects.bulk_create([
            ContributionTerrain(
                employe=employe, user=user, modele=_LIBELLE_MODELE[label], objet_id=str(instance.pk),
                objet_libelle=libelle, source=_source.get() if user else 'systeme', **ev)
            for ev in evenements
        ])
    except Exception:  # le journal ne doit jamais empêcher une sauvegarde
        logger.exception('Journal des contributions : enregistrement impossible')


def _avant_sauvegarde(sender, instance, update_fields=None, raw=False, **kwargs):
    label = sender._meta.label
    if raw or label not in SUIVI:
        return
    suivis = {c for champs in SUIVI[label].values() for c in champs}
    if update_fields is not None and not suivis.intersection(update_fields):
        instance._contrib_anciennes = False      # sauvegarde partielle sans rapport : rien à comparer
        return
    anciennes = None
    if not instance._state.adding:
        anciennes = sender.objects.filter(pk=instance.pk).values(*suivis).first()
    instance._contrib_anciennes = anciennes     # None = création


def _apres_sauvegarde(sender, instance, created=False, raw=False, **kwargs):
    label = sender._meta.label
    if raw or label not in SUIVI:
        return
    anciennes = getattr(instance, '_contrib_anciennes', False)
    if anciennes is False:
        return
    _enregistrer(label, instance, None if created else anciennes)
    instance._contrib_anciennes = False


def connecter_signaux():
    from django.apps import apps
    for label in SUIVI:
        modele = apps.get_model(label)
        pre_save.connect(_avant_sauvegarde, sender=modele, dispatch_uid=f'contrib_pre_{label}')
        post_save.connect(_apres_sauvegarde, sender=modele, dispatch_uid=f'contrib_post_{label}')
