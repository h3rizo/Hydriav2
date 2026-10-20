import base64
import binascii
import json
import uuid
from datetime import date, timedelta

import pytz
from django.contrib.auth import authenticate
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Case, Count, IntegerField, Max, Q, Sum, Value, When
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from urllib.parse import urlencode
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.organization.models import Ouvrage, Organisation, Base
from apps.organization.scoping import (
    get_user_accessible_gestionnaire_ids,
    get_user_default_scope_organisation_id,
    get_user_organisation,
    is_partenaire_user,
)
from apps.billing.models import (
    PointEau, Releve, ReleveCompteurTete,
    PaiementForfaitaire, TarifVolumetrique,
)
from apps.billing.points_eau_statut import compter_statuts, q_actif, statut_of
from apps.accounting.models import BaseDiameX
from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_generique
from apps.accounting.views_verification_ouvrages import diviser_paiement_volume_multi
from apps.planning.models import DebitSourceMesure, Planning, TypeActivite
from apps.planning.views import _get_debit_status_label, _get_ouvrage_debit_context
from apps.planning.repair_classification import get_repair_fiches_queryset
from apps.planning.views_reparations import (
    _get_scoped_organisations_for_user,
    _get_default_repair_organisation_id,
    _get_scoped_ouvrage_ids,
    _apply_employe_hierarchy_ouvrage_scope,
    _get_active_subordinate_employe_ids,
)
from apps.geography.models import Region, District, Commune
from apps.employees.permissions import filter_queryset_by_permissions, is_directeur_poste
from apps.employees.models import Employe, EmployeOuvrages
from apps.organization.views_compteurs_releves import (
    _allowed_compteurs_queryset,
    _get_initial_releve_ids,
    _get_releve_gap_classification,
)
from apps.core.models import InterventionWidgetRead, InterventionWidgetState, WidgetAuthToken
from apps.core.auth_tokens import token_or_session_required

TZ_MADAGASCAR = pytz.timezone('Indian/Antananarivo')
WIDGET_ACCOUNTING_CUTOFF = date(2026, 1, 1)


def _diamex_pair(numero, base):
    numero_value = str(numero or '').strip().lower()
    base_value = str(base or '').strip().lower()
    return (numero_value, base_value) if numero_value and base_value else None


def _billing_month_start(releve_date):
    """Mois de facture Hydria : le mois suivant celui du relevé."""
    if not releve_date:
        return None
    if releve_date.month == 12:
        return date(releve_date.year + 1, 1, 1)
    return date(releve_date.year, releve_date.month + 1, 1)


_MOIS_FR = (
    '', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
    'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre',
)


def _mois_facture_label(month_date):
    """Libellé court du mois de facture, ex. 'Septembre' (pour l'UI du widget)."""
    if not month_date:
        return ''
    return _MOIS_FR[month_date.month]


def _was_updated_during_current_month(updated_at, month_start, today_mg):
    if not updated_at:
        return False
    if timezone.is_aware(updated_at):
        updated_date = updated_at.astimezone(TZ_MADAGASCAR).date()
    else:
        updated_date = updated_at.date()
    return month_start <= updated_date <= today_mg


def _widget_coupure_periods(point_eau_ids):
    """Périodes de coupure par point d'eau (source unique apps.accounting.views)."""
    from apps.accounting.views import _build_coupure_periods_by_point
    return _build_coupure_periods_by_point(list(point_eau_ids or []))


def _is_widget_releve_non_recouvrable(releve, periodes_coupure=None):
    """Règle "hors recouvrement" d'une facture non pointée.

    Règle par période (apps.accounting.views._is_releve_during_coupure, mode
    facturation) : une facture sort du montant à recouvrer dès que son mois
    comptable (mois du relevé + 1) chevauche une coupure du point d'eau — donc
    "à partir du moment où il est coupé", y compris après remise en service et
    même si la coupure n'est tracée que par des événements CoupureEau.

    Sans périodes fournies, repli sur la règle "point actuellement coupé" du
    dashboard Paiements Volume (_is_releve_non_recouvrable).
    """
    from apps.accounting.views import (
        _is_releve_during_coupure,
        _is_releve_non_recouvrable,
    )
    if periodes_coupure is not None:
        return _is_releve_during_coupure(
            releve, periodes_coupure, check_facturation_month=True,
        )
    return _is_releve_non_recouvrable(releve)


def _active_collection_employee_scope(ouvrage_ids, selected_employee_id=''):
    """Options et périmètre des agents de recouvrement responsables actifs."""
    scope_ids = {value for value in (ouvrage_ids or []) if value}
    selected_employee_id = str(selected_employee_id or '').strip()
    if not scope_ids:
        return [], set()

    today_mg = timezone.now().astimezone(TZ_MADAGASCAR).date()
    relations = EmployeOuvrages.objects.filter(
        ouvrage_id__in=scope_ids,
        date_debut__lte=today_mg,
        employe__date_debauchage__isnull=True,
        employe__poste__nom_poste__icontains='recouvrement',
    ).filter(
        Q(date_fin__isnull=True) | Q(date_fin__gte=today_mg)
    ).select_related('employe', 'employe__poste').order_by(
        'employe__nom', 'employe__prenom', 'ouvrage__nom_ouvrage'
    )

    employees = {}
    ouvrage_ids_by_employee = {}
    for relation in relations:
        employee_id = str(relation.employe_id)
        employees[employee_id] = relation.employe
        ouvrage_ids_by_employee.setdefault(employee_id, set()).add(relation.ouvrage_id)

    options = []
    for employee_id, employee in employees.items():
        options.append({
            'id': employee_id,
            'nom': employee.nom_affichage,
            'poste': getattr(getattr(employee, 'poste', None), 'nom_poste', '') or '',
            'ouvrage_ids': [str(value) for value in ouvrage_ids_by_employee[employee_id]],
        })
    options.sort(key=lambda item: (item['nom'].casefold(), item['poste'].casefold()))

    if selected_employee_id and selected_employee_id in ouvrage_ids_by_employee:
        return options, ouvrage_ids_by_employee[selected_employee_id]
    return options, scope_ids


def _diamex_non_pointed_ids(ouvrage_ids, today_mg):
    """Retourne les lignes 748411/707401 sans facture pointée dans le périmètre.

    Retourne un tuple (ids_par_compte, pointed_volume_by_period). Le second
    élément est réutilisé par api_widget_details pour détailler, segment par
    segment, quelle période exacte d'une ligne 707401 multi-segments reste
    à pointer (une ligne peut avoir un segment déjà pointé et un autre non).
    """
    ouvrage_ids = {str(value) for value in ouvrage_ids}
    current_billing_month = today_mg.replace(day=1)
    pointed_volume_by_period = set()
    # Pas de filtre montant ici : un relevé qui porte déjà un couple
    # (numeroDiameX, baseDiameX) est réconcilié pour sa période, même si son
    # montant n'a pas encore été calculé (montant NULL par le workflow de
    # facturation). Sans ça, la transaction DiameX 707401 correspondante
    # ressortait à tort comme "volume à pointer" alors que les pages
    # volumétriques, elles, ignorent complètement les relevés à montant NULL.
    for releve in Releve.objects.filter(
        point_eau__ouvrage_id__in=ouvrage_ids,
        datereleve__gte=date(2025, 12, 1),
    ).select_related('point_eau').only(
        'id', 'datereleve', 'numeroDiameX', 'baseDiameX',
        'point_eau__ouvrage_id',
    ):
        billing_month = _billing_month_start(releve.datereleve)
        pair = _diamex_pair(releve.numeroDiameX, releve.baseDiameX)
        if (
            billing_month
            and WIDGET_ACCOUNTING_CUTOFF <= billing_month <= current_billing_month
            and pair
        ):
            pointed_volume_by_period.add((
                str(releve.point_eau.ouvrage_id),
                billing_month.year,
                billing_month.month,
                pair,
            ))

    pointed_by_account = {
        '748411': {
            pair for numero, base in PaiementForfaitaire.objects.filter(
                point_eau__ouvrage_id__in=ouvrage_ids,
            ).values_list('numeroDiameX', 'baseDiameX')
            if (pair := _diamex_pair(numero, base))
        },
    }
    result = {'707401': [], '748411': []}
    entries = BaseDiameX.objects.filter(compte_code__in=result.keys()).filter(
        Q(compte_code='707401')
        | Q(compte_code='748411', date_m__gte=WIDGET_ACCOUNTING_CUTOFF, date_m__lte=today_mg)
    ).only('id', 'id_access', 'prog', 'compte_code', 'description', 'montant_in')

    for entry in entries.iterator(chunk_size=500):
        compte = str(entry.compte_code or '').strip()
        pair = _diamex_pair(entry.id_access, entry.prog)
        if compte == '748411' and pair and pair in pointed_by_account.get(compte, set()):
            continue

        extracted_periods = []
        segments = []
        if compte == '707401' and entry.description and ';' in entry.description:
            segments = diviser_paiement_volume_multi(
                entry.description, compte, entry.montant_in or 0,
            )
        if segments:
            for segment in segments:
                extraction = segment.get('extraction') or {}
                ouvrage = extraction.get('ouvrage_obj')
                if ouvrage and extraction.get('annee') and extraction.get('mois'):
                    extracted_periods.append((
                        str(ouvrage.id), int(extraction['annee']), int(extraction['mois'])
                    ))
        else:
            extraction = extraire_ouvrage_et_mois_generique(entry.description or '', compte)
            extraction_items = extraction if isinstance(extraction, list) else [extraction]
            for item in extraction_items:
                ouvrage = item.get('ouvrage_obj') if isinstance(item, dict) else None
                if ouvrage:
                    extracted_periods.append((
                        str(ouvrage.id),
                        int(item.get('annee')) if item.get('annee') else None,
                        int(item.get('mois')) if item.get('mois') else None,
                    ))

        for ouvrage_id, annee, mois in extracted_periods:
            if ouvrage_id not in ouvrage_ids:
                continue
            if compte == '707401':
                if not annee or not mois:
                    continue
                billing_month = date(annee, mois, 1)
                if not (WIDGET_ACCOUNTING_CUTOFF <= billing_month <= current_billing_month):
                    continue
                if pair and (ouvrage_id, annee, mois, pair) in pointed_volume_by_period:
                    continue
            result[compte].append(entry.id)
            if compte == '748411':
                break
    return {
        account: list(dict.fromkeys(entry_ids))
        for account, entry_ids in result.items()
    }, pointed_volume_by_period


def _format_ar(value):
    """Montant en Ariary sans notation scientifique (le format 'g' bascule en
    exponentiel au-dela de ~1 000 000, illisible pour un montant en Ar)."""
    try:
        return f"{int(round(float(value or 0))):,}".replace(',', ' ')
    except (TypeError, ValueError):
        return '0'


def _diamex_707401_segment_diagnostic(ouvrage_id, annee, mois):
    """
    Pour un segment marqué "non pointé" : indique ce que porte réellement le
    relevé correspondant à cette période de facturation, afin de distinguer
    trois causes qui se ressemblent toutes en surface ("non pointé") :
    - aucun relevé n'existe pour cette période (rien à comparer) ;
    - un relevé existe et porte déjà un N°/Base DiameX — mais un AUTRE que
      celui de la ligne évaluée (pointé ailleurs, ou doublon BaseDiameX) ;
    - un relevé existe mais n'a vraiment aucun N° DiameX.
    """
    if mois == 1:
        releve_year, releve_month = annee - 1, 12
    else:
        releve_year, releve_month = annee, mois - 1
    releve = Releve.objects.filter(
        point_eau__ouvrage_id=ouvrage_id,
        datereleve__year=releve_year,
        datereleve__month=releve_month,
        montant__isnull=False,
        montant__gt=0,
    ).only('id', 'datereleve', 'numeroDiameX', 'baseDiameX').order_by('-datereleve').first()
    if not releve:
        return "aucun relevé pour cette période"
    if releve.numeroDiameX or releve.baseDiameX:
        return f"relevé porte {releve.numeroDiameX or '—'}/{releve.baseDiameX or '—'}"
    return "relevé trouvé sans N° DiameX"


def _diamex_707401_segments_status(entry, pointed_volume_by_period, include_diagnostic=True):
    """
    Détail segment par segment d'une ligne 707401 multi-segments (ex. deux
    mois facturés dans la même ligne DiameX, séparés par ';').

    Une ligne multi-segments est signalée "à pointer" dès qu'UN SEUL de ses
    segments n'a pas encore de relevé associé — même si les autres le sont
    déjà (le pointage se fait segment par segment, pas ligne entière). Sans
    ce détail :
    - un petit reliquat resté impayé (souvent bien plus petit que les autres
      montants de la ligne) est invisible dans le widget ;
    - le montant affiché en tête de ligne (entry.montant_in) est le TOTAL de
      la ligne, ce qui laisse croire qu'il faut pointer la ligne entière
      alors qu'une partie l'est déjà (montant_restant corrige ça).

    include_diagnostic=False évite la requête relevé supplémentaire par
    segment non pointé (_diamex_707401_segment_diagnostic) — à utiliser
    quand seul montant_restant est nécessaire (ex. total agrégé sur toute
    la portée du widget dans api_widget_stats, où la ligne n'est pas limitée
    à DETAIL_LIMIT et où le libellé détaillé n'est de toute façon pas affiché).

    Retourne {'breakdown': str, 'montant_restant': float|None}.
    'montant_restant' vaut None si la ligne n'a qu'un seul segment (rien à
    recalculer : l'appelant garde alors entry.montant_in tel quel).
    """
    if not entry.description or ';' not in entry.description:
        return {'breakdown': '', 'montant_restant': None}
    segments = diviser_paiement_volume_multi(
        entry.description, entry.compte_code, entry.montant_in or 0,
    )
    if len(segments) < 2:
        return {'breakdown': '', 'montant_restant': None}
    pair = _diamex_pair(entry.id_access, entry.prog)
    parts = []
    montant_restant = 0.0
    for segment in segments:
        extraction = segment.get('extraction') or {}
        ouvrage = extraction.get('ouvrage_obj')
        annee = extraction.get('annee')
        mois = extraction.get('mois')
        montant = float(segment.get('montant') or 0)
        if not (ouvrage and annee and mois):
            # Extraction du segment impossible : on ne peut pas savoir s'il
            # est pointé, on le compte donc par prudence dans le restant.
            parts.append(f"? · {_format_ar(montant)} Ar")
            montant_restant += montant
            continue
        mois = int(mois)
        is_pointe = bool(
            pair and (str(ouvrage.id), int(annee), mois, pair) in pointed_volume_by_period
        )
        mois_label = _MOIS_FR[mois][:3] if 1 <= mois <= 12 else '?'
        if is_pointe:
            parts.append(f"✓ {mois_label} {annee} · {_format_ar(montant)} Ar")
        else:
            montant_restant += montant
            if include_diagnostic:
                # Ce que porte reellement le releve de cette periode, pour
                # distinguer "aucun releve" / "pointe avec un autre numero"
                # (mismatch) / "vraiment pas pointe" — trois causes tres
                # differentes qui ont toutes la meme apparence "non pointe" ici.
                diag = _diamex_707401_segment_diagnostic(ouvrage.id, int(annee), mois)
                parts.append(f"✗ {mois_label} {annee} · {_format_ar(montant)} Ar ({diag})")
            else:
                parts.append(f"✗ {mois_label} {annee} · {_format_ar(montant)} Ar")
    return {'breakdown': ' | '.join(parts), 'montant_restant': montant_restant}


def _diamex_707401_total_restant(entry_ids, pointed_volume_by_period):
    """
    Somme des montants réellement à pointer pour un ensemble de lignes
    707401 : pour une ligne multi-segments partiellement pointée, seul le
    reliquat des segments non pointés est compté (pas le total de la ligne)
    — sinon le montant affiché sur la tuile du widget est gonflé par les
    segments déjà réglés (cf. _diamex_707401_segments_status).
    """
    total = 0.0
    if not entry_ids:
        return total
    entries = BaseDiameX.objects.filter(id__in=entry_ids).only(
        'id', 'id_access', 'prog', 'compte_code', 'description', 'montant_in',
    )
    for entry in entries.iterator(chunk_size=500):
        status = _diamex_707401_segments_status(
            entry, pointed_volume_by_period, include_diagnostic=False,
        )
        montant = status['montant_restant']
        total += montant if montant is not None else float(entry.montant_in or 0)
    return total


def _split_diamex_ids_by_scan(entry_ids):
    """Separe les lignes a scanner de celles deja pretes a etre pointees."""
    result = {'avec_scan': [], 'sans_scan': []}
    if not entry_ids:
        return result

    entries = BaseDiameX.objects.filter(id__in=entry_ids).only(
        'id', 'scan', 'scan_importe',
    )
    for entry in entries.iterator(chunk_size=500):
        imported_name = (
            getattr(getattr(entry, 'scan_importe', None), 'name', '') or ''
        ).strip()
        has_scan = bool((entry.scan or '').strip() or imported_name)
        result['avec_scan' if has_scan else 'sans_scan'].append(entry.id)
    return result


def _sum_amount(queryset, field_name):
    total = queryset.aggregate(total=Sum(field_name)).get('total') or 0
    return float(total)


def _distinct_ouvrages_points_eau(
    queryset,
    point_path='point_eau_id',
    ouvrage_path='point_eau__ouvrage_id',
):
    """(nb ouvrages distincts, nb points d'eau distincts) couverts par un queryset de factures."""
    ouvrages = set()
    points = set()
    for ouvrage_id, point_id in queryset.order_by().values_list(
        ouvrage_path, point_path,
    ).distinct():
        if ouvrage_id:
            ouvrages.add(ouvrage_id)
        if point_id:
            points.add(point_id)
    return len(ouvrages), len(points)


def _facture_scope_counts(stats, key, queryset):
    """Ajoute `<key>_ouvrages` et `<key>_points_eau` au dict de stats."""
    nb_ouvrages, nb_points = _distinct_ouvrages_points_eau(queryset)
    stats[f'{key}_ouvrages'] = nb_ouvrages
    stats[f'{key}_points_eau'] = nb_points


def _ouvrage_categories(ouvrage_ids, points_eau_qs):
    """
    Catégorie de chaque ouvrage du périmètre, sans double comptage :
    - 'mixte'      : au moins un point d'eau avec tarifforfaitaire > 0 ET au
                     moins un point d'eau ayant eu un relevé avec montant > 0 ;
    - 'forfait'    : au moins un point d'eau avec tarifforfaitaire > 0 seulement ;
    - 'volume'     : au moins un relevé avec montant > 0 seulement ;
    - 'sans_tarif' : ni tarif forfaitaire ni relevé facturé.
    Retourne (dict ouvrage_id -> catégorie, nb points forfait, nb points volume).
    """
    forfait_ouvrages = set()
    points_forfait = 0
    points_volume = 0
    for ouvrage_id, tarif in points_eau_qs.values_list('ouvrage_id', 'tarifforfaitaire'):
        if tarif and tarif > 0:
            points_forfait += 1
            forfait_ouvrages.add(ouvrage_id)
        else:
            points_volume += 1

    volume_ouvrages = set(
        Releve.objects.filter(
            point_eau_id__in=list(points_eau_qs.values_list('id', flat=True)),
            montant__gt=0,
        ).values_list('point_eau__ouvrage_id', flat=True).distinct()
    )

    categories = {}
    for o in set(ouvrage_ids):
        in_forfait = o in forfait_ouvrages
        in_volume = o in volume_ouvrages
        if in_forfait and in_volume:
            categories[o] = 'mixte'
        elif in_forfait:
            categories[o] = 'forfait'
        elif in_volume:
            categories[o] = 'volume'
        else:
            categories[o] = 'sans_tarif'
    return categories, points_forfait, points_volume


OUVRAGE_CATEGORIE_LABELS = {
    'forfait': 'Forfait',
    'volume': 'Volume',
    'mixte': 'Mixte',
    'sans_tarif': 'Sans tarif forfaitaire ni relevé',
}


def _modalite_scope_counts(ouvrage_ids, points_eau_qs):
    categories, points_forfait, points_volume = _ouvrage_categories(ouvrage_ids, points_eau_qs)
    values = list(categories.values())
    return {
        'ouvrages_forfaitaires': values.count('forfait'),
        'ouvrages_volumetriques': values.count('volume'),
        'ouvrages_mixtes': values.count('mixte'),
        'ouvrages_sans_tarif': values.count('sans_tarif'),
        'points_eau_forfaitaires': points_forfait,
        'points_eau_volumetriques': points_volume,
    }


def _relative_duration(value):
    """Libelle relatif volontairement sans exposer la date d'import."""
    if not value:
        return "jamais"
    now = timezone.now()
    if timezone.is_naive(value):
        value = timezone.make_aware(value)
    seconds = max(0, int((now - value).total_seconds()))
    if seconds < 60:
        return "à l'instant"
    minutes = seconds // 60
    if minutes < 60:
        return f"il y a {minutes} min"
    hours = minutes // 60
    if hours < 24:
        return f"il y a {hours} h"
    days = hours // 24
    if days < 30:
        return f"il y a {days} j"
    months = days // 30
    if months < 12:
        return f"il y a {months} mois"
    years = days // 365
    return f"il y a {years} an" if years == 1 else f"il y a {years} ans"


def _diamex_amounts_by_accounting_period(
    entry_ids, account, current_month, ouvrage_ids=None,
):
    """Ventile les DiameX non pointes selon leur mois comptable.

    CRITICAL : la ventilation doit couvrir EXACTEMENT la meme fenetre que le
    cote factures (cf. `_gather_widget_data`) :
        WIDGET_ACCOUNTING_CUTOFF <= mois de facture <= current_month
    Un segment/entree dont le mois de facture est hors fenetre (paiement
    d'avance pour un mois futur, ou anterieur a la bascule comptable) n'a
    aucune contrepartie parmi les factures et ne doit donc pas etre soustrait.
    Sans ce garde-fou, ces montants tombaient tous dans 'mois_anciens' et
    faisaient chuter a tort l'estimation des impayes des mois passes.
    """
    amounts = {'mois_courant': 0.0, 'mois_anciens': 0.0}
    ouvrage_ids = {str(value) for value in (ouvrage_ids or [])}

    def _in_window(period):
        return period is not None and WIDGET_ACCOUNTING_CUTOFF <= period <= current_month

    entries = BaseDiameX.objects.filter(id__in=entry_ids).only(
        'id', 'compte_code', 'description', 'montant_in', 'date_m',
    )
    for entry in entries.iterator(chunk_size=500):
        if account == '748411':
            period = entry.date_m.replace(day=1) if entry.date_m else None
            if not _in_window(period):
                continue
            key = 'mois_courant' if period == current_month else 'mois_anciens'
            amounts[key] += float(entry.montant_in or 0)
            continue

        segments = []
        if entry.description and ';' in entry.description:
            segments = diviser_paiement_volume_multi(
                entry.description, account, entry.montant_in or 0,
            )
        if segments:
            for segment in segments:
                extraction = segment.get('extraction') or {}
                ouvrage = extraction.get('ouvrage_obj')
                if ouvrage_ids and (not ouvrage or str(ouvrage.id) not in ouvrage_ids):
                    continue
                year, month = extraction.get('annee'), extraction.get('mois')
                if not year or not month:
                    continue
                period = date(int(year), int(month), 1)
                if not _in_window(period):
                    continue
                key = 'mois_courant' if period == current_month else 'mois_anciens'
                amounts[key] += float(segment.get('montant') or 0)
            continue

        extraction = extraire_ouvrage_et_mois_generique(
            entry.description or '', account,
        )
        extraction_items = extraction if isinstance(extraction, list) else [extraction]
        periods = {
            date(int(item['annee']), int(item['mois']), 1)
            for item in extraction_items
            if (
                isinstance(item, dict)
                and item.get('annee') and item.get('mois')
                and (
                    not ouvrage_ids
                    or (
                        item.get('ouvrage_obj')
                        and str(item['ouvrage_obj'].id) in ouvrage_ids
                    )
                )
            )
        }
        periods = {period for period in periods if _in_window(period)}
        if not periods:
            # Aucune periode exploitable dans la fenetre : pas de contrepartie
            # cote factures, on n'impute rien (ni mois_courant, ni mois_anciens).
            continue
        elif len(periods) == 1:
            period = next(iter(periods))
            key = 'mois_courant' if period == current_month else 'mois_anciens'
            amounts[key] += float(entry.montant_in or 0)
        else:
            # Cas rare non segmente : repartition egale pour eviter un double comptage.
            share = float(entry.montant_in or 0) / len(periods)
            for period in periods:
                key = 'mois_courant' if period == current_month else 'mois_anciens'
                amounts[key] += share
    return amounts


@login_required
def widget_meteo(request):
    """Page du widget météo installable en PWA (mobile + desktop)."""
    return render(request, 'core/widget_meteo.html')


def widget_manifest(request):
    """
    Manifest PWA dédié au widget, indépendant du manifest principal du site.
    Volontairement PAS protégé par @login_required : un navigateur doit
    pouvoir le récupérer pour proposer l'installation, avant même la
    connexion. Ce fichier ne contient aucune donnée sensible.
    """
    return render(
        request,
        'core/widget_manifest.json',
        content_type='application/manifest+json',
    )


def widget_service_worker(request):
    """
    Service worker dédié au widget, scope /widget/ uniquement.
    Volontairement PAS protégé par @login_required, pour la même raison
    que le manifest (sinon le navigateur récupère une page de login HTML
    à la place du JS attendu, et l'installation PWA échoue silencieusement).
    """
    response = render(
        request,
        'core/widget_sw.js',
        content_type='application/javascript',
    )
    # Autorise ce service worker (servi sous /widget/sw.js) à contrôler
    # tout le sous-arbre /widget/ malgré son emplacement.
    response['Service-Worker-Allowed'] = '/widget/'
    return response


# Alias conservé pour compatibilité : historiquement le seul décorateur du
# widget desktop, désormais un simple raccourci vers le décorateur générique
# (voir apps.core.auth_tokens) figé sur le scope 'widget'. Un token créé pour
# l'app mobile (scope='mobile') ne passera jamais ici, et inversement.
widget_auth_required = token_or_session_required(scope=WidgetAuthToken.SCOPE_WIDGET)


@csrf_exempt
@require_POST
def api_widget_login(request):
    """
    Login dédié au widget desktop (Electron) : vérifie les identifiants
    Hydria habituels et retourne un token opaque, à conserver localement
    par le widget. Ce token ne donne accès qu'aux endpoints /widget/api/*.

    @csrf_exempt car cet appel vient d'un processus Electron, pas d'un
    formulaire dans une page Hydria — pas de cookie CSRF disponible.
    """
    username = request.POST.get('username', '').strip()
    password = request.POST.get('password', '')
    device_label = request.POST.get('device_label', '').strip()[:120]

    if not username or not password:
        return JsonResponse({'success': False, 'error': "Nom d'utilisateur et mot de passe requis"}, status=400)

    user = authenticate(request, username=username, password=password)
    if user is None or not user.is_active:
        return JsonResponse({'success': False, 'error': 'Identifiants invalides'}, status=401)

    token = WidgetAuthToken.objects.create(
        user=user, device_label=device_label, scope=WidgetAuthToken.SCOPE_WIDGET,
    )

    return JsonResponse({
        'success': True,
        'token': token.key,
        'user': user.username,
    })


@widget_auth_required
def api_widget_ping(request):
    """
    Point d'entrée minimal pour de futures données Hydria dans le widget.
    Renvoie l'identité de l'utilisateur résolu (session ou token).
    """
    return JsonResponse({
        'success': True,
        'user': request.user.username,
        'is_staff': request.user.is_staff,
    })


def _widget_intervention_queryset(user):
    """Même périmètre par défaut que la page des interventions récentes."""
    from apps.core.views_ouvrage_interventions import (
        _accessible_intervention_ouvrages,
        _get_quick_repair_fiches_queryset,
    )

    repair_fiche_ids = _get_quick_repair_fiches_queryset().values_list('id', flat=True)
    return Planning.objects.filter(
        ouvrage__in=_accessible_intervention_ouvrages(user),
        fiche_poste_id__in=repair_fiche_ids,
        created_at__isnull=False,
    ).select_related(
        'ouvrage', 'fiche_poste', 'fiche_poste__type_activites',
        'type_activite', 'employe', 'employe__base',
    ).order_by('-created_at', '-updated_at', '-id').distinct()


def _serialize_widget_intervention(planning):
    from apps.core.views_ouvrage_interventions import _planning_attachments

    created_at = planning.created_at
    if created_at and timezone.is_aware(created_at):
        created_at = timezone.localtime(created_at, TZ_MADAGASCAR)
    intervention_date = planning.date
    if intervention_date and timezone.is_aware(intervention_date):
        intervention_date = timezone.localtime(intervention_date, TZ_MADAGASCAR)

    photos = []
    for index, attachment in enumerate(_planning_attachments(planning.photo)):
        photos.append({
            'index': index,
            'name': attachment['name'],
            'type': attachment['type'],
            'is_video': attachment['is_video'],
            'url': reverse(
                'core:api_widget_intervention_photo',
                kwargs={'planning_id': planning.id, 'photo_index': index},
            ),
        })

    return {
        'id': str(planning.id),
        'activite': planning.activite_display,
        'ouvrage_id': str(planning.ouvrage_id) if planning.ouvrage_id else '',
        'ouvrage': planning.ouvrage.nom_ouvrage if planning.ouvrage else 'Sans ouvrage',
        'employe_id': str(planning.employe_id) if planning.employe_id else '',
        'employe': planning.employe.nom_affichage if planning.employe else 'Non affecté',
        'base': planning.employe.base.nom_base if planning.employe and planning.employe.base else '',
        'remarque': planning.remarque or '',
        'statut': planning.get_statut_display() if planning.statut else 'Non défini',
        'date_intervention': intervention_date.strftime('%d/%m/%Y') if intervention_date else '',
        'date_saisie': created_at.strftime('%d/%m/%Y à %H:%M') if created_at else '',
        'date_saisie_iso': created_at.isoformat() if created_at else '',
        'photos': photos,
    }


def _widget_intervention_queue_payload(user):
    """Garde la publication courante stable tant qu'elle n'est pas marquée vue."""
    with transaction.atomic():
        state, created = InterventionWidgetState.objects.select_for_update().get_or_create(user=user)
        base_queryset = _widget_intervention_queryset(user)
        now_local = timezone.localtime(timezone.now(), TZ_MADAGASCAR)
        week_start = (now_local - timedelta(days=now_local.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        week_count = base_queryset.filter(created_at__gte=week_start).count()
        latest = base_queryset.first()
        if created:
            latest = base_queryset.first()
            state.monitoring_started_at = latest.created_at if latest else timezone.now()
            state.current_planning = latest
            state.save(update_fields=['monitoring_started_at', 'current_planning', 'updated_at'])
        unseen = base_queryset.filter(
            created_at__gte=state.monitoring_started_at,
        ).exclude(widget_reads__user=user)
        current = None
        if state.current_planning_id:
            current = unseen.filter(id=state.current_planning_id).first()
        if current is None:
            current = unseen.first()
            state.current_planning = current
            state.save(update_fields=['current_planning', 'updated_at'])
        unseen_count = unseen.count()

    return {
        'success': True,
        'week_count': week_count,
        'week_start': week_start.date().isoformat(),
        'unseen_count': unseen_count,
        'current': _serialize_widget_intervention(current) if current else None,
        # Evenement le plus recent, independant de la file "deja vu". Les
        # clients conservent cet identifiant pour notifier exactement une fois
        # chaque nouvelle publication, meme si unseen_count reste stable.
        'latest_event': ({
            'id': str(latest.id),
            'activite': latest.activite_display,
            'ouvrage': latest.ouvrage.nom_ouvrage if latest.ouvrage else 'Sans ouvrage',
            'date_saisie_iso': latest.created_at.isoformat() if latest.created_at else '',
        } if latest else None),
        'source_url': reverse('core:interventions_recentes'),
    }


@widget_auth_required
@require_GET
def api_widget_interventions(request):
    return JsonResponse(_widget_intervention_queue_payload(request.user))


@csrf_exempt
@widget_auth_required
@require_POST
def api_widget_intervention_mark_seen(request):
    try:
        data = json.loads(request.body.decode('utf-8') or '{}') if request.body else request.POST
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'error': 'Données invalides'}, status=400)

    planning_id = str(data.get('planning_id') or '').strip()
    with transaction.atomic():
        state, created = InterventionWidgetState.objects.select_for_update().get_or_create(user=request.user)
        if created:
            latest = _widget_intervention_queryset(request.user).first()
            state.monitoring_started_at = latest.created_at if latest else timezone.now()
            state.current_planning = latest
            state.save(update_fields=['monitoring_started_at', 'current_planning', 'updated_at'])
        current = _widget_intervention_queryset(request.user).filter(id=state.current_planning_id).first()
        if not current:
            state.current_planning = None
            state.save(update_fields=['current_planning', 'updated_at'])
            return JsonResponse(_widget_intervention_queue_payload(request.user))
        if planning_id != str(current.id):
            return JsonResponse({
                'success': False,
                'error': "Cette publication n'est plus la publication courante",
            }, status=409)
        InterventionWidgetRead.objects.get_or_create(user=request.user, planning=current)
        state.current_planning = None
        state.save(update_fields=['current_planning', 'updated_at'])

    return JsonResponse(_widget_intervention_queue_payload(request.user))


@widget_auth_required
@require_GET
def api_widget_intervention_photo(request, planning_id, photo_index):
    from apps.core.views_ouvrage_interventions import _planning_attachments

    planning = _widget_intervention_queryset(request.user).filter(id=planning_id).first()
    if not planning:
        return HttpResponseBadRequest('Intervention introuvable')
    attachments = _planning_attachments(planning.photo)
    if photo_index < 0 or photo_index >= len(attachments):
        return HttpResponseBadRequest('Photo introuvable')

    source = attachments[photo_index]['data']
    if source.startswith(('http://', 'https://', '/media/')):
        return redirect(source)
    try:
        header, encoded = source.split(',', 1)
        content_type = header[5:].split(';', 1)[0]
        attachment_bytes = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        return HttpResponseBadRequest('Photo invalide')
    if content_type != attachments[photo_index]['type']:
        return HttpResponseBadRequest('Type de photo invalide')

    response = HttpResponse(attachment_bytes, content_type=content_type)
    response['Content-Disposition'] = 'inline; filename="intervention-widget"'
    response['Cache-Control'] = 'private, max-age=600'
    return response


@widget_auth_required
def api_widget_filtres(request):
    """
    Options de filtrage pour le widget : organisations accessibles à
    l'utilisateur (celle de l'utilisateur en tête de liste), puis régions/
    districts/communes dérivés des ouvrages que l'utilisateur peut voir
    dans l'organisation sélectionnée (ou toutes ses organisations si aucune
    n'est encore choisie).
    """
    user = request.user
    gestionnaire_ids, organisations_qs = _get_scoped_organisations_for_user(user)
    user_org = get_user_organisation(user)
    user_org_id = str(user_org.id) if user_org else None

    organisations = [
        {'id': str(org.id), 'nom': org.nom_organisation}
        for org in organisations_qs.order_by('nom_organisation')
    ]
    # L'organisation de l'utilisateur en tête, pour mise en avant côté frontend.
    organisations.sort(key=lambda o: (o['id'] != user_org_id, o['nom']))

    organisation_id = (request.GET.get('organisation') or '').strip()
    if not organisation_id or organisation_id == 'all':
        organisation_id = get_user_default_scope_organisation_id(user)

    ouvrage_ids = _get_scoped_ouvrage_ids(organisation_id, gestionnaire_ids, annee=None)
    ouvrage_ids = _apply_employe_hierarchy_ouvrage_scope(ouvrage_ids, user)

    if ouvrage_ids is None:
        ouvrage_ids = list(Ouvrage.objects.values_list('id', flat=True))

    employe_id = (request.GET.get('employe_id') or '').strip()
    employes, ouvrage_ids = _active_collection_employee_scope(ouvrage_ids, employe_id)
    ouvrages_qs = Ouvrage.objects.filter(id__in=ouvrage_ids)

    region_ids = set(
        ouvrages_qs.exclude(pointeau__isnull=True)
        .values_list('pointeau__parcelle__village__fokontany__commune__district__region_id', flat=True)
        .distinct()
    )
    district_ids = set(
        ouvrages_qs.exclude(pointeau__isnull=True)
        .values_list('pointeau__parcelle__village__fokontany__commune__district_id', flat=True)
        .distinct()
    )
    commune_ids = set(
        ouvrages_qs.exclude(pointeau__isnull=True)
        .values_list('pointeau__parcelle__village__fokontany__commune_id', flat=True)
        .distinct()
    )

    regions = list(
        Region.objects.filter(id__in=region_ids).order_by('nom_region').values('id', 'nom_region')
    )
    districts = list(
        District.objects.filter(id__in=district_ids)
        .order_by('nom_district')
        .values('id', 'nom_district', 'region_id')
    )
    communes = list(
        Commune.objects.filter(id__in=commune_ids)
        .order_by('nom_commune')
        .values('id', 'nom_commune', 'district_id')
    )

    return JsonResponse({
        'success': True,
        'organisations': organisations,
        # Partenaire : pas d'organisation par défaut (= tous ses gestionnaires partenaires).
        'default_organisation_id': None if is_partenaire_user(user) else user_org_id,
        'employes': [
            {
                'id': employee['id'],
                'nom': employee['nom'],
                'poste': employee['poste'],
                'ouvrage_ids': employee['ouvrage_ids'],
            }
            for employee in employes
        ],
        'regions': [{'id': str(r['id']), 'nom': r['nom_region']} for r in regions],
        'districts': [{'id': str(d['id']), 'nom': d['nom_district'], 'region_id': str(d['region_id'])} for d in districts],
        'communes': [{'id': str(c['id']), 'nom': c['nom_commune'], 'district_id': str(c['district_id'])} for c in communes],
    })


OUVRAGE_MODALITE_ORDRE = ['sans_tarif', 'mixte', 'volume', 'forfait']
OUVRAGE_MODALITE_COURT = {'forfait': 'Forfait', 'volume': 'Volume', 'mixte': 'Mixte', 'sans_tarif': 'Sans tarif'}
COMMUNE_SANS_POINT = 'none'


def _split_modalite_commune(raw):
    """
    Le détail des ouvrages est regroupé « modalité de paiement » puis District → Commune sans changer le contrat
    des clients : la commune y est transmise sous la forme `<modalite>|<commune_id>` (commune_id = `none` pour un
    ouvrage sans point d'eau). Retourne (modalite ou None, commune_id ou '').
    """
    raw = (raw or '').strip()
    if '|' in raw:
        modalite, _, commune = raw.partition('|')
        if modalite in OUVRAGE_MODALITE_COURT:
            return modalite, commune
    return None, raw


def _resolve_scoped_ouvrage_ids(request):
    """
    Détermine la liste des ouvrages accessibles à l'utilisateur, en tenant
    compte des filtres optionnels organisation/région/district/commune
    envoyés en query string par le widget.
    """
    user = request.user
    gestionnaire_ids, _ = _get_scoped_organisations_for_user(user)

    organisation_id = (request.GET.get('organisation') or '').strip()
    if not organisation_id:
        organisation_id = get_user_default_scope_organisation_id(user)

    ouvrage_ids = _get_scoped_ouvrage_ids(organisation_id, gestionnaire_ids, annee=None)
    ouvrage_ids = _apply_employe_hierarchy_ouvrage_scope(ouvrage_ids, user)

    if ouvrage_ids is None:
        ouvrage_ids = list(Ouvrage.objects.values_list('id', flat=True))

    employe_id = (request.GET.get('employe_id') or '').strip()
    _, ouvrage_ids = _active_collection_employee_scope(ouvrage_ids, employe_id)
    ouvrages_qs = Ouvrage.objects.filter(id__in=ouvrage_ids)

    commune_id = (request.GET.get('commune_id') or 'all').strip()
    if _split_modalite_commune(commune_id)[0]:
        commune_id = 'all'  # valeur composite du détail des ouvrages : filtrée dans la vue de détail
    district_id = (request.GET.get('district_id') or 'all').strip()
    region_id = (request.GET.get('region_id') or 'all').strip()

    if commune_id and commune_id != 'all':
        ouvrages_qs = ouvrages_qs.filter(pointeau__parcelle__village__fokontany__commune_id=commune_id)
    elif district_id and district_id != 'all':
        ouvrages_qs = ouvrages_qs.filter(pointeau__parcelle__village__fokontany__commune__district_id=district_id)
    elif region_id and region_id != 'all':
        ouvrages_qs = ouvrages_qs.filter(pointeau__parcelle__village__fokontany__commune__district__region_id=region_id)

    return list(ouvrages_qs.distinct().values_list('id', flat=True))


def _head_meter_widget_rows(request):
    """Latest non-initial reading for every accessible head meter."""
    ouvrage_ids = _resolve_scoped_ouvrage_ids(request)
    compteurs = _allowed_compteurs_queryset(request.user).filter(
        ouvrage_id__in=ouvrage_ids,
    ).select_related('ouvrage').order_by('ouvrage__nom_ouvrage', 'numerocompteur')

    releves = ReleveCompteurTete.objects.filter(
        compteur_tete__in=compteurs,
    ).select_related('compteur_tete', 'compteur_tete__ouvrage').order_by(
        'compteur_tete_id', '-date_releve', '-created_at', '-id',
    )
    initial_ids = _get_initial_releve_ids(releves)
    if initial_ids:
        releves = releves.exclude(id__in=initial_ids)

    latest_by_compteur = {}
    for releve in releves:
        latest_by_compteur.setdefault(str(releve.compteur_tete_id), releve)

    rows = []
    for compteur in compteurs:
        releve = latest_by_compteur.get(str(compteur.id))
        if releve:
            severity, ecart, volume_tete, ecart_percent = _get_releve_gap_classification(releve)
            row = {
                'status': severity,
                'label': f"Compteur {compteur.numerocompteur}",
                'sub': (
                    f"{getattr(compteur.ouvrage, 'nom_ouvrage', '') or 'Sans ouvrage'} · "
                    f"écart {float(ecart_percent):.1f}% · "
                    f"{releve.date_releve.strftime('%d/%m/%Y')}"
                ),
            }
        else:
            row = {
                'status': 'non_mesure',
                'label': f"Compteur {compteur.numerocompteur}",
                'sub': f"{getattr(compteur.ouvrage, 'nom_ouvrage', '') or 'Sans ouvrage'} · aucun relevé exploitable",
            }
        row['compteur_status'] = compteur.statut
        rows.append(row)
    return rows


def _debit_source_widget_rows(request):
    """Latest source-flow evolution for every accessible ouvrage."""
    ouvrage_ids = _resolve_scoped_ouvrage_ids(request)
    ouvrages = list(
        Ouvrage.objects.filter(
            id__in=ouvrage_ids,
            type_ouvrage__nom_type_ouvrage__iexact='AEPG',
        ).order_by('nom_ouvrage')
    )
    ouvrage_ids = [ouvrage.id for ouvrage in ouvrages]
    mesures = DebitSourceMesure.objects.filter(
        ouvrage_id__in=ouvrage_ids,
    ).select_related('ouvrage').order_by(
        'ouvrage_id', '-date_visite', '-created_at', '-id',
    )

    two_latest = {}
    for mesure in mesures:
        bucket = two_latest.setdefault(str(mesure.ouvrage_id), [])
        if len(bucket) < 2:
            bucket.append(mesure)

    rows = []
    for ouvrage in ouvrages:
        ouvrage_mesures = two_latest.get(str(ouvrage.id), [])
        if not ouvrage_mesures:
            rows.append({
                'status': 'non_mesure',
                'label': ouvrage.nom_ouvrage,
                'sub': 'Aucune mesure de débit enregistrée',
                'id': str(ouvrage.id),
                'ouvrage_id': str(ouvrage.id),
            })
            continue

        latest = ouvrage_mesures[0]
        previous = ouvrage_mesures[1] if len(ouvrage_mesures) > 1 else None
        delta = None
        if previous and latest.debit_l_s is not None and previous.debit_l_s is not None:
            delta = latest.debit_l_s - previous.debit_l_s
        debit_info = _get_ouvrage_debit_context(ouvrage, latest.date_visite)
        status_value = _get_debit_status_label(latest, debit_info, delta)
        delta_label = f" · évolution {float(delta):+.3f} L/s" if delta is not None else ''
        seuil_minimum = debit_info.get('seuil_minimum')
        seuil_label = ''
        if seuil_minimum is not None:
            ecart_seuil = latest.debit_l_s - seuil_minimum
            comparaison = 'au-dessus' if ecart_seuil >= 0 else 'sous le seuil'
            seuil_label = (
                f" · seuil min. {float(seuil_minimum):.3f} L/s"
                f" · {comparaison} ({float(ecart_seuil):+.3f} L/s)"
            )
        rows.append({
            'status': status_value,
            'label': ouvrage.nom_ouvrage,
            'sub': (
                f"{float(latest.debit_l_s):.3f} L/s · "
                f"{latest.date_visite.strftime('%d/%m/%Y')}{seuil_label}{delta_label}"
            ),
            'id': str(ouvrage.id),
            'ouvrage_id': str(ouvrage.id),
        })
    return rows


@widget_auth_required
def api_widget_compteurs_tete(request):
    rows = _head_meter_widget_rows(request)
    requested_status = (request.GET.get('status') or '').strip()
    if requested_status == 'hors_service':
        filtered_rows = [row for row in rows if row['compteur_status'] == 'hors_service']
    else:
        filtered_rows = [row for row in rows if not requested_status or row['status'] == requested_status]
    stats = {
        status_value: sum(1 for row in rows if row['status'] == status_value)
        for status_value in ('good', 'acceptable', 'investigate', 'critical', 'non_mesure')
    }
    stats.update({
        'total': len(rows),
        'classes': len(rows) - stats['non_mesure'],
        'hors_service': sum(1 for row in rows if row['compteur_status'] == 'hors_service'),
    })
    page_filter = {
        'critical': 'anormal',
        'investigate': 'a_investiguer',
    }.get(requested_status, '')
    full_url = '/organisations/compteurs/releves/'
    if page_filter:
        full_url += f'?ecart_releve={page_filter}'
    return JsonResponse({
        'success': True,
        'stats': stats,
        'total': len(filtered_rows),
        'shown': min(len(filtered_rows), 25),
        'rows': filtered_rows[:25],
        'full_url': full_url,
    })


@widget_auth_required
def api_widget_debits_source(request):
    rows = _debit_source_widget_rows(request)
    requested_status = (request.GET.get('status') or '').strip()
    filtered_rows = [row for row in rows if not requested_status or row['status'] == requested_status]
    stats = {
        status_value: sum(1 for row in rows if row['status'] == status_value)
        for status_value in ('critique', 'baisse', 'stable', 'hausse', 'surveille', 'normal', 'inconnu', 'non_mesure')
    }
    stats['total'] = len(rows)
    full_url = '/plannings/debits-source/'
    if requested_status:
        full_url += f'?evolution={requested_status}'
    return JsonResponse({
        'success': True,
        'stats': stats,
        'total': len(filtered_rows),
        'shown': min(len(filtered_rows), 25),
        'rows': filtered_rows[:25],
        'full_url': full_url,
    })


@widget_auth_required
def api_widget_analyse_consommation(request):
    """Expose l'analyse volumétrique aux widgets web, desktop et Android."""
    from apps.planning.views_analyse_consommation import analyse_consommation

    query = request.GET.copy()
    query['format'] = 'widget_json'
    singular_to_plural = {
        'region_id': 'regions',
        'district_id': 'districts',
        'commune_id': 'communes',
        'village_id': 'villages',
        'parcelle_id': 'parcelles',
        'ouvrage_id': 'ouvrages',
        'type_pe_id': 'types_pe',
    }
    for singular, plural in singular_to_plural.items():
        value = query.get(singular)
        if value and value != 'all' and not query.getlist(plural):
            query.setlist(plural, [value])
        query.pop(singular, None)

    original_query = request.GET
    request.GET = query
    try:
        # Le décorateur login_required de la page est contourné ici seulement
        # après validation du token/session par widget_auth_required.
        return analyse_consommation.__wrapped__(request)
    finally:
        request.GET = original_query


def _gather_widget_data(request):
    """
    Calcule les querysets/ID bruts sous-jacents à chaque stat du widget,
    filtrés sur l'année en cours et le périmètre géographique/
    organisationnel choisi. Réutilisé à la fois par api_widget_stats
    (juste les compteurs) et api_widget_details (le détail par catégorie).

    Réutilise volontairement les mêmes fonctions de scoping que la page
    de référence /plannings/reparations/ (apps/planning/views_reparations*)
    pour que les chiffres réparations concordent exactement. Les factures
    (Releve, PaiementForfaitaire) sont scopées via ouvrage_id__in=... sur
    la même liste d'ouvrages, en cohérence avec le reste de l'application.
    """
    from apps.core.views_ouvrage_interventions import (
        _activity_deadline_summary_by_ouvrage,
    )

    user = request.user
    ouvrage_ids = _resolve_scoped_ouvrage_ids(request)
    annee_courante = timezone.now().year
    today_mg = timezone.now().astimezone(TZ_MADAGASCAR).date()
    debut_mois_courant = today_mg.replace(day=1)
    horizon = today_mg + timedelta(days=7)

    ouvrages_qs = Ouvrage.objects.filter(id__in=ouvrage_ids)
    points_eau_tous_qs = filter_queryset_by_permissions(PointEau.objects.all(), user).filter(
        ouvrage_id__in=ouvrage_ids
    )
    # Seuls les points actifs (branchés, sans date d'arrêt) comptent comme points
    # d'eau existants ; coupés et sans date de branchement sont comptés à part.
    points_eau_qs = points_eau_tous_qs.filter(q_actif())
    periodes_coupure = _widget_coupure_periods(
        PointEau.objects.filter(ouvrage_id__in=ouvrage_ids).values_list('id', flat=True)
    )

    # Factures volumétriques non pointées. Comme sur le dashboard volume,
    # leur mois comptable est le mois suivant celui du relevé.
    factures_volumetriques_base_qs = Releve.objects.filter(
        point_eau__ouvrage_id__in=ouvrage_ids,
        montant__isnull=False,
        montant__gt=0,
        datereleve__gte=date(2025, 12, 1),
    ).exclude(
        remarque__icontains='coupé',
    ).filter(
        Q(numeroDiameX__isnull=True) | Q(numeroDiameX__exact='')
        | Q(baseDiameX__isnull=True) | Q(baseDiameX__exact='')
    ).select_related('point_eau').only(
        'id', 'datereleve', 'updated_at', 'numeroDiameX', 'baseDiameX',
        'remarque', 'point_eau__ouvrage_id', 'point_eau__datearretbranchement',
    )

    factures_volumetriques_mises_a_jour_ids = []
    factures_volumetriques_non_mises_a_jour_ids = []
    factures_volumetriques_mois_courant_ids = []
    factures_volumetriques_mois_anciens_ids = []
    for releve in factures_volumetriques_base_qs:
        billing_month = _billing_month_start(releve.datereleve)
        if (
            not billing_month
            or billing_month < WIDGET_ACCOUNTING_CUTOFF
            or billing_month > debut_mois_courant
            or _is_widget_releve_non_recouvrable(releve, periodes_coupure)
        ):
            continue
        if billing_month == debut_mois_courant:
            factures_volumetriques_mois_courant_ids.append(releve.id)
        else:
            factures_volumetriques_mois_anciens_ids.append(releve.id)
        if _was_updated_during_current_month(
            releve.updated_at,
            debut_mois_courant,
            today_mg,
        ):
            factures_volumetriques_mises_a_jour_ids.append(releve.id)
        else:
            factures_volumetriques_non_mises_a_jour_ids.append(releve.id)

    # Factures forfaitaires non pointées, séparées des relevés au volume.
    factures_forfaitaires_base_qs = PaiementForfaitaire.objects.filter(
        point_eau__ouvrage_id__in=ouvrage_ids,
        montant__isnull=False,
        date_facture__gte=WIDGET_ACCOUNTING_CUTOFF,
        date_facture__lte=today_mg,
    ).filter(
        Q(numeroDiameX__isnull=True) | Q(numeroDiameX__exact='')
        | Q(baseDiameX__isnull=True) | Q(baseDiameX__exact='')
    )
    factures_forfaitaires_mises_a_jour_ids = []
    factures_forfaitaires_non_mises_a_jour_ids = []
    for paiement in factures_forfaitaires_base_qs.only('id', 'updated_at').iterator(chunk_size=500):
        if _was_updated_during_current_month(
            paiement.updated_at,
            debut_mois_courant,
            today_mg,
        ):
            factures_forfaitaires_mises_a_jour_ids.append(paiement.id)
        else:
            factures_forfaitaires_non_mises_a_jour_ids.append(paiement.id)

    # "Factures forfaitaires à collecter aujourd'hui" : paiement forfaitaire
    # non encaissé (paye=False) dont le Planning lié tombe aujourd'hui
    # (conversion timezone Madagascar obligatoire, cf. TIMEZONE_GUIDE.md —
    # jamais de comparaison de date directe en SQL sur un DateTimeField).
    paiements_annee = PaiementForfaitaire.objects.filter(
        point_eau__ouvrage_id__in=ouvrage_ids,
        paye=False,
        planning__isnull=False,
        planning__date__year=annee_courante,
    ).select_related('planning', 'point_eau', 'point_eau__ouvrage')
    paiements_du_jour_ids = []
    for paiement in paiements_annee:
        date_planning = paiement.planning.date
        if not date_planning:
            continue
        date_aware = date_planning if timezone.is_aware(date_planning) else timezone.make_aware(date_planning)
        if date_aware.astimezone(TZ_MADAGASCAR).date() == today_mg:
            paiements_du_jour_ids.append(paiement.id)

    # Meme calcul que /recherche/ouvrages/ : type Reparation/Rehabilitation
    # separe des autres activites, puis date passee separee de la date du jour
    # et des dates futures. Les rattachements via point d'eau/equipement sont inclus.
    activity_deadline_summary = _activity_deadline_summary_by_ouvrage(
        ouvrage_ids,
        today=today_mg,
        include_installation=True,
    )
    family_ids = {
        name: list(ids) for name, ids in activity_deadline_summary['family_planning_ids'].items()
    }
    repair_overdue_ids = list(activity_deadline_summary['planning_ids']['repair_overdue'])
    repair_upcoming_ids = list(activity_deadline_summary['planning_ids']['repair_upcoming'])
    other_overdue_ids = list(activity_deadline_summary['planning_ids']['other_overdue'])
    other_upcoming_ids = list(activity_deadline_summary['planning_ids']['other_upcoming'])
    reparations_non_terminees_echues_ids = repair_overdue_ids + other_overdue_ids
    reparations_non_terminees_non_echues_ids = repair_upcoming_ids + other_upcoming_ids
    reparations_non_terminees_ids = (
        reparations_non_terminees_echues_ids
        + reparations_non_terminees_non_echues_ids
    )
    reparations_7_jours_ids = []
    for rep in Planning.objects.filter(
        id__in=reparations_non_terminees_non_echues_ids,
        date__isnull=False,
    ).only('id', 'date'):
        date_aware = rep.date if timezone.is_aware(rep.date) else timezone.make_aware(rep.date)
        if today_mg <= date_aware.astimezone(TZ_MADAGASCAR).date() <= horizon:
            reparations_7_jours_ids.append(rep.id)

    ouvrages_reparations_non_terminees_echues_ids = list(
        activity_deadline_summary['repair_ouvrage_ids']
    )

    diamex_non_pointed, pointed_volume_by_period = _diamex_non_pointed_ids(ouvrage_ids, today_mg)
    diamex_748411_by_scan = _split_diamex_ids_by_scan(diamex_non_pointed['748411'])
    diamex_707401_by_scan = _split_diamex_ids_by_scan(diamex_non_pointed['707401'])

    factures_volumetriques_mises_a_jour_qs = Releve.objects.filter(
        id__in=factures_volumetriques_mises_a_jour_ids,
    )
    factures_volumetriques_non_mises_a_jour_qs = Releve.objects.filter(
        id__in=factures_volumetriques_non_mises_a_jour_ids,
    )
    factures_forfaitaires_mises_a_jour_qs = PaiementForfaitaire.objects.filter(
        id__in=factures_forfaitaires_mises_a_jour_ids,
    )
    factures_forfaitaires_non_mises_a_jour_qs = PaiementForfaitaire.objects.filter(
        id__in=factures_forfaitaires_non_mises_a_jour_ids,
    )
    factures_volumetriques_periode_courante_qs = Releve.objects.filter(
        id__in=factures_volumetriques_mois_courant_ids,
    )
    factures_volumetriques_periodes_anciennes_qs = Releve.objects.filter(
        id__in=factures_volumetriques_mois_anciens_ids,
    )
    factures_forfaitaires_periode_courante_qs = factures_forfaitaires_base_qs.filter(
        date_facture__gte=debut_mois_courant,
    )
    factures_forfaitaires_periodes_anciennes_qs = factures_forfaitaires_base_qs.filter(
        date_facture__lt=debut_mois_courant,
    )

    return {
        'ouvrage_ids': ouvrage_ids,
        'ouvrages_qs': ouvrages_qs,
        'points_eau_qs': points_eau_qs,
        'points_eau_tous_qs': points_eau_tous_qs,
        'factures_volumetriques_mises_a_jour_mois_courant_qs': factures_volumetriques_mises_a_jour_qs,
        'factures_volumetriques_non_mises_a_jour_mois_courant_qs': factures_volumetriques_non_mises_a_jour_qs,
        'factures_forfaitaires_mises_a_jour_mois_courant_qs': factures_forfaitaires_mises_a_jour_qs,
        'factures_forfaitaires_non_mises_a_jour_mois_courant_qs': factures_forfaitaires_non_mises_a_jour_qs,
        'factures_volumetriques_periode_courante_qs': factures_volumetriques_periode_courante_qs,
        'factures_volumetriques_periodes_anciennes_qs': factures_volumetriques_periodes_anciennes_qs,
        'factures_forfaitaires_periode_courante_qs': factures_forfaitaires_periode_courante_qs,
        'factures_forfaitaires_periodes_anciennes_qs': factures_forfaitaires_periodes_anciennes_qs,
        'debut_mois_courant': debut_mois_courant,
        # "mois courant / mois passes" = decoupage par MOIS DE FACTURE (mois du
        # releve + 1 pour le volume, date_facture pour le forfait), identique au
        # dashboard volumetrique/forfaitaire. A ne pas confondre avec le
        # decoupage "mis a jour ce mois / plus anciens" (recence d'edition).
        'factures_volumetriques_mois_courant_qs': factures_volumetriques_periode_courante_qs,
        'factures_volumetriques_mois_passes_qs': factures_volumetriques_periodes_anciennes_qs,
        'factures_forfaitaires_mois_courant_qs': factures_forfaitaires_periode_courante_qs,
        'factures_forfaitaires_mois_passes_qs': factures_forfaitaires_periodes_anciennes_qs,
        'paiements_du_jour_ids': paiements_du_jour_ids,
        'reparations_non_terminees_ids': reparations_non_terminees_ids,
        'reparations_non_terminees_non_echues_ids': reparations_non_terminees_non_echues_ids,
        'reparations_non_terminees_echues_ids': reparations_non_terminees_echues_ids,
        'reparations_rehabilitations_echues_ids': repair_overdue_ids,
        'reparations_rehabilitations_a_venir_ids': repair_upcoming_ids,
        'autres_activites_echues_ids': other_overdue_ids,
        'autres_activites_a_venir_ids': other_upcoming_ids,
        # Separation reparation / rehabilitation / installation.
        'reparations_echues_ids': family_ids['reparation_overdue'],
        'reparations_a_venir_ids': family_ids['reparation_upcoming'],
        'rehabilitations_echues_ids': family_ids['rehabilitation_overdue'],
        'rehabilitations_a_venir_ids': family_ids['rehabilitation_upcoming'],
        'installations_echues_ids': family_ids['installation_overdue'],
        'installations_a_venir_ids': family_ids['installation_upcoming'],
        'family_ouvrage_ids': {
            bucket: set(ouvrage_counts)
            for bucket, ouvrage_counts in activity_deadline_summary['family_activity_counts'].items()
        },
        'ouvrages_reparations_non_terminees_echues_ids': ouvrages_reparations_non_terminees_echues_ids,
        # Ouvrages distincts concernés par chaque famille d'activités non terminées.
        'activity_ouvrage_ids': {
            bucket: set(ouvrage_counts)
            for bucket, ouvrage_counts in activity_deadline_summary['activity_counts'].items()
        },
        'reparations_7_jours_ids': reparations_7_jours_ids,
        'diamex_748411_non_pointes_ids': diamex_non_pointed['748411'],
        'diamex_707401_non_pointes_ids': diamex_non_pointed['707401'],
        'diamex_748411_avec_scan_non_pointes_ids': diamex_748411_by_scan['avec_scan'],
        'diamex_748411_sans_scan_non_pointes_ids': diamex_748411_by_scan['sans_scan'],
        'diamex_707401_avec_scan_non_pointes_ids': diamex_707401_by_scan['avec_scan'],
        'diamex_707401_sans_scan_non_pointes_ids': diamex_707401_by_scan['sans_scan'],
        # Cle (ouvrage_id, annee, mois, pair) des periodes deja pointees, pour
        # detailler segment par segment une ligne 707401 multi-segments dans
        # api_widget_details (cf. _diamex_non_pointed_ids).
        'pointed_volume_by_period': pointed_volume_by_period,
    }


def classify_ouvrages(ouvrage_ids):
    """
    Classe des ouvrages (identifiants en chaînes) comme le diagramme du widget,
    sans dépendre d'une requête : catégorie (forfait / volume / mixte /
    sans_tarif), période de facture non pointée (passe / courant / a_jour),
    présence de réparation ou réhabilitation non terminée, nombre de points d'eau.
    Les règles de factures non pointées reprennent _gather_widget_data.
    Retourne {ouvrage_id(str): {'cat', 'per', 'avec', 'points'}}.
    """
    from apps.core.views_ouvrage_interventions import _activity_deadline_summary_by_ouvrage

    ids = list(ouvrage_ids)
    if not ids:
        return {}
    today_mg = timezone.now().astimezone(TZ_MADAGASCAR).date()
    debut_mois = today_mg.replace(day=1)

    forfait, points = set(), {}
    for oid, tarif in PointEau.objects.filter(ouvrage_id__in=ids).values_list('ouvrage_id', 'tarifforfaitaire'):
        points[str(oid)] = points.get(str(oid), 0) + 1
        if tarif and tarif > 0:
            forfait.add(str(oid))
    volume = {
        str(o) for o in Releve.objects.filter(
            point_eau__ouvrage_id__in=ids, montant__gt=0,
        ).values_list('point_eau__ouvrage_id', flat=True).distinct() if o
    }

    passe, courant = set(), set()
    coupures = _widget_coupure_periods(
        PointEau.objects.filter(ouvrage_id__in=ids).values_list('id', flat=True)
    )
    releves = Releve.objects.filter(
        point_eau__ouvrage_id__in=ids, montant__isnull=False, montant__gt=0,
        datereleve__gte=date(2025, 12, 1),
    ).exclude(remarque__icontains='coupé').filter(
        Q(numeroDiameX__isnull=True) | Q(numeroDiameX__exact='')
        | Q(baseDiameX__isnull=True) | Q(baseDiameX__exact='')
    ).select_related('point_eau').only(
        'id', 'datereleve', 'numeroDiameX', 'baseDiameX', 'remarque',
        'point_eau__ouvrage_id', 'point_eau__datearretbranchement',
    )
    for releve in releves:
        billing_month = _billing_month_start(releve.datereleve)
        if (not billing_month or billing_month < WIDGET_ACCOUNTING_CUTOFF
                or billing_month > debut_mois or _is_widget_releve_non_recouvrable(releve, coupures)):
            continue
        (courant if billing_month == debut_mois else passe).add(str(releve.point_eau.ouvrage_id))
    paiements = PaiementForfaitaire.objects.filter(
        point_eau__ouvrage_id__in=ids, montant__isnull=False,
        date_facture__gte=WIDGET_ACCOUNTING_CUTOFF, date_facture__lte=today_mg,
    ).filter(
        Q(numeroDiameX__isnull=True) | Q(numeroDiameX__exact='')
        | Q(baseDiameX__isnull=True) | Q(baseDiameX__exact='')
    ).values_list('point_eau__ouvrage_id', 'date_facture')
    for oid, date_facture in paiements:
        if oid:
            (courant if date_facture >= debut_mois else passe).add(str(oid))

    summary = _activity_deadline_summary_by_ouvrage(ids, today=today_mg)
    repair = {str(o) for o in summary['activity_counts'].get('repair_overdue', {})} \
        | {str(o) for o in summary['activity_counts'].get('repair_upcoming', {})}

    result = {}
    for oid in map(str, ids):
        in_f, in_v = oid in forfait, oid in volume
        cat = 'mixte' if in_f and in_v else 'forfait' if in_f else 'volume' if in_v else 'sans_tarif'
        per = 'passe' if oid in passe else 'courant' if oid in courant else 'a_jour'
        result[oid] = {'cat': cat, 'per': per, 'avec': oid in repair, 'points': points.get(oid, 0)}
    return result


@login_required
def widget_diagramme_page(request):
    """Page dédiée du diagramme de décomposition des ouvrages (Sankey)."""
    return render(request, 'core/widget_diagramme.html')


@widget_auth_required
def api_widget_diagramme(request):
    """
    Arbre de décomposition des ouvrages AVEC point d'eau, pour le diagramme
    (treemap) du widget : modalité → facture non pointée (mois passés / mois
    en cours / à jour) → avec / sans réparation ou réhabilitation.
    Chaque ouvrage est placé dans UNE seule feuille (les mois passés priment
    sur le mois en cours), de sorte que les feuilles somment exactement au parent.
    """
    data = _gather_widget_data(request)
    ouvrages = {
        str(o.id): o.nom_ouvrage or 'Ouvrage sans nom'
        for o in data['ouvrages_qs'].exclude(pointeau__isnull=True).distinct()
    }
    scope_ids = set(ouvrages)
    # Mêmes catégories que les compteurs du widget (calculées sur les identifiants
    # d'origine, pas sur des chaînes), puis restreintes aux ouvrages avec point d'eau.
    all_categories, _pf, _pv = _ouvrage_categories(data['ouvrage_ids'], data['points_eau_qs'])
    all_categories = {str(k): v for k, v in all_categories.items()}
    categories = {k: v for k, v in all_categories.items() if k in scope_ids}
    widget_counts = {
        key: list(all_categories.values()).count(key)
        for key in ('forfait', 'volume', 'mixte', 'sans_tarif')
    }
    sans_point_eau = len(set(all_categories) - scope_ids)
    points_par_ouvrage = {
        str(row['ouvrage_id']): row['n']
        for row in data['points_eau_qs'].order_by().values('ouvrage_id').annotate(n=Count('id', distinct=True))
        if str(row['ouvrage_id']) in scope_ids
    }

    def unpointed(*querysets):
        found = set()
        for qs in querysets:
            found |= {
                str(oid) for oid in qs.values_list('point_eau__ouvrage_id', flat=True).distinct()
                if oid
            }
        return found & scope_ids

    passe = unpointed(data['factures_volumetriques_mois_passes_qs'], data['factures_forfaitaires_mois_passes_qs'])
    courant = unpointed(data['factures_volumetriques_mois_courant_qs'], data['factures_forfaitaires_mois_courant_qs'])
    activity = data['activity_ouvrage_ids']
    repair = {str(o) for o in activity.get('repair_overdue', ())} | {str(o) for o in activity.get('repair_upcoming', ())}

    modalites = [
        ('forfait', 'Forfait'), ('volume', 'Volume'), ('mixte', 'Mixte'), ('sans_tarif', 'Sans tarif'),
    ]
    periodes = [
        ('passe', 'Factures non pointées · mois passés'),
        ('courant', 'Factures non pointées · mois en cours'),
        ('a_jour', 'Aucune facture non pointée'),
    ]

    def pts(ids):
        return sum(points_par_ouvrage.get(i, 0) for i in ids)

    def leaf(key, label, ids):
        return {'key': key, 'label': label, 'value': len(ids), 'points': pts(ids),
                'ouvrages': [
                    {'id': i, 'nom': ouvrages[i], 'points': points_par_ouvrage.get(i, 0)}
                    for i in sorted(ids, key=lambda x: ouvrages[x].lower())
                ]}

    children = []
    for mkey, mlabel in modalites:
        members = {o for o, c in categories.items() if c == mkey}
        if not members:
            continue
        periode_nodes = []
        remaining = set(members)
        for pkey, plabel in periodes:
            if pkey == 'passe':
                in_periode = remaining & passe
            elif pkey == 'courant':
                in_periode = remaining & courant
            else:
                in_periode = set(remaining)
            remaining -= in_periode
            if not in_periode:
                continue
            avec = in_periode & repair
            sans = in_periode - repair
            leaves = [
                leaf(f'{mkey}_{pkey}_avec', 'Avec réparation / réhabilitation', avec),
                leaf(f'{mkey}_{pkey}_sans', 'Sans réparation ni réhabilitation', sans),
            ]
            periode_nodes.append({
                'key': f'{mkey}_{pkey}', 'label': plabel, 'value': len(in_periode), 'points': pts(in_periode),
                'children': [l for l in leaves if l['value']],
            })
        children.append({'key': mkey, 'label': mlabel, 'value': len(members), 'points': pts(members),
                         'children': periode_nodes})

    return JsonResponse({
        'success': True,
        'mois_facture_courant_label': _mois_facture_label(data['debut_mois_courant']),
        'widget_counts': widget_counts,
        'sans_point_eau': sans_point_eau,
        'tree': {'key': 'root', 'label': "Ouvrages avec point d'eau", 'value': len(scope_ids),
                 'points': pts(scope_ids), 'children': children},
    })


@widget_auth_required
def api_widget_stats(request):
    data = _gather_widget_data(request)
    last_diamex_import = BaseDiameX.objects.aggregate(last=Max('date_import')).get('last')
    volumes_updated_amount = _sum_amount(
        data['factures_volumetriques_mises_a_jour_mois_courant_qs'], 'montant',
    )
    volumes_older_amount = _sum_amount(
        data['factures_volumetriques_non_mises_a_jour_mois_courant_qs'], 'montant',
    )
    flat_updated_amount = _sum_amount(
        data['factures_forfaitaires_mises_a_jour_mois_courant_qs'], 'montant',
    )
    flat_older_amount = _sum_amount(
        data['factures_forfaitaires_non_mises_a_jour_mois_courant_qs'], 'montant',
    )
    # Montants du decoupage par MOIS DE FACTURE (aligne sur le dashboard).
    volumes_facture_courante_amount = _sum_amount(
        data['factures_volumetriques_periode_courante_qs'], 'montant',
    )
    volumes_facture_anciennes_amount = _sum_amount(
        data['factures_volumetriques_periodes_anciennes_qs'], 'montant',
    )
    flat_facture_courante_amount = _sum_amount(
        data['factures_forfaitaires_periode_courante_qs'], 'montant',
    )
    flat_facture_anciennes_amount = _sum_amount(
        data['factures_forfaitaires_periodes_anciennes_qs'], 'montant',
    )
    diamex_amounts = {
        key: _sum_amount(BaseDiameX.objects.filter(id__in=data[key]), 'montant_in')
        for key in (
            'diamex_748411_avec_scan_non_pointes_ids',
            'diamex_748411_sans_scan_non_pointes_ids',
        )
    }
    # 707401 : sommer le RESTANT (pas le total de la ligne) pour les lignes
    # multi-segments partiellement pointées — sinon le montant affiché sur la
    # tuile widget compte des segments deja pointes (cf. _diamex_707401_total_restant).
    pointed_volume_by_period = data.get('pointed_volume_by_period') or set()
    diamex_amounts['diamex_707401_avec_scan_non_pointes_ids'] = _diamex_707401_total_restant(
        data['diamex_707401_avec_scan_non_pointes_ids'], pointed_volume_by_period,
    )
    diamex_amounts['diamex_707401_sans_scan_non_pointes_ids'] = _diamex_707401_total_restant(
        data['diamex_707401_sans_scan_non_pointes_ids'], pointed_volume_by_period,
    )
    collect_today_amount = _sum_amount(
        PaiementForfaitaire.objects.filter(id__in=data['paiements_du_jour_ids']),
        'montant',
    )
    volume_diamex_by_period = _diamex_amounts_by_accounting_period(
        data['diamex_707401_non_pointes_ids'],
        '707401',
        data['debut_mois_courant'],
        data['ouvrage_ids'],
    )
    flat_diamex_by_period = _diamex_amounts_by_accounting_period(
        data['diamex_748411_non_pointes_ids'],
        '748411',
        data['debut_mois_courant'],
        data['ouvrage_ids'],
    )
    unpaid_estimates = {
        'estimation_impayee_volumetrique_mois_courant': max(
            0.0,
            _sum_amount(data['factures_volumetriques_periode_courante_qs'], 'montant')
            - volume_diamex_by_period['mois_courant'],
        ),
        'estimation_impayee_volumetrique_mois_anciens': max(
            0.0,
            _sum_amount(data['factures_volumetriques_periodes_anciennes_qs'], 'montant')
            - volume_diamex_by_period['mois_anciens'],
        ),
        'estimation_impayee_forfaitaire_mois_courant': max(
            0.0,
            _sum_amount(data['factures_forfaitaires_periode_courante_qs'], 'montant')
            - flat_diamex_by_period['mois_courant'],
        ),
        'estimation_impayee_forfaitaire_mois_anciens': max(
            0.0,
            _sum_amount(data['factures_forfaitaires_periodes_anciennes_qs'], 'montant')
            - flat_diamex_by_period['mois_anciens'],
        ),
    }
    # Nombre d'ouvrages / points d'eau concernés par chaque tuile de factures
    # non pointées : l'ouvrage est le premier repère de l'utilisateur.
    scope_counts = {}
    for key, queryset in (
        ('factures_volumetriques_mois_courant_non_pointees', data['factures_volumetriques_mois_courant_qs']),
        ('factures_volumetriques_mois_passes_non_pointees', data['factures_volumetriques_mois_passes_qs']),
        ('factures_forfaitaires_mois_courant_non_pointees', data['factures_forfaitaires_mois_courant_qs']),
        ('factures_forfaitaires_mois_passes_non_pointees', data['factures_forfaitaires_mois_passes_qs']),
        (
            'factures_forfaitaires_a_collecter_aujourdhui',
            PaiementForfaitaire.objects.filter(id__in=data['paiements_du_jour_ids']),
        ),
    ):
        _facture_scope_counts(scope_counts, key, queryset)

    activity_ouvrages = data['activity_ouvrage_ids']
    scope_counts.update({
        'reparations_rehabilitations_echues_ouvrages': len(activity_ouvrages['repair_overdue']),
        'reparations_rehabilitations_a_venir_ouvrages': len(activity_ouvrages['repair_upcoming']),
        'reparations_echues_ouvrages': len(data['family_ouvrage_ids']['reparation_overdue']),
        'reparations_a_venir_ouvrages': len(data['family_ouvrage_ids']['reparation_upcoming']),
        'rehabilitations_echues_ouvrages': len(data['family_ouvrage_ids']['rehabilitation_overdue']),
        'rehabilitations_a_venir_ouvrages': len(data['family_ouvrage_ids']['rehabilitation_upcoming']),
        'installations_echues_ouvrages': len(data['family_ouvrage_ids']['installation_overdue']),
        'installations_a_venir_ouvrages': len(data['family_ouvrage_ids']['installation_upcoming']),
        'autres_activites_echues_ouvrages': len(activity_ouvrages['other_overdue']),
        'autres_activites_a_venir_ouvrages': len(activity_ouvrages['other_upcoming']),
        'reparations_non_terminees_echues_ouvrages': len(
            activity_ouvrages['repair_overdue'] | activity_ouvrages['other_overdue']
        ),
        'reparations_non_terminees_non_echues_ouvrages': len(
            activity_ouvrages['repair_upcoming'] | activity_ouvrages['other_upcoming']
        ),
        'reparations_non_terminees_ouvrages': len(
            activity_ouvrages['repair_overdue'] | activity_ouvrages['other_overdue']
            | activity_ouvrages['repair_upcoming'] | activity_ouvrages['other_upcoming']
        ),
    })
    scope_counts.update(_modalite_scope_counts(data['ouvrage_ids'], data['points_eau_qs']))
    statuts_points = compter_statuts(data['points_eau_tous_qs'])
    scope_counts['points_eau_coupes'] = statuts_points['coupes']
    scope_counts['points_eau_sans_date'] = statuts_points['sans_date']
    rbf_over_cap, rbf_unpaid = _rbf_anomalies(data)
    scope_counts['rbf_points_depassement_plafond'] = len(rbf_over_cap)
    scope_counts['rbf_points_sans_paiement_effectif'] = len(rbf_unpaid)

    return JsonResponse({
        'success': True,
        'annee': timezone.now().year,
        'derniere_importation_diamex_relative': _relative_duration(last_diamex_import),
        'stats': {
            **scope_counts,
            'ouvrages': data['ouvrages_qs'].count(),
            'points_eau': statuts_points['actifs'],
            'mois_facture_courant_label': _mois_facture_label(data['debut_mois_courant']),
            'factures_volumetriques_mises_a_jour_mois_courant_non_pointees': data['factures_volumetriques_mises_a_jour_mois_courant_qs'].count(),
            'factures_volumetriques_mises_a_jour_mois_courant_non_pointees_montant': volumes_updated_amount,
            'factures_volumetriques_non_mises_a_jour_mois_courant_non_pointees': data['factures_volumetriques_non_mises_a_jour_mois_courant_qs'].count(),
            'factures_volumetriques_non_mises_a_jour_mois_courant_non_pointees_montant': volumes_older_amount,
            'factures_forfaitaires_mises_a_jour_mois_courant_non_pointees': data['factures_forfaitaires_mises_a_jour_mois_courant_qs'].count(),
            'factures_forfaitaires_mises_a_jour_mois_courant_non_pointees_montant': flat_updated_amount,
            'factures_forfaitaires_non_mises_a_jour_mois_courant_non_pointees': data['factures_forfaitaires_non_mises_a_jour_mois_courant_qs'].count(),
            'factures_forfaitaires_non_mises_a_jour_mois_courant_non_pointees_montant': flat_older_amount,
            'factures_volumetriques_mois_courant_non_pointees': data['factures_volumetriques_mois_courant_qs'].count(),
            'factures_volumetriques_mois_courant_non_pointees_montant': volumes_facture_courante_amount,
            'factures_volumetriques_mois_passes_non_pointees': data['factures_volumetriques_mois_passes_qs'].count(),
            'factures_volumetriques_mois_passes_non_pointees_montant': volumes_facture_anciennes_amount,
            'factures_forfaitaires_mois_courant_non_pointees': data['factures_forfaitaires_mois_courant_qs'].count(),
            'factures_forfaitaires_mois_courant_non_pointees_montant': flat_facture_courante_amount,
            'factures_forfaitaires_mois_passes_non_pointees': data['factures_forfaitaires_mois_passes_qs'].count(),
            'factures_forfaitaires_mois_passes_non_pointees_montant': flat_facture_anciennes_amount,
            # Compatibilité avec les anciennes versions du widget.
            'factures_volumetriques_non_pointees': (
                data['factures_volumetriques_mois_courant_qs'].count()
                + data['factures_volumetriques_mois_passes_qs'].count()
            ),
            'factures_forfaitaires_non_pointees': (
                data['factures_forfaitaires_mois_courant_qs'].count()
                + data['factures_forfaitaires_mois_passes_qs'].count()
            ),
            'factures_non_pointees': (
                data['factures_volumetriques_mois_courant_qs'].count()
                + data['factures_volumetriques_mois_passes_qs'].count()
                + data['factures_forfaitaires_mois_courant_qs'].count()
                + data['factures_forfaitaires_mois_passes_qs'].count()
            ),
            'factures_forfaitaires_a_collecter_aujourdhui': len(data['paiements_du_jour_ids']),
            'factures_forfaitaires_a_collecter_aujourdhui_montant': collect_today_amount,
            'reparations_non_terminees': len(data['reparations_non_terminees_ids']),
            'reparations_non_terminees_non_echues': len(data['reparations_non_terminees_non_echues_ids']),
            'reparations_non_terminees_echues': len(data['reparations_non_terminees_echues_ids']),
            'reparations_rehabilitations_echues': len(data['reparations_rehabilitations_echues_ids']),
            'reparations_rehabilitations_a_venir': len(data['reparations_rehabilitations_a_venir_ids']),
            'reparations_echues': len(data['reparations_echues_ids']),
            'reparations_a_venir': len(data['reparations_a_venir_ids']),
            'rehabilitations_echues': len(data['rehabilitations_echues_ids']),
            'rehabilitations_a_venir': len(data['rehabilitations_a_venir_ids']),
            'installations_echues': len(data['installations_echues_ids']),
            'installations_a_venir': len(data['installations_a_venir_ids']),
            'autres_activites_echues': len(data['autres_activites_echues_ids']),
            'autres_activites_a_venir': len(data['autres_activites_a_venir_ids']),
            'ouvrages_reparations_non_terminees_echues': len(data['ouvrages_reparations_non_terminees_echues_ids']),
            'reparations_a_faire_7_jours': len(data['reparations_7_jours_ids']),
            'diamex_748411_non_pointes': len(data['diamex_748411_non_pointes_ids']),
            'diamex_707401_non_pointes': len(data['diamex_707401_non_pointes_ids']),
            'diamex_748411_avec_scan_non_pointes': len(data['diamex_748411_avec_scan_non_pointes_ids']),
            'diamex_748411_avec_scan_non_pointes_montant': diamex_amounts['diamex_748411_avec_scan_non_pointes_ids'],
            'diamex_748411_sans_scan_non_pointes': len(data['diamex_748411_sans_scan_non_pointes_ids']),
            'diamex_748411_sans_scan_non_pointes_montant': diamex_amounts['diamex_748411_sans_scan_non_pointes_ids'],
            'diamex_707401_avec_scan_non_pointes': len(data['diamex_707401_avec_scan_non_pointes_ids']),
            'diamex_707401_avec_scan_non_pointes_montant': diamex_amounts['diamex_707401_avec_scan_non_pointes_ids'],
            'diamex_707401_sans_scan_non_pointes': len(data['diamex_707401_sans_scan_non_pointes_ids']),
            'diamex_707401_sans_scan_non_pointes_montant': diamex_amounts['diamex_707401_sans_scan_non_pointes_ids'],
            **unpaid_estimates,
        },
    })


@widget_auth_required
def api_widget_realisations(request):
    """Compteurs « fait » (jour / semaine / mois) contre la période précédente à date équivalente.

    Endpoint séparé de api_widget_stats : le widget l'appelle à son rythme, et le
    constat à la demande (au plus toutes les 5 min) ne ralentit pas les stats.
    """
    from apps.core import widget_realisations

    periode = request.GET.get('periode', 'jour')
    if periode not in widget_realisations.PERIODES:
        return JsonResponse({'success': False, 'error': 'periode doit valoir jour, semaine ou mois'}, status=400)
    widget_realisations.constater_si_necessaire()
    payload = widget_realisations.compteurs(periode, _resolve_scoped_ouvrage_ids(request))
    return JsonResponse({'success': True, **payload})


DETAIL_LIMIT = 25


def _rbf_anomalies(data):
    """(dépassements du plafond, RBF sans paiement effectif) de l'année en cours, sur le périmètre du widget."""
    from apps.core import widget_rbf

    point_ids = {str(pk) for pk in data['points_eau_tous_qs'].order_by().values_list('id', flat=True)}
    return widget_rbf.compute(point_ids, timezone.localdate().year)

# Types de stats pouvant être regroupés géographiquement District → Commune.
GROUPABLE_STAT_TYPES = {
    'ouvrages', 'points_eau',
    'factures_volumetriques_mises_a_jour_mois_courant_non_pointees',
    'factures_volumetriques_non_mises_a_jour_mois_courant_non_pointees',
    'factures_forfaitaires_mises_a_jour_mois_courant_non_pointees',
    'factures_forfaitaires_non_mises_a_jour_mois_courant_non_pointees',
    'factures_volumetriques_mois_courant_non_pointees',
    'factures_volumetriques_mois_passes_non_pointees',
    'factures_forfaitaires_mois_courant_non_pointees',
    'factures_forfaitaires_mois_passes_non_pointees',
}


RBF_STAT_TYPES = {'rbf_points_depassement_plafond', 'rbf_points_sans_paiement_effectif'}
GEO_POINT = 'parcelle__village__fokontany__commune'


def _widget_explication_href(request, stat_type, point_id):
    """Chemin relatif de la page « pourquoi ce point d'eau est compté », avec le périmètre du widget."""
    path = reverse('core:widget_explication_rbf', args=[stat_type, point_id])
    keep = {k: request.GET[k] for k in ('organisation', 'employe_id', 'region_id', 'district_id', 'commune_id')
            if request.GET.get(k) and request.GET[k] != 'all'}
    return f"{path}?{urlencode(keep)}" if keep else path


def _rbf_groupes_response(data, stat_type):
    """
    Points d'eau en anomalie RBF regroupés Région → District → Commune → Ouvrage. Renvoie des lignes à plat
    (une par ouvrage) : le widget en fait un arbre en sautant les niveaux déjà fixés par son filtre actif.
    """
    over_cap, unpaid = _rbf_anomalies(data)
    items = over_cap if stat_type == 'rbf_points_depassement_plafond' else unpaid
    point_ids = [i['point_id'] for i in items]
    rows = {}
    for p in PointEau.objects.filter(id__in=point_ids).order_by().values(
        'id', 'ouvrage_id', 'ouvrage__nom_ouvrage',
        f'{GEO_POINT}_id', f'{GEO_POINT}__nom_commune',
        f'{GEO_POINT}__district_id', f'{GEO_POINT}__district__nom_district',
        f'{GEO_POINT}__district__region_id', f'{GEO_POINT}__district__region__nom_region',
    ):
        key = (p['ouvrage_id'], p[f'{GEO_POINT}_id'])
        row = rows.setdefault(key, {
            'region_id': str(p[f'{GEO_POINT}__district__region_id'] or ''),
            'region': p[f'{GEO_POINT}__district__region__nom_region'] or 'Sans région',
            'district_id': str(p[f'{GEO_POINT}__district_id'] or ''),
            'district': p[f'{GEO_POINT}__district__nom_district'] or 'Sans district',
            'commune_id': str(p[f'{GEO_POINT}_id'] or ''),
            'commune': p[f'{GEO_POINT}__nom_commune'] or 'Sans commune',
            'ouvrage_id': str(p['ouvrage_id'] or ''),
            'ouvrage': p['ouvrage__nom_ouvrage'] or 'Sans ouvrage',
            'count': 0,
        })
        row['count'] += 1
    flat = sorted(rows.values(), key=lambda r: (r['region'], r['district'], r['commune'], r['ouvrage']))
    return JsonResponse({'success': True, 'flat': True, 'total': len(items), 'rows': flat})


def _ouvrages_groupes_par_modalite(data, request=None):
    """
    Ouvrages regroupés par modalité de paiement d'abord (« sans tarif » en tête pour repérer les ouvrages à
    corriger), puis District → Commune. Les ouvrages sans aucun point d'eau (donc sans tarif) restent visibles,
    dans un groupe « Sans point d'eau ». Quand le filtre actif du widget fixe déjà le district (ou la commune),
    le niveau district n'est pas répété : un seul groupe par modalité.
    """
    district_fixed = bool(request) and any(
        (request.GET.get(k) or 'all') != 'all' for k in ('district_id', 'commune_id')
    )
    categories, _pf, _pv = _ouvrage_categories(data['ouvrage_ids'], data['points_eau_qs'])
    geo = 'pointeau__parcelle__village__fokontany__commune'
    pairs = {}
    for row in data['ouvrages_qs'].order_by().values(
        'id', f'{geo}_id', f'{geo}__nom_commune', f'{geo}__district_id', f'{geo}__district__nom_district',
    ):
        pairs[(row['id'], row[f'{geo}_id'])] = row
    localized = {ouvrage_id for ouvrage_id, commune_pk in pairs if commune_pk is not None}
    groups = {}
    for (ouvrage_id, commune_pk), row in pairs.items():
        modalite = categories.get(ouvrage_id, 'sans_tarif')
        if commune_pk is None:
            # Point d'eau non localisé : ne pas écraser un ouvrage déjà rattaché à une commune.
            if ouvrage_id in localized:
                continue
            district_key, district_nom = 'none', 'Sans localisation'
            commune_key, commune_nom = COMMUNE_SANS_POINT, "Sans point d'eau localisé"
        else:
            district_key = str(row[f'{geo}__district_id'] or 'none')
            district_nom = row[f'{geo}__district__nom_district'] or 'Sans district'
            commune_key, commune_nom = str(commune_pk), row[f'{geo}__nom_commune'] or 'Sans commune'
        if district_fixed:
            district_key, district_nom = 'fixe', ''
        group = groups.setdefault((modalite, district_key), {
            'district': (OUVRAGE_MODALITE_COURT[modalite] if district_fixed
                         else f"{OUVRAGE_MODALITE_COURT[modalite]} · {district_nom}"),
            'district_id': None if district_key in ('none', 'fixe') else district_key,
            'modalite': modalite, 'communes': {}, 'total': 0,
        })
        commune = group['communes'].setdefault(commune_key, {
            'commune_id': f"{modalite}|{commune_key}", 'commune': commune_nom, 'count': 0,
        })
        commune['count'] += 1
        group['total'] += 1
    result = []
    for group in groups.values():
        group['communes'] = sorted(group['communes'].values(), key=lambda c: (-c['count'], c['commune']))
        result.append(group)
    result.sort(key=lambda g: (OUVRAGE_MODALITE_ORDRE.index(g['modalite']), -g['total'], g['district']))
    return JsonResponse({
        'success': True,
        'total': len({ouvrage_id for ouvrage_id, _ in pairs}),
        'districts': result,
    })


@widget_auth_required
def api_widget_groupes(request, stat_type):
    """
    Vue groupée District → Commune (avec compteur) pour une stat
    géolocalisable, afin d'afficher une hiérarchie dépliable dans le
    widget plutôt qu'un simple nombre. Cliquer sur une commune appelle
    ensuite api_widget_details avec commune_id pour voir la vraie liste.
    """
    if stat_type not in GROUPABLE_STAT_TYPES and stat_type not in RBF_STAT_TYPES:
        return JsonResponse({'success': False, 'error': 'Type non regroupable'}, status=400)

    data = _gather_widget_data(request)

    if stat_type == 'ouvrages':
        return _ouvrages_groupes_par_modalite(data, request)

    if stat_type in RBF_STAT_TYPES:
        return _rbf_groupes_response(data, stat_type)

    if stat_type == 'points_eau':
        geo_path = 'parcelle__village__fokontany__commune'
        qs = data['points_eau_qs']
    elif stat_type == 'factures_volumetriques_mises_a_jour_mois_courant_non_pointees':
        geo_path = 'point_eau__parcelle__village__fokontany__commune'
        qs = data['factures_volumetriques_mises_a_jour_mois_courant_qs']
    elif stat_type == 'factures_volumetriques_non_mises_a_jour_mois_courant_non_pointees':
        geo_path = 'point_eau__parcelle__village__fokontany__commune'
        qs = data['factures_volumetriques_non_mises_a_jour_mois_courant_qs']
    elif stat_type == 'factures_volumetriques_mois_courant_non_pointees':
        geo_path = 'point_eau__parcelle__village__fokontany__commune'
        qs = data['factures_volumetriques_mois_courant_qs']
    elif stat_type == 'factures_volumetriques_mois_passes_non_pointees':
        geo_path = 'point_eau__parcelle__village__fokontany__commune'
        qs = data['factures_volumetriques_mois_passes_qs']
    elif stat_type == 'factures_forfaitaires_mises_a_jour_mois_courant_non_pointees':
        geo_path = 'point_eau__parcelle__village__fokontany__commune'
        qs = data['factures_forfaitaires_mises_a_jour_mois_courant_qs']
    elif stat_type == 'factures_forfaitaires_mois_courant_non_pointees':
        geo_path = 'point_eau__parcelle__village__fokontany__commune'
        qs = data['factures_forfaitaires_mois_courant_qs']
    elif stat_type == 'factures_forfaitaires_mois_passes_non_pointees':
        geo_path = 'point_eau__parcelle__village__fokontany__commune'
        qs = data['factures_forfaitaires_mois_passes_qs']
    else:
        geo_path = 'point_eau__parcelle__village__fokontany__commune'
        qs = data['factures_forfaitaires_non_mises_a_jour_mois_courant_qs']

    # Niveau suivant : avec commune_id, regroupement des factures par OUVRAGE
    # (District → Commune → Ouvrage → factures). Ne concerne que les stats de
    # factures ; ouvrages / points d'eau n'ont pas de niveau ouvrage.
    commune_id = (request.GET.get('commune_id') or '').strip()
    if commune_id and stat_type not in ('ouvrages', 'points_eau'):
        from collections import defaultdict as _defaultdict

        commune_qs = _filter_by_commune_geo(qs, commune_id, f'{geo_path}_id')
        par_ouvrage = _defaultdict(lambda: {'nom': '', 'factures': 0, 'points': set(), 'montant': 0.0})
        for facture_id, ouvrage_id, ouvrage_nom, point_id, montant in commune_qs.order_by().values_list(
            'id', 'point_eau__ouvrage_id', 'point_eau__ouvrage__nom_ouvrage',
            'point_eau_id', 'montant',
        ):
            entry = par_ouvrage[ouvrage_id]
            entry['nom'] = ouvrage_nom or 'Sans ouvrage'
            entry['factures'] += 1
            entry['points'].add(point_id)
            entry['montant'] += float(montant or 0)
        ouvrages_rows = [
            {
                'ouvrage_id': str(ouvrage_id) if ouvrage_id else '',
                'ouvrage': entry['nom'] or 'Sans ouvrage',
                'count': entry['factures'],
                'points_eau': len(entry['points']),
                'montant': entry['montant'],
            }
            for ouvrage_id, entry in par_ouvrage.items()
        ]
        ouvrages_rows.sort(key=lambda row: (-row['count'], row['ouvrage']))
        return JsonResponse({
            'success': True,
            'total': sum(row['count'] for row in ouvrages_rows),
            'ouvrages': ouvrages_rows,
        })

    # Comptage par commune sur des OBJETS DISTINCTS (id, commune_id), pas
    # sur les lignes brutes : un Ouvrage a plusieurs PointEau (relation
    # inverse pointeau), donc qs.values() sans dédup compterait le même
    # ouvrage une fois par point d'eau. On déduplique via un set de paires
    # (id_objet, commune_id) avant de compter par commune.
    from collections import defaultdict

    seen_pairs = set()
    commune_meta = {}
    commune_object_ids = defaultdict(set)

    for row in qs.values(
        'id',
        f'{geo_path}_id',
        f'{geo_path}__nom_commune',
        f'{geo_path}__district_id',
        f'{geo_path}__district__nom_district',
        f'{geo_path}__district__region_id',
        f'{geo_path}__district__region__nom_region',
    ):
        commune_id = row[f'{geo_path}_id']
        obj_id = row['id']
        if not commune_id:
            continue
        pair = (obj_id, commune_id)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        commune_object_ids[commune_id].add(obj_id)
        commune_meta[commune_id] = {
            'commune_id': str(commune_id),
            'commune': row[f'{geo_path}__nom_commune'] or 'Sans commune',
            'district_id': str(row[f'{geo_path}__district_id']) if row[f'{geo_path}__district_id'] else None,
            'district': row[f'{geo_path}__district__nom_district'] or 'Sans district',
            'region_id': str(row[f'{geo_path}__district__region_id'] or ''),
            'region': row[f'{geo_path}__district__region__nom_region'] or 'Sans région',
        }

    districts = defaultdict(lambda: {
        'district': '', 'district_id': None, 'region': '', 'region_id': '', 'communes': [], 'total': 0,
    })
    for commune_id, object_ids in commune_object_ids.items():
        meta = commune_meta[commune_id]
        count = len(object_ids)
        d_id = meta['district_id'] or 'none'
        districts[d_id]['district'] = meta['district']
        districts[d_id]['district_id'] = meta['district_id']
        districts[d_id]['region'] = meta['region']
        districts[d_id]['region_id'] = meta['region_id']
        districts[d_id]['communes'].append({
            'commune_id': meta['commune_id'],
            'commune': meta['commune'],
            'count': count,
        })
        districts[d_id]['total'] += count

    result = list(districts.values())
    for d in result:
        d['communes'].sort(key=lambda c: -c['count'])
    result.sort(key=lambda d: -d['total'])

    return JsonResponse({
        'success': True,
        'total': sum(d['total'] for d in result),
        'districts': result,
    })


def _filter_by_commune_geo(queryset, commune_id, path_prefix):
    """
    Applique un filtre commune_id sur un queryset dont le chemin vers
    Commune est donné par path_prefix (ex: 'pointeau__parcelle__village__
    fokontany__commune_id' pour Ouvrage, ou 'point_eau__parcelle__village__
    fokontany__commune_id' pour Releve/PaiementForfaitaire — la chaîne
    géographique complète Ouvrage→PointEau→Parcelle→Village→Fokontany→
    Commune→District→Région documentée dans le projet).
    """
    if not commune_id or commune_id == 'all':
        return queryset
    return queryset.filter(**{path_prefix: commune_id})


@widget_auth_required
def api_widget_details(request, stat_type):
    """
    Détail concis (max DETAIL_LIMIT lignes) pour une stat du widget, afin
    d'afficher un mini-tableau au clic sans quitter le widget. Accepte un
    paramètre optionnel commune_id pour restreindre à une commune précise
    (utilisé après avoir "déplié" la vue groupée District → Commune).
    """
    data = _gather_widget_data(request)
    commune_id = (request.GET.get('commune_id') or '').strip()
    ouvrage_filter_id = (request.GET.get('ouvrage_id') or '').strip()
    # `limit=all` : liste complète (page « voir tout » sur Hydria) ; sinon aperçu du widget.
    limit = None if request.GET.get('limit') == 'all' else DETAIL_LIMIT
    if ouvrage_filter_id:
        try:
            ouvrage_filter_id = str(uuid.UUID(ouvrage_filter_id))
        except ValueError:
            return JsonResponse({'success': False, 'error': 'ouvrage_id invalide'}, status=400)

    def _restrict_ouvrage(queryset):
        if not ouvrage_filter_id:
            return queryset
        return queryset.filter(point_eau__ouvrage_id=ouvrage_filter_id)

    if stat_type == 'ouvrages':
        modalite_filtre, commune_pk = _split_modalite_commune(commune_id)
        if commune_pk == COMMUNE_SANS_POINT:
            qs = data['ouvrages_qs'].filter(pointeau__isnull=True).distinct()
        else:
            qs = _filter_by_commune_geo(
                data['ouvrages_qs'], commune_pk,
                'pointeau__parcelle__village__fokontany__commune_id',
            ).distinct()
        categories, _pf, _pv = _ouvrage_categories(data['ouvrage_ids'], data['points_eau_qs'])
        if modalite_filtre:
            qs = qs.filter(id__in=[o for o, c in categories.items() if c == modalite_filtre])
        # Regroupé par modalité, « sans tarif » en tête pour repérer les
        # ouvrages à corriger. Pas de limite : une commune a peu d'ouvrages.
        ordre = {'sans_tarif': 0, 'mixte': 1, 'volume': 2, 'forfait': 3}
        ouvrages = list(qs.select_related('type_ouvrage').order_by('nom_ouvrage'))
        ouvrages.sort(key=lambda o: ordre.get(categories.get(o.id), 9))
        rows = [
            {
                'id': str(o.id),
                'label': o.nom_ouvrage,
                'sub': getattr(o.type_ouvrage, 'nom_type_ouvrage', '') or '',
                'group': OUVRAGE_CATEGORIE_LABELS.get(categories.get(o.id), 'Autres'),
            }
            for o in ouvrages
        ]
        total = qs.count()

    elif stat_type == 'points_eau':
        qs = _filter_by_commune_geo(
            data['points_eau_qs'], commune_id,
            'parcelle__village__fokontany__commune_id',
        )
        rows = [
            {'label': p.nomabonne or p.idxls or str(p.id), 'idxls': p.idxls or '',
             'sub': getattr(p.ouvrage, 'nom_ouvrage', '') or ''}
            for p in qs.select_related('ouvrage').order_by('nomabonne')[:limit]
        ]
        total = qs.count()

    elif stat_type in (
        'factures_volumetriques_mises_a_jour_mois_courant_non_pointees',
        'factures_volumetriques_non_mises_a_jour_mois_courant_non_pointees',
        'factures_volumetriques_mois_courant_non_pointees',
        'factures_volumetriques_mois_passes_non_pointees',
    ):
        queryset_key = {
            'factures_volumetriques_mises_a_jour_mois_courant_non_pointees':
                'factures_volumetriques_mises_a_jour_mois_courant_qs',
            'factures_volumetriques_non_mises_a_jour_mois_courant_non_pointees':
                'factures_volumetriques_non_mises_a_jour_mois_courant_qs',
            'factures_volumetriques_mois_courant_non_pointees':
                'factures_volumetriques_mois_courant_qs',
            'factures_volumetriques_mois_passes_non_pointees':
                'factures_volumetriques_mois_passes_qs',
        }[stat_type]
        qs = _restrict_ouvrage(_filter_by_commune_geo(
            data[queryset_key], commune_id,
            'point_eau__parcelle__village__fokontany__commune_id',
        )).select_related('point_eau', 'point_eau__ouvrage').order_by('-datereleve')
        rows = []
        for r in qs[:limit]:
            ouvrage = getattr(r.point_eau, 'ouvrage', None) if r.point_eau else None
            # Mois de facture = mois suivant le relevé (cf. dashboard-paiements-volume),
            # nécessaire pour ouvrir directement le bon modal mensuel depuis le widget.
            billing_month = _billing_month_start(r.datereleve)
            rows.append({
                'label': r.point_eau.nomabonne if r.point_eau else '—',
                'idxls': (r.point_eau.idxls or '') if r.point_eau else '',
                'sub': f"{getattr(ouvrage, 'nom_ouvrage', '') or ''} · {r.montant} Ar · {r.datereleve.strftime('%d/%m/%Y') if r.datereleve else ''}",
                'ouvrage_id': str(ouvrage.id) if ouvrage else None,
                'ouvrage_nom': getattr(ouvrage, 'nom_ouvrage', '') or None,
                'annee': billing_month.year if billing_month else None,
                'mois': billing_month.month if billing_month else None,
            })
        total = qs.count()

    elif stat_type in (
        'factures_forfaitaires_mises_a_jour_mois_courant_non_pointees',
        'factures_forfaitaires_non_mises_a_jour_mois_courant_non_pointees',
        'factures_forfaitaires_mois_courant_non_pointees',
        'factures_forfaitaires_mois_passes_non_pointees',
    ):
        queryset_key = {
            'factures_forfaitaires_mises_a_jour_mois_courant_non_pointees':
                'factures_forfaitaires_mises_a_jour_mois_courant_qs',
            'factures_forfaitaires_non_mises_a_jour_mois_courant_non_pointees':
                'factures_forfaitaires_non_mises_a_jour_mois_courant_qs',
            'factures_forfaitaires_mois_courant_non_pointees':
                'factures_forfaitaires_mois_courant_qs',
            'factures_forfaitaires_mois_passes_non_pointees':
                'factures_forfaitaires_mois_passes_qs',
        }[stat_type]
        qs = _restrict_ouvrage(_filter_by_commune_geo(
            data[queryset_key], commune_id,
            'point_eau__parcelle__village__fokontany__commune_id',
        )).select_related('point_eau', 'point_eau__ouvrage').order_by('-date_facture')
        rows = []
        for p in qs[:limit]:
            ouvrage = getattr(p.point_eau, 'ouvrage', None) if p.point_eau else None
            rows.append({
                'label': p.point_eau.nomabonne if p.point_eau else '—',
                'idxls': (p.point_eau.idxls or '') if p.point_eau else '',
                'sub': f"{getattr(ouvrage, 'nom_ouvrage', '') or ''} · {p.montant} Ar · {p.date_facture.strftime('%d/%m/%Y') if p.date_facture else ''}",
                'ouvrage_id': str(ouvrage.id) if ouvrage else None,
                'ouvrage_nom': getattr(ouvrage, 'nom_ouvrage', '') or None,
                'annee': p.date_facture.year if p.date_facture else None,
            })
        total = qs.count()

    elif stat_type == 'factures_forfaitaires_jour':
        qs = PaiementForfaitaire.objects.filter(
            id__in=data['paiements_du_jour_ids']
        ).select_related('point_eau', 'point_eau__ouvrage').order_by('point_eau__nomabonne')
        rows = []
        for p in qs[:limit]:
            ouvrage = getattr(p.point_eau, 'ouvrage', None) if p.point_eau else None
            rows.append({
                'label': p.point_eau.nomabonne if p.point_eau else '—',
                'idxls': (p.point_eau.idxls or '') if p.point_eau else '',
                'sub': f"{getattr(ouvrage, 'nom_ouvrage', '') or ''} · {p.montant} Ar",
                'ouvrage_id': str(ouvrage.id) if ouvrage else None,
                'ouvrage_nom': getattr(ouvrage, 'nom_ouvrage', '') or None,
                'annee': p.date_facture.year if p.date_facture else None,
            })
        total = len(data['paiements_du_jour_ids'])

    elif stat_type in (
        'diamex_748411_non_pointes', 'diamex_707401_non_pointes',
        'diamex_748411_avec_scan_non_pointes', 'diamex_748411_sans_scan_non_pointes',
        'diamex_707401_avec_scan_non_pointes', 'diamex_707401_sans_scan_non_pointes',
    ):
        compte = '748411' if stat_type == 'diamex_748411_non_pointes' else '707401'
        if '748411' in stat_type:
            compte = '748411'
        if '_avec_scan_' in stat_type:
            ids_key = f'diamex_{compte}_avec_scan_non_pointes_ids'
        elif '_sans_scan_' in stat_type:
            ids_key = f'diamex_{compte}_sans_scan_non_pointes_ids'
        else:
            ids_key = f'diamex_{compte}_non_pointes_ids'
        qs = BaseDiameX.objects.filter(id__in=data[ids_key]).order_by('-date_m', '-id')
        action_label = (
            'A scanner d abord'
            if '_sans_scan_' in stat_type
            else 'Pret a pointer'
            if '_avec_scan_' in stat_type
            else 'A traiter'
        )
        pointed_volume_by_period = data.get('pointed_volume_by_period') or set()
        rows = []
        for entry in qs[:limit]:
            breakdown = ''
            # Par defaut (ligne a segment unique, ou compte 748411) : le
            # montant a pointer = le montant total de la ligne, inchange.
            montant_affiche = entry.montant_in or 0
            if compte == '707401':
                status = _diamex_707401_segments_status(entry, pointed_volume_by_period)
                breakdown = status['breakdown']
                if status['montant_restant'] is not None:
                    # Ligne multi-segments partiellement pointee : n'afficher
                    # QUE le reliquat encore du, pas le total de la ligne —
                    # sinon on donne l'impression qu'il faut tout re-pointer.
                    montant_affiche = status['montant_restant']
            sub = (
                f"{action_label} · {entry.date_m.strftime('%d/%m/%Y') if entry.date_m else 'Sans date'}"
                f" · {_format_ar(montant_affiche)} Ar"
            )
            if breakdown and montant_affiche != (entry.montant_in or 0):
                sub += f" restant (sur {_format_ar(entry.montant_in)} Ar au total)"
            sub += f" · {entry.id_access}/{entry.prog or '—'}"
            if breakdown:
                sub += f" · {breakdown}"
            rows.append({
                'label': entry.description or f'Ligne DiameX {entry.id_access}',
                'sub': sub,
            })
        total = len(data[ids_key])

    elif stat_type in {
        'reparations_non_terminees',
        'reparations_non_terminees_non_echues',
        'reparations_non_terminees_echues',
        'reparations_rehabilitations_echues',
        'reparations_rehabilitations_a_venir',
        'reparations_echues',
        'reparations_a_venir',
        'rehabilitations_echues',
        'rehabilitations_a_venir',
        'installations_echues',
        'installations_a_venir',
        'autres_activites_echues',
        'autres_activites_a_venir',
    }:
        ids_key = {
            'reparations_echues': 'reparations_echues_ids',
            'reparations_a_venir': 'reparations_a_venir_ids',
            'rehabilitations_echues': 'rehabilitations_echues_ids',
            'rehabilitations_a_venir': 'rehabilitations_a_venir_ids',
            'installations_echues': 'installations_echues_ids',
            'installations_a_venir': 'installations_a_venir_ids',
            'reparations_non_terminees': 'reparations_non_terminees_ids',
            'reparations_non_terminees_non_echues': 'reparations_non_terminees_non_echues_ids',
            'reparations_non_terminees_echues': 'reparations_non_terminees_echues_ids',
            'reparations_rehabilitations_echues': 'reparations_rehabilitations_echues_ids',
            'reparations_rehabilitations_a_venir': 'reparations_rehabilitations_a_venir_ids',
            'autres_activites_echues': 'autres_activites_echues_ids',
            'autres_activites_a_venir': 'autres_activites_a_venir_ids',
        }[stat_type]
        qs = Planning.objects.filter(
            id__in=data[ids_key]
        ).select_related('ouvrage', 'fiche_poste').order_by('date')
        rows = [
            {
                'label': getattr(r.ouvrage, 'nom_ouvrage', '') or '—',
                'sub': f"{getattr(r.fiche_poste, 'tache', '') or ''} · {r.date.strftime('%d/%m/%Y') if r.date else 'Sans date'}",
            }
            for r in qs[:limit]
        ]
        total = len(data[ids_key])

    elif stat_type == 'ouvrages_reparations_non_terminees_echues':
        qs = Ouvrage.objects.filter(
            id__in=data['ouvrages_reparations_non_terminees_echues_ids']
        ).order_by('nom_ouvrage')
        rows = [
            {
                'label': ouvrage.nom_ouvrage or '—',
                'sub': 'Au moins une reparation, rehabilitation ou panne echue a traiter',
            }
            for ouvrage in qs[:limit]
        ]
        total = len(data['ouvrages_reparations_non_terminees_echues_ids'])

    elif stat_type == 'reparations_7_jours':
        qs = Planning.objects.filter(
            id__in=data['reparations_7_jours_ids']
        ).select_related('ouvrage', 'fiche_poste').order_by('date')
        rows = [
            {
                'label': getattr(r.ouvrage, 'nom_ouvrage', '') or '—',
                'sub': f"{getattr(r.fiche_poste, 'tache', '') or ''} · {r.date.strftime('%d/%m/%Y') if r.date else ''}",
            }
            for r in qs[:limit]
        ]
        total = len(data['reparations_7_jours_ids'])

    elif stat_type in ('rbf_points_depassement_plafond', 'rbf_points_sans_paiement_effectif'):
        from apps.billing.models import PointEau as _PointEau
        over_cap, unpaid = _rbf_anomalies(data)
        items = over_cap if stat_type == 'rbf_points_depassement_plafond' else unpaid
        restricted = _filter_by_commune_geo(
            data['points_eau_tous_qs'], commune_id, 'parcelle__village__fokontany__commune_id',
        )
        if ouvrage_filter_id:
            restricted = restricted.filter(ouvrage_id=ouvrage_filter_id)
        if commune_id or ouvrage_filter_id:
            allowed = {str(pk) for pk in restricted.order_by().values_list('id', flat=True)}
            items = [i for i in items if i['point_id'] in allowed]
        shown = items[:limit]
        points = {
            str(p.id): p for p in _PointEau.objects.filter(
                id__in=[i['point_id'] for i in shown]).select_related('ouvrage')
        }
        rows = []
        for item in shown:
            point = points.get(item['point_id'])
            label = (getattr(point, 'nomabonne', '') or getattr(point, 'idxls', '') or '—') if point else '—'
            ouvrage = getattr(getattr(point, 'ouvrage', None), 'nom_ouvrage', '') or ''
            sub = f"{ouvrage} · RBF {int(item['total']):,} Ar".replace(',', ' ')
            if stat_type == 'rbf_points_depassement_plafond':
                sub += f" · excédent {int(item['excess']):,} Ar".replace(',', ' ')
            else:
                sub += f" · {item['paid']} période(s) de 3 mois payée(s)"
            rows.append({
                'label': label,
                'idxls': (getattr(point, 'idxls', '') or '') if point else '',
                'sub': sub,
                'point_id': item['point_id'],
                # Page Hydria qui explique pourquoi ce point figure dans le compteur.
                'href': _widget_explication_href(request, stat_type, item['point_id']),
            })
        total = len(items)

    else:
        return JsonResponse({'success': False, 'error': 'Type de détail inconnu'}, status=400)

    return JsonResponse({
        'success': True,
        'total': total,
        'shown': len(rows),
        'rows': rows,
    })


WIDGET_LISTE_TITRES = {
    'rbf_points_depassement_plafond': 'Indemnités RBF · au-dessus du plafond annuel',
    'rbf_points_sans_paiement_effectif': 'Indemnités RBF · sans paiement effectif',
}


@login_required
def widget_liste_page(request, stat_type):
    """
    Page « liste complète » vers laquelle pointe le bas de chaque modal du widget (« voir Hydria pour la liste
    complète »). Les lignes viennent de api_widget_details avec limit=all, donc exactement le même périmètre.
    """
    if not stat_type.replace('_', '').isalnum():
        return HttpResponseBadRequest('Type invalide')
    params = request.GET.copy()
    titre = params.pop('titre', [''])[0] or WIDGET_LISTE_TITRES.get(stat_type, 'Liste complète')
    params['limit'] = 'all'
    return render(request, 'core/widget_liste.html', {
        'titre': titre,
        'api_url': f"{reverse('core:api_widget_details', args=[stat_type])}?{params.urlencode()}",
    })


RBF_DASHBOARD_FILTER_KEYS = ('organisation', 'employe_id', 'region_id', 'district_id', 'commune_id', 'ouvrage_id', 'q')
RBF_TYPE_ORDER = ('rbf_points_sans_paiement_effectif', 'rbf_points_depassement_plafond')


def _rbf_point_context(data, point, stat_type, annee=None):
    """
    Pourquoi ce point d'eau figure dans le compteur : chaque chiffre de la règle, avec les pièces.
    `annee` : exercice affiché (par défaut l'année en cours) ; les autres années servent à contrôler la cohérence
    des paiements passés.
    """
    from decimal import Decimal
    from apps.core import widget_rbf
    from apps.core.views_ouvrage_interventions import (
        PLAFOND_INDEMNITE_PAR_POINT_EAU_PUBLIC, _rbf_indemnity_lines_by_ouvrage,
    )

    annee_courante = timezone.localdate().year
    annee = annee or annee_courante
    pid = str(point.id)
    all_lines = [
        line for line in _rbf_indemnity_lines_by_ouvrage().get(str(point.ouvrage_id), []) if line[4] == pid
    ]
    lines = [line for line in all_lines if line[2] == annee]
    # Années navigables : celles où le point a une indemnité RBF ou un paiement forfaitaire, plus l'année en cours.
    years = {annee_courante, annee} | {line[2] for line in all_lines if line[2]}
    for pay_date, bill_date in PaiementForfaitaire.objects.filter(point_eau=point).values_list(
            'date_paiement', 'date_facture'):
        d = pay_date or bill_date
        if d:
            years.add(d.year)
    entries = {e.id: e for e in BaseDiameX.objects.filter(id__in=[line[0] for line in lines])}
    rbf_lines = sorted(
        ({'entry': entries.get(line[0]), 'kind': line[1], 'amount': line[3]} for line in lines),
        key=lambda r: (getattr(r['entry'], 'date_m', None) or date.min),
    )
    total = sum((r['amount'] for r in rbf_lines), Decimal('0'))
    payments = list(
        PaiementForfaitaire.objects.filter(point_eau=point)
        .filter(Q(date_paiement__year=annee) | Q(date_paiement__isnull=True, date_facture__year=annee))
        .order_by('date_paiement', 'date_facture')
    )
    effective = [p for p in payments if (p.numeroDiameX or '').strip()]
    paid = sum(widget_rbf.periods_of(p.quantite) for p in effective)
    justified = widget_rbf.INDEMNITE_PAR_PAIEMENT_EFFECTIF * paid
    cap = PLAFOND_INDEMNITE_PAR_POINT_EAU_PUBLIC
    over_cap_items, unpaid_items = widget_rbf.classify({pid: total}, {pid: paid}, cap)
    is_cap_view = stat_type == 'rbf_points_depassement_plafond'
    return {
        'point': point,
        'stat_type': stat_type,
        'titre': WIDGET_LISTE_TITRES[stat_type],
        'annee': annee,
        'annee_courante': annee_courante,
        'annees': sorted(years, reverse=True),
        'rbf_lines': rbf_lines,
        'total': total,
        'payments': payments,
        'effective_count': paid,
        'pending_count': len(payments) - paid,
        'per_payment': widget_rbf.INDEMNITE_PAR_PAIEMENT_EFFECTIF,
        'justified': justified,
        'cap': cap,
        'excess_unpaid': max(total - justified, Decimal('0')),
        'excess_cap': max(total - cap, Decimal('0')),
        'is_cap_view': is_cap_view,
        'flagged': bool(over_cap_items) if is_cap_view else bool(unpaid_items),
    }


def _rbf_dashboard_rows(data):
    """Points en anomalie RBF du périmètre : {type: [ligne]} triées par excédent décroissant."""
    over_cap, unpaid = _rbf_anomalies(data)
    by_type = {'rbf_points_depassement_plafond': over_cap, 'rbf_points_sans_paiement_effectif': unpaid}
    ids = {item['point_id'] for items in by_type.values() for item in items}
    points = {
        str(p.id): p for p in PointEau.objects.filter(id__in=ids).select_related(
            'ouvrage', 'parcelle__village__fokontany__commune__district__region')
    }
    flags = {
        stat_type: {item['point_id'] for item in items} for stat_type, items in by_type.items()
    }
    result = {}
    for stat_type, items in by_type.items():
        rows = []
        for item in items:
            point = points.get(item['point_id'])
            if not point:
                continue
            commune = getattr(getattr(getattr(point.parcelle, 'village', None), 'fokontany', None), 'commune', None)
            district = getattr(commune, 'district', None)
            region = getattr(district, 'region', None)
            rows.append({
                'id': item['point_id'],
                'idxls': point.idxls or '',
                'nom': point.nomabonne or '',
                'ouvrage_id': str(point.ouvrage_id or ''),
                'ouvrage': getattr(point.ouvrage, 'nom_ouvrage', '') or 'Sans ouvrage',
                'commune_id': str(getattr(commune, 'id', '') or ''),
                'district_id': str(getattr(district, 'id', '') or ''),
                'region_id': str(getattr(region, 'id', '') or ''),
                'commune': getattr(commune, 'nom_commune', '') or '—',
                'district': getattr(district, 'nom_district', '') or '—',
                'region': getattr(region, 'nom_region', '') or '—',
                'total': item['total'],
                'paid': item['paid'],
                'excess': item['excess'],
                'in_cap': item['point_id'] in flags['rbf_points_depassement_plafond'],
                'in_unpaid': item['point_id'] in flags['rbf_points_sans_paiement_effectif'],
            })
        result[stat_type] = rows
    return result


def _rbf_top(rows, key, limit=8):
    """Classement (nombre de points, excédent) par ouvrage ou par commune, avec largeur relative de barre."""
    from collections import defaultdict as _dd
    groups = _dd(lambda: {'count': 0, 'excess': 0})
    for row in rows:
        entry = groups[row[key]]
        entry['count'] += 1
        entry['excess'] += row['excess']
    ranked = sorted(({'name': k, **v} for k, v in groups.items()), key=lambda g: -g['excess'])[:limit]
    peak = max((g['excess'] for g in ranked), default=0) or 1
    for g in ranked:
        g['pct'] = int(round(g['excess'] * 100 / peak))
    return ranked


@login_required
def widget_rbf_dashboard(request, stat_type=None, point_id=None):
    """
    Tableau de bord des indemnités RBF à contrôler : filtres, statistiques, liste navigable des points en anomalie
    et, quand un point est choisi, la page qui explique pourquoi il figure dans le compteur du widget.
    Même périmètre que le widget (organisation / employé / région / district / commune passés en query string).
    """
    from decimal import Decimal

    if stat_type is None:
        stat_type = request.GET.get('type') or RBF_TYPE_ORDER[0]
    if stat_type not in RBF_STAT_TYPES:
        return HttpResponseBadRequest('Type invalide')

    data = _gather_widget_data(request)
    all_rows = _rbf_dashboard_rows(data)
    counts = {t: len(all_rows[t]) for t in RBF_TYPE_ORDER}

    rows = all_rows[stat_type]

    # Options des filtres = uniquement les zones / ouvrages ayant des indemnités à contrôler. Elles ne doivent pas
    # dépendre des filtres géographiques actifs (sinon on ne pourrait plus changer de commune) : on repart du
    # périmètre sans région / district / commune.
    geo_keys = ('region_id', 'district_id', 'commune_id')
    if any(request.GET.get(k) and request.GET[k] != 'all' for k in geo_keys):
        import copy
        base_request = copy.copy(request)
        base_get = request.GET.copy()
        for k in geo_keys:
            base_get.pop(k, None)
        base_request.GET = base_get
        base_rows = _rbf_dashboard_rows(_gather_widget_data(base_request))[stat_type]
    else:
        base_rows = rows
    geo_options = {'regions': {}, 'districts': {}, 'communes': {}}
    for r in base_rows:
        if r['region_id']:
            geo_options['regions'][r['region_id']] = {'id': r['region_id'], 'nom': r['region']}
        if r['district_id']:
            geo_options['districts'][r['district_id']] = {
                'id': r['district_id'], 'nom': r['district'], 'region_id': r['region_id']}
        if r['commune_id']:
            geo_options['communes'][r['commune_id']] = {
                'id': r['commune_id'], 'nom': r['commune'], 'district_id': r['district_id']}
    geo_options = {k: sorted(v.values(), key=lambda o: o['nom'].lower()) for k, v in geo_options.items()}

    # Un ouvrage par entrée (rattaché à la commune de son premier point), avec ses parents pour le regroupement du filtre.
    ouvrage_options = []
    seen_ouvrages = set()
    for r in sorted(base_rows, key=lambda r: r['ouvrage'].lower()):
        if r['ouvrage_id'] in seen_ouvrages:
            continue
        seen_ouvrages.add(r['ouvrage_id'])
        ouvrage_options.append({k: r[k] for k in (
            'ouvrage_id', 'ouvrage', 'commune_id', 'commune', 'district_id', 'district', 'region_id', 'region')})
    ouvrage_id = (request.GET.get('ouvrage_id') or '').strip()
    search = (request.GET.get('q') or '').strip()
    if ouvrage_id:
        rows = [r for r in rows if r['ouvrage_id'] == ouvrage_id]
    if search:
        needle = search.lower()
        rows = [r for r in rows if needle in f"{r['idxls']} {r['nom']} {r['ouvrage']} {r['commune']}".lower()]

    keep = {k: request.GET[k] for k in RBF_DASHBOARD_FILTER_KEYS
            if request.GET.get(k) and request.GET[k] != 'all'}
    query = urlencode(keep)
    suffix = f"?{query}" if query else ''
    for row in rows:
        row['url'] = reverse('core:widget_explication_rbf', args=[stat_type, row['id']]) + suffix

    detail = prev_url = next_url = None
    position = None
    if point_id:
        pid = str(point_id)
        point = (
            data['points_eau_tous_qs'].filter(id=pid)
            .select_related('ouvrage', 'parcelle__village__fokontany__commune__district__region').first()
        )
        try:
            annee_demandee = int(request.GET.get('annee') or 0) or None
        except ValueError:
            annee_demandee = None
        if annee_demandee and not 2000 <= annee_demandee <= timezone.localdate().year + 1:
            annee_demandee = None
        detail = _rbf_point_context(data, point, stat_type, annee_demandee) if point else {'introuvable': True}
        ids = [r['id'] for r in rows]
        # Les liens Précédent / Suivant et le sélecteur d'année gardent l'année consultée.
        annee_sfx = (lambda url: url) if not annee_demandee else (
            lambda url: f"{url}{'&' if '?' in url else '?'}annee={annee_demandee}")
        if pid in ids:
            idx = ids.index(pid)
            position = idx + 1
            prev_url = annee_sfx(rows[idx - 1]['url']) if idx > 0 else None
            next_url = annee_sfx(rows[idx + 1]['url']) if idx + 1 < len(rows) else None
        if point and not detail.get('introuvable'):
            base = reverse('core:widget_explication_rbf', args=[stat_type, point_id]) + suffix
            sep = '&' if suffix else '?'
            detail['year_links'] = [
                {'annee': y, 'url': f"{base}{sep}annee={y}", 'active': y == detail['annee']}
                for y in detail['annees']
            ]

    total_rbf = sum((r['total'] for r in rows), Decimal('0'))
    total_excess = sum((r['excess'] for r in rows), Decimal('0'))
    stats = {
        'count': len(rows),
        'total_rbf': total_rbf,
        'total_excess': total_excess,
        'ouvrages': len({r['ouvrage_id'] for r in rows}),
        'communes': len({r['commune'] for r in rows}),
        'zero_paid': sum(1 for r in rows if r['paid'] == 0),
        'both': sum(1 for r in rows if r['in_cap'] and r['in_unpaid']),
    }
    return render(request, 'core/widget_rbf_dashboard.html', {
        'stat_type': stat_type,
        'titre': WIDGET_LISTE_TITRES[stat_type],
        'tabs': [
            {'type': t, 'titre': WIDGET_LISTE_TITRES[t], 'count': counts[t],
             'url': f"{reverse('core:widget_rbf_dashboard')}?{urlencode({**keep, 'type': t})}"}
            for t in RBF_TYPE_ORDER
        ],
        'rows': rows,
        'stats': stats,
        'top_ouvrages': _rbf_top(rows, 'ouvrage'),
        'top_communes': _rbf_top(rows, 'commune'),
        'ouvrage_options': ouvrage_options,
        'geo_options': geo_options,
        'filters': {
            'organisation': request.GET.get('organisation', ''),
            'region_id': request.GET.get('region_id', ''),
            'district_id': request.GET.get('district_id', ''),
            'commune_id': request.GET.get('commune_id', ''),
            'ouvrage_id': ouvrage_id,
            'q': search,
        },
        'detail': detail,
        'can_edit_libelle': _can_edit_rbf_libelle(request.user),
        'selected_id': str(point_id) if point_id else '',
        'position': position,
        'prev_url': prev_url,
        'next_url': next_url,
        'dashboard_url': f"{reverse('core:widget_rbf_dashboard')}?{urlencode({**keep, 'type': stat_type})}",
        'annee': timezone.localdate().year,
    })


@login_required
def widget_explication_rbf_page(request, stat_type, point_id):
    """Lien du widget : le tableau de bord RBF ouvert sur un point d'eau précis."""
    return widget_rbf_dashboard(request, stat_type=stat_type, point_id=point_id)


def _rbf_avance_plannings(request, point):
    """Plannings validés de l'ouvrage du point, du jour à +60 jours, dans le périmètre de l'utilisateur."""
    from apps.planning.views_livraisons import _filter_plannings_by_scope

    today = timezone.now().astimezone(TZ_MADAGASCAR).date()
    from datetime import datetime as _dt
    start = TZ_MADAGASCAR.localize(_dt(today.year, today.month, today.day))
    qs = _filter_plannings_by_scope(Planning.objects.all(), request.user).filter(
        ouvrage_id=point.ouvrage_id, estvalide=True, date__gte=start, date__lt=start + timedelta(days=60),
    ).select_related('employe').order_by('date')
    return list(qs[:40])


def _rbf_avance_point(request, point_id):
    from apps.employees.permissions import filter_queryset_by_permissions
    return filter_queryset_by_permissions(PointEau.objects.all(), request.user).filter(id=point_id).first()


@login_required
@require_GET
def api_widget_rbf_avance_controle(request, point_id):
    """Plannings sur lesquels l'avance peut être posée + verdict du contrôle pour le planning choisi."""
    from decimal import Decimal, InvalidOperation
    from apps.core import rbf_avance

    point = _rbf_avance_point(request, point_id)
    if not point:
        return JsonResponse({'success': False, 'error': 'Point d\'eau introuvable.'}, status=404)
    try:
        montant = Decimal(request.GET.get('montant') or widget_rbf_default_montant())
    except InvalidOperation:
        return JsonResponse({'success': False, 'error': 'Montant invalide.'}, status=400)

    plannings = _rbf_avance_plannings(request, point)
    chosen = next((p for p in plannings if str(p.id) == request.GET.get('planning_id')), None)
    date_ref = (chosen.date.astimezone(TZ_MADAGASCAR).date() if chosen
                else timezone.now().astimezone(TZ_MADAGASCAR).date())
    verdict = rbf_avance.evaluer(point, montant, date_ref)
    return JsonResponse({
        'success': True,
        'plannings': [{
            'id': str(p.id), 'date': p.date.astimezone(TZ_MADAGASCAR).strftime('%d/%m/%Y'),
            'agent': getattr(p.employe, 'surnom', None) or getattr(p.employe, 'nom', '') or '—',
        } for p in plannings],
        'planning_id': str(chosen.id) if chosen else '',
        'autorise': verdict['autorise'] and bool(chosen),
        'controles': verdict['controles'],
        'chiffres': {k: str(v) for k, v in verdict['chiffres'].items()},
    })


def widget_rbf_default_montant():
    from apps.core.widget_rbf import INDEMNITE_PAR_PAIEMENT_EFFECTIF
    return INDEMNITE_PAR_PAIEMENT_EFFECTIF


@login_required
@require_POST
def api_widget_rbf_avance_demander(request, point_id):
    """Crée la ligne d'avance « Indemnité RBF » sur le planning choisi, seulement si le contrôle est favorable."""
    from decimal import Decimal, InvalidOperation
    from apps.core import rbf_avance
    from apps.planning.models import Designation, PlanningDetail

    point = _rbf_avance_point(request, point_id)
    if not point:
        return JsonResponse({'success': False, 'error': 'Point d\'eau introuvable.'}, status=404)
    try:
        montant = Decimal(request.POST.get('montant') or '0')
    except InvalidOperation:
        return JsonResponse({'success': False, 'error': 'Montant invalide.'}, status=400)

    with transaction.atomic():
        # Verrou sur le point : deux demandes simultanées (double clic) ne peuvent pas passer toutes les deux.
        PointEau.objects.select_for_update().get(pk=point.pk)
        planning = next((p for p in _rbf_avance_plannings(request, point)
                         if str(p.id) == request.POST.get('planning_id')), None)
        if not planning:
            return JsonResponse({'success': False, 'error': 'Choisissez un planning valide de cet ouvrage.'}, status=400)
        verdict = rbf_avance.evaluer(point, montant, planning.date.astimezone(TZ_MADAGASCAR).date())
        if not verdict['autorise']:
            return JsonResponse({'success': False, 'error': 'Avance refusée par le contrôle.',
                                 'controles': verdict['controles']}, status=409)
        designation = Designation.objects.filter(
            nom__icontains='ndemnit', concerne_avance=True, actif=True,
        ).filter(nom__icontains='RBF').first()
        if not designation:
            return JsonResponse({'success': False, 'error': 'Désignation « Indemnité RBF » (avance) introuvable.'}, status=500)
        PlanningDetail.objects.create(
            planning=planning, designation=designation, quantity=1, pu=montant, montant=montant, point_eau=point,
            acheteur=(getattr(planning.employe, 'surnom', None) or '')[:100] or None,
        )
    return JsonResponse({'success': True, 'message': 'Avance demandée : elle apparaît dans la gestion des avances.'})


@login_required
def widget_rbf_avances_lot(request):
    """
    Contrôle en lot des avances d'indemnité RBF : toutes les lignes « Indemnité RBF » de PlanningDetail pas encore
    traitées par la caissière, avec leur verdict. Le verdict est calculé sur l'ensemble des lignes (ordre
    déterministe) puis seules celles du périmètre de l'utilisateur sont affichées.
    """
    from apps.core import rbf_avance
    from apps.planning.views_livraisons import _filter_plannings_by_scope

    details = rbf_avance.lignes_a_controler()
    verdicts = rbf_avance.evaluer_lot(details)
    visibles = set(
        _filter_plannings_by_scope(Planning.objects.filter(id__in=[d.planning_id for d in details]), request.user)
        .values_list('id', flat=True)
    )
    statut = request.GET.get('statut') or ''
    needle = (request.GET.get('q') or '').strip().lower()
    rows = []
    for d in sorted(details, key=lambda d: (d.planning.date, str(d.id))):
        if d.planning_id not in visibles:
            continue
        v = verdicts[d.id]
        point = d.point_eau
        row = {
            'id': str(d.id),
            'date': d.planning.date.astimezone(TZ_MADAGASCAR).date(),
            'agent': getattr(d.planning.employe, 'surnom', None) or getattr(d.planning.employe, 'nom', '') or '—',
            'ouvrage': getattr(d.planning.ouvrage, 'nom_ouvrage', '') or '—',
            'idxls': getattr(point, 'idxls', '') or '',
            'nom': getattr(point, 'nomabonne', '') or '',
            'montant': d.montant,
            'autorise': v['autorise'],
            'controles': v['controles'],
            'url': reverse('core:widget_explication_rbf', args=['rbf_points_sans_paiement_effectif', point.id])
                   if point else '',
        }
        if statut == 'autorisees' and not row['autorise']:
            continue
        if statut == 'refusees' and row['autorise']:
            continue
        if needle and needle not in f"{row['agent']} {row['ouvrage']} {row['idxls']} {row['nom']}".lower():
            continue
        rows.append(row)
    return render(request, 'core/widget_rbf_avances_lot.html', {
        'rows': rows,
        'nb_autorisees': sum(1 for r in rows if r['autorise']),
        'nb_refusees': sum(1 for r in rows if not r['autorise']),
        'montant_autorise': sum((r['montant'] for r in rows if r['autorise']), 0),
        'montant_refuse': sum((r['montant'] for r in rows if not r['autorise']), 0),
        'statut': statut, 'q': request.GET.get('q', ''),
        'fenetre': rbf_avance.FENETRE_JOURS,
    })


def _can_edit_rbf_libelle(user):
    return bool(getattr(user, 'is_superuser', False) or is_directeur_poste(user))


@login_required
@require_POST
def api_widget_rbf_modifier_libelle(request, entry_id):
    """
    Modification du libellé d'une ligne RBF depuis le tableau de bord (directeur uniquement).
    Délègue à accounting.update_entry (PostgreSQL + Access) : cette vue est servie sur www, alors que
    /comptabilite/ y est redirigé vers compta.hydria.mg (un POST fetch n'y survivrait pas).
    """
    if not _can_edit_rbf_libelle(request.user):
        return JsonResponse({'success': False, 'error': 'Réservé au directeur.'}, status=403)
    if not BaseDiameX.objects.filter(id=entry_id).exists():
        return JsonResponse({'success': False, 'error': 'Entrée introuvable'}, status=404)
    if not (request.POST.get('description') or '').strip():
        return JsonResponse({'success': False, 'error': 'Le libellé ne peut pas être vide.'}, status=400)
    from apps.accounting.views import update_entry
    return update_entry(request, entry_id)


def _date_iso(value):
    return value.isoformat() if value else None


@widget_auth_required
def api_widget_ouvrage_detail(request, ouvrage_id):
    """Fiche native compacte d'un ouvrage, limitée au périmètre du widget."""
    ouvrage = (
        Ouvrage.objects.select_related('type_ouvrage')
        .filter(id=ouvrage_id, id__in=_resolve_scoped_ouvrage_ids(request))
        .first()
    )
    if not ouvrage:
        return JsonResponse({'success': False, 'error': 'Ouvrage introuvable'}, status=404)

    # Actifs d'abord, puis coupés, puis sans date de branchement (mis à part)
    points_qs = (
        PointEau.objects.filter(ouvrage=ouvrage)
        .select_related(
            'type_point_eau', 'parcelle__village__fokontany__commune__district__region'
        )
        .annotate(statut_rang=Case(
            When(datebranchement__isnull=True, then=Value(2)),
            When(datearretbranchement__isnull=False, then=Value(1)),
            default=Value(0),
            output_field=IntegerField(),
        ))
        .order_by('statut_rang', 'nomabonne')
    )
    points_statuts = compter_statuts(points_qs)
    equipements_qs = (
        ouvrage.equipements_constitutifs.select_related('type_equipement')
        .order_by('nom')
    )

    locations = {}
    points = []
    for point in points_qs[:50]:
        village = getattr(getattr(point, 'parcelle', None), 'village', None)
        fokontany = getattr(village, 'fokontany', None)
        commune = getattr(fokontany, 'commune', None)
        district = getattr(commune, 'district', None)
        region = getattr(district, 'region', None)
        if commune:
            key = str(commune.id)
            location = locations.setdefault(key, {
                'commune': commune.nom_commune,
                'district': getattr(district, 'nom_district', '') or '',
                'region': getattr(region, 'nom_region', '') or '',
                'villages': set(),
            })
            if village:
                location['villages'].add(village.nom_village)
        points.append({
            'id': str(point.id),
            'code': point.code_point_eau or '',
            'nom': point.nomabonne or '',
            'type': getattr(point.type_point_eau, 'nom_type', '') or '',
            'village': getattr(village, 'nom_village', '') or '',
            'statut': statut_of(point),
        })

    location_rows = []
    for location in locations.values():
        location_rows.append({
            **{key: value for key, value in location.items() if key != 'villages'},
            'villages': sorted(location['villages']),
        })
    location_rows.sort(key=lambda row: (row['region'], row['district'], row['commune']))

    modalites = []
    for modalite in ouvrage.modalites_gestion.filter(
        date_fin__isnull=True
    ).select_related('gestionnaire').order_by('-date_debut')[:10]:
        modalites.append({
            'type_gestion': modalite.get_type_gestion_display(),
            'gestionnaire': str(modalite.gestionnaire) if modalite.gestionnaire else '',
            'paiement': modalite.get_modalitepaiement_display() if modalite.modalitepaiement else '',
            'statut': modalite.get_statut_display(),
            'date_debut': _date_iso(modalite.date_debut),
            'date_fin': _date_iso(modalite.date_fin),
        })

    tarifs = []
    for tarif in (
        TarifVolumetrique.objects.filter(ouvrage=ouvrage, actif=True)
        .select_related('type_point_eau').prefetch_related('tranches')
        .order_by('-datedebuttarif')[:10]
    ):
        tarifs.append({
            'type_point_eau': getattr(tarif.type_point_eau, 'nom_type', '') or 'Tous types',
            'prix_abonnement': tarif.prixabonnement,
            'volume_minimum': str(tarif.volume_minimum_facture) if tarif.volume_minimum_facture is not None else None,
            'date_debut': _date_iso(tarif.datedebuttarif),
            'date_fin': _date_iso(tarif.datefintarif),
            'tranches': [
                {'seuil': tranche.tranchesuperieur, 'tarif': tranche.tarif}
                for tranche in tarif.tranches.all()
            ],
        })

    equipements = [
        {
            'id': str(equipement.id),
            'nom': equipement.nom,
            'code': equipement.code_equipement or '',
            'type': getattr(equipement.type_equipement, 'nom_type', '') or '',
            'statut': equipement.get_statut_display(),
            'volume_m3': str(equipement.volume_m3) if equipement.volume_m3 is not None else None,
        }
        for equipement in equipements_qs[:50]
    ]

    today_mg = timezone.now().astimezone(TZ_MADAGASCAR).date()
    fiche_reparation_ids = list(get_repair_fiches_queryset().values_list('id', flat=True))
    reparations = []
    for planning in Planning.objects.filter(
        ouvrage=ouvrage,
        fiche_poste_id__in=fiche_reparation_ids,
        estvalide=False,
    ).select_related('fiche_poste', 'employe').order_by('date')[:20]:
        date_rep = planning.date.astimezone(TZ_MADAGASCAR).date() if planning.date else None
        reparations.append({
            'titre': planning.activite_display,
            'date': _date_iso(date_rep),
            'statut': 'Planifiée' if date_rep and date_rep > today_mg else 'En cours',
            'priorite': planning.get_priorite_suivi_display() if planning.priorite_suivi else 'Normale',
            'responsable': planning.employe.surnom if planning.employe else '',
        })

    paiements_echus = []
    releves = Releve.objects.filter(
        point_eau__ouvrage=ouvrage,
        montant__gt=0,
        facture_imprimee=True,
        # Le relevé de décembre 2025 produit une facture comptable en janvier 2026.
        datereleve__gte=date(2025, 12, 1),
    ).exclude(
        remarque__icontains='coupé',
    ).filter(
        Q(numeroDiameX__isnull=True) | Q(numeroDiameX__exact='')
        | Q(baseDiameX__isnull=True) | Q(baseDiameX__exact='')
    ).select_related('point_eau').order_by('datereleve')
    periodes_coupure_ouvrage = _widget_coupure_periods(
        PointEau.objects.filter(ouvrage=ouvrage).values_list('id', flat=True)
    )
    for releve in releves:
        if not releve.datereleve:
            continue
        # Point d'eau coupé : la facture n'est plus à recouvrer dès que son mois
        # de facture chevauche une coupure (règle par période, cf. dashboard).
        if _is_widget_releve_non_recouvrable(releve, periodes_coupure_ouvrage):
            continue
        # Une facture au volume devient exigible le mois suivant le relevé.
        if releve.datereleve.month == 12:
            echeance = releve.datereleve.replace(year=releve.datereleve.year + 1, month=1, day=1)
        else:
            echeance = releve.datereleve.replace(month=releve.datereleve.month + 1, day=1)
        if WIDGET_ACCOUNTING_CUTOFF <= echeance <= today_mg:
            paiements_echus.append({
                'type': 'Au volume',
                'point_eau': releve.point_eau.nomabonne or releve.point_eau.code_point_eau or '',
                'date': _date_iso(echeance),
                'montant': str(releve.montant),
            })

    forfaits_non_pointes = PaiementForfaitaire.objects.filter(
        point_eau__ouvrage=ouvrage,
        date_facture__gte=WIDGET_ACCOUNTING_CUTOFF,
        date_facture__lte=today_mg,
        montant__gt=0,
    ).filter(
        Q(numeroDiameX__isnull=True) | Q(numeroDiameX__exact='')
        | Q(baseDiameX__isnull=True) | Q(baseDiameX__exact='')
    ).select_related('point_eau').order_by('date_facture')
    for paiement in forfaits_non_pointes:
        paiements_echus.append({
            'type': 'Forfaitaire',
            'point_eau': paiement.point_eau.nomabonne or paiement.point_eau.code_point_eau or '',
            'date': _date_iso(paiement.date_facture),
            'montant': str(paiement.montant),
        })
    paiements_echus.sort(key=lambda row: row['date'] or '')
    paiements_echus = paiements_echus[:20]

    prochains_qs = PaiementForfaitaire.objects.filter(
        point_eau__ouvrage=ouvrage,
        date_facture__gt=today_mg,
    ).filter(
        Q(numeroDiameX__isnull=True) | Q(numeroDiameX__exact='')
    ).select_related('point_eau').order_by('date_facture', 'point_eau__nomabonne')
    prochaine_date = prochains_qs.values_list('date_facture', flat=True).first()
    prochains_paiements = []
    if prochaine_date:
        for paiement in prochains_qs.filter(date_facture=prochaine_date)[:20]:
            prochains_paiements.append({
                'type': 'Forfaitaire',
                'point_eau': paiement.point_eau.nomabonne or paiement.point_eau.code_point_eau or '',
                'date': _date_iso(paiement.date_facture),
                'montant': str(paiement.montant),
            })

    debit_mesures = list(
        DebitSourceMesure.objects.filter(ouvrage=ouvrage)
        .order_by('-date_visite', '-created_at')[:12]
    )
    debit_source = None
    if debit_mesures:
        derniere_mesure = debit_mesures[0]
        debit_info = _get_ouvrage_debit_context(ouvrage, derniere_mesure.date_visite)
        seuil_minimum = debit_info.get('seuil_minimum')
        ecart_seuil = (
            derniere_mesure.debit_l_s - seuil_minimum
            if seuil_minimum is not None and derniere_mesure.debit_l_s is not None
            else None
        )
        debit_source = {
            'dernier_debit': float(derniere_mesure.debit_l_s),
            'date_derniere_mesure': _date_iso(derniere_mesure.date_visite),
            'seuil_minimum': float(seuil_minimum) if seuil_minimum is not None else None,
            'ecart_seuil': float(ecart_seuil) if ecart_seuil is not None else None,
            'comparaison': (
                'au-dessus' if ecart_seuil is not None and ecart_seuil >= 0
                else 'sous le seuil' if ecart_seuil is not None
                else 'seuil indisponible'
            ),
            'historique': [
                {
                    'date': _date_iso(mesure.date_visite),
                    'debit': float(mesure.debit_l_s),
                }
                for mesure in reversed(debit_mesures)
            ],
        }

    return JsonResponse({
        'success': True,
        'ouvrage': {
            'id': str(ouvrage.id),
            'nom': ouvrage.nom_ouvrage,
            'type': getattr(ouvrage.type_ouvrage, 'nom_type_ouvrage', '') or '',
            'annee_realisation': ouvrage.annee_realisation,
            'annee_realisation_avant': ouvrage.annee_realisation_avant,
            'intervenant': ouvrage.intervenant or '',
            'saisonnier': ouvrage.saisonnier,
            'observation': ouvrage.observation or '',
            'stats': {
                'points_eau': points_statuts['actifs'],
                'points_eau_coupes': points_statuts['coupes'],
                'points_eau_sans_date': points_statuts['sans_date'],
                'equipements': equipements_qs.count(),
                'compteurs': ouvrage.compteurs_tete.count(),
                'plannings': Planning.objects.filter(ouvrage=ouvrage).count(),
            },
            'localisations': location_rows,
            'modalites': modalites,
            'tarifs': tarifs,
            'points_eau': points,
            'equipements': equipements,
            'reparations_non_terminees': reparations,
            'paiements_echus_non_pointes': paiements_echus,
            'prochains_paiements': prochains_paiements,
            'debit_source': debit_source,
            'full_url': request.build_absolute_uri(
                f'/recherche/details/ouvrage/{ouvrage.id}/'
            ),
        },
    })


# --------------------------------------------------------------------------- #
#  Widgets "Calendrier planning" / "Activites du jour"
#
#  Vue personnelle des activites de planning (recouvrement forfaitaire,
#  reparation, et toute autre valeur de type_activite) : chaque utilisateur
#  voit ses propres activites assignees, plus celles de ses subordonnes actifs
#  (meme hierarchie que _apply_employe_hierarchy_ouvrage_scope ci-dessus, mais
#  appliquee directement sur Planning.employe plutot que sur les ouvrages
#  dont on est responsable -- ce sont deux notions de perimetre differentes).
#  Un superuser ou un directeur voit tout, comme partout ailleurs dans ce
#  fichier. Filtres additionnels optionnels (query string) : employe_id,
#  base_id, region_id/district_id/commune_id (mutuellement exclusifs, du plus
#  precis au moins precis), type_activite_id (repetable). Un seul endpoint de
#  donnees pour les deux widgets : le widget "Activites du jour" appelle avec
#  debut=fin=aujourd'hui, le widget "Calendrier planning" avec la plage du
#  mois affiche.
# --------------------------------------------------------------------------- #

def _widget_planning_allowed_employe_ids(user, reference_date=None):
    """None = pas de restriction (superuser/directeur). Sinon l'ensemble des
    employes dont les activites sont visibles : soi-meme + subordonnes actifs
    de la hierarchie (HierarchieEmploye), ou aucun si l'utilisateur n'a pas de
    fiche employe liee."""
    if getattr(user, 'is_superuser', False) or is_directeur_poste(user):
        return None
    employe = getattr(user, 'employe', None)
    if not employe:
        return set()
    return _get_active_subordinate_employe_ids(employe.id, reference_date)


def _widget_planning_base_queryset(request):
    """Planning visible par l'utilisateur avant application des filtres
    optionnels de la requete -- voir _apply_widget_planning_filters."""
    allowed_employe_ids = _widget_planning_allowed_employe_ids(request.user)
    qs = Planning.objects.select_related(
        'employe', 'employe__base', 'employe__poste', 'type_activite', 'ouvrage',
    )
    if allowed_employe_ids is not None:
        qs = qs.filter(employe_id__in=allowed_employe_ids)
    return qs


def _apply_widget_planning_filters(qs, request):
    """Applique les filtres optionnels envoyes par les widgets, en plus du
    perimetre personnel deja applique par _widget_planning_base_queryset."""
    employe_id = (request.GET.get('employe_id') or '').strip()
    if employe_id:
        qs = qs.filter(employe_id=employe_id)

    base_id = (request.GET.get('base_id') or '').strip()
    if base_id:
        qs = qs.filter(employe__base_id=base_id)

    commune_id = (request.GET.get('commune_id') or '').strip()
    district_id = (request.GET.get('district_id') or '').strip()
    region_id = (request.GET.get('region_id') or '').strip()
    if commune_id:
        qs = qs.filter(ouvrage__pointeau__parcelle__village__fokontany__commune_id=commune_id)
    elif district_id:
        qs = qs.filter(ouvrage__pointeau__parcelle__village__fokontany__commune__district_id=district_id)
    elif region_id:
        qs = qs.filter(ouvrage__pointeau__parcelle__village__fokontany__commune__district__region_id=region_id)

    type_activite_ids = [value for value in request.GET.getlist('type_activite_id') if value]
    if type_activite_ids:
        qs = qs.filter(type_activite_id__in=type_activite_ids)

    return qs.distinct()


def _widget_planning_type_activite_choices(qs):
    """Types d'activite reellement presents dans le perimetre courant --
    recouvrement forfaitaire et reparation y figureront naturellement s'ils
    sont utilises, sans liste figee en dur cote serveur."""
    type_ids = qs.exclude(type_activite__isnull=True).values_list('type_activite_id', flat=True).distinct()
    return list(
        TypeActivite.objects.filter(id__in=type_ids).order_by('nomtype').values('id', 'nomtype')
    )


@widget_auth_required
@require_GET
def api_widget_planning_filtres(request):
    """Options de filtrage pour les widgets Calendrier planning / Activites du
    jour : personnes, bases, regions, districts, communes et types d'activite,
    tous derives du perimetre personnel de l'utilisateur courant."""
    base_qs = _widget_planning_base_queryset(request)

    employe_ids = base_qs.exclude(employe__isnull=True).values_list('employe_id', flat=True).distinct()
    employes = list(
        Employe.objects.filter(id__in=employe_ids)
        .select_related('poste', 'base')
        .order_by('nom', 'prenom')
    )

    base_ids = {employe.base_id for employe in employes if employe.base_id}
    bases = list(Base.objects.filter(id__in=base_ids).order_by('nom_base').values('id', 'nom_base'))

    ouvrage_ids = base_qs.exclude(ouvrage__isnull=True).values_list('ouvrage_id', flat=True).distinct()
    ouvrages_qs = Ouvrage.objects.filter(id__in=ouvrage_ids).exclude(pointeau__isnull=True)
    region_ids = set(ouvrages_qs.values_list(
        'pointeau__parcelle__village__fokontany__commune__district__region_id', flat=True,
    ))
    district_ids = set(ouvrages_qs.values_list(
        'pointeau__parcelle__village__fokontany__commune__district_id', flat=True,
    ))
    commune_ids = set(ouvrages_qs.values_list(
        'pointeau__parcelle__village__fokontany__commune_id', flat=True,
    ))

    regions = Region.objects.filter(id__in=region_ids).order_by('nom_region').values('id', 'nom_region')
    districts = District.objects.filter(id__in=district_ids).order_by('nom_district').values(
        'id', 'nom_district', 'region_id',
    )
    communes = Commune.objects.filter(id__in=commune_ids).order_by('nom_commune').values(
        'id', 'nom_commune', 'district_id',
    )

    return JsonResponse({
        'success': True,
        'employes': [
            {
                'id': str(employe.id),
                'nom': employe.nom_affichage,
                'base_id': str(employe.base_id) if employe.base_id else None,
            }
            for employe in employes
        ],
        'bases': [{'id': str(b['id']), 'nom': b['nom_base']} for b in bases],
        'regions': [{'id': str(r['id']), 'nom': r['nom_region']} for r in regions],
        'districts': [
            {'id': str(d['id']), 'nom': d['nom_district'], 'region_id': str(d['region_id'])}
            for d in districts
        ],
        'communes': [
            {'id': str(c['id']), 'nom': c['nom_commune'], 'district_id': str(c['district_id'])}
            for c in communes
        ],
        'types_activite': [
            {'id': str(t['id']), 'nom': t['nomtype']}
            for t in _widget_planning_type_activite_choices(base_qs)
        ],
    })


def _planning_activite_est_collecte_paiement(planning):
    return bool(planning.type_activite and planning.type_activite.nomtype == 'Collecte paiement')


def _planning_activite_est_termine(planning, paiements_pairs=None):
    """Une activite "Collecte paiement" est consideree terminee quand toutes ses
    lignes de paiement forfaitaire liees (PaiementForfaitaire.planning) sont
    pointees -- numeroDiameX + baseDiameX renseignes, meme definition du
    pointage que _diamex_non_pointed_ids plus haut dans ce fichier. Sans ligne
    liee, l'activite n'est pas consideree terminee (rien n'a encore ete
    enregistre). Toute autre activite suit simplement son statut manuel."""
    if _planning_activite_est_collecte_paiement(planning):
        if paiements_pairs is None:
            paiements_pairs = list(
                PaiementForfaitaire.objects.filter(planning_id=planning.id)
                .values_list('numeroDiameX', 'baseDiameX')
            )
        if not paiements_pairs:
            return False
        return all(_diamex_pair(numero, base) for numero, base in paiements_pairs)
    return planning.statut == 'termine'


def _serialize_widget_planning_activite(planning, commune_nom='', paiements_pairs=None):
    planning_date = planning.date
    if planning_date and timezone.is_aware(planning_date):
        planning_date = timezone.localtime(planning_date, TZ_MADAGASCAR)

    return {
        'id': str(planning.id),
        'date': planning_date.date().isoformat() if planning_date else '',
        'heure': planning_date.strftime('%H:%M') if planning_date else '',
        'activite': planning.activite_display,
        'type_activite_id': str(planning.type_activite_id) if planning.type_activite_id else '',
        'type_activite': planning.type_activite.nomtype if planning.type_activite else '',
        'ouvrage_id': str(planning.ouvrage_id) if planning.ouvrage_id else '',
        'ouvrage': planning.ouvrage.nom_ouvrage if planning.ouvrage else '',
        'commune': commune_nom or '',
        'employe_id': str(planning.employe_id) if planning.employe_id else '',
        'employe': planning.employe.nom_affichage if planning.employe else 'Non affecte',
        'base': planning.employe.base.nom_base if planning.employe and planning.employe.base else '',
        'statut': planning.get_statut_display() if planning.statut else '',
        'termine': _planning_activite_est_termine(planning, paiements_pairs),
        # Vrai pour "Collecte paiement" : le statut termine/en cours est calcule
        # automatiquement d'apres le pointage, pas modifiable depuis le modal.
        'termine_auto': _planning_activite_est_collecte_paiement(planning),
        'remarque': planning.remarque or '',
    }


@widget_auth_required
@require_GET
def api_widget_planning_activites(request):
    """Activites de planning sur une plage de dates, filtrables par
    personne/base/region/district/commune/type -- endpoint unique partage par
    les widgets Calendrier planning (plage = mois affiche) et Activites du
    jour (debut=fin=aujourd'hui)."""
    today_mg = timezone.now().astimezone(TZ_MADAGASCAR).date()

    debut_str = (request.GET.get('debut') or '').strip()
    fin_str = (request.GET.get('fin') or '').strip()
    try:
        debut = date.fromisoformat(debut_str) if debut_str else today_mg
    except ValueError:
        return JsonResponse(
            {'success': False, 'error': "Parametre 'debut' invalide (AAAA-MM-JJ attendu)."}, status=400,
        )
    try:
        fin = date.fromisoformat(fin_str) if fin_str else debut
    except ValueError:
        return JsonResponse(
            {'success': False, 'error': "Parametre 'fin' invalide (AAAA-MM-JJ attendu)."}, status=400,
        )
    if fin < debut:
        return JsonResponse(
            {'success': False, 'error': "'fin' ne peut pas etre avant 'debut'."}, status=400,
        )

    qs = _apply_widget_planning_filters(_widget_planning_base_queryset(request), request)
    qs = qs.filter(date__date__gte=debut, date__date__lte=fin).order_by('date')
    plannings = list(qs)

    # Une seule requete pour retrouver la commune de chaque ouvrage implique,
    # plutot qu'une requete par ligne serialisee (evite le N+1).
    ouvrage_ids = {p.ouvrage_id for p in plannings if p.ouvrage_id}
    commune_par_ouvrage = dict(
        Ouvrage.objects.filter(id__in=ouvrage_ids)
        .exclude(pointeau__isnull=True)
        .values_list('id', 'pointeau__parcelle__village__fokontany__commune__nom_commune')
    )

    # Idem pour le pointage des collectes de paiement : une seule requete
    # groupee plutot qu'une requete par ligne (voir _planning_activite_est_termine).
    collecte_ids = [p.id for p in plannings if _planning_activite_est_collecte_paiement(p)]
    paiements_par_planning = {}
    if collecte_ids:
        for planning_id, numero, base in PaiementForfaitaire.objects.filter(
            planning_id__in=collecte_ids,
        ).values_list('planning_id', 'numeroDiameX', 'baseDiameX'):
            paiements_par_planning.setdefault(planning_id, []).append((numero, base))

    return JsonResponse({
        'success': True,
        'debut': debut.isoformat(),
        'fin': fin.isoformat(),
        'activites': [
            _serialize_widget_planning_activite(
                p,
                commune_par_ouvrage.get(p.ouvrage_id, ''),
                paiements_pairs=paiements_par_planning.get(p.id, []) if _planning_activite_est_collecte_paiement(p) else None,
            )
            for p in plannings
        ],
    })


def _widget_planning_can_manage(user, planning, new_employe_id=None):
    """Autorise la modification si l'employe assigne actuel (et le nouvel
    employe cible, en cas de reaffectation) sont dans le perimetre personnel de
    l'utilisateur -- meme regle que la lecture (_widget_planning_allowed_employe_ids),
    sans restriction pour un superuser/directeur."""
    allowed_ids = _widget_planning_allowed_employe_ids(user)
    if allowed_ids is None:
        return True
    allowed_ids = {str(value) for value in allowed_ids}
    if planning.employe_id and str(planning.employe_id) not in allowed_ids:
        return False
    if new_employe_id and str(new_employe_id) not in allowed_ids:
        return False
    return True


@csrf_exempt
@widget_auth_required
@require_POST
def api_widget_planning_activite_update(request, planning_id):
    """Modifie une activite de planning (personne assignee, date, et statut
    termine/en cours) depuis les widgets Calendrier planning / Activites du
    jour. Pour "Collecte paiement", le statut est calcule automatiquement
    d'apres le pointage (voir _planning_activite_est_termine) et ne peut pas
    etre force par cet endpoint."""
    try:
        planning = Planning.objects.select_related(
            'type_activite', 'employe', 'employe__base', 'ouvrage',
        ).get(pk=planning_id)
    except Planning.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Activite introuvable.'}, status=404)

    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'JSON invalide.'}, status=400)

    new_employe_id = (payload.get('employe_id') or '').strip() or None
    if not _widget_planning_can_manage(request.user, planning, new_employe_id):
        return JsonResponse(
            {'success': False, 'error': "Vous n'avez pas le droit de modifier cette activite."}, status=403,
        )

    update_fields = []

    if new_employe_id and new_employe_id != str(planning.employe_id or ''):
        try:
            planning.employe = Employe.objects.get(pk=new_employe_id)
        except Employe.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Employe introuvable.'}, status=400)
        update_fields.append('employe')

    date_str = (payload.get('date') or '').strip()
    if date_str:
        try:
            new_date = date.fromisoformat(date_str)
        except ValueError:
            return JsonResponse(
                {'success': False, 'error': "Date invalide (AAAA-MM-JJ attendu)."}, status=400,
            )
        current = planning.date or timezone.now()
        planning.date = current.replace(year=new_date.year, month=new_date.month, day=new_date.day)
        update_fields.append('date')

    if 'termine' in payload:
        if _planning_activite_est_collecte_paiement(planning):
            return JsonResponse({
                'success': False,
                'error': (
                    "Le statut des collectes de paiement est calcule automatiquement "
                    "d'apres le pointage, il ne peut pas etre modifie manuellement."
                ),
            }, status=400)
        planning.statut = 'termine' if payload.get('termine') else 'en_cours'
        update_fields.append('statut')

    if update_fields:
        update_fields.append('updated_at')
        planning.save(update_fields=update_fields)

    commune_nom = ''
    if planning.ouvrage_id:
        commune_nom = Ouvrage.objects.filter(id=planning.ouvrage_id).exclude(
            pointeau__isnull=True,
        ).values_list(
            'pointeau__parcelle__village__fokontany__commune__nom_commune', flat=True,
        ).first() or ''

    return JsonResponse({'success': True, 'activite': _serialize_widget_planning_activite(planning, commune_nom)})
