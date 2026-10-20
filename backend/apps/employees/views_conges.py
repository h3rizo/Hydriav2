"""
Vues pour la gestion des congés et permissions.
"""
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Sum, Q, Value
from django.db.models.functions import Coalesce, NullIf
from django.utils import timezone
from decimal import Decimal
from datetime import datetime, date, timedelta
import calendar
import json
import unicodedata

from .models import Employe, HierarchieEmploye
from .models_conges import TypePermission, DemandeConge, SoldeConge, JourFerie
from apps.planning.models import Planning, Activite, PlanningEmploye
from apps.accounting.models import DiameXTemporaire
from .utils_conges import (
    get_jour_ferie_label as get_jour_ferie_label_util,
    get_jours_feries,
    get_jours_feries_records,
    valider_dates_repos,
    valider_dates_jour_ferie,
    calculer_nb_jours as calculer_nb_jours_avec_demi
)


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


def _filter_demandes_conges_by_scope(queryset, user):
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
        return queryset.filter(employe__base__organisation_id=organisation_id)

    base_id = getattr(employe, 'base_id', None)
    if not base_id:
        return queryset.none()
    return queryset.filter(employe__base_id=base_id)


def _filter_plannings_by_scope(queryset, user):
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
        return queryset.filter(employe__base__organisation_id=organisation_id)

    base_id = getattr(employe, 'base_id', None)
    if not base_id:
        return queryset.none()
    return queryset.filter(employe__base_id=base_id)


def _get_planning_activity_label(planning):
    if getattr(planning, 'fiche_poste', None) and getattr(planning.fiche_poste, 'tache', None):
        return str(planning.fiche_poste.tache).strip()
    if getattr(planning, 'type_activite', None) and getattr(planning.type_activite, 'nomtype', None):
        return str(planning.type_activite.nomtype).strip()
    remarque = _normalize_poste_name(getattr(planning, 'remarque', ''))
    if 'jour ferie' in remarque:
        return 'Jour férié'
    return ''


def _find_shared_absence_planning(date_value, employe, activity_label):
    if not employe:
        return None

    target_label = _normalize_poste_name(activity_label)
    if not target_label:
        return None

    candidates = (
        Planning.objects.filter(
            date__date=date_value,
            ouvrage__isnull=True,
        )
        .select_related('fiche_poste', 'type_activite', 'employe')
        .order_by('-estvalide', 'created_at', 'date', 'id')
    )

    for candidate in candidates:
        candidate_label = _normalize_poste_name(_get_planning_activity_label(candidate))
        if candidate_label == target_label:
            return candidate
    return None


def _get_self_and_subordinate_ids(user):
    employe = getattr(user, 'employe', None)
    if not employe or not getattr(employe, 'id', None):
        return []

    today = timezone.localdate()
    visited = set()
    result_ids = set()
    frontier = {str(employe.id)}

    while frontier:
        current_ids = {
            uuid_str for uuid_str in frontier
            if uuid_str and uuid_str not in visited
        }
        if not current_ids:
            break

        visited.update(current_ids)
        result_ids.update(current_ids)

        child_ids = set(
            HierarchieEmploye.objects.filter(
                superieur_id__in=current_ids,
                date_debut__lte=today,
            ).filter(
                Q(date_fin__isnull=True) | Q(date_fin__gte=today)
            ).values_list('employe_id', flat=True)
        )
        frontier = {str(child_id) for child_id in child_ids if child_id and str(child_id) not in visited}

    return list(result_ids)


def _get_jour_ferie_label(jour_ferie):
    return get_jour_ferie_label_util(jour_ferie)


# ==================== TYPES DE PERMISSIONS ====================

@login_required
def types_permissions_list(request):
    """Page de gestion des types de permissions"""
    types_permissions = TypePermission.objects.filter(actif=True).order_by('evenement')

    context = {
        'types_permissions': types_permissions,
        'title': 'Types de Permissions'
    }
    return render(request, 'employees/types_permissions_list.html', context)


@csrf_exempt
@require_http_methods(["GET"])
def api_types_permissions_list(request):
    """API pour lister les types de permissions"""
    try:
        types_permissions = TypePermission.objects.all().order_by('evenement')

        types_list = []
        for type_perm in types_permissions:
            types_list.append({
                'id': str(type_perm.id),
                'evenement': type_perm.evenement,
                'nb_jours_accordes': type_perm.nb_jours_accordes,
                'description': type_perm.description or '',
                'actif': type_perm.actif
            })

        return JsonResponse({
            'success': True,
            'types': types_list
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_type_permission_create(request):
    """API pour créer un type de permission"""
    try:
        data = json.loads(request.body)

        type_permission = TypePermission.objects.create(
            evenement=data['evenement'],
            nb_jours_accordes=int(data['nb_jours_accordes']),
            description=data.get('description', ''),
            actif=True
        )

        return JsonResponse({
            'success': True,
            'message': 'Type de permission créé avec succès',
            'type_permission': {
                'id': str(type_permission.id),
                'evenement': type_permission.evenement,
                'nb_jours_accordes': type_permission.nb_jours_accordes
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_type_permission_update(request, type_id):
    """API pour modifier un type de permission"""
    try:
        type_permission = get_object_or_404(TypePermission, id=type_id)
        data = json.loads(request.body)

        type_permission.evenement = data['evenement']
        type_permission.nb_jours_accordes = int(data['nb_jours_accordes'])
        type_permission.description = data.get('description', '')
        type_permission.actif = bool(data.get('actif', True))
        type_permission.save()

        return JsonResponse({
            'success': True,
            'message': 'Type de permission modifié avec succès'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_type_permission_delete(request, type_id):
    """API pour désactiver un type de permission"""
    try:
        type_permission = get_object_or_404(TypePermission, id=type_id)
        type_permission.actif = False
        type_permission.save()

        return JsonResponse({
            'success': True,
            'message': 'Type de permission désactivé avec succès'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# ==================== JOURS FERIES ====================

@login_required
def jours_feries_list(request):
    """Page de gestion des jours feries."""
    years = {timezone.localdate().year}
    for fallback_year in (timezone.localdate().year - 1, timezone.localdate().year + 1):
        if fallback_year > 0:
            years.add(fallback_year)
    for candidate_year in list(years):
        for record in get_jours_feries_records(candidate_year):
            years.add(record['date'].year)
    years = sorted(years, reverse=True)
    selected_year = request.GET.get('annee')

    context = {
        'years': years,
        'selected_year': selected_year or '',
        'title': 'Jours feries',
    }
    return render(request, 'employees/jours_feries_list.html', context)


@csrf_exempt
@require_http_methods(["GET"])
def api_jours_feries_list(request):
    """API pour lister les jours feries."""
    try:
        annee = (request.GET.get('annee') or '').strip()
        jours = []

        if annee.isdigit():
            for record in get_jours_feries_records(int(annee)):
                jours.append({
                    'id': str(record['id']) if record.get('id') else '',
                    'date': record['date'].isoformat(),
                    'date_display': record['date'].strftime('%d/%m/%Y'),
                    'nom': record['nom'],
                    'description': record.get('description', '') or '',
                    'actif': bool(record.get('actif', True)),
                    'type_jour': record.get('type_jour') or 'officiel',
                })
        else:
            try:
                queryset = JourFerie.objects.all().order_by('date')
                jours = [
                    {
                        'id': str(jour.id),
                        'date': jour.date.isoformat(),
                        'date_display': jour.date.strftime('%d/%m/%Y'),
                        'nom': jour.nom,
                        'description': jour.description or '',
                        'actif': jour.actif,
                        'type_jour': jour.type_jour,
                    }
                    for jour in queryset
                ]
            except Exception:
                years = [timezone.localdate().year - 1, timezone.localdate().year, timezone.localdate().year + 1]
                for year in years:
                    for record in get_jours_feries_records(year):
                        jours.append({
                            'id': str(record['id']) if record.get('id') else '',
                            'date': record['date'].isoformat(),
                            'date_display': record['date'].strftime('%d/%m/%Y'),
                            'nom': record['nom'],
                            'description': record.get('description', '') or '',
                            'actif': bool(record.get('actif', True)),
                            'type_jour': record.get('type_jour') or 'officiel',
                        })

        return JsonResponse({
            'success': True,
            'jours_feries': jours,
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_jour_ferie_create(request):
    """API pour creer un jour ferie."""
    try:
        data = json.loads(request.body)
        type_jour = data.get('type_jour') or JourFerie.TYPE_OFFICIEL
        if type_jour not in dict(JourFerie.TYPE_CHOICES):
            type_jour = JourFerie.TYPE_OFFICIEL
        jour = JourFerie.objects.create(
            date=datetime.strptime(data['date'], '%Y-%m-%d').date(),
            nom=(data.get('nom') or '').strip(),
            type_jour=type_jour,
            description=data.get('description', ''),
            actif=bool(data.get('actif', True)),
        )
        return JsonResponse({
            'success': True,
            'message': 'Jour ferie cree avec succes',
            'jour_ferie': {
                'id': str(jour.id),
                'date': jour.date.isoformat(),
                'nom': jour.nom,
                'type_jour': jour.type_jour,
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_jour_ferie_update(request, jour_ferie_id):
    """API pour modifier un jour ferie."""
    try:
        jour = get_object_or_404(JourFerie, id=jour_ferie_id)
        data = json.loads(request.body)

        type_jour = data.get('type_jour') or JourFerie.TYPE_OFFICIEL
        if type_jour not in dict(JourFerie.TYPE_CHOICES):
            type_jour = JourFerie.TYPE_OFFICIEL

        jour.date = datetime.strptime(data['date'], '%Y-%m-%d').date()
        jour.nom = (data.get('nom') or '').strip()
        jour.type_jour = type_jour
        jour.description = data.get('description', '')
        jour.actif = bool(data.get('actif', True))
        jour.save()

        return JsonResponse({
            'success': True,
            'message': 'Jour ferie modifie avec succes',
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_jour_ferie_delete(request, jour_ferie_id):
    """API pour desactiver un jour ferie."""
    try:
        jour = get_object_or_404(JourFerie, id=jour_ferie_id)
        jour.actif = False
        jour.save(update_fields=['actif', 'updated_at'])

        return JsonResponse({
            'success': True,
            'message': 'Jour ferie desactive avec succes',
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
        }, status=500)


# ==================== DEMANDES DE CONGES ====================

@login_required
def demandes_conges_list(request):
    """Page de liste et gestion des demandes de congés"""
    from apps.organization.models import Organisation

    subordinate_ids = _get_self_and_subordinate_ids(request.user)
    if subordinate_ids:
        employes = Employe.objects.filter(id__in=subordinate_ids).order_by('nom', 'prenom')
    else:
        current_employe = getattr(request.user, 'employe', None)
        if current_employe and getattr(current_employe, 'id', None):
            employes = Employe.objects.filter(id=current_employe.id).order_by('nom', 'prenom')
        else:
            employes = _filter_employes_by_scope(Employe.objects.all(), request.user).order_by('nom', 'prenom')[:50]
    organisations = Organisation.objects.all().order_by('nom_organisation')
    types_permissions = TypePermission.objects.filter(actif=True).order_by('evenement')
    employes_json = json.dumps([
        {
            'id': str(employe.id),
            'nom': getattr(employe, 'nom', '') or '',
            'prenom': getattr(employe, 'prenom', '') or '',
            'surnom': getattr(employe, 'surnom', '') or '',
        }
        for employe in employes
    ])
    jours_feries_options = []
    repos_options = []
    for annee in [timezone.localdate().year, timezone.localdate().year + 1]:
        for jour_ferie in get_jours_feries(annee):
            jours_feries_options.append({
                'value': jour_ferie.strftime('%Y-%m-%d'),
                'label': f"{jour_ferie.strftime('%d/%m/%Y')} - {_get_jour_ferie_label(jour_ferie)}",
                'month': jour_ferie.strftime('%Y-%m'),
            })
        current_date = date(annee, 1, 1)
        while current_date.year == annee:
            if current_date.weekday() in (5, 6):
                repos_options.append({
                    'value': current_date.strftime('%Y-%m-%d'),
                    'label': (
                        f"{current_date.strftime('%d/%m/%Y')} - "
                        f"{'Samedi' if current_date.weekday() == 5 else 'Dimanche'}"
                    ),
                    'month': current_date.strftime('%Y-%m'),
                })
            current_date += timedelta(days=1)

    context = {
        'employes': employes,
        'employes_json': employes_json,
        'organisations': organisations,
        'types_permissions': types_permissions,
        'jours_feries_options': jours_feries_options,
        'repos_options': repos_options,
        'title': 'Demandes de Congés'
    }
    return render(request, 'employees/demandes_conges_list.html', context)


@csrf_exempt
@require_http_methods(["GET"])
def api_demandes_conges_list(request):
    """API pour récupérer les demandes de congés (DemandeConge + Planning)"""
    try:
        # Filtres
        employe_id = request.GET.get('employe_id')
        type_demande = request.GET.get('type')
        statut_filter = request.GET.get('statut')
        organisation_id = request.GET.get('organisation_id')

        # 1. Récupérer les demandes en workflow (DemandeConge)
        queryset_demandes = DemandeConge.objects.select_related(
            'employe', 'employe__base__organisation', 'type_permission'
        ).order_by('-date_debut')
        queryset_demandes = _filter_demandes_conges_by_scope(queryset_demandes, request.user)

        if employe_id and employe_id != '':
            queryset_demandes = queryset_demandes.filter(employe_id=employe_id)
        if organisation_id and organisation_id != '':
            queryset_demandes = queryset_demandes.filter(employe__base__organisation_id=organisation_id)
        if type_demande:
            queryset_demandes = queryset_demandes.filter(type_demande=type_demande)
        if statut_filter:
            queryset_demandes = queryset_demandes.filter(statut=statut_filter)

        demandes = []
        # Calculer les soldes actuels une seule fois par employé
        soldes_employes = {}

        for demande in queryset_demandes:
            employe_id = str(demande.employe.id)

            # Calculer le solde actuel si pas déjÃ  fait pour cet employé
            if employe_id not in soldes_employes:
                soldes_employes[employe_id] = {
                    'conges': float(calculer_solde_conge_actuel(demande.employe)),
                    'permissions': calculer_solde_permission_actuel(demande.employe)
                }

            demandes.append({
                'id': str(demande.id),
                'employe_id': employe_id,
                'employe_nom': f"{demande.employe.nom} {demande.employe.prenom}",
                'type_demande': demande.type_demande,
                'type_demande_display': demande.get_type_demande_display(),
                'date_debut': demande.date_debut.isoformat(),
                'date_fin': demande.date_fin.isoformat(),
                'nb_jours_demandes': demande.nb_jours_demandes,
                'est_demi_journee': demande.est_demi_journee,
                'motif': demande.motif or '',
                'reliquat_conge_avant': float(demande.reliquat_conge_avant),
                'reliquat_permission_avant': demande.reliquat_permission_avant,
                'reliquat_conge_actuel': soldes_employes[employe_id]['conges'],
                'reliquat_permission_actuel': soldes_employes[employe_id]['permissions'],
                'statut': demande.statut,
                'statut_display': demande.get_statut_display(),
                'inscrit_planning': demande.inscrit_planning,
            })

        return JsonResponse({
            'success': True,
            'demandes': demandes,
            'count': len(demandes)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def calculer_nb_jours_ouvres(date_debut, date_fin):
    """Calcule le nombre de jours ouvrés entre deux dates (excluant week-ends)"""
    nb_jours = 0
    current_date = date_debut

    while current_date <= date_fin:
        # Exclure samedi (5) et dimanche (6)
        if current_date.weekday() < 5:
            nb_jours += 1
        current_date += timedelta(days=1)

    return nb_jours


def calculer_solde_conge_actuel(employe):
    """Calcule le solde de congés actuel d'un employé"""
    # Récupérer le dernier solde enregistré
    dernier_solde = SoldeConge.objects.filter(
        employe=employe
    ).order_by('-annee', '-mois').first()

    if dernier_solde:
        return dernier_solde.solde_conges_fin
    else:
        # Pas d'historique, retourner 0
        return Decimal('0')


def calculer_solde_permission_actuel(employe):
    """Calcule le solde de permissions actuel pour l'année en cours"""
    annee_courante = datetime.now().year

    # Total des permissions utilisées cette année
    total_utilise = DemandeConge.objects.filter(
        employe=employe,
        type_demande='permission',
        statut__in=['validee_directeur', 'inscrite_planning'],
        date_debut__year=annee_courante
    ).aggregate(total=Sum('nb_jours_demandes'))['total'] or 0

    # Maximum autorisé : 10 jours par an
    return 10 - total_utilise


@csrf_exempt
@require_http_methods(["GET"])
def api_jours_feries_planning_employe(request):
    """Retourne les jours déjà marqués Jour férié/Repos dans le planning d'un employé."""
    try:
        employe_id = request.GET.get('employe_id')
        planning_type = (request.GET.get('type') or 'jour_ferie').strip().lower()
        if not employe_id:
            return JsonResponse({
                'success': False,
                'error': 'employe_id manquant'
            }, status=400)

        employe = get_object_or_404(Employe, id=employe_id)
        allowed_employe_ids = set(_get_self_and_subordinate_ids(request.user))
        if str(employe.id) not in allowed_employe_ids:
            return JsonResponse({
                'success': False,
                'error': 'Accès refusé'
            }, status=403)

        activite_nom = 'Repos' if planning_type == 'repos' else 'Jour férié'
        matching_planning_ids = [
            planning.id
            for planning in Planning.objects.filter(
                date__year=timezone.now().year,
            ).select_related('fiche_poste', 'type_activite')
            if _normalize_poste_name(_get_planning_activity_label(planning)) == _normalize_poste_name(activite_nom)
        ]
        owner_dates = list(
            Planning.objects.filter(
                id__in=matching_planning_ids,
                employe=employe,
            ).values_list('date', flat=True)
        )
        participant_dates = list(
            PlanningEmploye.objects.filter(
                employee=employe,
                planning_id__in=matching_planning_ids,
            ).values_list('planning__date', flat=True)
        )
        ferie_dates = owner_dates + participant_dates
        ferie_dates = [
            (dt.date() if hasattr(dt, 'date') else dt).strftime('%Y-%m-%d')
            for dt in ferie_dates if dt
        ]

        return JsonResponse({
            'success': True,
            'dates': ferie_dates
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_demande_conge_create(request):
    """API pour créer une demande de congé"""
    try:
        data = json.loads(request.body)

        employe = get_object_or_404(Employe, id=data['employe_id'])
        allowed_employe_ids = set(_get_self_and_subordinate_ids(request.user))
        if str(employe.id) not in allowed_employe_ids:
            return JsonResponse({
                'success': False,
                'error': 'Accès refusé pour cet employé.'
            }, status=403)
        type_demande = data['type_demande']

        if type_demande == 'repos_medical':
            return JsonResponse({
                'success': False,
                'error': 'Le repos médical se gère dans le workflow Frais médicaux.'
            }, status=400)

        # Parser les dates
        if type_demande == 'jour_ferie' and data.get('jour_ferie_date'):
            selected_jour_ferie = datetime.strptime(data['jour_ferie_date'], '%Y-%m-%d').date()
            date_debut = selected_jour_ferie
            date_fin = selected_jour_ferie
        else:
            date_debut = datetime.strptime(data['date_debut'], '%Y-%m-%d').date()
            date_fin = datetime.strptime(data['date_fin'], '%Y-%m-%d').date()

        # Validations spécifiques selon le type
        if type_demande == 'repos':
            # Valider que repos respectent les règles (Sam/Dim pour non-journaliers)
            valider_dates_repos(employe, date_debut, date_fin)
        elif type_demande == 'jour_ferie':
            valider_dates_jour_ferie(date_debut, date_fin)

        # Vérifier si c'est une demi-journée
        est_demi_journee = data.get('est_demi_journee', False) and type_demande == 'conge_demi'

        # Calculer le nombre de jours
        if type_demande in ['conge', 'conge_demi', 'repos_medical']:
            # Pour ces types, utiliser la fonction avec support demi-journée
            nb_jours = calculer_nb_jours_avec_demi(date_debut, date_fin, est_demi_journee)
        elif type_demande == 'permission':
            # Permissions utilisent calcul jours ouvrés
            nb_jours = calculer_nb_jours_ouvres(date_debut, date_fin)
        else:
            # Repos et jours fériés : tous les jours
            nb_jours = (date_fin - date_debut).days + 1

        # Récupérer les soldes actuels
        reliquat_conge = calculer_solde_conge_actuel(employe)
        reliquat_permission = calculer_solde_permission_actuel(employe)

        # Gérer le fichier justificatif médical si présent
        justificatif_medical = None
        if type_demande == 'repos_medical' and request.FILES.get('justificatif_medical'):
            justificatif_medical = request.FILES['justificatif_medical']

        # Pour les repos, créer directement les entrées Planning et valider automatiquement
        if type_demande == 'jour_ferie':
            import pytz
            from apps.employees.views_gardiens import _resolve_planning_targets_for_activity

            tz_madagascar = pytz.timezone('Indian/Antananarivo')
            activite_ferie = Activite.objects.filter(nom='Jour férié').first()
            if not activite_ferie:
                return JsonResponse({
                    'success': False,
                    'error': 'Activité "Jour férié" non trouvée dans la base de données'
                }, status=500)

            date_planning = tz_madagascar.localize(
                datetime.combine(date_debut, datetime.min.time())
            )
            _, fiche_poste_ferie, type_activite_ferie = _resolve_planning_targets_for_activity('Jour f')
            if not type_activite_ferie and activite_ferie.type_activite_id:
                type_activite_ferie = activite_ferie.type_activite

            existing_same_employee = Planning.objects.filter(
                employe=employe,
                date__date=date_debut
            ).first()
            if existing_same_employee:
                return JsonResponse({
                    'success': False,
                    'error': "Cet employé a déjà un planning sur cette date."
                }, status=400)

            planning_jour_ferie = _find_shared_absence_planning(
                date_debut,
                employe,
                'Jour férié',
            )

            if planning_jour_ferie:
                if planning_jour_ferie.employe_id == employe.id:
                    return JsonResponse({
                        'success': False,
                        'error': "Cet employé est déjà propriétaire du jour férié à cette date."
                    }, status=400)

                existing_participation = PlanningEmploye.objects.filter(
                    employee=employe,
                    planning=planning_jour_ferie,
                ).exists()
                if existing_participation:
                    return JsonResponse({
                        'success': False,
                        'error': "Cet employé est déjà participant du jour férié à cette date."
                    }, status=400)

                PlanningEmploye.objects.get_or_create(
                    planning=planning_jour_ferie,
                    employee=employe,
                    defaults={'is_present': True}
                )
                return JsonResponse({
                    'success': True,
                    'message': 'Employé ajouté comme participant au jour férié existant.',
                    'planning_id': str(planning_jour_ferie.id),
                    'mode': 'participant'
                })

            planning_kwargs = {
                'employe': employe,
                'date': date_planning,
                'estvalide': True,
                'remarque': data.get('motif') or 'Jour férié inscrit depuis le modal',
            }
            if fiche_poste_ferie:
                planning_kwargs['fiche_poste'] = fiche_poste_ferie
            if type_activite_ferie:
                planning_kwargs['type_activite'] = type_activite_ferie

            planning = Planning.objects.create(
                **planning_kwargs
            )
            return JsonResponse({
                'success': True,
                'message': 'Jour férié inscrit automatiquement dans le planning validé.',
                'planning_id': str(planning.id),
                'mode': 'owner'
            })

        if type_demande == 'repos':
            import pytz
            from apps.employees.views_gardiens import _resolve_planning_targets_for_activity

            tz_madagascar = pytz.timezone('Indian/Antananarivo')

            # Récupérer l'activité "Repos"
            activite_repos = Activite.objects.filter(nom='Repos').first()
            if not activite_repos:
                return JsonResponse({
                    'success': False,
                    'error': 'Activité "Repos" non trouvée dans la base de données'
                }, status=500)

            _, fiche_poste_repos, type_activite_repos = _resolve_planning_targets_for_activity('Repos')
            if not type_activite_repos and activite_repos.type_activite_id:
                type_activite_repos = activite_repos.type_activite

            existing_same_employee = Planning.objects.filter(
                employe=employe,
                date__date=date_debut
            ).first()
            if existing_same_employee:
                return JsonResponse({
                    'success': False,
                    'error': "Cet employé a déjà un planning sur cette date."
                }, status=400)

            # Créer la demande avec statut validé directement
            demande = DemandeConge.objects.create(
                employe=employe,
                type_demande=type_demande,
                date_debut=date_debut,
                date_fin=date_fin,
                nb_jours_demandes=nb_jours,
                est_demi_journee=False,
                motif=data.get('motif', 'Repos auto-validé'),
                reliquat_conge_avant=reliquat_conge,
                reliquat_permission_avant=reliquat_permission,
                statut='validee_directeur',  # Statut validé automatiquement pour repos
                created_by=request.user
            )

            # Créer les entrées Planning pour chaque jour
            plannings_crees = []
            current_date = date_debut
            while current_date <= date_fin:
                shared_planning = _find_shared_absence_planning(
                    current_date,
                    employe,
                    'Repos',
                )

                if shared_planning:
                    if shared_planning.employe_id == employe.id:
                        return JsonResponse({
                            'success': False,
                            'error': "Cet employé est déjà propriétaire du repos à cette date."
                        }, status=400)

                    existing_participation = PlanningEmploye.objects.filter(
                        employee=employe,
                        planning=shared_planning,
                    ).exists()
                    if existing_participation:
                        return JsonResponse({
                            'success': False,
                            'error': "Cet employé est déjà participant du repos à cette date."
                        }, status=400)

                    PlanningEmploye.objects.get_or_create(
                        planning=shared_planning,
                        employee=employe,
                        defaults={'is_present': True}
                    )
                    plannings_crees.append(current_date.strftime('%Y-%m-%d'))
                    current_date += timedelta(days=1)
                    continue

                date_planning = tz_madagascar.localize(
                    datetime.combine(current_date, datetime.min.time())
                )
                planning_kwargs = {
                    'employe': employe,
                    'date': date_planning,
                    'estvalide': True,
                    'remarque': data.get('motif') or 'Repos inscrit depuis le modal',
                }
                if fiche_poste_repos:
                    planning_kwargs['fiche_poste'] = fiche_poste_repos
                if type_activite_repos:
                    planning_kwargs['type_activite'] = type_activite_repos

                Planning.objects.create(**planning_kwargs)
                plannings_crees.append(current_date.strftime('%Y-%m-%d'))

                current_date += timedelta(days=1)

            return JsonResponse({
                'success': True,
                'message': f'Repos créé et validé automatiquement pour {len(plannings_crees)} jour(s)',
                'demande_id': str(demande.id),
                'nb_jours_calcules': nb_jours,
                'plannings_crees': plannings_crees
            })

        # Pour tous les autres types, créer avec workflow normal
        demande = DemandeConge.objects.create(
            employe=employe,
            type_demande=type_demande,
            date_debut=date_debut,
            date_fin=date_fin,
            nb_jours_demandes=nb_jours,
            est_demi_journee=est_demi_journee,
            type_permission_id=data.get('type_permission_id') if type_demande == 'permission' else None,
            motif=data.get('motif', ''),
            justificatif_medical=justificatif_medical,
            reliquat_conge_avant=reliquat_conge,
            reliquat_permission_avant=reliquat_permission,
            statut='brouillon',
            created_by=request.user
        )

        return JsonResponse({
            'success': True,
            'message': 'Demande de congé créée avec succès',
            'demande_id': str(demande.id),
            'nb_jours_calcules': nb_jours
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def api_demande_conge_detail(request, demande_id):
    """API pour récupérer les détails d'une demande de congé"""
    try:
        demande = get_object_or_404(DemandeConge, id=demande_id)

        demande_data = {
            'id': str(demande.id),
            'employe_nom': f"{demande.employe.nom} {demande.employe.prenom}",
            'type_demande': demande.type_demande,
            'type_demande_display': demande.get_type_demande_display(),
            'date_debut': demande.date_debut.strftime('%Y-%m-%d'),
            'date_fin': demande.date_fin.strftime('%Y-%m-%d'),
            'nb_jours_demandes': demande.nb_jours_demandes,
            'est_demi_journee': demande.est_demi_journee,
            'motif': demande.motif,
            'justificatif_medical_url': demande.justificatif_medical.url if demande.justificatif_medical else None,
            'reliquat_conge_avant': float(demande.reliquat_conge_avant),
            'reliquat_permission_avant': demande.reliquat_permission_avant,
            'statut': demande.statut,
            'statut_display': demande.get_statut_display(),
            'date_demande': demande.date_demande.isoformat() if demande.date_demande else None,
            'commentaire_chef': demande.commentaire_chef or '',
            'validee_par_chef_nom': f"{demande.validee_par_chef.first_name} {demande.validee_par_chef.last_name}" if demande.validee_par_chef else '',
            'date_validation_chef': demande.date_validation_chef.isoformat() if demande.date_validation_chef else None,
            'commentaire_directeur': demande.commentaire_directeur or '',
            'validee_par_directeur_nom': f"{demande.validee_par_directeur.first_name} {demande.validee_par_directeur.last_name}" if demande.validee_par_directeur else '',
            'date_validation_directeur': demande.date_validation_directeur.isoformat() if demande.date_validation_directeur else None,
            'inscrit_planning': demande.inscrit_planning,
            # Informations d'annulation
            'motif_annulation': demande.motif_annulation or '',
            'annulee_par_nom': f"{demande.annulee_par.first_name} {demande.annulee_par.last_name}" if demande.annulee_par else '',
            'date_annulation': demande.date_annulation.isoformat() if demande.date_annulation else None,
            # Informations de report
            'motif_report': demande.motif_report or '',
            'reporte_par_nom': f"{demande.reporte_par.first_name} {demande.reporte_par.last_name}" if demande.reporte_par else '',
            'date_report': demande.date_report.isoformat() if demande.date_report else None,
            'dates_originales': demande.dates_originales or [],
        }

        return JsonResponse({
            'success': True,
            'demande': demande_data
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_demande_conge_soumettre(request, demande_id):
    """API pour soumettre une demande (passer de brouillon Ã  soumise)"""
    try:
        demande = get_object_or_404(DemandeConge, id=demande_id)

        if demande.statut != 'brouillon':
            return JsonResponse({
                'success': False,
                'error': 'Seules les demandes en brouillon peuvent être soumises'
            }, status=400)

        demande.statut = 'soumise'
        demande.date_demande = timezone.now()
        demande.save()

        return JsonResponse({
            'success': True,
            'message': 'Demande soumise avec succès'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_demande_conge_valider_chef(request, demande_id):
    """API pour valider une demande par le chef hiérarchique"""
    try:
        demande = get_object_or_404(DemandeConge, id=demande_id)
        data = json.loads(request.body)

        if not demande.peut_etre_validee_chef:
            return JsonResponse({
                'success': False,
                'error': 'Cette demande ne peut pas être validée par le chef'
            }, status=400)

        demande.statut = 'validee_chef'
        demande.validee_par_chef = request.user
        demande.date_validation_chef = timezone.now()
        demande.commentaire_chef = data.get('commentaire', '')
        demande.save()

        return JsonResponse({
            'success': True,
            'message': 'Demande validée par le chef avec succès'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_demande_conge_valider_directeur(request, demande_id):
    """API pour valider une demande par le directeur"""
    try:
        demande = get_object_or_404(DemandeConge, id=demande_id)
        data = json.loads(request.body)

        if not demande.peut_etre_validee_directeur:
            return JsonResponse({
                'success': False,
                'error': 'Cette demande ne peut pas être validée par le directeur'
            }, status=400)

        demande.statut = 'validee_directeur'
        demande.validee_par_directeur = request.user
        demande.date_validation_directeur = timezone.now()
        demande.commentaire_directeur = data.get('commentaire', '')
        demande.save()

        return JsonResponse({
            'success': True,
            'message': 'Demande validée par le directeur avec succès'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_demande_conge_refuser(request, demande_id):
    """API pour refuser une demande"""
    try:
        demande = get_object_or_404(DemandeConge, id=demande_id)
        data = json.loads(request.body)

        if demande.statut not in ['soumise', 'validee_chef']:
            return JsonResponse({
                'success': False,
                'error': 'Cette demande ne peut plus être refusée'
            }, status=400)

        demande.statut = 'refusee'
        demande.refusee_par = request.user
        demande.date_refus = timezone.now()
        demande.motif_refus = data.get('motif_refus', '')
        demande.save()

        return JsonResponse({
            'success': True,
            'message': 'Demande refusée'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_demande_conge_inscrire_planning(request, demande_id):
    """API pour inscrire une demande validée dans le planning"""
    try:
        demande = get_object_or_404(DemandeConge, id=demande_id)

        if demande.statut != 'validee_directeur':
            return JsonResponse({
                'success': False,
                'error': 'Seules les demandes validées peuvent être inscrites au planning'
            }, status=400)

        if demande.inscrit_planning:
            return JsonResponse({
                'success': False,
                'error': 'Cette demande est déjÃ  inscrite au planning'
            }, status=400)

        # Récupérer l'activité "Congé" ou "Congé demi-journée"
        activite_conge = Activite.objects.filter(nom__icontains='Congé').first()
        if not activite_conge:
            return JsonResponse({
                'success': False,
                'error': 'Activité "Congé" introuvable dans le système'
            }, status=400)
        _, fiche_poste_conge, type_activite_conge = _resolve_planning_targets_for_activity('Cong')
        if not type_activite_conge and activite_conge.type_activite_id:
            type_activite_conge = activite_conge.type_activite

        # Créer les entrées de planning pour chaque jour ouvré
        import pytz
        tz_madagascar = pytz.timezone('Indian/Antananarivo')

        current_date = demande.date_debut
        nb_inscrits = 0
        nb_deja_existants = 0

        while current_date <= demande.date_fin:
            # Seulement les jours ouvrés
            if current_date.weekday() < 5:
                # Créer planning Ã  minuit Madagascar
                date_planning = tz_madagascar.localize(
                    datetime.combine(current_date, datetime.min.time())
                )

                planning_defaults = {
                    'estvalide': True,
                }
                if fiche_poste_conge:
                    planning_defaults['fiche_poste'] = fiche_poste_conge
                if type_activite_conge:
                    planning_defaults['type_activite'] = type_activite_conge

                _, created = Planning.objects.get_or_create(
                    employe=demande.employe,
                    date=date_planning,
                    defaults=planning_defaults
                )
                if created:
                    nb_inscrits += 1
                else:
                    nb_deja_existants += 1

            current_date += timedelta(days=1)

        # Marquer la demande comme inscrite
        demande.inscrit_planning = True
        demande.date_inscription_planning = timezone.now()
        demande.statut = 'inscrite_planning'
        demande.save()

        # Mettre Ã  jour le solde de congés/permissions
        mettre_a_jour_solde_conge(demande)

        return JsonResponse({
            'success': True,
            'message': (
                f'{nb_inscrits} jour(s) de congé inscrit(s) au planning'
                + (
                    f' ({nb_deja_existants} deja present(s))'
                    if nb_deja_existants else ''
                )
            )
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def mettre_a_jour_solde_conge(demande):
    """Met Ã  jour le solde de congés après inscription au planning"""
    # Récupérer ou créer le solde pour le mois/année de début du congé
    annee = demande.date_debut.year
    mois = demande.date_debut.month

    solde, created = SoldeConge.objects.get_or_create(
        employe=demande.employe,
        annee=annee,
        mois=mois,
        defaults={
            'solde_conges_debut': calculer_solde_conge_actuel(demande.employe),
            'solde_permissions_debut': calculer_solde_permission_actuel(demande.employe)
        }
    )

    if demande.type_demande == 'conge':
        solde.consommation_conges += Decimal(str(demande.nb_jours_demandes))
    else:  # permission
        solde.consommation_permissions += demande.nb_jours_demandes

    solde.save()


# ==================== SUIVI DES CONGES ====================

@login_required
def suivi_conges(request):
    """Page de suivi des soldes de congés et permissions"""
    from apps.organization.models import Organisation

    employes_base_qs = Employe.objects.annotate(
        nom_affichage_calc=Coalesce(
            NullIf('surnom', Value('')),
            NullIf('nom', Value('')),
            NullIf('prenom', Value('')),
            Value('')
        )
    )

    subordinate_ids = _get_self_and_subordinate_ids(request.user)
    if subordinate_ids:
        employes = employes_base_qs.filter(
            id__in=subordinate_ids,
            date_debauchage__isnull=True
        ).order_by('nom_affichage_calc', 'nom', 'prenom')
    else:
        current_employe = getattr(request.user, 'employe', None)
        if current_employe and getattr(current_employe, 'id', None):
            employes = employes_base_qs.filter(
                id=current_employe.id,
                date_debauchage__isnull=True
            ).order_by('nom_affichage_calc', 'nom', 'prenom')
        else:
            employes = Employe.objects.none()

    # Plus besoin du filtre organisation dans le template
    user_org = None
    user_is_directeur = False
    if hasattr(request.user, 'employe') and request.user.employe and request.user.employe.base:
        user_org = request.user.employe.base.organisation
        poste_nom = _normalize_poste_name(getattr(getattr(request.user.employe, 'poste', None), 'nom_poste', ''))
        user_is_directeur = poste_nom == 'directeur'

    organisations = Organisation.objects.all().order_by('nom_organisation')

    # Année courante par défaut
    annee_courante = datetime.now().year

    context = {
        'employes': employes,
        'organisations': organisations,
        'annee_courante': annee_courante,
        'user_organisation': user_org,
        'user_is_directeur': user_is_directeur,
        'title': 'Suivi des Congés'
    }
    return render(request, 'employees/suivi_conges.html', context)


@csrf_exempt
@require_http_methods(["GET"])
def api_suivi_conges(request):
    """API pour récupérer le suivi des congés depuis le Planning"""
    try:
        import pytz
        from collections import defaultdict
        from django.db.models import Q

        # Filtres
        employe_id = request.GET.get('employe_id')
        organisation_id = request.GET.get('organisation_id')
        annee = int(request.GET.get('annee', datetime.now().year))

        # Récupérer tous les employés avec leurs congés depuis Planning
        queryset_employes = Employe.objects.filter(
            Q(date_debauchage__isnull=True) | Q(date_debauchage__gte=datetime(annee, 1, 1))
        ).select_related('poste', 'base', 'base__organisation')
        queryset_employes = _filter_employes_by_scope(queryset_employes, request.user)

        if employe_id and employe_id != '':
            queryset_employes = queryset_employes.filter(id=employe_id)
        if organisation_id and organisation_id != '':
            queryset_employes = queryset_employes.filter(base__organisation_id=organisation_id)

        # Récupérer tous les congés de l'année depuis Planning
        plannings_conges = Planning.objects.filter(
            Q(type_activite__nomtype__icontains='cong') |
            Q(fiche_poste__tache__icontains='cong') |
            Q(type_activite__nomtype__icontains='permission') |
            Q(fiche_poste__tache__icontains='permission'),
            date__year=annee
        ).select_related('employe', 'type_activite', 'fiche_poste')
        plannings_conges = _filter_plannings_by_scope(plannings_conges, request.user)

        # Grouper par employé et par mois
        tz_madagascar = pytz.timezone('Indian/Antananarivo')
        conges_par_employe = defaultdict(lambda: defaultdict(lambda: {'conges': 0, 'permissions': 0}))

        for planning in plannings_conges:
            # CRITICAL: Ignorer les plannings sans employé
            if not planning.employe:
                continue

            date_aware = planning.date if planning.date.tzinfo else tz_madagascar.localize(planning.date)
            date_locale = date_aware.astimezone(tz_madagascar).date()

            labels = [
                planning.fiche_poste.tache if planning.fiche_poste else '',
                planning.type_activite.nomtype if planning.type_activite else '',
            ]
            activite_label = ' '.join(label for label in labels if label).lower()
            if not activite_label:
                continue

            is_demi = ('demi' in activite_label) or ('permission' in activite_label)
            mois = date_locale.month

            if is_demi:
                conges_par_employe[planning.employe.id][mois]['permissions'] += 1
            else:
                conges_par_employe[planning.employe.id][mois]['conges'] += 1

        employe_ids = list(queryset_employes.values_list('id', flat=True))
        soldes_janvier = {
            solde.employe_id: solde for solde in SoldeConge.objects.filter(
                employe_id__in=employe_ids,
                annee=annee,
                mois=1
            )
        }
        soldes_decembre_prec = {
            solde.employe_id: solde for solde in SoldeConge.objects.filter(
                employe_id__in=employe_ids,
                annee=annee - 1,
                mois=12
            )
        }

        # Construire la réponse groupée par employé
        employes_data = []
        for employe in queryset_employes:
            historique_mensuel = []
            mois_ecoule = datetime.now().month if annee == datetime.now().year else 12

            solde_janvier = soldes_janvier.get(employe.id)
            solde_decembre_prec = soldes_decembre_prec.get(employe.id)

            if solde_janvier:
                solde_conges_debut_annee = solde_janvier.solde_conges_debut
                solde_permissions_debut_annee = solde_janvier.solde_permissions_debut
            else:
                solde_conges_debut_annee = solde_decembre_prec.solde_conges_fin if solde_decembre_prec else Decimal('0')
                solde_permissions_debut_annee = solde_decembre_prec.solde_permissions_fin if solde_decembre_prec else 10

            solde_conges_courant = Decimal(str(solde_conges_debut_annee))
            solde_permissions_courant = int(solde_permissions_debut_annee)
            total_conges_pris = Decimal('0')
            total_permissions_prises = 0
            total_acquis = Decimal('0')

            # Bornes de présence : pas d'acquisition avant l'embauche ni après le départ
            def _jour(valeur):
                return valeur.date() if isinstance(valeur, datetime) else valeur
            date_embauche = _jour(getattr(employe, 'date_embauche', None))
            date_depart = _jour(getattr(employe, 'date_debauchage', None))

            # Calculer pour chaque mois de l'année
            for mois in range(1, mois_ecoule + 1):
                conges_pris = Decimal(str(conges_par_employe[employe.id][mois]['conges']))
                permissions_prises = conges_par_employe[employe.id][mois]['permissions']
                debut_mois = date(annee, mois, 1)
                fin_mois = date(annee, mois, calendar.monthrange(annee, mois)[1])
                present = (
                    (date_embauche is None or date_embauche <= fin_mois)
                    and (date_depart is None or date_depart >= debut_mois)
                )
                acquisition_conges = Decimal('2.5') if present else Decimal('0')
                total_acquis += acquisition_conges
                solde_conges_debut_mois = solde_conges_courant
                solde_conges_fin_mois = solde_conges_debut_mois + acquisition_conges - conges_pris
                solde_permissions_fin_mois = solde_permissions_courant - permissions_prises

                historique_mensuel.append({
                    'mois': mois,
                    'annee': annee,
                    'conges_pris': float(conges_pris),
                    'permissions_prises': permissions_prises,
                    'acquisition_conges': float(acquisition_conges),
                    'acquisition_permissions': 0,
                    'solde_conges_debut_mois': float(solde_conges_debut_mois),
                    'solde_conges_fin_mois': float(solde_conges_fin_mois),
                    'solde_permissions_fin_mois': int(solde_permissions_fin_mois),
                })

                total_conges_pris += conges_pris
                total_permissions_prises += permissions_prises
                solde_conges_courant = solde_conges_fin_mois
                solde_permissions_courant = solde_permissions_fin_mois

            # Calcul des droits : 2.5 jours par mois de présence (embauche -> départ)
            conges_acquis = total_acquis
            conges_disponibles = solde_conges_courant
            permissions_disponibles = max(solde_permissions_courant, 0)
            has_mouvement = total_conges_pris > 0 or total_permissions_prises > 0
            has_solde_initial = Decimal(str(solde_conges_debut_annee)) > 0

            # Ajouter seulement si l'employé a des mouvements/solde ou si filtré explicitement
            if has_mouvement or has_solde_initial or employe_id:
                employes_data.append({
                    'employe_id': str(employe.id),
                    'nom_complet': f"{employe.nom} {employe.prenom}",
                    'surnom': employe.surnom or '',
                    'poste_nom': employe.poste.nom_poste if employe.poste else 'N/A',
                    'base_nom': employe.base.nom_base if employe.base else 'N/A',
                    'organisation_nom': employe.base.organisation.nom_organisation if employe.base and employe.base.organisation else 'N/A',
                    'solde_conges_debut_annee': float(solde_conges_debut_annee),
                    'solde_permissions_debut_annee': int(solde_permissions_debut_annee),
                    'conges_acquis': float(conges_acquis),
                    'conges_pris': float(total_conges_pris),
                    'conges_disponibles': float(conges_disponibles),
                    'permissions_prises': total_permissions_prises,
                    'permissions_disponibles': permissions_disponibles,
                    'historique': historique_mensuel
                })

        return JsonResponse({
            'success': True,
            'employes': employes_data,
            'count': len(employes_data),
            'annee': annee
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# ==================== PAIEMENT CONGES NON PRIS ====================

@csrf_exempt
@require_http_methods(["POST"])
def api_payer_conges_non_pris(request):
    """API pour payer des congés non pris (exceptionnel)"""
    try:
        data = json.loads(request.body)

        employe = get_object_or_404(Employe, id=data['employe_id'])
        nb_jours = Decimal(str(data['nb_jours']))
        annee = int(data['annee'])
        mois = int(data['mois'])

        # Vérifier que l'employé a un salaire
        from .models import Salaire
        dernier_salaire = Salaire.objects.filter(
            employe=employe
        ).order_by('-date_paiement').first()

        if not dernier_salaire or not dernier_salaire.salaire_net_paye:
            return JsonResponse({
                'success': False,
                'error': 'Impossible de calculer le prorata : aucun salaire trouvé pour cet employé'
            }, status=400)

        # Calculer le prorata journalier (salaire net / 22 jours ouvrés)
        salaire_net = dernier_salaire.salaire_net_paye
        prorata_journalier = salaire_net / Decimal('22')
        montant_indemnite = nb_jours * prorata_journalier

        # Arrondir au supérieur (100 Ar près)
        import math
        montant_indemnite_arrondi = Decimal(math.ceil(float(montant_indemnite) / 100) * 100)

        # Récupérer ou créer le solde
        solde, created = SoldeConge.objects.get_or_create(
            employe=employe,
            annee=annee,
            mois=mois,
            defaults={
                'solde_conges_debut': calculer_solde_conge_actuel(employe),
                'solde_permissions_debut': calculer_solde_permission_actuel(employe)
            }
        )

        # Mettre Ã  jour le solde
        solde.conges_payes_non_pris = nb_jours
        solde.montant_indemnite_conges = montant_indemnite_arrondi
        solde.save()

        # Créer l'export DiameX temporaire
        date_paiement = date(annee, mois, 1)

        # Description selon le format des salaires
        prefixe_poste = employe.poste.nom_poste[:4].upper() if employe.poste else 'EMP'
        nom_complet = f"{employe.nom} {employe.prenom}"
        description = f"_{prefixe_poste} {nom_complet}_Indemnité congés non pris_{annee} {mois:02d}"

        # Compte comptable
        compte_code = '600000'  # Par défaut
        if employe.poste and employe.poste.compte_salaire and employe.poste.compte_salaire.compte:
            compte_code = employe.poste.compte_salaire.compte

        # Détail
        detail = employe.surnom if employe.surnom else employe.prenom

        # ACTIV
        activ = employe.volet if employe.volet else 'GLOBAL'

        DiameXTemporaire.objects.create(
            description=description,
            compte_code=compte_code,
            detail=detail,
            activ=activ,
            montant_out=montant_indemnite_arrondi,
            date_mouvement=date_paiement,
            info='Hydria Indemnites Conges',
            type='depense',
            statut='en_attente'
        )

        return JsonResponse({
            'success': True,
            'message': f'{nb_jours} jour(s) de congé payé(s) pour {montant_indemnite_arrondi} Ar',
            'montant': float(montant_indemnite_arrondi),
            'prorata_journalier': float(prorata_journalier)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# ==================== ANNULATION ET REPORT ====================

@csrf_exempt
@require_http_methods(["POST"])
def api_demande_conge_annuler(request, demande_id):
    """Annuler une demande de congé"""
    try:
        demande = get_object_or_404(DemandeConge, id=demande_id)
        data = json.loads(request.body)

        if demande.statut == 'refusee':
            return JsonResponse({
                'success': False,
                'error': 'Une demande refusée ne peut pas être annulée'
            }, status=400)

        if demande.statut == 'annulee':
            return JsonResponse({
                'success': False,
                'error': 'Cette demande est déjÃ  annulée'
            }, status=400)

        # Si déjÃ  inscrite au planning, supprimer les entrées Planning
        nb_plannings_supprimes = 0
        if demande.inscrit_planning or demande.statut == 'inscrite_planning':
            from apps.planning.models import Planning, Activite

            # Trouver l'activité Congé correspondante
            activite_conge = Activite.objects.filter(nom__icontains='Cong').first()

            if activite_conge:
                # Supprimer les plannings de congé pour cette période
                plannings = Planning.objects.filter(
                    employe=demande.employe,
                    date__gte=demande.date_debut,
                    date__lte=demande.date_fin,
                    activite=activite_conge
                )
                nb_plannings_supprimes = plannings.count()
                plannings.delete()

            # Restaurer le solde de congés si nécessaire
            restaurer_solde_conge(demande)

        # Marquer comme annulée
        demande.statut = 'annulee'
        demande.motif_annulation = data.get('motif_annulation', '')
        demande.date_annulation = timezone.now()
        if request.user.is_authenticated:
            demande.annulee_par = request.user
        demande.save()

        message = f'Demande annulée avec succès'
        if nb_plannings_supprimes > 0:
            message += f'. {nb_plannings_supprimes} entrée(s) supprimée(s) du planning.'

        return JsonResponse({
            'success': True,
            'message': message
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_demande_conge_reporter(request, demande_id):
    """Reporter une demande de congé Ã  de nouvelles dates"""
    try:
        demande = get_object_or_404(DemandeConge, id=demande_id)
        data = json.loads(request.body)

        # Seules les demandes non encore inscrites peuvent être reportées facilement
        if demande.statut == 'inscrite_planning':
            return JsonResponse({
                'success': False,
                'error': 'Une demande déjÃ  inscrite au planning doit être annulée puis recréée'
            }, status=400)

        if demande.statut in ['refusee', 'annulee']:
            return JsonResponse({
                'success': False,
                'error': 'Une demande refusée ou annulée ne peut pas être reportée'
            }, status=400)

        # Parser les nouvelles dates
        nouvelle_date_debut = datetime.strptime(data['nouvelle_date_debut'], '%Y-%m-%d').date()
        nouvelle_date_fin = datetime.strptime(data['nouvelle_date_fin'], '%Y-%m-%d').date()

        # Calculer le nombre de jours ouvrés
        nb_jours = calculer_nb_jours_ouvres(nouvelle_date_debut, nouvelle_date_fin)

        # Sauvegarder les dates actuelles dans l'historique
        if not demande.dates_originales:
            demande.dates_originales = []

        demande.dates_originales.append({
            'date_debut': demande.date_debut.isoformat(),
            'date_fin': demande.date_fin.isoformat(),
            'date_report': timezone.now().isoformat(),
            'motif': data.get('motif_report', '')
        })

        # Mettre Ã  jour avec les nouvelles dates
        demande.date_debut = nouvelle_date_debut
        demande.date_fin = nouvelle_date_fin
        demande.nb_jours_demandes = nb_jours
        demande.motif_report = data.get('motif_report', '')
        demande.date_report = timezone.now()
        if request.user.is_authenticated:
            demande.reporte_par = request.user
        demande.save()

        return JsonResponse({
            'success': True,
            'message': f'Demande reportée avec succès ({nb_jours} jour(s))'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def restaurer_solde_conge(demande):
    """Restaure le solde de congés après annulation d'une demande"""
    annee = demande.date_debut.year
    mois = demande.date_debut.month

    try:
        solde = SoldeConge.objects.get(
            employe=demande.employe,
            annee=annee,
            mois=mois
        )

        if demande.type_demande == 'conge':
            solde.consommation_conges -= Decimal(str(demande.nb_jours_demandes))
            if solde.consommation_conges < 0:
                solde.consommation_conges = Decimal('0')
        else:
            solde.consommation_permissions -= demande.nb_jours_demandes
            if solde.consommation_permissions < 0:
                solde.consommation_permissions = 0

        solde.save()
    except SoldeConge.DoesNotExist:
        pass  # Aucun solde Ã  restaurer

