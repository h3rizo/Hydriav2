from __future__ import annotations

from datetime import date
from typing import Iterable, List, Optional
import unicodedata

from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from .models import Organisation, PartenaireGestionnaireAffectation


SUPPORT_SAME_BASE_RESPONSABLE_POSTES = {
    'caissiere',
    'caissier',
    'assistant(e) admin',
    'assistant admin',
    'assistante admin',
    'assistante administrative',
    'assistant administratif',
    'raf',
    'responsable administratif et financier',
    'responsable administrative et financier',
    'responsable administrative et financiere',
    'responsable administratif et financiere',
}

SUPPORT_SAME_BASE_RESPONSABLE_POSTES_NORMALIZED = {
    ' '.join(
        unicodedata.normalize('NFKD', poste)
        .encode('ascii', errors='ignore')
        .decode('ascii')
        .lower()
        .strip()
        .split()
    )
    for poste in SUPPORT_SAME_BASE_RESPONSABLE_POSTES
}


def _normalize_poste_name(value):
    if not value:
        return ''
    normalized = unicodedata.normalize('NFKD', str(value).replace('\u2019', "'").replace('`', "'"))
    ascii_only = normalized.encode('ascii', errors='ignore').decode('ascii')
    return ' '.join(ascii_only.lower().strip().split())


def get_user_organisation(user) -> Optional[Organisation]:
    if not user or not getattr(user, 'is_authenticated', False):
        return None
    employe = getattr(user, 'employe', None)
    base = getattr(employe, 'base', None)
    return getattr(base, 'organisation', None)


def get_user_accessible_gestionnaire_ids(user) -> Optional[List[str]]:
    """
    Retourne les IDs d'organisations gestionnaires accessibles.

    - superuser: None (pas de restriction)
    - organisation gestionnaire: [organisation courante]
    - organisation partenaire: IDs des gestionnaires affectés
    - autres cas: []
    """
    if getattr(user, 'is_superuser', False):
        return None

    organisation = get_user_organisation(user)
    if not organisation:
        return []

    if organisation.type_organisation == Organisation.TYPE_PARTENAIRE:
        return list(
            PartenaireGestionnaireAffectation.objects.filter(
                partenaire=organisation
            ).values_list('gestionnaire_id', flat=True)
        )

    return [str(organisation.id)]


def is_partenaire_user(user) -> bool:
    """True si l'utilisateur est rattaché (via sa base) à une organisation partenaire."""
    organisation = get_user_organisation(user)
    return bool(organisation and organisation.type_organisation == Organisation.TYPE_PARTENAIRE)


def get_user_default_scope_organisation_id(user) -> str:
    """
    Valeur par défaut d'un filtre « organisation » pour les pages qui scopent des ouvrages
    par gestionnaire.

    - organisation gestionnaire : son propre ID
    - organisation partenaire : 'all' = tous les gestionnaires qui lui sont affectés
      (son propre ID n'est pas un gestionnaire d'ouvrages : il viderait le périmètre)
    - sans organisation : 'all'
    """
    if is_partenaire_user(user):
        return 'all'
    organisation = get_user_organisation(user)
    return str(organisation.id) if organisation else 'all'


def get_employee_list_organisations(user):
    """
    Organisations entre lesquelles l'utilisateur peut basculer sur la liste des employés.

    - superuser : toutes les organisations
    - organisation partenaire : la sienne + les gestionnaires qui lui sont affectés
    - autres cas : None (pas de bascule, verrouillé sur sa propre organisation)
    """
    if getattr(user, 'is_superuser', False):
        return Organisation.objects.order_by('nom_organisation')
    if is_partenaire_user(user):
        organisation = get_user_organisation(user)
        ids = [str(organisation.id)] + [str(i) for i in (get_user_accessible_gestionnaire_ids(user) or [])]
        return Organisation.objects.filter(id__in=ids).order_by('nom_organisation')
    return None


def resolve_employee_organisation_scope(user, requested='', superuser_default_all=False):
    """
    Périmètre « organisation » d'une page RH (liste, organigramme...), avec sélecteur éventuel.

    Retourne un dict :
    - options        : organisations proposées dans le sélecteur ([] si l'utilisateur est verrouillé)
    - selected       : '' (verrouillé), 'all' ou l'ID d'une organisation
    - organisation   : l'organisation affichée, None si 'all' ou sans organisation
    - organisations  : organisations à filtrer ; None = aucune restriction (superuser sur 'all'),
                       [] = rien ne doit être visible (utilisateur sans organisation)
    `requested` est la valeur reçue en GET ; une valeur hors périmètre retombe sur le défaut.
    `superuser_default_all` : pages où un superuser voit toutes les organisations par défaut
    (sinon, comme les autres utilisateurs, sa propre organisation).
    """
    own = get_user_organisation(user)
    selectables = get_employee_list_organisations(user)
    if selectables is None:
        return {
            'options': [], 'selected': '', 'organisation': own,
            'organisations': [own] if own else [],
        }

    options = list(selectables)
    allowed = {str(o.id): o for o in options}
    default = str(own.id) if own and str(own.id) in allowed else 'all'
    if superuser_default_all and getattr(user, 'is_superuser', False):
        default = 'all'
    selected = (requested or '').strip() or default
    if selected != 'all' and selected not in allowed:
        selected = default
    if selected == 'all':
        return {
            'options': options, 'selected': 'all', 'organisation': None,
            'organisations': None if getattr(user, 'is_superuser', False) else options,
        }
    return {
        'options': options, 'selected': selected, 'organisation': allowed[selected],
        'organisations': [allowed[selected]],
    }


def apply_employee_organisation_scope(queryset, scope, field='base__organisation'):
    """Applique le résultat de resolve_employee_organisation_scope à un queryset d'employés."""
    organisations = scope['organisations']
    if organisations is None:
        return queryset
    return queryset.filter(**{f'{field}__in': organisations})


def get_default_gestionnaire_filter_value(user, allowed_ids=None) -> str:
    """
    Retourne la valeur par défaut à utiliser pour un filtre organisation.

    - superuser: '' (pas de valeur imposée)
    - organisation gestionnaire: son propre ID
    - organisation partenaire: premier gestionnaire partenaire accessible
    - autres cas: ''
    """
    if allowed_ids is None:
        allowed_ids = get_user_accessible_gestionnaire_ids(user)

    if allowed_ids is None:
        return ''

    normalized_ids = [str(item) for item in allowed_ids if item]
    if not normalized_ids:
        return ''

    organisation = get_user_organisation(user)
    if organisation and organisation.type_organisation == Organisation.TYPE_GESTIONNAIRE:
        organisation_id = str(organisation.id)
        if organisation_id in normalized_ids:
            return organisation_id

    return normalized_ids[0]


def get_gestionnaire_organisations_queryset():
    return Organisation.objects.filter(
        type_organisation=Organisation.TYPE_GESTIONNAIRE
    ).order_by('nom_organisation')


def get_gestionnaire_period_bounds(annee=None, limit_current_year_to_today=False):
    today = timezone.localdate()
    if annee not in (None, ''):
        try:
            year = int(annee)
            period_end = date(year, 12, 31)
            if limit_current_year_to_today and year == today.year:
                period_end = today
            return date(year, 1, 1), period_end
        except (TypeError, ValueError):
            pass

    return today, today


def current_modalite_q(prefix='', reference_date=None, allowed_statuts=('actif',)):
    """Condition unique pour une modalite effectivement active a une date.

    Une modalite sans date de fin n'est pas necessairement active : sa date
    de debut peut etre future. ``prefix`` permet de reutiliser exactement la
    meme regle depuis Ouvrage, PointEau, Parcelle, etc.
    """
    reference_date = reference_date or timezone.localdate()
    field = f'{prefix}__' if prefix else ''
    return (
        Q(**{
            f'{field}statut__in': allowed_statuts,
            f'{field}date_debut__lte': reference_date,
        })
        & (
            Q(**{f'{field}date_fin__isnull': True})
            | Q(**{f'{field}date_fin__gte': reference_date})
        )
    )


def filter_current_modalites(modalites_qs, reference_date=None, allowed_statuts=('actif',)):
    """Filtre un queryset ModaliteGestion sur les contrats actifs maintenant."""
    return modalites_qs.filter(
        current_modalite_q(
            reference_date=reference_date,
            allowed_statuts=allowed_statuts,
        )
    )


def _normalize_gestionnaire_ids(gestionnaire_ids):
    if gestionnaire_ids is None:
        return None

    if isinstance(gestionnaire_ids, (str, int)):
        value = str(gestionnaire_ids).strip()
        if not value or value == 'all':
            return []
        return [value]

    normalized = []
    for gestionnaire_id in gestionnaire_ids:
        if gestionnaire_id in (None, ''):
            continue
        normalized.append(str(gestionnaire_id))
    return normalized


def get_active_subordinate_employe_ids(root_employe_id, reference_date=None):
    """
    Retourne l'employé racine et tous ses subordonnés actifs à la date donnée.
    """
    from apps.employees.models import HierarchieEmploye

    reference_date = reference_date or date.today()
    employe_ids = {root_employe_id}
    frontier_ids = {root_employe_id}

    while frontier_ids:
        child_ids = set(
            HierarchieEmploye.objects.filter(
                superieur_id__in=frontier_ids,
                date_debut__lte=reference_date,
            ).filter(
                Q(date_fin__isnull=True) | Q(date_fin__gte=reference_date)
            ).values_list('employe_id', flat=True)
        )
        child_ids -= employe_ids
        if not child_ids:
            break
        employe_ids.update(child_ids)
        frontier_ids = child_ids

    return employe_ids


def get_active_employee_scope_ids(root_employe_id, reference_date=None):
    """Retourne la hierarchie descendante en excluant les employes debauches."""
    from apps.employees.models import Employe

    reference_date = reference_date or date.today()
    hierarchy_ids = get_active_subordinate_employe_ids(root_employe_id, reference_date)
    return set(
        Employe.objects.filter(
            pk__in=hierarchy_ids,
            date_debauchage__isnull=True,
        ).values_list('pk', flat=True)
    )


def get_active_employee_ouvrage_ids(root_employe_id, reference_date=None):
    """Retourne les ouvrages actuellement confies a l'employe ou ses subordonnes actifs."""
    from apps.employees.models import EmployeOuvrages

    reference_date = reference_date or date.today()
    employee_ids = get_active_employee_scope_ids(root_employe_id, reference_date)
    return set(
        EmployeOuvrages.objects.filter(
            employe_id__in=employee_ids,
            date_debut__lte=reference_date,
        ).filter(
            Q(date_fin__isnull=True) | Q(date_fin__gte=reference_date)
        ).values_list('ouvrage_id', flat=True).distinct()
    )


def get_employe_ids_with_responsible_ouvrage_scope(reference_date=None):
    """
    Retourne les employes actifs ayant un ouvrage actif directement ou par
    l'intermediaire d'au moins un subordonne actif, a n'importe quel niveau.
    """
    from apps.employees.models import Employe, EmployeOuvrages, HierarchieEmploye

    reference_date = reference_date or date.today()
    active_employee_ids = set(
        Employe.objects.filter(
            date_debauchage__isnull=True,
        ).values_list('pk', flat=True)
    )
    if not active_employee_ids:
        return set()

    eligible_ids = set(
        EmployeOuvrages.objects.filter(
            employe_id__in=active_employee_ids,
            date_debut__lte=reference_date,
        ).filter(
            Q(date_fin__isnull=True) | Q(date_fin__gte=reference_date)
        ).values_list('employe_id', flat=True).distinct()
    )
    if not eligible_ids:
        return set()

    parents_by_child = {}
    hierarchy_rows = HierarchieEmploye.objects.filter(
        superieur_id__in=active_employee_ids,
        employe_id__in=active_employee_ids,
        date_debut__lte=reference_date,
    ).filter(
        Q(date_fin__isnull=True) | Q(date_fin__gte=reference_date)
    ).values_list('superieur_id', 'employe_id')
    for parent_id, child_id in hierarchy_rows:
        parents_by_child.setdefault(child_id, set()).add(parent_id)

    frontier_ids = set(eligible_ids)
    while frontier_ids:
        parent_ids = {
            parent_id
            for child_id in frontier_ids
            for parent_id in parents_by_child.get(child_id, set())
        } - eligible_ids
        if not parent_ids:
            break
        eligible_ids.update(parent_ids)
        frontier_ids = parent_ids

    return eligible_ids


def is_same_base_responsable_support_role(user) -> bool:
    employe = getattr(user, 'employe', None)
    poste_nom = getattr(getattr(employe, 'poste', None), 'nom_poste', '')
    return _normalize_poste_name(poste_nom) in SUPPORT_SAME_BASE_RESPONSABLE_POSTES_NORMALIZED


def get_same_base_active_employe_ids(root_employe, reference_date=None):
    if not root_employe or not getattr(root_employe, 'base_id', None):
        root_id = getattr(root_employe, 'id', None)
        return {root_id} if root_id else set()

    from apps.employees.models import Employe

    reference_date = reference_date or date.today()
    employe_ids = set(
        Employe.objects.filter(
            base_id=root_employe.base_id,
        ).filter(
            Q(date_debauchage__isnull=True) | Q(date_debauchage__gte=reference_date)
        ).values_list('id', flat=True)
    )
    if getattr(root_employe, 'id', None):
        employe_ids.add(root_employe.id)
    return employe_ids


def get_user_responsable_ouvrage_ids(user, reference_date=None, allow_same_base_support_roles=False):
    """
    Retourne les ouvrages responsables visibles par l'utilisateur :
    - superuser/directeur : None (pas de restriction supplémentaire)
    - autre employé : ouvrages dont lui ou ses subordonnés actifs sont responsables
    - sans employé lié : ensemble vide
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return set()

    if getattr(user, 'is_superuser', False):
        return None

    # Partner scope is defined by its assignments to managing organisations.
    # Partner employees normally have no local EmployeOuvrages assignments, so
    # that second scope must not erase the organisation-level permissions.
    if is_partenaire_user(user):
        return None

    from apps.employees.permissions import is_directeur_poste

    if is_directeur_poste(user):
        return None

    employe = getattr(user, 'employe', None)
    if not employe:
        return set()

    from apps.employees.models import EmployeOuvrages

    reference_date = reference_date or date.today()
    if allow_same_base_support_roles and is_same_base_responsable_support_role(user):
        employe_ids = get_same_base_active_employe_ids(employe, reference_date)
    else:
        employe_ids = get_active_subordinate_employe_ids(employe.id, reference_date)
    return set(
        EmployeOuvrages.objects.filter(
            employe_id__in=employe_ids,
            date_debut__lte=reference_date,
        ).filter(
            Q(date_fin__isnull=True) | Q(date_fin__gte=reference_date)
        ).values_list('ouvrage_id', flat=True).distinct()
    )


def apply_user_responsable_ouvrage_scope(
    ouvrage_ids,
    user,
    reference_date=None,
    allow_same_base_support_roles=False,
):
    """
    Applique le cloisonnement par hiérarchie + responsabilités d'ouvrages.

    `None` signifie "pas de scope initial", auquel cas on retourne uniquement
    les ouvrages responsables accessibles à l'utilisateur.
    """
    scoped_ids = None if ouvrage_ids is None else set(ouvrage_ids)
    allowed_ids = get_user_responsable_ouvrage_ids(
        user,
        reference_date=reference_date,
        allow_same_base_support_roles=allow_same_base_support_roles,
    )

    if allowed_ids is None:
        return scoped_ids

    if scoped_ids is None:
        return allowed_ids

    return scoped_ids.intersection(allowed_ids)


def filter_modalites_by_gestionnaire_period(
    modalites_qs,
    gestionnaire_ids=None,
    annee=None,
    allowed_statuts=('actif', 'resilie'),
    limit_current_year_to_today=False,
):
    ids = _normalize_gestionnaire_ids(gestionnaire_ids)
    if ids == []:
        return modalites_qs.none()

    date_debut, date_fin = get_gestionnaire_period_bounds(
        annee,
        limit_current_year_to_today=limit_current_year_to_today,
    )
    filtered_qs = modalites_qs.filter(
        statut__in=allowed_statuts,
        date_debut__lte=date_fin,
    ).filter(
        Q(date_fin__isnull=True) | Q(date_fin__gte=date_debut)
    )

    if ids is None:
        return filtered_qs

    return filtered_qs.filter(gestionnaire_id__in=ids)


def filter_ouvrages_by_gestionnaire_period(
    ouvrages_qs,
    gestionnaire_ids=None,
    annee=None,
    allowed_statuts=('actif', 'resilie'),
    limit_current_year_to_today=False,
):
    ids = _normalize_gestionnaire_ids(gestionnaire_ids)
    if ids == []:
        return ouvrages_qs.none()

    from apps.billing.models import ModaliteGestion

    date_debut, date_fin = get_gestionnaire_period_bounds(
        annee,
        limit_current_year_to_today=limit_current_year_to_today,
    )
    matching_modalites = ModaliteGestion.objects.filter(
        ouvrage_id=OuterRef('pk'),
        statut__in=allowed_statuts,
        date_debut__lte=date_fin,
    ).filter(
        Q(date_fin__isnull=True) | Q(date_fin__gte=date_debut)
    )

    if ids is not None:
        matching_modalites = matching_modalites.filter(gestionnaire_id__in=ids)

    return ouvrages_qs.annotate(
        _matching_gestionnaire_modalite=Exists(matching_modalites)
    ).filter(
        _matching_gestionnaire_modalite=True
    )
