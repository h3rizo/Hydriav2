"""
Vues pour la gestion des indemnités journalières.
Les indemnités sont calculées automatiquement à partir du planning.
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.utils import timezone
from django.conf import settings
from decimal import Decimal
import math
import json
import unicodedata
import pytz
from datetime import datetime, date, timedelta

from .models import Planning, IndemniteJournaliere
from apps.employees.models import Employe, Poste
from apps.organization.models import Base, Organisation, Ouvrage, TypeOuvrage


INDEMNITE_VALIDEE_STATUSES = ('avancee', 'confirmee')
INDEMNITE_PRINTABLE_STATUSES = INDEMNITE_VALIDEE_STATUSES
INDEMNITE_RESETTABLE_STATUSES = ('calculee', 'avancee', 'confirmee', 'imprimee', 'exportee')


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


def _filter_bases_by_scope(queryset, user):
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
        return queryset.filter(organisation_id=organisation_id)

    base_id = getattr(employe, 'base_id', None)
    if not base_id:
        return queryset.none()
    return queryset.filter(id=base_id)


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


def _filter_indemnites_by_scope(queryset, user):
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


def _get_indemnite_ui_status(statut):
    if statut in INDEMNITE_VALIDEE_STATUSES:
        return 'validee'
    return statut


def _is_indemnite_validatable_status(statut):
    return statut == 'calculee'


def _is_indemnite_printable_status(statut):
    return statut in INDEMNITE_PRINTABLE_STATUSES


def _is_indemnite_resettable_status(statut):
    return statut in INDEMNITE_RESETTABLE_STATUSES


def _filter_indemnites_by_requested_status(queryset, statut):
    if not statut:
        return queryset
    if statut == 'validee':
        return queryset.filter(statut__in=INDEMNITE_VALIDEE_STATUSES)
    return queryset.filter(statut=statut)


def _build_indemnite_export_payload(indemnites):
    """Reconstruit les champs DiameXTemporaire crees lors de l export d un lot d indemnites."""
    indemnites_list = list(indemnites.order_by('date'))
    if not indemnites_list:
        return None

    employe = indemnites_list[0].employe
    poste = getattr(employe, 'poste', None)
    if not poste:
        return None

    premiere_date = indemnites_list[0].date
    nb_jours = len(indemnites_list)
    prix_unitaire = float(poste.tarif_indemnite) if poste.tarif_indemnite else 0
    montant_total = float(sum((ind.montant for ind in indemnites_list), Decimal('0')))
    montant_arrondi = math.ceil(montant_total / 100) * 100
    prefixe = poste.prefixe if poste.prefixe else ''
    nom_complet = employe.nom_complet
    annee = premiere_date.year
    mois_num = premiere_date.month
    description = (
        f"_{prefixe} {nom_complet}_Indemnite terrain_"
        f"{nb_jours}_jours_{int(prix_unitaire)}_{int(montant_arrondi)}_{annee} {mois_num}"
    )

    return {
        'description': description,
        'compte_code': poste.compte_indemnite.compte if poste.compte_indemnite else None,
        'detail': employe.surnom if employe.surnom else employe.prenom,
        'info': 'Hydria Indemnites',
        'activ': employe.volet if employe.volet else '',
        'montant_out': float(montant_arrondi),
        'date_m': premiere_date,
        'annee': annee,
        'mois_num': mois_num,
    }


def get_type_bureau():
    """Récupère le type d'ouvrage 'Bureau'"""
    return TypeOuvrage.objects.filter(nom_type_ouvrage__iexact='Bureau').first()


def est_journee_terrain(employe, ouvrage):
    """
    Détermine si un ouvrage correspond à une journée terrain pour un employé.

    Règles:
    - Si l'ouvrage n'est pas de type 'Bureau' → terrain
    - Si l'ouvrage est de type 'Bureau' mais n'est pas l'ouvrage_correspondant
      de la base de l'employé → terrain
    - Sinon → pas terrain (c'est son bureau)
    """
    if not ouvrage:
        return False

    type_bureau = get_type_bureau()

    # Si pas de type Bureau défini, considérer comme terrain
    if not type_bureau:
        return True

    # Si l'ouvrage n'est pas un bureau → terrain
    if ouvrage.type_ouvrage_id != type_bureau.id:
        return True

    # C'est un bureau - vérifier si c'est le bureau de l'employé
    if employe and employe.base:
        base = employe.base
        # Si la base a un ouvrage_correspondant et que c'est cet ouvrage → pas terrain
        if base.ouvrage_correspondant_id == ouvrage.id:
            return False
        # C'est un autre bureau → terrain
        return True

    # Pas de base assignée → considérer comme terrain
    return True


def calculer_indemnites_mois(employe, annee, mois):
    """
    Calcule les indemnités pour un employé sur un mois donné.
    Retourne une liste de dictionnaires avec les infos de chaque jour terrain.
    """
    tz_madagascar = pytz.timezone('Indian/Antananarivo')

    # Vérifier que l'employé a droit aux indemnités
    if not employe.poste or not employe.poste.tarif_indemnite:
        return []

    tarif_journalier = employe.poste.tarif_indemnite

    # Récupérer tous les plannings de l'employé pour ce mois
    plannings = Planning.objects.filter(
        Q(employe=employe) | Q(planning_employees__employee=employe),
        date__year=annee,
        date__month=mois,
        ouvrage__isnull=False
    ).select_related('ouvrage', 'ouvrage__type_ouvrage', 'fiche_poste', 'type_activite').distinct().order_by('date')

    # Grouper par date
    jours_terrain = {}

    for planning in plannings:
        # Convertir la date en timezone Madagascar
        date_aware = planning.date
        if date_aware.tzinfo:
            date_mg = date_aware.astimezone(tz_madagascar).date()
        else:
            date_mg = date_aware.date()

        # Vérifier si c'est une journée terrain
        if not est_journee_terrain(employe, planning.ouvrage):
            continue

        date_str = str(date_mg)

        if date_str not in jours_terrain:
            jours_terrain[date_str] = {
                'date': date_mg,
                'ouvrages': [],
                'ouvrages_ids': [],
                'activites': [],
                'montant': tarif_journalier
            }

        # Ajouter l'ouvrage s'il n'est pas déjà dans la liste
        ouvrage_nom = planning.ouvrage.nom_ouvrage if planning.ouvrage else 'N/A'
        if ouvrage_nom not in jours_terrain[date_str]['ouvrages']:
            jours_terrain[date_str]['ouvrages'].append(ouvrage_nom)
            if planning.ouvrage:
                jours_terrain[date_str]['ouvrages_ids'].append(str(planning.ouvrage.id))

        # Ajouter l'activité
        activite_nom = ''
        if getattr(planning, 'fiche_poste', None) and planning.fiche_poste.tache:
            activite_nom = planning.fiche_poste.tache
        elif getattr(planning, 'type_activite', None) and planning.type_activite.nomtype:
            activite_nom = planning.type_activite.nomtype
        if activite_nom and activite_nom not in jours_terrain[date_str]['activites']:
            jours_terrain[date_str]['activites'].append(activite_nom)

    # Convertir en liste
    result = []
    for date_str, data in sorted(jours_terrain.items()):
        result.append({
            'date': data['date'],
            'ouvrages_visites': ' / '.join(data['ouvrages']),
            'ouvrages_ids': ','.join(data['ouvrages_ids']),
            'activites': ' / '.join(data['activites']) if data['activites'] else 'N/A',
            'montant': data['montant']
        })

    return result


def generer_indemnites_mois(employe, annee, mois):
    """
    Génère les IndemniteJournaliere pour un employé sur un mois.
    Ne crée pas de doublons (utilise get_or_create).
    Retourne le nombre d'indemnités créées.
    """
    jours_terrain = calculer_indemnites_mois(employe, annee, mois)

    nb_creees = 0
    for jour in jours_terrain:
        indemnite, created = IndemniteJournaliere.objects.get_or_create(
            employe=employe,
            date=jour['date'],
            defaults={
                'ouvrages_visites': jour['ouvrages_visites'],
                'ouvrages_ids': jour['ouvrages_ids'],
                'activites': jour['activites'],
                'montant': jour['montant'],
                'statut': 'calculee'
            }
        )
        if created:
            nb_creees += 1
        else:
            # Mettre à jour les infos si l'indemnité existe déjà
            indemnite.ouvrages_visites = jour['ouvrages_visites']
            indemnite.ouvrages_ids = jour['ouvrages_ids']
            indemnite.activites = jour['activites']
            indemnite.save()

    return nb_creees


# ==================== VUES ====================

def indemnites_list(request):
    """Page de visualisation des indemnités journalières"""
    from apps.organization.models import Organisation

    organisations = Organisation.objects.all().order_by('nom_organisation')
    bases = Base.objects.all().order_by('nom_base')
    employes = Employe.objects.filter(
        poste__tarif_indemnite__isnull=False
    ).select_related('base', 'poste').order_by('nom')

    # Cloisonnement des filtres
    scope = _get_planning_scope(request.user)
    if scope == 'organisation':
        organisation_id = getattr(getattr(getattr(request.user, 'employe', None), 'base', None), 'organisation_id', None)
        if organisation_id:
            organisations = organisations.filter(id=organisation_id)
        else:
            organisations = organisations.none()
    elif scope == 'base':
        organisation_id = getattr(getattr(getattr(request.user, 'employe', None), 'base', None), 'organisation_id', None)
        if organisation_id:
            organisations = organisations.filter(id=organisation_id)
        else:
            organisations = organisations.none()

    bases = _filter_bases_by_scope(bases, request.user)
    employes = _filter_employes_by_scope(employes, request.user)

    # Mois disponibles (12 derniers mois) - aligné sur le 1er de chaque mois
    today = date.today()
    mois_disponibles = []
    base_year = today.year
    base_month = today.month
    for i in range(12):
        month = base_month - i
        year = base_year
        if month <= 0:
            year -= (abs(month) // 12) + 1
            month = 12 - (abs(month) % 12)
        d = date(year, month, 1)
        mois_disponibles.append({
            'value': f"{d.year}-{d.month:02d}",
            'label': d.strftime('%B %Y')
        })

    default_base_id = str(bases.first().id) if bases.count() == 1 else ''

    context = {
        'organisations': organisations,
        'bases': bases,
        'employes': employes,
        'mois_disponibles': mois_disponibles,
        'default_base_id': default_base_id,
    }
    return render(request, 'planning/indemnites_list.html', context)


# ==================== INDEMNITES HORS ZONE ====================

def indemnites_hors_zone(request):
    """Page de gestion des indemnités hors zone (planning + participants)"""
    from apps.organization.models import Organisation

    organisations = Organisation.objects.all().order_by('nom_organisation')
    bases = Base.objects.all().order_by('nom_base')
    employes = Employe.objects.filter(
        date_debauchage__isnull=True
    ).select_related('base', 'poste').order_by('nom', 'prenom')

    connected_organisation_id = getattr(
        getattr(getattr(request.user, 'employe', None), 'base', None),
        'organisation_id',
        None
    )
    # Limiter les choix à l'organisation connectée (bases + employés).
    if connected_organisation_id:
        organisations = organisations.filter(id=connected_organisation_id)
        bases = bases.filter(organisation_id=connected_organisation_id)
        employes = employes.filter(base__organisation_id=connected_organisation_id)

    scope = _get_planning_scope(request.user)
    if scope == 'organisation':
        organisation_id = getattr(getattr(getattr(request.user, 'employe', None), 'base', None), 'organisation_id', None)
        if organisation_id:
            organisations = organisations.filter(id=organisation_id)
        else:
            organisations = organisations.none()
    elif scope == 'base':
        organisation_id = getattr(getattr(getattr(request.user, 'employe', None), 'base', None), 'organisation_id', None)
        if organisation_id:
            organisations = organisations.filter(id=organisation_id)
        else:
            organisations = organisations.none()

    bases = _filter_bases_by_scope(bases, request.user)
    employes = _filter_employes_by_scope(employes, request.user)

    # Mois disponibles (12 derniers mois) - aligné sur le 1er de chaque mois
    today = date.today()
    mois_disponibles = []
    base_year = today.year
    base_month = today.month
    for i in range(12):
        month = base_month - i
        year = base_year
        if month <= 0:
            year -= (abs(month) // 12) + 1
            month = 12 - (abs(month) % 12)
        d = date(year, month, 1)
        mois_disponibles.append({
            'value': f"{d.year}-{d.month:02d}",
            'label': d.strftime('%B %Y')
        })

    default_base_id = str(bases.first().id) if bases.count() == 1 else ''

    context = {
        'organisations': organisations,
        'bases': bases,
        'employes': employes,
        'mois_disponibles': mois_disponibles,
        'default_base_id': default_base_id,
    }
    return render(request, 'planning/indemnites_hors_zone.html', context)


@csrf_exempt
@login_required
@require_http_methods(["GET"])
def api_indemnites_hors_zone_list(request):
    """Liste des lignes planning/participants pour indemnité hors zone"""
    from apps.employees.models import ConfigSalaire
    tz_mg = pytz.timezone('Indian/Antananarivo')
    tz_mg = pytz.timezone('Indian/Antananarivo')

    mois = request.GET.get('mois')  # YYYY-MM
    base_id = request.GET.get('base_id')
    employe_id = request.GET.get('employe_id')

    if not mois:
        return JsonResponse({'success': False, 'error': 'Mois requis'}, status=400)

    try:
        annee, m = mois.split('-')
        annee = int(annee)
        m = int(m)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Format de mois invalide'}, status=400)

    config = ConfigSalaire.get_config()
    montant_unitaire = float(config.indemnite_hors_zone)

    start_local = tz_mg.localize(datetime(annee, m, 1))
    if m == 12:
        end_local = tz_mg.localize(datetime(annee + 1, 1, 1))
    else:
        end_local = tz_mg.localize(datetime(annee, m + 1, 1))

    if settings.USE_TZ:
        start_dt = start_local.astimezone(pytz.UTC)
        end_dt = end_local.astimezone(pytz.UTC)
    else:
        start_dt = start_local.replace(tzinfo=None)
        end_dt = end_local.replace(tzinfo=None)

    connected_organisation_id = getattr(
        getattr(getattr(request.user, 'employe', None), 'base', None),
        'organisation_id',
        None
    )

    plannings = Planning.objects.filter(
        date__gte=start_dt,
        date__lt=end_dt
    ).select_related(
        'ouvrage', 'employe__base__organisation', 'fiche_poste', 'type_activite'
    ).prefetch_related(
        'planning_employees__employee__base__organisation',
        'planning_employees__employee__poste'
    )
    plannings = _filter_plannings_by_scope(plannings, request.user)
    if connected_organisation_id:
        plannings = plannings.filter(
            Q(employe__base__organisation_id=connected_organisation_id) |
            Q(planning_employees__employee__base__organisation_id=connected_organisation_id)
        ).distinct()

    lignes = []
    seen = set()
    for planning in plannings:
        employes_participants = []
        if planning.employe:
            employes_participants.append(planning.employe)

        for pe in planning.planning_employees.all():
            if pe.is_present and pe.employee not in employes_participants:
                employes_participants.append(pe.employee)

        for emp in employes_participants:
            if connected_organisation_id and (
                not getattr(emp, 'base_id', None) or
                getattr(getattr(emp, 'base', None), 'organisation_id', None) != connected_organisation_id
            ):
                continue
            if base_id and emp.base_id and str(emp.base_id) != base_id:
                continue
            if employe_id and str(emp.id) != employe_id:
                continue

            if planning.date:
                if settings.USE_TZ and timezone.is_aware(planning.date):
                    date_mg = timezone.localtime(planning.date, tz_mg).date()
                else:
                    date_mg = planning.date.date()
                date_str = date_mg.strftime('%Y-%m-%d')
            else:
                date_str = ''
            dedup_key = (str(emp.id), date_str)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            base_nom = emp.base.nom_base if emp.base else 'N/A'
            lignes.append({
                'planning_id': str(planning.id),
                'employe_id': str(emp.id),
                'employe_nom': emp.nom_affichage,
                'employe_base': base_nom,
                'date': date_str,
                'ouvrage': planning.ouvrage_nom if hasattr(planning, 'ouvrage_nom') else (planning.ouvrage.nom_ouvrage if planning.ouvrage else 'N/A'),
                'activite': planning.activite_display if hasattr(planning, 'activite_display') else 'N/A',
                'remarque': planning.remarque or '',
                'montant': montant_unitaire,
            })

    lignes.sort(key=lambda x: (x['date'], x['employe_nom']))

    return JsonResponse({
        'success': True,
        'montant_unitaire': montant_unitaire,
        'lignes': lignes
    })


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def api_imprimer_facture_indemnite_hors_zone(request):
    """Génère les données de facture d'indemnité hors zone"""
    from apps.employees.models import ConfigSalaire

    try:
        data = json.loads(request.body)
        selections = data.get('selections', [])

        if not selections:
            return JsonResponse({'success': False, 'error': 'Aucune ligne sélectionnée'}, status=400)

        config = ConfigSalaire.get_config()
        montant_unitaire = float(config.indemnite_hors_zone)

        facture_par_employe = {}
        connected_organisation_id = getattr(
            getattr(getattr(request.user, 'employe', None), 'base', None),
            'organisation_id',
            None
        )
        allowed_plannings = _filter_plannings_by_scope(
            Planning.objects.select_related('ouvrage'),
            request.user
        )
        if connected_organisation_id:
            allowed_plannings = allowed_plannings.filter(
                Q(employe__base__organisation_id=connected_organisation_id) |
                Q(planning_employees__employee__base__organisation_id=connected_organisation_id)
            ).distinct()
        allowed_employes = _filter_employes_by_scope(
            Employe.objects.select_related('base__organisation', 'poste'),
            request.user
        )
        if connected_organisation_id:
            allowed_employes = allowed_employes.filter(base__organisation_id=connected_organisation_id)

        for item in selections:
            planning_id = item.get('planning_id')
            employe_id = item.get('employe_id')
            if not planning_id or not employe_id:
                continue

            try:
                planning = allowed_plannings.get(id=planning_id)
                employe = allowed_employes.get(id=employe_id)
            except Exception:
                continue

            emp_key = str(employe.id)
            if emp_key not in facture_par_employe:
                org = employe.base.organisation if employe.base else None
                facture_par_employe[emp_key] = {
                    'employe': {
                        'nom': employe.nom_affichage,
                        'poste': employe.poste.nom_poste if employe.poste else 'N/A',
                        'base': employe.base.nom_base if employe.base else 'N/A',
                    },
                    'organisation': {
                        'nom': org.nom_organisation if org else 'N/A',
                        'logo': org.logo.url if org and org.logo else ''
                    },
                    'montant_unitaire': montant_unitaire,
                    'lignes': [],
                }

            if planning.date:
                if settings.USE_TZ and timezone.is_aware(planning.date):
                    date_mg = timezone.localtime(planning.date, tz_mg).date()
                else:
                    date_mg = planning.date.date()
                date_label = date_mg.strftime('%d/%m/%Y')
            else:
                date_label = 'N/A'

            facture_par_employe[emp_key]['lignes'].append({
                'date': date_label,
                'ouvrage': planning.ouvrage_nom if hasattr(planning, 'ouvrage_nom') else (planning.ouvrage.nom_ouvrage if planning.ouvrage else 'N/A'),
                'activite': planning.activite_display if hasattr(planning, 'activite_display') else 'N/A',
                'remarque': planning.remarque or '',
                'montant': montant_unitaire,
            })

        factures = []
        for facture in facture_par_employe.values():
            facture['total'] = sum(l['montant'] for l in facture['lignes'])
            factures.append(facture)

        return JsonResponse({
            'success': True,
            'factures': factures
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def api_indemnites_list(request):
    """API pour récupérer la liste des indemnités avec filtres"""
    # Filtres
    employe_id = request.GET.get('employe_id')
    base_id = request.GET.get('base_id')
    mois = request.GET.get('mois')  # Format YYYY-MM
    statut = request.GET.get('statut')

    queryset = IndemniteJournaliere.objects.select_related(
        'employe', 'employe__base', 'employe__poste'
    )
    queryset = _filter_indemnites_by_scope(queryset, request.user)

    if employe_id:
        queryset = queryset.filter(employe_id=employe_id)

    if base_id:
        queryset = queryset.filter(employe__base_id=base_id)

    if mois:
        try:
            annee, m = mois.split('-')
            queryset = queryset.filter(date__year=int(annee), date__month=int(m))
        except:
            pass

    queryset = _filter_indemnites_by_requested_status(queryset, statut)

    queryset = queryset.order_by('-date', 'employe__nom')[:500]

    data = []
    for ind in queryset:
        data.append({
            'id': str(ind.id),
            'employe_id': str(ind.employe.id),
            'employe_nom': ind.employe.nom_affichage,
            'employe_base': ind.employe.base.nom_base if ind.employe.base else 'N/A',
            'employe_poste': ind.employe.poste.nom_poste if ind.employe.poste else 'N/A',
            'date': ind.date.strftime('%Y-%m-%d'),
            'ouvrages_visites': ind.ouvrages_visites,
            'activites': ind.activites,
            'montant': float(ind.montant),
            'statut': ind.statut,
            'statut_ui': _get_indemnite_ui_status(ind.statut),
            'can_validate': _is_indemnite_validatable_status(ind.statut),
            'can_print': _is_indemnite_printable_status(ind.statut),
            'can_reset': _is_indemnite_resettable_status(ind.statut),
            'numero_diamex': ind.numero_diamex,
            'base_diamex': ind.base_diamex,
        })

    return JsonResponse({'success': True, 'indemnites': data})


@csrf_exempt
@require_http_methods(["POST"])
def api_generer_indemnites(request):
    """API pour générer les indemnités d'un mois pour une base ou un employé"""
    try:
        data = json.loads(request.body)
        mois = data.get('mois')  # Format YYYY-MM
        base_id = data.get('base_id')
        employe_id = data.get('employe_id')

        if not mois:
            return JsonResponse({'success': False, 'error': 'Mois requis'}, status=400)

        try:
            annee, m = mois.split('-')
            annee = int(annee)
            m = int(m)
        except:
            return JsonResponse({'success': False, 'error': 'Format mois invalide (YYYY-MM)'}, status=400)

        # Filtrer les employés
        employes_qs = Employe.objects.filter(
            poste__tarif_indemnite__isnull=False
        ).select_related('base', 'poste')
        employes_qs = _filter_employes_by_scope(employes_qs, request.user)

        if employe_id:
            employes_qs = employes_qs.filter(id=employe_id)
        elif base_id:
            employes_qs = employes_qs.filter(base_id=base_id)

        total_creees = 0
        for employe in employes_qs:
            nb = generer_indemnites_mois(employe, annee, m)
            total_creees += nb

        return JsonResponse({
            'success': True,
            'message': f'{total_creees} indemnité(s) générée(s)',
            'nb_creees': total_creees
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def api_annuler_indemnites(request):
    """API pour remettre des indemnites a l etat calculee afin de les refaire."""
    from apps.accounting.models import DiameXTemporaire

    try:
        data = json.loads(request.body)
        indemnite_ids = data.get('indemnite_ids', [])

        if not indemnite_ids:
            return JsonResponse({'success': False, 'error': 'Aucune indemnite selectionnee'}, status=400)

        scoped_queryset = _filter_indemnites_by_scope(
            IndemniteJournaliere.objects.all(),
            request.user
        )
        queryset = scoped_queryset.filter(id__in=indemnite_ids)

        if not queryset.exists():
            return JsonResponse({'success': False, 'error': 'Indemnites non trouvees'}, status=404)

        non_resettable = queryset.exclude(statut__in=INDEMNITE_RESETTABLE_STATUSES)
        if non_resettable.exists():
            return JsonResponse({'success': False, 'error': 'Certaines indemnites ne peuvent pas etre annulees'}, status=400)

        groupes = {}
        for ind in queryset.select_related('employe', 'employe__poste'):
            key = (
                str(ind.employe_id),
                ind.date.year,
                ind.date.month,
            )
            groupes.setdefault(key, []).append(ind.id)

        nb_transactions_supprimees = 0
        for indemnites_ids_groupe in groupes.values():
            indemnites_groupe = scoped_queryset.filter(id__in=indemnites_ids_groupe).select_related(
                'employe', 'employe__poste'
            )
            if not indemnites_groupe.filter(statut='exportee').exists():
                continue

            export_payload = _build_indemnite_export_payload(indemnites_groupe)
            if not export_payload:
                return JsonResponse({
                    'success': False,
                    'error': 'Impossible de reconstruire la ligne DiameXTemporaire a supprimer pour une ou plusieurs indemnites exportees.'
                }, status=400)

            transaction_qs = DiameXTemporaire.objects.filter(
                type_transaction='depense',
                compte_code=export_payload['compte_code'],
                detail=export_payload['detail'],
                activ=export_payload['activ'],
                montant_out=export_payload['montant_out'],
                date_m=export_payload['date_m'],
                statut='en_attente',
                description__icontains=f"{export_payload['annee']} {export_payload['mois_num']}",
            )

            deleted_count, _ = transaction_qs.delete()
            if deleted_count == 0:
                return JsonResponse({
                    'success': False,
                    'error': 'Ligne DiameXTemporaire introuvable pour au moins un lot exporte. Annulation interrompue pour eviter une incoherence.'
                }, status=400)
            nb_transactions_supprimees += deleted_count

        nb_updated = queryset.update(
            statut='calculee',
            date_avance=None,
            date_confirmation=None,
            date_impression=None,
            date_export=None,
            numero_diamex=None,
            base_diamex=None,
        )

        return JsonResponse({
            'success': True,
            'message': f'{nb_updated} indemnite(s) remise(s) a l etat calculee, {nb_transactions_supprimees} ligne(s) DiameXTemporaire supprimee(s)',
            'nb_updated': nb_updated,
            'nb_transactions_supprimees': nb_transactions_supprimees,
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_marquer_avancees(request):
    """API pour marquer des indemnités comme avancées"""
    try:
        data = json.loads(request.body)
        indemnite_ids = data.get('indemnite_ids', [])

        if not indemnite_ids:
            return JsonResponse({'success': False, 'error': 'Aucune indemnité sélectionnée'}, status=400)

        nb_updated = IndemniteJournaliere.objects.filter(
            id__in=indemnite_ids,
            statut='calculee'
        ).update(
            statut='avancee',
            date_avance=timezone.now()
        )

        return JsonResponse({
            'success': True,
            'message': f'{nb_updated} indemnité(s) marquée(s) comme avancée(s)',
            'nb_updated': nb_updated
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def api_confirmer_indemnites(request):
    """API pour confirmer des indemnités (retour terrain)"""
    try:
        data = json.loads(request.body)
        indemnite_ids = data.get('indemnite_ids', [])

        if not indemnite_ids:
            return JsonResponse({'success': False, 'error': 'Aucune indemnité sélectionnée'}, status=400)

        scoped_queryset = _filter_indemnites_by_scope(
            IndemniteJournaliere.objects.all(),
            request.user
        )
        nb_updated = scoped_queryset.filter(
            id__in=indemnite_ids,
            statut='calculee'
        ).update(
            statut='confirmee',
            date_confirmation=timezone.now()
        )

        return JsonResponse({
            'success': True,
            'message': f'{nb_updated} indemnité(s) validée(s)',
            'nb_updated': nb_updated
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def retour_indemnites(request):
    return redirect('planning:indemnites')
    """Page de retour/confirmation des indemnités avec impression"""
    bases = Base.objects.all().order_by('nom_base')
    employes = Employe.objects.filter(
        poste__tarif_indemnite__isnull=False
    ).select_related('base', 'poste').order_by('nom')
    bases = _filter_bases_by_scope(bases, request.user)
    employes = _filter_employes_by_scope(employes, request.user)

    # Mois disponibles (12 derniers mois) - aligné sur le 1er de chaque mois
    today = date.today()
    mois_disponibles = []
    base_year = today.year
    base_month = today.month
    for i in range(12):
        month = base_month - i
        year = base_year
        if month <= 0:
            year -= (abs(month) // 12) + 1
            month = 12 - (abs(month) % 12)
        d = date(year, month, 1)
        mois_disponibles.append({
            'value': f"{d.year}-{d.month:02d}",
            'label': d.strftime('%B %Y')
        })

    default_base_id = str(bases.first().id) if bases.count() == 1 else ''

    context = {
        'bases': bases,
        'employes': employes,
        'mois_disponibles': mois_disponibles,
        'default_base_id': default_base_id,
    }
    return render(request, 'planning/retour_indemnites.html', context)


@csrf_exempt
@login_required
@require_http_methods(["GET"])
def api_indemnites_a_confirmer(request):
    """API pour récupérer les indemnités avancées à confirmer"""
    employe_id = request.GET.get('employe_id')
    base_id = request.GET.get('base_id')
    mois = request.GET.get('mois')

    queryset = IndemniteJournaliere.objects.filter(
        statut='avancee'
    ).select_related('employe', 'employe__base', 'employe__poste')
    queryset = _filter_indemnites_by_scope(queryset, request.user)

    if employe_id:
        queryset = queryset.filter(employe_id=employe_id)

    if base_id:
        queryset = queryset.filter(employe__base_id=base_id)

    if mois:
        try:
            annee, m = mois.split('-')
            queryset = queryset.filter(date__year=int(annee), date__month=int(m))
        except:
            pass

    queryset = queryset.order_by('employe__nom', 'date')

    # Grouper par employé
    employes_data = {}
    for ind in queryset:
        emp_id = str(ind.employe.id)
        if emp_id not in employes_data:
            employes_data[emp_id] = {
                'employe_id': emp_id,
                'employe_nom': ind.employe.nom_affichage,
                'employe_base': ind.employe.base.nom_base if ind.employe.base else 'N/A',
                'employe_poste': ind.employe.poste.nom_poste if ind.employe.poste else 'N/A',
                'indemnites': [],
                'total': Decimal('0')
            }

        employes_data[emp_id]['indemnites'].append({
            'id': str(ind.id),
            'date': ind.date.strftime('%Y-%m-%d'),
            'ouvrages_visites': ind.ouvrages_visites,
            'activites': ind.activites,
            'montant': float(ind.montant),
        })
        employes_data[emp_id]['total'] += ind.montant

    # Convertir en liste
    result = []
    for emp_data in employes_data.values():
        emp_data['total'] = float(emp_data['total'])
        result.append(emp_data)

    return JsonResponse({'success': True, 'employes': result})


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def api_imprimer_facture_indemnite(request):
    """
    API pour marquer les indemnités comme imprimées, exporter vers DiameXTemporaire
    et retourner les données pour impression.

    Format de description DiameX:
    _[Prefixe du poste] [Nom de l'employé]_Indemnité terrain_[Nombre jours]_jours_[PU]_[Montant total]_[Année] [Mois]

    Champs DiameX:
    - Cat (compte_code): compte_indemnite du poste
    - Info: "Hydria Indemnités"
    - Detail: surnom de l'employé
    - Activ: volet de l'employé
    """
    from apps.accounting.models import DiameXTemporaire

    try:
        data = json.loads(request.body)
        indemnite_ids = data.get('indemnite_ids', [])

        if not indemnite_ids:
            return JsonResponse({'success': False, 'error': 'Aucune indemnité sélectionnée'}, status=400)

        # Récupérer les indemnités avec toutes les relations
        indemnites = IndemniteJournaliere.objects.filter(
            id__in=indemnite_ids
        ).select_related(
            'employe', 'employe__base', 'employe__poste',
            'employe__base__organisation', 'employe__poste__compte_indemnite'
        )
        indemnites = _filter_indemnites_by_scope(indemnites, request.user)

        if not indemnites.exists():
            return JsonResponse({'success': False, 'error': 'Indemnités non trouvées'}, status=404)

        # Vérifier qu'elles appartiennent au même employé
        employe = indemnites.first().employe
        for ind in indemnites:
            if ind.employe_id != employe.id:
                return JsonResponse({'success': False, 'error': 'Les indemnités doivent appartenir au même employé'}, status=400)

        # Marquer comme imprimées
        nb_updated = indemnites.filter(statut__in=['avancee', 'confirmee']).update(
            statut='imprimee',
            date_impression=timezone.now()
        )

        # Préparer les données pour la facture
        lignes = []
        total = Decimal('0')
        for ind in indemnites.order_by('date'):
            lignes.append({
                'date': ind.date.strftime('%d/%m/%Y'),
                'activites': ind.activites,
                'ouvrages': ind.ouvrages_visites,
                'montant': float(ind.montant)
            })
            total += ind.montant

        # Déterminer le mois en français
        mois_fr = ['', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
                   'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']
        premiere_date = indemnites.order_by('date').first().date
        mois_label = f"{mois_fr[premiere_date.month]} {premiere_date.year}"

        # === EXPORT VERS DiameXTemporaire ===
        nb_exportes = 0
        erreurs_export = []

        try:
            poste = employe.poste
            if poste and poste.compte_indemnite:
                # Calcul des valeurs
                nb_jours = len(lignes)
                prix_unitaire = float(poste.tarif_indemnite) if poste.tarif_indemnite else 0
                montant_total = float(total)
                montant_arrondi = math.ceil(montant_total / 100) * 100

                # Construction de la description
                # Format: _[Prefixe] [Nom]_Indemnité terrain_[Nb jours]_jours_[PU]_[Total]_[Année] [Mois]
                prefixe = poste.prefixe if poste.prefixe else ''
                nom_complet = employe.nom_complet
                annee = premiere_date.year
                mois_num = premiere_date.month

                description = f"_{prefixe} {nom_complet}_Indemnité terrain_{nb_jours}_jours_{int(prix_unitaire)}_{int(montant_arrondi)}_{annee} {mois_num}"

                # Créer la ligne DiameXTemporaire
                DiameXTemporaire.objects.create(
                    type_transaction='depense',
                    description=description,
                    compte_code=poste.compte_indemnite.compte,  # Cat
                    info='Hydria Indemnités',  # Info fixe
                    detail=employe.surnom if employe.surnom else employe.prenom,  # Detail
                    activ=employe.volet if employe.volet else '',  # ACTIV
                    montant_out=float(montant_arrondi),  # Montant arrondi
                    date_m=premiere_date,  # Date mouvement = 1ère date du lot
                    statut='en_attente'
                )
                nb_exportes = 1

                # Mettre à jour les indemnités avec le statut exporté
                indemnites.update(statut='exportee', date_export=timezone.now())

            else:
                erreurs_export.append(f"Pas de compte indemnité configuré pour le poste {poste.nom_poste if poste else 'N/A'}")

        except Exception as e:
            erreurs_export.append(f"Erreur export DiameX: {str(e)}")

        facture_data = {
            'employe': {
                'nom': employe.nom_complet,
                'poste': employe.poste.nom_poste if employe.poste else 'N/A',
                'base': employe.base.nom_base if employe.base else 'N/A',
            },
            'organisation': {
                'nom': employe.base.organisation.nom_organisation if employe.base else 'N/A',
                'logo': employe.base.organisation.logo.url if employe.base and employe.base.organisation.logo else None,
            },
            'mois': mois_label,
            'lignes': lignes,
            'total': float(total),
            'nb_jours': len(lignes),
        }

        message = f'{nb_updated} indemnité(s) marquée(s) comme imprimée(s)'
        if nb_exportes > 0:
            message += f', {nb_exportes} ligne(s) exportée(s) vers DiameX'
        if erreurs_export:
            message += f' ({len(erreurs_export)} erreur(s))'

        return JsonResponse({
            'success': True,
            'message': message,
            'facture': facture_data,
            'nb_exportes': nb_exportes,
            'erreurs_export': erreurs_export
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ==================== EXPORT DIAMEX ====================

@csrf_exempt
@require_http_methods(["POST"])
def api_export_diamex_indemnites(request):
    """API pour exporter les indemnités vers DiameXTemporaire"""
    from apps.billing.models import TemporaireDiameX

    try:
        data = json.loads(request.body)
        indemnite_ids = data.get('indemnite_ids', [])

        if not indemnite_ids:
            return JsonResponse({'success': False, 'error': 'Aucune indemnité sélectionnée'}, status=400)

        indemnites = IndemniteJournaliere.objects.filter(
            id__in=indemnite_ids,
            statut='imprimee'
        ).select_related('employe', 'employe__base', 'employe__poste', 'employe__poste__compte_indemnite')

        nb_exportees = 0
        erreurs = []

        for ind in indemnites:
            try:
                # Vérifier que le poste a un compte indemnité
                if not ind.employe.poste or not ind.employe.poste.compte_indemnite:
                    erreurs.append(f"{ind.employe.nom_affichage}: Pas de compte indemnité configuré")
                    continue

                compte = ind.employe.poste.compte_indemnite

                # Créer la ligne DiameXTemporaire
                description = f"Indemnité_{ind.date.strftime('%Y-%m-%d')}_{ind.employe.surnom or ind.employe.prenom}"

                TemporaireDiameX.objects.create(
                    description=description,
                    compte_code=compte.compte,
                    detail=ind.employe.surnom or ind.employe.prenom,
                    activite=ind.employe.volet,
                    montant_out=ind.montant,
                    date_mouvement=ind.date,
                    type_mouvement='depense',
                    statut='en_attente',
                    source='indemnite',
                    reference_id=str(ind.id)
                )

                # Marquer comme exportée
                ind.statut = 'exportee'
                ind.date_export = timezone.now()
                ind.save()

                nb_exportees += 1

            except Exception as e:
                erreurs.append(f"{ind.employe.nom_affichage} {ind.date}: {str(e)}")

        return JsonResponse({
            'success': True,
            'message': f'{nb_exportees} indemnité(s) exportée(s) vers DiameX',
            'nb_exportees': nb_exportees,
            'erreurs': erreurs
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ==================== IMPORT/EXPORT EXCEL ====================

def export_excel_indemnites(request):
    """Export des indemnités en Excel"""
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill

    mois = request.GET.get('mois')
    base_id = request.GET.get('base_id')

    queryset = IndemniteJournaliere.objects.select_related(
        'employe', 'employe__base', 'employe__poste'
    ).order_by('-date', 'employe__nom')

    if mois:
        try:
            annee, m = mois.split('-')
            queryset = queryset.filter(date__year=int(annee), date__month=int(m))
        except:
            pass

    if base_id:
        queryset = queryset.filter(employe__base_id=base_id)

    # Créer le workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Indemnités"

    # En-têtes
    headers = ['ID', 'Employé', 'Base', 'Poste', 'Date', 'Ouvrages', 'Activités', 'Montant', 'Statut', 'N° DiameX', 'Base DiameX']
    header_fill = PatternFill(start_color='366092', end_color='366092', fill_type='solid')
    header_font = Font(color='FFFFFF', bold=True)

    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')

    # Données
    for row_num, ind in enumerate(queryset, 2):
        ws.cell(row=row_num, column=1, value=str(ind.id))
        ws.cell(row=row_num, column=2, value=ind.employe.nom_affichage)
        ws.cell(row=row_num, column=3, value=ind.employe.base.nom_base if ind.employe.base else '')
        ws.cell(row=row_num, column=4, value=ind.employe.poste.nom_poste if ind.employe.poste else '')
        ws.cell(row=row_num, column=5, value=ind.date.strftime('%d/%m/%Y'))
        ws.cell(row=row_num, column=6, value=ind.ouvrages_visites)
        ws.cell(row=row_num, column=7, value=ind.activites)
        ws.cell(row=row_num, column=8, value=float(ind.montant))
        ws.cell(row=row_num, column=9, value=ind.statut)
        ws.cell(row=row_num, column=10, value=ind.numero_diamex or '')
        ws.cell(row=row_num, column=11, value=ind.base_diamex or '')

    # Ajuster les largeurs
    for col in range(1, len(headers) + 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = 15

    # Réponse HTTP
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename=indemnites_{mois or "all"}.xlsx'
    wb.save(response)

    return response


def template_excel_indemnites(request):
    """Génère un template Excel vide pour l'import des indemnités"""
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Indemnités à importer"

    # En-têtes
    headers = [
        ('ID Employé ou Surnom*', 25),
        ('Date (JJ/MM/AAAA)*', 18),
        ('Ouvrages visités*', 40),
        ('Activités', 30),
        ('Montant (optionnel)', 18),
    ]

    header_fill = PatternFill(start_color='366092', end_color='366092', fill_type='solid')
    header_font = Font(color='FFFFFF', bold=True)

    for col, (header, width) in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')
        ws.column_dimensions[get_column_letter(col)].width = width

    # Exemples
    exemples = [
        ('JD', '01/11/2025', 'Ouvrage A / Ouvrage B', 'Maintenance préventive', '15000'),
        ('Marie', '02/11/2025', 'Ouvrage C', 'Réparation fuite', ''),
    ]

    for row_num, exemple in enumerate(exemples, 2):
        for col, val in enumerate(exemple, 1):
            cell = ws.cell(row=row_num, column=col, value=val)
            cell.font = Font(italic=True, color='808080')

    # Ajouter une feuille de référence des employés
    ws_emp = wb.create_sheet(title="Employés (référence)")
    ws_emp.cell(row=1, column=1, value="ID Employé").font = Font(bold=True)
    ws_emp.cell(row=1, column=2, value="Surnom").font = Font(bold=True)
    ws_emp.cell(row=1, column=3, value="Nom complet").font = Font(bold=True)
    ws_emp.cell(row=1, column=4, value="Base").font = Font(bold=True)
    ws_emp.cell(row=1, column=5, value="Tarif indemnité").font = Font(bold=True)

    employes = Employe.objects.filter(
        poste__tarif_indemnite__isnull=False
    ).select_related('base', 'poste').order_by('base__nom_base', 'nom')

    for row_num, emp in enumerate(employes, 2):
        ws_emp.cell(row=row_num, column=1, value=str(emp.id))
        ws_emp.cell(row=row_num, column=2, value=emp.surnom or emp.prenom)
        ws_emp.cell(row=row_num, column=3, value=emp.nom_complet)
        ws_emp.cell(row=row_num, column=4, value=emp.base.nom_base if emp.base else 'N/A')
        ws_emp.cell(row=row_num, column=5, value=float(emp.poste.tarif_indemnite) if emp.poste else 0)

    ws_emp.column_dimensions['A'].width = 40
    ws_emp.column_dimensions['B'].width = 15
    ws_emp.column_dimensions['C'].width = 25
    ws_emp.column_dimensions['D'].width = 15
    ws_emp.column_dimensions['E'].width = 15

    # Réponse HTTP
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename=template_indemnites.xlsx'
    wb.save(response)

    return response


@csrf_exempt
@require_http_methods(["POST"])
def import_excel_indemnites(request):
    """Import des indemnités depuis un fichier Excel"""
    import openpyxl
    from datetime import datetime

    try:
        file = request.FILES.get('file')
        if not file:
            return JsonResponse({'success': False, 'error': 'Aucun fichier fourni'}, status=400)

        # Charger le fichier Excel
        wb = openpyxl.load_workbook(file)
        ws = wb.active

        nb_importees = 0
        nb_mises_a_jour = 0
        erreurs = []

        # Parcourir les lignes (skip l'en-tête)
        for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
            if not row or not row[0] or not row[1]:
                continue  # Ligne vide

            employe_ref = str(row[0]).strip()
            date_str = row[1]
            ouvrages_visites = str(row[2]).strip() if row[2] else ''
            activites = str(row[3]).strip() if len(row) > 3 and row[3] else ''
            montant_str = row[4] if len(row) > 4 and row[4] else None

            # Trouver l'employé (par ID ou surnom)
            employe = None
            try:
                # Essayer par UUID
                from uuid import UUID
                UUID(employe_ref)
                employe = Employe.objects.filter(id=employe_ref).first()
            except (ValueError, AttributeError):
                # Essayer par surnom
                employe = Employe.objects.filter(
                    Q(surnom__iexact=employe_ref) | Q(prenom__iexact=employe_ref)
                ).first()

            if not employe:
                erreurs.append(f"Ligne {row_num}: Employé '{employe_ref}' non trouvé")
                continue

            # Vérifier que l'employé a droit aux indemnités
            if not employe.poste or not employe.poste.tarif_indemnite:
                erreurs.append(f"Ligne {row_num}: {employe.nom_affichage} n'a pas de tarif indemnité configuré")
                continue

            # Parser la date
            try:
                if isinstance(date_str, datetime):
                    date_obj = date_str.date()
                elif isinstance(date_str, date):
                    date_obj = date_str
                else:
                    date_str = str(date_str).strip()
                    # Essayer différents formats
                    for fmt in ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y']:
                        try:
                            date_obj = datetime.strptime(date_str, fmt).date()
                            break
                        except ValueError:
                            continue
                    else:
                        raise ValueError(f"Format de date non reconnu: {date_str}")
            except Exception as e:
                erreurs.append(f"Ligne {row_num}: {str(e)}")
                continue

            # Déterminer le montant
            if montant_str:
                try:
                    montant = Decimal(str(montant_str))
                except:
                    montant = employe.poste.tarif_indemnite
            else:
                montant = employe.poste.tarif_indemnite

            # Créer ou mettre à jour l'indemnité
            indemnite, created = IndemniteJournaliere.objects.get_or_create(
                employe=employe,
                date=date_obj,
                defaults={
                    'ouvrages_visites': ouvrages_visites,
                    'activites': activites,
                    'montant': montant,
                    'statut': 'calculee'
                }
            )

            if created:
                nb_importees += 1
            else:
                # Mettre à jour si déjà existant
                indemnite.ouvrages_visites = ouvrages_visites
                indemnite.activites = activites
                if montant_str:  # Ne mettre à jour le montant que s'il est fourni
                    indemnite.montant = montant
                indemnite.save()
                nb_mises_a_jour += 1

        message = f"{nb_importees} indemnité(s) importée(s)"
        if nb_mises_a_jour > 0:
            message += f", {nb_mises_a_jour} mise(s) à jour"

        return JsonResponse({
            'success': True,
            'message': message,
            'nb_importees': nb_importees,
            'nb_mises_a_jour': nb_mises_a_jour,
            'erreurs': erreurs
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
