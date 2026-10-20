from django.http import JsonResponse
from django.db import connection, transaction
from django.db.models import Q
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
import json
import re
import unicodedata
from datetime import datetime, timedelta
from urllib.parse import urlencode
from uuid import UUID
from apps.planning.models import (
    Planning,
    PlanningDetail,
    ActivitePoste,
    PlanningPiece,
    PlanningEmploye,
    TypeActivite,
    BonLivraison,
)
from apps.planning.validation_permissions import can_user_adjust_planning_validation
from apps.core.views_mobile_auth import mobile_auth_required
from apps.planning.repair_workflow_grading import get_repair_workflow_grading_from_plannings
from apps.filemanager.models import FileUpload
from apps.filemanager.services import storage_service, generate_unique_filename, get_file_category
from apps.billing.models import PaiementForfaitaire
from apps.employees.models import Employe
from apps.employees.models_evaluation import Evaluation
from apps.employees.utils_conges import est_jour_ferie as est_jour_ferie_officiel

PLANNING_FORM_ALLOWED_TYPE_NAMES = (
    'Bureau',
    'Entretien',
    'Frais de déplacement',
)

SHARED_NO_OUVRAGE_ACTIVITY_LABELS = {
    'jour ferie',
}


def _normalize_poste_name(value):
    if not value:
        return ''
    normalized = unicodedata.normalize('NFKD', str(value))
    return normalized.encode('ascii', errors='ignore').decode('ascii').lower().strip()


def _is_shared_no_ouvrage_activity_label(label):
    return _normalize_poste_name(label) in SHARED_NO_OUVRAGE_ACTIVITY_LABELS


def _format_frequence_requise_label(frequence_mois, mode_frequence):
    if not frequence_mois:
        return ''

    frequency_labels = {
        1: 'Tous les mois',
        2: 'Tous les 2 mois',
        6: 'Tous les 6 mois',
        12: 'Tous les ans',
    }
    base_label = frequency_labels.get(frequence_mois, f'Tous les {frequence_mois} mois')

    mode_labels = {
        'par_employe': 'par employe',
        'par_employe_ouvrage': 'par employe et ouvrage',
    }
    mode_label = mode_labels.get(mode_frequence or '', '')
    if mode_label:
        return f'{base_label}, {mode_label}'
    return base_label


def _build_fiche_frequency_maps(fiches_poste, employees):
    fiche_ids = [fiche.id for fiche in fiches_poste]
    poste_ids = {str(emp.poste_id) for emp in employees if getattr(emp, 'poste_id', None)}
    if not fiche_ids:
        return {}, {}

    links = list(
        ActivitePoste.objects.filter(
            is_active=True,
            fiche_poste_id__in=fiche_ids,
        ).filter(
            Q(poste_id__isnull=True) | Q(poste_id__in=poste_ids)
        ).select_related('poste')
    )

    generic_labels = {}
    poste_labels = {}

    for link in links:
        label = _format_frequence_requise_label(link.frequence_mois, link.mode_frequence)
        if not label:
            continue

        fiche_key = str(link.fiche_poste_id)
        poste_key = str(link.poste_id) if link.poste_id else ''

        if poste_key:
            poste_labels[f'{poste_key}:{fiche_key}'] = label
        else:
            generic_labels.setdefault(fiche_key, label)

    return generic_labels, poste_labels


def _build_fiche_access_maps(fiches_poste, employees):
    fiche_ids = [fiche.id for fiche in fiches_poste]
    poste_ids = {str(emp.poste_id) for emp in employees if getattr(emp, 'poste_id', None)}
    if not fiche_ids:
        return set(), {}

    links = list(
        ActivitePoste.objects.filter(
            is_active=True,
            fiche_poste_id__in=fiche_ids,
        ).filter(
            Q(poste_id__isnull=True) | Q(poste_id__in=poste_ids)
        )
    )

    generic_fiche_ids = set()
    poste_to_fiche_ids = {}

    for link in links:
        fiche_key = str(link.fiche_poste_id)
        poste_key = str(link.poste_id) if link.poste_id else ''
        if poste_key:
            poste_to_fiche_ids.setdefault(poste_key, set()).add(fiche_key)
        else:
            generic_fiche_ids.add(fiche_key)

    return generic_fiche_ids, poste_to_fiche_ids




def _get_employee_scope_kind(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return 'none'
    if getattr(user, 'is_superuser', False):
        return 'all'

    employe = getattr(user, 'employe', None)
    if not employe:
        return 'none'

    poste_nom = _normalize_poste_name(getattr(getattr(employe, 'poste', None), 'nom_poste', ''))
    if 'directeur' in poste_nom:
        return 'organisation'
    return 'base'


def _get_descendant_employee_ids(employe):
    if not employe or not getattr(employe, 'id', None):
        return set()

    descendants = set()
    queue = [str(employe.id)]
    today = timezone.localdate()

    while queue:
        current_superieur_id = queue.pop(0)
        relations = (
            Employe.objects.filter(relations_hierarchiques__superieur_id=current_superieur_id)
            .filter(relations_hierarchiques__date_debut__lte=today)
            .filter(Q(relations_hierarchiques__date_fin__gte=today) | Q(relations_hierarchiques__date_fin__isnull=True))
            .distinct()
        )

        for subordonne in relations:
            subordonne_id = str(subordonne.id)
            if subordonne_id in descendants:
                continue
            descendants.add(subordonne_id)
            queue.append(subordonne_id)

    return descendants


def _get_scoped_employees_queryset(user):
    scope = _get_employee_scope_kind(user)
    if scope == 'none':
        return Employe.objects.none()
    if scope == 'all':
        return Employe.objects.filter(date_debauchage__isnull=True)

    employe = getattr(user, 'employe', None)
    if not employe:
        return Employe.objects.none()

    queryset = Employe.objects.filter(date_debauchage__isnull=True)

    if scope == 'base':
        base_id = getattr(employe, 'base_id', None)
        if not base_id:
            return Employe.objects.none()
        return queryset.filter(base_id=base_id)

    if scope == 'organisation':
        organisation_id = getattr(getattr(employe, 'base', None), 'organisation_id', None)
        if not organisation_id:
            return Employe.objects.none()
        return queryset.filter(base__organisation_id=organisation_id)

    allowed_ids = _get_descendant_employee_ids(employe)
    allowed_ids.add(str(employe.id))
    return queryset.filter(id__in=allowed_ids)

def _get_planning_activity_label(*, planning=None, fiche_poste=None, type_activite=None):
    if fiche_poste and getattr(fiche_poste, 'tache', None):
        return str(fiche_poste.tache).strip()
    if type_activite and getattr(type_activite, 'nomtype', None):
        return str(type_activite.nomtype).strip()
    if planning is not None:
        if getattr(planning, 'fiche_poste', None) and getattr(planning.fiche_poste, 'tache', None):
            return str(planning.fiche_poste.tache).strip()
        if getattr(planning, 'type_activite', None) and getattr(planning.type_activite, 'nomtype', None):
            return str(planning.type_activite.nomtype).strip()
        remarque = _normalize_poste_name(getattr(planning, 'remarque', ''))
        if 'jour ferie' in remarque:
            return 'Jour férié'
    return ''


def _find_duplicate_plannings_by_activity_label(
    candidates,
    *,
    planning=None,
    fiche_poste=None,
    type_activite=None,
):
    target_label = _normalize_poste_name(
        _get_planning_activity_label(
            planning=planning,
            fiche_poste=fiche_poste,
            type_activite=type_activite,
        )
    )
    if not target_label:
        return []

    matches = []
    for candidate in candidates:
        candidate_label = _normalize_poste_name(_get_planning_activity_label(planning=candidate))
        if candidate_label and candidate_label == target_label:
            matches.append(candidate)
    return matches


def _match_duplicate_planning_by_activity_label(candidates, *, fiche_poste=None, type_activite=None):
    matches = _find_duplicate_plannings_by_activity_label(
        candidates,
        fiche_poste=fiche_poste,
        type_activite=type_activite,
    )
    return matches[0] if matches else None


def _find_duplicate_planning_for_submission(
    date_planning,
    ouvrage_id,
    *,
    fiche_poste=None,
    type_activite=None,
    exclude_planning_id=None,
    employe=None,
):
    if not date_planning:
        return None

    activity_label = _normalize_poste_name(
        _get_planning_activity_label(
            fiche_poste=fiche_poste,
            type_activite=type_activite,
        )
    )
    if not activity_label:
        return None

    try:
        planning_date = datetime.strptime(str(date_planning), '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None

    candidate_filters = {
        'date__date': planning_date,
    }
    if ouvrage_id:
        candidate_filters['ouvrage_id'] = ouvrage_id
    elif _is_shared_no_ouvrage_activity_label(activity_label):
        candidate_filters['ouvrage_id__isnull'] = True
    else:
        return None

    candidates = Planning.objects.filter(
        **candidate_filters,
    ).select_related('fiche_poste', 'type_activite', 'employe').order_by('created_at', 'date')
    if exclude_planning_id:
        candidates = candidates.exclude(id=exclude_planning_id)

    return _match_duplicate_planning_by_activity_label(
        candidates,
        fiche_poste=fiche_poste,
        type_activite=type_activite,
    )


def _build_new_secondary_participant_ids(planning, employe_id, participant_ids, existing_participant_ids=None):
    existing_ids = {
        str(participant_id).strip()
        for participant_id in (existing_participant_ids or [])
        if participant_id
    }
    owner_id = str(getattr(planning, 'employe_id', '') or '').strip()
    new_ids = []

    for candidate_id in [employe_id, *(participant_ids or [])]:
        candidate_str = str(candidate_id or '').strip()
        if not candidate_str or candidate_str == owner_id or candidate_str in existing_ids:
            continue
        existing_ids.add(candidate_str)
        new_ids.append(candidate_str)

    return new_ids


def _parse_planning_photo_payload(value):
    if not value:
        return []

    if isinstance(value, list):
        items = value
    else:
        try:
            items = json.loads(str(value))
        except (TypeError, ValueError, json.JSONDecodeError):
            return []

    if not isinstance(items, list):
        return []

    return [item for item in items if isinstance(item, dict) and item.get('data')]


def _merge_planning_photo_payloads(primary_photo, duplicate_photos):
    merged_items = []
    seen_keys = set()

    for payload in [primary_photo, *(duplicate_photos or [])]:
        for item in _parse_planning_photo_payload(payload):
            dedupe_key = (
                str(item.get('name') or '').strip(),
                str(item.get('size') or '').strip(),
                str(item.get('date') or '').strip(),
                str(item.get('data') or '').strip(),
            )
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            merged_items.append(item)

    return json.dumps(merged_items, ensure_ascii=True) if merged_items else ''


def _merge_duplicate_planning_participants(planning, employe_id, participant_ids):
    existing_participant_ids = list(
        PlanningEmploye.objects.filter(planning_id=planning.id).values_list('employee_id', flat=True)
    )
    new_participant_ids = _build_new_secondary_participant_ids(
        planning,
        employe_id,
        participant_ids,
        existing_participant_ids=existing_participant_ids,
    )

    for participant_id in new_participant_ids:
        PlanningEmploye.objects.get_or_create(
            planning_id=planning.id,
            employee_id=participant_id,
        )

    if new_participant_ids:
        planning.updated_at = timezone.now()
        planning.save(update_fields=['updated_at'])

    return new_participant_ids


def _find_duplicate_plannings_for_existing_planning(planning):
    if not planning or not planning.date:
        return []

    activity_label = _normalize_poste_name(_get_planning_activity_label(planning=planning))
    if not activity_label:
        return []

    candidate_filters = {
        'date__date': planning.date.date(),
    }
    if planning.ouvrage_id:
        candidate_filters['ouvrage_id'] = planning.ouvrage_id
    elif _is_shared_no_ouvrage_activity_label(activity_label):
        candidate_filters['ouvrage_id__isnull'] = True
    else:
        return []

    candidates = (
        Planning.objects.filter(
            **candidate_filters,
        )
        .exclude(id=planning.id)
        .select_related('fiche_poste', 'type_activite', 'employe')
        .order_by('created_at', 'date', 'id')
    )

    return _find_duplicate_plannings_by_activity_label(candidates, planning=planning)


def _merge_duplicate_plannings_into_current(planning):
    duplicate_plannings = _find_duplicate_plannings_for_existing_planning(planning)
    if not duplicate_plannings:
        return {
            'duplicates': 0,
            'participants_added': 0,
            'details_moved': 0,
            'bons_moved': 0,
            'paiements_moved': 0,
            'pieces_moved': 0,
            'photos_added': 0,
        }

    duplicate_ids = [duplicate.id for duplicate in duplicate_plannings]
    duplicate_owner_ids = [duplicate.employe_id for duplicate in duplicate_plannings if duplicate.employe_id]
    duplicate_participant_ids = list(
        PlanningEmploye.objects.filter(planning_id__in=duplicate_ids).values_list('employee_id', flat=True)
    )
    existing_participant_ids = list(
        PlanningEmploye.objects.filter(planning_id=planning.id).values_list('employee_id', flat=True)
    )
    new_participant_ids = _build_new_secondary_participant_ids(
        planning,
        '',
        [*duplicate_owner_ids, *duplicate_participant_ids],
        existing_participant_ids=existing_participant_ids,
    )

    details_count = PlanningDetail.objects.filter(planning_id__in=duplicate_ids).count()
    bons_count = BonLivraison.objects.filter(planning_id__in=duplicate_ids).count()
    paiements_count = PaiementForfaitaire.objects.filter(planning_id__in=duplicate_ids).count()
    pieces_count = PlanningPiece.objects.filter(planning_id__in=duplicate_ids).count()

    initial_photo_count = len(_parse_planning_photo_payload(planning.photo))
    merged_photo_payload = _merge_planning_photo_payloads(
        planning.photo,
        [duplicate.photo for duplicate in duplicate_plannings],
    )
    merged_photo_count = len(_parse_planning_photo_payload(merged_photo_payload))

    with transaction.atomic():
        if details_count:
            PlanningDetail.objects.filter(planning_id__in=duplicate_ids).update(planning=planning)
        if bons_count:
            BonLivraison.objects.filter(planning_id__in=duplicate_ids).update(planning=planning)
        if paiements_count:
            PaiementForfaitaire.objects.filter(planning_id__in=duplicate_ids).update(planning=planning)
        if pieces_count:
            PlanningPiece.objects.filter(planning_id__in=duplicate_ids).update(planning=planning)
        if new_participant_ids:
            PlanningEmploye.objects.bulk_create(
                [
                    PlanningEmploye(planning_id=planning.id, employee_id=participant_id)
                    for participant_id in new_participant_ids
                ],
                ignore_conflicts=True,
            )

        planning.updated_at = timezone.now()
        update_fields = ['updated_at']
        if merged_photo_payload != (planning.photo or ''):
            planning.photo = merged_photo_payload
            update_fields.append('photo')
        planning.save(update_fields=update_fields)

        Planning.objects.filter(id__in=duplicate_ids).delete()

    return {
        'duplicates': len(duplicate_ids),
        'participants_added': len(new_participant_ids),
        'details_moved': details_count,
        'bons_moved': bons_count,
        'paiements_moved': paiements_count,
        'pieces_moved': pieces_count,
        'photos_added': max(0, merged_photo_count - initial_photo_count),
    }


def _build_next_day_planning_redirect(date_planning, employe_id, participant_ids):
    next_params = {}

    try:
        if date_planning:
            next_date = (datetime.strptime(date_planning, '%Y-%m-%d').date() + timedelta(days=1)).isoformat()
            next_params['date'] = next_date
    except ValueError:
        pass

    if employe_id:
        next_params['employe'] = employe_id

    participants_next = [
        emp_id for emp_id in (participant_ids or [])
        if emp_id and str(emp_id) != str(employe_id or '')
    ]
    if participants_next:
        next_params['participants'] = ','.join(participants_next)

    redirect_url = reverse('planning:form_create')
    if next_params:
        redirect_url = f"{redirect_url}?{urlencode(next_params)}"
    return redirect(redirect_url)


def _is_generic_planning_avance_designation(designation):
    """Designation saisissable depuis le formulaire planning generaliste."""
    if not designation:
        return False

    type_avance = _normalize_poste_name(getattr(designation, 'type_avance_caissiere', ''))
    nom_designation = _normalize_poste_name(getattr(designation, 'nom', ''))
    is_frais_deplacement = (
        'frais de deplacement' in nom_designation
        or 'deplacement' in nom_designation
        or 'deplacement' in _normalize_poste_name(getattr(designation, 'libelle', ''))
    )
    if type_avance != 'avance' and not is_frais_deplacement:
        return False

    if getattr(designation, 'concerne_livraison', False):
        return False

    # Les designations de pieces/materiaux/chantiers doivent passer
    # par le workflow reparations, pas par le formulaire planning generique.
    if getattr(designation, 'code_materiel', None):
        return False
    if getattr(designation, 'type_designation_chantier', None):
        return False

    return True


def _is_planning_deplacement_designation(designation):
    if not designation:
        return False

    nom_designation = _normalize_poste_name(getattr(designation, 'nom', ''))
    libelle_designation = _normalize_poste_name(getattr(designation, 'libelle', ''))
    return (
        'frais de deplacement' in nom_designation
        or 'deplacement' in nom_designation
        or 'deplacement' in libelle_designation
    )


def _build_planning_form_avance_designations(editable_designations, details):
    designations_by_id = {
        str(designation.id): designation
        for designation in editable_designations
        if getattr(designation, 'id', None)
    }

    for detail in details or []:
        designation = getattr(detail, 'designation', None)
        designation_id = getattr(detail, 'designation_id', None)
        if designation and designation_id:
            designations_by_id.setdefault(str(designation_id), designation)

    return sorted(
        designations_by_id.values(),
        key=lambda designation: _normalize_poste_name(getattr(designation, 'nom', ''))
    )


def _get_fallback_deplacement_designation():
    """Trouver une designation de secours pour les frais de deplacement."""
    from apps.planning.models import Designation

    designations = Designation.objects.all().order_by('nom')

    explicit_match = next(
        (designation for designation in designations if _is_planning_deplacement_designation(designation)),
        None,
    )
    if explicit_match:
        return explicit_match

    advance_match = next(
        (
            designation for designation in designations
            if _normalize_poste_name(getattr(designation, 'type_avance_caissiere', '')) == 'avance'
        ),
        None,
    )
    return advance_match


def _resolve_planning_operation_date(value):
    if not value:
        return None
    if isinstance(value, datetime):
        if timezone.is_aware(value):
            return timezone.localtime(value).date()
        return value.date()
    return value


def _is_planning_operation_advanced(planning_date, *, livraison=False, utilise=False, retour=False, today=None):
    """Determine si une operation doit etre consideree comme avancee."""
    if utilise or retour:
        return False
    if livraison:
        return True

    operation_date = _resolve_planning_operation_date(planning_date)
    if not operation_date:
        return False

    reference_day = today or timezone.localdate()
    return (reference_day - operation_date).days > 30


def _get_planning_scope(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return 'none'
    if getattr(user, 'is_superuser', False):
        return 'all'
    if not hasattr(user, 'employe') or not user.employe:
        return 'none'

    poste_nom = _normalize_poste_name(getattr(getattr(user.employe, 'poste', None), 'nom_poste', ''))

    if poste_nom == 'directeur':
        return 'all'

    organisation_postes = (
        'directeur adjoint',
        'responsable administratif',
        'responsable administratif et financier',
        'raf',
    )
    if any(p in poste_nom for p in organisation_postes):
        return 'organisation'

    return 'base'


def _point_eau_idxls_sort_key(point_eau):
    idxls = (getattr(point_eau, 'idxls', '') or '').strip()
    match = re.search(r'\d+', idxls)
    if match:
        return (
            0,
            int(match.group()),
            idxls.lower(),
            (getattr(point_eau, 'nomabonne', '') or '').lower(),
        )
    return (
        1,
        0,
        idxls.lower(),
        (getattr(point_eau, 'nomabonne', '') or '').lower(),
    )


def _sort_points_eau_by_idxls(points_eau):
    return sorted(points_eau, key=_point_eau_idxls_sort_key)


def _coerce_request_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {'true', '1', 'yes', 'on'}:
            return True
        if normalized in {'false', '0', 'no', 'off', ''}:
            return False
    return bool(value)


def _resolve_requested_validation_value(data, *, current_validation=False):
    try:
        validation_provided = 'validation' in data
    except TypeError:
        validation_provided = False

    if not validation_provided:
        return current_validation, False

    return _coerce_request_bool(data.get('validation'), default=False), True


def _serialize_point_eau_for_template(point_eau):
    label = getattr(point_eau, 'forfaitaire_display_label', '') or ''
    nomabonne = getattr(point_eau, 'nomabonne', '') or ''
    code_point_eau = getattr(point_eau, 'code_point_eau', '') or ''
    tarif = getattr(point_eau, 'tarifforfaitaire', 0) or 0
    fallback_label = label or nomabonne or code_point_eau or str(point_eau.id)
    return {
        'id': str(point_eau.id),
        'nom': fallback_label,
        'nomabonne': nomabonne,
        'forfaitaire_display_label': fallback_label,
        'code_point_eau': code_point_eau,
        'tarif': tarif,
        'tarifforfaitaire': tarif,
        'idxls': getattr(point_eau, 'idxls', '') or '',
    }


def _serialize_compte_for_template(compte):
    nom_compte = getattr(compte, 'nom_compte', '') or ''
    return {
        'id': str(compte.id),
        'nom': nom_compte,
        'nom_compte': nom_compte,
    }


def _serialize_village_for_template(village):
    nom_village = getattr(village, 'nom_village', '') or ''
    return {
        'id': str(village.id),
        'nom': nom_village,
        'nom_village': nom_village,
    }


def _serialize_magasin_for_template(magasin):
    nom_magasin = getattr(magasin, 'nom_magasin', '') or ''
    return {
        'id': str(magasin.id),
        'nom': nom_magasin,
        'nom_magasin': nom_magasin,
    }


def is_jour_ferie_malgache(date):
    """Vérifie si une date est un jour férié Ã  Madagascar"""
    return est_jour_ferie_officiel(date)


@api_view(['GET'])
@permission_classes([AllowAny])
def planning_data_api_simple(request):
    """API simplifiée pour récupérer les données de planning avec les tables existantes"""

    try:
        cursor = connection.cursor()
        
        # Construire la requÃªte optimisée avec une seule sous-requÃªte pour les détails
        # Utiliser BOOL_OR pour agréger les booléens en une seule passe
        query = """
        SELECT DISTINCT ON (p.id)
            p.id,
            p.date,
            p.employe_uuid_id,
            p.type_activite_uuid_id,
            p.fiche_poste_id,
            p.ouvrage_uuid_id,
            p.remarque,
            p.estvalide,
            p.statut,
            COALESCE(e.nom, e.prenom, 'Employé inconnu') as employe_nom,
            COALESCE(e.surnom, e.prenom || ' ' || e.nom, 'Employé inconnu') as employe_surnom,
            COALESCE(fp.tache, ta.nomtype, 'Activit? inconnue') as activite_nom,
            COALESCE(o.nom_ouvrage, 'Aucun ouvrage') as ouvrage_nom,
            COALESCE(ta.nomtype, 'Type inconnu') as type_activite_nom,
            COALESCE(c.nom_commune, '') as commune_nom,
            e.poste_id as employe_poste_id,
            fp.preuve_type as preuve_type,
            COALESCE(fp.preuve_obligatoire, FALSE) as preuve_obligatoire,
            COALESCE(dc.nb_details, 0) as nb_details,
            COALESCE(dc.nb_deplacements, 0) as nb_deplacements,
            COALESCE(dc.nb_livraisons, 0) as nb_livraisons,
            COALESCE(dc.nb_paiements, 0) as nb_paiements,
            COALESCE(dc.has_livraison, FALSE) as has_livraison,
            COALESCE(dc.has_avance, FALSE) as has_avance,
            COALESCE(dc.has_paiement, FALSE) as has_paiement,
            COALESCE(pp.participants, '') as participants
        FROM plannings p
        LEFT JOIN employes e ON p.employe_uuid_id = e.id
        LEFT JOIN planning_employees pe_emp ON p.id = pe_emp.planning_id
        LEFT JOIN typesactivites ta ON p.type_activite_uuid_id = ta.id
        LEFT JOIN fiches_poste fp ON p.fiche_poste_id = fp.id
        LEFT JOIN ouvrages o ON p.ouvrage_uuid_id = o.id
        LEFT JOIN pointseaus pe ON pe.ouvrageid = o.id
        LEFT JOIN parcelles pa ON pe.parcelleid = pa.id
        LEFT JOIN villages v ON pa.village_id = v.id
        LEFT JOIN fokontanys f ON v.fokontany_id = f.id
        LEFT JOIN communes c ON f.commune_id = c.id
        LEFT JOIN (
            SELECT
                planning_id,
                SUM(nb_avances) as nb_details,
                SUM(nb_deplacements) as nb_deplacements,
                SUM(nb_livraisons) as nb_livraisons,
                SUM(nb_paiements) as nb_paiements,
                BOOL_OR(has_avance) as has_avance,
                BOOL_OR(has_livraison) as has_livraison,
                BOOL_OR(has_paiement) as has_paiement
            FROM (
                -- Compter les avances depuis planningdetails
                SELECT
                    pd.planning_id,
                    COUNT(*) FILTER (
                        WHERE COALESCE(pd.livraison, FALSE) = FALSE
                        AND pdd.planning_detail_id IS NULL
                        AND (d.type_avance_caissiere IS NULL OR d.type_avance_caissiere != 'Bon de livraison')
                    ) as nb_avances,
                    COUNT(*) FILTER (
                        WHERE COALESCE(pd.livraison, FALSE) = FALSE
                        AND pdd.planning_detail_id IS NOT NULL
                    ) as nb_deplacements,
                    0 as nb_livraisons,
                    0 as nb_paiements,
                    BOOL_OR(
                        COALESCE(pd.livraison, FALSE) = FALSE
                        AND pdd.planning_detail_id IS NULL
                        AND (d.type_avance_caissiere IS NULL OR d.type_avance_caissiere != 'Bon de livraison')
                    ) as has_avance,
                    FALSE as has_livraison,
                    BOOL_OR(d.nom ILIKE '%%paiement forfaitaire%%' AND pd.utilise = FALSE AND pd.retour = FALSE) as has_paiement
                FROM planningdetails pd
                LEFT JOIN designations d ON pd.designationid = d.id
                LEFT JOIN planningdetail_deplacements pdd ON pdd.planning_detail_id = pd.id
                WHERE pd.utilise = FALSE AND pd.retour = FALSE
                GROUP BY pd.planning_id

                UNION ALL

                -- Compter les bons de livraison depuis bons_livraison
                SELECT
                    bl.planning_id,
                    0 as nb_avances,
                    0 as nb_deplacements,
                    COUNT(*) as nb_livraisons,
                    0 as nb_paiements,
                    FALSE as has_avance,
                    TRUE as has_livraison,
                    FALSE as has_paiement
                FROM bons_livraison bl
                WHERE bl.utilise = FALSE AND bl.retour = FALSE
                GROUP BY bl.planning_id

                UNION ALL

                -- Compter les paiements forfaitaires lies au planning
                SELECT
                    pf.planning_id,
                    0 as nb_avances,
                    0 as nb_deplacements,
                    0 as nb_livraisons,
                    COUNT(*) as nb_paiements,
                    FALSE as has_avance,
                    FALSE as has_livraison,
                    TRUE as has_paiement
                FROM paiements_forfaitaires pf
                WHERE pf.planning_id IS NOT NULL
                GROUP BY pf.planning_id
            ) combined
            GROUP BY planning_id
        ) dc ON p.id = dc.planning_id
        LEFT JOIN (
            SELECT
                pe.planning_id,
                STRING_AGG(
                    DISTINCT COALESCE(e2.surnom, e2.prenom || ' ' || e2.nom),
                    ', '
                ) as participants
            FROM (
                SELECT planning_id, employee_id FROM planning_employees
                UNION
                SELECT id as planning_id, employe_uuid_id as employee_id
                FROM plannings
                WHERE employe_uuid_id IS NOT NULL
            ) pe
            LEFT JOIN employes e2 ON pe.employee_id = e2.id
            GROUP BY pe.planning_id
        ) pp ON p.id = pp.planning_id
        WHERE 1=1
        """
        
        params = []

        # Cloisonnement selon poste utilisateur
        scope = _get_planning_scope(request.user)
        if scope == 'none':
            return Response([])
        if scope == 'base':
            base_id = getattr(getattr(request.user, 'employe', None), 'base_id', None)
            if not base_id:
                return Response([])
            query += " AND e.base_id = %s"
            params.append(base_id)
        elif scope == 'organisation':
            organisation_id = getattr(getattr(getattr(request.user, 'employe', None), 'base', None), 'organisation_id', None)
            if not organisation_id:
                return Response([])
            query += " AND e.base_id IN (SELECT id FROM bases WHERE organisation_id = %s)"
            params.append(organisation_id)
        
        # Filtre par mois : pré-filtrer en SQL par année, puis affiner en Python
        filter_mois = request.GET.get('mois')
        filter_year = None
        filter_month = None
        if filter_mois:
            year_month = filter_mois.split('-')
            if len(year_month) == 2:
                filter_year = int(year_month[0])
                filter_month = int(year_month[1])
                # Pré-filtrer en SQL par année pour réduire les données
                query += " AND EXTRACT(YEAR FROM p.date) = %s"
                params.append(filter_year)
        else:
            # Si pas de filtre, limiter aux 6 derniers mois par défaut
            from datetime import datetime, timedelta
            six_months_ago = datetime.now() - timedelta(days=180)
            query += " AND p.date >= %s"
            params.append(six_months_ago)

        # Filtrer par employé
        employe = request.GET.get('employe')
        if employe:
            query += " AND (p.employe_uuid_id = %s OR pe_emp.employee_id = %s)"
            params.append(employe)
            params.append(employe)

        # Filtrer par ouvrage
        ouvrage = request.GET.get('ouvrage')
        if ouvrage:
            query += " AND p.ouvrage_uuid_id = %s"
            params.append(ouvrage)

        # Filtrer par ouvrages ayant des équipements ou des points d'eau
        ouvrages_equipements = request.GET.get('ouvrages_equipements')
        if ouvrages_equipements == 'true':
            query += """ AND (
                EXISTS (
                    SELECT 1 FROM equipements_constitutifs ec
                    WHERE ec.ouvrage_id = p.ouvrage_uuid_id
                ) OR EXISTS (
                    SELECT 1 FROM pointseaus pe
                    WHERE pe.ouvrageid = p.ouvrage_uuid_id
                )
            )"""

        # Filtrer par validation
        validation = request.GET.get('validation')
        if validation in ['true', 'false']:
            query += " AND p.estvalide = %s"
            params.append(validation == 'true')

        query += " ORDER BY p.id, p.date DESC"

        cursor.execute(query, tuple(params))

        # Récupérer les résultats et les trier par date en Python
        rows = cursor.fetchall()
        # Trier les résultats par date (colonne index 1) de façon décroissante
        rows = sorted(rows, key=lambda x: x[1] if x[1] else '', reverse=True)

        plannings = []
        import pytz
        tz_madagascar = pytz.timezone('Indian/Antananarivo')

        # Construire la liste des mois avec evaluation terminee par employe
        eval_months = set()
        employe_months = set()
        employe_ids = set()

        for row in rows:
            emp_id = row[2]
            if not emp_id:
                continue
            employe_ids.add(str(emp_id))
        for row in rows:
            emp_id = row[2]
            if not emp_id:
                continue
            if row[1]:
                date_aware = row[1] if row[1].tzinfo else timezone.make_aware(row[1])
                date_madagascar = date_aware.astimezone(tz_madagascar)
                d = date_madagascar.date()
                employe_months.add((str(emp_id), d.year, d.month))

        if employe_ids and employe_months:
            evals = Evaluation.objects.filter(
                employe_id__in=employe_ids,
                statut='terminee'
            ).values('employe_id', 'date_modification')
            for ev in evals:
                if not ev['date_modification']:
                    continue
                d = ev['date_modification'].date()
                key = (str(ev['employe_id']), d.year, d.month)
                if key in employe_months:
                    eval_months.add(key)

        ouvrage_grading_map = {}
        ouvrage_ids = {row[5] for row in rows if row[5]}
        if ouvrage_ids:
            reparations_by_ouvrage = {}
            reparations_qs = (
                Planning.objects.filter(ouvrage_id__in=ouvrage_ids)
                .select_related('fiche_poste')
                .order_by('ouvrage_id')
            )
            for rep in reparations_qs:
                key = str(rep.ouvrage_id)
                reparations_by_ouvrage.setdefault(key, []).append(rep)

            for ouvrage_id in ouvrage_ids:
                ouvrage_key = str(ouvrage_id)
                try:
                    grading_code = (
                        get_repair_workflow_grading_from_plannings(
                            reparations_by_ouvrage.get(ouvrage_key, [])
                        ).get('code') or ''
                    ).strip()
                except Exception:
                    grading_code = ''
                ouvrage_grading_map[ouvrage_key] = grading_code

        for row in rows:
            # Convertir la date UTC en timezone Madagascar avant d'extraire la date
            if row[1]:
                date_aware = row[1] if row[1].tzinfo else timezone.make_aware(row[1])
                date_madagascar = date_aware.astimezone(tz_madagascar)
                date_obj = date_madagascar.date()
            else:
                date_obj = None

            # Filtrer par mois en Python (après conversion timezone)
            if filter_year and filter_month and date_obj:
                if date_obj.year != filter_year or date_obj.month != filter_month:
                    continue  # Ignorer cette ligne si elle ne correspond pas au filtre

            is_weekend = date_obj.weekday() >= 5 if date_obj else False  # 5=Samedi, 6=Dimanche
            is_ferie = is_jour_ferie_malgache(date_obj) if date_obj else False

            planning = {
                'id': row[0],
                'date_planning': date_obj.isoformat() if date_obj else None,
                'is_weekend': is_weekend,
                'is_ferie': is_ferie,
                'employeid': row[2],  # employe_uuid_id
                'activiteid': row[3],  # type_activite_uuid_id (compat)
                'ouvrageid': row[5],  # ouvrage_uuid_id
                'remarques': row[6] or '',
                'validation': row[7] or False,
                'statut': row[8] or 'en_cours',
                'employe_nom': row[9],
                'employe_surnom': row[10],  # Surnom de l'employe
                'activite_display': row[11],  # Fiche de poste (ou type si absent)
                'ouvrage_nom': row[12],
                'type_activite_nom': row[13],  # nomtype
                'activite_nom': row[11],  # Fiche de poste
                'commune_name': row[14] or '',  # Nom de la commune
                'nb_details': row[18] or 0,  # Nombre d'avances
                'nb_deplacements': row[19] or 0,  # Nombre de frais de déplacement
                'nb_livraisons': row[20] or 0,  # Nombre de bons de livraison
                'nb_paiements': row[21] or 0,  # Nombre de paiements forfaitaires
                'has_livraison': row[22] or False,  # Boolean: a des livraisons
                'has_avance': row[23] or False,  # Boolean: a des avances
                'has_paiement': row[24] or False,  # Boolean: a des paiements forfaitaires
                'participants': row[25] or '',
                'fiche_poste_display': row[11] or '',
                'preuve_type': row[16],
                'preuve_obligatoire': row[17] or False,
                'preuve_manquante': False,
                # Champs pour le formulaire modal (compatibilite)
                'employe': row[2],  # Meme valeur que employeid
                'type_activite': row[3],  # Meme valeur que activiteid
                'activite': row[4],  # fiche_poste_id (compat)
                'fiche_poste': row[4],
                'ouvrage': row[5],  # Meme valeur que ouvrageid
                'ouvrage_grading': ouvrage_grading_map.get(str(row[5]), '') if row[5] else '',
                'activite_text': '',  # Texte libre vide par defaut
                # Champs attendus par le calendrier JavaScript
                'assigned_employee_name': row[10],  # Utiliser le surnom
                'assigned_employee_id': row[2],  # ID de l'employe pour le filtre
                'infrastructure_name': row[12],
                'task_type_display': row[13],  # Type d'activite
                'task_description': f"{row[11]} - {row[12]}" + (f" - {row[6]}" if row[6] else ""),
                # Champs pour les filtres JavaScript
                'employe_id': str(row[2]) if row[2] else None,  # UUID en string pour le filtre
                'ouvrage_id': str(row[5]) if row[5] else None,  # UUID en string pour le filtre
                'can_adjust_validation': bool(
                    row[2] and can_user_adjust_planning_validation(request.user, row[2])
                ),
            }
            if planning.get('preuve_type') == 'evaluation' and planning.get('preuve_obligatoire'):
                if date_obj and planning.get('employeid'):
                    key = (str(planning.get('employeid')), date_obj.year, date_obj.month)
                    planning['preuve_manquante'] = key not in eval_months
            
            plannings.append(planning)

        # Compteur de doublons (reparation / rehabilitation / maconnerie uniquement)
        from apps.planning.doublons_reparations import calculer_doublons_securise, type_eligible
        doublons = calculer_doublons_securise([
            item['id'] for item in plannings if type_eligible(item.get('type_activite_nom'))
        ])
        for item in plannings:
            item['doublons'] = doublons.get(str(item['id']))

        return Response(plannings)
        
    except Exception as e:
        return Response({
            'error': f'Erreur lors de la récupération des plannings: {str(e)}',
            'plannings': []
        }, status=500)


@mobile_auth_required
@api_view(['GET'])
@permission_classes([AllowAny])
def planning_details_api_simple(request, planning_id):
    """API simplifiée pour récupérer les détails d'un planning
    Retourne 2 listes séparées : avances (PlanningDetail) et livraisons (BonLivraison)"""

    try:
        planning = Planning.objects.filter(id=planning_id).only('date').first()
        planning_date = _resolve_planning_operation_date(getattr(planning, 'date', None))
        planning_is_validated = bool(getattr(planning, 'estvalide', False)) if planning else False
        cursor = connection.cursor()

        # 1. Récupérer les AVANCES hors déplacement depuis PlanningDetail
        cursor.execute("""
        SELECT
            pd.id,
            COALESCE(d.nom, 'Désignation inconnue') as designation,
            pd.quantity,
            pd.pu,
            pd.montant,
            pd.acheteur,
            COALESCE(ec.nom, '') as equipement_nom,
            COALESCE(pe.idxls, '') as point_eau_idxlsx,
            COALESCE(d.type_avance_caissiere, '') as type_avance_caissiere,
            COALESCE(pd.livraison, FALSE) as livraison
        FROM planningdetails pd
        LEFT JOIN designations d ON pd.designationid = d.id
        LEFT JOIN equipements_constitutifs ec ON pd.equipement_constitutif_id = ec.id
        LEFT JOIN pointseaus pe ON pd.point_eau_id = pe.id
        LEFT JOIN planningdetail_deplacements pdd ON pdd.planning_detail_id = pd.id
        WHERE pd.planning_id = %s
          AND pd.utilise = FALSE
          AND COALESCE(pd.livraison, FALSE) = FALSE
          AND pd.retour = FALSE
          AND pdd.id IS NULL
          AND (d.type_avance_caissiere IS NULL OR d.type_avance_caissiere != 'Bon de livraison')
        """, [planning_id])

        avances = []
        for row in cursor.fetchall():
            is_advanced = planning_is_validated and _is_planning_operation_advanced(planning_date, livraison=bool(row[9]))
            avance = {
                'id': str(row[0]) if row[0] else '',
                'designation': row[1] if row[1] else '',
                'quantity': float(row[2]) if row[2] else 0,
                'pu': float(row[3]) if row[3] else 0,
                'montant': float(row[4]) if row[4] else 0,
                'acheteur': row[5] if row[5] else '',
                'equipement_nom': row[6] if row[6] else '',
                'point_eau_idxlsx': row[7] if row[7] else '',
                'trajet': False,
                'point_a_nom': '',
                'point_b_nom': '',
                'moyen_transport': '',
                'type_avance_caissiere': row[8] if row[8] else '',
                'statut_label': 'Avancee' if is_advanced else 'En cours',
                'statut_badge_class': 'badge-info' if is_advanced else 'badge-warning',
            }
            avances.append(avance)

        # 1bis. Récupérer les frais de déplacement
        cursor.execute("""
        SELECT
            pd.id,
            COALESCE(d.nom, 'Désignation inconnue') as designation,
            pd.quantity,
            pd.pu,
            pd.montant,
            pd.acheteur,
            COALESCE(pdd.trajet, '') as trajet,
            COALESCE(va.nom_village, '') as point_a_nom,
            COALESCE(vb.nom_village, '') as point_b_nom,
            COALESCE(pdd.moyen_transport, '') as moyen_transport
        FROM planningdetails pd
        INNER JOIN planningdetail_deplacements pdd ON pdd.planning_detail_id = pd.id
        LEFT JOIN designations d ON pd.designationid = d.id
        LEFT JOIN villages va ON pdd.point_a_id = va.id
        LEFT JOIN villages vb ON pdd.point_b_id = vb.id
        WHERE pd.planning_id = %s
          AND pd.utilise = FALSE
          AND COALESCE(pd.livraison, FALSE) = FALSE
          AND pd.retour = FALSE
        """, [planning_id])

        deplacements = []
        for row in cursor.fetchall():
            is_pending = not _is_planning_operation_advanced(planning_date)
            deplacements.append({
                'id': str(row[0]) if row[0] else '',
                'designation': row[1] if row[1] else '',
                'quantity': float(row[2]) if row[2] else 0,
                'pu': float(row[3]) if row[3] else 0,
                'montant': float(row[4]) if row[4] else 0,
                'acheteur': row[5] if row[5] else '',
                'trajet': row[6] if row[6] else '',
                'point_a_nom': row[7] if row[7] else '',
                'point_b_nom': row[8] if row[8] else '',
                'moyen_transport': row[9] if row[9] else '',
                'statut_label': 'A avancer' if is_pending else 'Avancee',
                'statut_badge_class': 'badge-primary' if is_pending else 'badge-info',
            })

        # 2. Récupérer les LIVRAISONS depuis BonLivraison
        cursor.execute("""
        SELECT
            bl.id,
            COALESCE(d.nom, 'Désignation inconnue') as designation,
            bl.quantite,
            COALESCE(bl.magasin, '') as magasin,
            COALESCE(ec.nom, '') as equipement_nom,
            COALESCE(pe.idxls, '') as point_eau_idxlsx
        FROM bons_livraison bl
        LEFT JOIN designations d ON bl.designation_id = d.id
        LEFT JOIN equipements_constitutifs ec ON bl.equipement_id = ec.id
        LEFT JOIN pointseaus pe ON bl.point_eau_id = pe.id
        WHERE bl.planning_id = %s
          AND bl.utilise = FALSE
          AND bl.retour = FALSE
        """, [planning_id])

        livraisons = []
        for row in cursor.fetchall():
            from apps.planning.views_livraisons import _get_magasin_display_label

            livraison = {
                'id': str(row[0]) if row[0] else '',
                'designation': row[1] if row[1] else '',
                'quantite': float(row[2]) if row[2] else 0,
                'magasin': _get_magasin_display_label(row[3]),
                'equipement_nom': row[4] if row[4] else '',
                'point_eau_idxlsx': row[5] if row[5] else ''
            }
            livraisons.append(livraison)

        # 3. Récupérer les PAIEMENTS FORFAITAIRES depuis PaiementForfaitaire
        cursor.execute("""
        SELECT
            pf.id,
            COALESCE(pe.code_point_eau, pe.idxls::text, pe.nomabonne, 'Point d''eau ' || pe.id::text) as point_eau_label,
            pf.quantite,
            pf.prix_unitaire,
            pf.montant,
            pf.paye,
            pf.date_facture,
            pf.date_paiement,
            COALESCE(pf."numeroDiameX", '') as numero_diamex
        FROM paiements_forfaitaires pf
        LEFT JOIN pointseaus pe ON pf.point_eau_id = pe.id
        WHERE pf.planning_id = %s
        ORDER BY pf.date_facture DESC, pf.created_at DESC
        """, [planning_id])

        paiements = []
        for row in cursor.fetchall():
            paiement = {
                'id': row[0],
                'point_eau_label': row[1] if row[1] else '',
                'quantite': int(row[2]) if row[2] is not None else 0,
                'prix_unitaire': float(row[3]) if row[3] else 0,
                'montant': float(row[4]) if row[4] else 0,
                'paye': bool(row[5]),
                'date_facture': row[6].isoformat() if row[6] else None,
                'date_paiement': row[7].isoformat() if row[7] else None,
                'numero_diamex': row[8] if row[8] else ''
            }
            paiements.append(paiement)

        return Response({
            'avances': avances,
            'deplacements': deplacements,
            'livraisons': livraisons,
            'paiements': paiements,
            'details': avances,
            'bons_livraison': livraisons
        })

    except Exception as e:
        return Response({
            'error': f'Erreur lors de la récupération des détails: {str(e)}',
            'details': [],
            'avances': [],
            'deplacements': [],
            'livraisons': [],
            'paiements': []
        }, status=500)


@api_view(['GET'])
@permission_classes([AllowAny])
@api_view(['GET'])
@permission_classes([AllowAny])

@api_view(['GET'])
@permission_classes([AllowAny])
def employees_api_simple(request):
    """API simplifiee pour recuperer la liste des employes actifs (meme base que l'utilisateur)."""
    try:
        planning = Planning.objects.filter(id=planning_id).select_related('employe').first()
        if not planning:
            return Response({'error': 'Planning non trouve'}, status=404)

        if not can_user_adjust_planning_validation(request.user, planning):
            return Response({
                'error': "Acces refuse. Vous pouvez seulement valider les plannings de vos subordonnes directs ou indirects. Le directeur peut aussi valider son propre planning."
            }, status=403)

        cursor = connection.cursor()
        planning = Planning.objects.filter(id=planning_id).only('date').first()
        planning_date = _resolve_planning_operation_date(getattr(planning, 'date', None))
        params = []
        scope = _get_planning_scope(request.user)
        if scope == 'none':
            return JsonResponse([], safe=False)

        where_scope = ""
        if scope == 'base':
            base_id = getattr(getattr(request.user, 'employe', None), 'base_id', None)
            if not base_id:
                return JsonResponse([], safe=False)
            where_scope = " AND base_id = %s"
            params.append(base_id)
        elif scope == 'organisation':
            organisation_id = getattr(getattr(getattr(request.user, 'employe', None), 'base', None), 'organisation_id', None)
            if not organisation_id:
                return JsonResponse([], safe=False)
            where_scope = " AND base_id IN (SELECT id FROM bases WHERE organisation_id = %s)"
            params.append(organisation_id)

        cursor.execute(
            """
        SELECT
            id,
            nom,
            prenom,
            surnom,
            COALESCE(NULLIF(surnom, ''), prenom || ' ' || nom, 'Employe ' || CAST(id AS TEXT)) as display_name
        FROM employes
        WHERE date_debauchage IS NULL
        """ + where_scope + """
        ORDER BY surnom, nom, prenom
        """,
            params,
        )

        employees = []
        for row in cursor.fetchall():
            employees.append({
                'id': row[0],
                'nom': row[1] or '',
                'prenom': row[2] or '',
                'surnom': row[3] or '',
                'display_name': row[4] or ''
            })

        return JsonResponse(employees, safe=False)
    except Exception:
        return JsonResponse([], safe=False)



@api_view(['GET'])
@permission_classes([AllowAny])
def ouvrages_api_simple(request):
    """API simplifiee pour recuperer la liste des ouvrages."""
    try:
        cursor = connection.cursor()
        cursor.execute("""
        SELECT id, nom_ouvrage
        FROM ouvrages
        ORDER BY nom_ouvrage
        """)

        ouvrages = []
        for row in cursor.fetchall():
            ouvrages.append({
                'id': row[0],
                'infra_name': row[1],
                'infra_status': 'operationnel'
            })

        return JsonResponse(ouvrages, safe=False)
    except Exception:
        return JsonResponse([], safe=False)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def ouvrages_inspectables_api(request):
    """API pour récupérer uniquement les ouvrages qui ont des équipements ou des points d'eau.

    @api_view ajouté : sans lui, la Response DRF n'avait pas de renderer (erreur 500).
    """

    try:
        cursor = connection.cursor()
        # Note: equipements_constitutifs utilise ouvrage_id (avec underscore)
        #       pointseaus utilise ouvrageid (sans underscore)
        cursor.execute("""
        SELECT DISTINCT o.id, o.nom_ouvrage
        FROM ouvrages o
        WHERE EXISTS (
            SELECT 1 FROM equipements_constitutifs ec WHERE ec.ouvrage_id = o.id
        )
        OR EXISTS (
            SELECT 1 FROM pointseaus pe WHERE pe.ouvrageid = o.id
        )
        ORDER BY o.nom_ouvrage
        """)

        ouvrages = []
        for row in cursor.fetchall():
            ouvrage = {
                'id': str(row[0]),  # Convertir UUID en string pour cohérence
                'infra_name': row[1],
                'infra_status': 'operationnel'
            }
            ouvrages.append(ouvrage)

        print(f"[OK] Ouvrages inspectables trouves: {len(ouvrages)}")
        return Response(ouvrages)

    except Exception as e:
        # Si erreur, retourner une liste vide
        print(f"[ERREUR] API ouvrages inspectables: {e}")
        import traceback
        traceback.print_exc()
        return Response([])


@api_view(['GET'])
@permission_classes([AllowAny])
def types_activites_api_simple(request):
    """API simplifiée pour récupérer les types d'activités"""

    try:
        cursor = connection.cursor()
        cursor.execute("""
        SELECT id, nomtype
        FROM typesactivites
        ORDER BY nomtype
        """)

        types = []
        for row in cursor.fetchall():
            type_activite = {
                'id': str(row[0]),  # Convertir UUID en string
                'nom': row[1]
            }
            types.append(type_activite)

        return Response(types)

    except Exception as e:
        print(f"Erreur API types activités: {e}")
        # Si la table n'existe pas, retourner des types par défaut
        return Response([
            {'id': '1', 'nom': 'Maintenance'},
            {'id': '2', 'nom': 'Installation'},
            {'id': '3', 'nom': 'Réparation'},
            {'id': '4', 'nom': 'Inspection'},
            {'id': '5', 'nom': 'Formation'}
        ])


@api_view(['GET'])
@permission_classes([AllowAny])
def activites_postes_api_simple(request):
    """API simplifiée pour récupérer les activités de poste"""
    
    try:
        cursor = connection.cursor()
        cursor.execute("""
        SELECT id, nom
        FROM activites
        ORDER BY nom
        """)
        
        activites = []
        for row in cursor.fetchall():
            activite = {
                'id': row[0],
                'nom': row[1]
            }
            activites.append(activite)
        
        return Response(activites)
        
    except Exception as e:
        # Si la table n'existe pas, retourner des activités par défaut
        return Response([
            {'id': 1, 'nom': 'Vérification pompe'},
            {'id': 2, 'nom': 'Nettoyage réservoir'},
            {'id': 3, 'nom': 'Controle pression'},
            {'id': 4, 'nom': 'Réparation fuite'},
            {'id': 5, 'nom': 'Installation compteur'}
        ])


@api_view(['GET'])
@permission_classes([AllowAny])
def available_months_api_simple(request):
    """API simplifiée pour récupérer les mois disponibles"""
    
    try:
        cursor = connection.cursor()
        cursor.execute("""
        SELECT DISTINCT EXTRACT(YEAR FROM date) as year, EXTRACT(MONTH FROM date) as month
        FROM plannings
        ORDER BY year DESC, month DESC
        """)
        
        months = []
        for row in cursor.fetchall():
            year = int(row[0])
            month = int(row[1])
            date_obj = datetime(year, month, 1)
            months.append({
                'value': f'{year:04d}-{month:02d}',
                'label': date_obj.strftime('%B %Y').capitalize()
            })
        
        return Response(months)
        
    except Exception as e:
        # Si erreur, retourner quelques mois par défaut
        return Response([
            {'value': '2025-09', 'label': 'Septembre 2025'},
            {'value': '2025-08', 'label': 'AoÃ»t 2025'},
            {'value': '2025-07', 'label': 'Juillet 2025'}
        ])


@api_view(['POST'])
@permission_classes([AllowAny])
def planning_validate_api_simple(request, planning_id):
    """API simplifiee pour valider un planning."""

    try:
        planning = Planning.objects.filter(id=planning_id).select_related('employe').first()
        if not planning:
            return Response({'error': 'Planning non trouve'}, status=404)

        if not can_user_adjust_planning_validation(request.user, planning):
            return Response({
                'error': "Acces refuse. Vous pouvez seulement valider les plannings de vos subordonnes directs ou indirects. Le directeur peut aussi valider son propre planning."
            }, status=403)

        cursor = connection.cursor()
        cursor.execute("""
        UPDATE plannings 
        SET estvalide = true,
            updated_at = NOW()
        WHERE id = %s
        """, [planning_id])

        connection.commit()
        return Response({'message': 'Planning valide avec succes'})

    except Exception as e:
        return Response({'error': f'Erreur lors de la validation: {str(e)}'}, status=500)


@mobile_auth_required
@api_view(['POST'])
@permission_classes([AllowAny])
def planning_create_api_simple(request):
    """API simplifiée pour créer un planning"""

    try:
        data = request.data
        requested_validation, _ = _resolve_requested_validation_value(data, current_validation=False)
        employe_id = data.get('employe') or None
        type_activite_id = data.get('type_activite') or None
        fiche_poste_id = data.get('fiche_poste') or data.get('activite') or None
        ouvrage_id = data.get('ouvrage') or None
        participant_values = (
            data.get('participants')
            or data.get('participants_ids')
            or data.get('participants[]')
            or []
        )
        if isinstance(participant_values, str):
            participant_ids = [value.strip() for value in participant_values.split(',') if value.strip()]
        else:
            participant_ids = [
                str(value).strip()
                for value in participant_values
                if str(value or '').strip()
            ]

        if requested_validation and not can_user_adjust_planning_validation(request.user, employe_id):
            return Response({
                'error': "Acces refuse. Vous pouvez seulement valider les plannings de vos subordonnes directs ou indirects. Le directeur peut aussi valider son propre planning."
            }, status=403)

        # Convertir date_planning en datetime
        date_planning = data.get('date_planning')
        duplicate_check_date = date_planning
        if date_planning:
            # Ajouter l'heure si seulement la date est fournie
            if 'T' not in date_planning:
                date_planning = f"{date_planning} 00:00:00"

        selected_employe = Employe.objects.only('id', 'base_id').filter(id=employe_id).first() if employe_id else None
        selected_fiche_poste = None
        if fiche_poste_id:
            from apps.employees.models_evaluation import FichePoste

            selected_fiche_poste = (
                FichePoste.objects.select_related('type_activites')
                .filter(id=fiche_poste_id)
                .first()
            )
            if selected_fiche_poste and not type_activite_id:
                type_activite_id = str(selected_fiche_poste.type_activites_id or '') or None

        selected_type_activite = None
        if type_activite_id:
            selected_type_activite = TypeActivite.objects.filter(id=type_activite_id).first()

        duplicate_planning = _find_duplicate_planning_for_submission(
            duplicate_check_date,
            ouvrage_id,
            fiche_poste=selected_fiche_poste,
            type_activite=selected_type_activite,
            employe=selected_employe,
        )
        if duplicate_planning:
            added_participant_ids = _merge_duplicate_planning_participants(
                duplicate_planning,
                employe_id,
                participant_ids,
            )
            return Response({
                'message': "Planning existant conserve; les employes ont ete rattaches comme participants.",
                'id': duplicate_planning.id,
                'merged': True,
                'participants_added': added_participant_ids,
            })

        # Utiliser le ORM Django au lieu de SQL brut pour gérer la séquence automatiquement
        planning = Planning(
            date=date_planning,
            employe_id=employe_id,
            type_activite_id=type_activite_id,
            fiche_poste_id=fiche_poste_id,
            ouvrage_id=ouvrage_id,
            remarque=data.get('remarques', ''),
            estvalide=requested_validation,
            statut=data.get('statut', 'en_cours')
        )
        planning.save()

        for participant_id in _build_new_secondary_participant_ids(planning, None, participant_ids):
            PlanningEmploye.objects.get_or_create(
                planning_id=planning.id,
                employee_id=participant_id,
            )

        return Response({'message': 'Planning créé avec succès', 'id': planning.id})

    except Exception as e:
        return Response({'error': f'Erreur lors de la création: {str(e)}'}, status=500)


@csrf_exempt
@api_view(['PUT'])
@permission_classes([AllowAny])
def planning_update_api_simple(request, id):
    """API simplifiée pour modifier un planning"""

    import logging
    logger = logging.getLogger(__name__)

    try:
        data = request.data
        logger.info(f"ðŸ”µ API UPDATE - Planning ID: {id}")
        logger.info(f"ðŸ”µ Données reçues: {data}")
        logger.info(f"ðŸ”µ Ouvrage dans les données: '{data.get('ouvrage')}'")

        planning = Planning.objects.filter(id=id).select_related('employe').first()
        if not planning:
            return Response({'error': 'Planning non trouve'}, status=404)

        current_validation = bool(planning.estvalide)
        requested_validation, validation_provided = _resolve_requested_validation_value(
            data,
            current_validation=current_validation,
        )
        target_employe_id = data.get('employe') or planning.employe_id or None
        employe_changed = str(target_employe_id or '') != str(planning.employe_id or '')
        type_activite_value = data.get('type_activite') if 'type_activite' in data else planning.type_activite_id
        fiche_poste_value = data.get('activite') if 'activite' in data else planning.fiche_poste_id
        ouvrage_value = data.get('ouvrage') if 'ouvrage' in data else planning.ouvrage_id
        remarque_value = data.get('remarques') if 'remarques' in data else (planning.remarque or '')
        statut_value = data.get('statut') if 'statut' in data else (planning.statut or 'en_cours')

        if requested_validation and (requested_validation != current_validation or employe_changed):
            if not can_user_adjust_planning_validation(request.user, target_employe_id):
                return Response({
                    'error': "Acces refuse. Vous pouvez seulement valider les plannings de vos subordonnes directs ou indirects. Le directeur peut aussi valider son propre planning."
                }, status=403)

        if validation_provided and not requested_validation and current_validation:
            if not can_user_adjust_planning_validation(request.user, planning):
                return Response({
                    'error': "Acces refuse. Vous pouvez seulement devalider les plannings de vos subordonnes directs ou indirects. Le directeur peut aussi devalider son propre planning."
                }, status=403)

        cursor = connection.cursor()

        # Lire l'ancien ouvrage avant modification
        cursor.execute("SELECT ouvrage_uuid_id FROM plannings WHERE id = %s", [id])
        old_ouvrage = cursor.fetchone()
        logger.info(f"ðŸ”µ Ancien ouvrage_uuid_id: {old_ouvrage[0] if old_ouvrage else 'None'}")

        # Convertir date_planning en datetime
        date_planning = data.get('date_planning') or data.get('date')
        if date_planning:
            # Ajouter l'heure si seulement la date est fournie
            if 'T' not in date_planning:
                date_planning = f"{date_planning} 00:00:00"
        else:
            existing_date = getattr(planning, 'date', None)
            date_planning = existing_date.isoformat(sep=' ') if existing_date else None

        cursor.execute("""
        UPDATE plannings
        SET date = %s, employe_uuid_id = %s, type_activite_uuid_id = %s, fiche_poste_id = %s, ouvrage_uuid_id = %s,
            remarque = %s, estvalide = %s, statut = %s, updated_at = NOW()
        WHERE id = %s
        """, [
            date_planning,
            target_employe_id,
            type_activite_value or None,
            fiche_poste_value or None,
            ouvrage_value or None,
            remarque_value,
            requested_validation,
            statut_value,
            id
        ])

        # Vérifier le nouvel ouvrage après modification
        cursor.execute("SELECT ouvrage_uuid_id FROM plannings WHERE id = %s", [id])
        new_ouvrage = cursor.fetchone()
        logger.info(f"ðŸ”µ Nouvel ouvrage_uuid_id: {new_ouvrage[0] if new_ouvrage else 'None'}")

        connection.commit()
        logger.info(f"âœ… Planning {id} modifié avec succès")

        return Response({'message': 'Planning modifié avec succès'})

    except Exception as e:
        logger.error(f"âŒ ERREUR API UPDATE: {str(e)}", exc_info=True)
        return Response({'error': f'Erreur lors de la modification: {str(e)}'}, status=500)


@api_view(['DELETE'])
@permission_classes([AllowAny])
def planning_delete_api_simple(request, id):
    """API simplifiee pour supprimer un planning"""

    try:
        planning = Planning.objects.filter(id=id).first()
        if not planning:
            return Response({'error': 'Planning non trouve'}, status=404)

        # Interdire la suppression des plannings valides
        if planning.estvalide:
            return Response({
                'error': "Ce planning est valide et ne peut pas etre supprime. Vous pouvez seulement modifier la date ou l'employe."
            }, status=403)

        # Supprimer d'abord les details associes
        PlanningDetail.objects.filter(planning_id=id).delete()

        # Supprimer ensuite le planning
        planning.delete()

        return Response({'message': 'Planning supprime avec succes'})

    except Exception as e:
        return Response({'error': f'Erreur lors de la suppression: {str(e)}'}, status=500)
@api_view(['POST'])
@permission_classes([AllowAny])
def planning_unvalidate_api(request, id):
    """API pour devalider un planning."""

    import logging
    logger = logging.getLogger(__name__)

    try:
        planning = Planning.objects.filter(id=id).select_related('employe').first()
        if not planning:
            return Response({'error': 'Planning non trouve'}, status=404)

        if not can_user_adjust_planning_validation(request.user, planning):
            return Response({
                'error': "Acces refuse. Vous pouvez seulement devalider les plannings de vos subordonnes directs ou indirects. Le directeur peut aussi devalider son propre planning."
            }, status=403)

        cursor = connection.cursor()
        cursor.execute("SELECT estvalide FROM plannings WHERE id = %s", [id])
        result = cursor.fetchone()

        est_valide = result[0]
        if not est_valide:
            return Response({'error': "Ce planning n'est pas valide"}, status=400)

        logger.info("Devalidation du planning %s", id)
        cursor.execute("""
            UPDATE plannings
            SET estvalide = FALSE, updated_at = NOW()
            WHERE id = %s
        """, [id])

        connection.commit()
        logger.info("Planning %s devalide avec succes", id)
        return Response({'message': 'Planning devalide avec succes'})

    except Exception as e:
        logger.error("Erreur lors de la devalidation: %s", str(e), exc_info=True)
        return Response({'error': f'Erreur lors de la devalidation: {str(e)}'}, status=500)


@api_view(['POST'])
@permission_classes([AllowAny])
def planning_update_date_api(request, planning_id):
    """API pour mettre a jour la date d'un planning (drag & drop calendrier)"""
    try:
        payload = request.data if hasattr(request, 'data') else json.loads(request.body or '{}')
        new_date = payload.get('new_date') or payload.get('date')

        if not new_date:
            return Response({'error': 'new_date est requis'}, status=400)

        # Valider le format ISO (YYYY-MM-DD) ou datetime ISO
        try:
            if 'T' in new_date:
                new_date = datetime.fromisoformat(new_date).date().isoformat()
        except ValueError:
            return Response({'error': 'Format de date invalide'}, status=400)

        cursor = connection.cursor()
        cursor.execute('SELECT id FROM plannings WHERE id = %s', [planning_id])
        if not cursor.fetchone():
            return Response({'error': 'Planning non trouve'}, status=404)

        cursor.execute(
            'UPDATE plannings SET date = %s, updatedat = NOW() WHERE id = %s',
            [new_date, planning_id],
        )
        connection.commit()

        return Response({'message': 'Date mise a jour', 'planning_id': planning_id, 'new_date': new_date})
    except Exception as e:
        return Response({'error': f'Erreur lors de la mise a jour: {str(e)}'}, status=500)


@login_required
def planning_form_page(request, planning_id=None):
    from django.utils import timezone
    from decimal import Decimal
    from apps.planning.models import Planning, PlanningDetail, PlanningDetailDeplacement, PlanningEmploye, TypeActivite, Designation, BonLivraison
    from apps.employees.models import Employe
    from apps.employees.models_evaluation import FichePoste
    from apps.organization.models import Ouvrage, Compte, Magasin
    from apps.infrastructure.models import EquipementConstitutif
    from apps.billing.models import PointEau, PaiementForfaitaire
    from apps.geography.models import Village

    planning = None
    details = []
    deplacement_details = []
    managed_elsewhere_details = []
    livraisons = []
    paiements_forfaitaires = []
    planning_pieces = []
    participants_ids = []
    initial_date = ''
    initial_employe_id = ''
    auto_advanced_count = 0
    auto_advanced_detail_ids = set()

    if planning_id:
        planning = get_object_or_404(Planning, id=planning_id)
        all_details = list(PlanningDetail.objects.filter(planning_id=planning_id).select_related(
            'designation', 'equipement_constitutif', 'point_eau', 'compte', 'deplacement__point_a', 'deplacement__point_b'
        ))
        planning_operation_date = _resolve_planning_operation_date(getattr(planning, 'date', None))
        auto_advanced_detail_ids = {
            detail.id
            for detail in all_details
            if _is_planning_operation_advanced(
                planning_operation_date,
                livraison=bool(getattr(detail, 'livraison', False)),
                utilise=bool(getattr(detail, 'utilise', False)),
                retour=bool(getattr(detail, 'retour', False)),
            )
        }
        auto_advanced_count = sum(
            1
            for detail in all_details
            if detail.id in auto_advanced_detail_ids
            and not getattr(detail, 'livraison', False)
            and not getattr(detail, 'utilise', False)
            and not getattr(detail, 'retour', False)
        )
        details = []
        deplacement_details = []
        managed_elsewhere_details = []
        for detail in all_details:
            designation = getattr(detail, 'designation', None)
            if designation and (
                _is_planning_deplacement_designation(designation)
                or getattr(detail, 'trajet', None)
                or getattr(detail, 'point_a_id', None)
                or getattr(detail, 'point_b_id', None)
            ):
                deplacement_details.append(detail)
            elif _is_generic_planning_avance_designation(designation):
                details.append(detail)
            else:
                managed_elsewhere_details.append(detail)
        livraisons = list(
            BonLivraison.objects.filter(planning_id=planning_id)
            .select_related('designation', 'equipement', 'point_eau')
            .order_by('-created_at')
        )
        paiements_forfaitaires = list(
            PaiementForfaitaire.objects.filter(planning_id=planning_id)
            .select_related('point_eau', 'point_eau__ouvrage')
            .order_by('-date_facture', '-created_at')
        )
        planning_pieces = list(
            PlanningPiece.objects.filter(planning_id=planning_id)
            .select_related('fichier')
            .order_by('-created_at')
        )
        participants_ids = [
            str(employee_id)
            for employee_id in PlanningEmploye.objects.filter(planning_id=planning_id).values_list('employee_id', flat=True)
        ]
    else:
        initial_date_raw = request.GET.get('date') or request.GET.get('initial_date')
        if initial_date_raw:
            try:
                initial_date = datetime.strptime(initial_date_raw, '%Y-%m-%d').date().isoformat()
            except ValueError:
                initial_date = ''

        initial_employe_id = (request.GET.get('employe') or request.GET.get('initial_employe') or '').strip()
        participants_param = (request.GET.get('participants') or request.GET.get('initial_participants') or '').strip()
        if participants_param:
            participants_ids = [pid.strip() for pid in participants_param.split(',') if pid.strip()]

    allowed_type_names = list(PLANNING_FORM_ALLOWED_TYPE_NAMES)
    planning_current_type_name = ''
    if planning and planning.type_activite and planning.type_activite.nomtype:
        planning_current_type_name = planning.type_activite.nomtype
    elif (
        planning and planning.fiche_poste and planning.fiche_poste.type_activites
        and planning.fiche_poste.type_activites.nomtype
    ):
        planning_current_type_name = planning.fiche_poste.type_activites.nomtype

    if planning_current_type_name and planning_current_type_name not in allowed_type_names:
        allowed_type_names.append(planning_current_type_name)

    allowed_types_qs = TypeActivite.objects.filter(nomtype__in=allowed_type_names).order_by('nomtype')
    allowed_type_ids = {str(type_id) for type_id in allowed_types_qs.values_list('id', flat=True)}

    fiches_poste = FichePoste.objects.filter(
        type_activites_id__in=allowed_type_ids
    ).select_related('type_activites').order_by('tache')
    allowed_fiche_ids = {str(fiche_id) for fiche_id in fiches_poste.values_list('id', flat=True)}

    if planning and planning.fiche_poste_id and str(planning.fiche_poste_id) not in allowed_fiche_ids:
        fiches_poste = (
            FichePoste.objects
            .filter(id__in=list(allowed_fiche_ids) + [str(planning.fiche_poste_id)])
            .select_related('type_activites')
            .order_by('tache')
        )
        allowed_fiche_ids = {str(fiche_id) for fiche_id in fiches_poste.values_list('id', flat=True)}

    employees_qs = _get_scoped_employees_queryset(request.user)
    employee_ids_to_include = set(participants_ids)
    if planning and planning.employe_id:
        employee_ids_to_include.add(str(planning.employe_id))
    if initial_employe_id:
        employee_ids_to_include.add(str(initial_employe_id))
    if employee_ids_to_include:
        employees_qs = (
            Employe.objects.filter(
                Q(id__in=employees_qs.values_list('id', flat=True)) | Q(id__in=employee_ids_to_include)
            )
            .filter(date_debauchage__isnull=True)
            .distinct()
        )
    employees = employees_qs.order_by('surnom', 'nom', 'prenom')

    generic_access_fiche_ids, poste_access_fiche_ids = _build_fiche_access_maps(
        fiches_poste,
        employees,
    )
    deplacement_default_designation = _get_fallback_deplacement_designation()

    if request.method == 'POST':
        from itertools import zip_longest
        # Champs de base
        date_planning = request.POST.get('date_planning')
        employe_id = request.POST.get('employe')
        type_activite_id = request.POST.get('type_activite')
        fiche_poste_id = request.POST.get('fiche_poste') or request.POST.get('activite')
        ouvrage_id = request.POST.get('ouvrage')
        remarque = request.POST.get('remarque')
        statut = request.POST.get('statut') or 'en_cours'
        photos_json = request.POST.get('photos_json')
        submit_action = (request.POST.get('submit_action') or 'save').strip()
        participant_ids = request.POST.getlist('participants[]')
        avance_designation_ids = request.POST.getlist('avance_designation_id[]')
        avance_quantities = request.POST.getlist('avance_quantity[]')
        avance_pus = request.POST.getlist('avance_pu[]')
        avance_montants = request.POST.getlist('avance_montant[]')
        avance_acheteurs = request.POST.getlist('avance_acheteur[]')
        avance_compte_ids = request.POST.getlist('avance_compte_id[]')
        avance_trajets = request.POST.getlist('avance_trajet[]')
        avance_point_a_ids = request.POST.getlist('avance_point_a_id[]')
        avance_point_b_ids = request.POST.getlist('avance_point_b_id[]')
        avance_moyen_transports = request.POST.getlist('avance_moyen_transport[]')
        avance_is_deplacements = request.POST.getlist('avance_is_deplacement[]')

        selected_employe = Employe.objects.only('id', 'poste_id', 'base_id').filter(id=employe_id).first() if employe_id else None
        selected_fiche_poste = None
        if fiche_poste_id:
            selected_fiche_poste = FichePoste.objects.select_related('type_activites').filter(id=fiche_poste_id).first()
            if not selected_fiche_poste:
                messages.error(request, 'Fiche de poste introuvable')
                return redirect(request.path)
            type_activite_id = str(selected_fiche_poste.type_activites_id or '') or type_activite_id
            selected_poste_id = str(getattr(selected_employe, 'poste_id', '') or '')
            allowed_fiche_ids_for_employe = set(generic_access_fiche_ids)
            if selected_poste_id:
                allowed_fiche_ids_for_employe.update(poste_access_fiche_ids.get(selected_poste_id, set()))
            if allowed_fiche_ids_for_employe and str(fiche_poste_id) not in allowed_fiche_ids_for_employe:
                messages.error(request, "Cette fiche de poste n'est pas liee a l'employe selectionne.")
                return redirect(request.path)
        selected_type_activite = None
        if type_activite_id:
            selected_type_activite = allowed_types_qs.filter(id=type_activite_id).first() or TypeActivite.objects.filter(id=type_activite_id).first()

        current_allowed_type_ids = set(allowed_type_ids)
        current_allowed_fiche_ids = set(allowed_fiche_ids)
        if planning and planning.type_activite_id:
            current_allowed_type_ids.add(str(planning.type_activite_id))
        if planning and planning.fiche_poste_id:
            current_allowed_fiche_ids.add(str(planning.fiche_poste_id))

        if type_activite_id and str(type_activite_id) not in current_allowed_type_ids:
            messages.error(request, "Ce type d'activite n'est plus gere depuis ce formulaire.")
            return redirect(request.path)

        if fiche_poste_id and str(fiche_poste_id) not in current_allowed_fiche_ids:
            messages.error(request, "Cette fiche de poste doit etre geree depuis son workflow dedie.")
            return redirect(request.path)

        if not planning:
            duplicate_planning = _find_duplicate_planning_for_submission(
                date_planning,
                ouvrage_id,
                fiche_poste=selected_fiche_poste,
                type_activite=selected_type_activite,
                employe=selected_employe,
            )
            if duplicate_planning:
                added_participant_ids = _merge_duplicate_planning_participants(
                    duplicate_planning,
                    employe_id,
                    participant_ids,
                )
                if added_participant_ids:
                    messages.warning(
                        request,
                        "Activite deja saisie pour cet ouvrage a cette date. "
                        "La ligne existante a ete conservee et les employes ont ete ajoutes comme participants."
                    )
                else:
                    messages.warning(
                        request,
                        "Activite deja saisie pour cet ouvrage a cette date. La ligne existante a ete conservee."
                    )
                if submit_action == 'save_next_day':
                    return _build_next_day_planning_redirect(date_planning, employe_id, participant_ids)
                return redirect('planning:dashboard')

        if planning and planning.estvalide:
            # Sur planning valide, limiter aux champs autorises
            if date_planning:
                planning.date = date_planning
            if employe_id:
                planning.employe_id = employe_id
            planning.updated_at = timezone.now()
            planning.save(update_fields=['date', 'employe_id', 'updated_at'])
        else:
            if not planning:
                planning = Planning()
            if date_planning:
                planning.date = date_planning
            planning.employe_id = employe_id or None
            planning.type_activite_id = type_activite_id or None
            planning.fiche_poste_id = fiche_poste_id or None
            planning.ouvrage_id = ouvrage_id or None
            planning.remarque = remarque
            planning.statut = statut
            if photos_json is not None:
                planning.photo = photos_json
            planning.updated_at = timezone.now()
            if not planning.created_at:
                planning.created_at = timezone.now()
            planning.save()

        if planning and not planning.estvalide:
            PlanningDetail.objects.filter(planning=planning).delete()
            fallback_deplacement_designation = deplacement_default_designation
            for designation_id, quantity, pu, montant, acheteur, compte_id, trajet, point_a_id, point_b_id, moyen_transport, is_deplacement_flag in zip_longest(
                avance_designation_ids,
                avance_quantities,
                avance_pus,
                avance_montants,
                avance_acheteurs,
                avance_compte_ids,
                avance_trajets,
                avance_point_a_ids,
                avance_point_b_ids,
                avance_moyen_transports,
                avance_is_deplacements,
                fillvalue='',
            ):
                designation_id = (designation_id or '').strip()
                is_deplacement_row = (str(is_deplacement_flag or '').strip() == '1') or bool(
                    (trajet or '').strip() in ['aller', 'retour']
                    or (point_a_id or '').strip()
                    or (point_b_id or '').strip()
                    or (moyen_transport or '').strip()
                )
                if is_deplacement_row and fallback_deplacement_designation:
                    designation_id = str(fallback_deplacement_designation.id)
                if not designation_id:
                    continue
                try:
                    designation = Designation.objects.get(id=designation_id)
                except Designation.DoesNotExist:
                    continue

                try:
                    quantity_val = float(quantity or 0)
                except Exception:
                    quantity_val = 0.0
                try:
                    pu_val = Decimal(str(pu or 0))
                except Exception:
                    pu_val = Decimal('0')
                try:
                    montant_val = Decimal(str(montant or 0))
                except Exception:
                    montant_val = Decimal('0')

                detail = PlanningDetail(
                    planning=planning,
                    designation=designation,
                    quantity=quantity_val,
                    pu=pu_val,
                    montant=montant_val,
                    acheteur=(acheteur or '').strip() or None,
                )
                detail.utilise = False
                detail.retour = False
                detail.livraison = False
                if compte_id:
                    detail.compte_id = compte_id
                detail.save()
                if trajet in ['aller', 'retour'] or point_a_id or point_b_id or moyen_transport:
                    PlanningDetailDeplacement.objects.create(
                        planning_detail=detail,
                        trajet=trajet if trajet in ['aller', 'retour'] else 'aller',
                        point_a_id=point_a_id or None,
                        point_b_id=point_b_id or None,
                        moyen_transport=moyen_transport or None,
                    )

        # Participants: restent modifiables meme sur planning valide.
        PlanningEmploye.objects.filter(planning_id=planning.id).delete()
        for emp_id in participant_ids:
            if emp_id and str(emp_id) != str(planning.employe_id or ''):
                PlanningEmploye.objects.create(planning_id=planning.id, employee_id=emp_id)

        messages.success(request, 'Planning enregistre avec succes')
        if submit_action == 'save_next_day':
            return _build_next_day_planning_redirect(date_planning, employe_id, participant_ids)

        return redirect('planning:dashboard')

    employees_list = [
        {
            'id': str(emp.id),
            'name': emp.nom_affichage,
            'poste_id': str(emp.poste_id) if emp.poste_id else '',
            'base_id': str(emp.base_id) if emp.base_id else '',
            'base_name': emp.base.nom_base if emp.base_id and emp.base else 'Sans base',
            'poste_name': emp.poste.nom_poste if emp.poste_id and emp.poste else 'Sans poste',
            'display_name': emp.nom_affichage,
            'organisation_id': str(emp.base.organisation_id) if emp.base_id and emp.base and emp.base.organisation_id else '',
        }
        for emp in employees.select_related('base', 'poste')
    ]

    # Liste du select Employe : limitee a l'organisation de l'utilisateur
    # (l'employe deja affecte / participants restent toujours presents).
    user_base = getattr(getattr(request.user, 'employe', None), 'base', None)
    user_organisation_id = str(getattr(user_base, 'organisation_id', '') or '')
    pinned_ids = {str(i) for i in employee_ids_to_include}
    employees_select_list = [
        item for item in employees_list
        if not user_organisation_id
        or item['organisation_id'] == user_organisation_id
        or item['id'] in pinned_ids
    ]

    # Participants : meme liste, regroupee par base puis par poste.
    participants_groups = []
    for item in sorted(
        employees_select_list,
        key=lambda i: (i['base_name'].casefold(), i['poste_name'].casefold(), i['name'].casefold()),
    ):
        if not participants_groups or participants_groups[-1]['base'] != item['base_name']:
            participants_groups.append({'base': item['base_name'], 'postes': []})
        postes = participants_groups[-1]['postes']
        if not postes or postes[-1]['poste'] != item['poste_name']:
            postes.append({'poste': item['poste_name'], 'employees': []})
        postes[-1]['employees'].append(item)

    types_activites = allowed_types_qs

    generic_frequency_labels, poste_frequency_labels = _build_fiche_frequency_maps(
        fiches_poste,
        employees,
    )

    fiches_poste_data = [
        {
            'id': str(fp.id),
            'nom': fp.tache,
            'titre': fp.tache,
            'type_id': str(fp.type_activites.id) if fp.type_activites else '',
            'frequence_label': generic_frequency_labels.get(str(fp.id), ''),
        }
        for fp in fiches_poste
    ]

    ouvrages = Ouvrage.objects.exclude(nom_ouvrage__isnull=True).exclude(nom_ouvrage='').order_by('nom_ouvrage')
    ouvrages_data = [
        {
            'id': str(o.id),
            'nom': o.nom_ouvrage
        }
        for o in ouvrages
    ]

    villages = Village.objects.all().order_by('nom_village')
    villages_display = [_serialize_village_for_template(v) for v in villages]
    villages_data = [
        {
            'id': str(v.id),
            'nom': v.nom_village
        }
        for v in villages
    ]

    comptes = Compte.objects.all().order_by('nom_compte')
    comptes_display = [_serialize_compte_for_template(c) for c in comptes]
    comptes_data = [
        {
            'id': str(c.id),
            'nom': c.nom_compte
        }
        for c in comptes
    ]

    magasins = Magasin.objects.all().order_by('nom_magasin')
    magasins_display = [_serialize_magasin_for_template(m) for m in magasins]
    magasins_data = [
        {
            'id': str(m.id),
            'nom': m.nom_magasin
        }
        for m in magasins
    ]

    planning_ouvrage_id = getattr(planning, 'ouvrage_id', None) if planning else None

    designations = Designation.objects.all().order_by('nom')
    editable_avance_designations = [
        designation for designation in designations
        if _is_generic_planning_avance_designation(designation)
        and not _is_planning_deplacement_designation(designation)
    ]
    avance_designations_for_form = _build_planning_form_avance_designations(
        editable_avance_designations,
        details,
    )
    designations_data = [
        {
            'id': str(d.id),
            'nom': d.nom,
            'type_id': str(d.type_designation_id) if d.type_designation_id else '',
            'type_avance_caissiere': d.get_type_avance_caissiere_display() if d.type_avance_caissiere else '',
            'concerne_livraison': bool(d.concerne_livraison),
            'concerne_avance': bool(d.concerne_avance),
            'prix_unitaire': float(d.prix_unitaire) if d.prix_unitaire is not None else 0,
            'poste_acheteur': getattr(getattr(d, 'poste_acheteur', None), 'nom_poste', '') or '',
            'is_generic_planning_avance': _is_generic_planning_avance_designation(d),
        }
        for d in designations
    ]
    editable_avance_designations_data = [
        {
            'id': str(d.id),
            'nom': d.nom,
            'prix_unitaire': float(d.prix_unitaire) if d.prix_unitaire is not None else 0,
            'poste_acheteur': getattr(getattr(d, 'poste_acheteur', None), 'nom_poste', '') or '',
            'type_avance_caissiere': d.get_type_avance_caissiere_display() if d.type_avance_caissiere else '',
            'concerne_livraison': bool(d.concerne_livraison),
            'concerne_avance': bool(d.concerne_avance),
        }
        for d in avance_designations_for_form
    ]

    equipements_qs = EquipementConstitutif.objects.all()
    points_eau_qs = PointEau.objects.all()
    if planning_ouvrage_id:
        equipements_qs = equipements_qs.filter(ouvrage_id=planning_ouvrage_id)
        points_eau_qs = points_eau_qs.filter(ouvrage_id=planning_ouvrage_id)

    equipements = equipements_qs.order_by('nom')
    points_eau = _sort_points_eau_by_idxls(points_eau_qs)
    points_eau_display = [_serialize_point_eau_for_template(pe) for pe in points_eau]

    from .models import Deplacement

    deplacements = Deplacement.objects.select_related('point_a', 'point_b').order_by('point_a__nom_village', 'point_b__nom_village', 'moyen_transport')
    deplacements_data = [
        {
            'id': str(d.id),
            'point_a_id': str(d.point_a_id) if d.point_a_id else '',
            'point_a_nom': d.point_a.nom_village if d.point_a else '',
            'point_b_id': str(d.point_b_id) if d.point_b_id else '',
            'point_b_nom': d.point_b.nom_village if d.point_b else '',
            'moyen_transport': d.moyen_transport or '',
            'moyen_transport_label': d.get_moyen_transport_display() if d.moyen_transport else '',
            'prix_unitaire': float(d.prix_unitaire) if d.prix_unitaire is not None else 0,
            'date_prix': d.date_prix.isoformat() if d.date_prix else '',
        }
        for d in deplacements
    ]

    is_directeur = False
    if request.user.is_authenticated and hasattr(request.user, 'employe') and request.user.employe:
        is_directeur = request.user.employe.is_directeur
    can_adjust_validation = bool(planning and can_user_adjust_planning_validation(request.user, planning))

    context = {
        'planning': planning,
        'initial_date': initial_date,
        'initial_employe_id': initial_employe_id,
        'details': details,
        'deplacement_details': deplacement_details,
        'managed_elsewhere_details': managed_elsewhere_details,
        'livraisons': livraisons,
        'paiements_forfaitaires': paiements_forfaitaires,
        'planning_pieces': planning_pieces,
        'auto_advanced_count': auto_advanced_count,
        'auto_advanced_detail_ids': auto_advanced_detail_ids,
        'employees': employees_list,
        'employees_select': employees_select_list,
        'participants_groups': participants_groups,
        'participants_ids': participants_ids,
        'types_activites': [{'id': str(t.id), 'nom': t.nomtype} for t in types_activites],
        'fiches_poste': [
            {
                'id': str(fp.id),
                'nom': fp.tache,
                'type_id': str(fp.type_activites_id) if fp.type_activites_id else '',
                'frequence_label': generic_frequency_labels.get(str(fp.id), ''),
            }
            for fp in fiches_poste
        ],
        'designations': designations,
        'editable_avance_designations': avance_designations_for_form,
        'deplacement_default_designation': deplacement_default_designation,
        'comptes': comptes_display,
        'equipements': equipements,
        'villages': villages_display,
        'magasins': magasins_display,
        'points_eau': points_eau_display,
        'deplacements_json': json.dumps(deplacements_data),
        'fiches_poste_json': json.dumps(fiches_poste_data),
        'ouvrages_json': json.dumps(ouvrages_data),
        'villages_json': json.dumps(villages_data),
        'comptes_json': json.dumps(comptes_data),
        'magasins_json': json.dumps(magasins_data),
        'designations_json': json.dumps(designations_data),
        'editable_avance_designations_json': json.dumps(editable_avance_designations_data),
        'deplacement_default_designation_json': json.dumps({
            'id': str(deplacement_default_designation.id) if deplacement_default_designation else '',
            'nom': deplacement_default_designation.nom if deplacement_default_designation else 'Frais de déplacement',
            'prix_unitaire': float(deplacement_default_designation.prix_unitaire) if deplacement_default_designation and deplacement_default_designation.prix_unitaire is not None else 0,
            'poste_acheteur': getattr(getattr(deplacement_default_designation, 'poste_acheteur', None), 'nom_poste', '') or '',
        }),
        'employees_json': json.dumps(employees_list),
        'fiche_frequency_labels_json': json.dumps(generic_frequency_labels),
        'fiche_frequency_labels_by_poste_json': json.dumps(poste_frequency_labels),
        'fiche_access_generic_ids_json': json.dumps(sorted(generic_access_fiche_ids)),
        'fiche_access_by_poste_json': json.dumps({key: sorted(value) for key, value in poste_access_fiche_ids.items()}),
        'is_directeur': is_directeur,
        'can_adjust_validation': can_adjust_validation,
    }

    return render(request, 'planning/planning_form.html', context)


@login_required
def planning_merge_current_duplicates(request, planning_id):
    if request.method != 'POST':
        return redirect('planning:form_update', planning_id=planning_id)

    planning = get_object_or_404(
        Planning.objects.select_related('fiche_poste', 'type_activite', 'ouvrage', 'employe'),
        id=planning_id,
    )

    activity_label = _normalize_poste_name(_get_planning_activity_label(planning=planning))
    if not activity_label:
        messages.warning(request, "Controle impossible: ce planning n'a pas d'activite exploitable.")
        return redirect('planning:form_update', planning_id=planning.id)

    if not planning.ouvrage_id and not _is_shared_no_ouvrage_activity_label(activity_label):
        messages.warning(
            request,
            "Controle impossible: ce planning n'a pas d'ouvrage et son activite n'est pas fusionnable sans ouvrage.",
        )
        return redirect('planning:form_update', planning_id=planning.id)

    merge_summary = _merge_duplicate_plannings_into_current(planning)
    if not merge_summary['duplicates']:
        messages.info(
            request,
            "Aucun doublon detecte pour cette date et cette activite.",
        )
        return redirect('planning:form_update', planning_id=planning.id)

    messages.success(
        request,
        (
            f"{merge_summary['duplicates']} doublon(s) fusionne(s). "
            f"{merge_summary['participants_added']} participant(s) ajoute(s), "
            f"{merge_summary['details_moved']} detail(s), "
            f"{merge_summary['bons_moved']} bon(s), "
            f"{merge_summary['paiements_moved']} paiement(s), "
            f"{merge_summary['pieces_moved']} piece(s) et "
            f"{merge_summary['photos_added']} photo(s) rattache(s) au planning courant."
        ),
    )
    return redirect('planning:form_update', planning_id=planning.id)


@login_required
def api_employee_month_preview(request):
    employe_id = (request.GET.get('employe_id') or '').strip()
    month_value = (request.GET.get('month') or '').strip()
    exclude_planning_id = (request.GET.get('exclude_planning_id') or '').strip()

    if not employe_id:
        return JsonResponse({'rows': [], 'month': month_value or ''})

    if not month_value:
        month_value = timezone.localdate().strftime('%Y-%m')

    try:
        month_start = datetime.strptime(f'{month_value}-01', '%Y-%m-%d').date()
    except ValueError:
        return JsonResponse(
            {'error': 'Parametre month invalide. Format attendu: YYYY-MM.'},
            status=400
        )

    month_end = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)

    scope = _get_planning_scope(request.user)
    if scope == 'none':
        return JsonResponse({'rows': [], 'month': month_value})

    plannings_qs = Planning.objects.filter(
        employe_id=employe_id,
        date__date__gte=month_start,
        date__date__lt=month_end,
    ).select_related('employe', 'fiche_poste', 'type_activite', 'ouvrage')

    if scope == 'base':
        base_id = getattr(getattr(request.user, 'employe', None), 'base_id', None)
        if not base_id:
            return JsonResponse({'rows': [], 'month': month_value})
        plannings_qs = plannings_qs.filter(employe__base_id=base_id)
    elif scope == 'organisation':
        organisation_id = getattr(
            getattr(getattr(request.user, 'employe', None), 'base', None),
            'organisation_id',
            None
        )
        if not organisation_id:
            return JsonResponse({'rows': [], 'month': month_value})
        plannings_qs = plannings_qs.filter(employe__base__organisation_id=organisation_id)

    if exclude_planning_id:
        plannings_qs = plannings_qs.exclude(id=exclude_planning_id)

    status_labels = {
        'en_cours': 'En cours',
        'termine': 'Termine',
        'annule': 'Annule',
        'reporte': 'Reporte',
    }

    tz = timezone.get_current_timezone()
    rows = []
    for planning in plannings_qs.order_by('date'):
        if not planning.date:
            continue

        date_value = planning.date
        if timezone.is_aware(date_value):
            local_date = timezone.localtime(date_value, tz).date()
        else:
            local_date = date_value.date()

        activite_label = ''
        if planning.fiche_poste_id and planning.fiche_poste:
            activite_label = planning.fiche_poste.tache or ''
        elif planning.type_activite_id and planning.type_activite:
            activite_label = planning.type_activite.nomtype or ''

        ouvrage_label = ''
        if planning.ouvrage:
            ouvrage_label = (
                getattr(planning.ouvrage, 'nom_ouvrage', '')
                or getattr(planning.ouvrage, 'infra_name', '')
                or getattr(planning.ouvrage, 'nom', '')
            )

        raw_status = planning.statut or ''
        if raw_status:
            status_label = status_labels.get(raw_status, raw_status.replace('_', ' ').title())
        else:
            status_label = 'Valide' if planning.estvalide else 'En attente'

        rows.append({
            'id': str(planning.id),
            'date': local_date.isoformat(),
            'date_label': local_date.strftime('%d/%m/%Y'),
            'activite': activite_label or 'Sans activite',
            'ouvrage': ouvrage_label or '-',
            'statut': raw_status or 'en_attente',
            'statut_label': status_label,
            'validation': bool(planning.estvalide),
            'validation_label': 'Valide' if planning.estvalide else 'Non valide',
            'remarque': planning.remarque or '',
        })

    return JsonResponse({'rows': rows, 'month': month_value})


@api_view(['GET'])
@permission_classes([AllowAny])
def api_equipements_by_ouvrage(request):
    try:
        from apps.infrastructure.models import EquipementConstitutif
        ouvrage_id = request.GET.get('ouvrage_id')
        qs = EquipementConstitutif.objects.all()
        if ouvrage_id:
            qs = qs.filter(ouvrage_id=ouvrage_id)
        equipements = [
            {'id': str(e.id), 'nom': e.nom}
            for e in qs.order_by('nom')
        ]
        return Response({'equipements': equipements})
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['GET'])
@permission_classes([AllowAny])
def api_points_eau_by_ouvrage(request):
    try:
        from apps.billing.models import PointEau
        ouvrage_id = request.GET.get('ouvrage_id')
        qs = PointEau.objects.all()
        if ouvrage_id:
            qs = qs.filter(ouvrage_id=ouvrage_id)
        points_eau = [
            {
                'id': str(pe.id),
                'nom': pe.nomabonne,
                'nom_abonne': pe.nomabonne,
                'idxls': pe.idxls,
                'forfaitaire_label': pe.forfaitaire_display_label,
                'tarif': float(pe.tarifforfaitaire or 0)
            }
            for pe in _sort_points_eau_by_idxls(qs)
        ]
        return Response({'points_eau': points_eau})
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['GET'])
@permission_classes([AllowAny])
def api_designations_by_activite(request):
    try:
        from apps.planning.models import DesignationTypeActivite, Designation
        type_activite_id = request.GET.get('type_activite_id')
        activite_id = request.GET.get('activite_id')

        designations = []
        if type_activite_id:
            links = DesignationTypeActivite.objects.filter(type_activite_id=type_activite_id).select_related('designation')
            designations = [
                {'id': str(l.designation.id), 'nom': l.designation.nom}
                for l in links
            ]
        elif activite_id:
            # Fallback: retourner toutes les designations si activite_id est fourni sans mapping
            designations = [
                {'id': str(d.id), 'nom': d.nom}
                for d in Designation.objects.all().order_by('nom')
            ]

        return Response({'designations': designations})
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['GET'])
@permission_classes([AllowAny])
def api_comptes_by_designation(request):
    try:
        from apps.planning.models import DesignationCompte
        designation_id = request.GET.get('designation_id')
        if not designation_id:
            return Response({'comptes': []})
        links = DesignationCompte.objects.filter(designation_id=designation_id).select_related('compte')
        comptes = [
            {'id': str(l.compte.id), 'nom': l.compte.nom_compte}
            for l in links
        ]
        return Response({'comptes': comptes})
    except Exception as e:
        return Response({'error': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([AllowAny])
def create_planning_from_inspection_dev(request):
    """API placeholder pour creation de planning depuis inspection."""
    return Response({'error': 'Endpoint non implemente'}, status=501)


@api_view(['GET'])
@permission_classes([AllowAny])
def activites_api_simple(request):
    """API pour r?cup?rer les fiches de poste (remplace les activit?s)"""
    try:
        from apps.employees.models_evaluation import FichePoste
        fiches = FichePoste.objects.all().select_related('type_activites')
        fiches_data = []
        for fiche in fiches:
            fiches_data.append({
                'id': str(fiche.id),
                'titre': fiche.tache,
                'nom': fiche.tache,
                'description': fiche.description or '',
                'type': fiche.type_activites.nomtype if fiche.type_activites else '',
                'type_display': fiche.type_activites.nomtype if fiche.type_activites else '',
                'type_id': str(fiche.type_activites.id) if fiche.type_activites else '',
                'is_active': True,
                'created_at': None
            })
        return Response(fiches_data)
    except Exception as e:
        return Response({'error': str(e)}, status=500)


def employees_api_plain(request):
    """API simple JSON pour employes actifs."""
    try:
        if not request.user.is_authenticated:
            return JsonResponse([], safe=False)

        employees_qs = _get_scoped_employees_queryset(request.user).select_related('poste', 'base')
        employees = [
            {
                'id': str(emp.id),
                'nom': emp.nom or '',
                'prenom': emp.prenom or '',
                'surnom': emp.surnom or '',
                'display_name': emp.surnom or emp.nom_complet or emp.nom or '',
                'base_id': str(emp.base_id) if emp.base_id else '',
                'base_name': emp.base.nom_base if emp.base else 'Sans base',
                'poste_id': str(emp.poste_id) if emp.poste_id else '',
                'poste_name': emp.poste.nom_poste if emp.poste else 'Sans poste',
            }
            for emp in employees_qs.order_by(
                'base__nom_base', 'poste__nom_poste', 'surnom', 'nom', 'prenom'
            )
        ]
        return JsonResponse(employees, safe=False)
    except Exception:
        return JsonResponse([], safe=False)


def ouvrages_api_plain(request):
    """API simple JSON pour ouvrages."""
    try:
        if not request.user.is_authenticated:
            return JsonResponse([], safe=False)
        cursor = connection.cursor()
        cursor.execute("""
            SELECT id, nom_ouvrage
            FROM ouvrages
            ORDER BY nom_ouvrage
        """)
        ouvrages = [
            {
                'id': row[0],
                'infra_name': row[1],
                'infra_status': 'operationnel'
            }
            for row in cursor.fetchall()
        ]
        return JsonResponse(ouvrages, safe=False)
    except Exception:
        return JsonResponse([], safe=False)
