from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse, NoReverseMatch
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.db.models import Q, Count
from django.db.models.functions import TruncDate
from django.db import transaction
from django.core.paginator import Paginator
from urllib.parse import urlencode
import re
import json
import unicodedata
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from datetime import datetime, date
from calendar import monthrange
from decimal import Decimal

# Import des vues Excel pour déplacements
from .views_deplacements_excel import (
    export_excel_deplacements,
    template_excel_deplacements,
    import_excel_deplacements
)

# Import des vues simplifiées pour le formulaire de planning
from . import views_simple

from .models import Planning, Indemnite, PlanningDetail, PlanningDetailDeplacement, TypeActivite, ActivitePoste, PlanningEmploye, PlanningPiece, Designation, Activite, BonLivraison, DebitSourceMesure
from apps.billing.models import PaiementForfaitaire, PointEau, Releve, ModaliteGestion
from .forms import PlanningForm, IndemniteForm
from .validation_permissions import (
    can_user_adjust_planning_validation,
    get_planning_validation_target_employe_ids,
    is_planning_validation_director,
)
from .serializers import (
    PlanningSerializer, PlanningCreateSerializer, PlanningDetailSerializer,
    TypeActiviteSerializer, ActivitePosteSerializer, EmployeSimpleSerializer,
    OuvrageSimpleSerializer, PlanningFilterSerializer
)
from apps.employees.models import Employe
from apps.organization.models import Ouvrage
from apps.organization.scoping import (
    apply_user_responsable_ouvrage_scope,
    filter_ouvrages_by_gestionnaire_period,
    get_active_subordinate_employe_ids,
    get_user_accessible_gestionnaire_ids,
)
from apps.billing.models import PointEau, Releve, ModaliteGestion
from apps.geography.models import Region, District, Commune
from apps.employees.models_evaluation import FichePoste
from apps.employees.permissions import employe_required, filter_queryset_by_permissions


PLANNING_PAPER_VERIFICATION_CHOICES = [
    ('', 'Non renseigne'),
    ('papier_conforme', 'Conforme au papier'),
    ('papier_ecart', 'Ecart avec le papier'),
    ('papier_absent', 'Feuille papier absente'),
    ('papier_a_verifier', 'A verifier'),
]

PLANNING_PAPER_VERIFICATION_LABELS = dict(PLANNING_PAPER_VERIFICATION_CHOICES)

PLANNING_STATUS_BADGE_CLASSES = {
    'en_cours': 'badge-info',
    'termine': 'badge-success',
    'annule': 'badge-error',
    'reporte': 'badge-warning',
}

PLANNING_MONTHLY_CLOTURE_CHOICES = [
    ('termine', 'Termine'),
    ('annule', 'Annule'),
    ('reporte', 'Reporte'),
]

PLANNING_MONTHLY_CLOTURE_ALLOWED = {value for value, _ in PLANNING_MONTHLY_CLOTURE_CHOICES}

PLANNING_PAPER_BADGE_CLASSES = {
    'papier_conforme': 'badge-success',
    'papier_ecart': 'badge-error',
    'papier_absent': 'badge-warning',
    'papier_a_verifier': 'badge-info',
}




def _parse_excel_date(value):
    from datetime import datetime
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    return None

def _attach_fiche_poste_display(plannings):
    plannings_list = list(plannings)
    if not plannings_list:
        return plannings_list

    for planning in plannings_list:
        if getattr(planning, 'fiche_poste', None):
            planning._fiche_poste_display = planning.fiche_poste.tache
        else:
            planning._fiche_poste_display = ''
        planning.fiche_poste_display_value = planning._fiche_poste_display

    return plannings_list


def _get_paiement_forfaitaire_point_label(point_eau):
    if not point_eau:
        return '-'

    return (
        getattr(point_eau, 'forfaitaire_display_label', None)
        or getattr(point_eau, 'nomabonne', None)
        or getattr(point_eau, 'nom', None)
        or getattr(point_eau, 'code_point_eau', None)
        or '-'
    )


def _calculate_volume_reference_debit(ouvrage, date_visite, peak_factor=Decimal('2')):
    shared_ouvrage_ids = _get_shared_source_ouvrage_ids(ouvrage)
    points = PointEau.objects.filter(ouvrage_id__in=shared_ouvrage_ids).only('id')
    point_ids = list(points.values_list('id', flat=True))
    peak_factor = Decimal(str(peak_factor))
    monthly_totals = {}
    monthly_points = {}
    monthly_releves = {}
    seen_point_months = set()

    releves = Releve.objects.filter(
        point_eau_id__in=point_ids,
        datereleve__lte=date_visite,
    ).only(
        'id',
        'point_eau_id',
        'datereleve',
        'consommation',
        'volume_facture',
        'created_at',
    ).order_by('-datereleve', '-created_at', '-id')

    for releve in releves:
        if not releve.datereleve:
            continue

        raw_volume = releve.volume_facture if releve.volume_facture is not None else releve.consommation
        if raw_volume is None:
            continue

        month_key = releve.datereleve.replace(day=1)
        point_month_key = (str(releve.point_eau_id), month_key)
        if point_month_key in seen_point_months:
            continue

        seen_point_months.add(point_month_key)
        volume_m3 = Decimal(str(raw_volume))
        monthly_totals[month_key] = monthly_totals.get(month_key, Decimal('0')) + volume_m3
        monthly_points[month_key] = monthly_points.get(month_key, 0) + 1
        monthly_releves[month_key] = monthly_releves.get(month_key, 0) + 1

    if monthly_totals:
        reference_month, total_volume_m3 = max(
            monthly_totals.items(),
            key=lambda item: (item[1], item[0]),
        )
    else:
        reference_month = None
        total_volume_m3 = Decimal('0')

    if total_volume_m3 <= 0:
        return {
            'total_volume_m3': Decimal('0'),
            'debit_moyen_l_s': Decimal('0'),
            'debit_pointe_l_s': Decimal('0'),
            'peak_factor': peak_factor,
            'points_count': len(point_ids),
            'reference_points_count': 0,
            'reference_releves_count': 0,
            'available_months_count': len(monthly_totals),
            'reference_month': reference_month,
            'reference_month_label': reference_month.strftime('%m/%Y') if reference_month else '',
        }

    seconds_per_month = Decimal('30') * Decimal('24') * Decimal('3600')
    debit_moyen_l_s = (total_volume_m3 * Decimal('1000')) / seconds_per_month
    debit_pointe_l_s = debit_moyen_l_s * peak_factor

    return {
        'total_volume_m3': total_volume_m3,
        'debit_moyen_l_s': debit_moyen_l_s,
        'debit_pointe_l_s': debit_pointe_l_s,
        'peak_factor': peak_factor,
        'points_count': len(point_ids),
        'reference_points_count': monthly_points.get(reference_month, 0),
        'reference_releves_count': monthly_releves.get(reference_month, 0),
        'available_months_count': len(monthly_totals),
        'reference_month': reference_month,
        'reference_month_label': reference_month.strftime('%m/%Y') if reference_month else '',
    }


def _get_shared_source_ouvrage_ids(ouvrage):
    ouvrage_reference = getattr(ouvrage, 'ouvrage_source_effectif', ouvrage) or ouvrage
    ouvrage_ids = {str(ouvrage.id), str(ouvrage_reference.id)}

    extension_ids = Ouvrage.objects.filter(
        ouvrage_source=ouvrage_reference
    ).values_list('id', flat=True)
    ouvrage_ids.update(str(item) for item in extension_ids)

    return list(ouvrage_ids)


def _get_ouvrage_debit_context(ouvrage, date_visite):
    ouvrage_reference = getattr(ouvrage, 'ouvrage_source_effectif', ouvrage) or ouvrage
    shared_ouvrage_ids = _get_shared_source_ouvrage_ids(ouvrage)
    points_eau = PointEau.objects.filter(ouvrage_id__in=shared_ouvrage_ids).select_related('type_point_eau')
    bornes = points_eau.filter(
        Q(type_point_eau__nom_type__iexact='BF') |
        Q(type_point_eau__nom_type__icontains='borne fontaine') |
        Q(type_point_eau__nom_type__icontains='borne') |
        Q(type_point_eau__nom_type__icontains='bf')
    ).count()

    modalites_actives = list(
        ModaliteGestion.objects.filter(
            ouvrage__in=[ouvrage] if ouvrage_reference == ouvrage else [ouvrage, ouvrage_reference],
            statut='actif',
        ).filter(
            Q(date_debut__isnull=True) | Q(date_debut__lte=date_visite),
        ).filter(
            Q(date_fin__isnull=True) | Q(date_fin__gte=date_visite),
        ).order_by('-date_debut', '-updated_at', '-created_at')
    )

    def _modalite_rank(modalite_obj):
        raw = str(getattr(modalite_obj, 'modalitepaiement', '') or '').strip().lower()
        if raw in {'au_volume', 'volume'} or 'volume' in raw:
            return 0
        if raw in {'mixte'}:
            return 1
        if raw in {'forfaitaire'} or 'forfait' in raw:
            return 2
        return 3

    modalite_active = modalites_actives[0] if modalites_actives else None
    for candidate in modalites_actives:
        if _modalite_rank(candidate) < _modalite_rank(modalite_active):
            modalite_active = candidate

    modalite_raw = str(getattr(modalite_active, 'modalitepaiement', '') or '').strip().lower()
    modalite_forfaitaire = modalite_raw in {'forfaitaire', 'mixte'} or 'forfait' in modalite_raw
    modalite_volume = modalite_raw in {'au_volume', 'volume'} or 'volume' in modalite_raw

    previous_measure = DebitSourceMesure.objects.filter(
        ouvrage=ouvrage_reference,
        date_visite__lt=date_visite,
    ).order_by('-date_visite', '-created_at').first()

    seuil_minimum = None
    interpretation = ''
    comparative_label = 'Historique des debits'
    volume_reference = None
    mode_paiement = 'volume'
    if modalite_forfaitaire:
        mode_paiement = 'forfaitaire'
        seuil_minimum = Decimal('0.05') * Decimal(str(bornes or 0))
        if bornes <= 0:
            interpretation = 'Aucune borne fontaine de type BF trouvee pour cet ouvrage.'
        elif seuil_minimum is not None:
            interpretation = 'Compare au seuil minimum forfaitaire.'
        comparative_label = f'Seuil minimum: {seuil_minimum} L/s' if seuil_minimum is not None else 'Seuil minimum non disponible'
    elif modalite_volume or modalite_active:
        volume_reference = _calculate_volume_reference_debit(ouvrage_reference, date_visite, peak_factor=Decimal('2'))
        interpretation = 'Reference volumetrique: maximum des sommes mensuelles des releves par point d eau.'
        if volume_reference['total_volume_m3'] > 0:
            seuil_minimum = volume_reference['debit_pointe_l_s']
            month_label = volume_reference.get('reference_month_label')
            comparative_label = (
                f"Mois ref. {month_label}: " if month_label else ''
            ) + (
                f"{volume_reference['total_volume_m3']:.3f} m3/mois -> "
                f"{volume_reference['debit_moyen_l_s']:.3f} L/s -> "
                f"{volume_reference['debit_pointe_l_s']:.3f} L/s"
            )
        else:
            comparative_label = 'Aucun releve de reference'
    else:
        volume_reference = None
        interpretation = 'Modalite de paiement non detectee.'

    return {
        'bornes': bornes,
        'is_forfaitaire': modalite_forfaitaire,
        'modalite_paiement_label': getattr(modalite_active, 'get_modalitepaiement_display', lambda: None)() if modalite_active else None,
        'modalite_paiement_value': getattr(modalite_active, 'modalitepaiement', None) if modalite_active else None,
        'previous_measure': previous_measure,
        'seuil_minimum': seuil_minimum,
        'interpretation': interpretation,
        'comparative_label': comparative_label,
        'volume_reference': volume_reference,
        'mode_paiement': mode_paiement,
        'ouvrage_reference': ouvrage_reference,
        'ouvrage_source': getattr(ouvrage, 'ouvrage_source', None),
    }


def _get_debit_status_label(mesure, debit_info, delta=None):
    if not mesure or not debit_info:
        return 'inconnu'

    if debit_info.get('is_forfaitaire'):
        seuil = debit_info.get('seuil_minimum')
        if seuil is not None and mesure.debit_l_s is not None:
            if Decimal(str(mesure.debit_l_s)) < Decimal(str(seuil)):
                return 'critique'
        if delta is None:
            return 'surveille'
        if delta < 0:
            return 'surveille'
        return 'normal'

    if mesure.debit_l_s is None:
        return 'inconnu'
    if delta is None:
        return 'surveille'
    if delta < 0:
        return 'baisse'
    if delta == 0:
        return 'stable'
    return 'hausse'


def _get_debit_status_priority(statut):
    return {
        'critique': 0,
        'baisse': 1,
        'surveille': 2,
        'stable': 3,
        'hausse': 4,
        'normal': 5,
        'inconnu': 6,
    }.get(statut, 9)


def _get_debit_source_type(date_obj):
    if not date_obj:
        return 'moyen'
    # Étiage: Octobre (10) à Décembre (12)
    if 10 <= date_obj.month <= 12:
        return 'etiage'
    return 'moyen'


def _get_debit_source_ouvrages_queryset(user, annee=None):
    accessible_gestionnaire_ids = get_user_accessible_gestionnaire_ids(user)
    ouvrages_qs = filter_ouvrages_by_gestionnaire_period(
        Ouvrage.objects.filter(
            # Les ouvrages "AEPG extension" partagent la meme source que leur
            # ouvrage de reference. On ne saisit donc pas de debit source
            # specifique pour eux et ils ne doivent pas apparaitre dans les filtres.
            Q(type_ouvrage__nom_type_ouvrage__iexact='AEPG')
        ),
        accessible_gestionnaire_ids,
        annee or timezone.localdate().year,
        allowed_statuts=('actif',),
    )
    scoped_ouvrage_ids = apply_user_responsable_ouvrage_scope(
        ouvrages_qs.values_list('id', flat=True).distinct(),
        user,
    )
    if scoped_ouvrage_ids == []:
        return Ouvrage.objects.none()
    return ouvrages_qs.filter(id__in=scoped_ouvrage_ids).order_by('nom_ouvrage')


def _normalize_debit_source_lookup(value):
    raw = str(value or '').strip()
    if not raw:
        return ''
    return ' '.join(
        unicodedata.normalize('NFKD', raw)
        .encode('ascii', errors='ignore')
        .decode('ascii')
        .lower()
        .split()
    )


def _get_debit_source_employes_queryset(user, reference_date=None):
    if not user or not getattr(user, 'is_authenticated', False):
        return Employe.objects.none()

    employe = getattr(user, 'employe', None)
    if not employe:
        return Employe.objects.none()

    reference_date = reference_date or timezone.localdate()
    employe_ids = get_active_subordinate_employe_ids(employe.id, reference_date)
    return Employe.objects.filter(id__in=employe_ids).select_related('base', 'poste').order_by('nom_employe')


def _build_debit_source_employe_lookup(employes):
    lookup = {}
    for employe in employes:
        keys = {
            str(employe.id),
            _normalize_debit_source_lookup(getattr(employe, 'surnom', '')),
            _normalize_debit_source_lookup(getattr(employe, 'nom_employe', '')),
            _normalize_debit_source_lookup(getattr(employe, 'nom_complet', '')),
            _normalize_debit_source_lookup(getattr(employe, 'nom_affichage', '')),
        }
        for key in keys:
            if key:
                lookup[key] = employe
    return lookup


def _resolve_debit_source_employe(value, employe_lookup):
    raw_value = str(value or '').strip()
    if not raw_value:
        return None
    return employe_lookup.get(raw_value) or employe_lookup.get(_normalize_debit_source_lookup(raw_value))


def _get_debit_source_geo_queryset_map(ouvrages_qs, region_id='', district_id='', commune_id=''):
    point_eau_qs = PointEau.objects.filter(
        ouvrage_id__in=ouvrages_qs.values_list('id', flat=True)
    ).exclude(
        parcelle__isnull=True
    ).exclude(
        parcelle__village__isnull=True
    ).exclude(
        parcelle__village__fokontany__isnull=True
    ).exclude(
        parcelle__village__fokontany__commune__isnull=True
    ).select_related('parcelle__village__fokontany__commune__district__region')

    geo_map = {}
    for point_eau in point_eau_qs:
        commune = point_eau.parcelle.village.fokontany.commune
        district = commune.district
        region = district.region
        bucket = geo_map.setdefault(
            str(point_eau.ouvrage_id),
            {'region_ids': set(), 'district_ids': set(), 'commune_ids': set()}
        )
        bucket['region_ids'].add(str(region.id))
        bucket['district_ids'].add(str(district.id))
        bucket['commune_ids'].add(str(commune.id))

    filtered_ouvrage_ids = []
    for ouvrage_id, geo in geo_map.items():
        if region_id and region_id not in geo['region_ids']:
            continue
        if district_id and district_id not in geo['district_ids']:
            continue
        if commune_id and commune_id not in geo['commune_ids']:
            continue
        filtered_ouvrage_ids.append(ouvrage_id)

    filtered_ouvrages = ouvrages_qs.filter(id__in=filtered_ouvrage_ids).order_by('nom_ouvrage')

    region_ids = {
        region_id_item
        for geo in geo_map.values()
        for region_id_item in geo['region_ids']
    }
    district_ids = {
        district_id_item
        for geo in geo_map.values()
        for district_id_item in geo['district_ids']
        if not region_id or region_id in geo['region_ids']
    }
    commune_ids = {
        commune_id_item
        for geo in geo_map.values()
        for commune_id_item in geo['commune_ids']
        if (
            (not region_id or region_id in geo['region_ids']) and
            (not district_id or district_id in geo['district_ids'])
        )
    }

    regions_qs = Region.objects.filter(id__in=region_ids).order_by('nom_region')
    if region_id:
        regions_qs = regions_qs.filter(id=region_id)

    districts_qs = District.objects.filter(id__in=district_ids).select_related('region').order_by('region__nom_region', 'nom_district')
    if district_id:
        districts_qs = districts_qs.filter(id=district_id)

    communes_qs = Commune.objects.filter(id__in=commune_ids).select_related('district__region').order_by('district__region__nom_region', 'district__nom_district', 'nom_commune')
    if commune_id:
        communes_qs = communes_qs.filter(id=commune_id)

    return {
        'regions': regions_qs,
        'districts': districts_qs,
        'communes': communes_qs,
        'ouvrages': filtered_ouvrages,
    }


def _resolve_debit_source_geography_for_ouvrage(ouvrage):
    point_eau = (
        PointEau.objects.filter(
            ouvrage=ouvrage,
            parcelle__village__fokontany__commune__district__region__isnull=False,
        )
        .select_related('parcelle__village__fokontany__commune__district__region')
        .first()
    )
    if not point_eau or not getattr(point_eau, 'parcelle', None) or not getattr(point_eau.parcelle, 'village', None):
        return {
            'region': None,
            'district': None,
            'commune': None,
        }
    commune = point_eau.parcelle.village.fokontany.commune
    district = commune.district if commune else None
    region = district.region if district else None
    return {
        'region': region,
        'district': district,
        'commune': commune,
    }


@login_required
def debit_source_page(request):
    region_id = request.GET.get('region') or ''
    district_id = request.GET.get('district') or ''
    commune_id = request.GET.get('commune') or ''
    ouvrage_id = request.GET.get('ouvrage') or ''
    dashboard_ouvrage_id = request.GET.get('dashboard_ouvrage') or ''
    selected_evolution = (request.GET.get('evolution') or '').strip()
    date_min_raw = request.GET.get('date_min') or ''
    date_max_raw = request.GET.get('date_max') or ''
    date_visite_raw = request.GET.get('date_visite') or timezone.localdate().isoformat()
    date_visite = timezone.localdate()
    date_min = None
    date_max = None
    try:
        if date_min_raw:
            date_min = datetime.strptime(date_min_raw, '%Y-%m-%d').date()
    except Exception:
        date_min = None
    try:
        if date_max_raw:
            date_max = datetime.strptime(date_max_raw, '%Y-%m-%d').date()
    except Exception:
        date_max = None
    try:
        date_visite = datetime.strptime(date_visite_raw, '%Y-%m-%d').date()
    except Exception:
        pass

    base_ouvrages = _get_debit_source_ouvrages_queryset(request.user)
    employe_options = list(_get_debit_source_employes_queryset(request.user))
    employe_lookup = _build_debit_source_employe_lookup(employe_options)
    default_debit_employe_id = ''
    user_employe = getattr(request.user, 'employe', None)
    if user_employe and any(str(item.id) == str(user_employe.id) for item in employe_options):
        default_debit_employe_id = str(user_employe.id)
    accessible_ouvrage_ids = {str(item) for item in base_ouvrages.values_list('id', flat=True)}
    geo_options = _get_debit_source_geo_queryset_map(base_ouvrages, region_id, district_id, commune_id)
    ouvrages = geo_options['ouvrages']
    regions = geo_options['regions']
    districts = geo_options['districts']
    communes = geo_options['communes']
    regions_data = [{'id': str(item.id), 'name': item.nom_region} for item in regions]
    districts_data = [{'id': str(item.id), 'name': item.nom_district, 'region_id': str(item.region_id)} for item in districts]
    communes_data = [{'id': str(item.id), 'name': item.nom_commune, 'district_id': str(item.district_id), 'region_id': str(item.district.region_id)} for item in communes]

    ouvrage_geo_map = {}
    for ouvrage in ouvrages:
        geo = _resolve_debit_source_geography_for_ouvrage(ouvrage)
        ouvrage.debit_geo_region_id = str(geo['region'].id) if geo['region'] else ''
        ouvrage.debit_geo_district_id = str(geo['district'].id) if geo['district'] else ''
        ouvrage.debit_geo_commune_id = str(geo['commune'].id) if geo['commune'] else ''
        ouvrage_geo_map[str(ouvrage.id)] = geo

    selected_ouvrage = ouvrages.filter(id=ouvrage_id).first() if ouvrage_id and ouvrage_id in accessible_ouvrage_ids else ouvrages.first()
    if request.method == 'POST':
        try:
            payload = json.loads(request.body or '{}')
        except Exception:
            payload = {}

        action = (payload.get('action') or '').strip()
        if action in {'update_debit_measure', 'delete_debit_measure'}:
            mesure_id = (payload.get('mesure_id') or '').strip()
            if not mesure_id:
                return JsonResponse({'success': False, 'error': 'mesure_id requis.'}, status=400)

            mesure = get_object_or_404(DebitSourceMesure.objects.select_related('ouvrage', 'employe'), id=mesure_id)
            if str(mesure.ouvrage_id) not in accessible_ouvrage_ids:
                return JsonResponse({'success': False, 'error': 'Acces refuse.'}, status=403)

            if action == 'delete_debit_measure':
                mesure.delete()
                return JsonResponse({'success': True, 'message': 'Mesure supprimee avec succes.'})

            date_visite_raw = (payload.get('date_visite') or '').strip()
            debit_l_s_raw = (payload.get('debit_l_s') or '').strip()
            remarque = (payload.get('remarque') or '').strip()
            ouvrage_id_raw = (payload.get('ouvrage_id') or '').strip()
            employe_id_raw = (payload.get('employe_id') or '').strip()

            if not date_visite_raw or debit_l_s_raw == '':
                return JsonResponse({'success': False, 'error': 'Date de visite et debit requis.'}, status=400)

            try:
                date_visite = datetime.strptime(date_visite_raw, '%Y-%m-%d').date()
                debit_l_s = Decimal(str(debit_l_s_raw))
            except Exception:
                return JsonResponse({'success': False, 'error': 'Valeurs invalides.'}, status=400)

            employe = _resolve_debit_source_employe(employe_id_raw, employe_lookup)
            if employe_id_raw and not employe:
                return JsonResponse({'success': False, 'error': "Employe introuvable ou hors perimetre."}, status=400)

            mesure.date_visite = date_visite
            mesure.debit_l_s = debit_l_s
            mesure.remarque = remarque
            mesure.employe = employe
            mesure.save(update_fields=['date_visite', 'debit_l_s', 'remarque', 'employe', 'updated_at'])
            if ouvrage_id_raw and str(mesure.ouvrage_id) != ouvrage_id_raw:
                new_ouvrage = ouvrages.filter(id=ouvrage_id_raw).first()
                if not new_ouvrage:
                    return JsonResponse({'success': False, 'error': 'Ouvrage cible introuvable.'}, status=404)
                if str(new_ouvrage.id) not in accessible_ouvrage_ids:
                    return JsonResponse({'success': False, 'error': 'Acces refuse.'}, status=403)
                mesure.ouvrage = new_ouvrage
                mesure.save(update_fields=['ouvrage'])
            if 'saisonnier' in payload and mesure.ouvrage_id:
                saisonnier_value = bool(payload.get('saisonnier'))
                if mesure.ouvrage.saisonnier != saisonnier_value:
                    mesure.ouvrage.saisonnier = saisonnier_value
                    mesure.ouvrage.save(update_fields=['saisonnier'])
            return JsonResponse({'success': True, 'message': 'Mesure mise a jour avec succes.'})

        ouvrage_id = request.POST.get('ouvrage') or ouvrage_id
        selected_ouvrage = ouvrages.filter(id=ouvrage_id).first() if ouvrage_id and ouvrage_id in accessible_ouvrage_ids else None
        date_visite_raw = request.POST.get('date_visite') or date_visite_raw
        try:
            date_visite = datetime.strptime(date_visite_raw, '%Y-%m-%d').date()
        except Exception:
            date_visite = timezone.localdate()

        debit_l_s = request.POST.get('debit_l_s')
        remarque = request.POST.get('remarque', '').strip()
        employe_id_raw = (request.POST.get('employe') or '').strip()
        saisonnier = request.POST.get('saisonnier') == 'on'
        employe = _resolve_debit_source_employe(employe_id_raw, employe_lookup)
        if employe_id_raw and not employe:
            messages.error(request, "Employe introuvable ou hors perimetre.")
        elif selected_ouvrage and debit_l_s not in [None, '']:
            DebitSourceMesure.objects.update_or_create(
                ouvrage=selected_ouvrage,
                date_visite=date_visite,
                defaults={
                    'debit_l_s': Decimal(str(debit_l_s)),
                    'remarque': remarque,
                    'employe': employe,
                    'created_by': getattr(request.user, 'employe', None),
                },
            )
            if selected_ouvrage.saisonnier != saisonnier:
                selected_ouvrage.saisonnier = saisonnier
                selected_ouvrage.save(update_fields=['saisonnier'])
            messages.success(request, 'Debit de source enregistre.')
            return redirect(f"{reverse('planning:debit_source')}?ouvrage={selected_ouvrage.id}&date_visite={date_visite.isoformat()}")
        if ouvrage_id and str(ouvrage_id) not in accessible_ouvrage_ids:
            messages.error(request, "Acces refuse. Vous ne pouvez saisir que les ouvrages sous votre responsabilite ou celle de vos subordonnes.")
        else:
            messages.error(request, 'Veuillez renseigner un ouvrage et un debit valide.')

    debit_info = _get_ouvrage_debit_context(selected_ouvrage, date_visite) if selected_ouvrage else {}

    historique = []
    dernier_releve = None
    releve_plus_bas = None
    dernier_releve_sous_seuil = False
    releve_plus_bas_sous_seuil = False
    if selected_ouvrage:
        historique_qs = DebitSourceMesure.objects.select_related('employe').filter(ouvrage=selected_ouvrage)
        if date_min:
            historique_qs = historique_qs.filter(date_visite__gte=date_min)
        if date_max:
            historique_qs = historique_qs.filter(date_visite__lte=date_max)
        historique = list(historique_qs.order_by('-date_visite', '-created_at')[:20])
        dernier_releve = historique[0] if historique else None
        releve_plus_bas = min(
            historique,
            key=lambda item: (item.debit_l_s if item.debit_l_s is not None else Decimal('999999999')),
            default=None,
        )
        for measure in historique:
            measure.type_mesure = _get_debit_source_type(measure.date_visite)
            prev = DebitSourceMesure.objects.filter(
                ouvrage=selected_ouvrage,
                date_visite__lt=measure.date_visite,
            ).order_by('-date_visite', '-created_at').first()
            measure.delta_vs_prev = None
            measure.tendance = 'stable'
            if prev and prev.debit_l_s is not None and measure.debit_l_s is not None:
                measure.delta_vs_prev = measure.debit_l_s - prev.debit_l_s
                if measure.delta_vs_prev > 0:
                    measure.tendance = 'augmente'
                elif measure.delta_vs_prev < 0:
                    measure.tendance = 'diminue'
        seuil_minimum = debit_info.get('seuil_minimum') if selected_ouvrage else None
        if dernier_releve and seuil_minimum is not None and dernier_releve.debit_l_s is not None:
            dernier_releve_sous_seuil = dernier_releve.debit_l_s < seuil_minimum
        if releve_plus_bas and seuil_minimum is not None and releve_plus_bas.debit_l_s is not None:
            releve_plus_bas_sous_seuil = releve_plus_bas.debit_l_s < seuil_minimum

    dashboard_mesures = []
    alert_count = 0
    latest_measures = (
        DebitSourceMesure.objects.filter(ouvrage_id__in=ouvrages.values_list('id', flat=True))
        .select_related('ouvrage', 'employe')
        .order_by('ouvrage__nom_ouvrage', '-date_visite', '-created_at')
    )
    latest_by_ouvrage = {}
    for measure in latest_measures:
        oid = str(measure.ouvrage_id)
        if oid not in latest_by_ouvrage:
            latest_by_ouvrage[oid] = measure
    for mesure in latest_by_ouvrage.values():
        if dashboard_ouvrage_id and str(mesure.ouvrage_id) != dashboard_ouvrage_id:
            continue
        prev = DebitSourceMesure.objects.filter(
            ouvrage_id=mesure.ouvrage_id,
            date_visite__lt=mesure.date_visite,
        ).order_by('-date_visite', '-created_at').first()
        delta = None
        tendance = 'stable'
        if prev and prev.debit_l_s is not None and mesure.debit_l_s is not None:
            delta = mesure.debit_l_s - prev.debit_l_s
            if delta > 0:
                tendance = 'augmente'
            elif delta < 0:
                tendance = 'diminue'
        dashboard_debit_info = _get_ouvrage_debit_context(mesure.ouvrage, mesure.date_visite)
        statut = _get_debit_status_label(mesure, dashboard_debit_info, delta)
        dashboard_mesures.append({
            'ouvrage': mesure.ouvrage,
            'measure': mesure,
            'type_mesure': _get_debit_source_type(mesure.date_visite),
            'delta': delta,
            'tendance': tendance,
            'statut': statut,
            'debit_info': dashboard_debit_info,
            'alerte': bool(
                dashboard_debit_info.get('is_forfaitaire')
                and dashboard_debit_info.get('seuil_minimum') is not None
                and mesure.debit_l_s is not None
                and mesure.debit_l_s < dashboard_debit_info['seuil_minimum']
            ),
        })
        if dashboard_mesures[-1]['alerte']:
            alert_count += 1

    # Include accessible ouvrages without any source-flow measurement so the
    # dashboard distribution reflects the full operational perimeter.
    measured_ouvrage_ids = set(latest_by_ouvrage.keys())
    for ouvrage in ouvrages:
        if dashboard_ouvrage_id and str(ouvrage.id) != dashboard_ouvrage_id:
            continue
        if str(ouvrage.id) in measured_ouvrage_ids:
            continue
        dashboard_mesures.append({
            'ouvrage': ouvrage,
            'measure': None,
            'type_mesure': None,
            'delta': None,
            'tendance': None,
            'statut': 'non_mesure',
            'debit_info': {},
            'alerte': False,
        })

    debit_status_counts = {
        status: sum(1 for item in dashboard_mesures if item['statut'] == status)
        for status in ('critique', 'baisse', 'stable', 'hausse', 'surveille', 'normal', 'non_mesure')
    }
    debit_status_counts['total'] = len(dashboard_mesures)

    valid_evolutions = set(debit_status_counts) - {'total'}
    if selected_evolution not in valid_evolutions:
        selected_evolution = ''
    if selected_evolution:
        dashboard_mesures = [
            item for item in dashboard_mesures
            if item['statut'] == selected_evolution
        ]
    dashboard_mesures.sort(key=lambda item: (
        _get_debit_status_priority(item['statut']),
        item['ouvrage'].nom_ouvrage if item.get('ouvrage') else '',
    ))

    def _build_abaque_groups(volume_liters, start_second, end_second, step_seconds, group_size=20):
        grouped_rows = []
        current_group = None
        for second in range(start_second, end_second + 1, step_seconds):
            debit_l_s = Decimal(str(volume_liters)) / Decimal(second)
            debit_l_s_rounded = debit_l_s.quantize(Decimal('0.01'))
            if current_group and current_group['debit_l_s'] == debit_l_s_rounded:
                current_group['secondes_fin'] = second
            else:
                if current_group:
                    grouped_rows.append(current_group)
                current_group = {
                    'secondes_debut': second,
                    'secondes_fin': second,
                    'debit_l_s': debit_l_s_rounded,
                }
        if current_group:
            grouped_rows.append(current_group)
        return [
            grouped_rows[index:index + group_size]
            for index in range(0, len(grouped_rows), group_size)
        ]

    abaque_groups = _build_abaque_groups(volume_liters=5, start_second=2, end_second=120, step_seconds=2)
    abaque_1l_groups = _build_abaque_groups(volume_liters=1, start_second=1, end_second=60, step_seconds=1)

    context = {
        'ouvrages': ouvrages,
        'regions': regions,
        'districts': districts,
        'communes': communes,
        'regions_data': regions_data,
        'districts_data': districts_data,
        'communes_data': communes_data,
        'selected_region_id': region_id,
        'selected_district_id': district_id,
        'selected_commune_id': commune_id,
        'selected_ouvrage': selected_ouvrage,
        'dashboard_ouvrage_id': dashboard_ouvrage_id,
        'selected_evolution': selected_evolution,
        'date_visite': date_visite,
        'date_min': date_min,
        'date_max': date_max,
        'historique': historique,
        'dernier_releve': dernier_releve,
        'releve_plus_bas': releve_plus_bas,
        'dernier_releve_sous_seuil': dernier_releve_sous_seuil,
        'releve_plus_bas_sous_seuil': releve_plus_bas_sous_seuil,
        'dashboard_mesures': dashboard_mesures[:50],
        'alert_count': alert_count,
        'debit_status_counts': debit_status_counts,
        'historique_chart_labels': [m.date_visite.strftime('%d/%m/%Y') for m in reversed(historique)],
        'historique_chart_values': [float(m.debit_l_s) for m in reversed(historique)],
        'historique_chart_types': [_get_debit_source_type(m.date_visite) for m in reversed(historique)],
        'historique_chart_threshold': float(debit_info.get('seuil_minimum') or 0) if debit_info else 0,
        'debit_info': debit_info,
        'debit_status_labels': {
            'normal': 'Normal',
            'surveille': 'A surveiller',
            'stable': 'Stable',
            'baisse': 'Baisse',
            'hausse': 'Hausse',
            'critique': 'Critique',
            'inconnu': 'Inconnu',
        },
        'employe_options': employe_options,
        'default_debit_employe_id': default_debit_employe_id,
        'abaque_groups': abaque_groups,
        'abaque_1l_groups': abaque_1l_groups,
    }
    return render(request, 'planning/debit_source_page.html', context)


@login_required
def export_excel_debits_source(request):
    from io import BytesIO
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from django.http import HttpResponse

    ouvrages = _get_debit_source_ouvrages_queryset(request.user)
    region_id = (request.GET.get('region') or '').strip()
    district_id = (request.GET.get('district') or '').strip()
    commune_id = (request.GET.get('commune') or '').strip()
    # L'ouvrage explicitement selectionne dans le formulaire est prioritaire.
    # ``dashboard_ouvrage`` reste accepte pour compatibilite avec les anciens liens.
    selected_ouvrage_id = (request.GET.get('ouvrage') or '').strip()
    ouvrage_id = selected_ouvrage_id or (request.GET.get('dashboard_ouvrage') or '').strip()
    date_min_raw = (request.GET.get('date_min') or '').strip()
    date_max_raw = (request.GET.get('date_max') or '').strip()

    date_min = None
    date_max = None
    try:
        if date_min_raw:
            date_min = datetime.strptime(date_min_raw, '%Y-%m-%d').date()
    except Exception:
        pass
    try:
        if date_max_raw:
            date_max = datetime.strptime(date_max_raw, '%Y-%m-%d').date()
    except Exception:
        pass

    ouvrages = _get_debit_source_geo_queryset_map(ouvrages, region_id, district_id, commune_id)['ouvrages']
    qs = DebitSourceMesure.objects.select_related('ouvrage', 'employe').order_by('ouvrage__nom_ouvrage', '-date_visite', '-created_at')
    qs = qs.filter(ouvrage_id__in=ouvrages.values_list('id', flat=True))
    if ouvrage_id:
        qs = qs.filter(ouvrage_id=ouvrage_id)
    # Un export lance depuis la fiche ouvrage couvre toujours tout son historique.
    if date_min and not selected_ouvrage_id:
        qs = qs.filter(date_visite__gte=date_min)
    if date_max and not selected_ouvrage_id:
        qs = qs.filter(date_visite__lte=date_max)

    wb = Workbook()
    ws = wb.active
    ws.title = "Debits source"
    headers = ['Ouvrage', 'Region', 'District', 'Commune', 'Date visite', 'Debit (L/s)', 'Employe', 'Remarque', 'Statut']
    ws.append(headers)

    header_fill = PatternFill('solid', fgColor='1E293B')
    header_font = Font(color='FFFFFF', bold=True)
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')

    for mesure in qs:
        debit_info = _get_ouvrage_debit_context(mesure.ouvrage, mesure.date_visite)
        geo = _resolve_debit_source_geography_for_ouvrage(mesure.ouvrage)
        prev = DebitSourceMesure.objects.filter(
            ouvrage=mesure.ouvrage,
            date_visite__lt=mesure.date_visite,
        ).order_by('-date_visite', '-created_at').first()
        delta = None
        if prev and prev.debit_l_s is not None and mesure.debit_l_s is not None:
            delta = Decimal(str(mesure.debit_l_s)) - Decimal(str(prev.debit_l_s))
        statut = _get_debit_status_label(mesure, debit_info, delta)
        ws.append([
            mesure.ouvrage.nom_ouvrage if mesure.ouvrage_id else '-',
            geo['region'].nom_region if geo['region'] else '-',
            geo['district'].nom_district if geo['district'] else '-',
            geo['commune'].nom_commune if geo['commune'] else '-',
            mesure.date_visite.isoformat() if mesure.date_visite else '-',
            float(mesure.debit_l_s) if mesure.debit_l_s is not None else None,
            mesure.employe.nom_affichage if mesure.employe_id else '',
            mesure.remarque or '',
            statut,
        ])

    for col in ws.columns:
        max_length = 0
        column_letter = col[0].column_letter
        for cell in col:
            value = '' if cell.value is None else str(cell.value)
            if len(value) > max_length:
                max_length = len(value)
        ws.column_dimensions[column_letter].width = min(max_length + 4, 45)

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    filename = f"historique_debit_source_{ouvrage_id}.xlsx" if ouvrage_id else "debits_source.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def export_pdf_debits_source(request):
    from io import BytesIO
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from django.http import HttpResponse
    from xml.sax.saxutils import escape

    ouvrages = _get_debit_source_ouvrages_queryset(request.user)
    region_id = (request.GET.get('region') or '').strip()
    district_id = (request.GET.get('district') or '').strip()
    commune_id = (request.GET.get('commune') or '').strip()
    # L'ouvrage choisi sur la page doit produire son historique, et non la liste
    # de tous les ouvrages rattaches a l'utilisateur.
    selected_ouvrage_id = (request.GET.get('ouvrage') or '').strip()
    ouvrage_id = selected_ouvrage_id or (request.GET.get('dashboard_ouvrage') or '').strip()
    date_min_raw = (request.GET.get('date_min') or '').strip()
    date_max_raw = (request.GET.get('date_max') or '').strip()

    date_min = None
    date_max = None
    try:
        if date_min_raw:
            date_min = datetime.strptime(date_min_raw, '%Y-%m-%d').date()
    except Exception:
        pass
    try:
        if date_max_raw:
            date_max = datetime.strptime(date_max_raw, '%Y-%m-%d').date()
    except Exception:
        pass

    ouvrages = _get_debit_source_geo_queryset_map(ouvrages, region_id, district_id, commune_id)['ouvrages']
    qs = DebitSourceMesure.objects.select_related('ouvrage', 'employe').order_by('ouvrage__nom_ouvrage', '-date_visite', '-created_at')
    qs = qs.filter(ouvrage_id__in=ouvrages.values_list('id', flat=True))
    if ouvrage_id:
        qs = qs.filter(ouvrage_id=ouvrage_id)
    # Un export lance depuis la fiche ouvrage couvre toujours tout son historique.
    if date_min and not selected_ouvrage_id:
        qs = qs.filter(date_visite__gte=date_min)
    if date_max and not selected_ouvrage_id:
        qs = qs.filter(date_visite__lte=date_max)

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=1*cm, leftMargin=1*cm, topMargin=1*cm, bottomMargin=1*cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DebitTitle',
        parent=styles['Title'],
        fontSize=16,
        leading=20,
        textColor=colors.HexColor('#0f172a'),
    )
    normal_style = styles['BodyText']
    table_cell_style = ParagraphStyle(
        'DebitTableCell',
        parent=normal_style,
        fontName='Helvetica',
        fontSize=6.5,
        leading=8,
        spaceAfter=0,
        spaceBefore=0,
        wordWrap='CJK',
    )
    table_header_style = ParagraphStyle(
        'DebitTableHeader',
        parent=table_cell_style,
        fontName='Helvetica-Bold',
        textColor=colors.white,
        alignment=1,
    )

    headers = ['Ouvrage', 'Region', 'District', 'Commune', 'Date visite', 'Debit (L/s)', 'Employe', 'Statut', 'Remarque']
    debit_rows = [[Paragraph(escape(label), table_header_style) for label in headers]]
    alert_count = 0
    status_counts = {
        'normal': 0,
        'surveille': 0,
        'stable': 0,
        'baisse': 0,
        'hausse': 0,
        'critique': 0,
        'inconnu': 0,
    }
    pdf_rows = []
    for mesure in qs:
        debit_info = _get_ouvrage_debit_context(mesure.ouvrage, mesure.date_visite)
        geo = _resolve_debit_source_geography_for_ouvrage(mesure.ouvrage)
        prev = DebitSourceMesure.objects.filter(
            ouvrage=mesure.ouvrage,
            date_visite__lt=mesure.date_visite,
        ).order_by('-date_visite', '-created_at').first()
        delta = None
        if prev and prev.debit_l_s is not None and mesure.debit_l_s is not None:
            delta = Decimal(str(mesure.debit_l_s)) - Decimal(str(prev.debit_l_s))
        statut = _get_debit_status_label(mesure, debit_info, delta)
        if statut == 'critique':
            alert_count += 1
        status_counts[statut] = status_counts.get(statut, 0) + 1
        pdf_rows.append({
            'ouvrage': mesure.ouvrage.nom_ouvrage if mesure.ouvrage_id else '-',
            'region': geo['region'].nom_region if geo['region'] else '-',
            'district': geo['district'].nom_district if geo['district'] else '-',
            'commune': geo['commune'].nom_commune if geo['commune'] else '-',
            'date_visite': mesure.date_visite.isoformat() if mesure.date_visite else '-',
            'debit': str(mesure.debit_l_s),
            'employe': mesure.employe.nom_affichage if mesure.employe_id else '-',
            'statut': statut,
            'remarque': mesure.remarque or '-',
        })

    pdf_rows.sort(key=lambda row: (
        _get_debit_status_priority(row['statut']),
        row['ouvrage'],
        row['date_visite'],
    ))

    for row in pdf_rows:
        debit_rows.append([
            Paragraph(escape(str(row['ouvrage'])), table_cell_style),
            Paragraph(escape(str(row['region'])), table_cell_style),
            Paragraph(escape(str(row['district'])), table_cell_style),
            Paragraph(escape(str(row['commune'])), table_cell_style),
            Paragraph(escape(str(row['date_visite'])), table_cell_style),
            Paragraph(escape(str(row['debit'])), table_cell_style),
            Paragraph(escape(str(row['employe'])), table_cell_style),
            Paragraph(escape(str(row['statut'])), table_cell_style),
            Paragraph(escape(str(row['remarque'])), table_cell_style),
        ])

    elements = [
        Paragraph('Synthese des debits de source', title_style),
        Spacer(1, 0.3 * cm),
        Paragraph(
            "Filtres: "
            + (
                f"Ouvrage={ouvrage_id}" if ouvrage_id else "Tous les ouvrages"
            )
            + (
                f" | Region={region_id}" if region_id else ""
            )
            + (
                f" | District={district_id}" if district_id else ""
            )
            + (
                f" | Commune={commune_id}" if commune_id else ""
            )
            + (
                f" | Du={date_min.isoformat()}" if date_min else ""
            )
            + (
                f" | Au={date_max.isoformat()}" if date_max else ""
            ),
            normal_style,
        ),
        Spacer(1, 0.2 * cm),
        Paragraph(
            f"Mesures exportees: {max(len(debit_rows) - 1, 0)} | Alertes critiques: {alert_count}",
            normal_style,
        ),
        Spacer(1, 0.3 * cm),
    ]
    summary_rows = [
        ['Indicateur', 'Valeur'],
        ['Critique', str(status_counts.get('critique', 0))],
        ['A surveiller', str(status_counts.get('surveille', 0))],
        ['Stable', str(status_counts.get('stable', 0))],
        ['Hausse', str(status_counts.get('hausse', 0))],
        ['Baisse', str(status_counts.get('baisse', 0))],
        ['Normal', str(status_counts.get('normal', 0))],
    ]
    summary_table = Table(summary_rows, colWidths=[6 * cm, 3 * cm])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e293b')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#cbd5e1')),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
    ]))
    elements.extend([
        summary_table,
        Spacer(1, 0.35 * cm),
    ])
    # Largeur totale: 25,1 cm, inferieure a la largeur utile du paysage A4
    # (27,7 cm avec les marges ci-dessus). Les Paragraph assurent le retour a
    # la ligne des noms et remarques longs sans elargir le tableau.
    table = Table(
        debit_rows,
        colWidths=[3.2 * cm, 2.5 * cm, 2.7 * cm, 2.7 * cm, 2.1 * cm, 1.8 * cm, 3.3 * cm, 2.1 * cm, 4.7 * cm],
        repeatRows=1,
        hAlign='LEFT',
    )
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e293b')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#cbd5e1')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2.5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2.5),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    for row_index, row in enumerate(pdf_rows, start=1):
        if row['statut'] == 'critique':
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, row_index), (-1, row_index), colors.HexColor('#fee2e2')),
                ('TEXTCOLOR', (0, row_index), (-1, row_index), colors.HexColor('#991b1b')),
            ]))
    elements.append(table)
    doc.build(elements)

    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    filename = f"historique_debit_source_{ouvrage_id}.pdf" if ouvrage_id else "debits_source.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def import_excel_debits_source(request):
    if request.method != 'POST':
        return redirect('planning:debit_source')

    from openpyxl import load_workbook

    uploaded_file = request.FILES.get('file')
    if not uploaded_file:
        messages.error(request, "Aucun fichier Excel fourni.")
        return redirect('planning:debit_source')

    ouvrages = _get_debit_source_ouvrages_queryset(request.user)
    ouvrage_by_id = {str(o.id): o for o in ouvrages}
    ouvrage_by_name = {str(o.nom_ouvrage).strip().lower(): o for o in ouvrages}
    employe_options = list(_get_debit_source_employes_queryset(request.user))
    employe_lookup = _build_debit_source_employe_lookup(employe_options)

    created = 0
    updated = 0
    errors = []

    try:
        workbook = load_workbook(uploaded_file)
        sheet = workbook.active
        expected_headers = ['Ouvrage', 'Date visite', 'Debit (L/s)', 'Employe', 'Remarque']
        actual_headers = [
            str(cell.value).strip() if cell.value is not None else ''
            for cell in next(sheet.iter_rows(min_row=1, max_row=1))
        ]
        if actual_headers[:len(expected_headers)] != expected_headers:
            messages.error(
                request,
                "Le fichier Excel n'utilise pas le modele attendu. "
                "Colonnes requises: Ouvrage, Date visite, Debit (L/s), Employe, Remarque."
            )
            return redirect('planning:debit_source')

        for idx, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
            if not row or not any(row):
                continue
            ouvrage_val, date_visite_val, debit_val, employe_val, remarque_val = (list(row) + [None] * 5)[:5]
            ouvrage = ouvrage_by_id.get(str(ouvrage_val).strip()) or ouvrage_by_name.get(str(ouvrage_val).strip().lower())
            if not ouvrage:
                errors.append(f"Ligne {idx}: ouvrage introuvable")
                continue
            try:
                if isinstance(date_visite_val, datetime):
                    date_visite = date_visite_val.date()
                elif isinstance(date_visite_val, date):
                    date_visite = date_visite_val
                else:
                    date_visite = datetime.strptime(str(date_visite_val).strip(), '%d/%m/%Y').date()
                debit = Decimal(str(debit_val))
            except Exception:
                errors.append(f"Ligne {idx}: date ou debit invalide")
                continue

            employe = _resolve_debit_source_employe(employe_val, employe_lookup)
            if str(employe_val or '').strip() and not employe:
                errors.append(f"Ligne {idx}: employe introuvable ou hors perimetre")
                continue

            _, was_created = DebitSourceMesure.objects.update_or_create(
                ouvrage=ouvrage,
                date_visite=date_visite,
                defaults={
                    'debit_l_s': debit,
                    'employe': employe,
                    'remarque': str(remarque_val).strip() if remarque_val else '',
                    'created_by': getattr(request.user, 'employe', None),
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1
    except Exception as exc:
        messages.error(request, f"Erreur lors de l'import Excel: {exc}")
        return redirect('planning:debit_source')

    if created:
        messages.success(request, f"{created} mesure(s) importee(s).")
    if updated:
        messages.info(request, f"{updated} mesure(s) mise(s) a jour.")
    for error in errors[:10]:
        messages.warning(request, error)
    return redirect('planning:debit_source')


@login_required
def template_excel_debits_source(request):
    from io import BytesIO
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from django.http import HttpResponse

    wb = Workbook()
    ws = wb.active
    ws.title = "Debits source"
    headers = ['Ouvrage', 'Date visite', 'Debit (L/s)', 'Employe', 'Remarque']
    ws.append(headers)

    header_fill = PatternFill('solid', fgColor='1E293B')
    header_font = Font(color='FFFFFF', bold=True)
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')

    ws.append(['Nom ou ID ouvrage', '14/04/2026', 0.0, 'Mon surnom ou UUID', 'Exemple de remarque'])

    for column, width in {'A': 32, 'B': 18, 'C': 16, 'D': 28, 'E': 40}.items():
        ws.column_dimensions[column].width = width

    ws_info = wb.create_sheet("Instructions")
    ws_info.append(["MODELE IMPORT DEBITS SOURCE"])
    ws_info.append([])
    ws_info.append(["Colonnes obligatoires"])
    ws_info.append(["- Ouvrage"])
    ws_info.append(["- Date visite"])
    ws_info.append(["- Debit (L/s)"])
    ws_info.append(["- Employe (facultatif)"])
    ws_info.append(["- Remarque"])
    ws_info.append([])
    ws_info.append(["Format attendu"])
    ws_info.append(["- Date visite : DD/MM/YYYY"])
    ws_info.append(["- Debit (L/s) : nombre decimal"])
    ws_info.append(["- Ouvrage : nom ou ID de l'ouvrage"])
    ws_info.append(["- Employe : UUID, surnom, nom complet ou nom d'affichage"])
    ws_info.append([])
    ws_info.append(["Exemple de ligne"])
    ws_info.append(["Nom ou ID ouvrage", "14/04/2026", 0.125, "Mon surnom ou UUID", "Mesure normale"])
    ws_info.column_dimensions['A'].width = 75

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="template_debits_source.xlsx"'
    return response


@login_required
def api_debit_source_filter_options(request):
    region_id = (request.GET.get('region') or '').strip()
    district_id = (request.GET.get('district') or '').strip()
    commune_id = (request.GET.get('commune') or '').strip()
    geo_options = _get_debit_source_geo_queryset_map(
        _get_debit_source_ouvrages_queryset(request.user),
        region_id,
        district_id,
        commune_id,
    )
    return JsonResponse({
        'success': True,
        'regions': [{'id': str(item.id), 'name': item.nom_region} for item in geo_options['regions']],
        'districts': [{'id': str(item.id), 'name': item.nom_district, 'region_id': str(item.region_id)} for item in geo_options['districts']],
        'communes': [{'id': str(item.id), 'name': item.nom_commune, 'district_id': str(item.district_id), 'region_id': str(item.district.region_id)} for item in geo_options['communes']],
        'ouvrages': [{'id': str(item.id), 'name': item.nom_ouvrage} for item in geo_options['ouvrages']],
    })


@login_required
def api_debits_source_alert_count(request):
    ouvrages = _get_debit_source_ouvrages_queryset(request.user).values_list('id', flat=True)

    latest_measures = (
        DebitSourceMesure.objects.filter(ouvrage_id__in=ouvrages)
        .select_related('ouvrage')
        .order_by('ouvrage_id', '-date_visite', '-created_at')
        .distinct('ouvrage_id')
    )

    count = 0
    for mesure in latest_measures:
        debit_info = _get_ouvrage_debit_context(mesure.ouvrage, mesure.date_visite)
        prev = DebitSourceMesure.objects.filter(
            ouvrage=mesure.ouvrage,
            date_visite__lt=mesure.date_visite,
        ).order_by('-date_visite', '-created_at').first()
        delta = None
        if prev and prev.debit_l_s is not None and mesure.debit_l_s is not None:
            delta = Decimal(str(mesure.debit_l_s)) - Decimal(str(prev.debit_l_s))
        if _get_debit_status_label(mesure, debit_info, delta) == 'critique':
            count += 1

    return JsonResponse({
        'success': True,
        'count': count,
    })


def _format_planning_print_date(value, tz=None):
    if not value:
        return '-'

    if isinstance(value, datetime):
        if value.tzinfo:
            value_to_format = value.astimezone(tz) if tz else value
        else:
            aware_value = timezone.make_aware(value)
            value_to_format = aware_value.astimezone(tz) if tz else aware_value
        return value_to_format.strftime('%d/%m/%Y')

    if hasattr(value, 'strftime'):
        return value.strftime('%d/%m/%Y')

    return str(value)


def _format_paiement_forfaitaire_validity(paiement):
    start_label = _format_planning_print_date(getattr(paiement, 'date_debut_validite', None))
    end_label = _format_planning_print_date(getattr(paiement, 'date_fin_validite', None))

    if start_label != '-' and end_label != '-':
        return f"{start_label} -> {end_label}"
    if start_label != '-':
        return start_label
    if end_label != '-':
        return end_label
    return '-'


def _normalize_poste_name(value):
    if not value:
        return ''
    normalized = unicodedata.normalize('NFKD', str(value))
    return normalized.encode('ascii', errors='ignore').decode('ascii').lower().strip()


def _get_planning_scope(user):
    """
    Regles de cloisonnement plannings:
    - Superuser: tout
    - Directeur: tout
    - Directeur adjoint / Responsable administratif (et financier) / RAF: organisation
    - Autres postes: base
    """
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


def _is_planning_director(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    employe = getattr(user, 'employe', None)
    poste = getattr(employe, 'poste', None)
    poste_nom = getattr(poste, 'nom_poste', '')
    return poste_nom in ['Directeur', 'Directrice', 'Directeur General', 'Directeur adjoint']


def _get_planning_validation_ui_context(user):
    allowed_ids = get_planning_validation_target_employe_ids(user)
    allowed_ids_json = json.dumps(
        sorted(str(employe_id) for employe_id in (allowed_ids or set()))
    )
    return {
        'planning_validation_is_director': is_planning_validation_director(user),
        'planning_validation_target_ids_json': allowed_ids_json,
    }


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


def _get_scoped_plannings_queryset(user):
    queryset = Planning.objects.select_related(
        'employe', 'employe__poste', 'fiche_poste', 'type_activite', 'ouvrage'
    )
    queryset = filter_queryset_by_permissions(queryset, user)
    return _filter_plannings_by_scope(queryset, user)


def _coerce_merge_duplicate_bool(value):
    if isinstance(value, bool):
        return value
    normalized = str(value or '').strip().lower()
    if normalized in {'true', '1', 'oui', 'yes'}:
        return True
    if normalized in {'false', '0', 'non', 'no'}:
        return False
    return None


def _apply_dashboard_merge_filters(queryset, filters):
    filters = filters or {}

    employe_id = str(filters.get('employe') or '').strip()
    if employe_id:
        queryset = queryset.filter(employe_id=employe_id)

    mois = str(filters.get('mois') or '').strip()
    if re.match(r'^\d{4}-\d{2}$', mois):
        year, month = mois.split('-')
        queryset = queryset.filter(date__year=int(year), date__month=int(month))

    ouvrage_id = str(filters.get('ouvrage') or '').strip()
    if ouvrage_id:
        queryset = queryset.filter(ouvrage_id=ouvrage_id)

    type_activite_id = str(filters.get('type_activite') or '').strip()
    if type_activite_id:
        queryset = queryset.filter(type_activite_id=type_activite_id)

    activite_id = str(filters.get('activite') or '').strip()
    if activite_id:
        queryset = queryset.filter(fiche_poste_id=activite_id)

    validation = _coerce_merge_duplicate_bool(filters.get('validation'))
    if validation is not None:
        queryset = queryset.filter(estvalide=validation)

    return queryset


def _build_duplicate_merge_group_key(planning, mode='activity'):
    if not planning or not getattr(planning, 'date', None):
        return None

    planning_date = planning.date.date() if hasattr(planning.date, 'date') else planning.date

    activity_label = views_simple._normalize_poste_name(
        views_simple._get_planning_activity_label(planning=planning)
    )
    if not activity_label:
        return None

    if getattr(planning, 'ouvrage_id', None):
        ouvrage_scope = str(planning.ouvrage_id)
    elif views_simple._is_shared_no_ouvrage_activity_label(activity_label):
        ouvrage_scope = 'shared:no-ouvrage'
    else:
        return None

    if mode == 'strict':
        return (
            planning_date,
            ouvrage_scope,
            str(getattr(planning, 'employe_id', '') or ''),
            str(getattr(planning, 'fiche_poste_id', '') or ''),
            str(getattr(planning, 'type_activite_id', '') or ''),
        )

    return (planning_date, ouvrage_scope, activity_label)


def _get_planning_status_badge_class(statut):
    return PLANNING_STATUS_BADGE_CLASSES.get((statut or '').strip(), 'badge-ghost')


def _get_planning_paper_badge_class(verification):
    return PLANNING_PAPER_BADGE_CLASSES.get((verification or '').strip(), 'badge-ghost')


def _get_planning_paper_label(verification):
    verification = (verification or '').strip()
    if not verification:
        return 'Non renseigne'
    return PLANNING_PAPER_VERIFICATION_LABELS.get(verification, verification)


def _annotate_planning_execution_meta(planning):
    planning.effective_status_value = ((planning.statut or '').strip() or 'en_cours')
    planning.status_badge_class = _get_planning_status_badge_class(planning.statut)
    planning.paper_verification_label = _get_planning_paper_label(planning.verification)
    planning.paper_badge_class = _get_planning_paper_badge_class(planning.verification)
    planning.has_known_paper_verification = bool((planning.verification or '').strip())
    return planning


def _get_planning_monthly_cloture_selected_status(planning):
    statut = ((getattr(planning, 'statut', '') or '').strip() or '')
    if statut in PLANNING_MONTHLY_CLOTURE_ALLOWED:
        return statut
    return 'termine'


def _build_monthly_cloture_report_datetime(planning, raw_report_date):
    report_date_value = (raw_report_date or '').strip()
    if not report_date_value:
        raise ValueError('Nouvelle date obligatoire pour une activite reportee.')

    try:
        report_date = datetime.strptime(report_date_value, '%Y-%m-%d').date()
    except ValueError as exc:
        raise ValueError('Nouvelle date de report invalide.') from exc

    current_datetime = getattr(planning, 'date', None)
    if not current_datetime:
        return datetime.combine(report_date, datetime.min.time())

    if timezone.is_aware(current_datetime):
        current_local_datetime = timezone.localtime(current_datetime)
        if current_local_datetime.date() == report_date:
            raise ValueError('La nouvelle date doit etre differente de la date actuelle.')
        rebuilt_datetime = datetime.combine(
            report_date,
            current_local_datetime.time().replace(tzinfo=None),
        )
        return timezone.make_aware(rebuilt_datetime, timezone.get_current_timezone())

    if current_datetime.date() == report_date:
        raise ValueError('La nouvelle date doit etre differente de la date actuelle.')

    return datetime.combine(report_date, current_datetime.time())


def _prepare_monthly_cloture_actions(plannings, payload):
    payload = payload or {}
    actions = []
    errors = []

    for planning in plannings:
        planning.monthly_cloture_selected_status = _get_planning_monthly_cloture_selected_status(planning)
        planning.report_date_input_value = ''

        if getattr(planning, 'is_blocked_activity', False):
            continue

        selected_status = (
            payload.get(f'statut_{planning.id}')
            or planning.monthly_cloture_selected_status
            or 'termine'
        ).strip()
        report_date_raw = (payload.get(f'report_date_{planning.id}') or '').strip()

        planning.monthly_cloture_selected_status = selected_status
        planning.report_date_input_value = report_date_raw

        if selected_status not in PLANNING_MONTHLY_CLOTURE_ALLOWED:
            errors.append(
                f"Decision invalide pour la ligne du {planning.date:%d/%m/%Y}."
            )
            continue

        report_datetime = None
        if selected_status == 'reporte':
            try:
                report_datetime = _build_monthly_cloture_report_datetime(planning, report_date_raw)
            except ValueError as exc:
                errors.append(f"{planning.date:%d/%m/%Y} - {exc}")
                continue

        actions.append({
            'planning': planning,
            'selected_status': selected_status,
            'report_datetime': report_datetime,
        })

    return actions, errors


def _apply_monthly_cloture_actions(actions):
    summary = {
        'termine': 0,
        'annule': 0,
        'reporte': 0,
    }

    with transaction.atomic():
        for action in actions:
            planning = action['planning']
            selected_status = action['selected_status']

            if selected_status == 'annule':
                planning.delete()
                summary['annule'] += 1
                continue

            if selected_status == 'reporte':
                planning.date = action['report_datetime']
                planning.statut = 'en_cours'
                planning.verification = ''
                planning.commentaire_verification = ''
                planning.estvalide = False
                planning.save()
                summary['reporte'] += 1
                continue

            planning.statut = 'termine'
            planning.save()
            summary['termine'] += 1

    return summary


def _get_default_planning_month_value():
    return timezone.localdate().strftime('%Y-%m')


def _resolve_planning_cloture_filters(user, payload):
    payload = payload or {}
    mois_value = (payload.get('mois') or '').strip() or _get_default_planning_month_value()
    employe_value = (payload.get('employe') or '').strip()

    if not employe_value and not _is_planning_director(user):
        employe = getattr(user, 'employe', None)
        if employe and getattr(employe, 'id', None):
            employe_value = str(employe.id)

    return {
        'mois_value': mois_value,
        'employe_value': employe_value,
    }


def _get_planning_activity_label(planning):
    if getattr(planning, 'fiche_poste', None) and getattr(planning.fiche_poste, 'tache', None):
        return planning.fiche_poste.tache
    if getattr(planning, 'type_activite', None) and getattr(planning.type_activite, 'nomtype', None):
        return planning.type_activite.nomtype
    return ''


def _is_planning_cloture_blocked(planning):
    return _get_planning_activity_label(planning) in ['Congé', 'Congé demi-journée', 'Permission']


@employe_required
def workflow_terrain(request):
    """Vue dédiée au workflow terrain : inspections et traitement des activités
    Affiche uniquement les plannings validés avec équipements ou points d'eau"""

    # Récupérer l'employé connecté
    employe_connecte_id = None
    if hasattr(request.user, 'employe'):
        employe_connecte_id = str(request.user.employe.id)

    context = {
        'employe_connecte_id': employe_connecte_id
    }

    return render(request, 'planning/workflow_terrain.html', context)


@employe_required
def planning_dashboard(request):
    """Dashboard principal des plannings"""
    employe_connecte_id = ''
    employe = getattr(request.user, 'employe', None)
    if employe and getattr(employe, 'id', None):
        employe_connecte_id = str(employe.id)

    try:
        debit_source_url = reverse('planning:debit_source')
    except NoReverseMatch:
        debit_source_url = ''

    context = {
        'employe_connecte_id': employe_connecte_id,
        'current_month': timezone.localdate().strftime('%Y-%m'),
        'debit_source_url': debit_source_url,
    }
    context.update(_get_planning_validation_ui_context(request.user))
    return render(request, 'planning/planning_dashboard.html', context)


@employe_required
def planning_list(request):
    from datetime import datetime
    selected_mois = (request.GET.get('mois') or '').strip()
    selected_employe_filter = (request.GET.get('employe_filter') or '').strip()
    default_filters_applied = False
    try:
        plannings = _get_scoped_plannings_queryset(request.user)

        # Appliquer les filtres par défaut si aucun filtre n'est appliqué
        # Filtre par défaut : employé connecté + mois en cours (sauf si un filtre est actif ou ?all=1)
        active_filters = ['all', 'estvalide', 'nonvalide', 'activite', 'fiche_poste', 'ouvrage', 'employe_filter', 'mois']
        has_active_filter = any(request.GET.get(f) for f in active_filters)

        if not has_active_filter:
            # Mois en cours
            now = datetime.now()
            plannings = plannings.filter(
                date__year=now.year,
                date__month=now.month
            )
            selected_mois = f"{now.year}-{now.month:02d}"
            if getattr(request, 'employe', None):
                plannings = plannings.filter(employe_id=request.employe.id)
                selected_employe_filter = str(request.employe.id)
            default_filters_applied = True

        # Filtre par mois
        if selected_mois:
            try:
                selected_mois_date = datetime.strptime(selected_mois, "%Y-%m")
                plannings = plannings.filter(
                    date__year=selected_mois_date.year,
                    date__month=selected_mois_date.month,
                )
            except ValueError:
                selected_mois = ''

        # Filtre Validé
        estvalide = request.GET.get('estvalide', '')
        nonvalide = request.GET.get('nonvalide', '')

        if estvalide == 'true':
            plannings = plannings.filter(estvalide=True)
        elif nonvalide == 'true':
            plannings = plannings.filter(Q(estvalide=False) | Q(estvalide__isnull=True))

        # Nouveaux filtres
        activite_id = request.GET.get('activite')
        if activite_id:
            plannings = plannings.filter(type_activite_id=activite_id)

        fiche_poste_id = request.GET.get('fiche_poste')
        if fiche_poste_id:
            plannings = plannings.filter(fiche_poste_id=fiche_poste_id)

        ouvrage_id = request.GET.get('ouvrage')
        if ouvrage_id:
            plannings = plannings.filter(ouvrage_id=ouvrage_id)

        if selected_employe_filter:
            plannings = plannings.filter(employe_id=selected_employe_filter)

        plannings = plannings.order_by('date', 'employe__nom', 'employe__prenom', 'id')

    except Exception as e:
        print(f"[ERROR] planning_list: {e}")
        plannings = Planning.objects.none()

    # Calculer les statistiques
    from django.db.models import Count, Sum, Q, F
    from decimal import Decimal

    planning_ids = plannings.values_list('id', flat=True)

    # Nombre total de détails de planning
    total_details = PlanningDetail.objects.filter(planning_id__in=planning_ids).count()

    # Montants recettes et avances (via designation.type_avance_caissiere)
    details_with_designation = PlanningDetail.objects.filter(
        planning_id__in=planning_ids
    ).select_related('designation')

    montant_recettes = Decimal('0.00')
    montant_avances = Decimal('0.00')

    for detail in details_with_designation:
        if detail.designation and detail.designation.type_avance_caissiere:
            type_avance = detail.designation.type_avance_caissiere.lower() if detail.designation.type_avance_caissiere else ''
            if type_avance == 'recette':
                montant_recettes += Decimal(str(detail.montant or 0))
            elif type_avance == 'avance':
                montant_avances += Decimal(str(detail.montant or 0))

    plannings_display = _attach_fiche_poste_display(
        plannings.prefetch_related('details__deplacement__point_a', 'details__deplacement__point_b')
    )
    for planning in plannings_display:
        try:
            participant_ids = [str(p.employee_id) for p in planning.planning_employees.all()]
        except Exception:
            participant_ids = []
        planning.participants_ids_csv = ','.join(participant_ids)
        planning.can_adjust_validation = can_user_adjust_planning_validation(request.user, planning)
        _annotate_planning_execution_meta(planning)
        planning.deplacement_summaries = [
            detail
            for detail in planning.details.all()
            if getattr(detail, 'deplacement_detail', None)
        ]

    employes_qs = Employe.objects.filter(
        date_debauchage__isnull=True
    ).select_related('base', 'poste').order_by(
        'base__nom_base', 'poste__nom_poste', 'nom', 'prenom'
    )
    employes_qs = _filter_employes_by_scope(employes_qs, request.user)

    # Filtre employe : limite a l'organisation de l'utilisateur, meme pour les
    # portees "all" (directeur / superuser) qui couvrent plusieurs organisations.
    employes_filter_qs = employes_qs
    user_base = getattr(getattr(request.user, 'employe', None), 'base', None)
    user_organisation_id = getattr(user_base, 'organisation_id', None)
    if user_organisation_id:
        employes_filter_qs = employes_qs.filter(base__organisation_id=user_organisation_id)

    return render(request, 'planning/planning_list.html', {
        'plannings': plannings_display,
        'title': 'Plannings',
        'employe': request.employe,
        'default_filters_applied': default_filters_applied,
        'selected_mois': selected_mois,
        'selected_employe_filter': selected_employe_filter,
        'total_details': total_details,
        'montant_recettes': montant_recettes,
        'montant_avances': montant_avances,
        'activites': TypeActivite.objects.all().order_by('nomtype'),
        'fiches_poste': FichePoste.objects.filter(dans_planning=True).select_related('type_activites').order_by('tache'),
        'ouvrages': Ouvrage.objects.all().order_by('nom_ouvrage'),
        'employes': employes_qs,
        'employes_filter': employes_filter_qs,
        'is_planning_director': _is_planning_director(request.user),
    })


@employe_required
def planning_consolide(request):
    """Vue consolidée des plannings avec filtres et détails"""
    from django.db.models import Sum
    from datetime import datetime
    from apps.organization.models import Organisation

    plannings = Planning.objects.select_related(
        'employe', 'ouvrage', 'type_activite', 'fiche_poste'
    ).prefetch_related(
        'details__designation__compte',
        'details__equipement_constitutif',
        'details__point_eau',
        'details__point_a',
        'details__point_b',
        'bons_livraison__designation',
        'bons_livraison__equipement',
        'bons_livraison__point_eau'
    )
    plannings = _filter_plannings_by_scope(plannings, request.user)

    # Filtres
    organisation_filter = request.GET.get('organisation', 'all')
    if organisation_filter and organisation_filter != 'all':
        plannings = plannings.filter(employe__base__organisation_id=organisation_filter)

    date_debut = request.GET.get('date_debut')
    if date_debut:
        try:
            plannings = plannings.filter(date__date__gte=datetime.strptime(date_debut, "%Y-%m-%d").date())
        except Exception:
            pass

    date_fin = request.GET.get('date_fin')
    if date_fin:
        try:
            plannings = plannings.filter(date__date__lte=datetime.strptime(date_fin, "%Y-%m-%d").date())
        except Exception:
            pass

    ouvrage_id = request.GET.get('ouvrage')
    if ouvrage_id:
        plannings = plannings.filter(ouvrage_id=ouvrage_id)
    else:
        ouvrage_search = request.GET.get('ouvrage_search')
        if ouvrage_search:
            plannings = plannings.filter(ouvrage__nom_ouvrage__icontains=ouvrage_search)

    employe_id = request.GET.get('employe')
    if employe_id:
        plannings = plannings.filter(employe_id=employe_id)

    activite_search = request.GET.get('activite_search')
    if activite_search:
        plannings = plannings.filter(fiche_poste__tache__icontains=activite_search)

    plannings = plannings.order_by('-date')

    # Attacher fiche_poste_display pour le template
    plannings_display = _attach_fiche_poste_display(plannings)
    for planning in plannings_display:
        planning.fiche_poste_display = getattr(planning, '_fiche_poste_display', '') or ''

    planning_ids = [p.id for p in plannings_display]
    details_avances = PlanningDetail.objects.filter(
        planning_id__in=planning_ids,
        designation__type_avance_caissiere='Avance'
    )

    total_plannings = len(plannings_display)
    total_details = details_avances.count()
    montant_avances = details_avances.aggregate(total=Sum('montant'))['total'] or 0
    total_bons_livraison = BonLivraison.objects.filter(planning_id__in=planning_ids).count()

    employes_qs = Employe.objects.filter(
        date_debauchage__isnull=True
    ).select_related('base', 'poste').order_by(
        'base__nom_base', 'poste__nom_poste', 'nom', 'prenom'
    )
    employes_qs = _filter_employes_by_scope(employes_qs, request.user)

    context = {
        'plannings': plannings_display,
        'total_plannings': total_plannings,
        'total_details': total_details,
        'total_bons_livraison': total_bons_livraison,
        'montant_avances': montant_avances,
        'organisations': Organisation.objects.all().order_by('nom_organisation'),
        'organisation_filter': organisation_filter,
        'ouvrages': Ouvrage.objects.all().order_by('nom_ouvrage'),
        'employes': employes_qs,
        'activites': FichePoste.objects.all().order_by('tache'),
    }
    return render(request, 'planning/planning_consolide.html', context)


@employe_required
def planning_create(request):
    return views_simple.planning_form_page(request)

@employe_required
def planning_update(request, pk):
    return views_simple.planning_form_page(request, planning_id=pk)

@employe_required
def planning_delete(request, pk):
    from django.shortcuts import get_object_or_404
    planning = get_object_or_404(Planning, id=pk)
    planning.delete()
    return redirect('planning:dashboard')


@employe_required
def planning_detail(request, pk):
    return views_simple.planning_form_page(request, planning_id=pk)

@api_view(['GET'])
def planning_data_api(request):
    """API pour r??cup??rer les donn??es de planning avec filtres"""
    if not request.user.is_authenticated:
        return Response({'error': 'Utilisateur non authentifie'}, status=status.HTTP_401_UNAUTHORIZED)
    if not hasattr(request.user, 'employe') or not request.user.employe:
        return Response({'error': 'Compte non associe a un employe'}, status=status.HTTP_403_FORBIDDEN)

    filter_serializer = PlanningFilterSerializer(data=request.GET)
    if not filter_serializer.is_valid():
        return Response(filter_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    filters = filter_serializer.validated_data
    plannings = Planning.objects.select_related(
        'employe', 'employe__poste', 'fiche_poste', 'type_activite', 'ouvrage'
    ).all()
    plannings = _filter_plannings_by_scope(plannings, request.user)

    # Appliquer les filtres
    if filters.get('employe'):
        # Filtrer par employeid (champ existant)
        plannings = plannings.filter(employeid=filters['employe'])

    if filters.get('mois'):
        year, month = filters['mois'].split('-')
        # Filtrer par date
        plannings = plannings.filter(
            Q(date__year=int(year), date__month=int(month))
        )

    if filters.get('ouvrage'):
        # Filtrer par ouvrage_id (champ existant)
        plannings = plannings.filter(ouvrage_id=filters['ouvrage'])

    if filters.get('type_activite'):
        plannings = plannings.filter(type_activite_id=filters['type_activite'])

    if filters.get('activite'):
        plannings = plannings.filter(fiche_poste_id=filters['activite'])

    if filters.get('validation') is not None:
        # Filtrer par estvalide (champ existant)
        plannings = plannings.filter(estvalide=filters['validation'])

    # Ordonner par date
    plannings = plannings.order_by('-date')
    serializer = PlanningSerializer(plannings, many=True)
    return Response(serializer.data)


@api_view(['POST'])
@employe_required
def api_merge_planning_duplicates(request):
    """Fusionner les doublons sur le perimetre planning courant."""
    dry_run = _coerce_merge_duplicate_bool(request.data.get('dry_run'))
    if dry_run is None:
        dry_run = True

    mode = str(request.data.get('mode') or 'activity').strip().lower()
    if mode not in ('strict', 'activity'):
        mode = 'activity'

    raw_filters = request.data.get('filters') or {}
    if not isinstance(raw_filters, dict):
        raw_filters = {}

    scoped_plannings = _get_scoped_plannings_queryset(request.user)
    scoped_plannings = _apply_dashboard_merge_filters(scoped_plannings, raw_filters)
    scoped_plannings = scoped_plannings.order_by('date', 'created_at', 'id')

    planning_list = list(scoped_plannings)
    grouped_plannings = {}
    for planning in planning_list:
        group_key = _build_duplicate_merge_group_key(planning, mode=mode)
        if not group_key:
            continue
        grouped_plannings.setdefault(group_key, []).append(planning)

    total_groups = 0
    total_duplicates = 0
    total_valides = 0
    total_non_valides = 0
    total_details = 0
    total_bons = 0
    total_paiements = 0
    total_pieces = 0
    total_participants = 0
    total_photos_added = 0

    for grouped_items in grouped_plannings.values():
        if len(grouped_items) <= 1:
            continue

        primary = next((item for item in grouped_items if item.estvalide), None) or grouped_items[0]
        duplicates = [item for item in grouped_items if item.id != primary.id]
        if not duplicates:
            continue

        duplicate_ids = [duplicate.id for duplicate in duplicates]
        total_groups += 1
        total_duplicates += len(duplicate_ids)

        details_count = PlanningDetail.objects.filter(planning_id__in=duplicate_ids).count()
        bons_count = BonLivraison.objects.filter(planning_id__in=duplicate_ids).count()
        paiements_count = PaiementForfaitaire.objects.filter(planning_id__in=duplicate_ids).count()
        pieces_count = PlanningPiece.objects.filter(planning_id__in=duplicate_ids).count()

        total_details += details_count
        total_bons += bons_count
        total_paiements += paiements_count
        total_pieces += pieces_count

        duplicate_owner_ids = [duplicate.employe_id for duplicate in duplicates if duplicate.employe_id]
        duplicate_participant_ids = list(
            PlanningEmploye.objects.filter(planning_id__in=duplicate_ids).values_list('employee_id', flat=True)
        )
        existing_participant_ids = list(
            PlanningEmploye.objects.filter(planning_id=primary.id).values_list('employee_id', flat=True)
        )
        participants_to_add = views_simple._build_new_secondary_participant_ids(
            primary,
            '',
            [*duplicate_owner_ids, *duplicate_participant_ids],
            existing_participant_ids=existing_participant_ids,
        )
        total_participants += len(participants_to_add)

        initial_photo_count = len(views_simple._parse_planning_photo_payload(primary.photo))
        merged_photo_payload = views_simple._merge_planning_photo_payloads(
            primary.photo,
            [duplicate.photo for duplicate in duplicates],
        )
        merged_photo_count = len(views_simple._parse_planning_photo_payload(merged_photo_payload))
        total_photos_added += max(0, merged_photo_count - initial_photo_count)

        if dry_run:
            continue

        with transaction.atomic():
            if details_count:
                PlanningDetail.objects.filter(planning_id__in=duplicate_ids).update(planning=primary)
            if bons_count:
                BonLivraison.objects.filter(planning_id__in=duplicate_ids).update(planning=primary)
            if paiements_count:
                PaiementForfaitaire.objects.filter(planning_id__in=duplicate_ids).update(planning=primary)
            if pieces_count:
                PlanningPiece.objects.filter(planning_id__in=duplicate_ids).update(planning=primary)
            if participants_to_add:
                PlanningEmploye.objects.bulk_create(
                    [PlanningEmploye(planning_id=primary.id, employee_id=emp_id) for emp_id in participants_to_add],
                    ignore_conflicts=True
                )

            primary.updated_at = timezone.now()
            update_fields = ['updated_at']
            if merged_photo_payload != (primary.photo or ''):
                primary.photo = merged_photo_payload
                update_fields.append('photo')
            primary.save(update_fields=update_fields)

            Planning.objects.filter(id__in=duplicate_ids).delete()

    return Response({
        'dry_run': dry_run,
        'mode': mode,
        'scanned_plannings': len(planning_list),
        'groups': total_groups,
        'duplicates': total_duplicates,
        'participants_added': total_participants,
        'details_moved': total_details,
        'bons_moved': total_bons,
        'paiements_moved': total_paiements,
        'pieces_moved': total_pieces,
        'photos_added': total_photos_added,
    })




@api_view(["POST"])
@employe_required
def api_planning_bulk_update(request):
    """Met a jour en masse les plannings affiches."""
    try:
        body = request.data if hasattr(request, "data") else {}
        planning_ids = body.get("planning_ids") or []
        updates = body.get("updates") or {}
        if not planning_ids:
            return Response({"success": False, "error": "Aucun planning_id"}, status=400)

        qs = Planning.objects.filter(id__in=planning_ids)
        if "employe_id" in updates and updates["employe_id"]:
            qs.update(employe_id=updates["employe_id"])
        if "fiche_poste_id" in updates and updates["fiche_poste_id"]:
            qs.update(fiche_poste_id=updates["fiche_poste_id"])
        if "ouvrage_id" in updates and updates["ouvrage_id"]:
            qs.update(ouvrage_id=updates["ouvrage_id"])
        if "date" in updates and updates["date"]:
            # date attendue YYYY-MM-DD
            qs.update(date=updates["date"])

        # Participants (optionnel) : appliquer a chaque planning
        participants_ids = updates.get("participants_ids")
        if participants_ids is not None:
            if not isinstance(participants_ids, list):
                participants_ids = []
            for planning in qs:
                PlanningEmploye.objects.filter(planning=planning).delete()
                for emp_id in participants_ids:
                    if emp_id and str(emp_id) != str(planning.employe_id or ''):
                        PlanningEmploye.objects.get_or_create(planning=planning, employee_id=emp_id)

        return Response({"success": True, "count": qs.count()})
    except Exception as e:
        return Response({"success": False, "error": str(e)}, status=500)


@api_view(['POST'])
@employe_required
def api_planning_fast_update(request, planning_id):
    """Mise a jour rapide d'un planning (fiche, employe, participants, ouvrage, date)."""
    try:
        planning = get_object_or_404(Planning, id=planning_id)
        body = request.data if hasattr(request, "data") else {}

        fiche_poste_id = body.get('fiche_poste_id')
        employe_id = body.get('employe_id')
        ouvrage_id = body.get('ouvrage_id')
        date_str = body.get('date')
        participants_ids = body.get('participants_ids')

        updates = False

        if fiche_poste_id:
            fiche = get_object_or_404(FichePoste, id=fiche_poste_id)
            planning.fiche_poste = fiche
            if fiche.type_activites:
                planning.type_activite = fiche.type_activites
            updates = True

        if employe_id:
            employe = get_object_or_404(Employe, id=employe_id)
            planning.employe = employe
            updates = True

        if ouvrage_id:
            ouvrage = get_object_or_404(Ouvrage, id=ouvrage_id)
            planning.ouvrage = ouvrage
            updates = True

        if date_str:
            try:
                planning.date = datetime.strptime(date_str, "%Y-%m-%d").date()
                updates = True
            except Exception:
                return Response({'success': False, 'error': 'Date invalide'}, status=400)

        if participants_ids is not None:
            if not isinstance(participants_ids, list):
                participants_ids = []
            PlanningEmploye.objects.filter(planning=planning).delete()
            for emp_id in participants_ids:
                if emp_id and str(emp_id) != str(planning.employe_id or ''):
                    PlanningEmploye.objects.get_or_create(planning=planning, employee_id=emp_id)
            updates = True

        if not updates:
            return Response({'success': False, 'error': 'Aucune valeur a mettre a jour'}, status=400)

        planning.save()

        return Response({
            'success': True,
            'new_display': planning.fiche_poste.tache if planning.fiche_poste else '',
            'new_type': planning.type_activite.nomtype if planning.type_activite else ''
        })
    except Exception as e:
        return Response({'success': False, 'error': str(e)}, status=500)

@api_view(['GET'])
@employe_required
def api_frequence_check(request):
    """Controle des frequences (placeholder si non disponible)."""
    return Response({'missing': []})

@employe_required
def planning_clear_all(request):
    """Supprimer tous les plannings.

    SÉCURITÉ : POST uniquement et superutilisateur. Auparavant un simple GET de n'importe quel
    employé (lien, favori, préchargement du navigateur) supprimait l'intégralité des plannings.
    """
    if request.method != 'POST' or not request.user.is_superuser:
        messages.error(request, "Suppression de tous les plannings refusée (réservée à un superutilisateur, par formulaire).")
        return redirect('planning:dashboard')
    Planning.objects.all().delete()
    messages.success(request, "Tous les plannings ont ete supprimes.")
    return redirect('planning:dashboard')

@api_view(['GET'])
@permission_classes([AllowAny])
def planning_stats_api(request):
    """API pour récupérer les statistiques de planning avec filtres"""
    import logging
    logger = logging.getLogger(__name__)

    logger.info(f"=== API STATS APPELÃ‰E ===")
    logger.info(f"GET params: {dict(request.GET)}")

    filter_serializer = PlanningFilterSerializer(data=request.GET)
    if not filter_serializer.is_valid():
        logger.error(f"Validation errors: {filter_serializer.errors}")
        return Response(filter_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    filters = filter_serializer.validated_data
    logger.info(f"Validated filters: {filters}")

    if not request.user.is_authenticated:
        return Response({'error': 'Utilisateur non authentifie'}, status=status.HTTP_401_UNAUTHORIZED)
    if not hasattr(request.user, 'employe') or not request.user.employe:
        return Response({'error': 'Compte non associe a un employe'}, status=status.HTTP_403_FORBIDDEN)

    plannings = _filter_plannings_by_scope(Planning.objects.all(), request.user)
    logger.info(f"Total plannings avant filtres: {len(plannings)}")

    # Appliquer les mÃªmes filtres que planning_data_api
    if filters.get('employe'):
        employe_id = filters['employe']
        plannings = plannings.filter(
            Q(employe_id=employe_id) | Q(planning_employees__employee_id=employe_id)
        ).distinct()
        logger.info(f"Après filtre employe: {len(plannings)}")

    if filters.get('mois'):
        year, month = filters['mois'].split('-')
        plannings = plannings.filter(
            Q(date__year=int(year), date__month=int(month))
        )
        logger.info(f"Après filtre mois: {len(plannings)}")

    if filters.get('ouvrage'):
        plannings = plannings.filter(ouvrage_id=filters['ouvrage'])
        logger.info(f"Après filtre ouvrage: {len(plannings)}")

    if filters.get('type_activite'):
        plannings = plannings.filter(type_activite_id=filters['type_activite'])
        logger.info(f"Après filtre type_activite: {len(plannings)}")

    if filters.get('activite'):
        plannings = plannings.filter(fiche_poste_id=filters['activite'])
        logger.info(f"Après filtre activite: {len(plannings)}")

    # NE PAS appliquer le filtre validation car on veut toujours compter les validés/non validés
    # mÃªme si l'utilisateur filtre par statut de validation
    # Le filtre validation sert uniquement Ã  filtrer les données du tableau, pas les stats globales

    # Calculer les statistiques sur le queryset filtré (sauf validation)
    total = len(plannings)
    valides = plannings.filter(estvalide=True).count()
    non_valides = plannings.filter(estvalide=False).count()

    # Compter les employés uniques (chef + participants)
    employes_uniques = Employe.objects.filter(
        Q(plannings__in=plannings) | Q(planning_participations__planning__in=plannings)
    ).distinct().count()

    # Compter les ouvrages uniques (seulement ceux qui ont des équipements ou des points d'eau)
    from django.db.models import Exists, OuterRef
    from apps.infrastructure.models import EquipementConstitutif
    from apps.billing.models import PointEau

    # Sous-requÃªtes pour vérifier si l'ouvrage a des équipements ou points d'eau
    has_equipements = EquipementConstitutif.objects.filter(ouvrage=OuterRef('ouvrage'))
    has_points_eau = PointEau.objects.filter(ouvrage=OuterRef('ouvrage'))

    ouvrages_uniques = plannings.filter(
        ouvrage__isnull=False
    ).filter(
        Q(Exists(has_equipements)) | Q(Exists(has_points_eau))
    ).values('ouvrage').distinct().count()

    logger.info(f"Statistiques finales: total={total}, valides={valides}, non_valides={non_valides}")

    stats = {
        'total': total,
        'valides': valides,
        'non_valides': non_valides,
        'employes_uniques': employes_uniques,
        'ouvrages_uniques': ouvrages_uniques,
        'taux_validation': int(round((valides / total * 100) if total > 0 else 0))
    }

    logger.info(f"Stats calculées: {stats}")

    return Response(stats)


@api_view(['GET'])
def planning_details_api(request, planning_id):
    """API pour récupérer les détails d'un planning ET les bons de livraison"""
    try:
        if not request.user.is_authenticated:
            return Response({'error': 'Utilisateur non authentifie'}, status=status.HTTP_401_UNAUTHORIZED)
        if not hasattr(request.user, 'employe') or not request.user.employe:
            return Response({'error': 'Compte non associe a un employe'}, status=status.HTTP_403_FORBIDDEN)
        _filter_plannings_by_scope(Planning.objects.all(), request.user).get(id=planning_id)
        return views_simple.planning_details_api_simple(request, planning_id)
        planning = _filter_plannings_by_scope(Planning.objects.all(), request.user).get(id=planning_id)

        # Récupérer les détails (SANS les recettes)
        details = PlanningDetail.objects.filter(
            planning=planning
        ).exclude(
            designation__type_avance_caissiere='Recette'
        ).select_related(
            'designation',
            'designation__type_designation',
            'compte',
            'equipement_constitutif',
            'point_eau',
            'point_a',
            'point_b'
        )

        # Récupérer les bons de livraison
        bons_livraison = BonLivraison.objects.filter(
            planning=planning
        ).select_related(
            'designation',
            'point_eau',
            'equipement'
        )

        # Sérialiser les détails
        details_serializer = PlanningDetailSerializer(details, many=True)

        # Sérialiser les bons de livraison (manuellement car pas de serializer)
        bons_data = []
        for bon in bons_livraison:
            bons_data.append({
                'id': str(bon.id),
                'designation': bon.designation.nom if bon.designation else '',
                'quantite': float(bon.quantite),
                'magasin': bon.magasin or '',
                'equipement': bon.equipement.nom if bon.equipement else '',
                'point_eau': bon.point_eau.code_point_eau if bon.point_eau else '',
                'utilise': bon.utilise,
                'date_utilisation': bon.date_utilisation.strftime('%d/%m/%Y') if bon.date_utilisation else '',
                'retour': bon.retour,
                'date_retour': bon.date_retour.strftime('%d/%m/%Y') if bon.date_retour else '',
                'numero_bon': bon.numero_bon or ''
            })

        return Response({
            'details': details_serializer.data,
            'bons_livraison': bons_data
        })
    except Planning.DoesNotExist:
        return Response({'error': 'Planning non trouvé'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
def planning_validate_api(request, planning_id):
    """API pour valider un planning (réservé au directeur)"""
    # Vérifier que l'utilisateur est directeur
    if request.user.is_authenticated and hasattr(request.user, 'employe'):
        poste_nom = request.user.employe.poste.nom_poste if request.user.employe.poste else ''
        est_directeur = poste_nom in ['Directeur', 'Directrice', 'Directeur General', 'Directeur adjoint']

        if not est_directeur:
            return Response({
                'error': 'Accès refusé. Seul le directeur peut valider les plannings.'
            }, status=status.HTTP_403_FORBIDDEN)
    else:
        return Response({
            'error': 'Utilisateur non authentifié'
        }, status=status.HTTP_401_UNAUTHORIZED)

    try:
        planning = Planning.objects.get(id=planning_id)

        # Si le planning a un ouvrage, rediriger vers la page de validation avec historique
        if planning.ouvrage:
            return Response({
                'error': 'Ce planning a un ouvrage. Veuillez passer par la page de validation pour voir l\'historique de l\'ouvrage.',
                'redirect_url': f'/plannings/validation/{planning_id}/'
            }, status=status.HTTP_400_BAD_REQUEST)

        planning.validation = True
        planning.save()
        return Response({'message': 'Planning validé avec succès'})
    except Planning.DoesNotExist:
        return Response({'error': 'Planning non trouvé'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
def employees_api(request):
    """API pour récupérer la liste des employés"""
    employees_qs = views_simple._get_scoped_employees_queryset(request.user).select_related('poste', 'base')
    data = [
        {
            'id': str(emp.id),
            'nom': emp.nom or '',
            'prenom': emp.prenom or '',
            'surnom': emp.surnom or '',
            'display_name': emp.surnom or emp.nom_complet or emp.nom or '',
        }
        for emp in employees_qs.order_by('surnom', 'nom', 'prenom')
    ]
    return Response(data)


@api_view(['GET'])
def ouvrages_api(request):
    """API pour récupérer la liste des ouvrages/infrastructures"""
    ouvrages = Ouvrage.objects.all().order_by('nom_ouvrage')
    serializer = OuvrageSimpleSerializer(ouvrages, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def types_activites_api(request):
    """API pour récupérer les types d'activités"""
    types = TypeActivite.objects.filter(is_active=True).order_by('nom')
    serializer = TypeActiviteSerializer(types, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def activites_postes_api(request):
    """API pour récupérer les activités de poste par type"""
    type_activite_id = request.GET.get('type_activite')
    activites = ActivitePoste.objects.filter(is_active=True)
    
    if type_activite_id:
        activites = activites.filter(type_activite_id=type_activite_id)
    
    activites = activites.order_by('nom')
    serializer = ActivitePosteSerializer(activites, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def available_months_api(request):
    """API pour récupérer les mois disponibles dans les plannings"""
    # Récupérer les mois du champ date existant
    months = Planning.objects.filter(date__isnull=False).dates('date', 'month', order='DESC')
    
    # Convertir en liste
    month_list = []
    for month in months:
        month_list.append({
            'value': month.strftime('%Y-%m'),
            'label': month.strftime('%B %Y').capitalize()
        })
    return Response(month_list)


class PlanningCreateAPI(generics.CreateAPIView):
    """API pour créer un nouveau planning"""
    queryset = Planning.objects.all()
    serializer_class = PlanningCreateSerializer


class PlanningUpdateAPI(generics.UpdateAPIView):
    """API pour modifier un planning (restreint si validé)"""
    queryset = Planning.objects.all()
    serializer_class = PlanningCreateSerializer
    lookup_field = 'id'

    def update(self, request, *args, **kwargs):
        instance = self.get_object()

        # Si le planning est validé, autoriser uniquement la modification de date et employé
        if instance.estvalide:
            # Liste des champs autorisés pour un planning validé
            champs_autorises = ['date', 'employe', 'employe_id']

            # Vérifier si des champs non autorisés sont modifiés
            for key in request.data.keys():
                if key not in champs_autorises:
                    from rest_framework.exceptions import PermissionDenied
                    raise PermissionDenied(
                        f'Un planning validé ne peutêtre modifié que pour la date et l\'employé. '
                        f'Le champ "{key}" ne peut pasêtre modifié.'
                    )

        return super().update(request, *args, **kwargs)


class PlanningDeleteAPI(generics.DestroyAPIView):
    """API pour supprimer un planning (interdit si validé)"""
    queryset = Planning.objects.all()
    lookup_field = 'id'

    def perform_destroy(self, instance):
        # EmpÃªcher la suppression des plannings validés
        if instance.estvalide:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('Impossible de supprimer un planning validé.')
        instance.delete()

def test_buttons(request):
    """Page de test pour les boutons"""
    return render(request, 'planning/test_buttons.html')


def debug_view(request):
    """Page de debug pour diagnostiquer les problèmes d'affichage"""
    return render(request, 'planning/debug.html')


def planning_calendar(request):
    """Vue calendrier des plannings avec cartes interactives"""
    # Vérifier si l'utilisateur est directeur
    est_directeur = _is_planning_director(request.user)

    context = {
        'title': 'Planning Calendrier',
        'est_directeur': est_directeur,
    }
    context.update(_get_planning_validation_ui_context(request.user))
    return render(request, 'planning/planning_calendar.html', context)

@employe_required
def planning_agenda(request):
    """Vue agenda mobile-first pour la consultation et la saisie des plannings."""
    est_directeur = _is_planning_director(request.user)
    default_employe_id = ''

    if not est_directeur and getattr(request.user, 'employe', None):
        default_employe_id = str(request.user.employe.id)

    return render(request, 'planning/planning_agenda.html', {
        'title': 'Agenda Planning',
        'est_directeur': est_directeur,
        'default_employe_id': default_employe_id,
    })


@employe_required
def planning_cloture_mensuelle_page(request):
    """Page de cloture mensuelle par employe pour rapprocher tout le mois."""
    raw_next_url = (request.GET.get('next') or request.POST.get('next') or '').strip()
    next_url = ''
    if raw_next_url and url_has_allowed_host_and_scheme(
        raw_next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure()
    ):
        next_url = raw_next_url

    filters = _resolve_planning_cloture_filters(
        request.user,
        request.POST if request.method == 'POST' else request.GET,
    )
    mois_value = filters['mois_value']
    selected_employe_id = filters['employe_value']

    try:
        mois_date = datetime.strptime(mois_value, '%Y-%m')
        mois_value = mois_date.strftime('%Y-%m')
    except ValueError:
        mois_value = _get_default_planning_month_value()
        mois_date = datetime.strptime(mois_value, '%Y-%m')

    employes_qs = Employe.objects.filter(
        date_debauchage__isnull=True
    ).select_related('base', 'poste').order_by(
        'base__nom_base', 'poste__nom_poste', 'nom', 'prenom'
    )
    employes_qs = _filter_employes_by_scope(employes_qs, request.user)
    selected_employe = employes_qs.filter(id=selected_employe_id).first() if selected_employe_id else None

    monthly_queryset = _get_scoped_plannings_queryset(request.user).prefetch_related(
        'details__designation',
        'planning_employees__employee',
    )
    if selected_employe:
        monthly_queryset = monthly_queryset.filter(
            employe_id=selected_employe.id,
            date__year=mois_date.year,
            date__month=mois_date.month,
        )
    else:
        monthly_queryset = monthly_queryset.none()

    monthly_plannings = _attach_fiche_poste_display(monthly_queryset.order_by('date', 'id'))
    for planning in monthly_plannings:
        _annotate_planning_execution_meta(planning)
        planning.activity_label = _get_planning_activity_label(planning) or planning.activite_display
        planning.is_blocked_activity = _is_planning_cloture_blocked(planning)
        planning.monthly_cloture_selected_status = _get_planning_monthly_cloture_selected_status(planning)
        planning.report_date_input_value = ''

    if request.method == 'POST' and selected_employe:
        skipped_blocked_count = 0
        for planning in monthly_plannings:
            if planning.is_blocked_activity:
                skipped_blocked_count += 1
        actions, validation_errors = _prepare_monthly_cloture_actions(monthly_plannings, request.POST)

        if validation_errors:
            messages.error(request, ' '.join(validation_errors))
        else:
            closure_summary = _apply_monthly_cloture_actions(actions)
            message_parts = [
                f"{closure_summary['termine']} activite(s) terminee(s)",
                f"{closure_summary['annule']} activite(s) supprimee(s)",
                f"{closure_summary['reporte']} activite(s) reportee(s)",
            ]
            message = 'Cloture mensuelle enregistree: ' + ', '.join(message_parts) + '.'
            if skipped_blocked_count:
                message += f' {skipped_blocked_count} ligne(s) geree(s) par un autre module non modifiee(s).'
            messages.success(request, message)

            query_params = {'employe': selected_employe_id, 'mois': mois_value}
            if next_url:
                query_params['next'] = next_url
            return redirect(f"{reverse('planning:cloture_mensuelle_page')}?{urlencode(query_params)}")

    month_summary = {
        'total': len(monthly_plannings),
        'termine': sum(1 for item in monthly_plannings if item.statut == 'termine'),
        'en_cours': sum(1 for item in monthly_plannings if (item.statut or 'en_cours') == 'en_cours'),
        'reporte': sum(1 for item in monthly_plannings if item.statut == 'reporte'),
        'annule': sum(1 for item in monthly_plannings if item.statut == 'annule'),
        'bloquees': sum(1 for item in monthly_plannings if item.is_blocked_activity),
    }

    context = {
        'title': 'Cloture mensuelle',
        'employes': employes_qs,
        'selected_employe': selected_employe,
        'selected_employe_id': selected_employe_id,
        'mois_value': mois_value,
        'monthly_plannings': monthly_plannings,
        'month_summary': month_summary,
        'closure_status_choices': PLANNING_MONTHLY_CLOTURE_CHOICES,
        'next_url': next_url,
    }
    return render(request, 'planning/planning_cloture_mensuelle.html', context)


@employe_required
def planning_cloture_page(request, planning_id):
    """Page de cloture terrain et de rapprochement avec le planning papier."""
    raw_next_url = (request.GET.get('next') or request.POST.get('next') or '').strip()
    next_url = ''
    if raw_next_url and url_has_allowed_host_and_scheme(
        raw_next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure()
    ):
        next_url = raw_next_url

    planning = get_object_or_404(
        _get_scoped_plannings_queryset(request.user).prefetch_related(
            'details__designation',
            'planning_employees__employee',
        ),
        id=planning_id,
    )
    _annotate_planning_execution_meta(planning)

    current_url = reverse('planning:cloture_page', args=[planning.id])
    if next_url:
        current_url = f"{current_url}?{urlencode({'next': next_url})}"

    activite_label = _get_planning_activity_label(planning)
    is_blocked_activity = _is_planning_cloture_blocked(planning)

    same_month_queryset = _get_scoped_plannings_queryset(request.user)
    if planning.employe_id:
        same_month_queryset = same_month_queryset.filter(
            employe_id=planning.employe_id,
            date__year=planning.date.year,
            date__month=planning.date.month,
        )
    else:
        same_month_queryset = same_month_queryset.filter(id=planning.id)

    same_month_plannings = _attach_fiche_poste_display(
        same_month_queryset.order_by('date', 'id')
    )
    for monthly_planning in same_month_plannings:
        _annotate_planning_execution_meta(monthly_planning)
        monthly_planning.is_current = monthly_planning.id == planning.id

    month_summary = {
        'total': len(same_month_plannings),
        'termine': sum(1 for item in same_month_plannings if item.statut == 'termine'),
        'reporte': sum(1 for item in same_month_plannings if item.statut == 'reporte'),
        'annule': sum(1 for item in same_month_plannings if item.statut == 'annule'),
        'papier_conforme': sum(1 for item in same_month_plannings if item.verification == 'papier_conforme'),
        'papier_ecart': sum(1 for item in same_month_plannings if item.verification == 'papier_ecart'),
    }

    details = PlanningDetail.objects.filter(planning=planning).select_related('designation')
    total_montant = sum([Decimal(str(detail.montant or 0)) for detail in details], Decimal('0'))

    if request.method == 'POST':
        if is_blocked_activity:
            messages.error(
                request,
                f'La cloture de "{activite_label}" se gere depuis son module dedie.'
            )
            return redirect(current_url)

        allowed_statuts = {choice[0] for choice in Planning.STATUS_CHOICES}
        statut = (request.POST.get('statut') or planning.statut or 'en_cours').strip()
        if statut not in allowed_statuts:
            messages.error(request, 'Statut terrain invalide.')
            return redirect(current_url)

        verification = (request.POST.get('verification') or '').strip()
        allowed_verifications = {choice[0] for choice in PLANNING_PAPER_VERIFICATION_CHOICES if choice[0]}
        if verification and verification not in allowed_verifications:
            messages.error(request, 'Verdict papier invalide.')
            return redirect(current_url)

        planning.statut = statut
        planning.verification = verification
        planning.commentaire_verification = (request.POST.get('commentaire_verification') or '').strip()
        planning.bilan = (request.POST.get('bilan') or '').strip()
        planning.suiteadonner = (request.POST.get('suiteadonner') or '').strip()

        if request.POST.get('ajuster_validation') == '1' and _is_planning_director(request.user):
            planning.estvalide = verification == 'papier_conforme'

        planning.save()

        status_label = dict(Planning.STATUS_CHOICES).get(statut, statut)
        paper_label = _get_planning_paper_label(verification)
        if request.POST.get('ajuster_validation') == '1' and _is_planning_director(request.user):
            validation_label = 'Planning valide' if planning.estvalide else 'Planning non valide'
            messages.success(
                request,
                f'Cloture enregistree: {status_label}. Controle papier: {paper_label}. {validation_label}.'
            )
        else:
            messages.success(
                request,
                f'Cloture enregistree: {status_label}. Controle papier: {paper_label}.'
            )
        return redirect(current_url)

    context = {
        'planning': planning,
        'details': details,
        'total_montant': total_montant,
        'same_month_plannings': same_month_plannings,
        'month_summary': month_summary,
        'status_choices': Planning.STATUS_CHOICES,
        'paper_verification_choices': PLANNING_PAPER_VERIFICATION_CHOICES[1:],
        'can_adjust_validation': _is_planning_director(request.user),
        'is_blocked_activity': is_blocked_activity,
        'activite_label': activite_label or planning.activite_display,
        'next_url': next_url,
        'month_reference': planning.date.strftime('%m/%Y') if planning.date else '',
        'monthly_cloture_url': (
            f"{reverse('planning:cloture_mensuelle_page')}?{urlencode({'employe': planning.employe_id, 'mois': planning.date.strftime('%Y-%m')})}"
            if planning.date and planning.employe_id else reverse('planning:cloture_mensuelle_page')
        ),
        'title': 'Cloture de planning',
    }
    return render(request, 'planning/planning_cloture.html', context)


@employe_required
def planning_validation_page(request, planning_id):
    """Page de validation d'un planning avec historique complet de l'ouvrage"""
    from django.utils import timezone

    raw_next_url = (request.GET.get('next') or request.POST.get('next') or '').strip()
    next_url = ''
    # Accepter les URLs relatives (commençant par '/') ou validées par Django
    if raw_next_url:
        if raw_next_url.startswith('/') or url_has_allowed_host_and_scheme(
            raw_next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure()
        ):
            next_url = raw_next_url

    # Récupérer le planning
    planning = get_object_or_404(Planning, id=planning_id)

    can_adjust_validation = can_user_adjust_planning_validation(request.user, planning)
    if not can_adjust_validation:
        messages.error(
            request,
            "Acces refuse. Vous pouvez seulement valider ou devalider les plannings de vos subordonnes directs ou indirects. Le directeur peut aussi valider son propre planning."
        )
        return redirect(next_url or reverse('planning:list'))

    # URL de retour vers cette mÃªme page (POST-Redirect-GET) en conservant "next"
    self_validation_url = reverse('planning:validation_page', args=[planning.id])
    if next_url:
        self_validation_url = f"{self_validation_url}?{urlencode({'next': next_url})}"

    # BLOQUER la validation/modification de congés et permissions
    activites_bloquees = ['Congé', 'Congé demi-journée', 'Permission']
    activite_label = planning.fiche_poste.tache if planning.fiche_poste else ''
    if activite_label in activites_bloquees:
        messages.error(request, f'La validation et modification de "{activite_label}" est bloquée. Ces activités sont gérées via le module "Demandes de Congés".')
        return redirect(next_url or reverse('planning:dashboard'))

    # Note: On permet maintenant d'accéder Ã  la page mÃªme si validé (pour dévalider)

    # Récupérer l'historique complet de l'ouvrage (plannings passés et futurs)
    historique_plannings = Planning.objects.filter(
        ouvrage=planning.ouvrage
    ).select_related(
        'employe', 'type_activite', 'fiche_poste', 'ouvrage'
    ).prefetch_related(
        'details__designation'
    ).order_by('-date')

    # Séparer en passé et futur
    plannings_passes = historique_plannings.filter(date__lt=planning.date)
    plannings_futurs = historique_plannings.filter(date__gt=planning.date)

    # Récupérer les détails du planning actuel
    details = PlanningDetail.objects.filter(planning=planning).select_related('designation')

    # Calculer le total des montants
    from decimal import Decimal
    total_montant = sum([Decimal(str(detail.montant or 0)) for detail in details])

    # Traitement du formulaire de validation
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'valider':
            planning.estvalide = True
            planning.date_validation = timezone.now()
            planning.validateur = request.user.employe
            planning.updatedat = timezone.now()
            planning.save()

            ouvrage_info = f' pour {planning.ouvrage.nom_ouvrage}' if planning.ouvrage else ''
            messages.success(request, f'Planning du {planning.date}{ouvrage_info} validé avec succès!')
            return redirect(self_validation_url)

        elif action == 'devalider':
            planning.estvalide = False
            planning.date_validation = None
            planning.validateur = None
            planning.updatedat = timezone.now()
            planning.save()

            ouvrage_info = f' pour {planning.ouvrage.nom_ouvrage}' if planning.ouvrage else ''
            messages.success(request, f'Planning du {planning.date}{ouvrage_info} dévalidé avec succès! Vous pouvez maintenant le modifier.')
            return redirect(self_validation_url)

        elif action == 'rejeter':
            commentaire_rejet = request.POST.get('commentaire_rejet', '')
            messages.warning(request, 'Planning rejeté. Retour Ã  la liste.')
            return redirect(next_url or reverse('planning:dashboard'))

    context = {
        'planning': planning,
        'details': details,
        'total_montant': total_montant,
        'plannings_passes': plannings_passes,
        'plannings_futurs': plannings_futurs,
        'ouvrage': planning.ouvrage,
        'next_url': next_url,
        'can_adjust_validation': can_adjust_validation,
        'title': f'Validation Planning - {planning.ouvrage.nom_ouvrage if planning.ouvrage else "Sans ouvrage"}',
    }

    return render(request, 'planning/planning_validation.html', context)


def test_grid(request):
    """Page de test pour la grille CSS"""
    return render(request, 'planning/test_grid.html')


# ViewSets hiérarchiques avec filtrage par role

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from django.conf import settings
from .serializers import (
    PlanningHierarchicalSerializer, PlanningEmployeHierarchicalSerializer,
    IndemniteHierarchicalSerializer, PlanningDetailHierarchicalSerializer
)


class BaseHierarchicalPlanningViewSet(viewsets.ModelViewSet):
    """
    Classe de base pour tous les ViewSets Planning avec filtrage hiérarchique.
    Implémente la logique commune de filtrage selon le role de l'utilisateur.
    """
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Filtre dynamiquement le queryset basé sur le role de l'utilisateur.
        - Les postes standards voient les données de leur organisation.
        - Les postes Ã  privilèges voient les données de toute leur organisation.
        """
        user = self.request.user

        if not user.is_authenticated:
            return self.get_base_queryset().none()

        # Vérification si l'utilisateur a un profil employé
        if not hasattr(user, 'employee_profile') or not user.employee_profile:
            # Si pas de profil employé, limiter l'accès (par défaut, accès restreint)
            return self.get_base_queryset().none()

        profile = user.employee_profile

        # Si le poste de l'utilisateur est dans la liste des roles Ã  privilèges
        if profile.poste and profile.poste.poste_name in settings.ROLES_NIVEAU_ORGANISATION:
            # On filtre par l'organisation de l'utilisateur
            return self.filter_by_organization(profile.organization)
        else:
            # Sinon, on applique le filtrage standard par organisation
            return self.filter_by_organization(profile.organization)

    def get_base_queryset(self):
        """Retourne le queryset de base pour ce ViewSet. Ã€ surcharger dans les sous-classes."""
        return self.queryset

    def filter_by_organization(self, organization):
        """Filtre les données par organisation. Ã€ surcharger dans les sous-classes."""
        raise NotImplementedError("Cette méthode doitêtre implémentée dans les sous-classes.")


class PlanningHierarchicalViewSet(BaseHierarchicalPlanningViewSet):
    serializer_class = PlanningHierarchicalSerializer
    queryset = Planning.objects.all()

    def get_base_queryset(self):
        return Planning.objects.select_related('employe', 'ouvrage', 'activite')

    def filter_by_organization(self, organization):
        # Filtrage par organisation via l'employé du planning
        return Planning.objects.filter(employe__organization=organization)

    def perform_create(self, serializer):
        """
        Assigne l'employé responsable du planning.
        Pour un employé standard, il ne peut créer que ses propres plannings.
        Pour un directeur, il peut assigner d'autres employés de son organisation.
        """
        user = self.request.user
        if not hasattr(user, 'employee_profile') or not user.employee_profile:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Utilisateur non associé Ã  un profil employé.")
        
        profile = user.employee_profile

        if profile.poste and profile.poste.poste_name in settings.ROLES_NIVEAU_ORGANISATION:
            # Le directeur peut créer des plannings pour d'autres employés
            # L'employé sera validé par le serializer
            serializer.save()
        else:
            # L'employé standard ne peut créer que ses propres plannings
            serializer.save(
                employe=profile,
                employeid=profile.id
            )


class PlanningEmployeHierarchicalViewSet(BaseHierarchicalPlanningViewSet):
    serializer_class = PlanningEmployeHierarchicalSerializer
    queryset = PlanningEmploye.objects.all()

    def get_base_queryset(self):
        return PlanningEmploye.objects.select_related('planning', 'employee')

    def filter_by_organization(self, organization):
        # Filtrage par organisation via l'employé participant
        return PlanningEmploye.objects.filter(employee__organization=organization)

    def perform_create(self, serializer):
        """
        Crée une participation au planning.
        """
        serializer.save()


class IndemniteHierarchicalViewSet(BaseHierarchicalPlanningViewSet):
    serializer_class = IndemniteHierarchicalSerializer
    queryset = Indemnite.objects.all()

    def get_base_queryset(self):
        return Indemnite.objects.select_related('employee', 'planning')

    def filter_by_organization(self, organization):
        # Filtrage par organisation via l'employé
        return Indemnite.objects.filter(employee__organization=organization)

    def perform_create(self, serializer):
        """
        Assigne l'employé concerné par l'indemnité.
        Pour un employé standard, il ne peut créer que ses propres indemnités.
        Pour un directeur, il peut créer des indemnités pour ses employés.
        """
        user = self.request.user
        if not hasattr(user, 'employee_profile') or not user.employee_profile:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Utilisateur non associé Ã  un profil employé.")
        
        profile = user.employee_profile

        if profile.poste and profile.poste.poste_name in settings.ROLES_NIVEAU_ORGANISATION:
            # Le directeur peut créer des indemnités pour d'autres employés
            # L'employé sera validé par le serializer
            serializer.save()
        else:
            # L'employé standard ne peut créer que ses propres indemnités
            serializer.save(employee=profile)


class PlanningDetailHierarchicalViewSet(BaseHierarchicalPlanningViewSet):
    serializer_class = PlanningDetailHierarchicalSerializer
    queryset = PlanningDetail.objects.all()

    def get_base_queryset(self):
        return PlanningDetail.objects.select_related('planning')

    def filter_by_organization(self, organization):
        # Filtrage par organisation via l'employé du planning
        return PlanningDetail.objects.filter(planning__employe__organization=organization)

    def perform_create(self, serializer):
        """
        Crée un détail de planning.
        """
        serializer.save()


@api_view(['GET'])
@api_view(['GET'])
@api_view(['GET'])
def api_employes_list(request):
    """API pour recuperer la liste des employes pour le selecteur de PDF"""
    try:
        if not request.user.is_authenticated or not hasattr(request.user, 'employe') or not request.user.employe:
            return JsonResponse({'employes': []})

        employes = Employe.objects.filter(date_debauchage__isnull=True)
        employes = _filter_employes_by_scope(employes, request.user)
        employes = employes.order_by('surnom', 'nom', 'prenom')
        data = {
            'employes': [
                {
                    'id': str(emp.id),
                    'display_name': emp.surnom or emp.nom_affichage or emp.prenom or emp.nom or ''
                }
                for emp in employes
            ]
        }
        return JsonResponse(data)
    except Exception:
        return JsonResponse({'employes': []})


def print_planning_pdf(request):
    """Génère un PDF A4 du planning consolidé d'un employé pour un mois donné (validés uniquement)"""
    from django.http import HttpResponse
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas
    from io import BytesIO
    from decimal import Decimal

    # Classe pour ajouter en-tÃªte et pied de page
    class NumberedCanvas(canvas.Canvas):
        def __init__(self, *args, **kwargs):
            self.organisation_name = kwargs.pop('organisation_name', '')
            canvas.Canvas.__init__(self, *args, **kwargs)
            self._saved_page_states = []

        def showPage(self):
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            num_pages = len(self._saved_page_states)
            for state in self._saved_page_states:
                self.__dict__.update(state)
                self.draw_page_decorations(num_pages)
                canvas.Canvas.showPage(self)
            canvas.Canvas.save(self)

        def draw_page_decorations(self, page_count):
            self.saveState()
            # En-tÃªte avec logo organisation
            self.setFont('Helvetica-Bold', 10)
            self.drawString(2*cm, A4[1] - 1*cm, self.organisation_name)

            # Pied de page avec numéro de page
            self.setFont('Helvetica', 9)
            page_num = f"Page {self._pageNumber} / {page_count}"
            self.drawCentredString(A4[0] / 2, 0.75*cm, page_num)
            self.restoreState()

    # Récupérer les paramètres
    employe_id = request.GET.get('employe')
    mois_str = request.GET.get('mois')  # Format: YYYY-MM
    print_mode = (request.GET.get('print_mode') or 'all').strip().lower()
    include_all_statuses = print_mode == 'all'
    include_validated = print_mode != 'non_validated'

    if not employe_id or not mois_str:
        return HttpResponse("Paramètres manquants", status=400)

    try:
        employe = Employe.objects.get(id=employe_id)
        year, month = map(int, mois_str.split('-'))
    except (Employe.DoesNotExist, ValueError):
        return HttpResponse("Employé ou mois invalide", status=400)

    if not request.user.is_authenticated or not hasattr(request.user, 'employe') or not request.user.employe:
        return HttpResponse("Acces refuse", status=403)

    allowed_employes = _filter_employes_by_scope(Employe.objects.filter(id=employe_id), request.user)
    if not allowed_employes.exists():
        return HttpResponse("Acces refuse", status=403)

    # Récupérer les plannings validés (SANS filtrer par date en SQL - timezone!)
    import pytz
    from django.db.models import Prefetch
    from django.utils import timezone as dj_timezone

    tz_madagascar = pytz.timezone('Indian/Antananarivo')

    # Récupérer tous les plannings de l'employé validés
    all_plannings = Planning.objects.filter(
        employe_id=employe_id,
    )
    if not include_all_statuses:
        planning_status_filter = Q(estvalide=True) if include_validated else (Q(estvalide=False) | Q(estvalide__isnull=True))
        all_plannings = all_plannings.filter(planning_status_filter)

    all_plannings = all_plannings.prefetch_related(
        Prefetch('details', queryset=PlanningDetail.objects.exclude(
            designation__type_avance_caissiere='Recette'
        ).select_related(
            'designation',
            'equipement_constitutif',
            'point_eau',
            'deplacement__point_a',
            'deplacement__point_b'
        )),
        Prefetch('bons_livraison', queryset=BonLivraison.objects.select_related(
            'designation', 'point_eau', 'equipement'
        )),
        Prefetch('paiements_forfaitaires', queryset=PaiementForfaitaire.objects.select_related(
            'point_eau', 'point_eau__ouvrage'
        ))
    ).select_related('employe', 'ouvrage', 'type_activite', 'fiche_poste').order_by('date')

    # Filtrer par mois EN PYTHON après conversion timezone
    plannings = []
    for planning in all_plannings:
        if planning.date:
            # Convertir en timezone Madagascar
            date_aware = planning.date if planning.date.tzinfo else dj_timezone.make_aware(planning.date)
            date_madagascar = date_aware.astimezone(tz_madagascar)
            date_obj = date_madagascar.date()

            # Filtrer par année et mois
            if date_obj.year == year and date_obj.month == month:
                plannings.append(planning)

    plannings_display = _attach_fiche_poste_display(plannings)
    for planning in plannings_display:
        try:
            participant_ids = [str(p.employee_id) for p in planning.planning_employees.all()]
        except Exception:
            participant_ids = []
        planning.participants_ids_csv = ','.join(participant_ids)

    # Créer le PDF en mode portrait
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=1*cm, leftMargin=1*cm,
                           topMargin=1.5*cm, bottomMargin=1.5*cm)

    elements = []
    styles = getSampleStyleSheet()

    # Style pour le titre
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=14,
        textColor=colors.HexColor('#1e40af'),
        spaceAfter=10,
        alignment=TA_CENTER
    )

    # Style pour le sous-titre
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#374151'),
        spaceAfter=8,
        alignment=TA_CENTER
    )

    # Style pour texte petit
    small_style = ParagraphStyle(
        'Small',
        parent=styles['Normal'],
        fontSize=7,
        leading=8
    )

    # Titre du document
    month_names = ['', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
                   'Juillet', 'AoÃ»t', 'Septembre', 'Octobre', 'Novembre', 'Décembre']
    titre = Paragraph(f"Planning validé - {month_names[month]} {year}", title_style)
    if not include_validated:
        titre = Paragraph(f"Planning non validé - {month_names[month]} {year}", title_style)
    titre = Paragraph(f"Planning mensuel - {month_names[month]} {year}", title_style)
    elements.append(titre)

    # Informations employé
    employe_info = Paragraph(f"Employé: <b>{employe.surnom or employe.prenom} {employe.nom}</b>", subtitle_style)
    elements.append(employe_info)

    # Calculer les statistiques globales (SANS recettes)
    total_valides = 0
    total_non_valides = 0
    total_details = 0
    total_bons = 0
    montant_avances = Decimal('0.00')
    total_paiements_forfaitaires = 0
    montant_forfaitaires = Decimal('0.00')

    for planning in plannings:
        if planning.estvalide is True:
            total_valides += 1
        else:
            total_non_valides += 1
        for detail in planning.details.all():
            total_details += 1
            montant_avances += Decimal(str(detail.montant or 0))
        total_bons += planning.bons_livraison.count()
        for paiement in planning.paiements_forfaitaires.all():
            total_paiements_forfaitaires += 1
            montant_forfaitaires += Decimal(str(paiement.montant or 0))

    montant_global = montant_avances + montant_forfaitaires
    stats_text = (
        f"Plannings: <b>{len(plannings)}</b> | Valides: <b>{total_valides}</b> | Non valides: <b>{total_non_valides}</b> | Avances: <b>{total_details}</b> | "
        f"Bons: <b>{total_bons}</b> | Forfaitaires: <b>{total_paiements_forfaitaires}</b> | "
        f"Total: <b>{montant_global:,.0f} Ar</b>"
    )
    stats_info = Paragraph(stats_text, subtitle_style)
    elements.append(stats_info)
    elements.append(Spacer(1, 12))

    if not plannings:
        no_data = Paragraph("Aucun planning validé pour cette période", styles['Normal'])
        elements.append(no_data)
    else:
        # Parcourir chaque planning
        for planning in plannings:
            # Convertir la date en timezone Madagascar pour l'affichage
            date_aware = planning.date if planning.date.tzinfo else dj_timezone.make_aware(planning.date)
            date_madagascar = date_aware.astimezone(tz_madagascar)
            date_display = date_madagascar.strftime('%d/%m/%Y')

            # Tableau des infos du planning (en haut) - sans en-tÃªte
            planning_status_label = 'Valide' if planning.estvalide is True else 'Non valide'
            planning_data = [[
                date_display,
                planning.ouvrage.nom_ouvrage if planning.ouvrage else 'N/A',
                planning.type_activite.nomtype if planning.type_activite else 'N/A',
                planning.fiche_poste.tache if planning.fiche_poste else 'N/A',
                planning_status_label
            ]]

            planning_info_table = Table(planning_data, colWidths=[2.6*cm, 4.8*cm, 3.5*cm, 4.8*cm, 2.3*cm])
            planning_info_table.setStyle(TableStyle([
                # Style pour les infos planning (sans fond, sans gras)
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ]))

            elements.append(planning_info_table)

            # Tableau des détails (en bas) - seulement si des détails existent
            if planning.details.exists():
                details_data = [[
                    'Désignation', 'Type', 'Qté', 'P.U.', 'Montant',
                    'Acheteur', 'Equipement', 'Pt Eau', 'Trajet', 'Transport'
                ]]

                for detail in planning.details.all():
                    # Type (Avance uniquement, recettes exclues)
                    type_badge = 'Av' if detail.designation and detail.designation.type_avance_caissiere == 'Avance' else '-'

                    # Déplacement via table séparée PlanningDetailDeplacement
                    deplacement = getattr(detail, 'deplacement_detail', None)

                    # Trajet
                    trajet_text = '-'
                    if deplacement and detail.trajet:
                        pt_a = detail.point_a.nom_village if detail.point_a else '-'
                        pt_b = detail.point_b.nom_village if detail.point_b else '-'
                        trajet_label = detail.get_trajet_display() if hasattr(detail, 'get_trajet_display') else ''
                        trajet_text = f"{pt_a} -> {pt_b}"
                        if trajet_label:
                            trajet_text = f"{trajet_text} ({trajet_label})"

                    # Moyen de transport
                    transport_text = '-'
                    if deplacement and detail.moyen_transport:
                        transport_text = detail.get_moyen_transport_display()

                    planning_date_text = planning.date.strftime('%Y-%m-%d') if planning.date else ''
                    employe_text = planning.employe.surnom if planning.employe and planning.employe.surnom else (planning.employe.prenom if planning.employe and planning.employe.prenom else '-')
                    ouvrage_text = planning.ouvrage.nom_ouvrage if planning.ouvrage else '-'

                    details_data.append([
                        Paragraph(detail.designation.nom if detail.designation else '-', small_style),
                        type_badge,
                        f"{detail.quantity:.1f}" if detail.quantity else '0',
                        f"{detail.pu:,.0f}" if detail.pu else '0',
                        f"{detail.montant:,.0f}" if detail.montant else '0',
                        Paragraph(detail.acheteur[:15] if detail.acheteur else '-', small_style),
                        Paragraph(detail.equipement_constitutif.nom[:15] if detail.equipement_constitutif else '-', small_style),
                        str(detail.point_eau.code_point_eau) if detail.point_eau and detail.point_eau.code_point_eau else '-',
                        Paragraph(trajet_text[:20], small_style),
                        Paragraph(transport_text[:10], small_style)
                    ])

                details_table = Table(details_data, colWidths=[
                    3.5*cm, 0.6*cm, 0.8*cm, 1*cm, 1.2*cm,  # Détails base
                    1.8*cm, 1.8*cm, 0.8*cm, 2.2*cm, 1.2*cm  # Autres détails (sans Magasin)
                ])

                details_table.setStyle(TableStyle([
                    # En-tÃªte
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#059669')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 6),
                    ('TOPPADDING', (0, 0), (-1, 0), 2),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 2),
                    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),

                    # Corps du tableau - padding minimal
                    ('FONTSIZE', (0, 1), (-1, -1), 6),
                    ('TOPPADDING', (0, 1), (-1, -1), 1),
                    ('BOTTOMPADDING', (0, 1), (-1, -1), 1),
                    ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
                    ('ALIGN', (2, 1), (4, -1), 'RIGHT'),  # Qté, P.U., Montant alignés Ã  droite
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),

                    # Grille
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),

                    # Alternance de couleurs
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0fdf4')])
                ]))

                elements.append(details_table)

            # Tableau des bons de livraison - seulement si des bons existent
            if planning.bons_livraison.exists():
                elements.append(Spacer(1, 0.2*cm))

                # Titre bons de livraison
                bons_title_style = ParagraphStyle(
                    'BonsTitle',
                    parent=styles['Normal'],
                    fontSize=7,
                    textColor=colors.HexColor('#059669'),
                    spaceAfter=2
                )
                bons_title = Paragraph(f"<b>Bons de Livraison ({planning.bons_livraison.count()})</b>", bons_title_style)
                elements.append(bons_title)

                bons_data = [[
                    'Désignation', 'Qté', 'Magasin', 'Equipement', 'Pt Eau', 'Livré', 'Retourné', 'N° Bon'
                ]]

                for bon in planning.bons_livraison.all():
                    # Statut livraison
                    livraison_text = 'Oui' if bon.utilise else 'Non'
                    if bon.date_utilisation:
                        date_util_aware = bon.date_utilisation if bon.date_utilisation.tzinfo else dj_timezone.make_aware(bon.date_utilisation)
                        date_util_mg = date_util_aware.astimezone(tz_madagascar)
                        livraison_text += f" ({date_util_mg.strftime('%d/%m')})"

                    # Statut retour
                    retour_text = 'Oui' if bon.retour else 'Non'
                    if bon.date_retour:
                        date_retour_aware = bon.date_retour if bon.date_retour.tzinfo else dj_timezone.make_aware(bon.date_retour)
                        date_retour_mg = date_retour_aware.astimezone(tz_madagascar)
                        retour_text += f" ({date_retour_mg.strftime('%d/%m')})"

                    bons_data.append([
                        Paragraph(bon.designation.nom if bon.designation else '-', small_style),
                        f"{bon.quantite:.1f}" if bon.quantite else '0',
                        Paragraph(bon.magasin[:12] if bon.magasin else '-', small_style),
                        Paragraph(bon.equipement.nom[:12] if bon.equipement else '-', small_style),
                        str(bon.point_eau.code_point_eau) if bon.point_eau and bon.point_eau.code_point_eau else '-',
                        livraison_text,
                        retour_text,
                        Paragraph(bon.numero_bon[:10] if bon.numero_bon else '-', small_style)
                    ])

                bons_table = Table(bons_data, colWidths=[
                    3.5*cm, 0.8*cm, 1.5*cm, 1.8*cm, 0.8*cm, 1.8*cm, 1.8*cm, 1.5*cm
                ])

                bons_table.setStyle(TableStyle([
                    # En-tÃªte
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#10b981')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 6),
                    ('TOPPADDING', (0, 0), (-1, 0), 2),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 2),
                    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),

                    # Corps du tableau
                    ('FONTSIZE', (0, 1), (-1, -1), 6),
                    ('TOPPADDING', (0, 1), (-1, -1), 1),
                    ('BOTTOMPADDING', (0, 1), (-1, -1), 1),
                    ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
                    ('ALIGN', (1, 1), (1, -1), 'RIGHT'),  # Qté alignée Ã  droite
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),

                    # Grille
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),

                    # Alternance de couleurs
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#ecfdf5')])
                ]))

                elements.append(bons_table)

            if planning.paiements_forfaitaires.exists():
                elements.append(Spacer(1, 0.2*cm))

                forfait_title_style = ParagraphStyle(
                    'ForfaitTitle',
                    parent=styles['Normal'],
                    fontSize=7,
                    textColor=colors.HexColor('#15803d'),
                    spaceAfter=2
                )
                forfait_title = Paragraph(
                    f"<b>Paiements forfaitaires ({planning.paiements_forfaitaires.count()})</b>",
                    forfait_title_style,
                )
                elements.append(forfait_title)

                forfait_data = [[
                    "Point d'eau", 'Date facture', 'Qte', 'P.U.', 'Montant', 'Statut', 'Date paiement', 'Validite'
                ]]

                for paiement in planning.paiements_forfaitaires.all():
                    point_label = _get_paiement_forfaitaire_point_label(getattr(paiement, 'point_eau', None))
                    statut_label = 'Pointe' if paiement.est_paye else 'Non pointe'
                    date_paiement_label = _format_planning_print_date(
                        getattr(paiement, 'effective_payment_date', None),
                        tz_madagascar,
                    )
                    validite_label = _format_paiement_forfaitaire_validity(paiement)

                    forfait_data.append([
                        Paragraph(str(point_label)[:36], small_style),
                        _format_planning_print_date(getattr(paiement, 'date_facture', None), tz_madagascar),
                        str(getattr(paiement, 'quantite', 0) or 0),
                        f"{getattr(paiement, 'prix_unitaire', 0) or 0:,.0f}",
                        f"{getattr(paiement, 'montant', 0) or 0:,.0f}",
                        statut_label,
                        date_paiement_label,
                        Paragraph(validite_label[:30], small_style),
                    ])

                forfait_table = Table(forfait_data, colWidths=[
                    4.1*cm, 1.8*cm, 0.8*cm, 1.2*cm, 1.4*cm, 1.7*cm, 2.0*cm, 3.0*cm
                ])

                forfait_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#16a34a')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 6),
                    ('TOPPADDING', (0, 0), (-1, 0), 2),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 2),
                    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),

                    ('FONTSIZE', (0, 1), (-1, -1), 6),
                    ('TOPPADDING', (0, 1), (-1, -1), 1),
                    ('BOTTOMPADDING', (0, 1), (-1, -1), 1),
                    ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
                    ('ALIGN', (2, 1), (4, -1), 'RIGHT'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0fdf4')]),
                ]))

                elements.append(forfait_table)

            # Petit espace entre les plannings
            elements.append(Spacer(1, 0.3*cm))

    # Récupérer le nom de l'organisation
    organisation_name = ''
    if employe.base and employe.base.organisation:
        organisation_name = employe.base.organisation.nom_organisation

    # Générer le PDF avec canvas personnalisé
    doc.build(elements, canvasmaker=lambda *args, **kwargs: NumberedCanvas(
        *args, **{**kwargs, 'organisation_name': organisation_name}
    ))
    buffer.seek(0)

    # Retourner le PDF
    response = HttpResponse(buffer, content_type='application/pdf')
    filename = (
        f"planning_mensuel_{employe.surnom or employe.nom}_{month_names[month]}_{year}.pdf"
        if include_all_statuses
        else (
            f"planning_consolide_{employe.surnom or employe.nom}_{month_names[month]}_{year}.pdf"
            if include_validated
            else f"planning_non_valide_{employe.surnom or employe.nom}_{month_names[month]}_{year}.pdf"
        )
    )
    response['Content-Disposition'] = f'inline; filename="{filename}"'

    return response


@login_required
def print_fiche_temps(request):
    """Impression fiche temps mensuelle d'un employé, agrégée à une ligne par date."""
    import pytz
    from django.http import HttpResponse
    from django.utils import timezone as dj_timezone

    employe_id = request.GET.get('employe')
    mois_str = request.GET.get('mois')

    if not employe_id or not mois_str:
        return HttpResponse("Parametres manquants", status=400)

    try:
        employe = Employe.objects.select_related('base', 'base__organisation').get(id=employe_id)
        year, month = map(int, mois_str.split('-'))
    except (Employe.DoesNotExist, ValueError):
        return HttpResponse("Employe ou mois invalide", status=400)

    if not request.user.is_authenticated or not hasattr(request.user, 'employe') or not request.user.employe:
        return HttpResponse("Acces refuse", status=403)

    allowed_employes = _filter_employes_by_scope(Employe.objects.filter(id=employe_id), request.user)
    if not allowed_employes.exists():
        return HttpResponse("Acces refuse", status=403)

    tz_madagascar = pytz.timezone('Indian/Antananarivo')
    all_plannings = Planning.objects.filter(
        employe_id=employe_id,
        estvalide=include_validated
    ).select_related(
        'employe', 'ouvrage', 'type_activite', 'fiche_poste'
    ).order_by('date', 'id')

    grouped_rows = {}
    for planning in all_plannings:
        if not planning.date:
            continue

        date_aware = planning.date if planning.date.tzinfo else dj_timezone.make_aware(planning.date)
        local_date = date_aware.astimezone(tz_madagascar).date()
        if local_date.year != year or local_date.month != month:
            continue

        row = grouped_rows.setdefault(local_date, {
            'date': local_date,
            'activites': [],
            'ouvrages': [],
            'remarques': [],
            'has_ouvrage': False,
            'is_ferie_planning': False,
        })

        activite_label = ''
        if getattr(planning, 'fiche_poste', None) and planning.fiche_poste.tache:
            activite_label = planning.fiche_poste.tache.strip()
        elif getattr(planning, 'type_activite', None) and planning.type_activite.nomtype:
            activite_label = planning.type_activite.nomtype.strip()

        if activite_label and activite_label not in row['activites']:
            row['activites'].append(activite_label)

        if planning.ouvrage and planning.ouvrage.nom_ouvrage:
            ouvrage_nom = planning.ouvrage.nom_ouvrage.strip()
            if ouvrage_nom and ouvrage_nom not in row['ouvrages']:
                row['ouvrages'].append(ouvrage_nom)
            row['has_ouvrage'] = True

        remarque = (planning.remarque or '').strip()
        if remarque and remarque not in row['remarques']:
            row['remarques'].append(remarque)

        normalized_activity = unicodedata.normalize('NFKD', activite_label or '').encode('ascii', 'ignore').decode('ascii').lower()
        if 'jour ferie' in normalized_activity:
            row['is_ferie_planning'] = True

    month_names = ['', 'Janvier', 'Fevrier', 'Mars', 'Avril', 'Mai', 'Juin',
                   'Juillet', 'Aout', 'Septembre', 'Octobre', 'Novembre', 'Decembre']
    week_days_fr = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']

    fiche_rows = []
    jours_travailles = 0
    for local_date in sorted(grouped_rows.keys()):
        row = grouped_rows[local_date]
        is_ferie_officiel = views_simple.is_jour_ferie_malgache(local_date)
        is_ferie = is_ferie_officiel or row['is_ferie_planning']
        if row['has_ouvrage']:
            jours_travailles += 1

        fiche_rows.append({
            'date': local_date,
            'date_display': local_date.strftime('%d/%m/%Y'),
            'jour_semaine': week_days_fr[local_date.weekday()],
            'activites': ' / '.join(row['activites']) if row['activites'] else '-',
            'ouvrages': ' / '.join(row['ouvrages']) if row['ouvrages'] else '-',
            'remarques': ' | '.join(row['remarques']) if row['remarques'] else '-',
            'is_ferie': is_ferie,
            'is_weekend': local_date.weekday() == 6,
            'has_ouvrage': row['has_ouvrage'],
        })

    _, last_day = monthrange(year, month)
    jours_ouvres = 0
    jours_feries = 0
    for day in range(1, last_day + 1):
        current_date = date(year, month, day)
        is_ferie = views_simple.is_jour_ferie_malgache(current_date)
        if is_ferie:
            jours_feries += 1
            continue
        if current_date.weekday() != 6:
            jours_ouvres += 1

    context = {
        'title': 'Fiche temps',
        'employe': employe,
        'mois': mois_str,
        'mois_label': f"{month_names[month]} {year}",
        'organisation_name': getattr(getattr(employe, 'base', None), 'organisation', None).nom_organisation if getattr(getattr(employe, 'base', None), 'organisation', None) else '',
        'generated_at': timezone.localtime(),
        'rows': fiche_rows,
        'stats': {
            'jours_travailles': jours_travailles,
            'jours_ouvres': jours_ouvres,
            'jours_feries': jours_feries,
        }
    }
    return render(request, 'planning/fiche_temps_print.html', context)


# ========== EXPORT / IMPORT EXCEL ==========

def export_excel_plannings(request):
    """Export des plannings en Excel - Version consolidée avec détails si employé et mois fournis"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from django.http import HttpResponse
    from decimal import Decimal
    from django.db.models import Prefetch
    from django.utils import timezone

    # Vérifier si c'est un export consolidé (employé + mois)
    employe_id = request.GET.get('employe')
    mois_str = request.GET.get('mois')  # Format: YYYY-MM

    # Créer le workbook
    wb = Workbook()
    ws = wb.active

    # Mode consolidé avec détails
    if employe_id and mois_str:
        ws.title = "Planning Consolidé"

        try:
            employe = Employe.objects.get(id=employe_id)
            year, month = map(int, mois_str.split('-'))
        except (Employe.DoesNotExist, ValueError):
            # Si erreur, retourner export simple
            return export_simple_plannings(wb, ws)

        if not request.user.is_authenticated or not hasattr(request.user, 'employe') or not request.user.employe:
            return export_simple_plannings(wb, ws)
        if not _filter_employes_by_scope(Employe.objects.filter(id=employe_id), request.user).exists():
            return export_simple_plannings(wb, ws)

        # Récupérer les plannings validés (filtrage par mois sera fait après conversion timezone)
        plannings_all = Planning.objects.filter(
            employe_id=employe_id,
            estvalide=True
        ).prefetch_related(
            Prefetch('details', queryset=PlanningDetail.objects.select_related(
                'designation',
                'equipement_constitutif',
                'point_eau',
                'deplacement__point_a',
                'deplacement__point_b'
            ))
        ).select_related('employe', 'ouvrage', 'type_activite', 'fiche_poste').order_by('date')
        # Filtrer par mois en Python après conversion timezone
        import pytz
        tz_madagascar = pytz.timezone('Indian/Antananarivo')
        plannings = []
        for p in plannings_all:
            date_aware = p.date if p.date.tzinfo else timezone.make_aware(p.date)
            date_madagascar = date_aware.astimezone(tz_madagascar)
            date_obj = date_madagascar.date()

            # Vérifier si la date (en timezone Madagascar) correspond au mois filtré
            if date_obj.year == year and date_obj.month == month:
                # Ajouter la date convertie comme attribut temporaire pour l'export
                p._date_madagascar = date_madagascar
                plannings.append(p)

        plannings_display = _attach_fiche_poste_display(plannings)
        for planning in plannings_display:
            try:
                participant_ids = [str(p.employee_id) for p in planning.planning_employees.all()]
            except Exception:
                participant_ids = []
            planning.participants_ids_csv = ','.join(participant_ids)

        # Calculer les statistiques
        total_details = 0
        montant_recettes = Decimal('0.00')
        montant_avances = Decimal('0.00')
        montant_total = Decimal('0.00')

        for planning in plannings:
            for detail in planning.details.all():
                total_details += 1
                montant_total += Decimal(str(detail.montant or 0))
                if detail.designation and detail.designation.type_avance_caissiere:
                    type_avance = detail.designation.type_avance_caissiere.lower()
                    if type_avance == 'recette':
                        montant_recettes += Decimal(str(detail.montant or 0))
                    elif type_avance == 'avance':
                        montant_avances += Decimal(str(detail.montant or 0))

        # En-tÃªte du document
        month_names = ['', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
                       'Juillet', 'AoÃ»t', 'Septembre', 'Octobre', 'Novembre', 'Décembre']

        ws.append([f"Planning Consolidé - {month_names[month]} {year}"])
        ws.append([f"Employé: {employe.surnom or employe.prenom} {employe.nom}"])
        ws.append([f"Plannings: {len(plannings)} | Détails: {total_details} | Total: {montant_total:,.0f} Ar | Recettes: {montant_recettes:,.0f} Ar | Avances: {montant_avances:,.0f} Ar"])
        ws.append([])  # Ligne vide

        # Style pour les titres
        title_font = Font(bold=True, size=14, color="1E40AF")
        ws['A1'].font = title_font
        ws['A2'].font = Font(bold=True, size=11)
        ws['A3'].font = Font(size=10)

        # Styles pour les tableaux
        header_fill = PatternFill(start_color="374151", end_color="374151", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF", size=9)
        planning_header_fill = PatternFill(start_color="DBEAFE", end_color="DBEAFE", fill_type="solid")
        planning_header_font = Font(bold=True, size=10)
        border_thin = Border(left=Side(style='thin'), right=Side(style='thin'),
                            top=Side(style='thin'), bottom=Side(style='thin'))

        current_row = 5

        # Pour chaque planning
        for planning in plannings:
            # En-tÃªte du planning (utiliser la date Madagascar convertie)
            date_display = planning._date_madagascar.strftime('%d/%m/%Y') if hasattr(planning, '_date_madagascar') else planning.date.strftime('%d/%m/%Y')
            ws.append([f"Date: {date_display} | Ouvrage: {planning.ouvrage.nom_ouvrage if planning.ouvrage else 'Aucun ouvrage'} | Type: {planning.type_activite.nomtype if planning.type_activite else 'N/A'} | Activité: {planning.fiche_poste.tache if planning.fiche_poste else 'N/A'}"])
            ws[f'A{current_row}'].font = planning_header_font
            ws[f'A{current_row}'].fill = planning_header_fill
            current_row += 1

            # Si le planning a des détails
            if planning.details.exists():
                # En-tÃªtes du tableau de détails
                detail_headers = [
                    'Date planning', 'Surnom employé', 'Ouvrage',
                    'Désignation', 'Type', 'Qté', 'P.U.', 'Montant',
                    'Acheteur', 'Compte', 'Fournisseur', 'Equipement',
                    "Point d'eau", 'Trajet', 'Transport'
                ]
                ws.append(detail_headers)

                for col_idx, cell in enumerate(ws[current_row], start=1):
                    cell.fill = header_fill
                    cell.font = header_font
                    cell.alignment = Alignment(horizontal='center')
                    cell.border = border_thin

                current_row += 1

                # Données des détails
                for detail in planning.details.all():
                    # Type (Recette/Avance)
                    type_badge = '-'
                    if detail.designation and detail.designation.type_avance_caissiere:
                        if detail.designation.type_avance_caissiere.lower() == 'recette':
                            type_badge = 'Recette'
                        elif detail.designation.type_avance_caissiere.lower() == 'avance':
                            type_badge = 'Avance'

                    # Trajet
                    trajet_text = '-'
                    if detail.trajet:
                        pt_a = detail.point_a.nom_village if detail.point_a else '-'
                        pt_b = detail.point_b.nom_village if detail.point_b else '-'
                        trajet_text = f"{pt_a} â†’ {pt_b}"

                    # Moyen de transport
                    transport_text = '-'
                    if detail.moyen_transport:
                        transport_text = detail.get_moyen_transport_display()

                    compte_label = ''
                    if detail.compte:
                        compte_label = detail.compte.nom_compte if hasattr(detail.compte, 'nom_compte') else str(detail.compte)

                    fournisseur_label = ''
                    if detail.fournisseur:
                        fournisseur_label = detail.fournisseur.nom if hasattr(detail.fournisseur, 'nom') else str(detail.fournisseur)

                    ws.append([
                        planning_date_text,
                        employe_text,
                        ouvrage_text,
                        detail.designation.nom if detail.designation else '-',
                        type_badge,
                        float(detail.quantity) if detail.quantity else 0,
                        float(detail.pu) if detail.pu else 0,
                        float(detail.montant) if detail.montant else 0,
                        detail.acheteur or '-',
                        compte_label or '-',
                        fournisseur_label or '-',
                        detail.equipement_constitutif.nom if detail.equipement_constitutif else '-',
                        detail.point_eau.nom if detail.point_eau else '-',
                        trajet_text,
                        transport_text
                    ])

                    # Appliquer les bordures
                    for col_idx in range(1, 16):
                        ws.cell(row=current_row, column=col_idx).border = border_thin
                        # Aligner les nombres Ã  droite
                        if col_idx in [6, 7, 8]:  # Qté, P.U., Montant
                            ws.cell(row=current_row, column=col_idx).alignment = Alignment(horizontal='right')

                    current_row += 1

            # Ligne vide entre plannings
            ws.append([])
            current_row += 1

        # Ajuster les largeurs des colonnes
        column_widths = [15, 18, 28, 40, 10, 8, 12, 15, 20, 20, 20, 25, 20, 30, 15]
        for idx, width in enumerate(column_widths, start=1):
            ws.column_dimensions[chr(64 + idx)].width = width

        filename = f"planning_consolide_{employe.surnom or employe.nom}_{month_names[month]}_{year}.xlsx"

    else:
        # Export simple (tous les plannings)
        ws.title = "Plannings"

        # En-tÃªtes
        headers = [
            'ID Planning',
            'Date (YYYY-MM-DD)',
            "Ouvrage (Nom)",
            "Fiche poste (TÃ¢che)",
            "Type d'activité",
            "Employé (Surnom)",
            'Statut',
            'Validé',
            'Remarques',
            'Date Signalement',
            'Vérification',
            'Commentaire Vérification',
            'Débit Mesure',
            'Bilan',
            'Suite Ã  donner',
            'Photos (JSON)',
            'Créé le',
            'Modifié le'
        ]
        ws.append(headers)

        # Style des en-tÃªtes
        header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF")

        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center')

        # Récupérer les plannings avec relations
        plannings = Planning.objects.select_related('ouvrage', 'type_activite', 'fiche_poste', 'employe').all().order_by('-date')

        # Convertir les dates en timezone Madagascar
        import pytz
        tz_madagascar = pytz.timezone('Indian/Antananarivo')

        for planning in plannings:
            # Récupérer le nom de l'ouvrage
            ouvrage_nom = ''
            if planning.ouvrage:
                ouvrage_nom = planning.ouvrage.nom_ouvrage
            elif hasattr(planning, 'ouvrage_nom') and planning.ouvrage_nom:
                ouvrage_nom = planning.ouvrage_nom

            # Récupérer le type d'activité (catégorie générale)
            type_activite_nom = ''
            if planning.type_activite:
                type_activite_nom = planning.type_activite.nomtype

            # Récupérer l'activité spécifique
            activite_nom = ''
            if planning.fiche_poste:
                activite_nom = planning.fiche_poste.tache
            elif hasattr(planning, 'fiche_poste_display') and planning.fiche_poste_display:
                activite_nom = planning.fiche_poste_display

            # Récupérer le surnom de l'employé (priorité au surnom)
            employe_nom = ''
            if planning.employe:
                employe_nom = planning.employe.surnom or planning.employe.prenom or planning.employe.nom_employe

            # Convertir la date en timezone Madagascar pour l'export
            date_str = ''
            if planning.date:
                date_aware = planning.date if planning.date.tzinfo else timezone.make_aware(planning.date)
                date_madagascar = date_aware.astimezone(tz_madagascar)
                date_str = date_madagascar.strftime('%Y-%m-%d')

            date_signalement_str = ''
            if planning.datesignalementactivite:
                date_sig_aware = planning.datesignalementactivite if planning.datesignalementactivite.tzinfo else timezone.make_aware(planning.datesignalementactivite)
                date_sig_mada = date_sig_aware.astimezone(tz_madagascar)
                date_signalement_str = date_sig_mada.strftime('%Y-%m-%d')

            ws.append([
                str(planning.id),
                date_str,
                ouvrage_nom,
                activite_nom,
                type_activite_nom,
                employe_nom,
                planning.statut or '',
                'Oui' if planning.estvalide else 'Non' if planning.estvalide is not None else '',
                planning.remarque or '',
                date_signalement_str,
                planning.verification or '',
                planning.commentaire_verification or '',
                planning.debitmesure if planning.debitmesure is not None else '',
                planning.bilan or '',
                planning.suiteadonner or '',
                planning.photo or '',
                planning.created_at.strftime('%Y-%m-%d %H:%M') if planning.created_at else '',
                planning.updated_at.strftime('%Y-%m-%d %H:%M') if planning.updated_at else ''
            ])

        # Ajuster les largeurs des colonnes
        for column in ws.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            ws.column_dimensions[column_letter].width = adjusted_width

        filename = 'plannings_export.xlsx'

    # Retourner le fichier
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename={filename}'
    wb.save(response)

    return response


def export_excel_details(request):
    """Export des détails de planning en Excel"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from django.http import HttpResponse

    wb = Workbook()
    ws = wb.active
    ws.title = "Planning Détails"

    # En-tÃªtes - colonnes réelles de PlanningDetail avec IDs
    headers = [
        'ID Détail',
        'ID Planning',
        'Date Planning',
        'Surnom Employé',
        'Ouvrage',
        'Désignation',
        'Quantité',
        'Prix Unitaire',
        'Montant',
        'Acheteur',
        'Compte',
        'ID Equipement Constitutif',
        'ID Point d\'Eau',
        'Trajet',
        'ID Point A',
        'ID Point B',
        'Moyen de Transport',
        'Utilisé',
        'Date Utilisation',
        'ID Fournisseur',
        'Facture Imprimée',
        'Livraison',
        'Date Livraison',
        'Retour',
        'Date Retour',
        'N° Bon Livraison',
        'N° Bon Avance',
        'N° Facture',
        'Numéro DiameX Avance',
        'Base DiameX Avance',
        'Numéro DiameX',
        'Base DiameX',
        'ID Photo Justificatif',
        'Créé le',
        'Modifié le'
    ]
    ws.append(headers)

    # Style des en-tÃªtes
    header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")

    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')

    # Récupérer les détails avec les relations
    details = PlanningDetail.objects.select_related(
        'planning', 'designation', 'compte',
        'equipement_constitutif', 'point_eau',
        'deplacement__point_a', 'deplacement__point_b'
    ).order_by('-created_at')

    for detail in details:
        planning_date = detail.planning.date.strftime('%Y-%m-%d') if detail.planning and detail.planning.date else ''
        employe_surnom = ''
        ouvrage_nom = ''
        if detail.planning:
            if detail.planning.employe:
                employe_surnom = detail.planning.employe.surnom or detail.planning.employe.prenom or detail.planning.employe.nom_employe or ''
            if detail.planning.ouvrage:
                ouvrage_nom = detail.planning.ouvrage.nom_ouvrage

        # Récupérer le nom du compte (au lieu du code)
        compte_nom = ''
        if detail.compte:
            compte_nom = detail.compte.nom if hasattr(detail.compte, 'nom') else str(detail.compte)

        # Récupérer les IDs et noms des villages
        village_a_id = str(detail.point_a.id) if detail.point_a else ''
        village_b_id = str(detail.point_b.id) if detail.point_b else ''

        fournisseur_id = ''
        if detail.fournisseur:
            fournisseur_id = str(detail.fournisseur.id)

        photo_justif_id = str(detail.photo_justificatif.id) if detail.photo_justificatif else ''

        ws.append([
            str(detail.id),
            str(detail.planning_id) if detail.planning_id else '',
            planning_date,
            employe_surnom,
            ouvrage_nom,
            detail.designation.nom if detail.designation else '',
            detail.quantity or 0,
            detail.pu or 0,
            detail.montant or 0,
            detail.acheteur or '',
            compte_nom,
            str(detail.equipement_constitutif.id) if detail.equipement_constitutif else '',
            str(detail.point_eau.id) if detail.point_eau else '',
            detail.trajet or '',
            village_a_id,
            village_b_id,
            detail.moyen_transport or '',
            'Oui' if detail.utilise else 'Non',
            detail.date_utilisation.strftime('%Y-%m-%d %H:%M') if detail.date_utilisation else '',
            fournisseur_id,
            'Oui' if detail.facture_imprimee else 'Non',
            'Oui' if detail.livraison else 'Non',
            detail.date_livraison.strftime('%Y-%m-%d') if detail.date_livraison else '',
            'Oui' if detail.retour else 'Non',
            detail.date_retour.strftime('%Y-%m-%d') if detail.date_retour else '',
            detail.numero_bon_livraison or '',
            detail.numero_bon_avance or '',
            detail.numero_facture or '',
            detail.numeroDiameXAvance or '',
            detail.BaseDiameXAvance or '',
            detail.numeroDiameX or '',
            detail.BaseDiameX or '',
            photo_justif_id,
            detail.created_at.strftime('%Y-%m-%d %H:%M') if detail.created_at else '',
            detail.updated_at.strftime('%Y-%m-%d %H:%M') if detail.updated_at else ''
        ])

    # Ajuster les largeurs
    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column_letter].width = adjusted_width

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=planning_details_export.xlsx'
    wb.save(response)

    return response


def template_excel_plannings(request):
    """Générer un template Excel pour l'import de plannings"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.comments import Comment
    from openpyxl.worksheet.datavalidation import DataValidation
    from django.http import HttpResponse

    wb = Workbook()
    ws = wb.active
    ws.title = "Template Plannings"

    # En-tÃªtes avec commentaires explicatifs
    headers = [
        'Date (DD/MM/YYYY)*',
        "Nom Ouvrage",
        "Fiche poste (TÃ¢che)",
        'Surnom Employé',
        'Statut',
        'Validé',
        'Remarques',
        'Date Signalement (DD/MM/YYYY)',
        'Vérification',
        'Commentaire Vérification',
        'Débit Mesure',
        'Bilan',
        'Suite Ã  donner',
        'Photos (JSON)'
    ]
    ws.append(headers)

    # Style et commentaires
    header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")

    comments = [
        "Format: 15/01/2025 (obligatoire)",
        "Nom de l'ouvrage (ex: AEP Ambohitrimanjaka)",
        "Nom exact de la fiche de poste (tÃ¢che) si applicable",
        "Surnom de l'employé (ex: JOHN)",
        "Valeurs: planifie, en_cours, termine, annule, reporte",
        "Valeurs: Oui, Non",
        "Remarques sur le planning (texte libre)",
        "Date du signalement si applicable (format: 15/01/2025)",
        "Valeurs: Appel OK tout OK, Appel OK Différence, Faux numéro, Injoignable",
        "Commentaire libre sur la vérification",
        "Débit mesuré (nombre, optionnel)",
        "Bilan (texte libre)",
        "Suite Ã  donner (texte libre)",
        "Photos au format JSON (optionnel)"
    ]

    for idx, cell in enumerate(ws[1]):
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')
        cell.comment = Comment(comments[idx], "Hydria")

    # Validation de données pour Statut (colonne E)
    statut_validation = DataValidation(
        type="list",
        formula1='"planifie,en_cours,termine,annule,reporte"',
        allow_blank=True
    )
    statut_validation.error = 'Valeur invalide'
    statut_validation.errorTitle = 'Statut incorrect'
    statut_validation.prompt = 'Choisissez: planifie, en_cours, termine, annule, reporte'
    ws.add_data_validation(statut_validation)
    statut_validation.add(f'F2:F1000')

    # Validation pour Validé (colonne F)
    valide_validation = DataValidation(
        type="list",
        formula1='"Oui,Non"',
        allow_blank=True
    )
    valide_validation.prompt = 'Choisissez: Oui ou Non'
    ws.add_data_validation(valide_validation)
    valide_validation.add(f'G2:G1000')

    # Validation pour Vérification (colonne I)
    verif_validation = DataValidation(
        type="list",
        formula1='"Appel OK tout OK,Appel OK Différence,Faux numéro,Injoignable"',
        allow_blank=True
    )
    verif_validation.prompt = 'Choisissez le résultat de la vérification'
    ws.add_data_validation(verif_validation)
    verif_validation.add(f'J2:J1000')

    # Exemple de ligne
    ws.append([
        '2025-01-15',
        'AEP Ambohitrimanjaka',
        'Entretien pompe',
        'Inspection',
        'JOHN',
        'planifie',
        'Non',
        'Exemple de remarque',
        '2025-01-14',
        'Appel OK tout OK',
        'Tout s\'est bien passé',
        '',
        '',
        '',
        ''
    ])

    # Ajuster les largeurs
    ws.column_dimensions['A'].width = 20  # Date
    ws.column_dimensions['B'].width = 30  # Nom Ouvrage
    ws.column_dimensions['C'].width = 30  # Fiche poste
    ws.column_dimensions['D'].width = 25  # Type activité
    ws.column_dimensions['E'].width = 20  # Surnom Employé
    ws.column_dimensions['F'].width = 15  # Statut
    ws.column_dimensions['G'].width = 12  # Validé
    ws.column_dimensions['H'].width = 40  # Remarques
    ws.column_dimensions['I'].width = 25  # Date Signalement
    ws.column_dimensions['J'].width = 25  # Vérification
    ws.column_dimensions['K'].width = 50  # Commentaire Vérification
    ws.column_dimensions['L'].width = 15  # Débit Mesure
    ws.column_dimensions['M'].width = 40  # Bilan
    ws.column_dimensions['N'].width = 40  # Suite Ã  donner
    ws.column_dimensions['O'].width = 50  # Photos (JSON)

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=template_plannings_ddmmyyyy.xlsx'
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response['Pragma'] = 'no-cache'
    wb.save(response)

    return response


def template_excel_details(request):
    """Générer un template Excel pour l'import de détails planning"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.comments import Comment
    from django.http import HttpResponse

    wb = Workbook()
    ws = wb.active
    ws.title = "Template Détails"

    # Colonnes correspondant au modèle PlanningDetail
    headers = [
        'Planning ID (UUID)*',
        'D?signation (Nom exact)*',
        'Quantit?*',
        'Prix Unitaire',
        'Montant',
        'Acheteur',
        'Compte (Nom)',
        'ID ?quipement Constitutif',
        "ID Point d'Eau",
        'Trajet (Aller/Retour)',
        'ID Point A (Village)',
        'ID Point B (Village)',
        'Moyen de Transport',
        'Utilis? (Oui/Non)',
        'Date Utilisation',
        'Fournisseur (ID)',
        'Facture Imprimée (Oui/Non)',
        'Livraison (Oui/Non)',
        'Date Livraison',
        'Retour (Oui/Non)',
        'Date Retour',
        'N? Bon Livraison',
        'N? Bon Avance',
        'N? Facture',
        'Num?ro DiameX Avance',
        'Base DiameX Avance',
        'Num?ro DiameX',
        'Base DiameX',
        'ID Photo Justificatif'
    ]
    ws.append(headers)

    header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    comments = [
        "UUID du planning parent (obligatoire)",
        "Nom exact de la d?signation - mat?riel/service ? commander (obligatoire, voir feuille D?signations)",
        "Quantit? ? commander (obligatoire, nombre)",
        "Prix unitaire en Ariary (optionnel, voir prix sugg?r?s dans feuille D?signations)",
        "Montant total (optionnel, calcul? automatiquement si vide)",
        "Nom de la personne responsable de l'achat (optionnel)",
        "Nom du compte comptable (optionnel, voir feuille Comptes)",
        "ID de l'?quipement constitutif (optionnel, voir colonne ID dans feuille ?quipements)",
        "ID du point d'eau (optionnel, voir colonne ID dans feuille Points d'Eau)",
        "Type de trajet: Aller ou Retour (optionnel)",
        "ID du village de d?part (optionnel, voir colonne ID dans feuille Villages)",
        "ID du village d'arriv?e (optionnel, voir colonne ID dans feuille Villages)",
        "Moyen de transport: taxi-brousse, pirogue, bac (optionnel, pour trajets avec Point A et Point B)",
        "Utilis? sur le terrain: Oui ou Non (optionnel, d?faut: Non)",
        "Date d'utilisation au format JJ/MM/AAAA (optionnel)",
        "ID du fournisseur (optionnel)",
        "Facture Imprimée: Oui ou Non (optionnel, d?faut: Non)",
        "Livraison effectu?e: Oui ou Non (optionnel, d?faut: Non)",
        "Date de livraison au format JJ/MM/AAAA (optionnel)",
        "Retour effectu?: Oui ou Non (optionnel, d?faut: Non)",
        "Date de retour au format JJ/MM/AAAA (optionnel)",
        "Num?ro de bon de livraison (optionnel)",
        "Num?ro de bon d'avance (optionnel)",
        "Num?ro de facture (optionnel)",
        "Num?ro DiameX pour avance - nombre entier (optionnel)",
        "Base DiameX pour avance (optionnel)",
        "Num?ro DiameX - nombre entier (optionnel)",
        "Base DiameX (optionnel)",
        "ID photo justificatif (optionnel)"
    ]

    for idx, cell in enumerate(ws[1]):
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')
        cell.comment = Comment(comments[idx], "Hydria")

    # Ligne d'exemple
    ws.append([
        '',  # Planning ID - ? remplir avec UUID du planning
        'Tuyau PVC 50mm',  # D?signation - nom exact
        10,  # Quantit?
        5000,  # Prix Unitaire
        '',  # Montant
        'Jean Rakoto',
        'Fonctionnement g?n?ral',  # Nom du compte
        12345,  # ID ?quipement constitutif (exemple)
        67890,  # ID Point d'eau (exemple)
        'Aller',  # Trajet
        11111,  # ID Point A (Village) (exemple)
        22222,  # ID Point B (Village) (exemple)
        'taxi-brousse',  # Moyen de Transport
        'Non',  # Utilis?
        '',  # Date Utilisation
        '',  # Fournisseur ID
        'Non',  # Facture Imprimée
        'Non',  # Livraison
        '',  # Date Livraison
        'Non',  # Retour
        '',  # Date Retour
        '',  # N? Bon Livraison
        '',  # N? Bon Avance
        '',  # N? Facture
        '',  # Num?ro DiameX Avance
        '',  # Base DiameX Avance
        '',  # Num?ro DiameX
        '',  # Base DiameX
        ''   # ID Photo Justificatif
    ])

    # Ajuster les largeurs des colonnes
    ws.column_dimensions['A'].width = 40  # Planning ID
    ws.column_dimensions['B'].width = 40  # D?signation (nom)
    ws.column_dimensions['C'].width = 12  # Quantit?
    ws.column_dimensions['D'].width = 15  # Prix Unitaire
    ws.column_dimensions['E'].width = 15  # Montant
    ws.column_dimensions['F'].width = 25  # Acheteur
    ws.column_dimensions['G'].width = 25  # Compte (nom)
    ws.column_dimensions['H'].width = 20  # ID ?quipement Constitutif
    ws.column_dimensions['I'].width = 20  # ID Point d'Eau
    ws.column_dimensions['J'].width = 18  # Trajet
    ws.column_dimensions['K'].width = 20  # ID Point A (Village)
    ws.column_dimensions['L'].width = 20  # ID Point B (Village)
    ws.column_dimensions['M'].width = 20  # Moyen de Transport
    ws.column_dimensions['N'].width = 15  # Utilis?
    ws.column_dimensions['O'].width = 18  # Date Utilisation
    ws.column_dimensions['P'].width = 18  # Fournisseur ID
    ws.column_dimensions['Q'].width = 18  # Facture Imprimée
    ws.column_dimensions['R'].width = 15  # Livraison
    ws.column_dimensions['S'].width = 18  # Date Livraison
    ws.column_dimensions['T'].width = 15  # Retour
    ws.column_dimensions['U'].width = 18  # Date Retour
    ws.column_dimensions['V'].width = 18  # N? Bon Livraison
    ws.column_dimensions['W'].width = 18  # N? Bon Avance
    ws.column_dimensions['X'].width = 18  # N? Facture
    ws.column_dimensions['Y'].width = 20  # Num?ro DiameX Avance
    ws.column_dimensions['Z'].width = 20  # Base DiameX Avance
    ws.column_dimensions['AA'].width = 18  # Num?ro DiameX
    ws.column_dimensions['AB'].width = 18  # Base DiameX
    ws.column_dimensions['AC'].width = 22  # ID Photo Justificatif

    # Feuille de référence des désignations disponibles
    ws_ref = wb.create_sheet("Désignations")
    ref_headers = ['Nom de la désignation', 'Type', 'Prix suggéré (Ar)', 'Comptes liés']
    ws_ref.append(ref_headers)

    for idx, cell in enumerate(ws_ref[1]):
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')

    # Récupérer toutes les désignations avec leurs comptes et prix suggérés
    designations = Designation.objects.select_related('type_designation').prefetch_related('comptes__compte').all()

    for designation in designations:
        # Comptes liés - designation.comptes retourne des DesignationCompte, donc accéder Ã  c.compte
        comptes_noms = ', '.join([
            (c.compte.compte or '') + ' - ' + c.compte.nom_compte
            for c in designation.comptes.all()
            if c.compte
        ])

        ws_ref.append([
            designation.nom,
            designation.type_designation.nom if designation.type_designation else '',
            designation.prix_unitaire or '',
            comptes_noms
        ])

    # Ajuster les largeurs des colonnes de référence
    ws_ref.column_dimensions['A'].width = 40  # Nom
    ws_ref.column_dimensions['B'].width = 20  # Type
    ws_ref.column_dimensions['C'].width = 18  # Prix suggéré
    ws_ref.column_dimensions['D'].width = 50  # Comptes

    # Feuille de référence des comptes disponibles
    from apps.organization.models import Compte
    ws_comptes = wb.create_sheet("Comptes")
    comptes_headers = ['Numéro de compte', 'Nom du compte', 'Organisation', 'Détails']
    ws_comptes.append(comptes_headers)

    for idx, cell in enumerate(ws_comptes[1]):
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')

    # Récupérer tous les comptes avec leurs organisations
    comptes = Compte.objects.select_related('organisation').all()

    for compte in comptes:
        ws_comptes.append([
            compte.compte or '',
            compte.nom_compte,
            compte.organisation.nom_organisation if compte.organisation else '',
            compte.detail or ''
        ])

    # Ajuster les largeurs des colonnes de comptes
    ws_comptes.column_dimensions['A'].width = 18  # Numéro
    ws_comptes.column_dimensions['B'].width = 40  # Nom
    ws_comptes.column_dimensions['C'].width = 30  # Organisation
    ws_comptes.column_dimensions['D'].width = 50  # Détails

    # Feuille de référence des équipements constitutifs
    from apps.infrastructure.models import EquipementConstitutif
    ws_equip = wb.create_sheet("Equipements")
    equip_headers = ['ID', 'Nom équipement', 'Type', 'Ouvrage']
    ws_equip.append(equip_headers)

    for idx, cell in enumerate(ws_equip[1]):
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')

    equipements = EquipementConstitutif.objects.select_related('ouvrage').all()[:200]
    for equip in equipements:
        ws_equip.append([
            str(equip.id),
            equip.nom if hasattr(equip, 'nom') else str(equip),
            equip.type if hasattr(equip, 'type') else '',
            equip.ouvrage.nom_ouvrage if equip.ouvrage else ''
        ])

    ws_equip.column_dimensions['A'].width = 15  # ID
    ws_equip.column_dimensions['B'].width = 40  # Nom
    ws_equip.column_dimensions['C'].width = 25  # Type
    ws_equip.column_dimensions['D'].width = 35  # Ouvrage

    # Feuille de référence des points d'eau
    from apps.billing.models import PointEau
    ws_pe = wb.create_sheet("Points d'Eau")
    pe_headers = ['ID', 'Nom point d\'eau', 'Type', 'Ouvrage', 'Village']
    ws_pe.append(pe_headers)

    for idx, cell in enumerate(ws_pe[1]):
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')

    points_eau = PointEau.objects.select_related('ouvrage', 'parcelle__village').all()[:200]
    for pe in points_eau:
        village_nom = ''
        if pe.parcelle and pe.parcelle.village:
            village_nom = pe.parcelle.village.nom_village if hasattr(pe.parcelle.village, 'nom_village') else str(pe.parcelle.village)

        ws_pe.append([
            str(pe.id),
            pe.nom if hasattr(pe, 'nom') else str(pe),
            pe.type_point_eau.nom if pe.type_point_eau and hasattr(pe.type_point_eau, 'nom') else '',
            pe.ouvrage.nom_ouvrage if pe.ouvrage else '',
            village_nom
        ])

    ws_pe.column_dimensions['A'].width = 15  # ID
    ws_pe.column_dimensions['B'].width = 35  # Nom
    ws_pe.column_dimensions['C'].width = 25  # Type
    ws_pe.column_dimensions['D'].width = 35  # Ouvrage
    ws_pe.column_dimensions['E'].width = 30  # Village

    # Feuille de référence des villages
    from apps.geography.models import Village
    ws_villages = wb.create_sheet("Villages")
    villages_headers = ['ID', 'Nom village', 'Fokontany', 'Commune']
    ws_villages.append(villages_headers)

    for idx, cell in enumerate(ws_villages[1]):
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')

    villages = Village.objects.select_related('fokontany__commune').all()[:500]
    for village in villages:
        commune_nom = ''
        fokontany_nom = ''
        if village.fokontany:
            fokontany_nom = village.fokontany.nom_fokontany if hasattr(village.fokontany, 'nom_fokontany') else ''
            if village.fokontany.commune:
                commune_nom = village.fokontany.commune.nom_commune if hasattr(village.fokontany.commune, 'nom_commune') else ''

        ws_villages.append([
            str(village.id),
            village.nom_village if hasattr(village, 'nom_village') else str(village),
            fokontany_nom,
            commune_nom
        ])

    ws_villages.column_dimensions['A'].width = 15  # ID
    ws_villages.column_dimensions['B'].width = 35  # Nom village
    ws_villages.column_dimensions['C'].width = 30  # Fokontany
    ws_villages.column_dimensions['D'].width = 30  # Commune

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=template_details_planning.xlsx'
    wb.save(response)

    return response


@api_view(['POST'])
def import_excel_plannings(request):
    """Import de plannings depuis Excel avec noms au lieu d'UUID"""
    import openpyxl
    from datetime import datetime
    from apps.employees.models_evaluation import FichePoste
    import logging

    logger = logging.getLogger(__name__)
    logger.info("=== Début import_excel_plannings ===")
    logger.info(f"Method: {request.method}")
    logger.info(f"FILES: {list(request.FILES.keys())}")

    if 'file' not in request.FILES:
        logger.error("Aucun fichier dans request.FILES")
        return JsonResponse({'success': False, 'message': 'Aucun fichier fourni'})

    file = request.FILES['file']
    logger.info(f"Fichier reçu: {file.name}, Taille: {file.size} bytes")

    try:
        wb = openpyxl.load_workbook(file)
        ws = wb.active
        logger.info(f"Excel chargé, {ws.max_row} lignes")

        created_count = 0
        updated_count = 0
        skipped_main = 0
        errors = []

        # Ignorer la ligne d'en-tÃªte
        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row[0]:  # Skip empty rows
                continue

            try:

                # Colonnes: (optionnel) ID Planning, Date, Nom Ouvrage, Fiche poste,
                #           Surnom Employ?, Statut, Valid?, Remarques, Date Signalement,
                #           V?rification, Commentaire V?rification, D?bit Mesure, Bilan, Suite ? donner, Photos (JSON)
                planning_id = None
                col_offset = 0
                first_cell = row[0]
                try:
                    from uuid import UUID
                    candidate_id = str(first_cell).strip()
                    if candidate_id:
                        UUID(candidate_id)
                        if Planning.objects.filter(id=candidate_id).exists():
                            planning_id = candidate_id
                            col_offset = 1
                except Exception:
                    pass

                date_str = row[col_offset + 0] if len(row) > col_offset + 0 else None
                nom_ouvrage = row[col_offset + 1] if len(row) > col_offset + 1 else None
                fiche_poste_nom = row[col_offset + 2] if len(row) > col_offset + 2 else None
                surnom_employe = row[col_offset + 3] if len(row) > col_offset + 3 else None
                statut = row[col_offset + 4] if len(row) > col_offset + 4 else 'planifie'
                valide_str = row[col_offset + 5] if len(row) > col_offset + 5 else None
                remarques = row[col_offset + 6] if len(row) > col_offset + 6 else None
                date_signalement_str = row[col_offset + 7] if len(row) > col_offset + 7 else None
                verification = row[col_offset + 8] if len(row) > col_offset + 8 else None
                commentaire_verification = row[col_offset + 9] if len(row) > col_offset + 9 else None
                debitmesure = row[col_offset + 10] if len(row) > col_offset + 10 else None
                bilan = row[col_offset + 11] if len(row) > col_offset + 11 else None
                suiteadonner = row[col_offset + 12] if len(row) > col_offset + 12 else None
                photo = row[col_offset + 13] if len(row) > col_offset + 13 else None

                # Parser la date avec timezone Madagascar (UTC+3)
                from django.utils import timezone as dj_timezone
                import pytz
                tz_madagascar = pytz.timezone('Indian/Antananarivo')

                date_parsed = _parse_excel_date(date_str)
                if isinstance(date_parsed, datetime):
                    if dj_timezone.is_aware(date_parsed):
                        date_obj = date_parsed.astimezone(tz_madagascar)
                    else:
                        date_obj = tz_madagascar.localize(date_parsed)
                else:
                    raise ValueError('Date invalide')

                # Parser date signalement avec timezone Madagascar
                date_signalement = None
                if date_signalement_str:
                    date_sig_parsed = _parse_excel_date(date_signalement_str)
                    if isinstance(date_sig_parsed, datetime):
                        if dj_timezone.is_aware(date_sig_parsed):
                            date_signalement = date_sig_parsed.astimezone(tz_madagascar)
                        else:
                            date_signalement = tz_madagascar.localize(date_sig_parsed)

                # Convertir "Validé" string en boolean
                valide = None
                if valide_str:
                    valide = str(valide_str).strip().lower() in ['oui', 'yes', 'true', '1']

                # Rechercher l'ouvrage par nom
                ouvrage_obj = None
                if nom_ouvrage:
                    ouvrage_obj = Ouvrage.objects.filter(nom_ouvrage__iexact=nom_ouvrage.strip()).first()

                # Rechercher la fiche de poste par t?che
                fiche_poste_obj = None
                if fiche_poste_nom:
                    fiche_poste_obj = FichePoste.objects.filter(tache__iexact=str(fiche_poste_nom).strip()).first()
                    if not fiche_poste_obj:
                        errors.append(f"Ligne {row_idx}: Fiche poste '{fiche_poste_nom}' introuvable - ligne ignor?e")
                        continue

                # Rechercher l'employ? par surnom
                employe_obj = None
                if surnom_employe:
                    employe_val = str(surnom_employe).strip()
                    employe_obj = Employe.objects.filter(
                        Q(surnom__iexact=employe_val) |
                        Q(prenom__iexact=employe_val) |
                        Q(nom__iexact=employe_val) |
                        Q(nom_employe__iexact=employe_val)
                    ).first()
                    if not employe_obj:
                        errors.append(f"Ligne {row_idx}: Employ? '{surnom_employe}' introuvable - ligne ignor?e")
                        continue  # Ignorer cette ligne

                # Cr?er ou mettre ? jour le planning
                from django.utils import timezone as dj_timezone
                try:
                    planning_data = {
                        'date': date_obj,
                        'employe': employe_obj,
                        'ouvrage': ouvrage_obj,
                        'fiche_poste': fiche_poste_obj,
                        'type_activite': fiche_poste_obj.type_activites if fiche_poste_obj else None,
                        'statut': statut if statut else 'planifie',
                        'estvalide': valide,
                        'remarque': remarques or '',
                        'datesignalementactivite': date_signalement,
                        'verification': verification or '',
                        'commentaire_verification': commentaire_verification or '',
                        'debitmesure': debitmesure if debitmesure not in [None, ''] else None,
                        'bilan': bilan or '',
                        'suiteadonner': suiteadonner or '',
                        'photo': photo or ''
                    }

                    if planning_id:
                        try:
                            planning = Planning.objects.get(id=planning_id)
                        except Planning.DoesNotExist:
                            errors.append(f"Ligne {row_idx}: Planning {planning_id} introuvable - ligne ignor?e")
                            continue
                        for key, value in planning_data.items():
                            setattr(planning, key, value)
                        planning.save()
                        updated_count += 1
                    else:
                        Planning.objects.create(**planning_data)
                        created_count += 1
                except Exception as e:
                    # Si erreur de contrainte d'unicit?, logger mais continuer
                    if 'unique' in str(e).lower():
                        errors.append(f"Ligne {row_idx}: Planning d?j? existant (ignor?)")
                    else:
                        raise


            except Exception as e:
                errors.append(f"Ligne {row_idx}: {str(e)}")

        message = f"Import terminé avec succès"
        if skipped_main:
            message += f" | {skipped_main} ignoré(s) (employé principal)"
        if errors:
            message += f" (avec {len(errors)} erreurs)"

        logger.info(f"Import terminé: {created_count} créés, {updated_count} mis Ã  jour, {len(errors)} erreurs")

        return JsonResponse({
            'success': True,
            'message': message,
            'created': created_count,
            'updated': updated_count,
            'errors': errors
        })

    except Exception as e:
        logger.error(f"Erreur import: {str(e)}", exc_info=True)
        return JsonResponse({'success': False, 'message': f'Erreur: {str(e)}'})


@api_view(['POST'])
def import_excel_details(request):
    """Import de détails planning depuis Excel avec noms de désignations"""
    import openpyxl

    if 'file' not in request.FILES:
        return JsonResponse({'success': False, 'message': 'Aucun fichier fourni'})

    file = request.FILES['file']

    try:
        wb = openpyxl.load_workbook(file)
        ws = wb.active

        header_row = [str(c).strip().lower() if c is not None else '' for c in next(ws.iter_rows(min_row=1, max_row=1, values_only=True))]
        def _find_idx(*keys):
            for i, h in enumerate(header_row):
                for k in keys:
                    if k in h:
                        return i
            return None

        idx_planning = _find_idx('planning id', 'id planning')
        idx_point = _find_idx('point d', 'point eau', 'point_eau', 'id point')
        idx_date = _find_idx('date facture', 'date_facture')
        idx_quantite = _find_idx('quantite')
        idx_pu = _find_idx('prix unitaire', 'pu')
        idx_montant = _find_idx('montant')
        idx_paye = _find_idx('paye')
        idx_date_paiement = _find_idx('date paiement', 'date_paiement')
        idx_num_diamex = _find_idx('numero diamex', 'num diamex', 'numerodiamex')
        idx_base_diamex = _find_idx('base diamex')
        idx_debut = _find_idx('date debut', 'debut validite')
        idx_fin = _find_idx('date fin', 'fin validite')
        idx_remarque = _find_idx('remarque', 'note')

        created_count = 0
        updated_count = 0
        errors = []

        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row[0] or not row[1]:  # Skip if first two columns are empty
                continue

            try:
                # Détecter si c'est un export (avec ID Détail) ou un template (avec Planning ID)
                # Export: ID Détail, ID Planning, Désignation, ...
                # Template: Planning ID, Désignation, ...

                detail_id = None
                planning_id = None

                # Essayer de déterminer si row[0] est un ID de détail existant
                try:
                    potential_detail = PlanningDetail.objects.get(id=str(row[0]).strip())
                    # C'est un export avec ID Détail
                    detail_id = str(row[0]).strip()
                    planning_id = str(row[1]).strip() if row[1] else None
                    designation_nom = row[2]
                    col_offset = 2  # Les autres colonnes commencent Ã  l'index 3
                except (PlanningDetail.DoesNotExist, ValueError, TypeError):
                    # C'est un template sans ID Détail
                    planning_id = str(row[0]).strip()
                    designation_nom = row[1]
                    col_offset = 1  # Les autres colonnes commencent Ã  l'index 2

                if not planning_id or not designation_nom:
                    continue

                # Extraire les autres colonnes avec le bon offset
                row_list = list(row) + [None] * 60
                quantity = row_list[col_offset + 1] if len(row_list) > col_offset + 1 else None
                pu = row_list[col_offset + 2] if len(row_list) > col_offset + 2 else None
                montant_excel = row_list[col_offset + 3] if len(row_list) > col_offset + 3 else None
                acheteur = row_list[col_offset + 4] if len(row_list) > col_offset + 4 else None
                compte_nom = row_list[col_offset + 5] if len(row_list) > col_offset + 5 else None
                equipement_id = row_list[col_offset + 6] if len(row_list) > col_offset + 6 else None
                point_eau_id = row_list[col_offset + 7] if len(row_list) > col_offset + 7 else None
                trajet = row_list[col_offset + 8] if len(row_list) > col_offset + 8 else None
                village_a_id = row_list[col_offset + 9] if len(row_list) > col_offset + 9 else None
                village_b_id = row_list[col_offset + 10] if len(row_list) > col_offset + 10 else None
                moyen_transport = row_list[col_offset + 11] if len(row_list) > col_offset + 11 else None
                utilise_str = row_list[col_offset + 12] if len(row_list) > col_offset + 12 else None
                date_utilisation_str = row_list[col_offset + 13] if len(row_list) > col_offset + 13 else None
                fournisseur_id = row_list[col_offset + 14] if len(row_list) > col_offset + 14 else None
                facture_imprimee_str = row_list[col_offset + 15] if len(row_list) > col_offset + 15 else None
                livraison_str = row_list[col_offset + 16] if len(row_list) > col_offset + 16 else None
                date_livraison_str = row_list[col_offset + 17] if len(row_list) > col_offset + 17 else None
                retour_str = row_list[col_offset + 18] if len(row_list) > col_offset + 18 else None
                date_retour_str = row_list[col_offset + 19] if len(row_list) > col_offset + 19 else None
                numero_bon_livraison = row_list[col_offset + 20] if len(row_list) > col_offset + 20 else None
                numero_bon_avance = row_list[col_offset + 21] if len(row_list) > col_offset + 21 else None
                numero_facture = row_list[col_offset + 22] if len(row_list) > col_offset + 22 else None
                numeroDiameXAvance = row_list[col_offset + 23] if len(row_list) > col_offset + 23 else None
                BaseDiameXAvance = row_list[col_offset + 24] if len(row_list) > col_offset + 24 else None
                numeroDiameX = row_list[col_offset + 25] if len(row_list) > col_offset + 25 else None
                BaseDiameX = row_list[col_offset + 26] if len(row_list) > col_offset + 26 else None
                photo_justificatif_id = row_list[col_offset + 27] if len(row_list) > col_offset + 27 else None

                # Rechercher le planning
                try:
                    planning = Planning.objects.get(id=planning_id)
                except Planning.DoesNotExist:
                    errors.append(f"Ligne {row_idx}: Planning {planning_id} introuvable")
                    continue

                # Rechercher la désignation par nom (case-insensitive et trim espaces)
                try:
                    designation_nom_clean = str(designation_nom).strip()
                    designation = Designation.objects.get(nom__iexact=designation_nom_clean)
                except Designation.DoesNotExist:
                    errors.append(f"Ligne {row_idx}: Désignation '{designation_nom}' introuvable")
                    continue
                except Designation.MultipleObjectsReturned:
                    # Prendre la première si plusieurs trouvées
                    designation = Designation.objects.filter(nom__iexact=designation_nom_clean).first()
                    if not designation:
                        errors.append(f"Ligne {row_idx}: Plusieurs désignations trouvées avec le nom '{designation_nom}'")
                        continue

                # Rechercher le compte par nom
                compte_obj = None
                if compte_nom:
                    from apps.organization.models import Compte
                    compte_obj = Compte.objects.filter(nom_compte__icontains=str(compte_nom).strip()).first()

                # Rechercher l'acheteur par surnom (employé)
                acheteur_nom = ''
                if acheteur:
                    from apps.employees.models import Employe
                    acheteur_employe = Employe.objects.filter(surnom__iexact=str(acheteur).strip()).first()
                    if acheteur_employe:
                        acheteur_nom = acheteur_employe.surnom
                    else:
                        # Si pas trouvé par surnom, garder le texte tel quel
                        acheteur_nom = str(acheteur).strip()

                # Rechercher l'équipement constitutif par ID (UUID)
                equipement_obj = None
                if equipement_id:
                    from apps.infrastructure.models import EquipementConstitutif
                    try:
                        equipement_obj = EquipementConstitutif.objects.get(id=str(equipement_id).strip())
                    except (EquipementConstitutif.DoesNotExist, ValueError, TypeError):
                        pass

                # Rechercher le point d'eau par ID (UUID)
                point_eau_obj = None
                if point_eau_id:
                    from apps.billing.models import PointEau
                    try:
                        point_eau_obj = PointEau.objects.get(id=str(point_eau_id).strip())
                    except (PointEau.DoesNotExist, ValueError, TypeError):
                        pass

                # Rechercher les villages par ID (UUID)
                village_a_obj = None
                if village_a_id:
                    from apps.geography.models import Village
                    try:
                        village_a_obj = Village.objects.get(id=str(village_a_id).strip())
                    except (Village.DoesNotExist, ValueError, TypeError):
                        pass

                village_b_obj = None
                if village_b_id:
                    from apps.geography.models import Village
                    try:
                        village_b_obj = Village.objects.get(id=str(village_b_id).strip())
                    except (Village.DoesNotExist, ValueError, TypeError):
                        pass

                # Rechercher le fournisseur par ID (UUID) ou nom
                fournisseur_obj = None
                if fournisseur_id:
                    from apps.billing.models import Fournisseur
                    fournisseur_id_str = str(fournisseur_id).strip()
                    try:
                        fournisseur_obj = Fournisseur.objects.get(id=fournisseur_id_str)
                    except (Fournisseur.DoesNotExist, ValueError, TypeError):
                        fournisseur_obj = Fournisseur.objects.filter(nom__iexact=fournisseur_id_str).first()

                # Photo justificatif (FileUpload)
                photo_justificatif_obj = None
                if photo_justificatif_id:
                    from apps.filemanager.models import FileUpload
                    try:
                        photo_justificatif_obj = FileUpload.objects.get(id=str(photo_justificatif_id).strip())
                    except (FileUpload.DoesNotExist, ValueError, TypeError):
                        pass

                # Utiliser le prix unitaire de la désignation si le prix unitaire n'est pas fourni
                prix_unitaire = pu if pu else (designation.prix_unitaire or 0)

                # Calculer le montant
                quantite = quantity if quantity else 0
                if montant_excel is not None and str(montant_excel).strip() != '':
                    try:
                        montant = float(montant_excel)
                    except Exception:
                        montant = quantite * float(prix_unitaire)
                else:
                    montant = quantite * float(prix_unitaire)

                # Parser les booléens
                utilise = str(utilise_str).strip().lower() in ['oui', 'yes', 'true', '1'] if utilise_str else False
                facture_imprimee = str(facture_imprimee_str).strip().lower() in ['oui', 'yes', 'true', '1'] if facture_imprimee_str else False
                livraison = str(livraison_str).strip().lower() in ['oui', 'yes', 'true', '1'] if livraison_str else False
                retour = str(retour_str).strip().lower() in ['oui', 'yes', 'true', '1'] if retour_str else False

                # Parser les dates avec timezone Madagascar (voir TIMEZONE_GUIDE.md)
                import pytz
                tz_madagascar = pytz.timezone('Indian/Antananarivo')
                date_utilisation = None
                if date_utilisation_str:
                    try:
                        date_util_parsed = _parse_excel_date(date_utilisation_str)
                        if isinstance(date_util_parsed, datetime):
                            if date_util_parsed.tzinfo:
                                date_utilisation = date_util_parsed.astimezone(tz_madagascar)
                            else:
                                date_utilisation = tz_madagascar.localize(date_util_parsed)
                    except Exception:
                        pass

                date_livraison = None
                if date_livraison_str:
                    try:
                        date_liv_parsed = _parse_excel_date(date_livraison_str)
                        if isinstance(date_liv_parsed, datetime):
                            if date_liv_parsed.tzinfo:
                                date_livraison = date_liv_parsed.astimezone(tz_madagascar).date()
                            else:
                                date_livraison = tz_madagascar.localize(date_liv_parsed).date()
                    except Exception:
                        pass

                date_retour = None
                if date_retour_str:
                    try:
                        date_ret_parsed = _parse_excel_date(date_retour_str)
                        if isinstance(date_ret_parsed, datetime):
                            if date_ret_parsed.tzinfo:
                                date_retour = date_ret_parsed.astimezone(tz_madagascar).date()
                            else:
                                date_retour = tz_madagascar.localize(date_ret_parsed).date()
                    except Exception:
                        pass

                # Parser les entiers
                num_diamex_avance = int(numeroDiameXAvance) if numeroDiameXAvance else None
                num_diamex = int(numeroDiameX) if numeroDiameX else None

                # Valider le moyen de transport
                moyen_transport_clean = None
                if moyen_transport and str(moyen_transport).strip():
                    mt = str(moyen_transport).strip().lower()
                    if mt in ['taxi-brousse', 'pirogue', 'bac']:
                        moyen_transport_clean = mt

                # Préparer les données pour créer/mettre Ã  jour
                deplacement_data = {
                    'trajet': trajet.lower() if trajet and trajet.strip().lower() in ['aller', 'retour'] else None,
                    'point_a': village_a_obj,
                    'point_b': village_b_obj,
                    'moyen_transport': moyen_transport_clean,
                }

                detail_data = {
                    'quantity': quantite,
                    'pu': prix_unitaire,
                    'montant': montant,
                    'acheteur': acheteur_nom,
                    'compte': compte_obj,
                    'equipement_constitutif': equipement_obj,
                    'point_eau': point_eau_obj,
                    'utilise': utilise,
                    'date_utilisation': date_utilisation,
                    'fournisseur': fournisseur_obj,
                    'facture_imprimee': facture_imprimee,
                    'livraison': livraison,
                    'date_livraison': date_livraison,
                    'retour': retour,
                    'date_retour': date_retour,
                    'numero_bon_livraison': str(numero_bon_livraison).strip() if numero_bon_livraison else '',
                    'numero_bon_avance': str(numero_bon_avance).strip() if numero_bon_avance else '',
                    'numero_facture': str(numero_facture).strip() if numero_facture else '',
                    'numeroDiameXAvance': num_diamex_avance,
                    'BaseDiameXAvance': BaseDiameXAvance or '',
                    'numeroDiameX': num_diamex,
                    'BaseDiameX': BaseDiameX or '',
                    'photo_justificatif': photo_justificatif_obj
                }

                # Créer ou mettre Ã  jour le détail
                if detail_id:
                    # Si on a un ID détail, mettre Ã  jour ce détail spécifique
                    try:
                        detail = PlanningDetail.objects.get(id=detail_id)
                        # Mettre Ã  jour tous les champs
                        for key, value in detail_data.items():
                            setattr(detail, key, value)
                        detail.save()
                        if any(deplacement_data.values()):
                            PlanningDetailDeplacement.objects.update_or_create(
                                planning_detail=detail,
                                defaults={
                                    'trajet': deplacement_data['trajet'] or 'aller',
                                    'point_a': deplacement_data['point_a'],
                                    'point_b': deplacement_data['point_b'],
                                    'moyen_transport': deplacement_data['moyen_transport'],
                                }
                            )
                        else:
                            PlanningDetailDeplacement.objects.filter(planning_detail=detail).delete()
                        updated_count += 1
                    except PlanningDetail.DoesNotExist:
                        errors.append(f"Ligne {row_idx}: Détail {detail_id} introuvable")
                        continue
                else:
                    # Créer un nouveau détail (ne pas utiliser update_or_create car un planning peut avoir plusieurs lignes avec la mÃªme désignation)
                    detail = PlanningDetail.objects.create(
                        planning=planning,
                        designation=designation,
                        **detail_data
                    )
                    if any(deplacement_data.values()):
                        PlanningDetailDeplacement.objects.create(
                            planning_detail=detail,
                            trajet=deplacement_data['trajet'] or 'aller',
                            point_a=deplacement_data['point_a'],
                            point_b=deplacement_data['point_b'],
                            moyen_transport=deplacement_data['moyen_transport'],
                        )
                    created_count += 1

            except Exception as e:
                errors.append(f"Ligne {row_idx}: {str(e)}")

        message = f"Import terminé: {created_count} détails créés"
        if errors:
            message += f" (avec {len(errors)} erreurs)"

        return JsonResponse({
            'success': True,
            'message': message,
            'created': created_count,
            'updated': updated_count,
            'errors': errors
        })

    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Erreur: {str(e)}'})


# ==================== EXPORT / IMPORT BONS DE LIVRAISON ====================

def export_excel_bons_livraison(request):
    """Export des bons de livraison en Excel"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from django.http import HttpResponse

    wb = Workbook()
    ws = wb.active
    ws.title = "Bons de livraison"

    headers = [
        'ID Bon',
        'Planning ID',
        'Date Planning',
        'Surnom Employé',
        'Ouvrage',
        'Désignation',
        'Quantité',
        'Magasin',
        "ID Point d'Eau",
        'ID Equipement Constitutif',
        'Utilisé',
        'Date Utilisation',
        'Retour',
        'Date Retour',
        'Numéro Bon',
        'ID Photo Justificatif',
        "Point d'Eau (Nom)",
        'Equipement (Nom)',
        'Date Planning',
        'Ouvrage',
        'Créé le',
        'Modifié le'
    ]
    ws.append(headers)

    header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')

    bons = BonLivraison.objects.select_related(
        'planning', 'planning__ouvrage', 'designation', 'point_eau', 'equipement', 'photo_justificatif'
    ).order_by('-created_at')

    for bon in bons:
        point_eau_nom = ''
        if bon.point_eau:
            point_eau_nom = bon.point_eau.nomabonne if hasattr(bon.point_eau, 'nomabonne') else str(bon.point_eau)

        equipement_nom = ''
        if bon.equipement:
            equipement_nom = bon.equipement.nom if hasattr(bon.equipement, 'nom') else str(bon.equipement)

        planning_date = ''
        planning_surnom = ''
        ouvrage_nom = ''
        if bon.planning:
            if bon.planning.date:
                planning_date = bon.planning.date.strftime('%Y-%m-%d')
            if bon.planning.employe:
                planning_surnom = bon.planning.employe.surnom or bon.planning.employe.prenom or bon.planning.employe.nom_employe or ''
            if bon.planning.ouvrage:
                ouvrage_nom = bon.planning.ouvrage.nom_ouvrage

        ws.append([
            str(bon.id),
            str(bon.planning_id) if bon.planning_id else '',
            planning_date,
            planning_surnom,
            ouvrage_nom,
            bon.designation.nom if bon.designation else '',
            bon.quantite or 0,
            bon.magasin or '',
            str(bon.point_eau.id) if bon.point_eau else '',
            str(bon.equipement.id) if bon.equipement else '',
            'Oui' if bon.utilise else 'Non',
            bon.date_utilisation.strftime('%Y-%m-%d %H:%M') if bon.date_utilisation else '',
            'Oui' if bon.retour else 'Non',
            bon.date_retour.strftime('%Y-%m-%d %H:%M') if bon.date_retour else '',
            bon.numero_bon or '',
            str(bon.photo_justificatif.id) if bon.photo_justificatif else '',
            point_eau_nom,
            equipement_nom,
            planning_date,
            ouvrage_nom,
            bon.created_at.strftime('%Y-%m-%d %H:%M') if bon.created_at else '',
            bon.updated_at.strftime('%Y-%m-%d %H:%M') if bon.updated_at else ''
        ])

    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except Exception:
                pass
        ws.column_dimensions[column_letter].width = min(max_length + 2, 50)

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=bons_livraison_export.xlsx'
    wb.save(response)
    return response


def template_excel_bons_livraison(request):
    """Template Excel pour l'import des bons de livraison"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.comments import Comment
    from django.http import HttpResponse

    wb = Workbook()
    ws = wb.active
    ws.title = "Template Bons Livraison"

    headers = [
        'Planning ID (UUID)*',
        'Désignation (Nom exact)*',
        'Quantité*',
        'Magasin',
        "ID Point d'Eau",
        'ID Equipement Constitutif',
        'Utilisé (Oui/Non)',
        'Date Utilisation',
        'Retour (Oui/Non)',
        'Date Retour',
        'Numéro Bon',
        'ID Photo Justificatif'
    ]
    ws.append(headers)

    header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    comments = [
        "UUID du planning parent (obligatoire)",
        "Nom exact de la désignation (obligatoire)",
        "Quantité livrée (obligatoire, nombre)",
        "Nom du magasin (optionnel)",
        "ID du point d'eau (optionnel)",
        "ID de l'équipement constitutif (optionnel)",
        "Utilisé: Oui/Non (optionnel)",
        "Date utilisation au format JJ/MM/AAAA (optionnel)",
        "Retour: Oui/Non (optionnel)",
        "Date retour au format JJ/MM/AAAA (optionnel)",
        "Numéro de bon (optionnel)",
        "ID photo justificatif (optionnel)"
    ]

    for idx, cell in enumerate(ws[1]):
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')
        cell.comment = Comment(comments[idx], "Hydria")

    ws.append([
        '',
        'Tuyau PVC 50mm',
        10,
        'Magasin Central',
        '',
        '',
        'Non',
        '',
        'Non',
        '',
        'BL-2025-001',
        ''
    ])

    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except Exception:
                pass
        ws.column_dimensions[column_letter].width = min(max_length + 2, 50)

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=template_bons_livraison.xlsx'
    wb.save(response)
    return response


@api_view(['POST'])
def import_excel_bons_livraison(request):
    """Import des bons de livraison depuis Excel"""
    import openpyxl
    from datetime import datetime
    import pytz

    if 'file' not in request.FILES:
        return JsonResponse({'success': False, 'message': 'Aucun fichier fourni'})

    file = request.FILES['file']
    tz_madagascar = pytz.timezone('Indian/Antananarivo')

    try:
        wb = openpyxl.load_workbook(file)
        ws = wb.active

        header_row = [str(c).strip().lower() if c is not None else '' for c in next(ws.iter_rows(min_row=1, max_row=1, values_only=True))]
        def _find_idx(*keys):
            for i, h in enumerate(header_row):
                for k in keys:
                    if k in h:
                        return i
            return None

        idx_planning = _find_idx('planning id', 'id planning')
        idx_point = _find_idx('point d', 'point eau', 'point_eau', 'id point')
        idx_date = _find_idx('date facture', 'date_facture')
        idx_quantite = _find_idx('quantite')
        idx_pu = _find_idx('prix unitaire', 'pu')
        idx_montant = _find_idx('montant')
        idx_paye = _find_idx('paye')
        idx_date_paiement = _find_idx('date paiement', 'date_paiement')
        idx_num_diamex = _find_idx('numero diamex', 'num diamex', 'numerodiamex')
        idx_base_diamex = _find_idx('base diamex')
        idx_debut = _find_idx('date debut', 'debut validite')
        idx_fin = _find_idx('date fin', 'fin validite')
        idx_remarque = _find_idx('remarque', 'note')

        created_count = 0
        updated_count = 0
        errors = []

        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row[0]:
                continue

            try:
                bon_id = None
                col_offset = 0

                try:
                    from uuid import UUID
                    candidate_id = str(row[0]).strip()
                    UUID(candidate_id)
                    if BonLivraison.objects.filter(id=candidate_id).exists():
                        bon_id = candidate_id
                        col_offset = 1
                except Exception:
                    pass

                planning_id = str(row[col_offset + 0]).strip() if len(row) > col_offset + 0 and row[col_offset + 0] else None
                designation_nom = row[col_offset + 1] if len(row) > col_offset + 1 else None
                quantite = row[col_offset + 2] if len(row) > col_offset + 2 else None
                magasin = row[col_offset + 3] if len(row) > col_offset + 3 else None
                point_eau_id = row[col_offset + 4] if len(row) > col_offset + 4 else None
                equipement_id = row[col_offset + 5] if len(row) > col_offset + 5 else None
                utilise_str = row[col_offset + 6] if len(row) > col_offset + 6 else None
                date_utilisation_str = row[col_offset + 7] if len(row) > col_offset + 7 else None
                retour_str = row[col_offset + 8] if len(row) > col_offset + 8 else None
                date_retour_str = row[col_offset + 9] if len(row) > col_offset + 9 else None
                numero_bon = row[col_offset + 10] if len(row) > col_offset + 10 else None
                photo_justificatif_id = row[col_offset + 11] if len(row) > col_offset + 11 else None

                if not planning_id or not designation_nom:
                    continue

                try:
                    planning = Planning.objects.get(id=planning_id)
                except Planning.DoesNotExist:
                    errors.append(f"Ligne {row_idx}: Planning {planning_id} introuvable")
                    continue

                try:
                    designation = Designation.objects.get(nom__iexact=str(designation_nom).strip())
                except Designation.DoesNotExist:
                    errors.append(f"Ligne {row_idx}: Désignation '{designation_nom}' introuvable")
                    continue
                except Designation.MultipleObjectsReturned:
                    designation = Designation.objects.filter(nom__iexact=str(designation_nom).strip()).first()

                point_eau_obj = None
                if point_eau_id:
                    from apps.billing.models import PointEau
                    try:
                        point_eau_obj = PointEau.objects.get(id=str(point_eau_id).strip())
                    except Exception:
                        pass

                equipement_obj = None
                if equipement_id:
                    from apps.infrastructure.models import EquipementConstitutif
                    try:
                        equipement_obj = EquipementConstitutif.objects.get(id=str(equipement_id).strip())
                    except Exception:
                        pass

                photo_justificatif_obj = None
                if photo_justificatif_id:
                    from apps.filemanager.models import FileUpload
                    try:
                        photo_justificatif_obj = FileUpload.objects.get(id=str(photo_justificatif_id).strip())
                    except Exception:
                        pass

                utilise = str(utilise_str).strip().lower() in ['oui', 'yes', 'true', '1'] if utilise_str else False
                retour = str(retour_str).strip().lower() in ['oui', 'yes', 'true', '1'] if retour_str else False

                date_utilisation = None
                if date_utilisation_str:
                    try:
                        date_util_parsed = _parse_excel_date(date_utilisation_str)
                        if isinstance(date_util_parsed, datetime):
                            if date_util_parsed.tzinfo:
                                date_utilisation = date_util_parsed.astimezone(tz_madagascar)
                            else:
                                date_utilisation = tz_madagascar.localize(date_util_parsed)
                    except Exception:
                        pass

                date_retour = None
                if date_retour_str:
                    try:
                        date_ret_parsed = _parse_excel_date(date_retour_str)
                        if isinstance(date_ret_parsed, datetime):
                            if date_ret_parsed.tzinfo:
                                date_retour = date_ret_parsed.astimezone(tz_madagascar)
                            else:
                                date_retour = tz_madagascar.localize(date_ret_parsed)
                    except Exception:
                        pass

                bon_data = {
                    'planning': planning,
                    'designation': designation,
                    'quantite': quantite or 0,
                    'magasin': magasin or '',
                    'point_eau': point_eau_obj,
                    'equipement': equipement_obj,
                    'utilise': utilise,
                    'date_utilisation': date_utilisation,
                    'retour': retour,
                    'date_retour': date_retour,
                    'numero_bon': str(numero_bon).strip() if numero_bon else '',
                    'photo_justificatif': photo_justificatif_obj
                }

                if bon_id:
                    try:
                        bon = BonLivraison.objects.get(id=bon_id)
                        for key, value in bon_data.items():
                            setattr(bon, key, value)
                        bon.save()
                        updated_count += 1
                    except BonLivraison.DoesNotExist:
                        errors.append(f"Ligne {row_idx}: Bon {bon_id} introuvable")
                else:
                    BonLivraison.objects.create(**bon_data)
                    created_count += 1

            except Exception as e:
                errors.append(f"Ligne {row_idx}: {str(e)}")

        message = f"Import terminé: {created_count} créés"
        if errors:
            message += f" (avec {len(errors)} erreurs)"

        return JsonResponse({
            'success': True,
            'message': message,
            'created': created_count,
            'updated': updated_count,
            'errors': errors
        })

    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Erreur: {str(e)}'})


# ==================== EXPORT / IMPORT PAIEMENTS FORFAITAIRES ====================

def export_excel_paiements_forfaitaires(request):
    """Export des paiements forfaitaires en Excel"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from django.http import HttpResponse

    wb = Workbook()
    ws = wb.active
    ws.title = "Paiements forfaitaires"

    headers = [
        'ID Paiement',
        'Planning ID',
        'Date Planning',
        'Surnom Employé',
        'Ouvrage',
        "ID Point d'Eau",
        'Date Facture',
        'Quantité',
        'Prix Unitaire',
        'Montant',
        'Payé',
        'Date Paiement',
        'Numéro DiameX',
        'Base DiameX',
        'Date Début Validité',
        'Date Fin Validité',
        'Remarque',
        "Point d'Eau (Nom)",
        'Ouvrage',
        'Date Planning',
        'Créé le',
        'Modifié le'
    ]
    ws.append(headers)

    header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')

    paiements = PaiementForfaitaire.objects.select_related(
        'point_eau', 'point_eau__ouvrage', 'planning'
    ).order_by('-date_facture')

    for p in paiements:
        point_eau_nom = ''
        ouvrage_nom = ''
        if p.point_eau:
            point_eau_nom = p.point_eau.nomabonne if hasattr(p.point_eau, 'nomabonne') else str(p.point_eau)
            if p.point_eau.ouvrage:
                ouvrage_nom = p.point_eau.ouvrage.nom_ouvrage

        planning_date = p.planning.date.strftime('%Y-%m-%d') if p.planning and p.planning.date else ''
        planning_surnom = ''
        if p.planning and p.planning.employe:
            planning_surnom = p.planning.employe.surnom or p.planning.employe.prenom or p.planning.employe.nom_employe or ''

        ws.append([
            str(p.id),
            str(p.planning_id) if p.planning_id else '',
            planning_date,
            planning_surnom,
            ouvrage_nom,
            str(p.point_eau.id) if p.point_eau else '',
            p.date_facture.strftime('%Y-%m-%d') if p.date_facture else '',
            p.quantite or 0,
            p.prix_unitaire or 0,
            p.montant or 0,
            'Oui' if p.paye else 'Non',
            p.date_paiement.strftime('%Y-%m-%d') if p.date_paiement else '',
            p.numeroDiameX or '',
            p.baseDiameX or '',
            p.date_debut_validite.strftime('%Y-%m-%d') if p.date_debut_validite else '',
            p.date_fin_validite.strftime('%Y-%m-%d') if p.date_fin_validite else '',
            p.remarque or '',
            point_eau_nom,
            ouvrage_nom,
            planning_date,
            p.created_at.strftime('%Y-%m-%d %H:%M') if p.created_at else '',
            p.updated_at.strftime('%Y-%m-%d %H:%M') if p.updated_at else ''
        ])

    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except Exception:
                pass
        ws.column_dimensions[column_letter].width = min(max_length + 2, 50)

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=paiements_forfaitaires_export.xlsx'
    wb.save(response)
    return response


def template_excel_paiements_forfaitaires(request):
    """Template Excel pour l'import des paiements forfaitaires"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.comments import Comment
    from django.http import HttpResponse

    wb = Workbook()
    ws = wb.active
    ws.title = "Template Paiements"

    headers = [
        'Planning ID (UUID)',
        "ID Point d'Eau*",
        'Date Facture (DD/MM/YYYY)*',
        'Quantité*',
        'Prix Unitaire',
        'Montant',
        'Payé (Oui/Non)',
        'Date Paiement',
        'Numéro DiameX',
        'Base DiameX',
        'Date Début Validité',
        'Date Fin Validité',
        'Remarque'
    ]
    ws.append(headers)

    header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    comments = [
        "UUID du planning (optionnel)",
        "ID du point d'eau (obligatoire)",
        "Date de facture (obligatoire, format JJ/MM/AAAA)",
        "Quantité (obligatoire, entier)",
        "Prix unitaire (optionnel, sinon tarif forfaitaire du point d'eau)",
        "Montant total (optionnel, calculé si vide)",
        "Payé: Oui/Non (optionnel)",
        "Date de paiement (optionnel, format JJ/MM/AAAA)",
        "Numéro DiameX (optionnel)",
        "Base DiameX (optionnel)",
        "Date début validité (optionnel)",
        "Date fin validité (optionnel)",
        "Remarque (optionnel)"
    ]

    for idx, cell in enumerate(ws[1]):
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')
        cell.comment = Comment(comments[idx], "Hydria")

    ws.append([
        '',
        '',
        '2025-01-15',
        1,
        '',
        '',
        'Non',
        '',
        '',
        '',
        '',
        '',
        ''
    ])

    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except Exception:
                pass
        ws.column_dimensions[column_letter].width = min(max_length + 2, 50)

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=template_paiements_forfaitaires.xlsx'
    wb.save(response)
    return response


@api_view(['POST'])
def import_excel_paiements_forfaitaires(request):
    """Import des paiements forfaitaires depuis Excel"""
    import openpyxl
    from datetime import datetime

    if 'file' not in request.FILES:
        return JsonResponse({'success': False, 'message': 'Aucun fichier fourni'})

    file = request.FILES['file']

    try:
        wb = openpyxl.load_workbook(file)
        ws = wb.active

        header_row = [str(c).strip().lower() if c is not None else '' for c in next(ws.iter_rows(min_row=1, max_row=1, values_only=True))]
        def _find_idx(*keys):
            for i, h in enumerate(header_row):
                for k in keys:
                    if k in h:
                        return i
            return None

        idx_planning = _find_idx('planning id', 'id planning')
        idx_point = _find_idx('point d', 'point eau', 'point_eau', 'id point')
        idx_date = _find_idx('date facture', 'date_facture')
        idx_quantite = _find_idx('quantite')
        idx_pu = _find_idx('prix unitaire', 'pu')
        idx_montant = _find_idx('montant')
        idx_paye = _find_idx('paye')
        idx_date_paiement = _find_idx('date paiement', 'date_paiement')
        idx_num_diamex = _find_idx('numero diamex', 'num diamex', 'numerodiamex')
        idx_base_diamex = _find_idx('base diamex')
        idx_debut = _find_idx('date debut', 'debut validite')
        idx_fin = _find_idx('date fin', 'fin validite')
        idx_remarque = _find_idx('remarque', 'note')

        created_count = 0
        updated_count = 0
        errors = []

        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row[0] and not row[1]:
                continue

            try:
                paiement_id = None
                col_offset = 0

                try:
                    from uuid import UUID
                    candidate_id = str(row[0]).strip()
                    UUID(candidate_id)
                    if PaiementForfaitaire.objects.filter(id=candidate_id).exists():
                        paiement_id = candidate_id
                        col_offset = 1
                except Exception:
                    pass

                if idx_point is not None or idx_date is not None or idx_quantite is not None:
                    planning_id = row[idx_planning] if idx_planning is not None and len(row) > idx_planning else None
                    point_eau_id = row[idx_point] if idx_point is not None and len(row) > idx_point else None
                    date_facture_str = row[idx_date] if idx_date is not None and len(row) > idx_date else None
                    quantite = row[idx_quantite] if idx_quantite is not None and len(row) > idx_quantite else None
                    prix_unitaire = row[idx_pu] if idx_pu is not None and len(row) > idx_pu else None
                    montant_excel = row[idx_montant] if idx_montant is not None and len(row) > idx_montant else None
                    paye_str = row[idx_paye] if idx_paye is not None and len(row) > idx_paye else None
                    date_paiement_str = row[idx_date_paiement] if idx_date_paiement is not None and len(row) > idx_date_paiement else None
                    numero_diamex = row[idx_num_diamex] if idx_num_diamex is not None and len(row) > idx_num_diamex else None
                    base_diamex = row[idx_base_diamex] if idx_base_diamex is not None and len(row) > idx_base_diamex else None
                    date_debut_validite_str = row[idx_debut] if idx_debut is not None and len(row) > idx_debut else None
                    date_fin_validite_str = row[idx_fin] if idx_fin is not None and len(row) > idx_fin else None
                    remarque = row[idx_remarque] if idx_remarque is not None and len(row) > idx_remarque else None
                else:
                    planning_id = row[col_offset + 0] if len(row) > col_offset + 0 else None
                    point_eau_id = row[col_offset + 1] if len(row) > col_offset + 1 else None
                    date_facture_str = row[col_offset + 2] if len(row) > col_offset + 2 else None
                    quantite = row[col_offset + 3] if len(row) > col_offset + 3 else None
                    prix_unitaire = row[col_offset + 4] if len(row) > col_offset + 4 else None
                    montant_excel = row[col_offset + 5] if len(row) > col_offset + 5 else None
                    paye_str = row[col_offset + 6] if len(row) > col_offset + 6 else None
                    date_paiement_str = row[col_offset + 7] if len(row) > col_offset + 7 else None
                    numero_diamex = row[col_offset + 8] if len(row) > col_offset + 8 else None
                    base_diamex = row[col_offset + 9] if len(row) > col_offset + 9 else None
                    date_debut_validite_str = row[col_offset + 10] if len(row) > col_offset + 10 else None
                    date_fin_validite_str = row[col_offset + 11] if len(row) > col_offset + 11 else None
                    remarque = row[col_offset + 12] if len(row) > col_offset + 12 else None


                # Fallback: si aucune colonne obligatoire n'est trouvee, supposer format sans Planning ID
                if not point_eau_id and not date_facture_str and not quantite:
                    point_eau_id = row[col_offset + 0] if len(row) > col_offset + 0 else None
                    date_facture_str = row[col_offset + 1] if len(row) > col_offset + 1 else None
                    quantite = row[col_offset + 2] if len(row) > col_offset + 2 else None
                    prix_unitaire = row[col_offset + 3] if len(row) > col_offset + 3 else None
                    montant_excel = row[col_offset + 4] if len(row) > col_offset + 4 else None
                    paye_str = row[col_offset + 5] if len(row) > col_offset + 5 else None
                    date_paiement_str = row[col_offset + 6] if len(row) > col_offset + 6 else None
                    numero_diamex = row[col_offset + 7] if len(row) > col_offset + 7 else None
                    base_diamex = row[col_offset + 8] if len(row) > col_offset + 8 else None
                    date_debut_validite_str = row[col_offset + 9] if len(row) > col_offset + 9 else None
                    date_fin_validite_str = row[col_offset + 10] if len(row) > col_offset + 10 else None
                    remarque = row[col_offset + 11] if len(row) > col_offset + 11 else None

                # Fallback: si la colonne Planning ID est en fait le point d'eau
                if planning_id and not point_eau_id:
                    try:
                        from uuid import UUID
                        UUID(str(planning_id).strip())
                    except Exception:
                        # Decaler: planning_id contient le point d'eau
                        point_eau_id = planning_id
                        date_facture_str = row[col_offset + 1] if len(row) > col_offset + 1 else None
                        quantite = row[col_offset + 2] if len(row) > col_offset + 2 else None
                        prix_unitaire = row[col_offset + 3] if len(row) > col_offset + 3 else None
                        montant_excel = row[col_offset + 4] if len(row) > col_offset + 4 else None
                        paye_str = row[col_offset + 5] if len(row) > col_offset + 5 else None
                        date_paiement_str = row[col_offset + 6] if len(row) > col_offset + 6 else None
                        numero_diamex = row[col_offset + 7] if len(row) > col_offset + 7 else None
                        base_diamex = row[col_offset + 8] if len(row) > col_offset + 8 else None
                        date_debut_validite_str = row[col_offset + 9] if len(row) > col_offset + 9 else None
                        date_fin_validite_str = row[col_offset + 10] if len(row) > col_offset + 10 else None
                        remarque = row[col_offset + 11] if len(row) > col_offset + 11 else None
                        planning_id = None

                if not point_eau_id or not date_facture_str or not quantite:
                    # Heuristique: tenter de retrouver les champs obligatoires dans la ligne
                    if not point_eau_id:
                        for cell in row:
                            if not cell:
                                continue
                            pe_candidate = str(cell).strip()
                            if not pe_candidate:
                                continue
                            try:
                                point_eau = PointEau.objects.get(id=pe_candidate)
                                point_eau_id = pe_candidate
                                break
                            except Exception:
                                pass
                            point_eau = PointEau.objects.filter(code_point_eau__iexact=pe_candidate).first()
                            if point_eau:
                                point_eau_id = pe_candidate
                                break
                            point_eau = PointEau.objects.filter(idxls__iexact=pe_candidate).first()
                            if point_eau:
                                point_eau_id = pe_candidate
                                break

                    if not date_facture_str:
                        for cell in row:
                            if _parse_date(cell):
                                date_facture_str = cell
                                break

                    if not quantite:
                        numeric_vals = []
                        for cell in row:
                            if isinstance(cell, (int, float)) and cell > 0:
                                numeric_vals.append(cell)
                        if numeric_vals:
                            quantite = min(numeric_vals)

                if not point_eau_id or not date_facture_str or not quantite:
                    errors.append(f"Ligne {row_idx}: Point d'eau, date facture et quantit? obligatoires")
                    continue

                from apps.billing.models import PointEau
                point_eau = None
                pe_raw = str(point_eau_id).strip()
                if pe_raw:
                    try:
                        point_eau = PointEau.objects.get(id=pe_raw)
                    except Exception:
                        point_eau = None
                if not point_eau and pe_raw:
                    point_eau = PointEau.objects.filter(code_point_eau__iexact=pe_raw).first()
                if not point_eau and pe_raw:
                    point_eau = PointEau.objects.filter(idxls__iexact=pe_raw).first()
                if not point_eau:
                    errors.append(f"Ligne {row_idx}: Point d'eau {point_eau_id} introuvable (ID ou code)")
                    continue

                planning = None
                if planning_id:
                    try:
                        planning = Planning.objects.get(id=str(planning_id).strip())
                    except Planning.DoesNotExist:
                        planning = None

                def _parse_date(value):
                    if not value:
                        return None
                    if isinstance(value, datetime):
                        return value.date()
                    parsed = _parse_excel_date(value)
                    if isinstance(parsed, datetime):
                        return parsed.date()
                    return None

                date_facture = _parse_date(date_facture_str)
                date_paiement = _parse_date(date_paiement_str)
                date_debut_validite = _parse_date(date_debut_validite_str)
                date_fin_validite = _parse_date(date_fin_validite_str)

                if date_facture is None:
                    errors.append(f"Ligne {row_idx}: Date facture invalide")
                    continue

                if (
                    planning
                    and planning.ouvrage_id
                    and point_eau.ouvrage_id
                    and planning.ouvrage_id != point_eau.ouvrage_id
                ):
                    planning_ouvrage_nom = getattr(getattr(planning, 'ouvrage', None), 'nomouvrage', 'Sans ouvrage')
                    point_eau_ouvrage_nom = getattr(getattr(point_eau, 'ouvrage', None), 'nomouvrage', 'Sans ouvrage')
                    point_eau_label = point_eau.code_point_eau or point_eau.nomabonne or str(point_eau.id)
                    errors.append(
                        f"Ligne {row_idx}: incoherence paiement forfaitaire - le point d'eau "
                        f"{point_eau_label} appartient a '{point_eau_ouvrage_nom}' et pas a "
                        f"l'ouvrage du planning '{planning_ouvrage_nom}'"
                    )
                    continue

                try:
                    q_raw = str(quantite).strip().replace(' ', '').replace(',', '.')
                    quantite_int = int(float(q_raw))
                except Exception:
                    errors.append(f"Ligne {row_idx}: Quantite invalide")
                    continue
                def _to_float(value):
                    if value in [None, '']:
                        return None
                    try:
                        return float(str(value).strip().replace(' ', '').replace(',', '.'))
                    except Exception:
                        return None

                prix_unit_val = _to_float(prix_unitaire)
                if prix_unit_val is None:
                    prix_unit_val = float(point_eau.tarifforfaitaire or 0)

                if montant_excel not in [None, '']:
                    try:
                        montant_val = float(montant_excel)
                    except Exception:
                        montant_val = float(quantite_int) * float(prix_unit_val)
                else:
                    montant_val = float(quantite_int) * float(prix_unit_val)

                paye = str(paye_str).strip().lower() in ['oui', 'yes', 'true', '1'] if paye_str else False

                paiement_data = {
                    'point_eau': point_eau,
                    'planning': planning,
                    'date_facture': date_facture,
                    'quantite': quantite_int,
                    'prix_unitaire': prix_unit_val,
                    'montant': montant_val,
                    'paye': paye,
                    'date_paiement': date_paiement,
                    'numeroDiameX': str(numero_diamex).strip() if numero_diamex else '',
                    'baseDiameX': str(base_diamex).strip() if base_diamex else '',
                    'date_debut_validite': date_debut_validite,
                    'date_fin_validite': date_fin_validite,
                    'remarque': remarque or ''
                }

                if paiement_id:
                    try:
                        paiement = PaiementForfaitaire.objects.get(id=paiement_id)
                        for key, value in paiement_data.items():
                            setattr(paiement, key, value)
                        paiement.save()
                        updated_count += 1
                    except PaiementForfaitaire.DoesNotExist:
                        errors.append(f"Ligne {row_idx}: Paiement {paiement_id} introuvable")
                else:
                    PaiementForfaitaire.objects.create(**paiement_data)
                    created_count += 1

            except Exception as e:
                errors.append(f"Ligne {row_idx}: {str(e)}")

        message = f"Import terminé: {created_count} créés"
        if errors:
            message += f" (avec {len(errors)} erreurs)"

        return JsonResponse({
            'success': True,
            'message': message,
            'created': created_count,
            'updated': updated_count,
            'errors': errors
        })

    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Erreur: {str(e)}'})


# ==================== EXPORT / IMPORT PARTICIPANTS ====================

def export_excel_participants(request):
    """Export des participants (planning_employees) en Excel"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from django.http import HttpResponse

    wb = Workbook()
    ws = wb.active
    ws.title = "Participants"

    headers = [
        'Planning ID (UUID)*',
        'Participant (Surnom)*',
        'Present (Oui/Non)',
        'Notes'
    ]
    ws.append(headers)

    header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')

    participants = PlanningEmploye.objects.select_related('planning', 'planning__ouvrage', 'employee').order_by('-created_at')

    for p in participants:
        employe_surnom = ''
        employe_nom = ''
        if p.employee:
            employe_surnom = p.employee.surnom or p.employee.prenom or ''
            employe_nom = p.employee.nom_affichage if hasattr(p.employee, 'nom_affichage') else str(p.employee)

        planning_date = p.planning.date.strftime('%Y-%m-%d') if p.planning and p.planning.date else ''
        ouvrage_nom = p.planning.ouvrage.nom_ouvrage if p.planning and p.planning.ouvrage else ''

        ws.append([
            str(p.id),
            str(p.planning_id) if p.planning_id else '',
            employe_surnom,
            'Oui' if p.is_present else 'Non',
            p.notes or '',
            employe_nom,
            planning_date,
            ouvrage_nom,
            p.created_at.strftime('%Y-%m-%d %H:%M') if p.created_at else '',
            p.updated_at.strftime('%Y-%m-%d %H:%M') if p.updated_at else ''
        ])

    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except Exception:
                pass
        ws.column_dimensions[column_letter].width = min(max_length + 2, 50)

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=participants_export.xlsx'
    wb.save(response)
    return response


def template_excel_participants(request):
    """Template Excel pour l'import des participants"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.comments import Comment
    from django.http import HttpResponse

    wb = Workbook()
    ws = wb.active
    ws.title = "Template Participants"

    headers = [
        'Planning ID (UUID)*',
        'Participant (Surnom)*',
        'Présent (Oui/Non)',
        'Notes'
    ]
    ws.append(headers)

    header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    comments = [
        "UUID du planning (obligatoire)",
        "Surnom du participant (autre que l'employe principal)",
        "Present: Oui/Non (optionnel, defaut: Oui)",
        "Notes (optionnel)"
    ]

    for idx, cell in enumerate(ws[1]):
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')
        cell.comment = Comment(comments[idx], "Hydria")

    ws.append([
        '',
        'JOHN',
        'Oui',
        ''
    ])

    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except Exception:
                pass
        ws.column_dimensions[column_letter].width = min(max_length + 2, 50)

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=template_participants.xlsx'
    wb.save(response)
    return response


@api_view(['POST'])
def import_excel_participants(request):
    """Import des participants depuis Excel"""
    import openpyxl

    if 'file' not in request.FILES:
        return JsonResponse({'success': False, 'message': 'Aucun fichier fourni'})

    file = request.FILES['file']

    try:
        wb = openpyxl.load_workbook(file)
        ws = wb.active

        header_row = [str(c).strip().lower() if c is not None else '' for c in next(ws.iter_rows(min_row=1, max_row=1, values_only=True))]
        def _find_idx(*keys):
            for i, h in enumerate(header_row):
                for k in keys:
                    if k in h:
                        return i
            return None

        idx_planning = _find_idx('planning id', 'id planning')
        idx_point = _find_idx('point d', 'point eau', 'point_eau', 'id point')
        idx_date = _find_idx('date facture', 'date_facture')
        idx_quantite = _find_idx('quantite')
        idx_pu = _find_idx('prix unitaire', 'pu')
        idx_montant = _find_idx('montant')
        idx_paye = _find_idx('paye')
        idx_date_paiement = _find_idx('date paiement', 'date_paiement')
        idx_num_diamex = _find_idx('numero diamex', 'num diamex', 'numerodiamex')
        idx_base_diamex = _find_idx('base diamex')
        idx_debut = _find_idx('date debut', 'debut validite')
        idx_fin = _find_idx('date fin', 'fin validite')
        idx_remarque = _find_idx('remarque', 'note')

        created_count = 0
        updated_count = 0
        skipped_main = 0
        errors = []

        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row[0] or not row[1]:
                continue

            try:
                participation_id = None
                col_offset = 0

                try:
                    from uuid import UUID
                    candidate_id = str(row[0]).strip()
                    UUID(candidate_id)
                    if PlanningEmploye.objects.filter(id=candidate_id).exists():
                        participation_id = candidate_id
                        col_offset = 1
                except Exception:
                    pass

                planning_id = row[col_offset + 0] if len(row) > col_offset + 0 else None
                employe_surnom = row[col_offset + 1] if len(row) > col_offset + 1 else None
                present_str = row[col_offset + 2] if len(row) > col_offset + 2 else None
                notes = row[col_offset + 3] if len(row) > col_offset + 3 else None

                if not planning_id or not employe_surnom:
                    continue

                try:
                    planning = Planning.objects.get(id=str(planning_id).strip())
                except Planning.DoesNotExist:
                    errors.append(f"Ligne {row_idx}: Planning {planning_id} introuvable")
                    continue

                employe_val = str(employe_surnom).strip()
                employe = Employe.objects.filter(
                    Q(surnom__iexact=employe_val) |
                    Q(prenom__iexact=employe_val) |
                    Q(nom__iexact=employe_val) |
                    Q(nom_employe__iexact=employe_val)
                ).first()

                if not employe:
                    errors.append(f"Ligne {row_idx}: Employé '{employe_surnom}' introuvable")
                    continue

                is_present = True if present_str is None else str(present_str).strip().lower() in ['oui', 'yes', 'true', '1']

                if employe and planning.employe_id and str(employe.id) == str(planning.employe_id):
                    # Ne pas dupliquer l'employe principal dans la table participants
                    skipped_main += 1
                    continue

                if participation_id:
                    try:
                        participation = PlanningEmploye.objects.get(id=participation_id)
                        participation.planning = planning
                        participation.employee = employe
                        participation.is_present = is_present
                        participation.notes = notes or ''
                        participation.save()
                        updated_count += 1
                    except PlanningEmploye.DoesNotExist:
                        errors.append(f"Ligne {row_idx}: Participation {participation_id} introuvable")
                else:
                    participation, created = PlanningEmploye.objects.get_or_create(
                        planning=planning,
                        employee=employe,
                        defaults={'is_present': is_present, 'notes': notes or ''}
                    )
                    if created:
                        created_count += 1
                    else:
                        participation.is_present = is_present
                        participation.notes = notes or ''
                        participation.save()
                        updated_count += 1

            except Exception as e:
                errors.append(f"Ligne {row_idx}: {str(e)}")

        message = f"Import terminé: {created_count} créés"
        if skipped_main:
            message += f" | {skipped_main} ignor?(s) (employ? principal)"
        if errors:
            message += f" (avec {len(errors)} erreurs)"

        return JsonResponse({
            'success': True,
            'skipped_main': skipped_main,
            'message': message,
            'created': created_count,
            'updated': updated_count,
            'errors': errors
        })

    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Erreur: {str(e)}'})


# ==================== GESTION DES DÃ‰PLACEMENTS ====================

@employe_required
def deplacements_list(request):
    """Liste et gestion des déplacements"""
    from .models import Deplacement
    from apps.geography.models import Village
    
    # Récupérer tous les déplacements
    deplacements = Deplacement.objects.select_related('point_a', 'point_b').order_by('-date_prix')
    
    # Filtres
    point_a_filter = request.GET.get('point_a', '')
    point_b_filter = request.GET.get('point_b', '')
    moyen_transport_filter = request.GET.get('moyen_transport', '')
    
    if point_a_filter:
        deplacements = deplacements.filter(point_a_id=point_a_filter)
    if point_b_filter:
        deplacements = deplacements.filter(point_b_id=point_b_filter)
    if moyen_transport_filter:
        deplacements = deplacements.filter(moyen_transport=moyen_transport_filter)
    
    # Récupérer tous les villages pour les filtres
    villages = Village.objects.all().order_by('nom_village')
    
    context = {
        'deplacements': deplacements,
        'villages': villages,
        'moyen_transport_choices': Deplacement.MOYEN_TRANSPORT_CHOICES,
        'point_a_filter': point_a_filter,
        'point_b_filter': point_b_filter,
        'moyen_transport_filter': moyen_transport_filter,
    }
    
    return render(request, 'planning/deplacements_list.html', context)


@api_view(['POST'])
def deplacement_create(request):
    """Créer un nouveau déplacement"""
    from .models import Deplacement
    from apps.geography.models import Village
    from datetime import datetime
    
    try:
        point_a_id = request.POST.get('point_a')
        point_b_id = request.POST.get('point_b')
        moyen_transport = request.POST.get('moyen_transport')
        prix_unitaire = request.POST.get('prix_unitaire')
        date_prix = request.POST.get('date_prix')
        
        # Validation
        if not all([point_a_id, point_b_id, moyen_transport, prix_unitaire, date_prix]):
            return JsonResponse({
                'success': False,
                'message': 'Tous les champs sont obligatoires'
            }, status=400)
        
        # Vérifier que les villages existent
        try:
            point_a = Village.objects.get(id=point_a_id)
            point_b = Village.objects.get(id=point_b_id)
        except Village.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Village introuvable'
            }, status=404)
        
        # Créer le déplacement
        deplacement = Deplacement.objects.create(
            point_a=point_a,
            point_b=point_b,
            moyen_transport=moyen_transport,
            prix_unitaire=prix_unitaire,
            date_prix=datetime.strptime(date_prix, '%Y-%m-%d').date()
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Déplacement créé avec succès',
            'deplacement_id': str(deplacement.id)
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur: {str(e)}'
        }, status=500)


@api_view(['POST'])
def deplacement_update(request, deplacement_id):
    """Modifier un déplacement"""
    from .models import Deplacement
    from apps.geography.models import Village
    from datetime import datetime
    
    try:
        deplacement = get_object_or_404(Deplacement, id=deplacement_id)
        
        point_a_id = request.POST.get('point_a')
        point_b_id = request.POST.get('point_b')
        moyen_transport = request.POST.get('moyen_transport')
        prix_unitaire = request.POST.get('prix_unitaire')
        date_prix = request.POST.get('date_prix')
        
        # Validation
        if not all([point_a_id, point_b_id, moyen_transport, prix_unitaire, date_prix]):
            return JsonResponse({
                'success': False,
                'message': 'Tous les champs sont obligatoires'
            }, status=400)
        
        # Vérifier que les villages existent
        try:
            point_a = Village.objects.get(id=point_a_id)
            point_b = Village.objects.get(id=point_b_id)
        except Village.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Village introuvable'
            }, status=404)
        
        # Mettre Ã  jour
        deplacement.point_a = point_a
        deplacement.point_b = point_b
        deplacement.moyen_transport = moyen_transport
        deplacement.prix_unitaire = prix_unitaire
        deplacement.date_prix = datetime.strptime(date_prix, '%Y-%m-%d').date()
        deplacement.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Déplacement modifié avec succès'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur: {str(e)}'
        }, status=500)


@api_view(['POST'])
def deplacement_delete(request, deplacement_id):
    """Supprimer un déplacement"""
    from .models import Deplacement

    try:
        deplacement = get_object_or_404(Deplacement, id=deplacement_id)
        deplacement.delete()

        return JsonResponse({
            'success': True,
            'message': 'Déplacement supprimé avec succès'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erreur: {str(e)}'
        }, status=500)


# ========== API ENDPOINTS POUR FILTRES EN CASCADE ==========

@api_view(['GET'])
@permission_classes([AllowAny])
def api_activites_par_poste(request):
    """Récupère les activités autorisées pour un poste donné"""
    poste_id = request.GET.get('poste_id')
    type_activite_id = request.GET.get('type_activite_id')

    if not poste_id:
        return Response({'error': 'poste_id requis'}, status=400)

    # Récupérer les activités liées au poste via ActivitePoste
    from .models import ActivitePoste, Activite
    activites_postes = ActivitePoste.objects.filter(
        poste_id=poste_id,
        is_active=True
    ).select_related('fiche_poste', 'fiche_poste__type_activites')

    # Filtrer par type d'activité si fourni
    if type_activite_id:
        activites_postes = activites_postes.filter(activite__type_activite_id=type_activite_id)

    data = [{
        'id': str(ap.activite.id),
        'nom': ap.activite.nom,
        'type_activite_id': str(ap.activite.type_activite.id),
        'type_activite_nom': ap.activite.type_activite.nomtype
    } for ap in activites_postes]

    return Response(data)


@api_view(['GET'])
@permission_classes([AllowAny])
def api_equipements_par_ouvrage(request):
    """Récupère les équipements d'un ouvrage"""
    ouvrage_id = request.GET.get('ouvrage_id')

    if not ouvrage_id:
        return Response({'error': 'ouvrage_id requis'}, status=400)

    from apps.infrastructure.models import EquipementConstitutif
    equipements = EquipementConstitutif.objects.filter(
        ouvrage_id=ouvrage_id
    ).order_by('nom')

    data = [{
        'id': str(eq.id),
        'nom': eq.nom
    } for eq in equipements]

    return Response(data)


@api_view(['GET'])
@permission_classes([AllowAny])
def api_pointseaus_par_ouvrage(request):
    """Récupère les points d'eau d'un ouvrage"""
    ouvrage_id = request.GET.get('ouvrage_id')

    if not ouvrage_id:
        return Response({'error': 'ouvrage_id requis'}, status=400)

    from apps.billing.models import PointEau
    points_eau = PointEau.objects.filter(
        ouvrage_id=ouvrage_id
    ).order_by('idxls')

    data = [{
        'id': str(pe.id),
        'idxls': pe.idxls,
        'tarif_forfaitaire': float(pe.tarifforfaitaire) if pe.tarifforfaitaire else 0
    } for pe in points_eau]

    return Response(data)


@api_view(['GET'])
@permission_classes([AllowAny])
def api_designations_par_type_activite(request):
    """Récupère les désignations autorisées pour un type d'activité"""
    type_activite_id = request.GET.get('type_activite_id')

    if not type_activite_id:
        return Response({'error': 'type_activite_id requis'}, status=400)

    from .models import DesignationTypeActivite
    designations_types = DesignationTypeActivite.objects.filter(
        type_activite_id=type_activite_id,
        is_active=True
    ).select_related('designation', 'designation__type_designation')

    data = [{
        'id': str(dt.designation.id),
        'nom': dt.designation.nom,
        'prix_unitaire': float(dt.designation.prix_unitaire) if dt.designation.prix_unitaire else None,
        'type_avance_caissiere': dt.designation.type_avance_caissiere,
        'concerne_livraison': dt.designation.concerne_livraison
    } for dt in designations_types]

    return Response(data)


@api_view(['GET'])
@permission_classes([AllowAny])
def api_compte_par_designation(request):
    """Récupère le compte par défaut pour une désignation"""
    designation_id = request.GET.get('designation_id')

    if not designation_id:
        return Response({'error': 'designation_id requis'}, status=400)

    from .models import DesignationCompte
    from apps.organization.models import Compte

    # Récupérer le premier compte actif lié Ã  cette désignation
    designation_compte = DesignationCompte.objects.filter(
        designation_id=designation_id,
        is_active=True
    ).select_related('compte').first()

    if designation_compte:
        return Response({
            'id': str(designation_compte.compte.id),
            'nom': designation_compte.compte.nom_compte
        })

    return Response(None)


@api_view(['GET'])
@permission_classes([AllowAny])
def api_prix_deplacement(request):
    """Récupère le prix unitaire d'un déplacement entre deux points"""
    point_a_id = request.GET.get('point_a_id')
    point_b_id = request.GET.get('point_b_id')
    moyen_transport = request.GET.get('moyen_transport', 'taxi-brousse')

    if not point_a_id or not point_b_id:
        return Response({'error': 'point_a_id et point_b_id requis'}, status=400)

    from .models import Deplacement

    # Chercher le déplacement correspondant (dans les deux sens)
    deplacement = Deplacement.objects.filter(
        Q(point_a_id=point_a_id, point_b_id=point_b_id) |
        Q(point_a_id=point_b_id, point_b_id=point_a_id),
        moyen_transport=moyen_transport
    ).order_by('-date_prix').first()

    donnees = {'prix_unitaire': float(deplacement.prix_unitaire),
               'date_prix': deplacement.date_prix.isoformat()} if deplacement else {'prix_unitaire': None}
    if request.user.is_authenticated:
        donnees.update(_trajet_routier(point_a_id, point_b_id, moyen_transport))
    return Response(donnees)


def _trajet_routier(point_a_id, point_b_id, moyen_transport='taxi-brousse'):
    """Distance et durée par le réseau routier entre deux villages (vide si indisponible).

    Un billet de taxi-brousse est un trajet en véhicule routier (profil « voiture ») ; pirogue et bac
    ne suivent pas les routes : pas de calcul.
    """
    vide = {'distance_route_km': None, 'duree_route_min': None, 'profil_route': None, 'part_sentier_pct': None}
    if moyen_transport not in (None, '', 'taxi-brousse'):
        return vide
    try:
        from apps.geography.services import itineraire
        r = itineraire.itineraire_villages(point_a_id, point_b_id, profil='voiture')
        rep = r['repartition_m']
        total = sum(rep.values()) or 1
        part_sentier = (rep.get('sentier', 0) + rep.get('marche', 0)) / total
        return {'distance_route_km': round(r['distance_m'] / 1000, 2), 'duree_route_min': round(r['duree_s'] / 60),
                'profil_route': 'voiture', 'part_sentier_pct': round(part_sentier * 100)}
    except Exception:  # village inconnu, hors réseau... : l'information est facultative
        return vide


@api_view(['GET'])
@permission_classes([AllowAny])
def api_villages_deplacement(request):
    """Récupère les villages de destination possibles depuis un point A"""
    point_a_id = request.GET.get('point_a_id')
    moyen_transport = request.GET.get('moyen_transport', 'taxi-brousse')

    if not point_a_id:
        return Response({'error': 'point_a_id requis'}, status=400)

    from .models import Deplacement
    from apps.geography.models import Village

    # Récupérer les destinations possibles depuis ce point
    deplacements = Deplacement.objects.filter(
        point_a_id=point_a_id,
        moyen_transport=moyen_transport
    ).select_related('point_b').order_by('point_b__nom_village')

    data = [{
        'id': str(d.point_b.id),
        'nom': d.point_b.nom_village,
        'prix_unitaire': float(d.prix_unitaire)
    } for d in deplacements]

    return Response(data)


from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods as req_http_methods

@csrf_exempt
@req_http_methods(["POST"])
def create_planning(request):
    """API pour créer un planning de réparation"""
    import pytz
    import logging
    import json
    logger = logging.getLogger(__name__)

    try:
        # Récupérer les données depuis request.body (JSON standard)
        data = json.loads(request.body)
        logger.info(f"Données reçues: {data}")

        def _as_bool(value):
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return value != 0
            if isinstance(value, str):
                return value.strip().lower() in ('1', 'true', 'vrai', 'yes', 'oui', 'on')
            return False

        ouvrage_id = data.get('ouvrage_id')
        activite_id = data.get('activite_id')
        fiche_poste_id = data.get('fiche_poste_id')
        date_str = data.get('date')
        employe_id = data.get('employe_id')
        remarque = data.get('remarque', '')
        detail_payload = data.get('detail') or {}
        details_payload = data.get('details')
        bons_payload = data.get('bons_livraison')
        validation_requested = _as_bool(data.get('validation') or data.get('estvalide'))
        repair_point_eau_id = (data.get('point_eau_id') or '').strip()
        repair_equipement_id = (data.get('equipement_id') or '').strip()

        # Validation
        if not ouvrage_id or not date_str or not (fiche_poste_id or activite_id):
            return JsonResponse({
                'success': False,
                'error': 'Ouvrage, fiche de poste et date sont obligatoires'
            }, status=400)
        if repair_point_eau_id and repair_equipement_id:
            return JsonResponse({
                'success': False,
                'error': "La réparation ne peut pas cibler à la fois un point d'eau et un équipement"
            }, status=400)

        activite = None
        fiche_poste = None
        if fiche_poste_id:
            from types import SimpleNamespace
            try:
                fiche_poste = FichePoste.objects.select_related('type_activites').get(id=fiche_poste_id)
                activite = SimpleNamespace(
                    id=fiche_poste.id,
                    nom=fiche_poste.tache or '',
                    type_activite=fiche_poste.type_activites,
                    type_activite_id=fiche_poste.type_activites_id,
                )
                activite_id = str(fiche_poste.id)
            except FichePoste.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Fiche de poste introuvable'
                }, status=404)

        # Recuperer l'ouvrage et l'activite
        try:
            ouvrage = Ouvrage.objects.get(id=ouvrage_id)
            if not activite:
                activite = Activite.objects.select_related('type_activite').get(id=activite_id)
                logger.info(f"Activite trouvee: {activite.nom}, Type: {activite.type_activite}")
            else:
                logger.info(f"Fiche de poste trouvee: {activite.nom}, Type: {activite.type_activite}")
        except (Ouvrage.DoesNotExist, Activite.DoesNotExist) as e:
            return JsonResponse({
                'success': False,
                'error': 'Ouvrage ou activité introuvable'
            }, status=404)

        # BLOQUER la création directe de congés et permissions
        activites_bloquees = ['Congé', 'Congé demi-journée', 'Permission']
        if activite.nom in activites_bloquees:
            return JsonResponse({
                'success': False,
                'error': f'La saisie directe de "{activite.nom}" est bloquée. Veuillez utiliser le module "Demandes de Congés" dans le menu Employés.'
            }, status=403)

        # Convertir la date (format YYYY-MM-DD) en timezone Madagascar
        tz_madagascar = pytz.timezone('Indian/Antananarivo')
        date_naive = datetime.strptime(date_str, '%Y-%m-%d')
        date_obj = tz_madagascar.localize(date_naive)

        # Récupérer l'employé si fourni
        employe = None
        if employe_id:
            try:
                employe = Employe.objects.select_related('poste').get(id=employe_id)
                logger.info(f"Employé trouvé: {employe.surnom}, Poste: {employe.poste if hasattr(employe, 'poste') else 'Aucun'}")
            except Employe.DoesNotExist:
                logger.warning(f"Employé {employe_id} non trouvé")
                pass

        logger.info(f"Création du planning avec type_activite_id={activite.type_activite.id if activite.type_activite else None}")

        repair_point_eau = None
        repair_equipement = None
        if repair_point_eau_id:
            try:
                repair_point_eau = PointEau.objects.get(id=repair_point_eau_id)
            except PointEau.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': "Point d'eau introuvable"
                }, status=404)
        if repair_equipement_id:
            from apps.infrastructure.models import EquipementConstitutif
            try:
                repair_equipement = EquipementConstitutif.objects.get(id=repair_equipement_id)
            except EquipementConstitutif.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Equipement introuvable'
                }, status=404)

        # Déterminer la fiche de poste liée Ã  l'activité
        fiche_poste = fiche_poste
        try:
            ap = ActivitePoste.objects.filter(
                activite_id=activite_id,
                fiche_poste__isnull=False
            ).select_related('fiche_poste').first()
            if ap:
                fiche_poste = ap.fiche_poste

            # Fallback 1: autre activité du mÃªme type avec une fiche de poste liée
            if not fiche_poste and activite.type_activite_id:
                fallback_links = list(
                    ActivitePoste.objects.filter(
                        activite__type_activite_id=activite.type_activite_id,
                        fiche_poste__isnull=False
                    ).select_related('fiche_poste')
                    .order_by('-fiche_poste__dans_planning', 'fiche_poste__ordre', 'fiche_poste__tache')
                )
                if fallback_links:
                    activity_name = (activite.nom or '').lower()
                    keyword = ''
                    if 'panne' in activity_name:
                        keyword = 'panne'
                    elif 'habilitation' in activity_name:
                        keyword = 'habilitation'
                    elif 'paration' in activity_name:
                        keyword = 'paration'

                    selected_link = None
                    if keyword:
                        selected_link = next(
                            (
                                link for link in fallback_links
                                if keyword in (link.fiche_poste.tache or '').lower()
                            ),
                            None
                        )
                    if not selected_link:
                        selected_link = fallback_links[0]
                    fiche_poste = selected_link.fiche_poste

            # Fallback 2: fiche de poste du mÃªme type d'activité
            if not fiche_poste and activite.type_activite_id:
                fiches = list(
                    FichePoste.objects.filter(type_activites_id=activite.type_activite_id)
                    .order_by('-dans_planning', 'ordre', 'tache')
                )
                if fiches:
                    activity_name = (activite.nom or '').lower()
                    keyword = ''
                    if 'panne' in activity_name:
                        keyword = 'panne'
                    elif 'habilitation' in activity_name:
                        keyword = 'habilitation'
                    elif 'paration' in activity_name:
                        keyword = 'paration'

                    if keyword:
                        fiche_poste = next(
                            (fiche for fiche in fiches if keyword in (fiche.tache or '').lower()),
                            None
                        )
                    if not fiche_poste:
                        fiche_poste = fiches[0]
        except Exception:
            fiche_poste = None

        if not fiche_poste:
            return JsonResponse({
                'success': False,
                'error': f"Aucune fiche de poste liée Ã  cette activité ({activite.nom}). Configurez la liaison Activité -> Fiche de poste."
            }, status=400)

        # Créer le planning (sans passer type_activite, laisser Django le gérer)
        planning = Planning.objects.create(
            ouvrage=ouvrage,
            fiche_poste=fiche_poste,
            type_activite_id=activite.type_activite.id if activite.type_activite else None,
            date=date_obj,
            employe=employe,
            remarque=remarque,
            suiteadonner='Ã€ faire',
            estvalide=validation_requested
        )

        from apps.planning.reparation_composants import (
            ComposantsError, apply_repair_target, parse_composants_ids, verifier_regles_fiche,
        )
        try:
            composants_recus = parse_composants_ids(data) or []
            verifier_regles_fiche(fiche_poste, repair_equipement, repair_point_eau, composants_recus)
            apply_repair_target(planning, repair_equipement, repair_point_eau, parse_composants_ids(data))
        except ComposantsError as exc:
            planning.delete()
            return JsonResponse({'success': False, 'error': str(exc)}, status=400)

        # Optionnel: ajouter un ou plusieurs details (table PlanningDetail)
        if isinstance(details_payload, list):
            detail_rows = details_payload
        elif detail_payload:
            detail_rows = [detail_payload]
        else:
            detail_rows = []

        if isinstance(bons_payload, list):
            bon_rows = bons_payload
        else:
            bon_rows = []

        for row in detail_rows:
            designation_id = row.get('designation_id')
            if not designation_id:
                continue

            try:
                designation = Designation.objects.get(id=designation_id)
            except Designation.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Designation detail introuvable'
                }, status=404)

            try:
                quantity = float(row.get('quantity') or 1)
            except (TypeError, ValueError):
                quantity = 1

            try:
                pu = Decimal(str(designation.prix_unitaire or 0))
            except Exception:
                pu = Decimal('0')

            PlanningDetail.objects.create(
                planning=planning,
                designation=designation,
                quantity=quantity,
                pu=pu,
                montant=Decimal('0'),
                equipement_constitutif=repair_equipement,
                point_eau=repair_point_eau,
            )

        # Optionnel: ajouter un ou plusieurs bons de livraison (table BonLivraison)
        for row in bon_rows:
            designation_id = row.get('designation_id')
            if not designation_id:
                continue

            try:
                designation = Designation.objects.get(id=designation_id)
            except Designation.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Designation bon de livraison introuvable'
                }, status=404)

            try:
                quantite = float(row.get('quantite') or row.get('quantity') or 1)
            except (TypeError, ValueError):
                quantite = 1

            magasin = (row.get('magasin') or '').strip() or None

            BonLivraison.objects.create(
                planning=planning,
                designation=designation,
                quantite=quantite,
                magasin=magasin,
                equipement=repair_equipement,
                point_eau=repair_point_eau,
            )

        return JsonResponse({
            'success': True,
            'message': 'Planning de réparation créé avec succès',
            'planning_id': str(planning.id)
        })

    except Exception as e:
        import traceback
        logger.error(f"Erreur lors de la création du planning: {str(e)}")
        logger.error(traceback.format_exc())
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)


def planning_automatique(request):
    automatic_goals = [
        "Automatiser l'inscription au Planning après validation des congés ou récupérations.",
        "Générer automatiquement les repos de fin de semaine et les jours fériés pour les salariés.",
        "Préparer les annulations avec création de récupérations quand nécessaire."
    ]

    contract_rules = [
        {
            'type': 'Journalier',
            'repos_auto': 'Non',
            'jours_feries_auto': 'Non',
            'notes': "Les journaliers gèrent leurs repos/jours fériés manuellement via le planning."
        },
        {
            'type': 'Salarié temps plein',
            'repos_auto': 'Oui (samedi + dimanche)',
            'jours_feries_auto': 'Oui',
            'notes': 'Repos et jours fériés sont créés via les commandes planifiées.'
        },
        {
            'type': 'Salarié temps partiel / mi-temps',
            'repos_auto': 'Oui (samedi + dimanche)',
            'jours_feries_auto': 'Oui',
            'notes': 'Le mécanisme est identique aux temps plein ; le planning évite les doublons.'
        }
    ]

    signals = [
        {
            'name': 'Demande de congé validée',
            'trigger': 'apps.employees.signals_conges.DemandeConge post_save',
            'condition': "instance.statut == 'validee_directeur'",
            'summary': "Inscrit un Planning validé pour chaque jour de la période avec l'activité 'Congé'."
        },
        {
            'name': 'Récupération validée',
            'trigger': 'apps.employees.signals_recuperations.Recuperation post_save',
            'condition': "instance.statut == 'validee_directeur'",
            'summary': 'Crée un Planning validé et marque la récupération comme utilisée.'
        }
    ]

    commands = [
        {
            'title': 'Repos automatiques (samedi + dimanche)',
            'description': 'Crée des plannings Repos validés pour tous les salariés sans doublon.',
            'command': 'python manage.py populate_repos_weekly --weeks 4',
            'note': 'Planifiez une tÃ¢che cron (ex. lundi 06h) pour générer 4 semaines Ã  la fois.'
        },
        {
            'title': 'Jours fériés automatiques',
            'description': 'Génère les plannings pour tous les jours fériés déclarés dans le script.',
            'command': 'python manage.py populate_jours_feries --year 2025',
            'note': "Exécutez au début de l'année (ou lors d'ajout de jours fériés)."
        }
    ]

    cancellation_steps = [
        "Identifier le planning concerné, il doitêtre un Repos ou un Jour férié.",
        "Supprimer le planning via l'interface ou l'API.",
        "Si la date est un dimanche ou un jour férié, créer automatiquement une récupération avec statut 'acquise'.",
        "Les samedis ne génèrent pas de récupération ; le planning disparaÃ®t sans substitution."
    ]

    return render(request, 'planning/planning_automatique.html', {
        'title': 'Planning Automatique',
        'automatic_goals': automatic_goals,
        'contract_rules': contract_rules,
        'signals': signals,
        'commands': commands,
        'cancellation_steps': cancellation_steps
    })

