from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.core.paginator import Paginator
from django.db.models import Count, Prefetch, Q
from django.utils import timezone
from urllib.parse import urlencode
import json
import uuid
from datetime import datetime
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from apps.infrastructure.models import EquipementConstitutif, Adresse
from apps.organization.models import Organisation, Ouvrage as OrgOuvrage, TypeOuvrage as OrgTypeOuvrage
from apps.billing.models import PointEau, CompteurTete, Fournisseur, TarifVolumetrique, TarifVolumetrique2, ModaliteGestion
from apps.employees.models import Employe
from apps.geography.models import Region, District, Commune, Fokontany, Village, Parcelle
from apps.organization.scoping import get_default_gestionnaire_filter_value, get_user_accessible_gestionnaire_ids
from apps.employees.permissions import filter_queryset_by_permissions
from .forms import (TypeOuvrageForm, OuvrageForm, PointEauForm, PointEauProblematiqueForm,
                   EquipementConstitutifForm, EquipementMaintenanceForm, CompteurTeteForm, FournisseurForm,
                   TarifVolumetriqueForm, ModaliteGestionForm)


def _ouvrages_subdomain_queryset():
    return OrgOuvrage.objects.filter(type_ouvrage__existe=True)


OUVRAGES_SCOPE_SESSION_KEY = 'ouvrages_scope_filters'
OUVRAGES_SCOPE_FIELDS = ('organisation_id', 'region_id', 'district_id', 'commune_id')
PROBLEMATIQUE_PAIEMENT_LEGEND = [
    (0, "Pas de problème"),
    (1, "Problème provoquant des attentes de l'agent avant d'avoir le paiement"),
    (2, "Certains usagers ne paient pas"),
    (3, "L'agent coupe souvent avant d'avoir le paiement"),
    (4, "La coupure peut durer longtemps avant d'avoir le paiement (plus de 2 semaines)"),
    (5, "Les usagers ne paient pas et l'agent n'arrive pas à réaliser la coupure"),
]


def _get_ouvrages_scope(request):
    session_scope = request.session.get(OUVRAGES_SCOPE_SESSION_KEY, {}) or {}
    scope = {
        field: (request.GET.get(field) or session_scope.get(field) or '').strip()
        for field in OUVRAGES_SCOPE_FIELDS
    }

    allowed_organisation_ids = get_user_accessible_gestionnaire_ids(request.user)
    default_organisation_id = get_default_gestionnaire_filter_value(request.user, allowed_organisation_ids)

    if allowed_organisation_ids is not None:
        allowed_organisation_ids = [str(item) for item in allowed_organisation_ids if item]
        if scope['organisation_id'] and scope['organisation_id'] not in allowed_organisation_ids:
            scope['organisation_id'] = default_organisation_id if default_organisation_id in allowed_organisation_ids else ''
        elif not scope['organisation_id'] and default_organisation_id in allowed_organisation_ids:
            scope['organisation_id'] = default_organisation_id
    elif not scope['organisation_id']:
        scope['organisation_id'] = default_organisation_id

    if request.GET:
        request.session[OUVRAGES_SCOPE_SESSION_KEY] = scope

    return scope, allowed_organisation_ids, default_organisation_id


def _apply_ouvrages_scope(queryset, scope):
    organisation_id = scope.get('organisation_id')
    region_id = scope.get('region_id')
    district_id = scope.get('district_id')
    commune_id = scope.get('commune_id')

    if organisation_id:
        today = timezone.localdate()
        queryset = queryset.filter(
            modalites_gestion__statut='actif',
            modalites_gestion__date_debut__lte=today,
            modalites_gestion__gestionnaire_id=organisation_id,
        ).filter(
            Q(modalites_gestion__date_fin__isnull=True)
            | Q(modalites_gestion__date_fin__gte=today)
        )
    if region_id:
        queryset = queryset.filter(
            pointeau__parcelle__village__fokontany__commune__district__region_id=region_id
        )
    if district_id:
        queryset = queryset.filter(
            pointeau__parcelle__village__fokontany__commune__district_id=district_id
        )
    if commune_id:
        queryset = queryset.filter(
            pointeau__parcelle__village__fokontany__commune_id=commune_id
        )
    return queryset.distinct()


def _get_ouvrages_scope_query(scope):
    params = {key: value for key, value in scope.items() if value}
    return f"?{urlencode(params)}" if params else ''


def _get_ouvrages_scope_filter_context(request, scope, allowed_organisation_ids=None, default_organisation_id=''):
    organisation_id = scope.get('organisation_id', '')
    region_id = scope.get('region_id', '')
    district_id = scope.get('district_id', '')

    base_ouvrages_qs = filter_queryset_by_permissions(
        _ouvrages_subdomain_queryset().select_related('type_ouvrage'),
        request.user,
    )

    today = timezone.localdate()
    active_modalites_qs = ModaliteGestion.objects.filter(
        statut='actif',
        date_debut__lte=today,
        ouvrage__in=base_ouvrages_qs,
    ).filter(
        Q(date_fin__isnull=True) | Q(date_fin__gte=today)
    ).select_related('gestionnaire')
    if allowed_organisation_ids is None:
        allowed_organisation_ids = get_user_accessible_gestionnaire_ids(request.user)
        default_organisation_id = get_default_gestionnaire_filter_value(request.user, allowed_organisation_ids)
    if allowed_organisation_ids is not None:
        allowed_organisation_ids = [str(item) for item in allowed_organisation_ids if item]
        if allowed_organisation_ids:
            active_modalites_qs = active_modalites_qs.filter(gestionnaire_id__in=allowed_organisation_ids)
        else:
            active_modalites_qs = active_modalites_qs.none()

    organisations = Organisation.objects.filter(
        id__in=active_modalites_qs.filter(gestionnaire_id__isnull=False).values_list('gestionnaire_id', flat=True).distinct(),
        type_organisation=Organisation.TYPE_GESTIONNAIRE,
    ).order_by('nom_organisation')
    organisation_ids = [str(item.id) for item in organisations]
    if organisation_id and organisation_id not in organisation_ids:
        organisation_id = default_organisation_id if default_organisation_id in organisation_ids else ''
    elif not organisation_id and default_organisation_id in organisation_ids:
        organisation_id = default_organisation_id

    geo_scope = {'organisation_id': organisation_id}
    geo_qs = _apply_ouvrages_scope(base_ouvrages_qs, geo_scope)

    regions = Region.objects.filter(
        districts__communes__fokontanys__villages__parcelles__pointeau__ouvrage__in=geo_qs
    ).distinct().order_by('nom_region')

    districts = District.objects.filter(
        communes__fokontanys__villages__parcelles__pointeau__ouvrage__in=geo_qs
    ).distinct()
    if region_id:
        districts = districts.filter(region_id=region_id)
    districts = districts.order_by('nom_district')

    communes = Commune.objects.filter(
        fokontanys__villages__parcelles__pointeau__ouvrage__in=geo_qs
    ).distinct()
    if region_id:
        communes = communes.filter(district__region_id=region_id)
    if district_id:
        communes = communes.filter(district_id=district_id)
    communes = communes.order_by('nom_commune')

    scope['organisation_id'] = organisation_id
    return {
        'organisations': organisations,
        'regions': regions,
        'districts': districts,
        'communes': communes,
    }


def _extend_context_with_ouvrages_scope(context, scope, request=None):
    context.update(scope)
    context['ouvrages_scope_query'] = _get_ouvrages_scope_query(scope)
    if request is not None:
        for key, value in _get_ouvrages_scope_filter_context(request, scope).items():
            context.setdefault(key, value)
    return context


def ouvrages_workspace_home(request):
    """Accueil du sous-domaine ouvrages avec filtres organisation et géographie."""
    scope, allowed_organisation_ids, default_organisation_id = _get_ouvrages_scope(request)
    requested_organisation_id = (request.GET.get('organisation_id') or '').strip()
    organisation_id = scope['organisation_id']
    region_id = scope['region_id']
    district_id = scope['district_id']
    commune_id = scope['commune_id']

    types_ouvrages = OrgTypeOuvrage.objects.all().order_by('nom_type_ouvrage')
    base_ouvrages_qs = filter_queryset_by_permissions(
        _ouvrages_subdomain_queryset().select_related('type_ouvrage'),
        request.user,
    )

    filter_context = _get_ouvrages_scope_filter_context(
        request,
        scope,
        allowed_organisation_ids=allowed_organisation_ids,
        default_organisation_id=default_organisation_id,
    )
    organisations = filter_context['organisations']
    regions = filter_context['regions']
    districts = filter_context['districts']
    communes = filter_context['communes']
    organisation_id = scope['organisation_id']
    if requested_organisation_id and organisation_id != requested_organisation_id:
        request.session[OUVRAGES_SCOPE_SESSION_KEY] = scope

    ouvrages_qs = _apply_ouvrages_scope(base_ouvrages_qs, scope)

    ouvrages_recent = ouvrages_qs.order_by('nom_ouvrage')[:8]
    point_eaux_count = PointEau.objects.filter(ouvrage__in=ouvrages_qs).distinct().count()
    modalites_count = ModaliteGestion.objects.filter(
        statut='actif', date_debut__lte=timezone.localdate(),
        ouvrage__in=ouvrages_qs,
    ).filter(
        Q(date_fin__isnull=True) | Q(date_fin__gte=timezone.localdate())
    ).distinct().count()

    ouvrages_by_type = []
    for type_ouvrage in types_ouvrages[:8]:
        count = ouvrages_qs.filter(type_ouvrage=type_ouvrage).count()
        if not count:
            continue
        ouvrages_by_type.append({
            'type': type_ouvrage,
            'count': count,
        })

    context = _extend_context_with_ouvrages_scope({
        'title': 'Pilotage des ouvrages',
        'types_ouvrages': types_ouvrages,
        'ouvrages_recent': ouvrages_recent,
        **filter_context,
        'stats': {
            'ouvrages': ouvrages_qs.count(),
            'types_ouvrages': types_ouvrages.count(),
            'points_eau': point_eaux_count,
            'modalites_actives': modalites_count,
        },
        'ouvrages_by_type': ouvrages_by_type,
        'logic_blocks': [
            {
                'title': 'Dossier ouvrage',
                'description': "Identité, type, localisation, observations, saisonnalité et pièces techniques.",
                'url': '/liste/',
                'cta': 'Ouvrir les ouvrages',
                'icon': 'fas fa-folder-open',
            },
            {
                'title': 'Référentiel',
                'description': "Normaliser les types d'ouvrages avant de structurer les tâches et obligations.",
                'url': '/types/',
                'cta': "Gérer les types",
                'icon': 'fas fa-sitemap',
            },
            {
                'title': 'Vue cascade',
                'description': "Relier ouvrage, point d'eau, équipements, compteurs, tarifs et modalités de gestion.",
                'url': '/cascade/',
                'cta': 'Voir la cascade',
                'icon': 'fas fa-diagram-project',
            },
            {
                'title': 'Gestion complète',
                'description': "Créer et mettre à jour rapidement les informations opérationnelles autour des ouvrages.",
                'url': '/gestion-complete/',
                'cta': 'Ouvrir la gestion',
                'icon': 'fas fa-sliders',
            },
        ],
    }, scope, request=request)
    return render(request, 'ouvrages/home.html', context)

def ouvrages_home(request):
    """Page d'accueil pour la gestion des ouvrages"""
    scope, _, _ = _get_ouvrages_scope(request)
    types_ouvrages = OrgTypeOuvrage.objects.all().order_by('nom_type_ouvrage')
    ouvrages_recent = _apply_ouvrages_scope(_ouvrages_subdomain_queryset(), scope).order_by('-id')[:5]

    return render(request, 'ouvrages/ouvrages_home.html', _extend_context_with_ouvrages_scope({
        'types_ouvrages': types_ouvrages,
        'ouvrages_recent': ouvrages_recent,
        'title': 'Gestion des Ouvrages'
    }, scope, request=request))


def ouvrages_dashboard(request):
    """Tableau de bord avec vue d'ensemble des ouvrages et donn?es en cascade"""
    scope, _, _ = _get_ouvrages_scope(request)
    ouvrages = _apply_ouvrages_scope(
        _ouvrages_subdomain_queryset().select_related('type_ouvrage'),
        scope,
    ).order_by('nom_ouvrage')
    return render(request, 'ouvrages/dashboard.html', _extend_context_with_ouvrages_scope({
        'title': 'Tableau de bord des ouvrages',
        'ouvrages': ouvrages[:10],
        'stats': {
            'ouvrages': ouvrages.count(),
            'types': OrgTypeOuvrage.objects.count(),
            'points_eau': PointEau.objects.count(),
            'modalites': ModaliteGestion.objects.filter(date_fin__isnull=True).count(),
        }
    }, scope, request=request))

def type_ouvrage_list(request):
    scope, _, _ = _get_ouvrages_scope(request)
    types_ouvrages = OrgTypeOuvrage.objects.all().order_by('nom_type_ouvrage')
    return render(request, 'ouvrages/type_ouvrage_list.html', _extend_context_with_ouvrages_scope({
        'types_ouvrages': types_ouvrages,
        'title': 'Types d\'Ouvrages'
    }, scope, request=request))

def type_ouvrage_create(request):
    scope, _, _ = _get_ouvrages_scope(request)
    if request.method == 'POST':
        form = TypeOuvrageForm(request.POST)
        if form.is_valid():
            type_ouvrage = form.save()

            # Gérer les requêtes AJAX
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': 'Type d\'ouvrage créé avec succès!',
                    'id': str(type_ouvrage.id)
                })

            messages.success(request, 'Type d\'ouvrage créé avec succès!')
            return redirect('ouvrages:type_ouvrage_list')
        else:
            # Gérer les erreurs pour les requêtes AJAX
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'errors': form.errors
                }, status=400)

            messages.error(request, 'Erreur dans le formulaire. Veuillez vérifier les champs.')
    else:
        form = TypeOuvrageForm()

    return render(request, 'ouvrages/type_ouvrage_form.html', _extend_context_with_ouvrages_scope({
        'form': form,
        'title': 'Nouveau Type d\'Ouvrage'
    }, scope, request=request))


def type_ouvrage_detail(request, pk):
    scope, _, _ = _get_ouvrages_scope(request)
    type_ouvrage = get_object_or_404(OrgTypeOuvrage, pk=pk)
    ouvrages = type_ouvrage.ouvrages.all().order_by('nom_ouvrage')
    return render(request, 'ouvrages/type_ouvrage_detail.html', _extend_context_with_ouvrages_scope({
        'type_ouvrage': type_ouvrage,
        'ouvrages': ouvrages[:20],
        'title': f'Type d\'ouvrage: {type_ouvrage.nom_type_ouvrage}'
    }, scope, request=request))


def type_ouvrage_update(request, pk):
    scope, _, _ = _get_ouvrages_scope(request)
    type_ouvrage = get_object_or_404(OrgTypeOuvrage, pk=pk)
    if request.method == 'POST':
        form = TypeOuvrageForm(request.POST, instance=type_ouvrage)
        if form.is_valid():
            form.save()

            # Gérer les requêtes AJAX
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': 'Type d\'ouvrage modifié avec succès!'
                })

            messages.success(request, 'Type d\'ouvrage modifié avec succès!')
            return redirect('ouvrages:type_ouvrage_detail', pk=pk)
        else:
            # Gérer les erreurs pour les requêtes AJAX
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'errors': form.errors
                }, status=400)

            messages.error(request, 'Erreur dans le formulaire. Veuillez vérifier les champs.')
    else:
        form = TypeOuvrageForm(instance=type_ouvrage)

    return render(request, 'ouvrages/type_ouvrage_form.html', _extend_context_with_ouvrages_scope({
        'form': form,
        'type_ouvrage': type_ouvrage,
        'title': f'Modifier: {type_ouvrage.nom_type_ouvrage}'
    }, scope, request=request))


def type_ouvrage_delete(request, pk):
    scope, _, _ = _get_ouvrages_scope(request)
    type_ouvrage = get_object_or_404(OrgTypeOuvrage, pk=pk)
    if request.method == 'POST':
        type_ouvrage.delete()
        messages.success(request, 'Type d\'ouvrage supprimé avec succès!')
        return redirect('ouvrages:type_ouvrage_list')

    return render(request, 'ouvrages/type_ouvrage_confirm_delete.html', _extend_context_with_ouvrages_scope({
        'type_ouvrage': type_ouvrage,
        'title': f'Supprimer: {type_ouvrage.nom_type_ouvrage}'
    }, scope, request=request))


# CRUD pour les Ouvrages
def ouvrage_list(request):
    scope, _, _ = _get_ouvrages_scope(request)
    page_number = request.GET.get('page') or 1
    current_year = datetime.now().year
    points_eau_qs = PointEau.objects.select_related(
        'type_point_eau',
        'parcelle__village__fokontany__commune__district__region',
    ).order_by('nomabonne', 'code_point_eau')
    equipements_qs = EquipementConstitutif.objects.select_related('type_equipement').order_by('nom')

    ouvrages_qs = _apply_ouvrages_scope(
        _ouvrages_subdomain_queryset().select_related('type_ouvrage').prefetch_related(
            Prefetch('pointeau_set', queryset=points_eau_qs),
            Prefetch('equipements_constitutifs', queryset=equipements_qs),
        ),
        scope,
    ).order_by('nom_ouvrage')

    unique_ouvrages = []
    seen_ouvrage_ids = set()
    for ouvrage in ouvrages_qs:
        ouvrage_id = str(ouvrage.pk)
        if ouvrage_id in seen_ouvrage_ids:
            continue
        seen_ouvrage_ids.add(ouvrage_id)
        unique_ouvrages.append(ouvrage)

    grouped_map = {}

    def _location_parts(point_eau):
        parcelle = getattr(point_eau, 'parcelle', None)
        village = getattr(parcelle, 'village', None)
        fokontany = getattr(village, 'fokontany', None)
        commune = getattr(fokontany, 'commune', None)
        district = getattr(commune, 'district', None)
        region = getattr(district, 'region', None)
        return (
            getattr(region, 'nom_region', None) or 'Sans région',
            getattr(district, 'nom_district', None) or 'Sans district',
            getattr(commune, 'nom_commune', None) or 'Sans commune',
        )

    for ouvrage in unique_ouvrages:
        points_eau = list(getattr(ouvrage, 'pointeau_set').all())
        equipements = list(getattr(ouvrage, 'equipements_constitutifs').all())
        first_point = points_eau[0] if points_eau else None
        region_name, district_name, commune_name = _location_parts(first_point) if first_point else (
            'Sans région',
            'Sans district',
            'Sans commune',
        )

        nettoyage_values = {
            str(eq.nombre_nettoyages_annuels)
            for eq in equipements
            if getattr(eq, 'nombre_nettoyages_annuels', None) is not None
        }
        if '12' in nettoyage_values:
            nettoyage_selection = '12'
        elif '6' in nettoyage_values:
            nettoyage_selection = '6'
        else:
            nettoyage_selection = '0.3'

        ouvrage.region_name = region_name
        ouvrage.district_name = district_name
        ouvrage.commune_name = commune_name
        ouvrage.points_eau_count = len(points_eau)
        ouvrage.equipements_count = len(equipements)
        ouvrage.nettoyage_selection = nettoyage_selection
        ouvrage.problematique_max = max(
            [getattr(point_eau, 'problematique_paiement', 0) or 0 for point_eau in points_eau],
            default=0,
        )
        annee_realisation = getattr(ouvrage, 'annee_realisation', None)
        if annee_realisation:
            try:
                ouvrage.age_ouvrage = max(0, round(current_year - int(annee_realisation)))
            except (TypeError, ValueError):
                ouvrage.age_ouvrage = None
        else:
            ouvrage.age_ouvrage = None

        grouped_map.setdefault(region_name, {}).setdefault(district_name, {}).setdefault(commune_name, []).append(ouvrage)

    commune_groups = []
    for region_name in sorted(grouped_map):
        for district_name in sorted(grouped_map[region_name]):
            for commune_name in sorted(grouped_map[region_name][district_name]):
                commune_groups.append({
                    'region_name': region_name,
                    'district_name': district_name,
                    'name': commune_name,
                    'ouvrages': grouped_map[region_name][district_name][commune_name],
                    'ouvrage_count': len(grouped_map[region_name][district_name][commune_name]),
                })

    grouped_pages = []
    current_page_groups = []
    current_page_ouvrage_count = 0
    max_ouvrages_per_page = 10

    for commune_group in commune_groups:
        commune_ouvrage_count = commune_group['ouvrage_count']
        if current_page_groups and current_page_ouvrage_count + commune_ouvrage_count > max_ouvrages_per_page:
            grouped_pages.append(current_page_groups)
            current_page_groups = []
            current_page_ouvrage_count = 0

        current_page_groups.append(commune_group)
        current_page_ouvrage_count += commune_ouvrage_count

    if current_page_groups:
        grouped_pages.append(current_page_groups)

    paginator = Paginator(grouped_pages or [[]], 1)
    page_obj = paginator.get_page(page_number)
    page_commune_groups = list(page_obj.object_list[0]) if page_obj.object_list else []

    grouped_ouvrages = []
    grouped_page_map = {}
    page_ouvrages = []
    cascade_points_eau = []
    cascade_equipements = []

    for commune_group in page_commune_groups:
        region_name = commune_group['region_name']
        district_name = commune_group['district_name']
        commune_name = commune_group['name']
        ouvrages = commune_group['ouvrages']

        grouped_page_map.setdefault(region_name, {}).setdefault(district_name, []).append({
            'name': commune_name,
            'ouvrages': ouvrages,
            'ouvrage_count': len(ouvrages),
        })

        for ouvrage in ouvrages:
            page_ouvrages.append(ouvrage)
            points_eau = list(getattr(ouvrage, 'pointeau_set').all())
            equipements = list(getattr(ouvrage, 'equipements_constitutifs').all())

            for point_eau in points_eau:
                pe_region, pe_district, pe_commune = _location_parts(point_eau)
                cascade_points_eau.append({
                    'ouvrage': ouvrage,
                    'point_eau': point_eau,
                    'region_name': pe_region,
                    'district_name': pe_district,
                    'commune_name': pe_commune,
                    'problematique_paiement': getattr(point_eau, 'problematique_paiement', 0) or 0,
                    'problematique_commentaire': getattr(point_eau, 'problematique_commentaire', '') or '',
                })

            for equipement in equipements:
                cascade_equipements.append({
                    'ouvrage': ouvrage,
                    'equipement': equipement,
                    'nettoyage': getattr(equipement, 'nombre_nettoyages_annuels', None),
                    'particularite_equipement': getattr(equipement, 'particularite_equipement', '') or '',
                })

    for region_name in sorted(grouped_page_map):
        districts_payload = []
        region_ouvrage_count = 0
        for district_name in sorted(grouped_page_map[region_name]):
            district_communes = grouped_page_map[region_name][district_name]
            district_ouvrage_count = sum(item['ouvrage_count'] for item in district_communes)
            region_ouvrage_count += district_ouvrage_count
            districts_payload.append({
                'name': district_name,
                'communes': district_communes,
                'ouvrage_count': district_ouvrage_count,
            })
        grouped_ouvrages.append({
            'name': region_name,
            'districts': districts_payload,
            'ouvrage_count': region_ouvrage_count,
        })

    pagination_query = urlencode({key: value for key, value in scope.items() if value})
    stats = {
        'total_ouvrages': len(unique_ouvrages),
        'total_saisonniers': len([ouvrage for ouvrage in unique_ouvrages if getattr(ouvrage, 'saisonnier', False)]),
        'total_points_eau': PointEau.objects.filter(ouvrage__in=unique_ouvrages).distinct().count(),
        'total_equipements': EquipementConstitutif.objects.filter(ouvrage__in=unique_ouvrages).distinct().count(),
    }

    return render(request, 'ouvrages/ouvrage_list.html', _extend_context_with_ouvrages_scope({
        'ouvrages': page_ouvrages,
        'grouped_ouvrages': grouped_ouvrages,
        'cascade_points_eau': cascade_points_eau,
        'cascade_equipements': cascade_equipements,
        'problematique_legend': PROBLEMATIQUE_PAIEMENT_LEGEND,
        'page_obj': page_obj,
        'page_ouvrages_count': len(page_ouvrages),
        'page_start_ouvrage': sum(len(page) for page in grouped_pages[:page_obj.number - 1]) + 1 if page_ouvrages else 0,
        'page_end_ouvrage': sum(len(page) for page in grouped_pages[:page_obj.number - 1]) + len(page_ouvrages) if page_ouvrages else 0,
        'pagination_query': pagination_query,
        'stats': stats,
        'title': 'Ouvrages'
    }, scope, request=request))

def ouvrage_create(request):
    scope, _, _ = _get_ouvrages_scope(request)
    if request.method == 'POST':
        form = OuvrageForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Ouvrage créé avec succès!')
            return redirect('ouvrages:ouvrage_list')
        else:
            messages.error(request, 'Erreur dans le formulaire. Veuillez vérifier les champs.')
    else:
        form = OuvrageForm()

    return render(request, 'ouvrages/ouvrage_form.html', _extend_context_with_ouvrages_scope({
        'form': form,
        'title': 'Nouvel Ouvrage'
    }, scope, request=request))


def point_eau_problematique_update(request, pk):
    scope, _, _ = _get_ouvrages_scope(request)
    point_eau = get_object_or_404(PointEau.objects.select_related('ouvrage'), pk=pk)
    next_url = request.GET.get('next') or request.POST.get('next') or redirect('ouvrages:ouvrage_list').url

    if request.method == 'POST':
        form = PointEauProblematiqueForm(request.POST, instance=point_eau)
        if form.is_valid():
            form.save()
            messages.success(request, "Problématique de paiement mise à jour.")
            return redirect(next_url)
        messages.error(request, "Le formulaire contient des erreurs.")
    else:
        form = PointEauProblematiqueForm(instance=point_eau)

    return render(request, 'ouvrages/point_eau_problematique_form.html', _extend_context_with_ouvrages_scope({
        'form': form,
        'point_eau': point_eau,
        'next_url': next_url,
        'problematique_legend': PROBLEMATIQUE_PAIEMENT_LEGEND,
        'title': f"Problématique paiement - {point_eau.code_point_eau or point_eau.nomabonne}",
    }, scope, request=request))


def equipement_maintenance_update(request, pk):
    equipement = get_object_or_404(EquipementConstitutif, pk=pk)
    next_url = request.GET.get('next') or request.POST.get('next') or redirect('ouvrages:ouvrage_list').url

    if request.method == 'POST':
        form = EquipementMaintenanceForm(request.POST, instance=equipement)
        if form.is_valid():
            form.save()
            messages.success(request, "Équipement mis à jour.")
        else:
            messages.error(request, "Le formulaire contient des erreurs.")

    return redirect(next_url)


def ouvrage_detail(request, pk):
    scope, _, _ = _get_ouvrages_scope(request)
    ouvrage = get_object_or_404(OrgOuvrage, pk=pk)
    bases = ouvrage.bases.all().order_by('nom_base')
    return render(request, 'ouvrages/ouvrage_detail.html', _extend_context_with_ouvrages_scope({
        'ouvrage': ouvrage,
        'bases': bases,
        'title': f'Ouvrage: {ouvrage.nom_ouvrage}'
    }, scope, request=request))


def ouvrage_update(request, pk):
    scope, _, _ = _get_ouvrages_scope(request)
    ouvrage = get_object_or_404(OrgOuvrage, pk=pk)
    if request.method == 'POST':
        form = OuvrageForm(request.POST, instance=ouvrage)
        if form.is_valid():
            form.save()
            messages.success(request, 'Ouvrage modifié avec succès!')
            return redirect('ouvrages:ouvrage_detail', pk=pk)
        else:
            messages.error(request, 'Erreur dans le formulaire. Veuillez vérifier les champs.')
    else:
        form = OuvrageForm(instance=ouvrage)

    return render(request, 'ouvrages/ouvrage_form.html', _extend_context_with_ouvrages_scope({
        'form': form,
        'ouvrage': ouvrage,
        'title': f'Modifier: {ouvrage.nom_ouvrage}'
    }, scope, request=request))


def ouvrage_delete(request, pk):
    scope, _, _ = _get_ouvrages_scope(request)
    ouvrage = get_object_or_404(OrgOuvrage, pk=pk)
    if request.method == 'POST':
        ouvrage.delete()
        messages.success(request, 'Ouvrage supprimé avec succès!')
        return redirect('ouvrages:ouvrage_list')

    return render(request, 'ouvrages/ouvrage_confirm_delete.html', _extend_context_with_ouvrages_scope({
        'ouvrage': ouvrage,
        'title': f'Supprimer: {ouvrage.nom_ouvrage}'
    }, scope, request=request))


# Vue pour la page CRUD en cascade
def ouvrages_cascade(request):
    """Page de gestion compl?te des ouvrages avec tous les composants en cascade"""
    scope, _, _ = _get_ouvrages_scope(request)
    return render(request, 'ouvrages/cascade.html', _extend_context_with_ouvrages_scope({
        'title': 'Vue cascade des ouvrages'
    }, scope, request=request))

def api_ouvrages(request):
    """API pour récupérer tous les ouvrages"""
    try:
        ouvrages = _ouvrages_subdomain_queryset().select_related('typeouvrage')
        data = []
        for ouvrage in ouvrages:
            data.append({
                'id': str(ouvrage.id),
                'nom': ouvrage.nom,
                'typeouvrage_id': str(ouvrage.typeouvrage.id) if ouvrage.typeouvrage else None,
                'typeouvrage_nom': ouvrage.typeouvrage.nomtype if ouvrage.typeouvrage else None,
                'anneerealisation': ouvrage.anneerealisation,
                'anneerealisationavant': ouvrage.anneerealisationavant,
                'intervenant': ouvrage.intervenant,
                'remarque': ouvrage.remarque,
                'estsaisonnier': ouvrage.estsaisonnier,
                'photos': ouvrage.photos,
                'idxls': ouvrage.idxls,
            })
        return JsonResponse(data, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def ouvrages_gestion_complete(request):
    """Vue pour la gestion compl?te avec formulaires en cascade"""
    scope, _, _ = _get_ouvrages_scope(request)
    ouvrages = _apply_ouvrages_scope(
        _ouvrages_subdomain_queryset().select_related('type_ouvrage'),
        scope,
    ).order_by('nom_ouvrage')

    context = _extend_context_with_ouvrages_scope({
        'title': 'Gestion Compl?te des Ouvrages',
        'ouvrages': ouvrages[:20],
    }, scope, request=request)
    return render(request, 'ouvrages/gestion_complete.html', context)

def export_tarifs_excel(request):
    """Export des tarifs volumétriques avec tranches vers Excel"""
    try:
        # Créer un nouveau workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Tarifs Volumétriques"

        # Styles
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True, size=12)
        border_style = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        # En-têtes
        headers = [
            'ID Tarif', 'Ouvrage', 'Date Début', 'Date Fin',
            'Prix Abonnement', 'Actif', 'Tranche Supérieure (m³)', 'Tarif (Ar/m³)'
        ]

        for col, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col)
            cell.value = header
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = border_style

        # Récupérer tous les tarifs avec leurs tranches
        tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('ouvrage__nom', '-datedebuttarif')

        row = 2
        for tarif in tarifs:
            tranches = tarif.tranches.all().order_by('tranchesuperieur')

            if tranches.exists():
                # Si le tarif a des tranches, une ligne par tranche
                for tranche in tranches:
                    ws.cell(row=row, column=1).value = str(tarif.id)
                    ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                    ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                    ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                    ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                    ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                    ws.cell(row=row, column=7).value = int(tranche.tranchesuperieur) if tranche.tranchesuperieur else 0
                    ws.cell(row=row, column=8).value = int(tranche.tarif) if tranche.tarif else 0

                    # Appliquer les bordures
                    for col in range(1, 9):
                        ws.cell(row=row, column=col).border = border_style

                    row += 1
            else:
                # Si le tarif n'a pas de tranches, une ligne vide pour les tranches
                ws.cell(row=row, column=1).value = str(tarif.id)
                ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                ws.cell(row=row, column=7).value = ''
                ws.cell(row=row, column=8).value = ''

                # Appliquer les bordures
                for col in range(1, 9):
                    ws.cell(row=row, column=col).border = border_style

                row += 1

        # Ajuster la largeur des colonnes
        column_widths = [35, 30, 15, 15, 18, 10, 22, 18]
        for col, width in enumerate(column_widths, start=1):
            ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = width

        # Créer la réponse HTTP avec le fichier Excel
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename=tarifs_volumetriques_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'

        wb.save(response)
        return response

    except Exception as e:
        messages.error(request, f'Erreur lors de l\'export Excel : {str(e)}')
        return redirect('ouvrages:gestion_complete')


@csrf_exempt
def import_tarifs_excel(request):
    """Import des tarifs volumétriques avec tranches depuis Excel"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        updated_count = 0
        errors = []

        # Dictionnaire pour regrouper les tranches par tarif
        tarifs_data = {}

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    ouvrage_nom = str(row[1]).strip() if row[1] else None
                    date_debut_str = str(row[2]).strip() if row[2] else None
                    date_fin_str = str(row[3]).strip() if row[3] else None
                    prix_abonnement = row[4] if row[4] is not None else 0
                    actif_str = str(row[5]).strip().lower() if row[5] else 'oui'
                    tranche_superieur = row[6] if row[6] is not None else None
                    tarif_tranche = row[7] if row[7] is not None else None

                    # Validation des champs obligatoires
                    if not ouvrage_nom or not date_debut_str:
                        errors.append(f"Ligne {row_num}: Ouvrage et Date Début sont obligatoires")
                        continue

                    # Récupérer l'ouvrage
                    try:
                        ouvrage = _ouvrages_subdomain_queryset().get(nom_ouvrage=ouvrage_nom)
                    except OrgOuvrage.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Ouvrage '{ouvrage_nom}' introuvable")
                        continue

                    # Parser les dates
                    try:
                        date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
                    except ValueError:
                        errors.append(f"Ligne {row_num}: Format de date début invalide (attendu: AAAA-MM-JJ)")
                        continue

                    date_fin = None
                    if date_fin_str and date_fin_str != 'None':
                        try:
                            date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
                        except ValueError:
                            errors.append(f"Ligne {row_num}: Format de date fin invalide (attendu: AAAA-MM-JJ)")
                            continue

                    actif = actif_str in ['oui', 'yes', 'true', '1']

                    # Créer ou récupérer le tarif volumétrique
                    if tarif_id and tarif_id != 'None':
                        # Mise à jour d'un tarif existant
                        try:
                            tarif = TarifVolumetrique.objects.get(id=tarif_id)
                            tarif.ouvrage = ouvrage
                            tarif.datedebuttarif = date_debut
                            tarif.datefintarif = date_fin
                            tarif.prixabonnement = prix_abonnement
                            tarif.actif = actif
                            tarif.save()

                            # Utiliser l'ID du tarif comme clé
                            tarif_key = str(tarif.id)
                            if tarif_key not in tarifs_data:
                                tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': True}

                        except TarifVolumetrique.DoesNotExist:
                            errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                            continue
                    else:
                        # Créer un nouveau tarif (générer une clé unique basée sur ouvrage + date)
                        tarif_key = f"{ouvrage.id}_{date_debut}"

                        if tarif_key not in tarifs_data:
                            tarif = TarifVolumetrique.objects.create(
                                ouvrage=ouvrage,
                                datedebuttarif=date_debut,
                                datefintarif=date_fin,
                                prixabonnement=prix_abonnement,
                                actif=actif
                            )
                            tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': False}
                        else:
                            tarif = tarifs_data[tarif_key]['tarif']

                    # Ajouter la tranche si elle existe (utiliser la même clé)
                    if tranche_superieur is not None and tarif_tranche is not None:
                        if tarif_key in tarifs_data:
                            tarifs_data[tarif_key]['tranches'].append({
                                'tranchesuperieur': int(tranche_superieur),
                                'tarif': int(tarif_tranche)
                            })

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

            # Créer les tranches pour chaque tarif
            tranches_count = 0
            for tarif_key, data in tarifs_data.items():
                tarif = data['tarif']

                # Supprimer les anciennes tranches si c'est une mise à jour
                if data['updated']:
                    TarifVolumetrique2.objects.filter(tarifvolumetrique=tarif).delete()
                    updated_count += 1
                else:
                    imported_count += 1

                # Créer les nouvelles tranches
                for tranche_data in data['tranches']:
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=tranche_data['tranchesuperieur'],
                        tarif=tranche_data['tarif']
                    )
                    tranches_count += 1

        response_data = {
            'success': True,
            'imported': imported_count,
            'updated': updated_count,
            'tranches_created': tranches_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


@csrf_exempt
def import_tranches_only(request):
    """Import UNIQUEMENT des tranches (3 colonnes: tarif_id, tranche_superieur, tarif)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        errors = []

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    tranche_superieur = row[1] if row[1] is not None else None
                    tarif_prix = row[2] if row[2] is not None else None

                    # Validation des champs obligatoires
                    if not tarif_id or tranche_superieur is None or tarif_prix is None:
                        errors.append(f"Ligne {row_num}: Tous les champs sont obligatoires (tarif_id, tranche_superieur, tarif)")
                        continue

                    # Récupérer le tarif volumétrique
                    try:
                        tarif = TarifVolumetrique.objects.get(id=tarif_id)
                    except TarifVolumetrique.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                        continue

                    # Créer la tranche
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=int(tranche_superieur),
                        tarif=int(tarif_prix)
                    )
                    imported_count += 1

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

        response_data = {
            'success': True,
            'imported': imported_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


def export_template_tranches(request):
    """Exporter un template Excel vide pour l'import de tranches"""
    wb = Workbook()
    ws = wb.active
    ws.title = "Tranches Template"

    # En-têtes
    headers = ['tarif_id', 'tranche_superieur', 'tarif']
    ws.append(headers)

    # Styles
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")

    for col_num, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center', vertical='center')

    # Ajuster les largeurs
    ws.column_dimensions['A'].width = 40  # UUID
    ws.column_dimensions['B'].width = 20
    ws.column_dimensions['C'].width = 20

    # Ajouter quelques exemples commentés
    ws.append(['# Exemple: ID du tarif volumétrique', '5', '500'])
    ws.append(['# Copiez un UUID de tarif depuis la liste des tarifs', '10', '800'])
    ws.append(['# Une ligne = une tranche', '20', '1000'])

    # Réponse HTTP
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="template_tranches_import.xlsx"'
    wb.save(response)
    return response


def tarifs_import_export_page(request):
    """Page pour l'import/export des tarifs volumétriques"""
    tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('-datedebuttarif')[:50]

    context = {
        'title': 'Import/Export Tarifs Volumétriques',
        'tarifs': tarifs,
    }
    return render(request, 'ouvrages/tarifs_import_export.html', context)


def ouvrages_gestion_complete(request):
    ouvrages = _ouvrages_subdomain_queryset().select_related('type_ouvrage').order_by('nom_ouvrage')

    context = {
        'title': 'Gestion Complète des Ouvrages',
        'ouvrages': ouvrages[:20],
    }
    return render(request, 'ouvrages/gestion_complete.html', context)


def ouvrages_gestion_complete(request):
    """Version finale stable de la vue de gestion complete pour le sous-domaine ouvrages."""
    ouvrages = _ouvrages_subdomain_queryset().select_related('type_ouvrage').order_by('nom_ouvrage')

    context = {
        'title': 'Gestion Complète des Ouvrages',
        'ouvrages': ouvrages[:20],
    }
    return render(request, 'ouvrages/gestion_complete.html', context)


def api_pointseaus(request):
    """API pour récupérer tous les points d'eau"""
    try:
        pointseaus = PointEau.objects.all().select_related('ouvrage', 'compteur_tete')
        data = []
        for pointeau in pointseaus:
            data.append({
                'id': str(pointeau.id),
                'nomabonne': pointeau.nomabonne,
                'contactabonne': pointeau.contactabonne,
                'ouvrage_id': str(pointeau.ouvrage.id) if pointeau.ouvrage else None,
                'compteur_tete_id': str(pointeau.compteur_tete.id) if pointeau.compteur_tete else None,
                'typeabonne': pointeau.typeabonne,
                'datebranchement': pointeau.datebranchement.isoformat() if pointeau.datebranchement else None,
                'datearretbranchement': pointeau.datearretbranchement.isoformat() if pointeau.datearretbranchement else None,
                'latitude': pointeau.latitude,
                'longitude': pointeau.longitude,
                'estbranchementinstitutionnel': pointeau.estbranchementinstitutionnel,
                'tarifforfaitaire': float(pointeau.tarifforfaitaire) if pointeau.tarifforfaitaire else None,
                'montantdemandepaye': float(pointeau.montantdemandepaye) if pointeau.montantdemandepaye else None,
                'montantdevispaye': float(pointeau.montantdevispaye) if pointeau.montantdevispaye else None,
                'is_active': pointeau.is_active,
            })
        return JsonResponse(data, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def ouvrages_gestion_complete(request):
    """Vue pour la gestion complète avec formulaires en cascade"""
    ouvrages = _ouvrages_subdomain_queryset().select_related('type_ouvrage').order_by('nom_ouvrage')

    context = {
        'title': 'Gestion Complète des Ouvrages',
        'ouvrages': ouvrages[:20],
    }
    return render(request, 'ouvrages/gestion_complete.html', context)


# ========== IMPORT/EXPORT EXCEL POUR TARIFS VOLUMÉTRIQUES ==========

def export_tarifs_excel(request):
    """Export des tarifs volumétriques avec tranches vers Excel"""
    try:
        # Créer un nouveau workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Tarifs Volumétriques"

        # Styles
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True, size=12)
        border_style = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        # En-têtes
        headers = [
            'ID Tarif', 'Ouvrage', 'Date Début', 'Date Fin',
            'Prix Abonnement', 'Actif', 'Tranche Supérieure (m³)', 'Tarif (Ar/m³)'
        ]

        for col, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col)
            cell.value = header
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = border_style

        # Récupérer tous les tarifs avec leurs tranches
        tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('ouvrage__nom', '-datedebuttarif')

        row = 2
        for tarif in tarifs:
            tranches = tarif.tranches.all().order_by('tranchesuperieur')

            if tranches.exists():
                # Si le tarif a des tranches, une ligne par tranche
                for tranche in tranches:
                    ws.cell(row=row, column=1).value = str(tarif.id)
                    ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                    ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                    ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                    ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                    ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                    ws.cell(row=row, column=7).value = int(tranche.tranchesuperieur) if tranche.tranchesuperieur else 0
                    ws.cell(row=row, column=8).value = int(tranche.tarif) if tranche.tarif else 0

                    # Appliquer les bordures
                    for col in range(1, 9):
                        ws.cell(row=row, column=col).border = border_style

                    row += 1
            else:
                # Si le tarif n'a pas de tranches, une ligne vide pour les tranches
                ws.cell(row=row, column=1).value = str(tarif.id)
                ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                ws.cell(row=row, column=7).value = ''
                ws.cell(row=row, column=8).value = ''

                # Appliquer les bordures
                for col in range(1, 9):
                    ws.cell(row=row, column=col).border = border_style

                row += 1

        # Ajuster la largeur des colonnes
        column_widths = [35, 30, 15, 15, 18, 10, 22, 18]
        for col, width in enumerate(column_widths, start=1):
            ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = width

        # Créer la réponse HTTP avec le fichier Excel
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename=tarifs_volumetriques_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'

        wb.save(response)
        return response

    except Exception as e:
        messages.error(request, f'Erreur lors de l\'export Excel : {str(e)}')
        return redirect('ouvrages:gestion_complete')


@csrf_exempt
def import_tarifs_excel(request):
    """Import des tarifs volumétriques avec tranches depuis Excel"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        updated_count = 0
        errors = []

        # Dictionnaire pour regrouper les tranches par tarif
        tarifs_data = {}

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    ouvrage_nom = str(row[1]).strip() if row[1] else None
                    date_debut_str = str(row[2]).strip() if row[2] else None
                    date_fin_str = str(row[3]).strip() if row[3] else None
                    prix_abonnement = row[4] if row[4] is not None else 0
                    actif_str = str(row[5]).strip().lower() if row[5] else 'oui'
                    tranche_superieur = row[6] if row[6] is not None else None
                    tarif_tranche = row[7] if row[7] is not None else None

                    # Validation des champs obligatoires
                    if not ouvrage_nom or not date_debut_str:
                        errors.append(f"Ligne {row_num}: Ouvrage et Date Début sont obligatoires")
                        continue

                    # Récupérer l'ouvrage
                    try:
                        ouvrage = _ouvrages_subdomain_queryset().get(nom_ouvrage=ouvrage_nom)
                    except OrgOuvrage.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Ouvrage '{ouvrage_nom}' introuvable")
                        continue

                    # Parser les dates
                    try:
                        date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
                    except ValueError:
                        errors.append(f"Ligne {row_num}: Format de date début invalide (attendu: AAAA-MM-JJ)")
                        continue

                    date_fin = None
                    if date_fin_str and date_fin_str != 'None':
                        try:
                            date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
                        except ValueError:
                            errors.append(f"Ligne {row_num}: Format de date fin invalide (attendu: AAAA-MM-JJ)")
                            continue

                    actif = actif_str in ['oui', 'yes', 'true', '1']

                    # Créer ou récupérer le tarif volumétrique
                    if tarif_id and tarif_id != 'None':
                        # Mise à jour d'un tarif existant
                        try:
                            tarif = TarifVolumetrique.objects.get(id=tarif_id)
                            tarif.ouvrage = ouvrage
                            tarif.datedebuttarif = date_debut
                            tarif.datefintarif = date_fin
                            tarif.prixabonnement = prix_abonnement
                            tarif.actif = actif
                            tarif.save()

                            # Utiliser l'ID du tarif comme clé
                            tarif_key = str(tarif.id)
                            if tarif_key not in tarifs_data:
                                tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': True}

                        except TarifVolumetrique.DoesNotExist:
                            errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                            continue
                    else:
                        # Créer un nouveau tarif (générer une clé unique basée sur ouvrage + date)
                        tarif_key = f"{ouvrage.id}_{date_debut}"

                        if tarif_key not in tarifs_data:
                            tarif = TarifVolumetrique.objects.create(
                                ouvrage=ouvrage,
                                datedebuttarif=date_debut,
                                datefintarif=date_fin,
                                prixabonnement=prix_abonnement,
                                actif=actif
                            )
                            tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': False}
                        else:
                            tarif = tarifs_data[tarif_key]['tarif']

                    # Ajouter la tranche si elle existe (utiliser la même clé)
                    if tranche_superieur is not None and tarif_tranche is not None:
                        if tarif_key in tarifs_data:
                            tarifs_data[tarif_key]['tranches'].append({
                                'tranchesuperieur': int(tranche_superieur),
                                'tarif': int(tarif_tranche)
                            })

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

            # Créer les tranches pour chaque tarif
            tranches_count = 0
            for tarif_key, data in tarifs_data.items():
                tarif = data['tarif']

                # Supprimer les anciennes tranches si c'est une mise à jour
                if data['updated']:
                    TarifVolumetrique2.objects.filter(tarifvolumetrique=tarif).delete()
                    updated_count += 1
                else:
                    imported_count += 1

                # Créer les nouvelles tranches
                for tranche_data in data['tranches']:
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=tranche_data['tranchesuperieur'],
                        tarif=tranche_data['tarif']
                    )
                    tranches_count += 1

        response_data = {
            'success': True,
            'imported': imported_count,
            'updated': updated_count,
            'tranches_created': tranches_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


@csrf_exempt
def import_tranches_only(request):
    """Import UNIQUEMENT des tranches (3 colonnes: tarif_id, tranche_superieur, tarif)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        errors = []

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    tranche_superieur = row[1] if row[1] is not None else None
                    tarif_prix = row[2] if row[2] is not None else None

                    # Validation des champs obligatoires
                    if not tarif_id or tranche_superieur is None or tarif_prix is None:
                        errors.append(f"Ligne {row_num}: Tous les champs sont obligatoires (tarif_id, tranche_superieur, tarif)")
                        continue

                    # Récupérer le tarif volumétrique
                    try:
                        tarif = TarifVolumetrique.objects.get(id=tarif_id)
                    except TarifVolumetrique.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                        continue

                    # Créer la tranche
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=int(tranche_superieur),
                        tarif=int(tarif_prix)
                    )
                    imported_count += 1

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

        response_data = {
            'success': True,
            'imported': imported_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


def tarifs_import_export_page(request):
    """Page pour l'import/export des tarifs volumétriques"""
    tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('-datedebuttarif')[:50]

    context = {
        'title': 'Import/Export Tarifs Volumétriques',
        'tarifs': tarifs,
    }
    return render(request, 'ouvrages/tarifs_import_export.html', context)


def api_equipements(request):
    """API pour récupérer tous les équipements constitutifs"""
    try:
        equipements = EquipementConstitutif.objects.all().select_related('ouvrage', 'responsable')
        data = []
        for equipement in equipements:
            data.append({
                'id': str(equipement.id),
                'nom': equipement.nom,
                'description': equipement.description,
                'type_equipement': equipement.type_equipement,
                'code_equipement': equipement.code_equipement,
                'ouvrage_id': str(equipement.ouvrage.id) if equipement.ouvrage else None,
                'statut': equipement.statut,
                'date_installation': equipement.date_installation.isoformat() if equipement.date_installation else None,
                'derniere_maintenance': equipement.derniere_maintenance.isoformat() if equipement.derniere_maintenance else None,
                'prochaine_maintenance': equipement.prochaine_maintenance.isoformat() if equipement.prochaine_maintenance else None,
                'responsable_id': str(equipement.responsable.id) if equipement.responsable else None,
            })
        return JsonResponse(data, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def ouvrages_gestion_complete(request):
    """Vue pour la gestion complète avec formulaires en cascade"""
    ouvrages = _ouvrages_subdomain_queryset().select_related('type_ouvrage').order_by('nom_ouvrage')

    context = {
        'title': 'Gestion Complète des Ouvrages',
        'ouvrages': ouvrages[:20],
    }
    return render(request, 'ouvrages/gestion_complete.html', context)


# ========== IMPORT/EXPORT EXCEL POUR TARIFS VOLUMÉTRIQUES ==========

def export_tarifs_excel(request):
    """Export des tarifs volumétriques avec tranches vers Excel"""
    try:
        # Créer un nouveau workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Tarifs Volumétriques"

        # Styles
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True, size=12)
        border_style = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        # En-têtes
        headers = [
            'ID Tarif', 'Ouvrage', 'Date Début', 'Date Fin',
            'Prix Abonnement', 'Actif', 'Tranche Supérieure (m³)', 'Tarif (Ar/m³)'
        ]

        for col, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col)
            cell.value = header
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = border_style

        # Récupérer tous les tarifs avec leurs tranches
        tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('ouvrage__nom', '-datedebuttarif')

        row = 2
        for tarif in tarifs:
            tranches = tarif.tranches.all().order_by('tranchesuperieur')

            if tranches.exists():
                # Si le tarif a des tranches, une ligne par tranche
                for tranche in tranches:
                    ws.cell(row=row, column=1).value = str(tarif.id)
                    ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                    ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                    ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                    ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                    ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                    ws.cell(row=row, column=7).value = int(tranche.tranchesuperieur) if tranche.tranchesuperieur else 0
                    ws.cell(row=row, column=8).value = int(tranche.tarif) if tranche.tarif else 0

                    # Appliquer les bordures
                    for col in range(1, 9):
                        ws.cell(row=row, column=col).border = border_style

                    row += 1
            else:
                # Si le tarif n'a pas de tranches, une ligne vide pour les tranches
                ws.cell(row=row, column=1).value = str(tarif.id)
                ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                ws.cell(row=row, column=7).value = ''
                ws.cell(row=row, column=8).value = ''

                # Appliquer les bordures
                for col in range(1, 9):
                    ws.cell(row=row, column=col).border = border_style

                row += 1

        # Ajuster la largeur des colonnes
        column_widths = [35, 30, 15, 15, 18, 10, 22, 18]
        for col, width in enumerate(column_widths, start=1):
            ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = width

        # Créer la réponse HTTP avec le fichier Excel
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename=tarifs_volumetriques_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'

        wb.save(response)
        return response

    except Exception as e:
        messages.error(request, f'Erreur lors de l\'export Excel : {str(e)}')
        return redirect('ouvrages:gestion_complete')


@csrf_exempt
def import_tarifs_excel(request):
    """Import des tarifs volumétriques avec tranches depuis Excel"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        updated_count = 0
        errors = []

        # Dictionnaire pour regrouper les tranches par tarif
        tarifs_data = {}

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    ouvrage_nom = str(row[1]).strip() if row[1] else None
                    date_debut_str = str(row[2]).strip() if row[2] else None
                    date_fin_str = str(row[3]).strip() if row[3] else None
                    prix_abonnement = row[4] if row[4] is not None else 0
                    actif_str = str(row[5]).strip().lower() if row[5] else 'oui'
                    tranche_superieur = row[6] if row[6] is not None else None
                    tarif_tranche = row[7] if row[7] is not None else None

                    # Validation des champs obligatoires
                    if not ouvrage_nom or not date_debut_str:
                        errors.append(f"Ligne {row_num}: Ouvrage et Date Début sont obligatoires")
                        continue

                    # Récupérer l'ouvrage
                    try:
                        ouvrage = _ouvrages_subdomain_queryset().get(nom_ouvrage=ouvrage_nom)
                    except OrgOuvrage.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Ouvrage '{ouvrage_nom}' introuvable")
                        continue

                    # Parser les dates
                    try:
                        date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
                    except ValueError:
                        errors.append(f"Ligne {row_num}: Format de date début invalide (attendu: AAAA-MM-JJ)")
                        continue

                    date_fin = None
                    if date_fin_str and date_fin_str != 'None':
                        try:
                            date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
                        except ValueError:
                            errors.append(f"Ligne {row_num}: Format de date fin invalide (attendu: AAAA-MM-JJ)")
                            continue

                    actif = actif_str in ['oui', 'yes', 'true', '1']

                    # Créer ou récupérer le tarif volumétrique
                    if tarif_id and tarif_id != 'None':
                        # Mise à jour d'un tarif existant
                        try:
                            tarif = TarifVolumetrique.objects.get(id=tarif_id)
                            tarif.ouvrage = ouvrage
                            tarif.datedebuttarif = date_debut
                            tarif.datefintarif = date_fin
                            tarif.prixabonnement = prix_abonnement
                            tarif.actif = actif
                            tarif.save()

                            # Utiliser l'ID du tarif comme clé
                            tarif_key = str(tarif.id)
                            if tarif_key not in tarifs_data:
                                tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': True}

                        except TarifVolumetrique.DoesNotExist:
                            errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                            continue
                    else:
                        # Créer un nouveau tarif (générer une clé unique basée sur ouvrage + date)
                        tarif_key = f"{ouvrage.id}_{date_debut}"

                        if tarif_key not in tarifs_data:
                            tarif = TarifVolumetrique.objects.create(
                                ouvrage=ouvrage,
                                datedebuttarif=date_debut,
                                datefintarif=date_fin,
                                prixabonnement=prix_abonnement,
                                actif=actif
                            )
                            tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': False}
                        else:
                            tarif = tarifs_data[tarif_key]['tarif']

                    # Ajouter la tranche si elle existe (utiliser la même clé)
                    if tranche_superieur is not None and tarif_tranche is not None:
                        if tarif_key in tarifs_data:
                            tarifs_data[tarif_key]['tranches'].append({
                                'tranchesuperieur': int(tranche_superieur),
                                'tarif': int(tarif_tranche)
                            })

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

            # Créer les tranches pour chaque tarif
            tranches_count = 0
            for tarif_key, data in tarifs_data.items():
                tarif = data['tarif']

                # Supprimer les anciennes tranches si c'est une mise à jour
                if data['updated']:
                    TarifVolumetrique2.objects.filter(tarifvolumetrique=tarif).delete()
                    updated_count += 1
                else:
                    imported_count += 1

                # Créer les nouvelles tranches
                for tranche_data in data['tranches']:
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=tranche_data['tranchesuperieur'],
                        tarif=tranche_data['tarif']
                    )
                    tranches_count += 1

        response_data = {
            'success': True,
            'imported': imported_count,
            'updated': updated_count,
            'tranches_created': tranches_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


@csrf_exempt
def import_tranches_only(request):
    """Import UNIQUEMENT des tranches (3 colonnes: tarif_id, tranche_superieur, tarif)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        errors = []

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    tranche_superieur = row[1] if row[1] is not None else None
                    tarif_prix = row[2] if row[2] is not None else None

                    # Validation des champs obligatoires
                    if not tarif_id or tranche_superieur is None or tarif_prix is None:
                        errors.append(f"Ligne {row_num}: Tous les champs sont obligatoires (tarif_id, tranche_superieur, tarif)")
                        continue

                    # Récupérer le tarif volumétrique
                    try:
                        tarif = TarifVolumetrique.objects.get(id=tarif_id)
                    except TarifVolumetrique.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                        continue

                    # Créer la tranche
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=int(tranche_superieur),
                        tarif=int(tarif_prix)
                    )
                    imported_count += 1

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

        response_data = {
            'success': True,
            'imported': imported_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


def tarifs_import_export_page(request):
    """Page pour l'import/export des tarifs volumétriques"""
    tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('-datedebuttarif')[:50]

    context = {
        'title': 'Import/Export Tarifs Volumétriques',
        'tarifs': tarifs,
    }
    return render(request, 'ouvrages/tarifs_import_export.html', context)


def api_compteurs(request):
    """API pour récupérer tous les compteurs de tête"""
    try:
        compteurs = CompteurTete.objects.all().select_related('ouvrage')
        data = []
        for compteur in compteurs:
            data.append({
                'id': str(compteur.id),
                'numerocompteur': compteur.numerocompteur,
                'ouvrage_id': str(compteur.ouvrage.id) if compteur.ouvrage else None,
                'marque': compteur.marque,
                'modele': compteur.modele,
                'date_installation': compteur.date_installation.isoformat() if compteur.date_installation else None,
                'index_initial': float(compteur.index_initial) if compteur.index_initial else 0,
                'statut': compteur.statut,
            })
        return JsonResponse(data, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def ouvrages_gestion_complete(request):
    """Vue pour la gestion complète avec formulaires en cascade"""
    ouvrages = _ouvrages_subdomain_queryset().select_related('type_ouvrage').order_by('nom_ouvrage')

    context = {
        'title': 'Gestion Complète des Ouvrages',
        'ouvrages': ouvrages[:20],
    }
    return render(request, 'ouvrages/gestion_complete.html', context)


# ========== IMPORT/EXPORT EXCEL POUR TARIFS VOLUMÉTRIQUES ==========

def export_tarifs_excel(request):
    """Export des tarifs volumétriques avec tranches vers Excel"""
    try:
        # Créer un nouveau workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Tarifs Volumétriques"

        # Styles
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True, size=12)
        border_style = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        # En-têtes
        headers = [
            'ID Tarif', 'Ouvrage', 'Date Début', 'Date Fin',
            'Prix Abonnement', 'Actif', 'Tranche Supérieure (m³)', 'Tarif (Ar/m³)'
        ]

        for col, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col)
            cell.value = header
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = border_style

        # Récupérer tous les tarifs avec leurs tranches
        tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('ouvrage__nom', '-datedebuttarif')

        row = 2
        for tarif in tarifs:
            tranches = tarif.tranches.all().order_by('tranchesuperieur')

            if tranches.exists():
                # Si le tarif a des tranches, une ligne par tranche
                for tranche in tranches:
                    ws.cell(row=row, column=1).value = str(tarif.id)
                    ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                    ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                    ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                    ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                    ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                    ws.cell(row=row, column=7).value = int(tranche.tranchesuperieur) if tranche.tranchesuperieur else 0
                    ws.cell(row=row, column=8).value = int(tranche.tarif) if tranche.tarif else 0

                    # Appliquer les bordures
                    for col in range(1, 9):
                        ws.cell(row=row, column=col).border = border_style

                    row += 1
            else:
                # Si le tarif n'a pas de tranches, une ligne vide pour les tranches
                ws.cell(row=row, column=1).value = str(tarif.id)
                ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                ws.cell(row=row, column=7).value = ''
                ws.cell(row=row, column=8).value = ''

                # Appliquer les bordures
                for col in range(1, 9):
                    ws.cell(row=row, column=col).border = border_style

                row += 1

        # Ajuster la largeur des colonnes
        column_widths = [35, 30, 15, 15, 18, 10, 22, 18]
        for col, width in enumerate(column_widths, start=1):
            ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = width

        # Créer la réponse HTTP avec le fichier Excel
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename=tarifs_volumetriques_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'

        wb.save(response)
        return response

    except Exception as e:
        messages.error(request, f'Erreur lors de l\'export Excel : {str(e)}')
        return redirect('ouvrages:gestion_complete')


@csrf_exempt
def import_tarifs_excel(request):
    """Import des tarifs volumétriques avec tranches depuis Excel"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        updated_count = 0
        errors = []

        # Dictionnaire pour regrouper les tranches par tarif
        tarifs_data = {}

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    ouvrage_nom = str(row[1]).strip() if row[1] else None
                    date_debut_str = str(row[2]).strip() if row[2] else None
                    date_fin_str = str(row[3]).strip() if row[3] else None
                    prix_abonnement = row[4] if row[4] is not None else 0
                    actif_str = str(row[5]).strip().lower() if row[5] else 'oui'
                    tranche_superieur = row[6] if row[6] is not None else None
                    tarif_tranche = row[7] if row[7] is not None else None

                    # Validation des champs obligatoires
                    if not ouvrage_nom or not date_debut_str:
                        errors.append(f"Ligne {row_num}: Ouvrage et Date Début sont obligatoires")
                        continue

                    # Récupérer l'ouvrage
                    try:
                        ouvrage = _ouvrages_subdomain_queryset().get(nom_ouvrage=ouvrage_nom)
                    except OrgOuvrage.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Ouvrage '{ouvrage_nom}' introuvable")
                        continue

                    # Parser les dates
                    try:
                        date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
                    except ValueError:
                        errors.append(f"Ligne {row_num}: Format de date début invalide (attendu: AAAA-MM-JJ)")
                        continue

                    date_fin = None
                    if date_fin_str and date_fin_str != 'None':
                        try:
                            date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
                        except ValueError:
                            errors.append(f"Ligne {row_num}: Format de date fin invalide (attendu: AAAA-MM-JJ)")
                            continue

                    actif = actif_str in ['oui', 'yes', 'true', '1']

                    # Créer ou récupérer le tarif volumétrique
                    if tarif_id and tarif_id != 'None':
                        # Mise à jour d'un tarif existant
                        try:
                            tarif = TarifVolumetrique.objects.get(id=tarif_id)
                            tarif.ouvrage = ouvrage
                            tarif.datedebuttarif = date_debut
                            tarif.datefintarif = date_fin
                            tarif.prixabonnement = prix_abonnement
                            tarif.actif = actif
                            tarif.save()

                            # Utiliser l'ID du tarif comme clé
                            tarif_key = str(tarif.id)
                            if tarif_key not in tarifs_data:
                                tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': True}

                        except TarifVolumetrique.DoesNotExist:
                            errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                            continue
                    else:
                        # Créer un nouveau tarif (générer une clé unique basée sur ouvrage + date)
                        tarif_key = f"{ouvrage.id}_{date_debut}"

                        if tarif_key not in tarifs_data:
                            tarif = TarifVolumetrique.objects.create(
                                ouvrage=ouvrage,
                                datedebuttarif=date_debut,
                                datefintarif=date_fin,
                                prixabonnement=prix_abonnement,
                                actif=actif
                            )
                            tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': False}
                        else:
                            tarif = tarifs_data[tarif_key]['tarif']

                    # Ajouter la tranche si elle existe (utiliser la même clé)
                    if tranche_superieur is not None and tarif_tranche is not None:
                        if tarif_key in tarifs_data:
                            tarifs_data[tarif_key]['tranches'].append({
                                'tranchesuperieur': int(tranche_superieur),
                                'tarif': int(tarif_tranche)
                            })

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

            # Créer les tranches pour chaque tarif
            tranches_count = 0
            for tarif_key, data in tarifs_data.items():
                tarif = data['tarif']

                # Supprimer les anciennes tranches si c'est une mise à jour
                if data['updated']:
                    TarifVolumetrique2.objects.filter(tarifvolumetrique=tarif).delete()
                    updated_count += 1
                else:
                    imported_count += 1

                # Créer les nouvelles tranches
                for tranche_data in data['tranches']:
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=tranche_data['tranchesuperieur'],
                        tarif=tranche_data['tarif']
                    )
                    tranches_count += 1

        response_data = {
            'success': True,
            'imported': imported_count,
            'updated': updated_count,
            'tranches_created': tranches_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


@csrf_exempt
def import_tranches_only(request):
    """Import UNIQUEMENT des tranches (3 colonnes: tarif_id, tranche_superieur, tarif)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        errors = []

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    tranche_superieur = row[1] if row[1] is not None else None
                    tarif_prix = row[2] if row[2] is not None else None

                    # Validation des champs obligatoires
                    if not tarif_id or tranche_superieur is None or tarif_prix is None:
                        errors.append(f"Ligne {row_num}: Tous les champs sont obligatoires (tarif_id, tranche_superieur, tarif)")
                        continue

                    # Récupérer le tarif volumétrique
                    try:
                        tarif = TarifVolumetrique.objects.get(id=tarif_id)
                    except TarifVolumetrique.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                        continue

                    # Créer la tranche
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=int(tranche_superieur),
                        tarif=int(tarif_prix)
                    )
                    imported_count += 1

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

        response_data = {
            'success': True,
            'imported': imported_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


def tarifs_import_export_page(request):
    """Page pour l'import/export des tarifs volumétriques"""
    tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('-datedebuttarif')[:50]

    context = {
        'title': 'Import/Export Tarifs Volumétriques',
        'tarifs': tarifs,
    }
    return render(request, 'ouvrages/tarifs_import_export.html', context)


def api_fournisseurs(request):
    """API pour récupérer tous les fournisseurs"""
    try:
        fournisseurs = Fournisseur.objects.all()
        data = []
        for fournisseur in fournisseurs:
            data.append({
                'id': str(fournisseur.id),
                'nom_fournisseur': fournisseur.nom_fournisseur,
                'telephone': fournisseur.telephone,
                'email': fournisseur.email,
                'adresse': fournisseur.adresse,
                'type_fournisseur': fournisseur.type_fournisseur,
                'numero_nif': fournisseur.numero_nif,
                'numero_stat': fournisseur.numero_stat,
                'actif': fournisseur.actif,
            })
        return JsonResponse(data, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def ouvrages_gestion_complete(request):
    """Vue pour la gestion complète avec formulaires en cascade"""
    ouvrages = _ouvrages_subdomain_queryset().select_related('type_ouvrage').order_by('nom_ouvrage')

    context = {
        'title': 'Gestion Complète des Ouvrages',
        'ouvrages': ouvrages[:20],
    }
    return render(request, 'ouvrages/gestion_complete.html', context)


# ========== IMPORT/EXPORT EXCEL POUR TARIFS VOLUMÉTRIQUES ==========

def export_tarifs_excel(request):
    """Export des tarifs volumétriques avec tranches vers Excel"""
    try:
        # Créer un nouveau workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Tarifs Volumétriques"

        # Styles
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True, size=12)
        border_style = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        # En-têtes
        headers = [
            'ID Tarif', 'Ouvrage', 'Date Début', 'Date Fin',
            'Prix Abonnement', 'Actif', 'Tranche Supérieure (m³)', 'Tarif (Ar/m³)'
        ]

        for col, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col)
            cell.value = header
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = border_style

        # Récupérer tous les tarifs avec leurs tranches
        tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('ouvrage__nom', '-datedebuttarif')

        row = 2
        for tarif in tarifs:
            tranches = tarif.tranches.all().order_by('tranchesuperieur')

            if tranches.exists():
                # Si le tarif a des tranches, une ligne par tranche
                for tranche in tranches:
                    ws.cell(row=row, column=1).value = str(tarif.id)
                    ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                    ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                    ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                    ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                    ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                    ws.cell(row=row, column=7).value = int(tranche.tranchesuperieur) if tranche.tranchesuperieur else 0
                    ws.cell(row=row, column=8).value = int(tranche.tarif) if tranche.tarif else 0

                    # Appliquer les bordures
                    for col in range(1, 9):
                        ws.cell(row=row, column=col).border = border_style

                    row += 1
            else:
                # Si le tarif n'a pas de tranches, une ligne vide pour les tranches
                ws.cell(row=row, column=1).value = str(tarif.id)
                ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                ws.cell(row=row, column=7).value = ''
                ws.cell(row=row, column=8).value = ''

                # Appliquer les bordures
                for col in range(1, 9):
                    ws.cell(row=row, column=col).border = border_style

                row += 1

        # Ajuster la largeur des colonnes
        column_widths = [35, 30, 15, 15, 18, 10, 22, 18]
        for col, width in enumerate(column_widths, start=1):
            ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = width

        # Créer la réponse HTTP avec le fichier Excel
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename=tarifs_volumetriques_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'

        wb.save(response)
        return response

    except Exception as e:
        messages.error(request, f'Erreur lors de l\'export Excel : {str(e)}')
        return redirect('ouvrages:gestion_complete')


@csrf_exempt
def import_tarifs_excel(request):
    """Import des tarifs volumétriques avec tranches depuis Excel"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        updated_count = 0
        errors = []

        # Dictionnaire pour regrouper les tranches par tarif
        tarifs_data = {}

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    ouvrage_nom = str(row[1]).strip() if row[1] else None
                    date_debut_str = str(row[2]).strip() if row[2] else None
                    date_fin_str = str(row[3]).strip() if row[3] else None
                    prix_abonnement = row[4] if row[4] is not None else 0
                    actif_str = str(row[5]).strip().lower() if row[5] else 'oui'
                    tranche_superieur = row[6] if row[6] is not None else None
                    tarif_tranche = row[7] if row[7] is not None else None

                    # Validation des champs obligatoires
                    if not ouvrage_nom or not date_debut_str:
                        errors.append(f"Ligne {row_num}: Ouvrage et Date Début sont obligatoires")
                        continue

                    # Récupérer l'ouvrage
                    try:
                        ouvrage = _ouvrages_subdomain_queryset().get(nom_ouvrage=ouvrage_nom)
                    except OrgOuvrage.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Ouvrage '{ouvrage_nom}' introuvable")
                        continue

                    # Parser les dates
                    try:
                        date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
                    except ValueError:
                        errors.append(f"Ligne {row_num}: Format de date début invalide (attendu: AAAA-MM-JJ)")
                        continue

                    date_fin = None
                    if date_fin_str and date_fin_str != 'None':
                        try:
                            date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
                        except ValueError:
                            errors.append(f"Ligne {row_num}: Format de date fin invalide (attendu: AAAA-MM-JJ)")
                            continue

                    actif = actif_str in ['oui', 'yes', 'true', '1']

                    # Créer ou récupérer le tarif volumétrique
                    if tarif_id and tarif_id != 'None':
                        # Mise à jour d'un tarif existant
                        try:
                            tarif = TarifVolumetrique.objects.get(id=tarif_id)
                            tarif.ouvrage = ouvrage
                            tarif.datedebuttarif = date_debut
                            tarif.datefintarif = date_fin
                            tarif.prixabonnement = prix_abonnement
                            tarif.actif = actif
                            tarif.save()

                            # Utiliser l'ID du tarif comme clé
                            tarif_key = str(tarif.id)
                            if tarif_key not in tarifs_data:
                                tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': True}

                        except TarifVolumetrique.DoesNotExist:
                            errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                            continue
                    else:
                        # Créer un nouveau tarif (générer une clé unique basée sur ouvrage + date)
                        tarif_key = f"{ouvrage.id}_{date_debut}"

                        if tarif_key not in tarifs_data:
                            tarif = TarifVolumetrique.objects.create(
                                ouvrage=ouvrage,
                                datedebuttarif=date_debut,
                                datefintarif=date_fin,
                                prixabonnement=prix_abonnement,
                                actif=actif
                            )
                            tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': False}
                        else:
                            tarif = tarifs_data[tarif_key]['tarif']

                    # Ajouter la tranche si elle existe (utiliser la même clé)
                    if tranche_superieur is not None and tarif_tranche is not None:
                        if tarif_key in tarifs_data:
                            tarifs_data[tarif_key]['tranches'].append({
                                'tranchesuperieur': int(tranche_superieur),
                                'tarif': int(tarif_tranche)
                            })

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

            # Créer les tranches pour chaque tarif
            tranches_count = 0
            for tarif_key, data in tarifs_data.items():
                tarif = data['tarif']

                # Supprimer les anciennes tranches si c'est une mise à jour
                if data['updated']:
                    TarifVolumetrique2.objects.filter(tarifvolumetrique=tarif).delete()
                    updated_count += 1
                else:
                    imported_count += 1

                # Créer les nouvelles tranches
                for tranche_data in data['tranches']:
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=tranche_data['tranchesuperieur'],
                        tarif=tranche_data['tarif']
                    )
                    tranches_count += 1

        response_data = {
            'success': True,
            'imported': imported_count,
            'updated': updated_count,
            'tranches_created': tranches_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


@csrf_exempt
def import_tranches_only(request):
    """Import UNIQUEMENT des tranches (3 colonnes: tarif_id, tranche_superieur, tarif)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        errors = []

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    tranche_superieur = row[1] if row[1] is not None else None
                    tarif_prix = row[2] if row[2] is not None else None

                    # Validation des champs obligatoires
                    if not tarif_id or tranche_superieur is None or tarif_prix is None:
                        errors.append(f"Ligne {row_num}: Tous les champs sont obligatoires (tarif_id, tranche_superieur, tarif)")
                        continue

                    # Récupérer le tarif volumétrique
                    try:
                        tarif = TarifVolumetrique.objects.get(id=tarif_id)
                    except TarifVolumetrique.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                        continue

                    # Créer la tranche
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=int(tranche_superieur),
                        tarif=int(tarif_prix)
                    )
                    imported_count += 1

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

        response_data = {
            'success': True,
            'imported': imported_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


def tarifs_import_export_page(request):
    """Page pour l'import/export des tarifs volumétriques"""
    tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('-datedebuttarif')[:50]

    context = {
        'title': 'Import/Export Tarifs Volumétriques',
        'tarifs': tarifs,
    }
    return render(request, 'ouvrages/tarifs_import_export.html', context)


def api_tarifs(request):
    """API pour récupérer tous les tarifs volumétriques"""
    try:
        tarifs = TarifVolumetrique.objects.all().select_related('ouvrage')
        data = []
        for tarif in tarifs:
            data.append({
                'id': str(tarif.id),
                'ouvrage_id': str(tarif.ouvrage.id) if tarif.ouvrage else None,
                'tranche_consommation': tarif.tranche_consommation,
                'volume_min': float(tarif.volume_min) if tarif.volume_min else None,
                'volume_max': float(tarif.volume_max) if tarif.volume_max else None,
                'prix_unitaire': float(tarif.prix_unitaire),
                'date_debut': tarif.date_debut.isoformat() if tarif.date_debut else None,
                'date_fin': tarif.date_fin.isoformat() if tarif.date_fin else None,
                'actif': tarif.actif,
            })
        return JsonResponse(data, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def ouvrages_gestion_complete(request):
    """Vue pour la gestion complète avec formulaires en cascade"""
    ouvrages = _ouvrages_subdomain_queryset().select_related('type_ouvrage').order_by('nom_ouvrage')

    context = {
        'title': 'Gestion Complète des Ouvrages',
        'ouvrages': ouvrages[:20],
    }
    return render(request, 'ouvrages/gestion_complete.html', context)


# ========== IMPORT/EXPORT EXCEL POUR TARIFS VOLUMÉTRIQUES ==========

def export_tarifs_excel(request):
    """Export des tarifs volumétriques avec tranches vers Excel"""
    try:
        # Créer un nouveau workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Tarifs Volumétriques"

        # Styles
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True, size=12)
        border_style = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        # En-têtes
        headers = [
            'ID Tarif', 'Ouvrage', 'Date Début', 'Date Fin',
            'Prix Abonnement', 'Actif', 'Tranche Supérieure (m³)', 'Tarif (Ar/m³)'
        ]

        for col, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col)
            cell.value = header
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = border_style

        # Récupérer tous les tarifs avec leurs tranches
        tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('ouvrage__nom', '-datedebuttarif')

        row = 2
        for tarif in tarifs:
            tranches = tarif.tranches.all().order_by('tranchesuperieur')

            if tranches.exists():
                # Si le tarif a des tranches, une ligne par tranche
                for tranche in tranches:
                    ws.cell(row=row, column=1).value = str(tarif.id)
                    ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                    ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                    ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                    ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                    ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                    ws.cell(row=row, column=7).value = int(tranche.tranchesuperieur) if tranche.tranchesuperieur else 0
                    ws.cell(row=row, column=8).value = int(tranche.tarif) if tranche.tarif else 0

                    # Appliquer les bordures
                    for col in range(1, 9):
                        ws.cell(row=row, column=col).border = border_style

                    row += 1
            else:
                # Si le tarif n'a pas de tranches, une ligne vide pour les tranches
                ws.cell(row=row, column=1).value = str(tarif.id)
                ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                ws.cell(row=row, column=7).value = ''
                ws.cell(row=row, column=8).value = ''

                # Appliquer les bordures
                for col in range(1, 9):
                    ws.cell(row=row, column=col).border = border_style

                row += 1

        # Ajuster la largeur des colonnes
        column_widths = [35, 30, 15, 15, 18, 10, 22, 18]
        for col, width in enumerate(column_widths, start=1):
            ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = width

        # Créer la réponse HTTP avec le fichier Excel
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename=tarifs_volumetriques_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'

        wb.save(response)
        return response

    except Exception as e:
        messages.error(request, f'Erreur lors de l\'export Excel : {str(e)}')
        return redirect('ouvrages:gestion_complete')


@csrf_exempt
def import_tarifs_excel(request):
    """Import des tarifs volumétriques avec tranches depuis Excel"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        updated_count = 0
        errors = []

        # Dictionnaire pour regrouper les tranches par tarif
        tarifs_data = {}

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    ouvrage_nom = str(row[1]).strip() if row[1] else None
                    date_debut_str = str(row[2]).strip() if row[2] else None
                    date_fin_str = str(row[3]).strip() if row[3] else None
                    prix_abonnement = row[4] if row[4] is not None else 0
                    actif_str = str(row[5]).strip().lower() if row[5] else 'oui'
                    tranche_superieur = row[6] if row[6] is not None else None
                    tarif_tranche = row[7] if row[7] is not None else None

                    # Validation des champs obligatoires
                    if not ouvrage_nom or not date_debut_str:
                        errors.append(f"Ligne {row_num}: Ouvrage et Date Début sont obligatoires")
                        continue

                    # Récupérer l'ouvrage
                    try:
                        ouvrage = _ouvrages_subdomain_queryset().get(nom_ouvrage=ouvrage_nom)
                    except OrgOuvrage.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Ouvrage '{ouvrage_nom}' introuvable")
                        continue

                    # Parser les dates
                    try:
                        date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
                    except ValueError:
                        errors.append(f"Ligne {row_num}: Format de date début invalide (attendu: AAAA-MM-JJ)")
                        continue

                    date_fin = None
                    if date_fin_str and date_fin_str != 'None':
                        try:
                            date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
                        except ValueError:
                            errors.append(f"Ligne {row_num}: Format de date fin invalide (attendu: AAAA-MM-JJ)")
                            continue

                    actif = actif_str in ['oui', 'yes', 'true', '1']

                    # Créer ou récupérer le tarif volumétrique
                    if tarif_id and tarif_id != 'None':
                        # Mise à jour d'un tarif existant
                        try:
                            tarif = TarifVolumetrique.objects.get(id=tarif_id)
                            tarif.ouvrage = ouvrage
                            tarif.datedebuttarif = date_debut
                            tarif.datefintarif = date_fin
                            tarif.prixabonnement = prix_abonnement
                            tarif.actif = actif
                            tarif.save()

                            # Utiliser l'ID du tarif comme clé
                            tarif_key = str(tarif.id)
                            if tarif_key not in tarifs_data:
                                tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': True}

                        except TarifVolumetrique.DoesNotExist:
                            errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                            continue
                    else:
                        # Créer un nouveau tarif (générer une clé unique basée sur ouvrage + date)
                        tarif_key = f"{ouvrage.id}_{date_debut}"

                        if tarif_key not in tarifs_data:
                            tarif = TarifVolumetrique.objects.create(
                                ouvrage=ouvrage,
                                datedebuttarif=date_debut,
                                datefintarif=date_fin,
                                prixabonnement=prix_abonnement,
                                actif=actif
                            )
                            tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': False}
                        else:
                            tarif = tarifs_data[tarif_key]['tarif']

                    # Ajouter la tranche si elle existe (utiliser la même clé)
                    if tranche_superieur is not None and tarif_tranche is not None:
                        if tarif_key in tarifs_data:
                            tarifs_data[tarif_key]['tranches'].append({
                                'tranchesuperieur': int(tranche_superieur),
                                'tarif': int(tarif_tranche)
                            })

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

            # Créer les tranches pour chaque tarif
            tranches_count = 0
            for tarif_key, data in tarifs_data.items():
                tarif = data['tarif']

                # Supprimer les anciennes tranches si c'est une mise à jour
                if data['updated']:
                    TarifVolumetrique2.objects.filter(tarifvolumetrique=tarif).delete()
                    updated_count += 1
                else:
                    imported_count += 1

                # Créer les nouvelles tranches
                for tranche_data in data['tranches']:
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=tranche_data['tranchesuperieur'],
                        tarif=tranche_data['tarif']
                    )
                    tranches_count += 1

        response_data = {
            'success': True,
            'imported': imported_count,
            'updated': updated_count,
            'tranches_created': tranches_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


@csrf_exempt
def import_tranches_only(request):
    """Import UNIQUEMENT des tranches (3 colonnes: tarif_id, tranche_superieur, tarif)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        errors = []

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    tranche_superieur = row[1] if row[1] is not None else None
                    tarif_prix = row[2] if row[2] is not None else None

                    # Validation des champs obligatoires
                    if not tarif_id or tranche_superieur is None or tarif_prix is None:
                        errors.append(f"Ligne {row_num}: Tous les champs sont obligatoires (tarif_id, tranche_superieur, tarif)")
                        continue

                    # Récupérer le tarif volumétrique
                    try:
                        tarif = TarifVolumetrique.objects.get(id=tarif_id)
                    except TarifVolumetrique.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                        continue

                    # Créer la tranche
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=int(tranche_superieur),
                        tarif=int(tarif_prix)
                    )
                    imported_count += 1

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

        response_data = {
            'success': True,
            'imported': imported_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


def tarifs_import_export_page(request):
    """Page pour l'import/export des tarifs volumétriques"""
    tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('-datedebuttarif')[:50]

    context = {
        'title': 'Import/Export Tarifs Volumétriques',
        'tarifs': tarifs,
    }
    return render(request, 'ouvrages/tarifs_import_export.html', context)


def api_modalites(request):
    """API pour récupérer toutes les modalités de gestion"""
    try:
        modalites = ModaliteGestion.objects.all().select_related('ouvrage')
        data = []
        for modalite in modalites:
            data.append({
                'id': str(modalite.id),
                'ouvrage_id': str(modalite.ouvrage.id) if modalite.ouvrage else None,
                'type_gestion': modalite.type_gestion,
                'gestionnaire': modalite.gestionnaire,
                'contact_gestionnaire': modalite.contact_gestionnaire,
                'date_debut': modalite.date_debut.isoformat() if modalite.date_debut else None,
                'date_fin': modalite.date_fin.isoformat() if modalite.date_fin else None,
                'statut': modalite.statut,
                'tarif_mensuel': float(modalite.tarif_mensuel) if modalite.tarif_mensuel else None,
                'pourcentage_recettes': float(modalite.pourcentage_recettes) if modalite.pourcentage_recettes else None,
                'observations': modalite.observations,
            })
        return JsonResponse(data, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def ouvrages_gestion_complete(request):
    """Vue pour la gestion complète avec formulaires en cascade"""
    ouvrages = _ouvrages_subdomain_queryset().select_related('type_ouvrage').order_by('nom_ouvrage')

    context = {
        'title': 'Gestion Complète des Ouvrages',
        'ouvrages': ouvrages[:20],
    }
    return render(request, 'ouvrages/gestion_complete.html', context)


# ========== IMPORT/EXPORT EXCEL POUR TARIFS VOLUMÉTRIQUES ==========

def export_tarifs_excel(request):
    """Export des tarifs volumétriques avec tranches vers Excel"""
    try:
        # Créer un nouveau workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Tarifs Volumétriques"

        # Styles
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True, size=12)
        border_style = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        # En-têtes
        headers = [
            'ID Tarif', 'Ouvrage', 'Date Début', 'Date Fin',
            'Prix Abonnement', 'Actif', 'Tranche Supérieure (m³)', 'Tarif (Ar/m³)'
        ]

        for col, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col)
            cell.value = header
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = border_style

        # Récupérer tous les tarifs avec leurs tranches
        tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('ouvrage__nom', '-datedebuttarif')

        row = 2
        for tarif in tarifs:
            tranches = tarif.tranches.all().order_by('tranchesuperieur')

            if tranches.exists():
                # Si le tarif a des tranches, une ligne par tranche
                for tranche in tranches:
                    ws.cell(row=row, column=1).value = str(tarif.id)
                    ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                    ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                    ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                    ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                    ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                    ws.cell(row=row, column=7).value = int(tranche.tranchesuperieur) if tranche.tranchesuperieur else 0
                    ws.cell(row=row, column=8).value = int(tranche.tarif) if tranche.tarif else 0

                    # Appliquer les bordures
                    for col in range(1, 9):
                        ws.cell(row=row, column=col).border = border_style

                    row += 1
            else:
                # Si le tarif n'a pas de tranches, une ligne vide pour les tranches
                ws.cell(row=row, column=1).value = str(tarif.id)
                ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                ws.cell(row=row, column=7).value = ''
                ws.cell(row=row, column=8).value = ''

                # Appliquer les bordures
                for col in range(1, 9):
                    ws.cell(row=row, column=col).border = border_style

                row += 1

        # Ajuster la largeur des colonnes
        column_widths = [35, 30, 15, 15, 18, 10, 22, 18]
        for col, width in enumerate(column_widths, start=1):
            ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = width

        # Créer la réponse HTTP avec le fichier Excel
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename=tarifs_volumetriques_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'

        wb.save(response)
        return response

    except Exception as e:
        messages.error(request, f'Erreur lors de l\'export Excel : {str(e)}')
        return redirect('ouvrages:gestion_complete')


@csrf_exempt
def import_tarifs_excel(request):
    """Import des tarifs volumétriques avec tranches depuis Excel"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        updated_count = 0
        errors = []

        # Dictionnaire pour regrouper les tranches par tarif
        tarifs_data = {}

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    ouvrage_nom = str(row[1]).strip() if row[1] else None
                    date_debut_str = str(row[2]).strip() if row[2] else None
                    date_fin_str = str(row[3]).strip() if row[3] else None
                    prix_abonnement = row[4] if row[4] is not None else 0
                    actif_str = str(row[5]).strip().lower() if row[5] else 'oui'
                    tranche_superieur = row[6] if row[6] is not None else None
                    tarif_tranche = row[7] if row[7] is not None else None

                    # Validation des champs obligatoires
                    if not ouvrage_nom or not date_debut_str:
                        errors.append(f"Ligne {row_num}: Ouvrage et Date Début sont obligatoires")
                        continue

                    # Récupérer l'ouvrage
                    try:
                        ouvrage = _ouvrages_subdomain_queryset().get(nom_ouvrage=ouvrage_nom)
                    except OrgOuvrage.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Ouvrage '{ouvrage_nom}' introuvable")
                        continue

                    # Parser les dates
                    try:
                        date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
                    except ValueError:
                        errors.append(f"Ligne {row_num}: Format de date début invalide (attendu: AAAA-MM-JJ)")
                        continue

                    date_fin = None
                    if date_fin_str and date_fin_str != 'None':
                        try:
                            date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
                        except ValueError:
                            errors.append(f"Ligne {row_num}: Format de date fin invalide (attendu: AAAA-MM-JJ)")
                            continue

                    actif = actif_str in ['oui', 'yes', 'true', '1']

                    # Créer ou récupérer le tarif volumétrique
                    if tarif_id and tarif_id != 'None':
                        # Mise à jour d'un tarif existant
                        try:
                            tarif = TarifVolumetrique.objects.get(id=tarif_id)
                            tarif.ouvrage = ouvrage
                            tarif.datedebuttarif = date_debut
                            tarif.datefintarif = date_fin
                            tarif.prixabonnement = prix_abonnement
                            tarif.actif = actif
                            tarif.save()

                            # Utiliser l'ID du tarif comme clé
                            tarif_key = str(tarif.id)
                            if tarif_key not in tarifs_data:
                                tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': True}

                        except TarifVolumetrique.DoesNotExist:
                            errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                            continue
                    else:
                        # Créer un nouveau tarif (générer une clé unique basée sur ouvrage + date)
                        tarif_key = f"{ouvrage.id}_{date_debut}"

                        if tarif_key not in tarifs_data:
                            tarif = TarifVolumetrique.objects.create(
                                ouvrage=ouvrage,
                                datedebuttarif=date_debut,
                                datefintarif=date_fin,
                                prixabonnement=prix_abonnement,
                                actif=actif
                            )
                            tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': False}
                        else:
                            tarif = tarifs_data[tarif_key]['tarif']

                    # Ajouter la tranche si elle existe (utiliser la même clé)
                    if tranche_superieur is not None and tarif_tranche is not None:
                        if tarif_key in tarifs_data:
                            tarifs_data[tarif_key]['tranches'].append({
                                'tranchesuperieur': int(tranche_superieur),
                                'tarif': int(tarif_tranche)
                            })

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

            # Créer les tranches pour chaque tarif
            tranches_count = 0
            for tarif_key, data in tarifs_data.items():
                tarif = data['tarif']

                # Supprimer les anciennes tranches si c'est une mise à jour
                if data['updated']:
                    TarifVolumetrique2.objects.filter(tarifvolumetrique=tarif).delete()
                    updated_count += 1
                else:
                    imported_count += 1

                # Créer les nouvelles tranches
                for tranche_data in data['tranches']:
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=tranche_data['tranchesuperieur'],
                        tarif=tranche_data['tarif']
                    )
                    tranches_count += 1

        response_data = {
            'success': True,
            'imported': imported_count,
            'updated': updated_count,
            'tranches_created': tranches_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


@csrf_exempt
def import_tranches_only(request):
    """Import UNIQUEMENT des tranches (3 colonnes: tarif_id, tranche_superieur, tarif)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        errors = []

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    tranche_superieur = row[1] if row[1] is not None else None
                    tarif_prix = row[2] if row[2] is not None else None

                    # Validation des champs obligatoires
                    if not tarif_id or tranche_superieur is None or tarif_prix is None:
                        errors.append(f"Ligne {row_num}: Tous les champs sont obligatoires (tarif_id, tranche_superieur, tarif)")
                        continue

                    # Récupérer le tarif volumétrique
                    try:
                        tarif = TarifVolumetrique.objects.get(id=tarif_id)
                    except TarifVolumetrique.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                        continue

                    # Créer la tranche
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=int(tranche_superieur),
                        tarif=int(tarif_prix)
                    )
                    imported_count += 1

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

        response_data = {
            'success': True,
            'imported': imported_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


def tarifs_import_export_page(request):
    """Page pour l'import/export des tarifs volumétriques"""
    tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('-datedebuttarif')[:50]

    context = {
        'title': 'Import/Export Tarifs Volumétriques',
        'tarifs': tarifs,
    }
    return render(request, 'ouvrages/tarifs_import_export.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def api_create(request):
    """API pour créer de nouvelles entités"""
    try:
        data = json.loads(request.body)
        entity_type = data.get('entity_type')

        # Mapping des types d'entités vers les modèles et formulaires
        entity_config = {
            'ouvrage': {'model': Ouvrage, 'form': OuvrageForm},
            'pointeau': {'model': PointEau, 'form': PointEauForm},
            'equipement': {'model': EquipementConstitutif, 'form': EquipementConstitutifForm},
            'compteur': {'model': CompteurTete, 'form': CompteurTeteForm},
            'fournisseur': {'model': Fournisseur, 'form': FournisseurForm},
            'tarif': {'model': TarifVolumetrique, 'form': TarifVolumetriqueForm},
            'modalite': {'model': ModaliteGestion, 'form': ModaliteGestionForm},
        }

        if entity_type not in entity_config:
            return JsonResponse({'error': 'Type d\'entité non supporté'}, status=400)

        config = entity_config[entity_type]

        # Préparer les données pour le formulaire
        form_data = data.copy()
        form_data.pop('entity_type', None)

        # Traitement spécial selon le type d'entité
        if entity_type == 'ouvrage':
            # Convertir les IDs en objets
            if 'typeouvrage' in form_data and form_data['typeouvrage']:
                form_data['typeouvrage'] = TypeOrgOuvrage.objects.get(id=form_data['typeouvrage'])
            if 'organisation' in form_data and form_data['organisation']:
                form_data['organisation'] = Organisation.objects.get(id=form_data['organisation'])

        elif entity_type in ['pointeau', 'equipement', 'compteur', 'tarif', 'modalite']:
            # Traitement des relations ForeignKey
            if 'ouvrage' in form_data and form_data['ouvrage']:
                form_data['ouvrage'] = _ouvrages_subdomain_queryset().get(id=form_data['ouvrage'])

        # Créer l'instance
        instance = config['model'](**form_data)
        instance.full_clean()  # Validation
        instance.save()

        return JsonResponse({
            'success': True,
            'message': f'{entity_type.title()} créé avec succès',
            'id': str(instance.id)
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON invalide'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["PUT"])
def api_update(request):
    """API pour modifier des entités existantes"""
    try:
        data = json.loads(request.body)
        entity_type = data.get('entity_type')
        entity_id = data.get('entity_id')

        if not entity_id:
            return JsonResponse({'error': 'ID d\'entité requis'}, status=400)

        # Mapping des types d'entités vers les modèles
        entity_models = {
            'ouvrage': Ouvrage,
            'pointeau': PointEau,
            'equipement': EquipementConstitutif,
            'compteur': CompteurTete,
            'fournisseur': Fournisseur,
            'tarif': TarifVolumetrique,
            'modalite': ModaliteGestion,
        }

        if entity_type not in entity_models:
            return JsonResponse({'error': 'Type d\'entité non supporté'}, status=400)

        model = entity_models[entity_type]
        instance = get_object_or_404(model, id=entity_id)

        # Mettre à jour les champs
        form_data = data.copy()
        form_data.pop('entity_type', None)
        form_data.pop('entity_id', None)

        # Traitement spécial selon le type d'entité
        if entity_type == 'ouvrage':
            if 'typeouvrage' in form_data and form_data['typeouvrage']:
                instance.typeouvrage = TypeOrgOuvrage.objects.get(id=form_data['typeouvrage'])
            if 'organisation' in form_data and form_data['organisation']:
                instance.organisation = Organisation.objects.get(id=form_data['organisation'])

        elif entity_type in ['pointeau', 'equipement', 'compteur', 'tarif', 'modalite']:
            if 'ouvrage' in form_data and form_data['ouvrage']:
                instance.ouvrage = _ouvrages_subdomain_queryset().get(id=form_data['ouvrage'])

        # Mettre à jour les autres champs
        for field, value in form_data.items():
            if hasattr(instance, field) and field not in ['typeouvrage', 'organisation', 'ouvrage']:
                setattr(instance, field, value)

        instance.full_clean()  # Validation
        instance.save()

        return JsonResponse({
            'success': True,
            'message': f'{entity_type.title()} modifié avec succès'
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON invalide'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["DELETE"])
def api_delete(request):
    """API pour supprimer des entités"""
    try:
        data = json.loads(request.body)
        entity_type = data.get('entity_type')
        entity_id = data.get('entity_id')

        if not entity_id:
            return JsonResponse({'error': 'ID d\'entité requis'}, status=400)

        # Mapping des types d'entités vers les modèles
        entity_models = {
            'ouvrage': Ouvrage,
            'pointeau': PointEau,
            'equipement': EquipementConstitutif,
            'compteur': CompteurTete,
            'fournisseur': Fournisseur,
            'tarif': TarifVolumetrique,
            'modalite': ModaliteGestion,
        }

        if entity_type not in entity_models:
            return JsonResponse({'error': 'Type d\'entité non supporté'}, status=400)

        model = entity_models[entity_type]
        instance = get_object_or_404(model, id=entity_id)
        instance.delete()

        return JsonResponse({
            'success': True,
            'message': f'{entity_type.title()} supprimé avec succès'
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON invalide'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# APIs pour les formulaires en cascade géographiques
def api_regions(request):
    """API pour récupérer toutes les régions"""
    try:
        regions = Region.objects.all().order_by('nom_region')
        data = []
        for region in regions:
            data.append({
                'id': str(region.id),
                'nom_region': region.nom_region,
            })
        return JsonResponse(data, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def ouvrages_gestion_complete(request):
    """Vue pour la gestion complète avec formulaires en cascade"""
    ouvrages = _ouvrages_subdomain_queryset().select_related('type_ouvrage').order_by('nom_ouvrage')

    context = {
        'title': 'Gestion Complète des Ouvrages',
        'ouvrages': ouvrages[:20],
    }
    return render(request, 'ouvrages/gestion_complete.html', context)


# ========== IMPORT/EXPORT EXCEL POUR TARIFS VOLUMÉTRIQUES ==========

def export_tarifs_excel(request):
    """Export des tarifs volumétriques avec tranches vers Excel"""
    try:
        # Créer un nouveau workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Tarifs Volumétriques"

        # Styles
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True, size=12)
        border_style = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        # En-têtes
        headers = [
            'ID Tarif', 'Ouvrage', 'Date Début', 'Date Fin',
            'Prix Abonnement', 'Actif', 'Tranche Supérieure (m³)', 'Tarif (Ar/m³)'
        ]

        for col, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col)
            cell.value = header
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = border_style

        # Récupérer tous les tarifs avec leurs tranches
        tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('ouvrage__nom', '-datedebuttarif')

        row = 2
        for tarif in tarifs:
            tranches = tarif.tranches.all().order_by('tranchesuperieur')

            if tranches.exists():
                # Si le tarif a des tranches, une ligne par tranche
                for tranche in tranches:
                    ws.cell(row=row, column=1).value = str(tarif.id)
                    ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                    ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                    ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                    ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                    ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                    ws.cell(row=row, column=7).value = int(tranche.tranchesuperieur) if tranche.tranchesuperieur else 0
                    ws.cell(row=row, column=8).value = int(tranche.tarif) if tranche.tarif else 0

                    # Appliquer les bordures
                    for col in range(1, 9):
                        ws.cell(row=row, column=col).border = border_style

                    row += 1
            else:
                # Si le tarif n'a pas de tranches, une ligne vide pour les tranches
                ws.cell(row=row, column=1).value = str(tarif.id)
                ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                ws.cell(row=row, column=7).value = ''
                ws.cell(row=row, column=8).value = ''

                # Appliquer les bordures
                for col in range(1, 9):
                    ws.cell(row=row, column=col).border = border_style

                row += 1

        # Ajuster la largeur des colonnes
        column_widths = [35, 30, 15, 15, 18, 10, 22, 18]
        for col, width in enumerate(column_widths, start=1):
            ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = width

        # Créer la réponse HTTP avec le fichier Excel
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename=tarifs_volumetriques_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'

        wb.save(response)
        return response

    except Exception as e:
        messages.error(request, f'Erreur lors de l\'export Excel : {str(e)}')
        return redirect('ouvrages:gestion_complete')


@csrf_exempt
def import_tarifs_excel(request):
    """Import des tarifs volumétriques avec tranches depuis Excel"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        updated_count = 0
        errors = []

        # Dictionnaire pour regrouper les tranches par tarif
        tarifs_data = {}

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    ouvrage_nom = str(row[1]).strip() if row[1] else None
                    date_debut_str = str(row[2]).strip() if row[2] else None
                    date_fin_str = str(row[3]).strip() if row[3] else None
                    prix_abonnement = row[4] if row[4] is not None else 0
                    actif_str = str(row[5]).strip().lower() if row[5] else 'oui'
                    tranche_superieur = row[6] if row[6] is not None else None
                    tarif_tranche = row[7] if row[7] is not None else None

                    # Validation des champs obligatoires
                    if not ouvrage_nom or not date_debut_str:
                        errors.append(f"Ligne {row_num}: Ouvrage et Date Début sont obligatoires")
                        continue

                    # Récupérer l'ouvrage
                    try:
                        ouvrage = _ouvrages_subdomain_queryset().get(nom_ouvrage=ouvrage_nom)
                    except OrgOuvrage.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Ouvrage '{ouvrage_nom}' introuvable")
                        continue

                    # Parser les dates
                    try:
                        date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
                    except ValueError:
                        errors.append(f"Ligne {row_num}: Format de date début invalide (attendu: AAAA-MM-JJ)")
                        continue

                    date_fin = None
                    if date_fin_str and date_fin_str != 'None':
                        try:
                            date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
                        except ValueError:
                            errors.append(f"Ligne {row_num}: Format de date fin invalide (attendu: AAAA-MM-JJ)")
                            continue

                    actif = actif_str in ['oui', 'yes', 'true', '1']

                    # Créer ou récupérer le tarif volumétrique
                    if tarif_id and tarif_id != 'None':
                        # Mise à jour d'un tarif existant
                        try:
                            tarif = TarifVolumetrique.objects.get(id=tarif_id)
                            tarif.ouvrage = ouvrage
                            tarif.datedebuttarif = date_debut
                            tarif.datefintarif = date_fin
                            tarif.prixabonnement = prix_abonnement
                            tarif.actif = actif
                            tarif.save()

                            # Utiliser l'ID du tarif comme clé
                            tarif_key = str(tarif.id)
                            if tarif_key not in tarifs_data:
                                tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': True}

                        except TarifVolumetrique.DoesNotExist:
                            errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                            continue
                    else:
                        # Créer un nouveau tarif (générer une clé unique basée sur ouvrage + date)
                        tarif_key = f"{ouvrage.id}_{date_debut}"

                        if tarif_key not in tarifs_data:
                            tarif = TarifVolumetrique.objects.create(
                                ouvrage=ouvrage,
                                datedebuttarif=date_debut,
                                datefintarif=date_fin,
                                prixabonnement=prix_abonnement,
                                actif=actif
                            )
                            tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': False}
                        else:
                            tarif = tarifs_data[tarif_key]['tarif']

                    # Ajouter la tranche si elle existe (utiliser la même clé)
                    if tranche_superieur is not None and tarif_tranche is not None:
                        if tarif_key in tarifs_data:
                            tarifs_data[tarif_key]['tranches'].append({
                                'tranchesuperieur': int(tranche_superieur),
                                'tarif': int(tarif_tranche)
                            })

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

            # Créer les tranches pour chaque tarif
            tranches_count = 0
            for tarif_key, data in tarifs_data.items():
                tarif = data['tarif']

                # Supprimer les anciennes tranches si c'est une mise à jour
                if data['updated']:
                    TarifVolumetrique2.objects.filter(tarifvolumetrique=tarif).delete()
                    updated_count += 1
                else:
                    imported_count += 1

                # Créer les nouvelles tranches
                for tranche_data in data['tranches']:
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=tranche_data['tranchesuperieur'],
                        tarif=tranche_data['tarif']
                    )
                    tranches_count += 1

        response_data = {
            'success': True,
            'imported': imported_count,
            'updated': updated_count,
            'tranches_created': tranches_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


@csrf_exempt
def import_tranches_only(request):
    """Import UNIQUEMENT des tranches (3 colonnes: tarif_id, tranche_superieur, tarif)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        errors = []

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    tranche_superieur = row[1] if row[1] is not None else None
                    tarif_prix = row[2] if row[2] is not None else None

                    # Validation des champs obligatoires
                    if not tarif_id or tranche_superieur is None or tarif_prix is None:
                        errors.append(f"Ligne {row_num}: Tous les champs sont obligatoires (tarif_id, tranche_superieur, tarif)")
                        continue

                    # Récupérer le tarif volumétrique
                    try:
                        tarif = TarifVolumetrique.objects.get(id=tarif_id)
                    except TarifVolumetrique.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                        continue

                    # Créer la tranche
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=int(tranche_superieur),
                        tarif=int(tarif_prix)
                    )
                    imported_count += 1

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

        response_data = {
            'success': True,
            'imported': imported_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


def tarifs_import_export_page(request):
    """Page pour l'import/export des tarifs volumétriques"""
    tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('-datedebuttarif')[:50]

    context = {
        'title': 'Import/Export Tarifs Volumétriques',
        'tarifs': tarifs,
    }
    return render(request, 'ouvrages/tarifs_import_export.html', context)


def api_districts(request):
    """API pour récupérer les districts par région"""
    try:
        region_id = request.GET.get('region_id')
        if region_id:
            districts = District.objects.filter(region_id=region_id).order_by('nom_district')
        else:
            districts = District.objects.all().order_by('region__nom_region', 'nom_district')

        data = []
        for district in districts:
            data.append({
                'id': str(district.id),
                'nom_district': district.nom_district,
                'region_id': str(district.region_id),
                'region_nom': district.region.nom_region,
            })
        return JsonResponse(data, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def ouvrages_gestion_complete(request):
    """Vue pour la gestion complète avec formulaires en cascade"""
    ouvrages = _ouvrages_subdomain_queryset().select_related('type_ouvrage').order_by('nom_ouvrage')

    context = {
        'title': 'Gestion Complète des Ouvrages',
        'ouvrages': ouvrages[:20],
    }
    return render(request, 'ouvrages/gestion_complete.html', context)


# ========== IMPORT/EXPORT EXCEL POUR TARIFS VOLUMÉTRIQUES ==========

def export_tarifs_excel(request):
    """Export des tarifs volumétriques avec tranches vers Excel"""
    try:
        # Créer un nouveau workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Tarifs Volumétriques"

        # Styles
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True, size=12)
        border_style = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        # En-têtes
        headers = [
            'ID Tarif', 'Ouvrage', 'Date Début', 'Date Fin',
            'Prix Abonnement', 'Actif', 'Tranche Supérieure (m³)', 'Tarif (Ar/m³)'
        ]

        for col, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col)
            cell.value = header
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = border_style

        # Récupérer tous les tarifs avec leurs tranches
        tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('ouvrage__nom', '-datedebuttarif')

        row = 2
        for tarif in tarifs:
            tranches = tarif.tranches.all().order_by('tranchesuperieur')

            if tranches.exists():
                # Si le tarif a des tranches, une ligne par tranche
                for tranche in tranches:
                    ws.cell(row=row, column=1).value = str(tarif.id)
                    ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                    ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                    ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                    ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                    ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                    ws.cell(row=row, column=7).value = int(tranche.tranchesuperieur) if tranche.tranchesuperieur else 0
                    ws.cell(row=row, column=8).value = int(tranche.tarif) if tranche.tarif else 0

                    # Appliquer les bordures
                    for col in range(1, 9):
                        ws.cell(row=row, column=col).border = border_style

                    row += 1
            else:
                # Si le tarif n'a pas de tranches, une ligne vide pour les tranches
                ws.cell(row=row, column=1).value = str(tarif.id)
                ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                ws.cell(row=row, column=7).value = ''
                ws.cell(row=row, column=8).value = ''

                # Appliquer les bordures
                for col in range(1, 9):
                    ws.cell(row=row, column=col).border = border_style

                row += 1

        # Ajuster la largeur des colonnes
        column_widths = [35, 30, 15, 15, 18, 10, 22, 18]
        for col, width in enumerate(column_widths, start=1):
            ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = width

        # Créer la réponse HTTP avec le fichier Excel
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename=tarifs_volumetriques_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'

        wb.save(response)
        return response

    except Exception as e:
        messages.error(request, f'Erreur lors de l\'export Excel : {str(e)}')
        return redirect('ouvrages:gestion_complete')


@csrf_exempt
def import_tarifs_excel(request):
    """Import des tarifs volumétriques avec tranches depuis Excel"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        updated_count = 0
        errors = []

        # Dictionnaire pour regrouper les tranches par tarif
        tarifs_data = {}

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    ouvrage_nom = str(row[1]).strip() if row[1] else None
                    date_debut_str = str(row[2]).strip() if row[2] else None
                    date_fin_str = str(row[3]).strip() if row[3] else None
                    prix_abonnement = row[4] if row[4] is not None else 0
                    actif_str = str(row[5]).strip().lower() if row[5] else 'oui'
                    tranche_superieur = row[6] if row[6] is not None else None
                    tarif_tranche = row[7] if row[7] is not None else None

                    # Validation des champs obligatoires
                    if not ouvrage_nom or not date_debut_str:
                        errors.append(f"Ligne {row_num}: Ouvrage et Date Début sont obligatoires")
                        continue

                    # Récupérer l'ouvrage
                    try:
                        ouvrage = _ouvrages_subdomain_queryset().get(nom_ouvrage=ouvrage_nom)
                    except OrgOuvrage.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Ouvrage '{ouvrage_nom}' introuvable")
                        continue

                    # Parser les dates
                    try:
                        date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
                    except ValueError:
                        errors.append(f"Ligne {row_num}: Format de date début invalide (attendu: AAAA-MM-JJ)")
                        continue

                    date_fin = None
                    if date_fin_str and date_fin_str != 'None':
                        try:
                            date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
                        except ValueError:
                            errors.append(f"Ligne {row_num}: Format de date fin invalide (attendu: AAAA-MM-JJ)")
                            continue

                    actif = actif_str in ['oui', 'yes', 'true', '1']

                    # Créer ou récupérer le tarif volumétrique
                    if tarif_id and tarif_id != 'None':
                        # Mise à jour d'un tarif existant
                        try:
                            tarif = TarifVolumetrique.objects.get(id=tarif_id)
                            tarif.ouvrage = ouvrage
                            tarif.datedebuttarif = date_debut
                            tarif.datefintarif = date_fin
                            tarif.prixabonnement = prix_abonnement
                            tarif.actif = actif
                            tarif.save()

                            # Utiliser l'ID du tarif comme clé
                            tarif_key = str(tarif.id)
                            if tarif_key not in tarifs_data:
                                tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': True}

                        except TarifVolumetrique.DoesNotExist:
                            errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                            continue
                    else:
                        # Créer un nouveau tarif (générer une clé unique basée sur ouvrage + date)
                        tarif_key = f"{ouvrage.id}_{date_debut}"

                        if tarif_key not in tarifs_data:
                            tarif = TarifVolumetrique.objects.create(
                                ouvrage=ouvrage,
                                datedebuttarif=date_debut,
                                datefintarif=date_fin,
                                prixabonnement=prix_abonnement,
                                actif=actif
                            )
                            tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': False}
                        else:
                            tarif = tarifs_data[tarif_key]['tarif']

                    # Ajouter la tranche si elle existe (utiliser la même clé)
                    if tranche_superieur is not None and tarif_tranche is not None:
                        if tarif_key in tarifs_data:
                            tarifs_data[tarif_key]['tranches'].append({
                                'tranchesuperieur': int(tranche_superieur),
                                'tarif': int(tarif_tranche)
                            })

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

            # Créer les tranches pour chaque tarif
            tranches_count = 0
            for tarif_key, data in tarifs_data.items():
                tarif = data['tarif']

                # Supprimer les anciennes tranches si c'est une mise à jour
                if data['updated']:
                    TarifVolumetrique2.objects.filter(tarifvolumetrique=tarif).delete()
                    updated_count += 1
                else:
                    imported_count += 1

                # Créer les nouvelles tranches
                for tranche_data in data['tranches']:
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=tranche_data['tranchesuperieur'],
                        tarif=tranche_data['tarif']
                    )
                    tranches_count += 1

        response_data = {
            'success': True,
            'imported': imported_count,
            'updated': updated_count,
            'tranches_created': tranches_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


@csrf_exempt
def import_tranches_only(request):
    """Import UNIQUEMENT des tranches (3 colonnes: tarif_id, tranche_superieur, tarif)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        errors = []

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    tranche_superieur = row[1] if row[1] is not None else None
                    tarif_prix = row[2] if row[2] is not None else None

                    # Validation des champs obligatoires
                    if not tarif_id or tranche_superieur is None or tarif_prix is None:
                        errors.append(f"Ligne {row_num}: Tous les champs sont obligatoires (tarif_id, tranche_superieur, tarif)")
                        continue

                    # Récupérer le tarif volumétrique
                    try:
                        tarif = TarifVolumetrique.objects.get(id=tarif_id)
                    except TarifVolumetrique.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                        continue

                    # Créer la tranche
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=int(tranche_superieur),
                        tarif=int(tarif_prix)
                    )
                    imported_count += 1

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

        response_data = {
            'success': True,
            'imported': imported_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


def tarifs_import_export_page(request):
    """Page pour l'import/export des tarifs volumétriques"""
    tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('-datedebuttarif')[:50]

    context = {
        'title': 'Import/Export Tarifs Volumétriques',
        'tarifs': tarifs,
    }
    return render(request, 'ouvrages/tarifs_import_export.html', context)


def api_communes(request):
    """API pour récupérer les communes par district"""
    try:
        district_id = request.GET.get('district_id')
        if district_id:
            communes = Commune.objects.filter(district_id=district_id).order_by('nom_commune')
        else:
            communes = Commune.objects.all().order_by('district__nom_district', 'nom_commune')

        data = []
        for commune in communes:
            data.append({
                'id': str(commune.id),
                'nom_commune': commune.nom_commune,
                'district_id': str(commune.district_id),
                'district_nom': commune.district.nom_district,
                'region_id': str(commune.district.region_id),
                'region_nom': commune.district.region.nom_region,
            })
        return JsonResponse(data, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def ouvrages_gestion_complete(request):
    """Vue pour la gestion complète avec formulaires en cascade"""
    ouvrages = _ouvrages_subdomain_queryset().select_related('type_ouvrage').order_by('nom_ouvrage')

    context = {
        'title': 'Gestion Complète des Ouvrages',
        'ouvrages': ouvrages[:20],
    }
    return render(request, 'ouvrages/gestion_complete.html', context)


# ========== IMPORT/EXPORT EXCEL POUR TARIFS VOLUMÉTRIQUES ==========

def export_tarifs_excel(request):
    """Export des tarifs volumétriques avec tranches vers Excel"""
    try:
        # Créer un nouveau workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Tarifs Volumétriques"

        # Styles
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True, size=12)
        border_style = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        # En-têtes
        headers = [
            'ID Tarif', 'Ouvrage', 'Date Début', 'Date Fin',
            'Prix Abonnement', 'Actif', 'Tranche Supérieure (m³)', 'Tarif (Ar/m³)'
        ]

        for col, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col)
            cell.value = header
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = border_style

        # Récupérer tous les tarifs avec leurs tranches
        tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('ouvrage__nom', '-datedebuttarif')

        row = 2
        for tarif in tarifs:
            tranches = tarif.tranches.all().order_by('tranchesuperieur')

            if tranches.exists():
                # Si le tarif a des tranches, une ligne par tranche
                for tranche in tranches:
                    ws.cell(row=row, column=1).value = str(tarif.id)
                    ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                    ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                    ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                    ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                    ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                    ws.cell(row=row, column=7).value = int(tranche.tranchesuperieur) if tranche.tranchesuperieur else 0
                    ws.cell(row=row, column=8).value = int(tranche.tarif) if tranche.tarif else 0

                    # Appliquer les bordures
                    for col in range(1, 9):
                        ws.cell(row=row, column=col).border = border_style

                    row += 1
            else:
                # Si le tarif n'a pas de tranches, une ligne vide pour les tranches
                ws.cell(row=row, column=1).value = str(tarif.id)
                ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                ws.cell(row=row, column=7).value = ''
                ws.cell(row=row, column=8).value = ''

                # Appliquer les bordures
                for col in range(1, 9):
                    ws.cell(row=row, column=col).border = border_style

                row += 1

        # Ajuster la largeur des colonnes
        column_widths = [35, 30, 15, 15, 18, 10, 22, 18]
        for col, width in enumerate(column_widths, start=1):
            ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = width

        # Créer la réponse HTTP avec le fichier Excel
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename=tarifs_volumetriques_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'

        wb.save(response)
        return response

    except Exception as e:
        messages.error(request, f'Erreur lors de l\'export Excel : {str(e)}')
        return redirect('ouvrages:gestion_complete')


@csrf_exempt
def import_tarifs_excel(request):
    """Import des tarifs volumétriques avec tranches depuis Excel"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        updated_count = 0
        errors = []

        # Dictionnaire pour regrouper les tranches par tarif
        tarifs_data = {}

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    ouvrage_nom = str(row[1]).strip() if row[1] else None
                    date_debut_str = str(row[2]).strip() if row[2] else None
                    date_fin_str = str(row[3]).strip() if row[3] else None
                    prix_abonnement = row[4] if row[4] is not None else 0
                    actif_str = str(row[5]).strip().lower() if row[5] else 'oui'
                    tranche_superieur = row[6] if row[6] is not None else None
                    tarif_tranche = row[7] if row[7] is not None else None

                    # Validation des champs obligatoires
                    if not ouvrage_nom or not date_debut_str:
                        errors.append(f"Ligne {row_num}: Ouvrage et Date Début sont obligatoires")
                        continue

                    # Récupérer l'ouvrage
                    try:
                        ouvrage = _ouvrages_subdomain_queryset().get(nom_ouvrage=ouvrage_nom)
                    except OrgOuvrage.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Ouvrage '{ouvrage_nom}' introuvable")
                        continue

                    # Parser les dates
                    try:
                        date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
                    except ValueError:
                        errors.append(f"Ligne {row_num}: Format de date début invalide (attendu: AAAA-MM-JJ)")
                        continue

                    date_fin = None
                    if date_fin_str and date_fin_str != 'None':
                        try:
                            date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
                        except ValueError:
                            errors.append(f"Ligne {row_num}: Format de date fin invalide (attendu: AAAA-MM-JJ)")
                            continue

                    actif = actif_str in ['oui', 'yes', 'true', '1']

                    # Créer ou récupérer le tarif volumétrique
                    if tarif_id and tarif_id != 'None':
                        # Mise à jour d'un tarif existant
                        try:
                            tarif = TarifVolumetrique.objects.get(id=tarif_id)
                            tarif.ouvrage = ouvrage
                            tarif.datedebuttarif = date_debut
                            tarif.datefintarif = date_fin
                            tarif.prixabonnement = prix_abonnement
                            tarif.actif = actif
                            tarif.save()

                            # Utiliser l'ID du tarif comme clé
                            tarif_key = str(tarif.id)
                            if tarif_key not in tarifs_data:
                                tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': True}

                        except TarifVolumetrique.DoesNotExist:
                            errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                            continue
                    else:
                        # Créer un nouveau tarif (générer une clé unique basée sur ouvrage + date)
                        tarif_key = f"{ouvrage.id}_{date_debut}"

                        if tarif_key not in tarifs_data:
                            tarif = TarifVolumetrique.objects.create(
                                ouvrage=ouvrage,
                                datedebuttarif=date_debut,
                                datefintarif=date_fin,
                                prixabonnement=prix_abonnement,
                                actif=actif
                            )
                            tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': False}
                        else:
                            tarif = tarifs_data[tarif_key]['tarif']

                    # Ajouter la tranche si elle existe (utiliser la même clé)
                    if tranche_superieur is not None and tarif_tranche is not None:
                        if tarif_key in tarifs_data:
                            tarifs_data[tarif_key]['tranches'].append({
                                'tranchesuperieur': int(tranche_superieur),
                                'tarif': int(tarif_tranche)
                            })

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

            # Créer les tranches pour chaque tarif
            tranches_count = 0
            for tarif_key, data in tarifs_data.items():
                tarif = data['tarif']

                # Supprimer les anciennes tranches si c'est une mise à jour
                if data['updated']:
                    TarifVolumetrique2.objects.filter(tarifvolumetrique=tarif).delete()
                    updated_count += 1
                else:
                    imported_count += 1

                # Créer les nouvelles tranches
                for tranche_data in data['tranches']:
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=tranche_data['tranchesuperieur'],
                        tarif=tranche_data['tarif']
                    )
                    tranches_count += 1

        response_data = {
            'success': True,
            'imported': imported_count,
            'updated': updated_count,
            'tranches_created': tranches_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


@csrf_exempt
def import_tranches_only(request):
    """Import UNIQUEMENT des tranches (3 colonnes: tarif_id, tranche_superieur, tarif)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        errors = []

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    tranche_superieur = row[1] if row[1] is not None else None
                    tarif_prix = row[2] if row[2] is not None else None

                    # Validation des champs obligatoires
                    if not tarif_id or tranche_superieur is None or tarif_prix is None:
                        errors.append(f"Ligne {row_num}: Tous les champs sont obligatoires (tarif_id, tranche_superieur, tarif)")
                        continue

                    # Récupérer le tarif volumétrique
                    try:
                        tarif = TarifVolumetrique.objects.get(id=tarif_id)
                    except TarifVolumetrique.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                        continue

                    # Créer la tranche
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=int(tranche_superieur),
                        tarif=int(tarif_prix)
                    )
                    imported_count += 1

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

        response_data = {
            'success': True,
            'imported': imported_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


def tarifs_import_export_page(request):
    """Page pour l'import/export des tarifs volumétriques"""
    tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('-datedebuttarif')[:50]

    context = {
        'title': 'Import/Export Tarifs Volumétriques',
        'tarifs': tarifs,
    }
    return render(request, 'ouvrages/tarifs_import_export.html', context)


def api_fokontanys(request):
    """API pour récupérer les fokontanys par commune"""
    try:
        commune_id = request.GET.get('commune_id')
        if commune_id:
            fokontanys = Fokontany.objects.filter(commune_id=commune_id).order_by('nom_fokontany')
        else:
            fokontanys = Fokontany.objects.all().order_by('commune__nom_commune', 'nom_fokontany')

        data = []
        for fokontany in fokontanys:
            data.append({
                'id': str(fokontany.id),
                'nom_fokontany': fokontany.nom_fokontany,
                'commune_id': str(fokontany.commune_id),
                'commune_nom': fokontany.commune.nom_commune,
                'district_id': str(fokontany.commune.district_id),
                'district_nom': fokontany.commune.district.nom_district,
                'region_id': str(fokontany.commune.district.region_id),
                'region_nom': fokontany.commune.district.region.nom_region,
            })
        return JsonResponse(data, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def ouvrages_gestion_complete(request):
    """Vue pour la gestion complète avec formulaires en cascade"""
    ouvrages = _ouvrages_subdomain_queryset().select_related('type_ouvrage').order_by('nom_ouvrage')

    context = {
        'title': 'Gestion Complète des Ouvrages',
        'ouvrages': ouvrages[:20],
    }
    return render(request, 'ouvrages/gestion_complete.html', context)


# ========== IMPORT/EXPORT EXCEL POUR TARIFS VOLUMÉTRIQUES ==========

def export_tarifs_excel(request):
    """Export des tarifs volumétriques avec tranches vers Excel"""
    try:
        # Créer un nouveau workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Tarifs Volumétriques"

        # Styles
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True, size=12)
        border_style = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        # En-têtes
        headers = [
            'ID Tarif', 'Ouvrage', 'Date Début', 'Date Fin',
            'Prix Abonnement', 'Actif', 'Tranche Supérieure (m³)', 'Tarif (Ar/m³)'
        ]

        for col, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col)
            cell.value = header
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = border_style

        # Récupérer tous les tarifs avec leurs tranches
        tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('ouvrage__nom', '-datedebuttarif')

        row = 2
        for tarif in tarifs:
            tranches = tarif.tranches.all().order_by('tranchesuperieur')

            if tranches.exists():
                # Si le tarif a des tranches, une ligne par tranche
                for tranche in tranches:
                    ws.cell(row=row, column=1).value = str(tarif.id)
                    ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                    ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                    ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                    ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                    ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                    ws.cell(row=row, column=7).value = int(tranche.tranchesuperieur) if tranche.tranchesuperieur else 0
                    ws.cell(row=row, column=8).value = int(tranche.tarif) if tranche.tarif else 0

                    # Appliquer les bordures
                    for col in range(1, 9):
                        ws.cell(row=row, column=col).border = border_style

                    row += 1
            else:
                # Si le tarif n'a pas de tranches, une ligne vide pour les tranches
                ws.cell(row=row, column=1).value = str(tarif.id)
                ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                ws.cell(row=row, column=7).value = ''
                ws.cell(row=row, column=8).value = ''

                # Appliquer les bordures
                for col in range(1, 9):
                    ws.cell(row=row, column=col).border = border_style

                row += 1

        # Ajuster la largeur des colonnes
        column_widths = [35, 30, 15, 15, 18, 10, 22, 18]
        for col, width in enumerate(column_widths, start=1):
            ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = width

        # Créer la réponse HTTP avec le fichier Excel
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename=tarifs_volumetriques_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'

        wb.save(response)
        return response

    except Exception as e:
        messages.error(request, f'Erreur lors de l\'export Excel : {str(e)}')
        return redirect('ouvrages:gestion_complete')


@csrf_exempt
def import_tarifs_excel(request):
    """Import des tarifs volumétriques avec tranches depuis Excel"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        updated_count = 0
        errors = []

        # Dictionnaire pour regrouper les tranches par tarif
        tarifs_data = {}

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    ouvrage_nom = str(row[1]).strip() if row[1] else None
                    date_debut_str = str(row[2]).strip() if row[2] else None
                    date_fin_str = str(row[3]).strip() if row[3] else None
                    prix_abonnement = row[4] if row[4] is not None else 0
                    actif_str = str(row[5]).strip().lower() if row[5] else 'oui'
                    tranche_superieur = row[6] if row[6] is not None else None
                    tarif_tranche = row[7] if row[7] is not None else None

                    # Validation des champs obligatoires
                    if not ouvrage_nom or not date_debut_str:
                        errors.append(f"Ligne {row_num}: Ouvrage et Date Début sont obligatoires")
                        continue

                    # Récupérer l'ouvrage
                    try:
                        ouvrage = _ouvrages_subdomain_queryset().get(nom_ouvrage=ouvrage_nom)
                    except OrgOuvrage.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Ouvrage '{ouvrage_nom}' introuvable")
                        continue

                    # Parser les dates
                    try:
                        date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
                    except ValueError:
                        errors.append(f"Ligne {row_num}: Format de date début invalide (attendu: AAAA-MM-JJ)")
                        continue

                    date_fin = None
                    if date_fin_str and date_fin_str != 'None':
                        try:
                            date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
                        except ValueError:
                            errors.append(f"Ligne {row_num}: Format de date fin invalide (attendu: AAAA-MM-JJ)")
                            continue

                    actif = actif_str in ['oui', 'yes', 'true', '1']

                    # Créer ou récupérer le tarif volumétrique
                    if tarif_id and tarif_id != 'None':
                        # Mise à jour d'un tarif existant
                        try:
                            tarif = TarifVolumetrique.objects.get(id=tarif_id)
                            tarif.ouvrage = ouvrage
                            tarif.datedebuttarif = date_debut
                            tarif.datefintarif = date_fin
                            tarif.prixabonnement = prix_abonnement
                            tarif.actif = actif
                            tarif.save()

                            # Utiliser l'ID du tarif comme clé
                            tarif_key = str(tarif.id)
                            if tarif_key not in tarifs_data:
                                tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': True}

                        except TarifVolumetrique.DoesNotExist:
                            errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                            continue
                    else:
                        # Créer un nouveau tarif (générer une clé unique basée sur ouvrage + date)
                        tarif_key = f"{ouvrage.id}_{date_debut}"

                        if tarif_key not in tarifs_data:
                            tarif = TarifVolumetrique.objects.create(
                                ouvrage=ouvrage,
                                datedebuttarif=date_debut,
                                datefintarif=date_fin,
                                prixabonnement=prix_abonnement,
                                actif=actif
                            )
                            tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': False}
                        else:
                            tarif = tarifs_data[tarif_key]['tarif']

                    # Ajouter la tranche si elle existe (utiliser la même clé)
                    if tranche_superieur is not None and tarif_tranche is not None:
                        if tarif_key in tarifs_data:
                            tarifs_data[tarif_key]['tranches'].append({
                                'tranchesuperieur': int(tranche_superieur),
                                'tarif': int(tarif_tranche)
                            })

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

            # Créer les tranches pour chaque tarif
            tranches_count = 0
            for tarif_key, data in tarifs_data.items():
                tarif = data['tarif']

                # Supprimer les anciennes tranches si c'est une mise à jour
                if data['updated']:
                    TarifVolumetrique2.objects.filter(tarifvolumetrique=tarif).delete()
                    updated_count += 1
                else:
                    imported_count += 1

                # Créer les nouvelles tranches
                for tranche_data in data['tranches']:
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=tranche_data['tranchesuperieur'],
                        tarif=tranche_data['tarif']
                    )
                    tranches_count += 1

        response_data = {
            'success': True,
            'imported': imported_count,
            'updated': updated_count,
            'tranches_created': tranches_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


@csrf_exempt
def import_tranches_only(request):
    """Import UNIQUEMENT des tranches (3 colonnes: tarif_id, tranche_superieur, tarif)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        errors = []

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    tranche_superieur = row[1] if row[1] is not None else None
                    tarif_prix = row[2] if row[2] is not None else None

                    # Validation des champs obligatoires
                    if not tarif_id or tranche_superieur is None or tarif_prix is None:
                        errors.append(f"Ligne {row_num}: Tous les champs sont obligatoires (tarif_id, tranche_superieur, tarif)")
                        continue

                    # Récupérer le tarif volumétrique
                    try:
                        tarif = TarifVolumetrique.objects.get(id=tarif_id)
                    except TarifVolumetrique.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                        continue

                    # Créer la tranche
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=int(tranche_superieur),
                        tarif=int(tarif_prix)
                    )
                    imported_count += 1

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

        response_data = {
            'success': True,
            'imported': imported_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


def tarifs_import_export_page(request):
    """Page pour l'import/export des tarifs volumétriques"""
    tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('-datedebuttarif')[:50]

    context = {
        'title': 'Import/Export Tarifs Volumétriques',
        'tarifs': tarifs,
    }
    return render(request, 'ouvrages/tarifs_import_export.html', context)


def api_villages(request):
    """API pour récupérer les villages par fokontany"""
    try:
        fokontany_id = request.GET.get('fokontany_id')
        if fokontany_id:
            villages = Village.objects.filter(fokontany_id=fokontany_id).order_by('nom_village')
        else:
            villages = Village.objects.all().order_by('fokontany__nom_fokontany', 'nom_village')

        data = []
        for village in villages:
            data.append({
                'id': str(village.id),
                'nom_village': village.nom_village,
                'fokontany_id': str(village.fokontany_id) if village.fokontany else None,
                'fokontany_nom': village.fokontany.nom_fokontany if village.fokontany else None,
                'commune_id': str(village.commune_obj.id) if village.commune_obj else None,
                'commune_nom': village.commune_obj.nom_commune if village.commune_obj else None,
            })
        return JsonResponse(data, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def ouvrages_gestion_complete(request):
    """Vue pour la gestion complète avec formulaires en cascade"""
    ouvrages = _ouvrages_subdomain_queryset().select_related('type_ouvrage').order_by('nom_ouvrage')

    context = {
        'title': 'Gestion Complète des Ouvrages',
        'ouvrages': ouvrages[:20],
    }
    return render(request, 'ouvrages/gestion_complete.html', context)


# ========== IMPORT/EXPORT EXCEL POUR TARIFS VOLUMÉTRIQUES ==========

def export_tarifs_excel(request):
    """Export des tarifs volumétriques avec tranches vers Excel"""
    try:
        # Créer un nouveau workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Tarifs Volumétriques"

        # Styles
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True, size=12)
        border_style = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        # En-têtes
        headers = [
            'ID Tarif', 'Ouvrage', 'Date Début', 'Date Fin',
            'Prix Abonnement', 'Actif', 'Tranche Supérieure (m³)', 'Tarif (Ar/m³)'
        ]

        for col, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col)
            cell.value = header
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = border_style

        # Récupérer tous les tarifs avec leurs tranches
        tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('ouvrage__nom', '-datedebuttarif')

        row = 2
        for tarif in tarifs:
            tranches = tarif.tranches.all().order_by('tranchesuperieur')

            if tranches.exists():
                # Si le tarif a des tranches, une ligne par tranche
                for tranche in tranches:
                    ws.cell(row=row, column=1).value = str(tarif.id)
                    ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                    ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                    ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                    ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                    ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                    ws.cell(row=row, column=7).value = int(tranche.tranchesuperieur) if tranche.tranchesuperieur else 0
                    ws.cell(row=row, column=8).value = int(tranche.tarif) if tranche.tarif else 0

                    # Appliquer les bordures
                    for col in range(1, 9):
                        ws.cell(row=row, column=col).border = border_style

                    row += 1
            else:
                # Si le tarif n'a pas de tranches, une ligne vide pour les tranches
                ws.cell(row=row, column=1).value = str(tarif.id)
                ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                ws.cell(row=row, column=7).value = ''
                ws.cell(row=row, column=8).value = ''

                # Appliquer les bordures
                for col in range(1, 9):
                    ws.cell(row=row, column=col).border = border_style

                row += 1

        # Ajuster la largeur des colonnes
        column_widths = [35, 30, 15, 15, 18, 10, 22, 18]
        for col, width in enumerate(column_widths, start=1):
            ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = width

        # Créer la réponse HTTP avec le fichier Excel
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename=tarifs_volumetriques_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'

        wb.save(response)
        return response

    except Exception as e:
        messages.error(request, f'Erreur lors de l\'export Excel : {str(e)}')
        return redirect('ouvrages:gestion_complete')


@csrf_exempt
def import_tarifs_excel(request):
    """Import des tarifs volumétriques avec tranches depuis Excel"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        updated_count = 0
        errors = []

        # Dictionnaire pour regrouper les tranches par tarif
        tarifs_data = {}

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    ouvrage_nom = str(row[1]).strip() if row[1] else None
                    date_debut_str = str(row[2]).strip() if row[2] else None
                    date_fin_str = str(row[3]).strip() if row[3] else None
                    prix_abonnement = row[4] if row[4] is not None else 0
                    actif_str = str(row[5]).strip().lower() if row[5] else 'oui'
                    tranche_superieur = row[6] if row[6] is not None else None
                    tarif_tranche = row[7] if row[7] is not None else None

                    # Validation des champs obligatoires
                    if not ouvrage_nom or not date_debut_str:
                        errors.append(f"Ligne {row_num}: Ouvrage et Date Début sont obligatoires")
                        continue

                    # Récupérer l'ouvrage
                    try:
                        ouvrage = _ouvrages_subdomain_queryset().get(nom_ouvrage=ouvrage_nom)
                    except OrgOuvrage.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Ouvrage '{ouvrage_nom}' introuvable")
                        continue

                    # Parser les dates
                    try:
                        date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
                    except ValueError:
                        errors.append(f"Ligne {row_num}: Format de date début invalide (attendu: AAAA-MM-JJ)")
                        continue

                    date_fin = None
                    if date_fin_str and date_fin_str != 'None':
                        try:
                            date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
                        except ValueError:
                            errors.append(f"Ligne {row_num}: Format de date fin invalide (attendu: AAAA-MM-JJ)")
                            continue

                    actif = actif_str in ['oui', 'yes', 'true', '1']

                    # Créer ou récupérer le tarif volumétrique
                    if tarif_id and tarif_id != 'None':
                        # Mise à jour d'un tarif existant
                        try:
                            tarif = TarifVolumetrique.objects.get(id=tarif_id)
                            tarif.ouvrage = ouvrage
                            tarif.datedebuttarif = date_debut
                            tarif.datefintarif = date_fin
                            tarif.prixabonnement = prix_abonnement
                            tarif.actif = actif
                            tarif.save()

                            # Utiliser l'ID du tarif comme clé
                            tarif_key = str(tarif.id)
                            if tarif_key not in tarifs_data:
                                tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': True}

                        except TarifVolumetrique.DoesNotExist:
                            errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                            continue
                    else:
                        # Créer un nouveau tarif (générer une clé unique basée sur ouvrage + date)
                        tarif_key = f"{ouvrage.id}_{date_debut}"

                        if tarif_key not in tarifs_data:
                            tarif = TarifVolumetrique.objects.create(
                                ouvrage=ouvrage,
                                datedebuttarif=date_debut,
                                datefintarif=date_fin,
                                prixabonnement=prix_abonnement,
                                actif=actif
                            )
                            tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': False}
                        else:
                            tarif = tarifs_data[tarif_key]['tarif']

                    # Ajouter la tranche si elle existe (utiliser la même clé)
                    if tranche_superieur is not None and tarif_tranche is not None:
                        if tarif_key in tarifs_data:
                            tarifs_data[tarif_key]['tranches'].append({
                                'tranchesuperieur': int(tranche_superieur),
                                'tarif': int(tarif_tranche)
                            })

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

            # Créer les tranches pour chaque tarif
            tranches_count = 0
            for tarif_key, data in tarifs_data.items():
                tarif = data['tarif']

                # Supprimer les anciennes tranches si c'est une mise à jour
                if data['updated']:
                    TarifVolumetrique2.objects.filter(tarifvolumetrique=tarif).delete()
                    updated_count += 1
                else:
                    imported_count += 1

                # Créer les nouvelles tranches
                for tranche_data in data['tranches']:
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=tranche_data['tranchesuperieur'],
                        tarif=tranche_data['tarif']
                    )
                    tranches_count += 1

        response_data = {
            'success': True,
            'imported': imported_count,
            'updated': updated_count,
            'tranches_created': tranches_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


@csrf_exempt
def import_tranches_only(request):
    """Import UNIQUEMENT des tranches (3 colonnes: tarif_id, tranche_superieur, tarif)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        errors = []

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    tranche_superieur = row[1] if row[1] is not None else None
                    tarif_prix = row[2] if row[2] is not None else None

                    # Validation des champs obligatoires
                    if not tarif_id or tranche_superieur is None or tarif_prix is None:
                        errors.append(f"Ligne {row_num}: Tous les champs sont obligatoires (tarif_id, tranche_superieur, tarif)")
                        continue

                    # Récupérer le tarif volumétrique
                    try:
                        tarif = TarifVolumetrique.objects.get(id=tarif_id)
                    except TarifVolumetrique.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                        continue

                    # Créer la tranche
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=int(tranche_superieur),
                        tarif=int(tarif_prix)
                    )
                    imported_count += 1

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

        response_data = {
            'success': True,
            'imported': imported_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


def tarifs_import_export_page(request):
    """Page pour l'import/export des tarifs volumétriques"""
    tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('-datedebuttarif')[:50]

    context = {
        'title': 'Import/Export Tarifs Volumétriques',
        'tarifs': tarifs,
    }
    return render(request, 'ouvrages/tarifs_import_export.html', context)


def api_parcelles(request):
    """API pour récupérer les parcelles par village"""
    try:
        village_id = request.GET.get('village_id')
        if village_id:
            parcelles = Parcelle.objects.filter(village_id=village_id).order_by('reference_parcelle')
        else:
            parcelles = Parcelle.objects.all().order_by('village__nom_village', 'reference_parcelle')

        data = []
        for parcelle in parcelles:
            data.append({
                'id': str(parcelle.id),
                'reference_parcelle': parcelle.reference_parcelle,
                'village_id': str(parcelle.village_id),
                'village_nom': parcelle.village.nom_village,
                'nombre_habitants': parcelle.nombre_habitants,
                'nombre_menages': parcelle.nombre_menages,
                'source_donnees': parcelle.source_donnees,
            })
        return JsonResponse(data, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def ouvrages_gestion_complete(request):
    """Vue pour la gestion complète avec formulaires en cascade"""
    ouvrages = _ouvrages_subdomain_queryset().select_related('type_ouvrage').order_by('nom_ouvrage')

    context = {
        'title': 'Gestion Complète des Ouvrages',
        'ouvrages': ouvrages[:20],
    }
    return render(request, 'ouvrages/gestion_complete.html', context)


# ========== IMPORT/EXPORT EXCEL POUR TARIFS VOLUMÉTRIQUES ==========

def export_tarifs_excel(request):
    """Export des tarifs volumétriques avec tranches vers Excel"""
    try:
        # Créer un nouveau workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Tarifs Volumétriques"

        # Styles
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True, size=12)
        border_style = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        # En-têtes
        headers = [
            'ID Tarif', 'Ouvrage', 'Date Début', 'Date Fin',
            'Prix Abonnement', 'Actif', 'Tranche Supérieure (m³)', 'Tarif (Ar/m³)'
        ]

        for col, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col)
            cell.value = header
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = border_style

        # Récupérer tous les tarifs avec leurs tranches
        tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('ouvrage__nom', '-datedebuttarif')

        row = 2
        for tarif in tarifs:
            tranches = tarif.tranches.all().order_by('tranchesuperieur')

            if tranches.exists():
                # Si le tarif a des tranches, une ligne par tranche
                for tranche in tranches:
                    ws.cell(row=row, column=1).value = str(tarif.id)
                    ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                    ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                    ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                    ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                    ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                    ws.cell(row=row, column=7).value = int(tranche.tranchesuperieur) if tranche.tranchesuperieur else 0
                    ws.cell(row=row, column=8).value = int(tranche.tarif) if tranche.tarif else 0

                    # Appliquer les bordures
                    for col in range(1, 9):
                        ws.cell(row=row, column=col).border = border_style

                    row += 1
            else:
                # Si le tarif n'a pas de tranches, une ligne vide pour les tranches
                ws.cell(row=row, column=1).value = str(tarif.id)
                ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                ws.cell(row=row, column=7).value = ''
                ws.cell(row=row, column=8).value = ''

                # Appliquer les bordures
                for col in range(1, 9):
                    ws.cell(row=row, column=col).border = border_style

                row += 1

        # Ajuster la largeur des colonnes
        column_widths = [35, 30, 15, 15, 18, 10, 22, 18]
        for col, width in enumerate(column_widths, start=1):
            ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = width

        # Créer la réponse HTTP avec le fichier Excel
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename=tarifs_volumetriques_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'

        wb.save(response)
        return response

    except Exception as e:
        messages.error(request, f'Erreur lors de l\'export Excel : {str(e)}')
        return redirect('ouvrages:gestion_complete')


@csrf_exempt
def import_tarifs_excel(request):
    """Import des tarifs volumétriques avec tranches depuis Excel"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        updated_count = 0
        errors = []

        # Dictionnaire pour regrouper les tranches par tarif
        tarifs_data = {}

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    ouvrage_nom = str(row[1]).strip() if row[1] else None
                    date_debut_str = str(row[2]).strip() if row[2] else None
                    date_fin_str = str(row[3]).strip() if row[3] else None
                    prix_abonnement = row[4] if row[4] is not None else 0
                    actif_str = str(row[5]).strip().lower() if row[5] else 'oui'
                    tranche_superieur = row[6] if row[6] is not None else None
                    tarif_tranche = row[7] if row[7] is not None else None

                    # Validation des champs obligatoires
                    if not ouvrage_nom or not date_debut_str:
                        errors.append(f"Ligne {row_num}: Ouvrage et Date Début sont obligatoires")
                        continue

                    # Récupérer l'ouvrage
                    try:
                        ouvrage = _ouvrages_subdomain_queryset().get(nom_ouvrage=ouvrage_nom)
                    except OrgOuvrage.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Ouvrage '{ouvrage_nom}' introuvable")
                        continue

                    # Parser les dates
                    try:
                        date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
                    except ValueError:
                        errors.append(f"Ligne {row_num}: Format de date début invalide (attendu: AAAA-MM-JJ)")
                        continue

                    date_fin = None
                    if date_fin_str and date_fin_str != 'None':
                        try:
                            date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
                        except ValueError:
                            errors.append(f"Ligne {row_num}: Format de date fin invalide (attendu: AAAA-MM-JJ)")
                            continue

                    actif = actif_str in ['oui', 'yes', 'true', '1']

                    # Créer ou récupérer le tarif volumétrique
                    if tarif_id and tarif_id != 'None':
                        # Mise à jour d'un tarif existant
                        try:
                            tarif = TarifVolumetrique.objects.get(id=tarif_id)
                            tarif.ouvrage = ouvrage
                            tarif.datedebuttarif = date_debut
                            tarif.datefintarif = date_fin
                            tarif.prixabonnement = prix_abonnement
                            tarif.actif = actif
                            tarif.save()

                            # Utiliser l'ID du tarif comme clé
                            tarif_key = str(tarif.id)
                            if tarif_key not in tarifs_data:
                                tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': True}

                        except TarifVolumetrique.DoesNotExist:
                            errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                            continue
                    else:
                        # Créer un nouveau tarif (générer une clé unique basée sur ouvrage + date)
                        tarif_key = f"{ouvrage.id}_{date_debut}"

                        if tarif_key not in tarifs_data:
                            tarif = TarifVolumetrique.objects.create(
                                ouvrage=ouvrage,
                                datedebuttarif=date_debut,
                                datefintarif=date_fin,
                                prixabonnement=prix_abonnement,
                                actif=actif
                            )
                            tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': False}
                        else:
                            tarif = tarifs_data[tarif_key]['tarif']

                    # Ajouter la tranche si elle existe (utiliser la même clé)
                    if tranche_superieur is not None and tarif_tranche is not None:
                        if tarif_key in tarifs_data:
                            tarifs_data[tarif_key]['tranches'].append({
                                'tranchesuperieur': int(tranche_superieur),
                                'tarif': int(tarif_tranche)
                            })

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

            # Créer les tranches pour chaque tarif
            tranches_count = 0
            for tarif_key, data in tarifs_data.items():
                tarif = data['tarif']

                # Supprimer les anciennes tranches si c'est une mise à jour
                if data['updated']:
                    TarifVolumetrique2.objects.filter(tarifvolumetrique=tarif).delete()
                    updated_count += 1
                else:
                    imported_count += 1

                # Créer les nouvelles tranches
                for tranche_data in data['tranches']:
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=tranche_data['tranchesuperieur'],
                        tarif=tranche_data['tarif']
                    )
                    tranches_count += 1

        response_data = {
            'success': True,
            'imported': imported_count,
            'updated': updated_count,
            'tranches_created': tranches_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


@csrf_exempt
def import_tranches_only(request):
    """Import UNIQUEMENT des tranches (3 colonnes: tarif_id, tranche_superieur, tarif)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        errors = []

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    tranche_superieur = row[1] if row[1] is not None else None
                    tarif_prix = row[2] if row[2] is not None else None

                    # Validation des champs obligatoires
                    if not tarif_id or tranche_superieur is None or tarif_prix is None:
                        errors.append(f"Ligne {row_num}: Tous les champs sont obligatoires (tarif_id, tranche_superieur, tarif)")
                        continue

                    # Récupérer le tarif volumétrique
                    try:
                        tarif = TarifVolumetrique.objects.get(id=tarif_id)
                    except TarifVolumetrique.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                        continue

                    # Créer la tranche
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=int(tranche_superieur),
                        tarif=int(tarif_prix)
                    )
                    imported_count += 1

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

        response_data = {
            'success': True,
            'imported': imported_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


def tarifs_import_export_page(request):
    """Page pour l'import/export des tarifs volumétriques"""
    tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('-datedebuttarif')[:50]

    context = {
        'title': 'Import/Export Tarifs Volumétriques',
        'tarifs': tarifs,
    }
    return render(request, 'ouvrages/tarifs_import_export.html', context)


# APIs pour les formulaires en cascade - Tables liées aux ouvrages

def api_points_eau(request):
    """API pour récupérer les points d'eau par ouvrage"""
    try:
        ouvrage_id = request.GET.get('ouvrage_id')
        if ouvrage_id:
            points_eau = PointEau.objects.select_related(
                'ouvrage', 'compteur_tete', 'type_point_eau', 'parcelle__village'
            ).filter(ouvrage_id=ouvrage_id).order_by('nomabonne')
        else:
            points_eau = PointEau.objects.select_related(
                'ouvrage', 'compteur_tete', 'type_point_eau', 'parcelle__village'
            ).all().order_by('ouvrage__nom', 'nomabonne')

        data = []
        for point in points_eau:
            data.append({
                'id': str(point.id),
                'nomabonne': point.nomabonne,
                'numeroteleph': point.numeroteleph,
                'contactabonne': point.contactabonne,
                'typeabonne': point.typeabonne,
                'typeabonne_display': point.get_typeabonne_display() if point.typeabonne else None,
                'tarifforfaitaire': float(point.tarifforfaitaire) if point.tarifforfaitaire else None,
                'datebranchement': point.datebranchement.isoformat() if point.datebranchement else None,
                'datearretbranchement': point.datearretbranchement.isoformat() if point.datearretbranchement else None,
                'longitude': float(point.longitude) if point.longitude else None,
                'latitude': float(point.latitude) if point.latitude else None,
                'is_active': point.is_active,
                # Relations existantes
                'ouvrage_id': str(point.ouvrage_id) if point.ouvrage else None,
                'ouvrage_nom': point.ouvrage.nom if point.ouvrage else None,
                # Compteur tête avec objet complet
                'compteur_tete': {
                    'id': str(point.compteur_tete.id) if point.compteur_tete else None,
                    'numerocompteur': point.compteur_tete.numerocompteur if point.compteur_tete else None,
                    'marque': point.compteur_tete.marque if point.compteur_tete else None
                } if point.compteur_tete else None,
                # Type point d'eau avec objet complet
                'type_point_eau': {
                    'id': str(point.type_point_eau.id) if point.type_point_eau else None,
                    'nom_type': point.type_point_eau.nom_type if point.type_point_eau else None,
                    'description': point.type_point_eau.description if point.type_point_eau else None
                } if point.type_point_eau else None,
                # Parcelle avec objet complet
                'parcelle': {
                    'id': str(point.parcelle.id) if point.parcelle else None,
                    'reference_parcelle': point.parcelle.reference_parcelle if point.parcelle else None,
                    'village_nom': point.parcelle.village.nom_village if point.parcelle and point.parcelle.village else None
                } if point.parcelle else None,
            })
        return JsonResponse(data, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def ouvrages_gestion_complete(request):
    """Vue pour la gestion complète avec formulaires en cascade"""
    ouvrages = _ouvrages_subdomain_queryset().select_related('type_ouvrage').order_by('nom_ouvrage')

    context = {
        'title': 'Gestion Complète des Ouvrages',
        'ouvrages': ouvrages[:20],
    }
    return render(request, 'ouvrages/gestion_complete.html', context)


# ========== IMPORT/EXPORT EXCEL POUR TARIFS VOLUMÉTRIQUES ==========

def export_tarifs_excel(request):
    """Export des tarifs volumétriques avec tranches vers Excel"""
    try:
        # Créer un nouveau workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Tarifs Volumétriques"

        # Styles
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True, size=12)
        border_style = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        # En-têtes
        headers = [
            'ID Tarif', 'Ouvrage', 'Date Début', 'Date Fin',
            'Prix Abonnement', 'Actif', 'Tranche Supérieure (m³)', 'Tarif (Ar/m³)'
        ]

        for col, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col)
            cell.value = header
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = border_style

        # Récupérer tous les tarifs avec leurs tranches
        tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('ouvrage__nom', '-datedebuttarif')

        row = 2
        for tarif in tarifs:
            tranches = tarif.tranches.all().order_by('tranchesuperieur')

            if tranches.exists():
                # Si le tarif a des tranches, une ligne par tranche
                for tranche in tranches:
                    ws.cell(row=row, column=1).value = str(tarif.id)
                    ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                    ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                    ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                    ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                    ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                    ws.cell(row=row, column=7).value = int(tranche.tranchesuperieur) if tranche.tranchesuperieur else 0
                    ws.cell(row=row, column=8).value = int(tranche.tarif) if tranche.tarif else 0

                    # Appliquer les bordures
                    for col in range(1, 9):
                        ws.cell(row=row, column=col).border = border_style

                    row += 1
            else:
                # Si le tarif n'a pas de tranches, une ligne vide pour les tranches
                ws.cell(row=row, column=1).value = str(tarif.id)
                ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                ws.cell(row=row, column=7).value = ''
                ws.cell(row=row, column=8).value = ''

                # Appliquer les bordures
                for col in range(1, 9):
                    ws.cell(row=row, column=col).border = border_style

                row += 1

        # Ajuster la largeur des colonnes
        column_widths = [35, 30, 15, 15, 18, 10, 22, 18]
        for col, width in enumerate(column_widths, start=1):
            ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = width

        # Créer la réponse HTTP avec le fichier Excel
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename=tarifs_volumetriques_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'

        wb.save(response)
        return response

    except Exception as e:
        messages.error(request, f'Erreur lors de l\'export Excel : {str(e)}')
        return redirect('ouvrages:gestion_complete')


@csrf_exempt
def import_tarifs_excel(request):
    """Import des tarifs volumétriques avec tranches depuis Excel"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        updated_count = 0
        errors = []

        # Dictionnaire pour regrouper les tranches par tarif
        tarifs_data = {}

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    ouvrage_nom = str(row[1]).strip() if row[1] else None
                    date_debut_str = str(row[2]).strip() if row[2] else None
                    date_fin_str = str(row[3]).strip() if row[3] else None
                    prix_abonnement = row[4] if row[4] is not None else 0
                    actif_str = str(row[5]).strip().lower() if row[5] else 'oui'
                    tranche_superieur = row[6] if row[6] is not None else None
                    tarif_tranche = row[7] if row[7] is not None else None

                    # Validation des champs obligatoires
                    if not ouvrage_nom or not date_debut_str:
                        errors.append(f"Ligne {row_num}: Ouvrage et Date Début sont obligatoires")
                        continue

                    # Récupérer l'ouvrage
                    try:
                        ouvrage = _ouvrages_subdomain_queryset().get(nom_ouvrage=ouvrage_nom)
                    except OrgOuvrage.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Ouvrage '{ouvrage_nom}' introuvable")
                        continue

                    # Parser les dates
                    try:
                        date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
                    except ValueError:
                        errors.append(f"Ligne {row_num}: Format de date début invalide (attendu: AAAA-MM-JJ)")
                        continue

                    date_fin = None
                    if date_fin_str and date_fin_str != 'None':
                        try:
                            date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
                        except ValueError:
                            errors.append(f"Ligne {row_num}: Format de date fin invalide (attendu: AAAA-MM-JJ)")
                            continue

                    actif = actif_str in ['oui', 'yes', 'true', '1']

                    # Créer ou récupérer le tarif volumétrique
                    if tarif_id and tarif_id != 'None':
                        # Mise à jour d'un tarif existant
                        try:
                            tarif = TarifVolumetrique.objects.get(id=tarif_id)
                            tarif.ouvrage = ouvrage
                            tarif.datedebuttarif = date_debut
                            tarif.datefintarif = date_fin
                            tarif.prixabonnement = prix_abonnement
                            tarif.actif = actif
                            tarif.save()

                            # Utiliser l'ID du tarif comme clé
                            tarif_key = str(tarif.id)
                            if tarif_key not in tarifs_data:
                                tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': True}

                        except TarifVolumetrique.DoesNotExist:
                            errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                            continue
                    else:
                        # Créer un nouveau tarif (générer une clé unique basée sur ouvrage + date)
                        tarif_key = f"{ouvrage.id}_{date_debut}"

                        if tarif_key not in tarifs_data:
                            tarif = TarifVolumetrique.objects.create(
                                ouvrage=ouvrage,
                                datedebuttarif=date_debut,
                                datefintarif=date_fin,
                                prixabonnement=prix_abonnement,
                                actif=actif
                            )
                            tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': False}
                        else:
                            tarif = tarifs_data[tarif_key]['tarif']

                    # Ajouter la tranche si elle existe (utiliser la même clé)
                    if tranche_superieur is not None and tarif_tranche is not None:
                        if tarif_key in tarifs_data:
                            tarifs_data[tarif_key]['tranches'].append({
                                'tranchesuperieur': int(tranche_superieur),
                                'tarif': int(tarif_tranche)
                            })

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

            # Créer les tranches pour chaque tarif
            tranches_count = 0
            for tarif_key, data in tarifs_data.items():
                tarif = data['tarif']

                # Supprimer les anciennes tranches si c'est une mise à jour
                if data['updated']:
                    TarifVolumetrique2.objects.filter(tarifvolumetrique=tarif).delete()
                    updated_count += 1
                else:
                    imported_count += 1

                # Créer les nouvelles tranches
                for tranche_data in data['tranches']:
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=tranche_data['tranchesuperieur'],
                        tarif=tranche_data['tarif']
                    )
                    tranches_count += 1

        response_data = {
            'success': True,
            'imported': imported_count,
            'updated': updated_count,
            'tranches_created': tranches_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


@csrf_exempt
def import_tranches_only(request):
    """Import UNIQUEMENT des tranches (3 colonnes: tarif_id, tranche_superieur, tarif)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        errors = []

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    tranche_superieur = row[1] if row[1] is not None else None
                    tarif_prix = row[2] if row[2] is not None else None

                    # Validation des champs obligatoires
                    if not tarif_id or tranche_superieur is None or tarif_prix is None:
                        errors.append(f"Ligne {row_num}: Tous les champs sont obligatoires (tarif_id, tranche_superieur, tarif)")
                        continue

                    # Récupérer le tarif volumétrique
                    try:
                        tarif = TarifVolumetrique.objects.get(id=tarif_id)
                    except TarifVolumetrique.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                        continue

                    # Créer la tranche
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=int(tranche_superieur),
                        tarif=int(tarif_prix)
                    )
                    imported_count += 1

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

        response_data = {
            'success': True,
            'imported': imported_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


def tarifs_import_export_page(request):
    """Page pour l'import/export des tarifs volumétriques"""
    tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('-datedebuttarif')[:50]

    context = {
        'title': 'Import/Export Tarifs Volumétriques',
        'tarifs': tarifs,
    }
    return render(request, 'ouvrages/tarifs_import_export.html', context)


def api_equipements(request):
    """API pour récupérer les équipements par ouvrage"""
    try:
        ouvrage_id = request.GET.get('ouvrage_id')
        if ouvrage_id:
            equipements = EquipementConstitutif.objects.filter(ouvrage_id=ouvrage_id).order_by('nom')
        else:
            equipements = EquipementConstitutif.objects.all().order_by('ouvrage__nom', 'nom')

        data = []
        for equipement in equipements:
            data.append({
                'id': str(equipement.id),
                'nom': equipement.nom,
                'description': equipement.description,
                'type_equipement': equipement.type_equipement,
                'type_equipement_display': equipement.get_type_equipement_display(),
                'code_equipement': equipement.code_equipement,
                'status': getattr(equipement, 'status', 'operationnel'),
                'ouvrage_id': str(equipement.ouvrage_id),
                'ouvrage_nom': equipement.ouvrage.nom,
            })
        return JsonResponse(data, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def ouvrages_gestion_complete(request):
    """Vue pour la gestion complète avec formulaires en cascade"""
    ouvrages = _ouvrages_subdomain_queryset().select_related('type_ouvrage').order_by('nom_ouvrage')

    context = {
        'title': 'Gestion Complète des Ouvrages',
        'ouvrages': ouvrages[:20],
    }
    return render(request, 'ouvrages/gestion_complete.html', context)


# ========== IMPORT/EXPORT EXCEL POUR TARIFS VOLUMÉTRIQUES ==========

def export_tarifs_excel(request):
    """Export des tarifs volumétriques avec tranches vers Excel"""
    try:
        # Créer un nouveau workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Tarifs Volumétriques"

        # Styles
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True, size=12)
        border_style = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        # En-têtes
        headers = [
            'ID Tarif', 'Ouvrage', 'Date Début', 'Date Fin',
            'Prix Abonnement', 'Actif', 'Tranche Supérieure (m³)', 'Tarif (Ar/m³)'
        ]

        for col, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col)
            cell.value = header
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = border_style

        # Récupérer tous les tarifs avec leurs tranches
        tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('ouvrage__nom', '-datedebuttarif')

        row = 2
        for tarif in tarifs:
            tranches = tarif.tranches.all().order_by('tranchesuperieur')

            if tranches.exists():
                # Si le tarif a des tranches, une ligne par tranche
                for tranche in tranches:
                    ws.cell(row=row, column=1).value = str(tarif.id)
                    ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                    ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                    ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                    ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                    ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                    ws.cell(row=row, column=7).value = int(tranche.tranchesuperieur) if tranche.tranchesuperieur else 0
                    ws.cell(row=row, column=8).value = int(tranche.tarif) if tranche.tarif else 0

                    # Appliquer les bordures
                    for col in range(1, 9):
                        ws.cell(row=row, column=col).border = border_style

                    row += 1
            else:
                # Si le tarif n'a pas de tranches, une ligne vide pour les tranches
                ws.cell(row=row, column=1).value = str(tarif.id)
                ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                ws.cell(row=row, column=7).value = ''
                ws.cell(row=row, column=8).value = ''

                # Appliquer les bordures
                for col in range(1, 9):
                    ws.cell(row=row, column=col).border = border_style

                row += 1

        # Ajuster la largeur des colonnes
        column_widths = [35, 30, 15, 15, 18, 10, 22, 18]
        for col, width in enumerate(column_widths, start=1):
            ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = width

        # Créer la réponse HTTP avec le fichier Excel
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename=tarifs_volumetriques_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'

        wb.save(response)
        return response

    except Exception as e:
        messages.error(request, f'Erreur lors de l\'export Excel : {str(e)}')
        return redirect('ouvrages:gestion_complete')


@csrf_exempt
def import_tarifs_excel(request):
    """Import des tarifs volumétriques avec tranches depuis Excel"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        updated_count = 0
        errors = []

        # Dictionnaire pour regrouper les tranches par tarif
        tarifs_data = {}

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    ouvrage_nom = str(row[1]).strip() if row[1] else None
                    date_debut_str = str(row[2]).strip() if row[2] else None
                    date_fin_str = str(row[3]).strip() if row[3] else None
                    prix_abonnement = row[4] if row[4] is not None else 0
                    actif_str = str(row[5]).strip().lower() if row[5] else 'oui'
                    tranche_superieur = row[6] if row[6] is not None else None
                    tarif_tranche = row[7] if row[7] is not None else None

                    # Validation des champs obligatoires
                    if not ouvrage_nom or not date_debut_str:
                        errors.append(f"Ligne {row_num}: Ouvrage et Date Début sont obligatoires")
                        continue

                    # Récupérer l'ouvrage
                    try:
                        ouvrage = _ouvrages_subdomain_queryset().get(nom_ouvrage=ouvrage_nom)
                    except OrgOuvrage.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Ouvrage '{ouvrage_nom}' introuvable")
                        continue

                    # Parser les dates
                    try:
                        date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
                    except ValueError:
                        errors.append(f"Ligne {row_num}: Format de date début invalide (attendu: AAAA-MM-JJ)")
                        continue

                    date_fin = None
                    if date_fin_str and date_fin_str != 'None':
                        try:
                            date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
                        except ValueError:
                            errors.append(f"Ligne {row_num}: Format de date fin invalide (attendu: AAAA-MM-JJ)")
                            continue

                    actif = actif_str in ['oui', 'yes', 'true', '1']

                    # Créer ou récupérer le tarif volumétrique
                    if tarif_id and tarif_id != 'None':
                        # Mise à jour d'un tarif existant
                        try:
                            tarif = TarifVolumetrique.objects.get(id=tarif_id)
                            tarif.ouvrage = ouvrage
                            tarif.datedebuttarif = date_debut
                            tarif.datefintarif = date_fin
                            tarif.prixabonnement = prix_abonnement
                            tarif.actif = actif
                            tarif.save()

                            # Utiliser l'ID du tarif comme clé
                            tarif_key = str(tarif.id)
                            if tarif_key not in tarifs_data:
                                tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': True}

                        except TarifVolumetrique.DoesNotExist:
                            errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                            continue
                    else:
                        # Créer un nouveau tarif (générer une clé unique basée sur ouvrage + date)
                        tarif_key = f"{ouvrage.id}_{date_debut}"

                        if tarif_key not in tarifs_data:
                            tarif = TarifVolumetrique.objects.create(
                                ouvrage=ouvrage,
                                datedebuttarif=date_debut,
                                datefintarif=date_fin,
                                prixabonnement=prix_abonnement,
                                actif=actif
                            )
                            tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': False}
                        else:
                            tarif = tarifs_data[tarif_key]['tarif']

                    # Ajouter la tranche si elle existe (utiliser la même clé)
                    if tranche_superieur is not None and tarif_tranche is not None:
                        if tarif_key in tarifs_data:
                            tarifs_data[tarif_key]['tranches'].append({
                                'tranchesuperieur': int(tranche_superieur),
                                'tarif': int(tarif_tranche)
                            })

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

            # Créer les tranches pour chaque tarif
            tranches_count = 0
            for tarif_key, data in tarifs_data.items():
                tarif = data['tarif']

                # Supprimer les anciennes tranches si c'est une mise à jour
                if data['updated']:
                    TarifVolumetrique2.objects.filter(tarifvolumetrique=tarif).delete()
                    updated_count += 1
                else:
                    imported_count += 1

                # Créer les nouvelles tranches
                for tranche_data in data['tranches']:
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=tranche_data['tranchesuperieur'],
                        tarif=tranche_data['tarif']
                    )
                    tranches_count += 1

        response_data = {
            'success': True,
            'imported': imported_count,
            'updated': updated_count,
            'tranches_created': tranches_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


@csrf_exempt
def import_tranches_only(request):
    """Import UNIQUEMENT des tranches (3 colonnes: tarif_id, tranche_superieur, tarif)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        errors = []

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    tranche_superieur = row[1] if row[1] is not None else None
                    tarif_prix = row[2] if row[2] is not None else None

                    # Validation des champs obligatoires
                    if not tarif_id or tranche_superieur is None or tarif_prix is None:
                        errors.append(f"Ligne {row_num}: Tous les champs sont obligatoires (tarif_id, tranche_superieur, tarif)")
                        continue

                    # Récupérer le tarif volumétrique
                    try:
                        tarif = TarifVolumetrique.objects.get(id=tarif_id)
                    except TarifVolumetrique.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                        continue

                    # Créer la tranche
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=int(tranche_superieur),
                        tarif=int(tarif_prix)
                    )
                    imported_count += 1

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

        response_data = {
            'success': True,
            'imported': imported_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


def tarifs_import_export_page(request):
    """Page pour l'import/export des tarifs volumétriques"""
    tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('-datedebuttarif')[:50]

    context = {
        'title': 'Import/Export Tarifs Volumétriques',
        'tarifs': tarifs,
    }
    return render(request, 'ouvrages/tarifs_import_export.html', context)


def api_compteurs_tete(request):
    """API pour récupérer les compteurs de tête par ouvrage"""
    try:
        ouvrage_id = request.GET.get('ouvrage_id')
        if ouvrage_id:
            compteurs = CompteurTete.objects.filter(ouvrage_id=ouvrage_id).order_by('numerocompteur')
        else:
            compteurs = CompteurTete.objects.all().order_by('ouvrage__nom', 'numerocompteur')

        data = []
        for compteur in compteurs:
            data.append({
                'id': str(compteur.id),
                'numerocompteur': compteur.numerocompteur,
                'marque': compteur.marque,
                'modele': compteur.modele,
                'date_installation': compteur.date_installation.isoformat() if compteur.date_installation else None,
                'index_initial': float(compteur.index_initial) if compteur.index_initial else 0,
                'statut': compteur.statut,
                'statut_display': compteur.get_statut_display(),
                'ouvrage_id': str(compteur.ouvrage_id) if compteur.ouvrage else None,
                'ouvrage_nom': compteur.ouvrage.nom if compteur.ouvrage else None,
            })
        return JsonResponse(data, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def ouvrages_gestion_complete(request):
    """Vue pour la gestion complète avec formulaires en cascade"""
    ouvrages = _ouvrages_subdomain_queryset().select_related('type_ouvrage').order_by('nom_ouvrage')

    context = {
        'title': 'Gestion Complète des Ouvrages',
        'ouvrages': ouvrages[:20],
    }
    return render(request, 'ouvrages/gestion_complete.html', context)


# ========== IMPORT/EXPORT EXCEL POUR TARIFS VOLUMÉTRIQUES ==========

def export_tarifs_excel(request):
    """Export des tarifs volumétriques avec tranches vers Excel"""
    try:
        # Créer un nouveau workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Tarifs Volumétriques"

        # Styles
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True, size=12)
        border_style = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        # En-têtes
        headers = [
            'ID Tarif', 'Ouvrage', 'Date Début', 'Date Fin',
            'Prix Abonnement', 'Actif', 'Tranche Supérieure (m³)', 'Tarif (Ar/m³)'
        ]

        for col, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col)
            cell.value = header
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = border_style

        # Récupérer tous les tarifs avec leurs tranches
        tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('ouvrage__nom', '-datedebuttarif')

        row = 2
        for tarif in tarifs:
            tranches = tarif.tranches.all().order_by('tranchesuperieur')

            if tranches.exists():
                # Si le tarif a des tranches, une ligne par tranche
                for tranche in tranches:
                    ws.cell(row=row, column=1).value = str(tarif.id)
                    ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                    ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                    ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                    ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                    ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                    ws.cell(row=row, column=7).value = int(tranche.tranchesuperieur) if tranche.tranchesuperieur else 0
                    ws.cell(row=row, column=8).value = int(tranche.tarif) if tranche.tarif else 0

                    # Appliquer les bordures
                    for col in range(1, 9):
                        ws.cell(row=row, column=col).border = border_style

                    row += 1
            else:
                # Si le tarif n'a pas de tranches, une ligne vide pour les tranches
                ws.cell(row=row, column=1).value = str(tarif.id)
                ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                ws.cell(row=row, column=7).value = ''
                ws.cell(row=row, column=8).value = ''

                # Appliquer les bordures
                for col in range(1, 9):
                    ws.cell(row=row, column=col).border = border_style

                row += 1

        # Ajuster la largeur des colonnes
        column_widths = [35, 30, 15, 15, 18, 10, 22, 18]
        for col, width in enumerate(column_widths, start=1):
            ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = width

        # Créer la réponse HTTP avec le fichier Excel
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename=tarifs_volumetriques_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'

        wb.save(response)
        return response

    except Exception as e:
        messages.error(request, f'Erreur lors de l\'export Excel : {str(e)}')
        return redirect('ouvrages:gestion_complete')


@csrf_exempt
def import_tarifs_excel(request):
    """Import des tarifs volumétriques avec tranches depuis Excel"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        updated_count = 0
        errors = []

        # Dictionnaire pour regrouper les tranches par tarif
        tarifs_data = {}

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    ouvrage_nom = str(row[1]).strip() if row[1] else None
                    date_debut_str = str(row[2]).strip() if row[2] else None
                    date_fin_str = str(row[3]).strip() if row[3] else None
                    prix_abonnement = row[4] if row[4] is not None else 0
                    actif_str = str(row[5]).strip().lower() if row[5] else 'oui'
                    tranche_superieur = row[6] if row[6] is not None else None
                    tarif_tranche = row[7] if row[7] is not None else None

                    # Validation des champs obligatoires
                    if not ouvrage_nom or not date_debut_str:
                        errors.append(f"Ligne {row_num}: Ouvrage et Date Début sont obligatoires")
                        continue

                    # Récupérer l'ouvrage
                    try:
                        ouvrage = _ouvrages_subdomain_queryset().get(nom_ouvrage=ouvrage_nom)
                    except OrgOuvrage.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Ouvrage '{ouvrage_nom}' introuvable")
                        continue

                    # Parser les dates
                    try:
                        date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
                    except ValueError:
                        errors.append(f"Ligne {row_num}: Format de date début invalide (attendu: AAAA-MM-JJ)")
                        continue

                    date_fin = None
                    if date_fin_str and date_fin_str != 'None':
                        try:
                            date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
                        except ValueError:
                            errors.append(f"Ligne {row_num}: Format de date fin invalide (attendu: AAAA-MM-JJ)")
                            continue

                    actif = actif_str in ['oui', 'yes', 'true', '1']

                    # Créer ou récupérer le tarif volumétrique
                    if tarif_id and tarif_id != 'None':
                        # Mise à jour d'un tarif existant
                        try:
                            tarif = TarifVolumetrique.objects.get(id=tarif_id)
                            tarif.ouvrage = ouvrage
                            tarif.datedebuttarif = date_debut
                            tarif.datefintarif = date_fin
                            tarif.prixabonnement = prix_abonnement
                            tarif.actif = actif
                            tarif.save()

                            # Utiliser l'ID du tarif comme clé
                            tarif_key = str(tarif.id)
                            if tarif_key not in tarifs_data:
                                tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': True}

                        except TarifVolumetrique.DoesNotExist:
                            errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                            continue
                    else:
                        # Créer un nouveau tarif (générer une clé unique basée sur ouvrage + date)
                        tarif_key = f"{ouvrage.id}_{date_debut}"

                        if tarif_key not in tarifs_data:
                            tarif = TarifVolumetrique.objects.create(
                                ouvrage=ouvrage,
                                datedebuttarif=date_debut,
                                datefintarif=date_fin,
                                prixabonnement=prix_abonnement,
                                actif=actif
                            )
                            tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': False}
                        else:
                            tarif = tarifs_data[tarif_key]['tarif']

                    # Ajouter la tranche si elle existe (utiliser la même clé)
                    if tranche_superieur is not None and tarif_tranche is not None:
                        if tarif_key in tarifs_data:
                            tarifs_data[tarif_key]['tranches'].append({
                                'tranchesuperieur': int(tranche_superieur),
                                'tarif': int(tarif_tranche)
                            })

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

            # Créer les tranches pour chaque tarif
            tranches_count = 0
            for tarif_key, data in tarifs_data.items():
                tarif = data['tarif']

                # Supprimer les anciennes tranches si c'est une mise à jour
                if data['updated']:
                    TarifVolumetrique2.objects.filter(tarifvolumetrique=tarif).delete()
                    updated_count += 1
                else:
                    imported_count += 1

                # Créer les nouvelles tranches
                for tranche_data in data['tranches']:
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=tranche_data['tranchesuperieur'],
                        tarif=tranche_data['tarif']
                    )
                    tranches_count += 1

        response_data = {
            'success': True,
            'imported': imported_count,
            'updated': updated_count,
            'tranches_created': tranches_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


@csrf_exempt
def import_tranches_only(request):
    """Import UNIQUEMENT des tranches (3 colonnes: tarif_id, tranche_superieur, tarif)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        errors = []

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    tranche_superieur = row[1] if row[1] is not None else None
                    tarif_prix = row[2] if row[2] is not None else None

                    # Validation des champs obligatoires
                    if not tarif_id or tranche_superieur is None or tarif_prix is None:
                        errors.append(f"Ligne {row_num}: Tous les champs sont obligatoires (tarif_id, tranche_superieur, tarif)")
                        continue

                    # Récupérer le tarif volumétrique
                    try:
                        tarif = TarifVolumetrique.objects.get(id=tarif_id)
                    except TarifVolumetrique.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                        continue

                    # Créer la tranche
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=int(tranche_superieur),
                        tarif=int(tarif_prix)
                    )
                    imported_count += 1

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

        response_data = {
            'success': True,
            'imported': imported_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


def tarifs_import_export_page(request):
    """Page pour l'import/export des tarifs volumétriques"""
    tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('-datedebuttarif')[:50]

    context = {
        'title': 'Import/Export Tarifs Volumétriques',
        'tarifs': tarifs,
    }
    return render(request, 'ouvrages/tarifs_import_export.html', context)


def api_modalites_gestion(request):
    """API pour récupérer les modalités de gestion par ouvrage"""
    try:
        ouvrage_id = request.GET.get('ouvrage_id')
        if ouvrage_id:
            modalites = ModaliteGestion.objects.filter(ouvrage_id=ouvrage_id).order_by('-date_debut')
        else:
            modalites = ModaliteGestion.objects.all().order_by('ouvrage__nom', '-date_debut')

        data = []
        for modalite in modalites:
            data.append({
                'id': str(modalite.id),
                'type_gestion': modalite.type_gestion,
                'type_gestion_display': modalite.get_type_gestion_display(),
                'gestionnaire': modalite.gestionnaire,
                'contact_gestionnaire': modalite.contact_gestionnaire,
                'date_debut': modalite.date_debut.isoformat(),
                'date_fin': modalite.date_fin.isoformat() if modalite.date_fin else None,
                'statut': modalite.statut,
                'statut_display': modalite.get_statut_display(),
                'tarif_mensuel': float(modalite.tarif_mensuel) if modalite.tarif_mensuel else None,
                'pourcentage_recettes': float(modalite.pourcentage_recettes) if modalite.pourcentage_recettes else None,
                'is_active_now': modalite.is_active_now,
                'ouvrage_id': str(modalite.ouvrage_id),
                'ouvrage_nom': modalite.ouvrage.nom,
            })
        return JsonResponse(data, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def ouvrages_gestion_complete(request):
    """Vue pour la gestion complète avec formulaires en cascade"""
    ouvrages = _ouvrages_subdomain_queryset().select_related('type_ouvrage').order_by('nom_ouvrage')

    context = {
        'title': 'Gestion Complète des Ouvrages',
        'ouvrages': ouvrages[:20],
    }
    return render(request, 'ouvrages/gestion_complete.html', context)


# ========== IMPORT/EXPORT EXCEL POUR TARIFS VOLUMÉTRIQUES ==========

def export_tarifs_excel(request):
    """Export des tarifs volumétriques avec tranches vers Excel"""
    try:
        # Créer un nouveau workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Tarifs Volumétriques"

        # Styles
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True, size=12)
        border_style = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        # En-têtes
        headers = [
            'ID Tarif', 'Ouvrage', 'Date Début', 'Date Fin',
            'Prix Abonnement', 'Actif', 'Tranche Supérieure (m³)', 'Tarif (Ar/m³)'
        ]

        for col, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col)
            cell.value = header
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = border_style

        # Récupérer tous les tarifs avec leurs tranches
        tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('ouvrage__nom', '-datedebuttarif')

        row = 2
        for tarif in tarifs:
            tranches = tarif.tranches.all().order_by('tranchesuperieur')

            if tranches.exists():
                # Si le tarif a des tranches, une ligne par tranche
                for tranche in tranches:
                    ws.cell(row=row, column=1).value = str(tarif.id)
                    ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                    ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                    ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                    ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                    ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                    ws.cell(row=row, column=7).value = int(tranche.tranchesuperieur) if tranche.tranchesuperieur else 0
                    ws.cell(row=row, column=8).value = int(tranche.tarif) if tranche.tarif else 0

                    # Appliquer les bordures
                    for col in range(1, 9):
                        ws.cell(row=row, column=col).border = border_style

                    row += 1
            else:
                # Si le tarif n'a pas de tranches, une ligne vide pour les tranches
                ws.cell(row=row, column=1).value = str(tarif.id)
                ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                ws.cell(row=row, column=7).value = ''
                ws.cell(row=row, column=8).value = ''

                # Appliquer les bordures
                for col in range(1, 9):
                    ws.cell(row=row, column=col).border = border_style

                row += 1

        # Ajuster la largeur des colonnes
        column_widths = [35, 30, 15, 15, 18, 10, 22, 18]
        for col, width in enumerate(column_widths, start=1):
            ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = width

        # Créer la réponse HTTP avec le fichier Excel
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename=tarifs_volumetriques_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'

        wb.save(response)
        return response

    except Exception as e:
        messages.error(request, f'Erreur lors de l\'export Excel : {str(e)}')
        return redirect('ouvrages:gestion_complete')


@csrf_exempt
def import_tarifs_excel(request):
    """Import des tarifs volumétriques avec tranches depuis Excel"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        updated_count = 0
        errors = []

        # Dictionnaire pour regrouper les tranches par tarif
        tarifs_data = {}

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    ouvrage_nom = str(row[1]).strip() if row[1] else None
                    date_debut_str = str(row[2]).strip() if row[2] else None
                    date_fin_str = str(row[3]).strip() if row[3] else None
                    prix_abonnement = row[4] if row[4] is not None else 0
                    actif_str = str(row[5]).strip().lower() if row[5] else 'oui'
                    tranche_superieur = row[6] if row[6] is not None else None
                    tarif_tranche = row[7] if row[7] is not None else None

                    # Validation des champs obligatoires
                    if not ouvrage_nom or not date_debut_str:
                        errors.append(f"Ligne {row_num}: Ouvrage et Date Début sont obligatoires")
                        continue

                    # Récupérer l'ouvrage
                    try:
                        ouvrage = _ouvrages_subdomain_queryset().get(nom_ouvrage=ouvrage_nom)
                    except OrgOuvrage.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Ouvrage '{ouvrage_nom}' introuvable")
                        continue

                    # Parser les dates
                    try:
                        date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
                    except ValueError:
                        errors.append(f"Ligne {row_num}: Format de date début invalide (attendu: AAAA-MM-JJ)")
                        continue

                    date_fin = None
                    if date_fin_str and date_fin_str != 'None':
                        try:
                            date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
                        except ValueError:
                            errors.append(f"Ligne {row_num}: Format de date fin invalide (attendu: AAAA-MM-JJ)")
                            continue

                    actif = actif_str in ['oui', 'yes', 'true', '1']

                    # Créer ou récupérer le tarif volumétrique
                    if tarif_id and tarif_id != 'None':
                        # Mise à jour d'un tarif existant
                        try:
                            tarif = TarifVolumetrique.objects.get(id=tarif_id)
                            tarif.ouvrage = ouvrage
                            tarif.datedebuttarif = date_debut
                            tarif.datefintarif = date_fin
                            tarif.prixabonnement = prix_abonnement
                            tarif.actif = actif
                            tarif.save()

                            # Utiliser l'ID du tarif comme clé
                            tarif_key = str(tarif.id)
                            if tarif_key not in tarifs_data:
                                tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': True}

                        except TarifVolumetrique.DoesNotExist:
                            errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                            continue
                    else:
                        # Créer un nouveau tarif (générer une clé unique basée sur ouvrage + date)
                        tarif_key = f"{ouvrage.id}_{date_debut}"

                        if tarif_key not in tarifs_data:
                            tarif = TarifVolumetrique.objects.create(
                                ouvrage=ouvrage,
                                datedebuttarif=date_debut,
                                datefintarif=date_fin,
                                prixabonnement=prix_abonnement,
                                actif=actif
                            )
                            tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': False}
                        else:
                            tarif = tarifs_data[tarif_key]['tarif']

                    # Ajouter la tranche si elle existe (utiliser la même clé)
                    if tranche_superieur is not None and tarif_tranche is not None:
                        if tarif_key in tarifs_data:
                            tarifs_data[tarif_key]['tranches'].append({
                                'tranchesuperieur': int(tranche_superieur),
                                'tarif': int(tarif_tranche)
                            })

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

            # Créer les tranches pour chaque tarif
            tranches_count = 0
            for tarif_key, data in tarifs_data.items():
                tarif = data['tarif']

                # Supprimer les anciennes tranches si c'est une mise à jour
                if data['updated']:
                    TarifVolumetrique2.objects.filter(tarifvolumetrique=tarif).delete()
                    updated_count += 1
                else:
                    imported_count += 1

                # Créer les nouvelles tranches
                for tranche_data in data['tranches']:
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=tranche_data['tranchesuperieur'],
                        tarif=tranche_data['tarif']
                    )
                    tranches_count += 1

        response_data = {
            'success': True,
            'imported': imported_count,
            'updated': updated_count,
            'tranches_created': tranches_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


@csrf_exempt
def import_tranches_only(request):
    """Import UNIQUEMENT des tranches (3 colonnes: tarif_id, tranche_superieur, tarif)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        errors = []

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    tranche_superieur = row[1] if row[1] is not None else None
                    tarif_prix = row[2] if row[2] is not None else None

                    # Validation des champs obligatoires
                    if not tarif_id or tranche_superieur is None or tarif_prix is None:
                        errors.append(f"Ligne {row_num}: Tous les champs sont obligatoires (tarif_id, tranche_superieur, tarif)")
                        continue

                    # Récupérer le tarif volumétrique
                    try:
                        tarif = TarifVolumetrique.objects.get(id=tarif_id)
                    except TarifVolumetrique.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                        continue

                    # Créer la tranche
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=int(tranche_superieur),
                        tarif=int(tarif_prix)
                    )
                    imported_count += 1

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

        response_data = {
            'success': True,
            'imported': imported_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


def tarifs_import_export_page(request):
    """Page pour l'import/export des tarifs volumétriques"""
    tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('-datedebuttarif')[:50]

    context = {
        'title': 'Import/Export Tarifs Volumétriques',
        'tarifs': tarifs,
    }
    return render(request, 'ouvrages/tarifs_import_export.html', context)


def api_tarifs_volumetriques(request):
    """API pour récupérer les tarifs volumétriques avec leurs tranches par ouvrage"""
    try:
        ouvrage_id = request.GET.get('ouvrage_id')
        if ouvrage_id:
            tarifs = TarifVolumetrique.objects.filter(ouvrage_id=ouvrage_id).prefetch_related('tranches').order_by('-datedebuttarif')
        else:
            tarifs = TarifVolumetrique.objects.all().prefetch_related('tranches').order_by('ouvrage__nom', '-datedebuttarif')

        data = []
        for tarif in tarifs:
            # Récupérer les tranches pour ce tarif
            tranches = []
            for tranche in tarif.tranches.all().order_by('tranchesuperieur'):
                tranches.append({
                    'id': str(tranche.id),
                    'tranchesuperieur': tranche.tranchesuperieur,
                    'tarif': tranche.tarif
                })

            data.append({
                'id': str(tarif.id),
                'datedebuttarif': tarif.datedebuttarif.isoformat(),
                'datefintarif': tarif.datefintarif.isoformat() if tarif.datefintarif else None,
                'prixabonnement': tarif.prixabonnement,
                'actif': tarif.actif,
                'is_active_now': tarif.is_active_now,
                'ouvrage_id': str(tarif.ouvrage_id),
                'ouvrage_nom': tarif.ouvrage.nom,
                'tranches': tranches  # Tranches de tarifs volumétriques
            })
        return JsonResponse(data, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def ouvrages_gestion_complete(request):
    """Vue pour la gestion complète avec formulaires en cascade"""
    ouvrages = _ouvrages_subdomain_queryset().select_related('type_ouvrage').order_by('nom_ouvrage')

    context = {
        'title': 'Gestion Complète des Ouvrages',
        'ouvrages': ouvrages[:20],
    }
    return render(request, 'ouvrages/gestion_complete.html', context)


# ========== IMPORT/EXPORT EXCEL POUR TARIFS VOLUMÉTRIQUES ==========

def export_tarifs_excel(request):
    """Export des tarifs volumétriques avec tranches vers Excel"""
    try:
        # Créer un nouveau workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Tarifs Volumétriques"

        # Styles
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True, size=12)
        border_style = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        # En-têtes
        headers = [
            'ID Tarif', 'Ouvrage', 'Date Début', 'Date Fin',
            'Prix Abonnement', 'Actif', 'Tranche Supérieure (m³)', 'Tarif (Ar/m³)'
        ]

        for col, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col)
            cell.value = header
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = border_style

        # Récupérer tous les tarifs avec leurs tranches
        tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('ouvrage__nom', '-datedebuttarif')

        row = 2
        for tarif in tarifs:
            tranches = tarif.tranches.all().order_by('tranchesuperieur')

            if tranches.exists():
                # Si le tarif a des tranches, une ligne par tranche
                for tranche in tranches:
                    ws.cell(row=row, column=1).value = str(tarif.id)
                    ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                    ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                    ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                    ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                    ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                    ws.cell(row=row, column=7).value = int(tranche.tranchesuperieur) if tranche.tranchesuperieur else 0
                    ws.cell(row=row, column=8).value = int(tranche.tarif) if tranche.tarif else 0

                    # Appliquer les bordures
                    for col in range(1, 9):
                        ws.cell(row=row, column=col).border = border_style

                    row += 1
            else:
                # Si le tarif n'a pas de tranches, une ligne vide pour les tranches
                ws.cell(row=row, column=1).value = str(tarif.id)
                ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                ws.cell(row=row, column=7).value = ''
                ws.cell(row=row, column=8).value = ''

                # Appliquer les bordures
                for col in range(1, 9):
                    ws.cell(row=row, column=col).border = border_style

                row += 1

        # Ajuster la largeur des colonnes
        column_widths = [35, 30, 15, 15, 18, 10, 22, 18]
        for col, width in enumerate(column_widths, start=1):
            ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = width

        # Créer la réponse HTTP avec le fichier Excel
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename=tarifs_volumetriques_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'

        wb.save(response)
        return response

    except Exception as e:
        messages.error(request, f'Erreur lors de l\'export Excel : {str(e)}')
        return redirect('ouvrages:gestion_complete')


@csrf_exempt
def import_tarifs_excel(request):
    """Import des tarifs volumétriques avec tranches depuis Excel"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        updated_count = 0
        errors = []

        # Dictionnaire pour regrouper les tranches par tarif
        tarifs_data = {}

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    ouvrage_nom = str(row[1]).strip() if row[1] else None
                    date_debut_str = str(row[2]).strip() if row[2] else None
                    date_fin_str = str(row[3]).strip() if row[3] else None
                    prix_abonnement = row[4] if row[4] is not None else 0
                    actif_str = str(row[5]).strip().lower() if row[5] else 'oui'
                    tranche_superieur = row[6] if row[6] is not None else None
                    tarif_tranche = row[7] if row[7] is not None else None

                    # Validation des champs obligatoires
                    if not ouvrage_nom or not date_debut_str:
                        errors.append(f"Ligne {row_num}: Ouvrage et Date Début sont obligatoires")
                        continue

                    # Récupérer l'ouvrage
                    try:
                        ouvrage = _ouvrages_subdomain_queryset().get(nom_ouvrage=ouvrage_nom)
                    except OrgOuvrage.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Ouvrage '{ouvrage_nom}' introuvable")
                        continue

                    # Parser les dates
                    try:
                        date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
                    except ValueError:
                        errors.append(f"Ligne {row_num}: Format de date début invalide (attendu: AAAA-MM-JJ)")
                        continue

                    date_fin = None
                    if date_fin_str and date_fin_str != 'None':
                        try:
                            date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
                        except ValueError:
                            errors.append(f"Ligne {row_num}: Format de date fin invalide (attendu: AAAA-MM-JJ)")
                            continue

                    actif = actif_str in ['oui', 'yes', 'true', '1']

                    # Créer ou récupérer le tarif volumétrique
                    if tarif_id and tarif_id != 'None':
                        # Mise à jour d'un tarif existant
                        try:
                            tarif = TarifVolumetrique.objects.get(id=tarif_id)
                            tarif.ouvrage = ouvrage
                            tarif.datedebuttarif = date_debut
                            tarif.datefintarif = date_fin
                            tarif.prixabonnement = prix_abonnement
                            tarif.actif = actif
                            tarif.save()

                            # Utiliser l'ID du tarif comme clé
                            tarif_key = str(tarif.id)
                            if tarif_key not in tarifs_data:
                                tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': True}

                        except TarifVolumetrique.DoesNotExist:
                            errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                            continue
                    else:
                        # Créer un nouveau tarif (générer une clé unique basée sur ouvrage + date)
                        tarif_key = f"{ouvrage.id}_{date_debut}"

                        if tarif_key not in tarifs_data:
                            tarif = TarifVolumetrique.objects.create(
                                ouvrage=ouvrage,
                                datedebuttarif=date_debut,
                                datefintarif=date_fin,
                                prixabonnement=prix_abonnement,
                                actif=actif
                            )
                            tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': False}
                        else:
                            tarif = tarifs_data[tarif_key]['tarif']

                    # Ajouter la tranche si elle existe (utiliser la même clé)
                    if tranche_superieur is not None and tarif_tranche is not None:
                        if tarif_key in tarifs_data:
                            tarifs_data[tarif_key]['tranches'].append({
                                'tranchesuperieur': int(tranche_superieur),
                                'tarif': int(tarif_tranche)
                            })

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

            # Créer les tranches pour chaque tarif
            tranches_count = 0
            for tarif_key, data in tarifs_data.items():
                tarif = data['tarif']

                # Supprimer les anciennes tranches si c'est une mise à jour
                if data['updated']:
                    TarifVolumetrique2.objects.filter(tarifvolumetrique=tarif).delete()
                    updated_count += 1
                else:
                    imported_count += 1

                # Créer les nouvelles tranches
                for tranche_data in data['tranches']:
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=tranche_data['tranchesuperieur'],
                        tarif=tranche_data['tarif']
                    )
                    tranches_count += 1

        response_data = {
            'success': True,
            'imported': imported_count,
            'updated': updated_count,
            'tranches_created': tranches_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


@csrf_exempt
def import_tranches_only(request):
    """Import UNIQUEMENT des tranches (3 colonnes: tarif_id, tranche_superieur, tarif)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        errors = []

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    tranche_superieur = row[1] if row[1] is not None else None
                    tarif_prix = row[2] if row[2] is not None else None

                    # Validation des champs obligatoires
                    if not tarif_id or tranche_superieur is None or tarif_prix is None:
                        errors.append(f"Ligne {row_num}: Tous les champs sont obligatoires (tarif_id, tranche_superieur, tarif)")
                        continue

                    # Récupérer le tarif volumétrique
                    try:
                        tarif = TarifVolumetrique.objects.get(id=tarif_id)
                    except TarifVolumetrique.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                        continue

                    # Créer la tranche
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=int(tranche_superieur),
                        tarif=int(tarif_prix)
                    )
                    imported_count += 1

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

        response_data = {
            'success': True,
            'imported': imported_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


def tarifs_import_export_page(request):
    """Page pour l'import/export des tarifs volumétriques"""
    tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('-datedebuttarif')[:50]

    context = {
        'title': 'Import/Export Tarifs Volumétriques',
        'tarifs': tarifs,
    }
    return render(request, 'ouvrages/tarifs_import_export.html', context)


def api_type_stats(request):
    """API pour récupérer les statistiques des types d'ouvrages"""
    try:
        from django.db.models import Count

        # Récupérer tous les types d'ouvrages avec leur nombre d'ouvrages
        types_ouvrages = OrgTypeOuvrage.objects.annotate(
            ouvrage_count=Count('ouvrages')
        ).values('id', 'nom_type_ouvrage', 'ouvrage_count')

        data = [
            {
                'type_id': str(type_ouvrage['id']),
                'type_name': type_ouvrage['nom_type_ouvrage'],
                'ouvrage_count': type_ouvrage['ouvrage_count']
            }
            for type_ouvrage in types_ouvrages
        ]

        return JsonResponse(data, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def api_fournisseurs(request):
    """API pour récupérer tous les fournisseurs"""
    try:
        type_fournisseur = request.GET.get('type_fournisseur')
        if type_fournisseur:
            fournisseurs = Fournisseur.objects.filter(type_fournisseur=type_fournisseur, actif=True).order_by('nom_fournisseur')
        else:
            fournisseurs = Fournisseur.objects.filter(actif=True).order_by('nom_fournisseur')

        data = []
        for fournisseur in fournisseurs:
            data.append({
                'id': str(fournisseur.id),
                'nom_fournisseur': fournisseur.nom_fournisseur,
                'telephone': fournisseur.telephone,
                'email': fournisseur.email,
                'adresse': fournisseur.adresse,
                'type_fournisseur': fournisseur.type_fournisseur,
                'type_fournisseur_display': fournisseur.get_type_fournisseur_display(),
                'numero_nif': fournisseur.numero_nif,
                'numero_stat': fournisseur.numero_stat,
                'actif': fournisseur.actif,
            })
        return JsonResponse(data, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def ouvrages_gestion_complete(request):
    """Vue pour la gestion complète avec formulaires en cascade"""
    ouvrages = _ouvrages_subdomain_queryset().select_related('type_ouvrage').order_by('nom_ouvrage')

    context = {
        'title': 'Gestion Complète des Ouvrages',
        'ouvrages': ouvrages[:20],
    }
    return render(request, 'ouvrages/gestion_complete.html', context)


# ========== IMPORT/EXPORT EXCEL POUR TARIFS VOLUMÉTRIQUES ==========

def export_tarifs_excel(request):
    """Export des tarifs volumétriques avec tranches vers Excel"""
    try:
        # Créer un nouveau workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Tarifs Volumétriques"

        # Styles
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True, size=12)
        border_style = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )

        # En-têtes
        headers = [
            'ID Tarif', 'Ouvrage', 'Date Début', 'Date Fin',
            'Prix Abonnement', 'Actif', 'Tranche Supérieure (m³)', 'Tarif (Ar/m³)'
        ]

        for col, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col)
            cell.value = header
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = border_style

        # Récupérer tous les tarifs avec leurs tranches
        tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('ouvrage__nom', '-datedebuttarif')

        row = 2
        for tarif in tarifs:
            tranches = tarif.tranches.all().order_by('tranchesuperieur')

            if tranches.exists():
                # Si le tarif a des tranches, une ligne par tranche
                for tranche in tranches:
                    ws.cell(row=row, column=1).value = str(tarif.id)
                    ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                    ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                    ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                    ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                    ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                    ws.cell(row=row, column=7).value = int(tranche.tranchesuperieur) if tranche.tranchesuperieur else 0
                    ws.cell(row=row, column=8).value = int(tranche.tarif) if tranche.tarif else 0

                    # Appliquer les bordures
                    for col in range(1, 9):
                        ws.cell(row=row, column=col).border = border_style

                    row += 1
            else:
                # Si le tarif n'a pas de tranches, une ligne vide pour les tranches
                ws.cell(row=row, column=1).value = str(tarif.id)
                ws.cell(row=row, column=2).value = tarif.ouvrage.nom if tarif.ouvrage else ''
                ws.cell(row=row, column=3).value = tarif.datedebuttarif.strftime('%Y-%m-%d') if tarif.datedebuttarif else ''
                ws.cell(row=row, column=4).value = tarif.datefintarif.strftime('%Y-%m-%d') if tarif.datefintarif else ''
                ws.cell(row=row, column=5).value = float(tarif.prixabonnement) if tarif.prixabonnement else 0
                ws.cell(row=row, column=6).value = 'Oui' if tarif.actif else 'Non'
                ws.cell(row=row, column=7).value = ''
                ws.cell(row=row, column=8).value = ''

                # Appliquer les bordures
                for col in range(1, 9):
                    ws.cell(row=row, column=col).border = border_style

                row += 1

        # Ajuster la largeur des colonnes
        column_widths = [35, 30, 15, 15, 18, 10, 22, 18]
        for col, width in enumerate(column_widths, start=1):
            ws.column_dimensions[ws.cell(row=1, column=col).column_letter].width = width

        # Créer la réponse HTTP avec le fichier Excel
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename=tarifs_volumetriques_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'

        wb.save(response)
        return response

    except Exception as e:
        messages.error(request, f'Erreur lors de l\'export Excel : {str(e)}')
        return redirect('ouvrages:gestion_complete')


@csrf_exempt
def import_tarifs_excel(request):
    """Import des tarifs volumétriques avec tranches depuis Excel"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        updated_count = 0
        errors = []

        # Dictionnaire pour regrouper les tranches par tarif
        tarifs_data = {}

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    ouvrage_nom = str(row[1]).strip() if row[1] else None
                    date_debut_str = str(row[2]).strip() if row[2] else None
                    date_fin_str = str(row[3]).strip() if row[3] else None
                    prix_abonnement = row[4] if row[4] is not None else 0
                    actif_str = str(row[5]).strip().lower() if row[5] else 'oui'
                    tranche_superieur = row[6] if row[6] is not None else None
                    tarif_tranche = row[7] if row[7] is not None else None

                    # Validation des champs obligatoires
                    if not ouvrage_nom or not date_debut_str:
                        errors.append(f"Ligne {row_num}: Ouvrage et Date Début sont obligatoires")
                        continue

                    # Récupérer l'ouvrage
                    try:
                        ouvrage = _ouvrages_subdomain_queryset().get(nom_ouvrage=ouvrage_nom)
                    except OrgOuvrage.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Ouvrage '{ouvrage_nom}' introuvable")
                        continue

                    # Parser les dates
                    try:
                        date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
                    except ValueError:
                        errors.append(f"Ligne {row_num}: Format de date début invalide (attendu: AAAA-MM-JJ)")
                        continue

                    date_fin = None
                    if date_fin_str and date_fin_str != 'None':
                        try:
                            date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
                        except ValueError:
                            errors.append(f"Ligne {row_num}: Format de date fin invalide (attendu: AAAA-MM-JJ)")
                            continue

                    actif = actif_str in ['oui', 'yes', 'true', '1']

                    # Créer ou récupérer le tarif volumétrique
                    if tarif_id and tarif_id != 'None':
                        # Mise à jour d'un tarif existant
                        try:
                            tarif = TarifVolumetrique.objects.get(id=tarif_id)
                            tarif.ouvrage = ouvrage
                            tarif.datedebuttarif = date_debut
                            tarif.datefintarif = date_fin
                            tarif.prixabonnement = prix_abonnement
                            tarif.actif = actif
                            tarif.save()

                            # Utiliser l'ID du tarif comme clé
                            tarif_key = str(tarif.id)
                            if tarif_key not in tarifs_data:
                                tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': True}

                        except TarifVolumetrique.DoesNotExist:
                            errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                            continue
                    else:
                        # Créer un nouveau tarif (générer une clé unique basée sur ouvrage + date)
                        tarif_key = f"{ouvrage.id}_{date_debut}"

                        if tarif_key not in tarifs_data:
                            tarif = TarifVolumetrique.objects.create(
                                ouvrage=ouvrage,
                                datedebuttarif=date_debut,
                                datefintarif=date_fin,
                                prixabonnement=prix_abonnement,
                                actif=actif
                            )
                            tarifs_data[tarif_key] = {'tarif': tarif, 'tranches': [], 'updated': False}
                        else:
                            tarif = tarifs_data[tarif_key]['tarif']

                    # Ajouter la tranche si elle existe (utiliser la même clé)
                    if tranche_superieur is not None and tarif_tranche is not None:
                        if tarif_key in tarifs_data:
                            tarifs_data[tarif_key]['tranches'].append({
                                'tranchesuperieur': int(tranche_superieur),
                                'tarif': int(tarif_tranche)
                            })

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

            # Créer les tranches pour chaque tarif
            tranches_count = 0
            for tarif_key, data in tarifs_data.items():
                tarif = data['tarif']

                # Supprimer les anciennes tranches si c'est une mise à jour
                if data['updated']:
                    TarifVolumetrique2.objects.filter(tarifvolumetrique=tarif).delete()
                    updated_count += 1
                else:
                    imported_count += 1

                # Créer les nouvelles tranches
                for tranche_data in data['tranches']:
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=tranche_data['tranchesuperieur'],
                        tarif=tranche_data['tarif']
                    )
                    tranches_count += 1

        response_data = {
            'success': True,
            'imported': imported_count,
            'updated': updated_count,
            'tranches_created': tranches_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


@csrf_exempt
def import_tranches_only(request):
    """Import UNIQUEMENT des tranches (3 colonnes: tarif_id, tranche_superieur, tarif)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)

    if 'file' not in request.FILES:
        return JsonResponse({'error': 'Aucun fichier fourni'}, status=400)

    excel_file = request.FILES['file']

    if not excel_file.name.endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Le fichier doit être au format Excel (.xlsx ou .xls)'}, status=400)

    try:
        # Charger le fichier Excel
        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        imported_count = 0
        errors = []

        with transaction.atomic():
            # Parcourir les lignes (en sautant l'en-tête)
            for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                try:
                    tarif_id = str(row[0]).strip() if row[0] else None
                    tranche_superieur = row[1] if row[1] is not None else None
                    tarif_prix = row[2] if row[2] is not None else None

                    # Validation des champs obligatoires
                    if not tarif_id or tranche_superieur is None or tarif_prix is None:
                        errors.append(f"Ligne {row_num}: Tous les champs sont obligatoires (tarif_id, tranche_superieur, tarif)")
                        continue

                    # Récupérer le tarif volumétrique
                    try:
                        tarif = TarifVolumetrique.objects.get(id=tarif_id)
                    except TarifVolumetrique.DoesNotExist:
                        errors.append(f"Ligne {row_num}: Tarif ID '{tarif_id}' introuvable")
                        continue

                    # Créer la tranche
                    TarifVolumetrique2.objects.create(
                        tarifvolumetrique=tarif,
                        tranchesuperieur=int(tranche_superieur),
                        tarif=int(tarif_prix)
                    )
                    imported_count += 1

                except Exception as e:
                    errors.append(f"Ligne {row_num}: Erreur - {str(e)}")
                    continue

        response_data = {
            'success': True,
            'imported': imported_count,
            'errors': errors
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'import : {str(e)}'}, status=500)


def tarifs_import_export_page(request):
    """Page pour l'import/export des tarifs volumétriques"""
    tarifs = TarifVolumetrique.objects.select_related('ouvrage').prefetch_related('tranches').all().order_by('-datedebuttarif')[:50]

    context = {
        'title': 'Import/Export Tarifs Volumétriques',
        'tarifs': tarifs,
    }
    return render(request, 'ouvrages/tarifs_import_export.html', context)




