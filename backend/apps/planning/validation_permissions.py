import unicodedata
from datetime import datetime

from django.db.models import Q
from django.utils import timezone

from apps.employees.models import HierarchieEmploye


PLANNING_VALIDATION_DIRECTOR_POSTES = {
    'directeur',
    'directrice',
    'directeur general',
    'directrice generale',
}


def _normalize_poste_name(value):
    if not value:
        return ''
    normalized = unicodedata.normalize('NFKD', str(value))
    return normalized.encode('ascii', errors='ignore').decode('ascii').lower().strip()


def _normalize_reference_date(reference_date=None):
    if reference_date is None:
        return timezone.localdate()
    if isinstance(reference_date, datetime):
        if timezone.is_aware(reference_date):
            return timezone.localtime(reference_date).date()
        return reference_date.date()
    return reference_date


def is_planning_validation_director(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return False

    if getattr(user, 'is_superuser', False):
        return True

    employe = getattr(user, 'employe', None)
    poste_nom = _normalize_poste_name(getattr(getattr(employe, 'poste', None), 'nom_poste', ''))
    return poste_nom in PLANNING_VALIDATION_DIRECTOR_POSTES


def get_active_subordinate_employe_ids(root_employe_id, reference_date=None, max_depth=None):
    reference_date = _normalize_reference_date(reference_date)
    if not root_employe_id:
        return set()

    employe_ids = {root_employe_id}
    frontier_ids = {root_employe_id}
    depth = 0

    while frontier_ids and (max_depth is None or depth < max_depth):
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
        depth += 1

    return employe_ids


def get_planning_validation_target_employe_ids(user, reference_date=None, max_depth=2):
    if not user or not getattr(user, 'is_authenticated', False):
        return set()

    if getattr(user, 'is_superuser', False) or is_planning_validation_director(user):
        return None

    employe = getattr(user, 'employe', None)
    root_employe_id = getattr(employe, 'id', None)
    if not root_employe_id:
        return set()

    employe_ids = get_active_subordinate_employe_ids(
        root_employe_id,
        reference_date=reference_date,
        max_depth=max_depth,
    )
    employe_ids.discard(root_employe_id)
    return employe_ids


def can_user_adjust_planning_validation(user, planning_or_employe=None, reference_date=None, max_depth=2):
    if not user or not getattr(user, 'is_authenticated', False):
        return False

    if getattr(user, 'is_superuser', False):
        return True

    employe = getattr(user, 'employe', None)
    current_employe_id = getattr(employe, 'id', None)
    if not current_employe_id:
        return False

    target_employe_id = getattr(planning_or_employe, 'employe_id', None)
    if target_employe_id is None and planning_or_employe is not None:
        target_employe_id = getattr(planning_or_employe, 'id', planning_or_employe)

    if target_employe_id in (None, ''):
        return is_planning_validation_director(user)

    if str(target_employe_id) == str(current_employe_id):
        return is_planning_validation_director(user)

    if is_planning_validation_director(user):
        return True

    allowed_ids = get_planning_validation_target_employe_ids(
        user,
        reference_date=reference_date,
        max_depth=max_depth,
    ) or set()
    target_employe_id = str(target_employe_id)
    return any(str(employe_id) == target_employe_id for employe_id in allowed_ids)
