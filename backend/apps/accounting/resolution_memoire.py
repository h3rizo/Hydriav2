"""Résolution en mémoire des référentiels d'extraction (ouvrages, alias, points d'eau).

Les extracteurs de libellés DiameX déterminent l'ouvrage (puis le point d'eau) d'une
écriture en interrogeant la base :

    Ouvrage.objects.filter(nom_ouvrage__iexact=…).first()   # exact
    OuvrageAlias.objects.filter(alias_normalise=…).first()  # alias connu
    Ouvrage.objects.filter(nom_ouvrage__icontains=…).first() # dernier recours
    PointEau.objects.filter(ouvrage=…, nomabonne__iexact=…).first()
    …

Soit jusqu'à cinq requêtes **par écriture**. Sur les pages qui traitent des milliers de
lignes (vue liste, export JSON du tableau de bord, panneau « Indemnités RBF par point
d'eau »), cela représente des dizaines de milliers de requêtes : plus de dix minutes
mesurées sur 7 500 lignes 621102.

Ce module charge les référentiels **une fois** et répond à ces recherches sans requête,
avec les mêmes règles de comparaison que PostgreSQL (``iexact`` insensible à la casse,
``icontains`` en sous-chaîne, ``in``, ``isnull``), dans l'ordre de ``.first()``
(``Meta.ordering``, sinon la clé primaire). Il ne s'active que dans un contexte
explicite :

    from apps.accounting.resolution_memoire import resolution_memoire

    with resolution_memoire():
        for ecriture in ecritures:
            extraire_ouvrage_et_mois_generique(ecriture.description, ecriture.compte_code)

Hors de ce contexte — ou dès qu'une requête sort du sous-ensemble reconnu (jointure,
annotation, OR, exclusion, agrégat, ordre explicite) — le comportement d'origine est
conservé : la requête part en base.
"""

import logging
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta

from django.db.models import Field
from django.db.models.expressions import Col
from django.db.models.query import ModelIterable, QuerySet

logger = logging.getLogger(__name__)

DUREE_VALIDITE_INDEX = 300  # secondes
_INCONNU = object()

_etat = threading.local()


def _compteurs():
    compteurs = getattr(_etat, 'compteurs', None)
    if compteurs is None:
        compteurs = {'memoire': 0, 'base': 0, 'chargements': 0}
        _etat.compteurs = compteurs
    return compteurs


def statistiques():
    """{recherches résolues en mémoire, renvoyées à la base, chargements d'index}."""
    return dict(_compteurs())


def _mode_actif():
    return bool(getattr(_etat, 'actif', False))


# --------------------------------------------------------------------------------------
# Index des référentiels
# --------------------------------------------------------------------------------------

class _Index:
    """Référentiels préchargés (une requête chacun) et index de recherche."""

    def __init__(self):
        self.charge_le = 0.0
        self.ouvrages = []
        self.ouvrages_par_nom = {}
        self.ouvrages_sans_espaces = {}
        self.alias = []
        self.alias_par_cle = {}
        self.points_eau = []
        self.points_par_ouvrage = {}

    def est_frais(self):
        return (
            self.charge_le
            and (time.monotonic() - self.charge_le) < DUREE_VALIDITE_INDEX
        )

    def charger(self):
        from apps.billing.models import PointEau
        from apps.organization.models import Ouvrage, OuvrageAlias, normaliser_alias_ouvrage

        compteurs = _compteurs()
        compteurs['chargements'] += 1

        # Ouvrage.Meta.ordering = ['nom_ouvrage'] → c'est l'ordre de .first()
        self.ouvrages = list(
            Ouvrage.objects.order_by('nom_ouvrage').only('id', 'nom_ouvrage')
        )
        self.ouvrages_par_nom = {}
        self.ouvrages_sans_espaces = {}
        for ouvrage in self.ouvrages:
            nom = (ouvrage.nom_ouvrage or '').strip()
            if not nom:
                continue
            self.ouvrages_par_nom.setdefault(nom.casefold(), ouvrage)
            self.ouvrages_sans_espaces.setdefault(
                normaliser_alias_ouvrage(nom), ouvrage)

        self.alias = list(
            OuvrageAlias.objects.select_related('ouvrage')
            .order_by('ouvrage__nom_ouvrage', 'alias')
        )
        self.alias_par_cle = {}
        for alias in self.alias:
            cle = (alias.alias_normalise or '').strip()
            if cle:
                self.alias_par_cle.setdefault(cle, alias)

        # PointEau n'a pas de Meta.ordering : .first() trie par clé primaire.
        self.points_eau = list(
            PointEau.objects.select_related('ouvrage', 'type_point_eau')
            .only('id', 'nomabonne', 'code_point_eau', 'idxls', 'ouvrage',
                  'type_point_eau', 'ouvrage__nom_ouvrage', 'type_point_eau__nom_type')
            .order_by('pk')
        )
        self.points_par_ouvrage = {}
        for point in self.points_eau:
            self.points_par_ouvrage.setdefault(point.ouvrage_id, []).append(point)

        self._preparer()

        self.charge_le = time.monotonic()
        logger.debug(
            "[resolution-memoire] index chargé : %s ouvrages, %s alias, %s points d'eau",
            len(self.ouvrages), len(self.alias), len(self.points_eau))
        return self

    # -- Structures de recherche ------------------------------------------------------
    def _preparer(self):
        """Dictionnaires (recherches exactes) et valeurs précalculées (scans)."""
        self.prepares = {}

        prepares_ouvrages = []
        for ouvrage in self.ouvrages:
            nom = ouvrage.nom_ouvrage or ''
            prepares_ouvrages.append((ouvrage, {'nom_ouvrage': nom, 'nom_ouvrage_cf': nom.casefold()}))
        self.prepares['Ouvrage'] = prepares_ouvrages
        self.dicts = {
            'Ouvrage': {
                'nom_ouvrage': {
                    'exact': self._indexer(prepares_ouvrages, 'nom_ouvrage'),
                    'iexact': self._indexer(prepares_ouvrages, 'nom_ouvrage_cf'),
                },
            },
        }

        prepares_alias = [
            (alias, {
                'alias': alias.alias or '',
                'alias_normalise': alias.alias_normalise or '',
                'alias_cf': (alias.alias or '').casefold(),
            })
            for alias in self.alias
        ]
        self.prepares['OuvrageAlias'] = prepares_alias
        self.dicts['OuvrageAlias'] = {
            'alias_normalise': {
                'exact': self._indexer(prepares_alias, 'alias_normalise'),
                'iexact': self._indexer(prepares_alias, 'alias_normalise'),
            },
            'alias': {
                'exact': self._indexer(prepares_alias, 'alias'),
                'iexact': self._indexer(prepares_alias, 'alias_cf'),
            },
        }

        prepares_points = []
        compteurs_indemnite = {}
        for point in self.points_eau:
            nom = point.nomabonne or ''
            code = point.code_point_eau or ''
            idxls = '' if point.idxls is None else str(point.idxls)
            type_point = getattr(point, 'type_point_eau', None)
            type_nom = (getattr(type_point, 'nom_type', '') or '') if type_point is not None else ''
            prepares_points.append((point, {
                'nomabonne': nom,
                'nomabonne_cf': nom.casefold(),
                'code_point_eau': code,
                'code_point_eau_cf': code.casefold(),
                'idxls': idxls,
                'ouvrage_id': point.ouvrage_id,
                'type_point_eau__nom_type': type_nom,
            }))
            # Comptage des points d'indemnité (BF / PMH / PMHI) par ouvrage : évite la
            # requête de _indemnity_point_id (une par ouvrage).
            compteurs_indemnite.setdefault(point.ouvrage_id, [0, 0])
            compteurs_indemnite[point.ouvrage_id][0] += 1
            if type_nom.upper() in ('BF', 'PMH', 'PMHI'):
                compteurs_indemnite[point.ouvrage_id][1] += 1
        self.prepares['PointEau'] = prepares_points
        self.compteurs_indemnite = compteurs_indemnite
        self._indexer_valeurs()
        self.dicts['PointEau'] = {
            'nomabonne': {
                'exact': self._indexer(prepares_points, 'nomabonne'),
                'iexact': self._indexer(prepares_points, 'nomabonne_cf'),
            },
            'code_point_eau': {
                'exact': self._indexer(prepares_points, 'code_point_eau'),
                'iexact': self._indexer(prepares_points, 'code_point_eau_cf'),
            },
            'idxls': {
                'exact': self._indexer(prepares_points, 'idxls'),
                'iexact': self._indexer(prepares_points, 'idxls'),
            },
            'ouvrage': {
                'exact': {str(cle): liste for cle, liste in self.points_par_ouvrage.items()},
            },
            'ouvrage_id': {
                'exact': {str(cle): liste for cle, liste in self.points_par_ouvrage.items()},
            },
            'type_point_eau__nom_type': {
                'exact': self._indexer(prepares_points, 'type_point_eau__nom_type'),
            },
        }
        self.dicts['PointEau']['ouvrage']['iexact'] = self.dicts['PointEau']['ouvrage']['exact']
        self.dicts['PointEau']['ouvrage_id']['iexact'] = self.dicts['PointEau']['ouvrage_id']['exact']

    @staticmethod
    def _indexer(prepares, cle_valeur):
        """Dict valeur → objets (dans l'ordre de ``.first()``)."""
        dictionnaire = {}
        for objet, valeurs in prepares:
            valeur = valeurs.get(cle_valeur)
            if valeur is None or valeur == '':
                continue
            dictionnaire.setdefault(valeur, []).append(objet)
        return dictionnaire

    def _indexer_valeurs(self):
        """Valeurs précalculées accessibles par identité d'objet."""
        self.valeurs_par_id = {}
        for prepares in self.prepares.values():
            for objet, valeurs in prepares:
                self.valeurs_par_id[id(objet)] = valeurs

        # Chaînes déjà passées en minuscules, pour les recherches « contient » :
        # un parcours direct évite getattr/casefold à chaque comparaison.
        self.chaines = {}
        for modele_nom, prepares in self.prepares.items():
            for champ in ('nom_ouvrage', 'alias', 'nomabonne', 'code_point_eau'):
                couples = []
                for objet, valeurs in prepares:
                    texte = valeurs.get(f'{champ}_cf')
                    if texte is None:
                        texte = valeurs.get(champ)
                        texte = texte.casefold() if isinstance(texte, str) else None
                    if texte:
                        couples.append((texte, objet))
                if couples:
                    self.chaines[(modele_nom, champ)] = couples

        # Réponses déjà calculées (recherches identiques d'une ligne à l'autre).
        self.memo = {}

    def recherche_directe(self, modele_nom, conditions):
        """Traite les recherches « contient » sur un seul champ, sans parcours générique."""
        if len(conditions) != 1:
            return False, None
        champ, lookup, attendu = conditions[0]
        if lookup != 'icontains' or attendu is None:
            return False, None
        couples = self.chaines.get((modele_nom, champ))
        if not couples:
            return False, None
        aiguille = str(attendu).casefold()
        for texte, objet in couples:
            if aiguille in texte:
                return True, objet
        return True, None

    def candidats(self, modele_nom, champ, lookup, attendu):
        """Objets candidats d'après l'index, ou ``None`` si ce champ n'est pas indexé.

        La liste renvoyée respecte l'ordre de ``.first()`` : le premier élément qui
        satisfait les autres conditions est bien la réponse de la base.
        """
        dictionnaires = self.dicts.get(modele_nom, {}).get(champ)
        if not dictionnaires:
            return None
        table = dictionnaires.get(lookup)
        if table is None:
            return None
        if lookup == 'iexact' and champ in CHAMPS_TEXTE:
            cle = str(attendu).casefold()
        else:
            cle = str(_sans_pk(attendu))
        return table.get(cle) or []


_index = _Index()
_verrou = threading.Lock()


def index_actuel(force=False):
    """Index courant. Rechargé (et échangé atomiquement) quand il a expiré."""
    global _index
    if _index.est_frais() and not force:
        return _index
    with _verrou:
        if _index.est_frais() and not force:
            return _index
        _index = _Index().charger()
    return _index


# --------------------------------------------------------------------------------------
# Lecture des conditions d'un queryset
# --------------------------------------------------------------------------------------

# Champs sur lesquels la résolution en mémoire est autorisée, par modèle.
CHAMPS_AUTORISES = {
    'Ouvrage': {'nom_ouvrage'},
    'OuvrageAlias': {'alias', 'alias_normalise'},
    'PointEau': {'nomabonne', 'code_point_eau', 'idxls', 'ouvrage', 'ouvrage_id',
                 'type_point_eau__nom_type'},
}
CHAMPS_TEXTE = {'nom_ouvrage', 'alias', 'alias_normalise', 'nomabonne', 'code_point_eau'}
# Jointures autorisées : champ de la requête → champ précalculé équivalent.
JOINTURES_AUTORISEES = {
    ('PointEau', 'TypePointEau', 'nom_type'): 'type_point_eau__nom_type',
}
LOOKUPS_AUTORISES = {'exact', 'iexact', 'icontains', 'in', 'isnull'}


def _conditions_simples(queryset):
    """Conditions ``champ lookup valeur`` du WHERE, ou ``None`` si non reconnu."""
    requete = queryset.query
    if getattr(queryset, '_iterable_class', None) is not ModelIterable:
        return None  # values()/values_list() : le résultat n'est pas un objet
    if requete.is_sliced or requete.distinct or requete.annotation_select:
        return None
    if requete.order_by:  # ordre explicite : laissé à la base
        return None
    if requete.combinator:
        return None

    autorises = CHAMPS_AUTORISES.get(queryset.model.__name__)
    if not autorises:
        return None

    where = requete.where
    if where.negated or where.connector != 'AND':
        return None

    conditions = []
    for enfant in where.children:
        lhs = getattr(enfant, 'lhs', None)
        lookup = getattr(enfant, 'lookup_name', None)
        if lookup not in LOOKUPS_AUTORISES:
            return None
        # Django résout le champ en colonne (Col) avant de le stocker dans le WHERE ;
        # sur les versions plus anciennes c'est directement le Field.
        if isinstance(lhs, Col):
            champ = lhs.target
        elif isinstance(lhs, Field):
            champ = lhs
        else:
            return None

        nom_modele = queryset.model.__name__
        if champ.model.__name__ == nom_modele:
            nom_champ = champ.name
        else:
            # Jointure traversée : seules celles déclarées sont résolues en mémoire.
            nom_champ = JOINTURES_AUTORISEES.get(
                (nom_modele, champ.model.__name__, champ.name))
            if nom_champ is None:
                return None
        if nom_champ not in autorises:
            return None
        if getattr(enfant, 'rhs', None) is None and lookup != 'isnull':
            return None
        conditions.append((nom_champ, lookup, enfant.rhs))
    return conditions


def _valeur_champ(objet, champ):
    if champ in ('ouvrage', 'ouvrage_id'):
        return getattr(objet, 'ouvrage_id')
    return getattr(objet, champ)


def _sans_pk(valeur):
    if hasattr(valeur, 'pk') and not isinstance(valeur, (str, bytes)):
        return valeur.pk
    return valeur


def _comparer(valeur, lookup, attendu, valeur_cf=None):
    if lookup == 'isnull':
        return (valeur is None) == bool(attendu)

    if lookup == 'in':
        return any(_comparer(valeur, 'exact', _sans_pk(item)) for item in attendu)

    attendu = _sans_pk(attendu)

    if lookup == 'exact':
        if valeur is None or attendu is None:
            return valeur is None and attendu is None
        return str(valeur) == str(attendu)
    if lookup == 'iexact':
        if valeur is None or attendu is None:
            return valeur is None and attendu is None
        texte = valeur_cf if valeur_cf is not None else str(valeur).casefold()
        return texte == str(attendu).casefold()
    if lookup == 'icontains':
        if valeur is None or attendu is None:
            return False
        texte = valeur_cf if valeur_cf is not None else str(valeur).casefold()
        return str(attendu).casefold() in texte
    return False


def _source_index(modele, index):
    nom = modele.__name__
    if nom == 'Ouvrage':
        return index.ouvrages
    if nom == 'OuvrageAlias':
        return index.alias
    if nom == 'PointEau':
        return index.points_eau
    return None


def _valeur_preparee(valeurs, objet, champ):
    if valeurs is not None and champ in valeurs:
        return valeurs[champ]
    return _valeur_champ(objet, champ)


def _valeur_casefold(valeurs, champ):
    if valeurs is None:
        return None
    return valeurs.get(f'{champ}_cf')


def _correspond(valeurs, objet, conditions):
    for champ, lookup, attendu in conditions:
        if lookup in ('iexact', 'icontains'):
            if not _comparer(_valeur_preparee(valeurs, objet, champ), lookup, attendu,
                             _valeur_casefold(valeurs, champ)):
                return False
        elif not _comparer(_valeur_preparee(valeurs, objet, champ), lookup, attendu):
            return False
    return True


def _cle_memo(modele_nom, conditions):
    morceaux = []
    for champ, lookup, attendu in conditions:
        if isinstance(attendu, (list, tuple, set)):
            valeur = tuple(sorted(str(_sans_pk(item)) for item in attendu))
        else:
            valeur = str(_sans_pk(attendu))
        morceaux.append((champ, lookup, valeur))
    return (modele_nom,) + tuple(morceaux)


def _iterer(conditions, modele_nom, index):
    """(objets à examiner, conditions restantes).

    Parmi les conditions indexées, on retient celle qui laisse le **moins** de
    candidats (``idxls='1'`` peut désigner des centaines de points d'eau, alors que
    ``ouvrage=…`` n'en désigne que quelques-uns). L'ordre de ``.first()`` est conservé
    par les listes d'index : le premier candidat qui satisfait le reste est la réponse.
    """
    prepares = index.prepares[modele_nom]
    meilleurs = None
    meilleures_conditions = conditions

    for position, (champ, lookup, attendu) in enumerate(conditions):
        candidats = index.candidats(modele_nom, champ, lookup, attendu)
        if candidats is None:
            continue
        if meilleurs is None or len(candidats) < len(meilleurs):
            meilleurs = candidats
            meilleures_conditions = conditions[:position] + conditions[position + 1:]
            if not meilleurs:
                break

    if meilleurs is not None:
        return meilleurs, meilleures_conditions
    return [objet for objet, _ in prepares], conditions


def resoudre(queryset, index=None):
    """Répond à ``queryset.first()`` depuis la mémoire.

    Retourne ``_INCONNU`` si la requête n'est pas reconnue (l'appelant interroge la
    base), sinon l'objet trouvé ou ``None``. Les réponses sont mémorisées : sur une
    page qui traite des milliers de lignes, les mêmes libellés reviennent.
    """
    index = index or index_actuel()
    conditions = _conditions_simples(queryset)
    if conditions is None:
        return _INCONNU

    modele_nom = queryset.model.__name__
    if modele_nom not in index.prepares:
        return _INCONNU

    cle = _cle_memo(modele_nom, conditions)
    if cle in index.memo:
        return index.memo[cle]

    traite, resultat = index.recherche_directe(modele_nom, conditions)
    if not traite:
        objets, restantes = _iterer(conditions, modele_nom, index)
        resultat = None
        for objet in objets:
            if _correspond(index.valeurs_par_id.get(id(objet)), objet, restantes):
                resultat = objet
                break

    index.memo[cle] = resultat
    return resultat


def compter(queryset, index=None):
    """Équivalent de ``queryset.count()`` depuis la mémoire, ou ``None`` si non reconnu."""
    index = index or index_actuel()
    conditions = _conditions_simples(queryset)
    if conditions is None:
        return None
    modele_nom = queryset.model.__name__
    if modele_nom not in index.prepares:
        return None
    objets, restantes = _iterer(conditions, modele_nom, index)
    return sum(
        1 for objet in objets
        if _correspond(index.valeurs_par_id.get(id(objet)), objet, restantes)
    )


def nombre_points_indemnite(ouvrage_id):
    """Nombre de points d'eau d'un ouvrage susceptibles de recevoir une indemnité (BF/PMH/PMHI).

    Retourne ``(actif, nombre)`` : ``actif=False`` signifie « mode mémoire inactif,
    interroge la base ».
    """
    if not _mode_actif():
        return False, None
    index = index_actuel()
    total, indemnites = index.compteurs_indemnite.get(ouvrage_id, [0, 0])
    return True, indemnites


def ouvrage_par_nom_sans_espaces(nom_sans_espaces):
    """Ouvrage dont le nom, espaces retirés et en minuscules, vaut ``nom_sans_espaces``.

    Retourne ``(actif, ouvrage)`` : ``actif=False`` signifie « mode mémoire inactif,
    interroge la base ».
    """
    if not _mode_actif():
        return False, None
    index = index_actuel()
    return True, index.ouvrages_sans_espaces.get((nom_sans_espaces or '').strip())


# --------------------------------------------------------------------------------------
# Substituts de manager / queryset
# --------------------------------------------------------------------------------------

class _QuerysetMemoire:
    """Enveloppe un queryset : ``first()``/``count()``/``exists()`` répondent depuis la
    mémoire, tout le reste est délégué (et ré-enveloppé quand c'est un queryset)."""

    __slots__ = ('_qs', '_index')

    def __init__(self, queryset, index):
        self._qs = queryset
        self._index = index

    def __getattr__(self, nom):
        attribut = getattr(self._qs, nom)
        if not callable(attribut):
            return attribut

        def enveloppe(*args, **kwargs):
            resultat = attribut(*args, **kwargs)
            if isinstance(resultat, QuerySet):
                return _QuerysetMemoire(resultat, self._index)
            return resultat

        return enveloppe

    def __iter__(self):
        return iter(self._qs)

    def __len__(self):
        return len(list(self._qs))

    def __getitem__(self, cle):
        return self._qs[cle]

    def __repr__(self):
        return f'<QuerysetMemoire {self._qs!r}>'

    def first(self):
        resultat = resoudre(self._qs, self._index)
        if resultat is _INCONNU:
            _compteurs()['base'] += 1
            return self._qs.first()
        _compteurs()['memoire'] += 1
        return resultat

    def count(self):
        total = compter(self._qs, self._index)
        if total is None:
            _compteurs()['base'] += 1
            return self._qs.count()
        _compteurs()['memoire'] += 1
        return total

    def exists(self):
        resultat = resoudre(self._qs, self._index)
        if resultat is _INCONNU:
            _compteurs()['base'] += 1
            return self._qs.exists()
        _compteurs()['memoire'] += 1
        return resultat is not None


class _ManagerMemoire:
    """Substitut de manager : renvoie des querysets enveloppés."""

    __slots__ = ('_manager', '_index')

    def __init__(self, manager, index):
        self._manager = manager
        self._index = index

    def __getattr__(self, nom):
        attribut = getattr(self._manager, nom)
        if not callable(attribut):
            return attribut

        def enveloppe(*args, **kwargs):
            resultat = attribut(*args, **kwargs)
            if isinstance(resultat, QuerySet):
                return _QuerysetMemoire(resultat, self._index)
            return resultat

        return enveloppe

    def __repr__(self):
        return f'<ManagerMemoire {self._manager!r}>'

    def get_queryset(self):
        return _QuerysetMemoire(self._manager.get_queryset(), self._index)

    def all(self):
        return _QuerysetMemoire(self._manager.all(), self._index)

    def filter(self, *args, **kwargs):
        return _QuerysetMemoire(self._manager.filter(*args, **kwargs), self._index)

    def exclude(self, *args, **kwargs):
        return _QuerysetMemoire(self._manager.exclude(*args, **kwargs), self._index)

    def none(self):
        return self._manager.none()

    def first(self):
        return _QuerysetMemoire(self._manager.all(), self._index).first()


_MODELES = ('Ouvrage', 'OuvrageAlias', 'PointEau')


def _modeles():
    from apps.billing.models import PointEau
    from apps.organization.models import Ouvrage, OuvrageAlias

    return {'Ouvrage': Ouvrage, 'OuvrageAlias': OuvrageAlias, 'PointEau': PointEau}


def _activer():
    index = index_actuel()
    originaux = {}
    for nom, modele in _modeles().items():
        originaux[nom] = modele.__dict__.get('objects')
        modele.objects = _ManagerMemoire(modele._default_manager, index)
    _etat.originaux = originaux
    _etat.actif = True


def _desactiver():
    originaux = getattr(_etat, 'originaux', {}) or {}
    for nom, modele in _modeles().items():
        if nom in originaux and originaux[nom] is not None:
            modele.objects = originaux[nom]
    _etat.originaux = {}
    _etat.actif = False


@contextmanager
def resolution_memoire():
    """Active la résolution en mémoire des référentiels pour le bloc courant."""
    if _mode_actif():  # déjà actif (appel imbriqué) : ne pas empiler les substituts
        yield
        return
    _activer()
    try:
        yield
    finally:
        _desactiver()


def reinitialiser_index():
    """Force le rechargement de l'index au prochain accès (tests, admin des ouvrages)."""
    _index.charge_le = 0.0
