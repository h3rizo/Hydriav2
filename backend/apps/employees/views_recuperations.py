"""
Vues pour la gestion des récupérations (jours de repos après travail dimanche/férié)
"""
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Q, Sum
from decimal import Decimal
import json
import unicodedata

from .models_recuperations import Recuperation, SoldeRecuperation
from .models import Employe
from apps.planning.models import Planning
from datetime import date, datetime, timedelta

RECUPERATION_VALIDITY_DAYS = 15


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


def _filter_employes_for_selection(queryset, user):
    """Pour les listes deroulantes, limiter a la meme base sauf directeur/superuser."""
    scope = _get_planning_scope(user)
    if scope == 'all':
        return queryset
    if scope == 'none':
        return queryset.none()

    employe = getattr(user, 'employe', None)
    base_id = getattr(employe, 'base_id', None) if employe else None
    if not base_id:
        return queryset.none()
    return queryset.filter(base_id=base_id)


def _filter_recuperations_by_scope(queryset, user):
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


def _planning_activity_name(planning):
    if getattr(planning, 'fiche_poste', None) and getattr(planning.fiche_poste, 'tache', None):
        return planning.fiche_poste.tache
    if getattr(planning, 'type_activite', None) and getattr(planning.type_activite, 'nomtype', None):
        return planning.type_activite.nomtype
    return ''


def _is_recovery_eligible_planning(planning):
    activity_name = _normalize_poste_name(_planning_activity_name(planning))
    if not activity_name:
        return True

    excluded_keywords = (
        'repos',
        'jour ferie',
        'conge',
        'permission',
        'recuperation',
    )
    return not any(keyword in activity_name for keyword in excluded_keywords)


def _get_easter_sunday(year):
    """Retourne la date du dimanche de Paques pour une annee donnee."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _get_recuperation_public_holidays(year):
    """Jours feries pris en compte pour les recuperations."""
    easter_sunday = _get_easter_sunday(year)
    return {
        date(year, 1, 1),                 # Nouvel An
        easter_sunday - timedelta(days=2),  # Vendredi Saint
        easter_sunday + timedelta(days=1),  # Lundi de Paques
        date(year, 5, 1),                 # Fete du Travail
        easter_sunday + timedelta(days=39),  # Ascension
        easter_sunday + timedelta(days=50),  # Lundi de Pentecote
        date(year, 6, 26),                # Fete de l'Independance
        date(year, 8, 15),                # Assomption
        date(year, 11, 1),                # Toussaint
        date(year, 12, 25),               # Noel
    }


def _build_recuperation_year_choices(current_year, recuperation_years=None, planning_years=None):
    years = {
        current_year - offset
        for offset in range(3)
        if current_year - offset > 0
    }

    for year_group in (recuperation_years or [], planning_years or []):
        for year in year_group:
            if year:
                years.add(int(year))

    return sorted(years, reverse=True)


def _get_recuperation_year_choices(user):
    current_year = timezone.localdate().year

    recuperation_years = list(
        _filter_recuperations_by_scope(Recuperation.objects.all(), user)
        .values_list('date_travail_exceptionnel__year', flat=True)
        .distinct()
    )

    employe_ids = _filter_employes_by_scope(Employe.objects.all(), user).values_list('id', flat=True)
    planning_years = list(
        Planning.objects.filter(employe_id__in=employe_ids)
        .values_list('date__year', flat=True)
        .distinct()
    )

    return _build_recuperation_year_choices(
        current_year=current_year,
        recuperation_years=recuperation_years,
        planning_years=planning_years,
    )


def _get_recuperation_deadline(work_date):
    if not work_date:
        return None
    return work_date + timedelta(days=RECUPERATION_VALIDITY_DAYS)


@login_required
def liste_recuperations(request):
    """
    Page principale de gestion des récupérations
    """
    # Récupérer tous les employés actifs
    employes = Employe.objects.filter(
        date_debauchage__isnull=True
    ).select_related('base__organisation', 'poste').order_by('nom', 'prenom')
    employes = _filter_employes_for_selection(employes, request.user)

    context = {
        'employes': employes,
        'annees_recuperations': _get_recuperation_year_choices(request.user),
        'annee_courante': timezone.localdate().year,
    }

    return render(request, 'employees/recuperations_list.html', context)


@csrf_exempt
@require_http_methods(["GET"])
def api_recuperations_list(request):
    """
    API pour lister les récupérations avec filtres
    """
    # Filtres
    employe_id = request.GET.get('employe_id')
    statut = request.GET.get('statut')
    annee = request.GET.get('annee')

    # QuerySet de base
    queryset = Recuperation.objects.all().select_related(
        'employe__base__organisation',
        'employe__poste',
        'validee_par_chef',
        'validee_par_directeur'
    )
    queryset = _filter_recuperations_by_scope(queryset, request.user)

    # Appliquer les filtres
    if employe_id:
        queryset = queryset.filter(employe_id=employe_id)

    if statut:
        queryset = queryset.filter(statut=statut)

    if annee:
        queryset = queryset.filter(date_travail_exceptionnel__year=int(annee))

    # Ordonner par date décroissante
    queryset = queryset.order_by('-date_travail_exceptionnel', '-date_acquisition')

    # Construire la réponse
    recuperations = []
    for recup in queryset:
        recuperations.append({
            'id': str(recup.id),
            'employe_id': str(recup.employe.id),
            'employe_nom': f"{recup.employe.prenom} {recup.employe.nom}",
            'employe_surnom': recup.employe.surnom,
            'organisation': recup.employe.base.organisation.nom_organisation,
            'date_travail_exceptionnel': recup.date_travail_exceptionnel.strftime('%Y-%m-%d'),
            'motif_acquisition': recup.motif_acquisition,
            'motif_acquisition_display': recup.get_motif_acquisition_display(),
            'nb_jours_acquis': float(recup.nb_jours_acquis),
            'statut': recup.statut,
            'statut_display': recup.get_statut_display(),
            'date_acquisition': recup.date_acquisition.strftime('%Y-%m-%d %H:%M'),
            'date_demande': recup.date_demande.strftime('%Y-%m-%d %H:%M') if recup.date_demande else None,
            'date_debut_recup': recup.date_debut_recup.strftime('%Y-%m-%d') if recup.date_debut_recup else None,
            'date_fin_recup': recup.date_fin_recup.strftime('%Y-%m-%d') if recup.date_fin_recup else None,
            'motif_demande': recup.motif_demande,
            'validee_par_chef': recup.validee_par_chef.username if recup.validee_par_chef else None,
            'date_validation_chef': recup.date_validation_chef.strftime('%Y-%m-%d %H:%M') if recup.date_validation_chef else None,
            'validee_par_directeur': recup.validee_par_directeur.username if recup.validee_par_directeur else None,
            'date_validation_directeur': recup.date_validation_directeur.strftime('%Y-%m-%d %H:%M') if recup.date_validation_directeur else None,
            'inscrit_planning': recup.inscrit_planning,
            'date_expiration': recup.date_expiration.strftime('%Y-%m-%d') if recup.date_expiration else None,
            'est_disponible': recup.est_disponible,
            'peut_etre_utilisee': recup.peut_etre_utilisee,
        })

    return JsonResponse({
        'success': True,
        'recuperations': recuperations,
        'total': len(recuperations)
    })


@csrf_exempt
@require_http_methods(["GET"])
def api_dates_recuperables(request, employe_id):
    """
    API pour obtenir les dates récupérables d'un employé
    (dimanches et jours fériés travaillés dans le Planning)
    """
    try:
        # Vérifier que l'employéexiste
        try:
            employe = _filter_employes_by_scope(Employe.objects.all(), request.user).get(id=employe_id)
        except Employe.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Employénon trouvé'
            }, status=404)

        # Période de recherche (6 derniers mois par défaut)
        annee = request.GET.get('annee')
        if annee:
            # Créer des datetimes timezone-aware pour la comparaison SQL
            tz_madagascar = timezone.get_default_timezone()
            date_debut_dt = timezone.make_aware(datetime(int(annee), 1, 1), tz_madagascar)
            date_fin_dt = timezone.make_aware(datetime(int(annee), 12, 31, 23, 59, 59), tz_madagascar)
        else:
            date_fin_dt = timezone.now()
            date_debut_dt = date_fin_dt - timedelta(days=180)  # 6 mois

        # Récupérer tous les plannings de l'employédans la période
        plannings = Planning.objects.filter(
            employe=employe,
            date__gte=date_debut_dt,
            date__lte=date_fin_dt
        ).select_related('type_activite', 'fiche_poste', 'ouvrage').order_by('date')

        holiday_years = range(date_debut_dt.year, date_fin_dt.year + 1)
        jours_feries = {
            holiday_date.isoformat()
            for year in holiday_years
            for holiday_date in _get_recuperation_public_holidays(year)
        }

        # Récupérer les récupérations déjÃ  créées pour cet employé
        recup_existantes = set(
            Recuperation.objects.filter(employe=employe).values_list('date_travail_exceptionnel', flat=True)
        )
        today = timezone.localdate()

        dates_recuperables = []
        plannings_par_date = {}

        for planning in plannings:
            planning_date = planning.date.date() if hasattr(planning.date, 'date') else planning.date
            if not planning_date:
                continue
            plannings_par_date.setdefault(planning_date, []).append(planning)

        for planning_date, day_plannings in sorted(plannings_par_date.items()):
            if planning_date in recup_existantes:
                continue
            deadline = _get_recuperation_deadline(planning_date)
            if deadline and today > deadline:
                continue

            date_str = planning_date.strftime('%Y-%m-%d')
            est_dimanche = planning_date.weekday() == 6  # 6 = dimanche
            est_jour_ferie = date_str in jours_feries

            eligible_plannings = [
                planning for planning in day_plannings
                if _is_recovery_eligible_planning(planning)
            ]

            if not eligible_plannings:
                continue

            planning_reference = None

            if est_jour_ferie:
                planning_reference = next(
                    (
                        planning for planning in eligible_plannings
                        if getattr(planning, 'ouvrage_id', None)
                        and _planning_activity_name(planning).strip()
                    ),
                    None
                )
            elif est_dimanche:
                planning_reference = eligible_plannings[0]

            if not planning_reference:
                continue

            dates_recuperables.append({
                'date': date_str,
                'date_limite': deadline.strftime('%Y-%m-%d') if deadline else '',
                'planning_id': str(planning_reference.id),
                'motif': 'jour_ferie' if est_jour_ferie else 'dimanche',
                'motif_display': 'Jour férié' if est_jour_ferie else 'Dimanche',
                'activite': _planning_activity_name(planning_reference),
                'ouvrage': planning_reference.ouvrage.nom_ouvrage if planning_reference.ouvrage else '',
                'jour_semaine': planning_date.strftime('%A'),
            })

        return JsonResponse({
            'success': True,
            'dates_recuperables': dates_recuperables,
            'total': len(dates_recuperables),
            'periode': {
                'debut': date_debut_dt.strftime('%Y-%m-%d'),
                'fin': date_fin_dt.strftime('%Y-%m-%d')
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_creer_recuperation(request):
    """
    API pour créer une nouvelle récupération (acquisition)
    MODIFIE: Vérifie que la date correspond bien Ã  un planning existant
    """
    try:
        data = json.loads(request.body)

        # Champs obligatoires
        employe_id = data.get('employe_id')
        date_travail = data.get('date_travail_exceptionnel')
        motif = data.get('motif_acquisition')
        planning_id = data.get('planning_id')  # NOUVEAU: référence au planning

        if not all([employe_id, date_travail, motif]):
            return JsonResponse({
                'success': False,
                'error': 'Champs obligatoires manquants: employe_id, date_travail_exceptionnel, motif_acquisition'
            }, status=400)

        # Vérifier que l'employéexiste
        try:
            employe = _filter_employes_by_scope(Employe.objects.all(), request.user).get(id=employe_id)
        except Employe.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Employénon trouvé'
            }, status=404)

        # NOUVEAU: Vérifier qu'il existe bien un planning pour cette date
        if planning_id:
            try:
                planning = Planning.objects.get(id=planning_id, employe=employe)
            except Planning.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Planning non trouvépour cette date'
                }, status=404)
        else:
            # Si pas de planning_id fourni, chercher un planning pour cette date
            planning = Planning.objects.filter(
                employe=employe,
                date=date_travail
            ).first()

        try:
            date_travail_obj = datetime.strptime(date_travail, '%Y-%m-%d').date()
        except ValueError:
            return JsonResponse({
                'success': False,
                'error': 'Date de travail exceptionnel invalide'
            }, status=400)

        deadline = _get_recuperation_deadline(date_travail_obj)
        today = timezone.localdate()
        if deadline and today > deadline:
            return JsonResponse({
                'success': False,
                'error': f'Cette journée n’est plus récupérable. Le délai de {RECUPERATION_VALIDITY_DAYS} jours est dépassé.'
            }, status=400)

        # Vérifier qu'une récupération n'existe pas déjÃ  pour cette date
        if Recuperation.objects.filter(employe=employe, date_travail_exceptionnel=date_travail).exists():
            return JsonResponse({
                'success': False,
                'error': 'Une récupération existe déjÃ  pour cette date'
            }, status=400)

        # Champs optionnels
        nb_jours = Decimal(str(data.get('nb_jours_acquis', 1.0)))
        date_expiration = data.get('date_expiration')

        # Créer la récupération
        recuperation = Recuperation.objects.create(
            employe=employe,
            date_travail_exceptionnel=date_travail_obj,
            motif_acquisition=motif,
            nb_jours_acquis=nb_jours,
            statut='acquise',
            date_expiration=date_expiration if date_expiration else deadline,
            planning_travail=planning  # Lier au planning
        )

        return JsonResponse({
            'success': True,
            'message': 'Récupération créée avec succès',
            'recuperation_id': str(recuperation.id)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_demander_recuperation(request, recuperation_id):
    """
    API pour demander Ã  utiliser une récupération
    """
    try:
        data = json.loads(request.body)

        # Récupérer la récupération
        try:
            recuperation = _filter_recuperations_by_scope(
                Recuperation.objects.select_related('employe'),
                request.user
            ).get(id=recuperation_id)
        except Recuperation.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Récupération non trouvée'
            }, status=404)

        # Vérifier que la récupération est disponible
        if recuperation.statut != 'acquise':
            return JsonResponse({
                'success': False,
                'error': f'Cette récupération ne peut pas être demandée (statut actuel: {recuperation.get_statut_display()})'
            }, status=400)

        deadline = recuperation.date_expiration or _get_recuperation_deadline(recuperation.date_travail_exceptionnel)
        if deadline and timezone.localdate() > deadline:
            return JsonResponse({
                'success': False,
                'error': f'Cette récupération a expiré. Elle devait être prise dans les {RECUPERATION_VALIDITY_DAYS} jours suivant la journée récupérable.'
            }, status=400)

        # Champs obligatoires
        date_debut = data.get('date_debut_recup')
        date_fin = data.get('date_fin_recup')

        if not all([date_debut, date_fin]):
            return JsonResponse({
                'success': False,
                'error': 'Dates de début et fin requises'
            }, status=400)

        # Mettre Ã  jour la récupération
        recuperation.statut = 'demandee'
        recuperation.date_demande = timezone.now()
        recuperation.date_debut_recup = date_debut
        recuperation.date_fin_recup = date_fin
        recuperation.motif_demande = data.get('motif_demande', '')
        recuperation.save()

        return JsonResponse({
            'success': True,
            'message': 'Demande de récupération enregistrée'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_valider_recuperation(request, recuperation_id):
    """
    API pour valider une récupération (chef ou directeur)
    """
    try:
        data = json.loads(request.body)

        # Récupérer la récupération
        try:
            recuperation = _filter_recuperations_by_scope(
                Recuperation.objects.select_related('employe'),
                request.user
            ).get(id=recuperation_id)
        except Recuperation.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Récupération non trouvée'
            }, status=404)

        # Type de validation
        type_validation = data.get('type')  # 'chef' ou 'directeur'
        commentaire = data.get('commentaire', '')

        if type_validation == 'chef':
            if recuperation.statut != 'demandee':
                return JsonResponse({
                    'success': False,
                    'error': 'Cette récupération ne peut pas être validée par le chef (statut incorrect)'
                }, status=400)

            recuperation.statut = 'validee_chef'
            recuperation.validee_par_chef = request.user
            recuperation.date_validation_chef = timezone.now()
            recuperation.commentaire_chef = commentaire

        elif type_validation == 'directeur':
            if recuperation.statut != 'validee_chef':
                return JsonResponse({
                    'success': False,
                    'error': 'Cette récupération doit d\'abord être validée par le chef'
                }, status=400)

            recuperation.statut = 'validee_directeur'
            recuperation.validee_par_directeur = request.user
            recuperation.date_validation_directeur = timezone.now()
            recuperation.commentaire_directeur = commentaire

        else:
            return JsonResponse({
                'success': False,
                'error': 'Type de validation invalide (chef ou directeur)'
            }, status=400)

        recuperation.save()

        return JsonResponse({
            'success': True,
            'message': f'Récupération validée par {type_validation}'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def api_solde_recuperations(request, employe_id):
    """
    API pour obtenir le solde de récupérations d'un employé
    """
    try:
        # Vérifier que l'employéexiste
        try:
            employe = _filter_employes_by_scope(Employe.objects.all(), request.user).get(id=employe_id)
        except Employe.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Employénon trouvé'
            }, status=404)

        # Récupérations disponibles (acquises non expirées)
        recup_disponibles = Recuperation.objects.filter(
            employe=employe,
            statut='acquise'
        )

        # Filtrer les non expirées
        today = timezone.now().date()
        recup_disponibles = [r for r in recup_disponibles if r.peut_etre_utilisee]

        nb_jours_disponibles = sum([float(r.nb_jours_acquis) for r in recup_disponibles])

        # Récupérations en attente de validation
        recup_en_attente = Recuperation.objects.filter(
            employe=employe,
            statut__in=['demandee', 'validee_chef']
        ).aggregate(total=Sum('nb_jours_acquis'))

        nb_jours_en_attente = float(recup_en_attente['total'] or 0)

        # Récupérations utilisées dans l'année en cours
        annee_courante = timezone.now().year
        recup_utilisees = Recuperation.objects.filter(
            employe=employe,
            statut='utilisee',
            date_debut_recup__year=annee_courante
        ).aggregate(total=Sum('nb_jours_acquis'))

        nb_jours_utilises = float(recup_utilisees['total'] or 0)

        # Dernier solde mensuel
        dernier_solde = SoldeRecuperation.objects.filter(
            employe=employe
        ).order_by('-annee', '-mois').first()

        return JsonResponse({
            'success': True,
            'solde': {
                'employe_id': str(employe.id),
                'employe_nom': f"{employe.prenom} {employe.nom}",
                'nb_jours_disponibles': nb_jours_disponibles,
                'nb_jours_en_attente': nb_jours_en_attente,
                'nb_jours_utilises_annee': nb_jours_utilises,
                'dernier_solde': {
                    'periode': f"{dernier_solde.mois:02d}/{dernier_solde.annee}" if dernier_solde else None,
                    'solde_fin': float(dernier_solde.solde_fin) if dernier_solde else 0
                } if dernier_solde else None
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

