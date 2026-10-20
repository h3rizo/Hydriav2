from datetime import datetime, time

from django.conf import settings
from django.db.models import Min
from django.utils import timezone


def get_auto_branchement_datetime(point_eau):
    first_releve_date = getattr(point_eau, '_first_releve_date', None)
    if first_releve_date is None:
        first_releve_date = point_eau.releves.aggregate(
            first_releve_date=Min('datereleve')
        )['first_releve_date']

    if not first_releve_date:
        return None

    # Store midday to avoid timezone shifts turning the displayed calendar date
    # into the previous day when this DateTimeField is later rendered directly.
    branchement_dt = datetime.combine(first_releve_date, time(hour=12))
    if settings.USE_TZ and timezone.is_naive(branchement_dt):
        branchement_dt = timezone.make_aware(
            branchement_dt,
            timezone.get_current_timezone(),
        )

    return branchement_dt


def normalize_missing_bp_branchements(queryset):
    candidates = queryset.filter(
        datebranchement__isnull=True,
        releves__isnull=False,
    ).annotate(
        _first_releve_date=Min('releves__datereleve')
    ).distinct()

    updates = []
    for point_eau in candidates:
        branchement_dt = get_auto_branchement_datetime(point_eau)
        if not branchement_dt:
            continue
        point_eau.datebranchement = branchement_dt
        updates.append(point_eau)

    if updates:
        queryset.model.objects.bulk_update(updates, ['datebranchement'])

    return len(updates)


def normalize_missing_bp_branchement(point_eau):
    if point_eau.datebranchement:
        return False

    branchement_dt = get_auto_branchement_datetime(point_eau)
    if not branchement_dt:
        return False

    point_eau.datebranchement = branchement_dt
    point_eau.save(update_fields=['datebranchement'])
    return True
