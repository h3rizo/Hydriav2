"""
API for cascading filters on the repairs dashboard.
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from apps.billing.models import PointEau
from apps.geography.models import Commune, District, Region
from apps.organization.models import Ouvrage
from apps.organization.scoping import (
    get_default_gestionnaire_filter_value,
    get_user_accessible_gestionnaire_ids,
)
from apps.planning import views_simple
from apps.planning.views_reparations import (
    _get_responsable_employes_for_ouvrage_ids,
    _get_user_scoped_ouvrage_ids,
)


def _get_selected_organisation_id(request, gestionnaire_ids):
    selected = (request.GET.get('organisation') or '').strip()
    if selected and selected.lower() == 'all':
        selected = ''
    if selected:
        return selected

    return get_default_gestionnaire_filter_value(request.user, gestionnaire_ids) or 'all'


def _get_scoped_ouvrage_ids(request):
    gestionnaire_ids = get_user_accessible_gestionnaire_ids(request.user)
    organisation_id = _get_selected_organisation_id(request, gestionnaire_ids)
    annee_filter = (request.GET.get('annee') or '').strip()
    try:
        annee_int = int(annee_filter) if annee_filter and annee_filter != 'all' else None
    except (TypeError, ValueError):
        annee_int = None

    return _get_user_scoped_ouvrage_ids(
        organisation_id,
        gestionnaire_ids,
        request.user,
        annee=annee_int,
    )


@require_http_methods(["GET"])
def api_get_filter_options(request):
    """Return scoped region, district and commune options."""
    try:
        region_id = request.GET.get('region_id', 'all')
        district_id = request.GET.get('district_id', 'all')
        commune_id = request.GET.get('commune_id', 'all')

        scoped_ouvrage_ids = _get_scoped_ouvrage_ids(request)
        if not scoped_ouvrage_ids:
            return JsonResponse({
                'success': True,
                'regions': [],
                'districts': [],
                'communes': [],
                'employes': [],
            })

        ouvrages_qs = Ouvrage.objects.filter(
            id__in=scoped_ouvrage_ids,
            type_ouvrage__existe=True
        ).distinct()

        employes_ouvrages_qs = ouvrages_qs
        if commune_id and commune_id != 'all':
            employes_ouvrages_qs = employes_ouvrages_qs.filter(
                pointeau__parcelle__village__fokontany__commune_id=commune_id
            ).distinct()
        elif district_id and district_id != 'all':
            employes_ouvrages_qs = employes_ouvrages_qs.filter(
                pointeau__parcelle__village__fokontany__commune__district_id=district_id
            ).distinct()
        elif region_id and region_id != 'all':
            employes_ouvrages_qs = employes_ouvrages_qs.filter(
                pointeau__parcelle__village__fokontany__commune__district__region_id=region_id
            ).distinct()

        points_eau_ids = PointEau.objects.filter(
            ouvrage__in=ouvrages_qs
        ).values_list('id', flat=True)

        communes_ids = PointEau.objects.filter(
            id__in=points_eau_ids,
            parcelle__village__fokontany__commune__isnull=False
        ).values_list('parcelle__village__fokontany__commune_id', flat=True).distinct()

        regions = Region.objects.filter(
            districts__communes__id__in=communes_ids
        ).distinct().order_by('nom_region')

        if region_id and region_id != 'all':
            districts = District.objects.filter(
                region_id=region_id,
                communes__id__in=communes_ids
            ).distinct().order_by('nom_district')
        else:
            districts = District.objects.filter(
                communes__id__in=communes_ids
            ).distinct().order_by('nom_district')

        if district_id and district_id != 'all':
            communes = Commune.objects.filter(
                id__in=communes_ids,
                district_id=district_id
            ).distinct().order_by('nom_commune')
        elif region_id and region_id != 'all':
            communes = Commune.objects.filter(
                id__in=communes_ids,
                district__region_id=region_id
            ).distinct().order_by('nom_commune')
        else:
            communes = Commune.objects.filter(
                id__in=communes_ids
            ).distinct().order_by('nom_commune')

        responsibles_qs = _get_responsable_employes_for_ouvrage_ids(
            employes_ouvrages_qs.values_list('id', flat=True)
        )
        scoped_employee_ids = set(
            views_simple._get_scoped_employees_queryset(request.user).values_list('id', flat=True)
        )
        employes = responsibles_qs.filter(
            id__in=scoped_employee_ids
        ).select_related('base', 'poste').order_by(
            'base__nom_base', 'poste__nom_poste', 'surnom', 'nom', 'prenom'
        )

        return JsonResponse({
            'success': True,
            'regions': [{'id': str(r.id), 'nom': r.nom_region} for r in regions],
            'districts': [{'id': str(d.id), 'nom': d.nom_district} for d in districts],
            'communes': [{'id': str(c.id), 'nom': c.nom_commune} for c in communes],
            'employes': [
                {
                    'id': str(employe.id),
                    'nom': employe.surnom or getattr(employe, 'nom_complet', None) or employe.nom_employe,
                    'base_name': employe.base.nom_base if employe.base else 'Sans base',
                    'poste_name': employe.poste.nom_poste if employe.poste else 'Sans poste',
                }
                for employe in employes
            ],
        })
    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)
