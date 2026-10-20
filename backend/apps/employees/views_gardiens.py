"""
Vues pour la gestion des rotations et congés des gardiens
"""
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from django.db.models import Max, Q
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from datetime import date, datetime, timedelta, time
from decimal import Decimal
import json
import pytz
import calendar
import unicodedata

from .models import Employe
from .models_gardiens import RotationGardien, HeuresSupplementairesGardien
from .utils_conges import est_jour_ferie as est_jour_ferie_configure, get_type_jour_ferie
from apps.planning.models import Planning, Activite, ActivitePoste


# IDs des 3 gardiens (hardcodés pour l'instant)
GARDIENS_IDS = [
    '64a11eeb-0dfc-4d6b-92ea-73175edc3642',  # RAOUL
    'cde49c47-0e00-4ba1-8631-a0b0ed150849',  # RENE
    'b866a66c-93fb-42b4-81ef-08caaa25c272',  # VELONASY
]


def _normalize_poste_name(value):
    if not value:
        return ''
    normalized = unicodedata.normalize('NFKD', str(value))
    return normalized.encode('ascii', errors='ignore').decode('ascii').lower().strip()


def _get_planning_scope(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return 'none'
    if getattr(user, 'is_superuser', False):
        return 'all'

    employe = getattr(user, 'employe', None)
    if not employe:
        return 'none'

    poste_nom = _normalize_poste_name(getattr(getattr(employe, 'poste', None), 'nom_poste', ''))
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


def _filter_employes_by_scope(queryset, user):
    scope = _get_planning_scope(user)
    if scope == 'all':
        return queryset
    if scope == 'none':
        return queryset.none()

    employe = getattr(user, 'employe', None)
    if not employe:
        return queryset.none()

    if scope == 'organisation':
        organisation_id = getattr(getattr(employe, 'base', None), 'organisation_id', None)
        if not organisation_id:
            return queryset.none()
        return queryset.filter(base__organisation_id=organisation_id)

    base_id = getattr(employe, 'base_id', None)
    if not base_id:
        return queryset.none()
    return queryset.filter(base_id=base_id)


def _get_allowed_guardians_queryset(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return Employe.objects.none()

    # Pour cette page, on cloisonne par organisation courante (sauf superuser)
    guardians_qs = Employe.objects.filter(poste__nom_poste__icontains='gardien')
    if getattr(user, 'is_superuser', False):
        scoped = guardians_qs
    else:
        user_employe = getattr(user, 'employe', None)
        organisation_id = getattr(getattr(user_employe, 'base', None), 'organisation_id', None)
        if not organisation_id:
            return Employe.objects.none()
        scoped = guardians_qs.filter(base__organisation_id=organisation_id)

    # Fallback legacy si les postes "Gardien" ne sont pas renseignes
    if scoped.exists():
        return scoped

    fallback_qs = Employe.objects.filter(id__in=GARDIENS_IDS)
    if getattr(user, 'is_superuser', False):
        return fallback_qs

    user_employe = getattr(user, 'employe', None)
    organisation_id = getattr(getattr(user_employe, 'base', None), 'organisation_id', None)
    if not organisation_id:
        return Employe.objects.none()
    return fallback_qs.filter(base__organisation_id=organisation_id)


def _get_allowed_guardian_ids(user):
    return [str(emp_id) for emp_id in _get_allowed_guardians_queryset(user).values_list('id', flat=True)]


def _resolve_planning_targets_for_activity(activity_lookup):
    from apps.employees.models_evaluation import FichePoste

    activite = (
        Activite.objects
        .select_related('type_activite')
        .filter(nom__icontains=activity_lookup)
        .first()
    )

    fiche_poste = None
    if activite:
        activite_poste = (
            ActivitePoste.objects
            .filter(activite=activite, fiche_poste__isnull=False)
            .select_related('fiche_poste', 'fiche_poste__type_activites')
            .order_by('-fiche_poste__dans_planning', 'fiche_poste__ordre', 'fiche_poste__tache')
            .first()
        )
        fiche_poste = activite_poste.fiche_poste if activite_poste else None

    if not fiche_poste:
        fiche_poste = (
            FichePoste.objects
            .filter(tache__icontains=activity_lookup)
            .select_related('type_activites')
            .order_by('-dans_planning', 'ordre', 'tache')
            .first()
        )

    type_activite = None
    if fiche_poste and fiche_poste.type_activites_id:
        type_activite = fiche_poste.type_activites
    elif activite and activite.type_activite_id:
        type_activite = activite.type_activite

    return activite, fiche_poste, type_activite


def est_jour_ferie(date_obj):
    """
    Vérifie si une date est un jour férié

    Args:
        date_obj: datetime.date

    Returns:
        bool: True si jour férié
    """
    return est_jour_ferie_configure(date_obj)


def _get_effective_holiday_flag(rotation):
    if not rotation or not getattr(rotation, 'date', None):
        return False
    return est_jour_ferie(rotation.date)


def get_jour_nuit_ids(date_obj):
    rotations = RotationGardien.objects.filter(
        employe_id__in=GARDIENS_IDS,
        date=date_obj
    )
    day_id = rotations.filter(shift_type='jour').values_list('employe_id', flat=True).first()
    night_id = rotations.filter(shift_type='nuit').values_list('employe_id', flat=True).first()
    if day_id and night_id and str(day_id) != str(night_id):
        return str(day_id), str(night_id)
    return None, None


def generer_rotation_standard(date_debut, nb_jours=30, start_day_guard_id=None, start_night_guard_id=None):
    """
    Génère une rotation standard pour les 3 gardiens sur N jours

    Rotation : Jour (8h-18h) → Nuit (18h-8h) → Congé → Répète

    Args:
        date_debut: datetime.date de début
        nb_jours: nombre de jours à générer

    Returns:
        list: Liste de dict {employe_id, date, shift_type, heure_debut, heure_fin}
    """
    rotations = []

    # Ordre initial (peut être modifié selon situation actuelle)
    if start_day_guard_id or start_night_guard_id:
        if not start_day_guard_id or not start_night_guard_id:
            raise ValueError('start_day_guard_id et start_night_guard_id sont obligatoires')
        if start_day_guard_id == start_night_guard_id:
            raise ValueError('Le gardien de jour et de nuit doivent être différents')
        if start_day_guard_id not in GARDIENS_IDS or start_night_guard_id not in GARDIENS_IDS:
            raise ValueError('Gardien de départ invalide')

        autres = [gid for gid in GARDIENS_IDS if gid not in [start_day_guard_id, start_night_guard_id]]
        if len(autres) != 1:
            raise ValueError('Impossible de déterminer le troisième gardien')
        ordre_gardiens = [start_day_guard_id, start_night_guard_id, autres[0]]
    else:
        ordre_gardiens = GARDIENS_IDS.copy()

    # Pattern de rotation : Jour, Nuit, Congé (répète tous les 3 jours)
    pattern = ['jour', 'nuit', 'conge']

    for i in range(nb_jours):
        date_courante = date_debut + timedelta(days=i)

        for idx, gardien_id in enumerate(ordre_gardiens):
            # Position dans le pattern (chaque gardien est décalé)
            position_pattern = (i + idx) % len(pattern)
            shift_type = pattern[position_pattern]

            if shift_type == 'conge':
                continue  # Pas de rotation à créer pour les congés

            # Définir les heures selon le type de shift
            if shift_type == 'jour':
                heure_debut = time(8, 0)
                heure_fin = time(18, 0)
            else:  # nuit
                heure_debut = time(18, 0)
                heure_fin = time(8, 0)  # Lendemain matin

            # Vérifier si dimanche ou férié
            est_dimanche = date_courante.weekday() == 6
            est_ferie = est_jour_ferie(date_courante)

            rotations.append({
                'employe_id': gardien_id,
                'date': date_courante,
                'shift_type': shift_type,
                'heure_debut': heure_debut,
                'heure_fin': heure_fin,
                'est_dimanche': est_dimanche,
                'est_jour_ferie': est_ferie,
                'est_extension': False,
            })

    return rotations


@csrf_exempt
@require_http_methods(["POST"])
def api_generer_rotations(request):
    """
    API pour générer automatiquement les rotations pour les gardiens

    POST /api/gardiens/generer-rotations/
    Body: {
        "date_debut": "2025-12-30",
        "nb_jours": 30
    }
    """
    try:
        data = json.loads(request.body)
        date_debut_str = data.get('date_debut')
        nb_jours = int(data.get('nb_jours', 30))
        start_day_guard_id = data.get('start_day_guard_id')
        start_night_guard_id = data.get('start_night_guard_id')

        if not date_debut_str:
            return JsonResponse({
                'success': False,
                'error': 'date_debut est obligatoire'
            }, status=400)

        if not start_day_guard_id or not start_night_guard_id:
            return JsonResponse({
                'success': False,
                'error': 'start_day_guard_id et start_night_guard_id sont obligatoires'
            }, status=400)

        # Parser la date
        date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
        if nb_jours <= 0:
            return JsonResponse({
                'success': False,
                'error': 'nb_jours doit etre superieur a 0'
            }, status=400)

        date_fin = date_debut + timedelta(days=nb_jours - 1)

        # Supprimer les rotations existantes sur la periode pour eviter les doublons
        rotations_supprimees = RotationGardien.objects.filter(
            employe_id__in=GARDIENS_IDS,
            date__gte=date_debut,
            date__lte=date_fin
        ).delete()[0]

        # Générer les rotations
        try:
            rotations_data = generer_rotation_standard(
                date_debut,
                nb_jours,
                start_day_guard_id=start_day_guard_id,
                start_night_guard_id=start_night_guard_id
            )
        except ValueError as exc:
            return JsonResponse({
                'success': False,
                'error': str(exc)
            }, status=400)

        # Créer les enregistrements en base
        rotations_creees = []
        rotations_existantes = []
        for rot_data in rotations_data:
            # Vérifier si existe déjà
            existe = RotationGardien.objects.filter(
                employe_id=rot_data['employe_id'],
                date=rot_data['date']
            ).exists()

            if not existe:
                rotation = RotationGardien.objects.create(**rot_data)
                rotations_creees.append(str(rotation.date))
            else:
                rotations_existantes.append(str(rot_data['date']))

        # Message adapté selon le résultat
        if len(rotations_creees) > 0:
            message = f'{len(rotations_creees)} rotation(s) créée(s)'
            if len(rotations_existantes) > 0:
                message += f' ({len(rotations_existantes)} existaient déjà)'
        else:
            message = f'Aucune rotation créée : {len(rotations_existantes)} rotation(s) existaient déjà pour cette période'

        return JsonResponse({
            'success': True,
            'message': message,
            'rotations_creees': rotations_creees,
            'rotations_existantes': rotations_existantes,
            'total_genere': len(rotations_data),
            'rotations_supprimees': rotations_supprimees
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_conge_gardien(request):
    """
    API pour créer un congé de gardien et étendre automatiquement les shifts des 2 autres

    POST /api/gardiens/creer-conge/
    Body: {
        "employe_id": "uuid",
        "date_debut": "2025-12-30",
        "date_fin": "2026-01-02",
        "motif": "Congé annuel"
    }

    Workflow:
    1. Marque le gardien en congé dans RotationGardien
    2. Trouve les 2 autres gardiens
    3. Pour chaque jour de congé:
       - Supprime le shift du gardien en congé
       - Étend les shifts des 2 autres à 8h-8h (24h)
       - Marque est_extension=True
    """
    try:
        allowed_guardian_ids = _get_allowed_guardian_ids(request.user)
        if set(allowed_guardian_ids) != set(GARDIENS_IDS):
            return JsonResponse({
                'success': False,
                'error': 'Acces non autorise pour gerer les conges des gardiens'
            }, status=403)

        data = json.loads(request.body)
        employe_id = data.get('employe_id')
        date_debut_str = data.get('date_debut')
        date_fin_str = data.get('date_fin')
        remplacement_start_guard_id = data.get('remplacement_start_guard_id')
        motif = data.get('motif', 'Congé')

        # Validation
        if not all([employe_id, date_debut_str, date_fin_str]):
            return JsonResponse({
                'success': False,
                'error': 'employe_id, date_debut et date_fin sont obligatoires'
            }, status=400)
        if not remplacement_start_guard_id:
            return JsonResponse({
                'success': False,
                'error': 'remplacement_start_guard_id est obligatoire'
            }, status=400)

        # Vérifier que c'est bien un gardien
        if employe_id not in GARDIENS_IDS:
            return JsonResponse({
                'success': False,
                'error': 'Cet employé n\'est pas un gardien'
            }, status=400)

        # Parser les dates
        date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
        date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()

        # Trouver les 2 autres gardiens
        autres_gardiens = [gid for gid in GARDIENS_IDS if gid != employe_id]
        if remplacement_start_guard_id not in autres_gardiens:
            return JsonResponse({
                'success': False,
                'error': 'Le gardien de remplacement doit etre un autre gardien'
            }, status=400)
        ordre_remplacement = [remplacement_start_guard_id] + [
            gid for gid in autres_gardiens if gid != remplacement_start_guard_id
        ]

        # Timezone Madagascar
        tz_madagascar = pytz.timezone('Indian/Antananarivo')

        # Récupérer l'activité "Congé"
        activite_conge = Activite.objects.filter(nom='Congé').first()
        if not activite_conge:
            return JsonResponse({
                'success': False,
                'error': 'Activité "Congé" non trouvée'
            }, status=404)

        # Pour chaque jour de congé
        _, fiche_poste_conge, type_activite_conge = _resolve_planning_targets_for_activity('Cong')
        if not type_activite_conge and activite_conge.type_activite_id:
            type_activite_conge = activite_conge.type_activite

        current_date = date_debut
        jours_traites = []
        shifts_etendus = []

        jour_index = 0
        while current_date <= date_fin:
            # 1. Supprimer les rotations existantes du gardien en congé
            RotationGardien.objects.filter(
                employe_id=employe_id,
                date=current_date
            ).delete()

            RotationGardien.objects.filter(
                employe_id__in=autres_gardiens,
                date=current_date
            ).delete()

            # 2. Créer entrée Planning pour le gardien en congé
            date_planning = tz_madagascar.localize(
                datetime.combine(current_date, datetime.min.time())
            )

            planning_defaults = {
                'estvalide': False
            }
            if fiche_poste_conge:
                planning_defaults['fiche_poste'] = fiche_poste_conge
            if type_activite_conge:
                planning_defaults['type_activite'] = type_activite_conge

            Planning.objects.get_or_create(
                employe_id=employe_id,
                date=date_planning,
                defaults=planning_defaults
            )

            # 3. Etendre le shift d'un seul gardien (alternance)
            est_dimanche = current_date.weekday() == 6
            est_ferie = est_jour_ferie(current_date)

            gardien_remplacement = ordre_remplacement[jour_index % len(ordre_remplacement)]

            RotationGardien.objects.create(
                employe_id=gardien_remplacement,
                date=current_date,
                shift_type='etendu',
                heure_debut=time(8, 0),
                heure_fin=time(8, 0),  # Lendemain
                heures_travaillees=Decimal('24'),
                est_dimanche=est_dimanche,
                est_jour_ferie=est_ferie,
                est_extension=True,
                remplace_employe_id=employe_id
            )

            shifts_etendus.append({
                'gardien_id': gardien_remplacement,
                'date': str(current_date)
            })
            jours_traites.append(str(current_date))
            current_date += timedelta(days=1)
            jour_index += 1

        # Recalage des rotations après le congé (cycle standard)
        reprise_info = None
        date_reprise = date_fin + timedelta(days=1)
        dernier_jour_rotation = RotationGardien.objects.filter(
            employe_id__in=GARDIENS_IDS,
            date__gte=date_reprise
        ).aggregate(Max('date'))['date__max']

        if dernier_jour_rotation:
            nb_jours_reprise = (dernier_jour_rotation - date_reprise).days + 1
            dernier_gardien = ordre_remplacement[(jour_index - 1) % len(ordre_remplacement)]
            gardien_repos = [gid for gid in autres_gardiens if gid != dernier_gardien][0]

            RotationGardien.objects.filter(
                employe_id__in=GARDIENS_IDS,
                date__gte=date_reprise,
                date__lte=dernier_jour_rotation
            ).delete()

            rotations_reprise = generer_rotation_standard(
                date_reprise,
                nb_jours_reprise,
                start_day_guard_id=employe_id,
                start_night_guard_id=gardien_repos
            )

            RotationGardien.objects.bulk_create([
                RotationGardien(**rot) for rot in rotations_reprise
            ])

            reprise_info = {
                'date_reprise': str(date_reprise),
                'date_fin': str(dernier_jour_rotation),
                'nb_jours': nb_jours_reprise,
                'start_day_guard_id': employe_id,
                'start_night_guard_id': gardien_repos
            }

        return JsonResponse({
            'success': True,
            'message': f'Congé créé pour {len(jours_traites)} jour(s). {len(shifts_etendus)} shift(s) étendu(s).',
            'jours_traites': jours_traites,
            'shifts_etendus': shifts_etendus,
            'reprise_rotations': reprise_info
        })

    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_recalculer_mois_gardiens(request):
    """
    Recalcule les rotations standard pour un mois.

    Body: { "month": "YYYY-MM", "start_day_guard_id": "uuid", "start_night_guard_id": "uuid" }
    """
    try:
        allowed_guardian_ids = _get_allowed_guardian_ids(request.user)
        if set(allowed_guardian_ids) != set(GARDIENS_IDS):
            return JsonResponse({
                'success': False,
                'error': 'Acces non autorise pour generer les rotations des gardiens'
            }, status=403)

        data = json.loads(request.body)
        month_value = data.get('month')
        start_day_guard_id = data.get('start_day_guard_id')
        start_night_guard_id = data.get('start_night_guard_id')

        if not month_value:
            return JsonResponse({
                'success': False,
                'error': 'month est obligatoire (format YYYY-MM)'
            }, status=400)

        annee_str, mois_str = month_value.split('-')
        annee = int(annee_str)
        mois = int(mois_str)
        nb_jours = calendar.monthrange(annee, mois)[1]
        date_debut = date(annee, mois, 1)
        date_fin = date(annee, mois, nb_jours)

        if start_day_guard_id or start_night_guard_id:
            if not start_day_guard_id or not start_night_guard_id:
                return JsonResponse({
                    'success': False,
                    'error': 'start_day_guard_id et start_night_guard_id sont obligatoires ensemble'
                }, status=400)
            if start_day_guard_id == start_night_guard_id:
                return JsonResponse({
                    'success': False,
                    'error': 'Les gardiens de debut jour/nuit doivent etre differents'
                }, status=400)
            if start_day_guard_id not in GARDIENS_IDS or start_night_guard_id not in GARDIENS_IDS:
                return JsonResponse({
                    'success': False,
                    'error': 'Gardiens de debut invalides'
                }, status=400)
        else:
            prev_day_id, prev_night_id = get_jour_nuit_ids(date_debut - timedelta(days=1))
            if prev_day_id and prev_night_id:
                autres = [gid for gid in GARDIENS_IDS if gid not in [prev_day_id, prev_night_id]]
                if len(autres) != 1:
                    return JsonResponse({
                        'success': False,
                        'error': 'Impossible de determiner le gardien de repos'
                    }, status=400)
                start_day_guard_id = autres[0]
                start_night_guard_id = prev_day_id
            else:
                day_id, night_id = get_jour_nuit_ids(date_debut)
                if not day_id or not night_id:
                    return JsonResponse({
                        'success': False,
                        'error': 'Impossible de determiner l ordre de debut. Utilisez Generer Rotations.'
                    }, status=400)
                start_day_guard_id = day_id
                start_night_guard_id = night_id

        rotations_supprimees = RotationGardien.objects.filter(
            employe_id__in=GARDIENS_IDS,
            date__gte=date_debut,
            date__lte=date_fin
        ).delete()[0]

        activite_conge = Activite.objects.filter(nom__icontains='Congé').first()
        _, fiche_poste_conge, type_activite_conge = _resolve_planning_targets_for_activity('Cong')
        if not type_activite_conge and activite_conge and activite_conge.type_activite_id:
            type_activite_conge = activite_conge.type_activite

        conges_supprimes = 0
        conge_filters = Q()
        if fiche_poste_conge:
            conge_filters |= Q(fiche_poste=fiche_poste_conge)
        if type_activite_conge:
            conge_filters |= Q(fiche_poste__isnull=True, type_activite=type_activite_conge)

        if conge_filters.children:
            conges_supprimes = Planning.objects.filter(
                employe_id__in=GARDIENS_IDS,
                date__date__gte=date_debut,
                date__date__lte=date_fin
            ).filter(conge_filters).delete()[0]

        rotations_data = generer_rotation_standard(
            date_debut,
            nb_jours,
            start_day_guard_id=start_day_guard_id,
            start_night_guard_id=start_night_guard_id
        )

        RotationGardien.objects.bulk_create([
            RotationGardien(**rot) for rot in rotations_data
        ])

        return JsonResponse({
            'success': True,
            'message': f'Mois {month_value} recalculé',
            'rotations_creees': len(rotations_data),
            'rotations_supprimees': rotations_supprimees,
            'conges_supprimes': conges_supprimes,
            'start_day_guard_id': start_day_guard_id,
            'start_night_guard_id': start_night_guard_id
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def api_rotations_liste(request):
    """
    API pour lister les rotations des gardiens

    GET /api/gardiens/rotations/?date_debut=...&date_fin=...&employe_id=...
    """
    try:
        allowed_guardian_ids = _get_allowed_guardian_ids(request.user)
        date_debut_str = request.GET.get('date_debut')
        date_fin_str = request.GET.get('date_fin')
        employe_id = request.GET.get('employe_id')

        # Construire le queryset
        qs = RotationGardien.objects.select_related('employe', 'remplace_employe')

        # Filtres
        if date_debut_str:
            date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
            qs = qs.filter(date__gte=date_debut)

        if date_fin_str:
            date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
            qs = qs.filter(date__lte=date_fin)

        if employe_id:
            qs = qs.filter(employe_id=employe_id)

        # Limiter aux gardiens uniquement
        qs = qs.filter(employe_id__in=allowed_guardian_ids)

        # Sérialiser
        rotations = []
        for rot in qs:
            est_ferie = _get_effective_holiday_flag(rot)
            type_jour_ferie = get_type_jour_ferie(rot.date) if est_ferie else None
            rotations.append({
                'id': str(rot.id),
                'employe_id': str(rot.employe.id),
                'employe_nom': rot.employe.surnom or rot.employe.nom,
                'date': str(rot.date),
                'shift_type': rot.shift_type,
                'shift_type_display': rot.get_shift_type_display(),
                'heure_debut': str(rot.heure_debut),
                'heure_fin': str(rot.heure_fin),
                'heures_travaillees': float(rot.heures_travaillees),
                'est_dimanche': rot.est_dimanche,
                'est_jour_ferie': est_ferie,
                'type_jour_ferie': type_jour_ferie,
                'est_extension': rot.est_extension,
                'remplace_employe_nom': rot.remplace_employe.surnom if rot.remplace_employe else None,
            })

        return JsonResponse({
            'success': True,
            'rotations': rotations,
            'count': len(rotations)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def api_heures_supplementaires(request):
    """
    API pour récupérer les heures supplémentaires d'un gardien

    GET /api/gardiens/heures-supplementaires/?employe_id=...&mois=...&annee=...
    """
    try:
        allowed_guardian_ids = _get_allowed_guardian_ids(request.user)
        employe_id = request.GET.get('employe_id')
        mois = request.GET.get('mois')
        annee = request.GET.get('annee')

        if not all([employe_id, mois, annee]):
            return JsonResponse({
                'success': False,
                'error': 'employe_id, mois et annee sont obligatoires'
            }, status=400)
        if employe_id not in allowed_guardian_ids:
            return JsonResponse({
                'success': False,
                'error': 'Acces non autorise a ce gardien'
            }, status=403)

        mois = int(mois)
        annee = int(annee)

        # Calculer les heures pour ce mois
        heures_supp = HeuresSupplementairesGardien.calculer_pour_mois(
            employe_id, mois, annee
        )

        return JsonResponse({
            'success': True,
            'heures_supplementaires': {
                'employe_id': str(heures_supp.employe.id),
                'employe_nom': heures_supp.employe.surnom or heures_supp.employe.nom,
                'mois': heures_supp.mois,
                'annee': heures_supp.annee,
                'heures_normales': float(heures_supp.heures_normales),
                'heures_supplementaires': float(heures_supp.heures_supplementaires),
                'heures_dimanche': float(heures_supp.heures_dimanche),
                'heures_jours_feries': float(heures_supp.heures_jours_feries),
                'heures_extensions': float(heures_supp.heures_extensions),
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def gestion_gardiens(request):
    """
    Page web de gestion des gardiens

    Affiche une interface complète pour :
    - Visualiser les rotations
    - Générer de nouvelles rotations
    - Créer des congés avec extension automatique
    - Consulter les heures supplémentaires
    """
    from apps.employees.models import Contrat

    gardiens_qs = _get_allowed_guardians_queryset(request.user).order_by('surnom', 'nom')

    gardiens_data = []
    for gardien in gardiens_qs:
        contrat_actif = Contrat.objects.filter(
            employe_id=gardien.id,
            fin_contrat__isnull=True,
        ).order_by('-debut_contrat').first()
        if not contrat_actif:
            contrat_actif = Contrat.objects.filter(
                employe_id=gardien.id,
            ).order_by('-debut_contrat').first()

        gardiens_data.append({
            'id': str(gardien.id),
            'nom': gardien.surnom or gardien.nom,
            'contrat_id': str(contrat_actif.id) if contrat_actif else None,
            'salaire_brut_base': float(contrat_actif.salaire_brut_base or 0) if contrat_actif else 0,
            'personnes_charge': gardien.personnes_charge or 0,
        })

    context = {
        'gardiens': gardiens_data,
    }
    return render(request, 'planning/gestion_gardiens.html', context)


def impression_calendrier_gardiens(request):
    """
    Vue d'impression pour le calendrier mensuel des gardiens
    Inspirée de impression_gestion_volumetrique
    """
    # Récupérer les paramètres
    mois = int(request.GET.get('mois', timezone.now().month))
    annee = int(request.GET.get('annee', timezone.now().year))

    allowed_guardian_ids = _get_allowed_guardian_ids(request.user)

    # Timezone Madagascar
    tz_madagascar = pytz.timezone('Indian/Antananarivo')

    # Calculer le nombre de jours du mois
    import calendar
    nb_jours = calendar.monthrange(annee, mois)[1]

    # Récupérer les rotations du mois
    date_debut = date(annee, mois, 1)
    date_fin = date(annee, mois, nb_jours)

    rotations = RotationGardien.objects.filter(
        employe_id__in=allowed_guardian_ids,
        date__gte=date_debut,
        date__lte=date_fin
    ).select_related('employe').order_by('date', 'employe__surnom')

    # Organiser les rotations par gardien et par jour
    rotations_par_gardien = {guard_id: {} for guard_id in allowed_guardian_ids}

    # Initialiser les statistiques par gardien
    HEURES_NORMALES_MOIS = Decimal('240')
    guardians_by_id = {
        str(g.id): (g.surnom or g.nom)
        for g in _get_allowed_guardians_queryset(request.user)
    }
    stats = {
        guard_id: {
            'feries': 0,
            'dimanches': 0,
            'jours': 0,
            'nuits': 0,
            'etendus': 0,
            'heures_total': Decimal('0'),
            'remplacement': Decimal('0'),
            'heures_feries': Decimal('0'),
            'heures_nuit': Decimal('0'),
            'heures_dimanche': Decimal('0'),
            'heures_1er_mai': Decimal('0'),
            'nom': guardians_by_id.get(guard_id, guard_id)
        }
        for guard_id in allowed_guardian_ids
    }

    for rot in rotations:
        employe_id = str(rot.employe.id)
        jour = rot.date.day
        est_ferie = _get_effective_holiday_flag(rot)

        # Organiser par gardien et jour
        if employe_id in rotations_par_gardien:
            rotations_par_gardien[employe_id][jour] = {
                'shift_type': rot.shift_type,
                'heure_debut': rot.heure_debut.strftime('%H:%M') if rot.heure_debut else '',
                'heure_fin': rot.heure_fin.strftime('%H:%M') if rot.heure_fin else '',
                'heures_travaillees': float(rot.heures_travaillees) if rot.heures_travaillees else 0,
                'est_dimanche': rot.est_dimanche,
                'est_jour_ferie': est_ferie,
                'est_extension': rot.est_extension,
            }

            # Calculer les statistiques
            if rot.shift_type != 'conge':
                is_extension = rot.shift_type == 'etendu' or rot.est_extension
                if is_extension:
                    stats[employe_id]['etendus'] += 1
                elif rot.shift_type == 'jour':
                    stats[employe_id]['jours'] += 1
                elif rot.shift_type == 'nuit':
                    stats[employe_id]['nuits'] += 1

                shift_hours = Decimal('24') if is_extension else {
                    'jour': Decimal('10'),
                    'nuit': Decimal('14'),
                }.get(rot.shift_type, Decimal(str(rot.heures_travaillees or 0)))
                if rot.shift_type == 'nuit' or is_extension:
                    stats[employe_id]['heures_nuit'] += Decimal('14')

                if rot.date.month == 5 and rot.date.day == 1:
                    stats[employe_id]['heures_1er_mai'] += shift_hours
                elif est_ferie:
                    stats[employe_id]['heures_feries'] += shift_hours
                elif rot.est_dimanche:
                    stats[employe_id]['heures_dimanche'] += shift_hours

            # CRITICAL: Ne compter les jours feries QUE si le gardien travaille (pas en conge)
            if est_ferie and rot.shift_type != 'conge':
                stats[employe_id]['feries'] += 1
            if rot.est_dimanche and rot.shift_type != 'conge':
                stats[employe_id]['dimanches'] += 1

    for stat in stats.values():
        heures_total = (stat['jours'] * 10) + (stat['nuits'] * 14) + (stat['etendus'] * 24)
        stat['heures_total'] = Decimal(str(heures_total))
        if stat['heures_total'] > HEURES_NORMALES_MOIS:
            stat['remplacement'] = stat['heures_total'] - HEURES_NORMALES_MOIS
        else:
            stat['remplacement'] = Decimal('0')
        stat['heures_total'] = float(stat['heures_total'])
        stat['remplacement'] = float(stat['remplacement'])
        stat['heures_feries'] = float(stat['heures_feries'])
        stat['heures_nuit'] = float(stat['heures_nuit'])
        stat['heures_dimanche'] = float(stat['heures_dimanche'])
        stat['heures_1er_mai'] = float(stat['heures_1er_mai'])

    # Noms des mois en français
    noms_mois = [
        '', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
        'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'
    ]

    context = {
        'mois': mois,
        'annee': annee,
        'mois_nom': noms_mois[mois],
        'nb_jours': nb_jours,
        'jours_liste': list(range(1, nb_jours + 1)),  # Liste des jours pour le template
        'jours_liste_1': list(range(1, min(16, nb_jours + 1))),
        'jours_liste_2': list(range(16, nb_jours + 1)) if nb_jours > 15 else [],
        'rotations_par_gardien': rotations_par_gardien,
        'stats': stats,
        'gardiens': [
            {'id': guard_id, 'nom': stats[guard_id]['nom']}
            for guard_id in allowed_guardian_ids
        ],
        'date_impression': datetime.now().strftime('%d/%m/%Y %H:%M'),
    }

    return render(request, 'planning/impression_calendrier_gardiens.html', context)
