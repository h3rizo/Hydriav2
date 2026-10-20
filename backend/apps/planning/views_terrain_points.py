"""API mobile : classement des contributeurs Terrain (absolu / mois / semaine / jour)."""
from datetime import datetime, time, timedelta

import pytz
from django.db.models import Sum
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from apps.core.views_mobile_auth import mobile_auth_required
from apps.planning.models_terrain_points import TerrainContribution

TZ = pytz.timezone('Indian/Antananarivo')
PERIODES = ('absolu', 'mois', 'semaine', 'jour')
TAILLE_TOP = 20
NB_COURBES = 3


def _local_midnight(day):
    return TZ.localize(datetime.combine(day, time.min))


def _add_months(day, delta):
    index = day.year * 12 + (day.month - 1) + delta
    return day.replace(year=index // 12, month=index % 12 + 1, day=1)


def _buckets(periode, today):
    """[(etiquette, debut, fin)] : de l'ancien au recent, en heure de Madagascar."""
    out = []
    if periode == 'jour':
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            out.append((d.strftime('%d/%m'), _local_midnight(d), _local_midnight(d + timedelta(days=1))))
    elif periode == 'semaine':
        monday = today - timedelta(days=today.weekday())
        for i in range(7, -1, -1):
            d = monday - timedelta(weeks=i)
            out.append((d.strftime('%d/%m'), _local_midnight(d), _local_midnight(d + timedelta(days=7))))
    else:  # mois et absolu : 6 / 12 derniers mois
        n = 5 if periode == 'mois' else 11
        first = today.replace(day=1)
        for i in range(n, -1, -1):
            d = _add_months(first, -i)
            out.append((d.strftime('%m/%y'), _local_midnight(d), _local_midnight(_add_months(d, 1))))
    return out


def _debut_periode(periode, today):
    if periode == 'jour':
        return _local_midnight(today)
    if periode == 'semaine':
        return _local_midnight(today - timedelta(days=today.weekday()))
    if periode == 'mois':
        return _local_midnight(today.replace(day=1))
    return None


def _nom(employe):
    return (employe.surnom or employe.nom or '').strip() or 'Anonyme'


@mobile_auth_required
@require_http_methods(['GET'])
def api_classement_terrain_mobile(request):
    periode = request.GET.get('periode', 'absolu')
    if periode not in PERIODES:
        periode = 'absolu'
    moi = getattr(request.user, 'employe', None)
    today = datetime.now(TZ).date()

    rows = TerrainContribution.objects.exclude(employe__isnull=True)
    debut = _debut_periode(periode, today)
    if debut:
        rows = rows.filter(created_at__gte=debut)
    totals = list(
        rows.values('employe_id').annotate(points=Sum('points')).order_by('-points', 'employe_id')
    )
    from apps.employees.models import Employe
    noms = {e.id: _nom(e) for e in Employe.objects.filter(id__in=[t['employe_id'] for t in totals])}

    classement = [
        {'rang': i + 1, 'employe_id': str(t['employe_id']), 'nom': noms.get(t['employe_id'], 'Anonyme'),
         'points': int(t['points']), 'moi': bool(moi and t['employe_id'] == moi.id)}
        for i, t in enumerate(totals)
    ]
    ma_ligne = next((c for c in classement if c['moi']), None)

    # Evolution : points par tranche (cumul pour le classement absolu), top 3 + moi.
    buckets = _buckets(periode, today)
    suivis = [c for c in classement[:NB_COURBES]]
    if ma_ligne and ma_ligne not in suivis:
        suivis.append(ma_ligne)
    ids = [c['employe_id'] for c in suivis]
    evo_rows = TerrainContribution.objects.filter(employe_id__in=ids, created_at__gte=buckets[0][1]).values_list(
        'employe_id', 'created_at', 'points')
    par_employe = {i: [0] * len(buckets) for i in ids}
    for employe_id, created_at, points in evo_rows:
        for index, (_, start, end) in enumerate(buckets):
            if start <= created_at < end:
                par_employe[str(employe_id)][index] += points
                break
    if periode == 'absolu':
        avant = {
            str(r['employe_id']): int(r['p'])
            for r in TerrainContribution.objects.filter(employe_id__in=ids, created_at__lt=buckets[0][1])
            .values('employe_id').annotate(p=Sum('points'))
        }
        for employe_id, serie in par_employe.items():
            cumul = avant.get(employe_id, 0)
            for index, value in enumerate(serie):
                cumul += value
                serie[index] = cumul

    total_absolu = TerrainContribution.objects.filter(employe=moi).aggregate(t=Sum('points'))['t'] or 0 if moi else 0
    aujourdhui = TerrainContribution.objects.filter(
        employe=moi, created_at__gte=_local_midnight(today)).aggregate(t=Sum('points'))['t'] or 0 if moi else 0
    return JsonResponse({
        'success': True,
        'periode': periode,
        'classement': classement[:TAILLE_TOP],
        'participants': len(classement),
        'moi': {
            'rang': ma_ligne['rang'] if ma_ligne else None,
            'points_periode': ma_ligne['points'] if ma_ligne else 0,
            'points_total': int(total_absolu),
            'points_aujourdhui': int(aujourdhui),
        },
        'evolution': {
            'labels': [b[0] for b in buckets],
            'series': [
                {'nom': c['nom'], 'moi': c['moi'], 'points': par_employe[c['employe_id']]}
                for c in suivis
            ],
        },
    })
