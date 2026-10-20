import json
from collections import defaultdict
from uuid import UUID

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from apps.billing.models import PointEau
from apps.geography.models import Commune, District


MAX_IDS_PER_LEVEL = 2000


def _valid_uuid_strings(values):
    """Keep only bounded, valid UUIDs received from options already in the DOM."""
    valid = []
    seen = set()
    for value in values if isinstance(values, list) else []:
        raw = str(value or '').strip()
        if not raw or raw in seen:
            continue
        try:
            UUID(raw)
        except (ValueError, TypeError, AttributeError):
            continue
        seen.add(raw)
        valid.append(raw)
        if len(valid) >= MAX_IDS_PER_LEVEL:
            break
    return valid


@login_required
@require_POST
def geographic_filter_hierarchy(request):
    """
    Return hierarchy metadata only for geographic IDs already visible in a page.

    The endpoint does not build filter choices and does not expand their scope. It
    only lets the common frontend group the options that each view already
    authorized and rendered.
    """
    try:
        payload = json.loads(request.body or b'{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'success': False, 'error': 'JSON invalide'}, status=400)

    district_ids = _valid_uuid_strings(payload.get('district_ids', []))
    commune_ids = _valid_uuid_strings(payload.get('commune_ids', []))
    ouvrage_ids = _valid_uuid_strings(payload.get('ouvrage_ids', []))

    districts = {}
    district_rows = District.objects.filter(id__in=district_ids).values(
        'id', 'nom_district', 'region_id', 'region__nom_region'
    )
    for district in district_rows:
        districts[str(district['id'])] = {
            'region_id': str(district['region_id']),
            'region': district['region__nom_region'] or 'Sans région',
            'district': district['nom_district'] or 'Sans district',
        }

    communes = {}
    commune_rows = Commune.objects.filter(id__in=commune_ids).values(
        'id', 'nom_commune',
        'district_id', 'district__nom_district',
        'district__region_id', 'district__region__nom_region',
    )
    for commune in commune_rows:
        communes[str(commune['id'])] = {
            'region_id': str(commune['district__region_id']),
            'region': commune['district__region__nom_region'] or 'Sans région',
            'district_id': str(commune['district_id']),
            'district': commune['district__nom_district'] or 'Sans district',
            'commune': commune['nom_commune'] or 'Sans commune',
        }

    ouvrage_paths = defaultdict(list)
    if ouvrage_ids:
        rows = PointEau.objects.filter(
            ouvrage_id__in=ouvrage_ids,
            parcelle__village__fokontany__commune__district__region__isnull=False,
        ).values(
            'ouvrage_id',
            'parcelle__village__fokontany__commune_id',
            'parcelle__village__fokontany__commune__nom_commune',
            'parcelle__village__fokontany__commune__district_id',
            'parcelle__village__fokontany__commune__district__nom_district',
            'parcelle__village__fokontany__commune__district__region_id',
            'parcelle__village__fokontany__commune__district__region__nom_region',
        ).distinct()

        for row in rows:
            ouvrage_id = str(row['ouvrage_id'])
            ouvrage_paths[ouvrage_id].append({
                'region_id': str(row['parcelle__village__fokontany__commune__district__region_id']),
                'region': row['parcelle__village__fokontany__commune__district__region__nom_region'] or 'Sans région',
                'district_id': str(row['parcelle__village__fokontany__commune__district_id']),
                'district': row['parcelle__village__fokontany__commune__district__nom_district'] or 'Sans district',
                'commune_id': str(row['parcelle__village__fokontany__commune_id']),
                'commune': row['parcelle__village__fokontany__commune__nom_commune'] or 'Sans commune',
            })

    for paths in ouvrage_paths.values():
        paths.sort(key=lambda path: (
            path['region'].lower(),
            path['district'].lower(),
            path['commune'].lower(),
        ))

    return JsonResponse({
        'success': True,
        'districts': districts,
        'communes': communes,
        'ouvrages': dict(ouvrage_paths),
    })
