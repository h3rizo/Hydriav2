from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from django.conf import settings
from types import SimpleNamespace
from .models import Planning, PlanningDetail, Designation, IndemniteJournaliere, BonLivraison
from .views_simple import _is_planning_operation_advanced
from apps.billing.models import FraisTransfertMvola, PaiementForfaitaire
from apps.employees.models import Employe
from apps.inventory.models import Stock, FicheStock, PurchaseItem
from apps.inventory.models_vehicles import AffectationVehicule
from apps.organization.models import Base, Magasin
import json
import logging
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from io import BytesIO
import datetime
from decimal import Decimal
import unicodedata
import uuid
import os


def _normalize_poste_name(value):
    if not value:
        return ''
    normalized = unicodedata.normalize('NFKD', str(value))
    return normalized.encode('ascii', errors='ignore').decode('ascii').lower().strip()


def _resolve_article_date(value):
    if not value:
        return None
    return value.date() if hasattr(value, 'date') else value


def _format_forfaitaire_tranche_label(numero):
    try:
        numero_int = int(numero)
    except (TypeError, ValueError):
        return ''

    if numero_int <= 0:
        return ''
    return f'Tranche faha-{numero_int}'


def _load_forfaitaire_history(point_eau_ids):
    """Charge en une requete l'historique des paiements forfaitaires par point d'eau.

    Retourne {point_eau_id: [(id, date_facture, created_at, quantite, montant), ...]}
    trie par (date_facture, created_at). Evite 2 requetes par ligne affichee.
    """
    history = {}
    rows = PaiementForfaitaire.objects.filter(
        point_eau_id__in=list(point_eau_ids)
    ).order_by('date_facture', 'created_at').values_list(
        'id', 'point_eau_id', 'date_facture', 'created_at', 'quantite', 'montant'
    )
    for pid, pe_id, date_f, created, qte, montant in rows:
        history.setdefault(pe_id, []).append((pid, date_f, created, qte, montant))
    return history


def _build_forfaitaire_tranches_header(paiement, history=None):
    point_eau_id = getattr(paiement, 'point_eau_id', None)
    date_facture = getattr(paiement, 'date_facture', None)
    quantite = int(getattr(paiement, 'quantite', None) or 0)
    if not point_eau_id or not date_facture or quantite <= 0:
        return ''

    if history is not None:
        created_at = getattr(paiement, 'created_at', None)
        tranches_precedentes = 0
        for pid, date_f, created, qte, _montant in history.get(point_eau_id, []):
            if pid == paiement.id or date_f.year != date_facture.year:
                continue
            if date_f < date_facture or (
                date_f == date_facture and created and created_at and created < created_at
            ):
                tranches_precedentes += int(qte or 0)
    else:
        paiements_anterieurs = (
            PaiementForfaitaire.objects.filter(
                point_eau_id=point_eau_id,
                date_facture__year=date_facture.year,
            )
            .filter(
                Q(date_facture__lt=date_facture)
                | Q(date_facture=date_facture, created_at__lt=getattr(paiement, 'created_at', None))
            )
            .exclude(id=paiement.id)
        )
        tranches_precedentes = sum(
            int(item.quantite or 0)
            for item in paiements_anterieurs.only('quantite')
        )
    debut_tranche = tranches_precedentes + 1
    fin_tranche = tranches_precedentes + quantite

    labels = [
        _format_forfaitaire_tranche_label(numero)
        for numero in range(debut_tranche, fin_tranche + 1)
    ]
    labels = [label for label in labels if label]
    if not labels:
        return ''
    if len(labels) == 1:
        return f"{labels[0]} taona {date_facture.year}"
    return f"{' sy '.join(labels)} taona {date_facture.year}"


def _build_forfaitaire_prochaine_echeance(paiement, history=None):
    date_fin_validite = getattr(paiement, 'date_fin_validite', None)
    date_facture = getattr(paiement, 'date_facture', None)
    quantite = int(getattr(paiement, 'quantite', None) or 0)
    prix_unitaire = getattr(paiement, 'prix_unitaire', None)
    point_eau = getattr(paiement, 'point_eau', None)

    try:
        from dateutil.relativedelta import relativedelta

        if history is not None:
            prochaine_facture = None
            for _pid, date_f, _created, _qte, montant_f in history.get(getattr(paiement, 'point_eau_id', None), []):
                if date_facture and date_f > date_facture:
                    prochaine_facture = SimpleNamespace(date_facture=date_f, montant=montant_f)
                    break
        else:
            prochaine_facture = (
                PaiementForfaitaire.objects.filter(
                    point_eau_id=getattr(paiement, 'point_eau_id', None),
                    date_facture__gt=date_facture,
                )
                .order_by('date_facture', 'created_at')
                .only('date_facture', 'montant')
                .first()
            )
        if prochaine_facture and prochaine_facture.date_facture:
            prochaine_date = prochaine_facture.date_facture
            prochaine_montant = getattr(prochaine_facture, 'montant', None)
            if prochaine_montant is None and point_eau and getattr(point_eau, 'tarifforfaitaire', None):
                prochaine_montant = Decimal(str(point_eau.tarifforfaitaire))
            return prochaine_date, Decimal(str(prochaine_montant or 0))

        if not date_fin_validite and date_facture and quantite > 0:
            date_fin_validite = date_facture + relativedelta(months=quantite * 3) - datetime.timedelta(days=1)
        if not date_fin_validite:
            return None, Decimal(str(getattr(point_eau, 'tarifforfaitaire', None) or prix_unitaire or 0))

        prochaine_date = date_fin_validite + relativedelta(days=1)
        prochaine_montant = getattr(point_eau, 'tarifforfaitaire', None) or prix_unitaire or 0
        return prochaine_date, Decimal(str(prochaine_montant))
    except Exception:
        return None, None


def _get_pending_planning_detail_cutoff_date(today=None):
    reference_day = today or timezone.localdate()
    return reference_day - datetime.timedelta(days=30)


def _parse_month_filter(raw_value):
    if not raw_value:
        return None

    try:
        return datetime.datetime.strptime(raw_value, "%Y-%m")
    except ValueError:
        return None


def _parse_positive_decimal_override(value, field_name):
    try:
        decimal_value = Decimal(str(value).replace(',', '.'))
    except Exception:
        raise ValueError(f"{field_name} invalide")
    if decimal_value < 0:
        raise ValueError(f"{field_name} ne peut pas etre negatif")
    return decimal_value


def _is_pending_planning_detail_visible(planning_date, *, livraison=False, utilise=False, retour=False, today=None):
    if livraison or utilise or retour:
        return False

    operation_date = _resolve_article_date(planning_date)
    if not operation_date:
        return True

    return operation_date > _get_pending_planning_detail_cutoff_date(today=today)


def _get_pending_planning_date_filter(today=None):
    latest_visible_date = _get_pending_planning_detail_cutoff_date(today=today)
    return Q(planning__date__isnull=True) | Q(planning__date__date__lte=latest_visible_date)


def _avance_or_recette_designation_q():
    return (
        Q(designation__type_avance_caissiere__iexact='avance') |
        Q(designation__type_avance_caissiere__iexact='recette')
    )


def _livraison_designation_q():
    return (
        Q(designation__type_avance_caissiere__iexact='bon_livraison') |
        Q(designation__concerne_livraison=True)
    )


def _ensure_pending_bons_livraison_for_allowed_plannings(allowed_planning_ids):
    if not allowed_planning_ids:
        return

    legacy_details = PlanningDetail.objects.filter(
        _get_pending_planning_date_filter(),
        planning_id__in=allowed_planning_ids,
        planning__estvalide=True,
        livraison=False,
    ).filter(
        _livraison_designation_q()
    ).select_related(
        'planning',
        'designation',
        'point_eau',
        'equipement_constitutif',
    )

    for detail in legacy_details:
        exists = BonLivraison.objects.filter(
            planning_id=detail.planning_id,
            designation_id=detail.designation_id,
            point_eau_id=detail.point_eau_id,
            equipement_id=detail.equipement_constitutif_id,
            quantite=detail.quantity,
            utilise=False,
            retour=False,
        ).exists()
        if exists:
            continue

        BonLivraison.objects.create(
            planning=detail.planning,
            point_eau=detail.point_eau,
            equipement=detail.equipement_constitutif,
            designation=detail.designation,
            quantite=detail.quantity or 0,
            magasin='',
            utilise=False,
            retour=False,
        )


def _normalize_sort_text(value):
    if value is None:
        return ''
    normalized = unicodedata.normalize('NFKD', str(value))
    return normalized.encode('ascii', errors='ignore').decode('ascii').lower().strip()


def _get_employe_label(employe):
    if not employe:
        return '-'

    label = (
        getattr(employe, 'surnom', None)
        or getattr(employe, 'nom_employe', None)
        or getattr(employe, 'prenom', None)
        or getattr(employe, 'nom', None)
        or '-'
    )
    return str(label).strip() or '-'


def _get_employe_initials(employe):
    label = _get_employe_label(employe)
    if not label or label == '-':
        return '??'
    tokens = [token for token in str(label).split() if token]
    if not tokens:
        return '??'
    initials = ''.join(token[0] for token in tokens[:2]).upper()
    return initials or '??'


def _get_planning_effective_employe(planning):
    if not planning:
        return None

    employe = getattr(planning, 'employe', None)
    if employe:
        return employe

    planning_employees = getattr(planning, 'planning_employees', None)
    if not planning_employees:
        return None

    for participant in planning_employees.all():
        employee = getattr(participant, 'employee', None)
        if employee:
            return employee
    return None


def _get_point_eau_label(point_eau):
    if not point_eau:
        return ''

    parts = []
    idxls = getattr(point_eau, 'idxls', None)
    nom_abonne = getattr(point_eau, 'nomabonne', None)
    code_point_eau = getattr(point_eau, 'code_point_eau', None)

    if idxls:
        parts.append(str(idxls).strip())
    if nom_abonne:
        parts.append(str(nom_abonne).strip())
    elif code_point_eau:
        parts.append(str(code_point_eau).strip())

    return ' - '.join(part for part in parts if part)


EMPLOYEE_EQUIPMENT_RULES = {
    'moto': {
        'label': 'Moto',
        'period_days': 0,
        'max_quantity': 1,
        'keywords': [],
        'managed_via_vehicle_assignment': True,
        'show_in_form': False,
    },
    'botte': {
        'label': 'Botte',
        'period_days': 365,
        'max_quantity': 1,
        'keywords': ['botte', 'bottes'],
        'show_in_form': True,
    },
    'sac_a_dos': {
        'label': 'Sac a dos',
        'period_days': 730,
        'max_quantity': 1,
        'keywords': ['sac a dos', 'sacados', 'sac a doss', 'backpack'],
        'show_in_form': True,
    },
    'impermeable': {
        'label': 'Impermeable',
        'period_days': 730,
        'max_quantity': 1,
        'keywords': ['impermeable', 'kway', 'k way', 'k-way'],
        'show_in_form': True,
    },
    'gilet': {
        'label': 'Gilet',
        'period_days': 365,
        'max_quantity': 1,
        'keywords': ['gilet', 'gilets', 'gilet de visibilite', 'gilet de securite'],
        'show_in_form': True,
    },
    'badge': {
        'label': 'Badge',
        'period_days': 365,
        'max_quantity': 1,
        'keywords': ['badge', 'badget', 'badges'],
        'show_in_form': True,
    },
    'casque_moto': {
        'label': 'Casque moto',
        'period_days': 365,
        'max_quantity': 1,
        'keywords': ['casque moto', 'casque de moto'],
        'requires_active_moto': True,
        'unique_asset_assignment': True,
        'show_in_form': True,
    },
    'bicyclette': {
        'label': 'Bicyclette',
        'period_days': 1095,
        'max_quantity': 1,
        'keywords': ['bicyclette', 'velo'],
        'strict_names': ['bicyclette', 'velo'],
        'exclude_keywords': ['developpement', 'enveloppe'],
        'allowed_postes': ['mpikojakoja ifotony'],
        'show_in_form': True,
    },
    'ordinateur_portable': {
        'label': 'Ordinateur portable',
        'period_days': 365,
        'max_quantity': 1,
        'keywords': ['ordinateur de bureau', 'ordinateur marque', 'ordinateur portable', 'laptop', 'pc portable'],
        'exclude_keywords': ['ecran', 'clavier', 'batterie', 'ram'],
        'excluded_postes': ['gardien', 'mpikojakoja ifotony'],
        'unique_asset_assignment': True,
        'show_in_form': True,
    },
}

EMPLOYEE_EQUIPMENT_REFERENCE_PREFIX = 'DOT'
EMPLOYEE_EQUIPMENT_NOTE_MARKER = '[DOTATION_EQUIPEMENT_EMPLOYE]'


def _normalize_equipment_text(value):
    if not value:
        return ''
    normalized = unicodedata.normalize('NFKD', str(value))
    ascii_value = normalized.encode('ascii', errors='ignore').decode('ascii').lower()
    return ' '.join(ascii_value.strip().split())


def _classify_employee_equipment_designation(designation_name):
    normalized_name = _normalize_equipment_text(designation_name)
    if not normalized_name:
        return None

    for equipment_type, rule in EMPLOYEE_EQUIPMENT_RULES.items():
        exclude_keywords = rule.get('exclude_keywords') or []
        if any(keyword in normalized_name for keyword in exclude_keywords):
            continue

        strict_names = rule.get('strict_names') or []
        if strict_names:
            if normalized_name in strict_names:
                return equipment_type
            continue

        for keyword in rule['keywords']:
            if keyword in normalized_name:
                return equipment_type
    return None


def _is_employee_equipment_allowed_for_employe(equipment_type, employe):
    rule = EMPLOYEE_EQUIPMENT_RULES.get(equipment_type) or {}
    allowed_postes = rule.get('allowed_postes') or []
    poste_name = _normalize_poste_name(getattr(getattr(employe, 'poste', None), 'nom_poste', ''))
    if allowed_postes and poste_name not in allowed_postes:
        return False

    excluded_postes = rule.get('excluded_postes') or []
    if excluded_postes and poste_name in excluded_postes:
        return False

    return True


def _get_employee_active_moto_affectations(user):
    affectations = (
        AffectationVehicule.objects.select_related('vehicule', 'employe')
        .filter(
            date_fin__isnull=True,
            vehicule__actif=True,
            vehicule__type_vehicule='moto',
            employe__date_debauchage__isnull=True,
            employe__salarie=True,
        )
        .order_by('vehicule__immatriculation', '-date_debut')
    )

    employe = getattr(user, 'employe', None)
    if employe and employe.base_id:
        organisation_id = getattr(employe.base, 'organisation_id', None)
        if organisation_id:
            affectations = affectations.filter(employe__base__organisation_id=organisation_id)
        else:
            affectations = affectations.filter(employe__base_id=employe.base_id)
    elif not getattr(user, 'is_superuser', False):
        affectations = affectations.none()

    moto_map = {}
    for affectation in affectations:
        moto_map.setdefault(str(affectation.employe_id), []).append(affectation)
    return moto_map


def _is_employee_equipment_fiche(fiche):
    notes_value = str(getattr(fiche, 'notes', '') or '')
    reference_value = str(getattr(fiche, 'reference', '') or '')
    return (
        EMPLOYEE_EQUIPMENT_NOTE_MARKER in notes_value
        or reference_value.startswith(f'{EMPLOYEE_EQUIPMENT_REFERENCE_PREFIX}-')
    )


def _build_employee_equipment_reference():
    return f"{EMPLOYEE_EQUIPMENT_REFERENCE_PREFIX}-{timezone.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"


def _extract_employee_equipment_note_context(notes_value):
    context = {
        'magasin_id': '',
        'magasin_nom': '',
        'employe_id': '',
        'equipment_type': '',
        'custom_notes': '',
    }
    raw_notes = str(notes_value or '')
    if not raw_notes:
        return context

    parts = [part.strip() for part in raw_notes.split(' - ') if part.strip()]
    custom_parts = []
    for part in parts:
        if part == EMPLOYEE_EQUIPMENT_NOTE_MARKER:
            continue
        if part.startswith('Type: '):
            context['equipment_type'] = part.replace('Type: ', '', 1).strip()
            continue
        if part.startswith('Magasin ID: '):
            context['magasin_id'] = part.replace('Magasin ID: ', '', 1).strip()
            continue
        if part.startswith('Magasin: '):
            context['magasin_nom'] = part.replace('Magasin: ', '', 1).strip()
            continue
        if part.startswith('Employe ID: '):
            context['employe_id'] = part.replace('Employe ID: ', '', 1).strip()
            continue
        custom_parts.append(part)

    context['custom_notes'] = ' - '.join(custom_parts).strip()
    return context


def _build_employee_equipment_note(equipment_type, magasin, employe, notes=''):
    note_parts = [
        EMPLOYEE_EQUIPMENT_NOTE_MARKER,
        f"Type: {equipment_type}",
        f"Magasin ID: {magasin.id}",
        f"Magasin: {magasin.nom_magasin}",
        f"Employe ID: {employe.id}",
    ]
    if notes:
        note_parts.append(notes)
    return ' - '.join(note_parts)


def _get_employee_equipment_designations_queryset():
    return Designation.objects.filter(
        concerne_livraison=True,
        actif=True,
    ).select_related('type_designation').order_by('nom')


def _get_active_employes_queryset(user):
    queryset = Employe.objects.select_related('base', 'poste').filter(
        date_debauchage__isnull=True,
        salarie=True,
    )
    
    employe = getattr(user, 'employe', None)
    if employe and employe.base_id:
        organisation_id = getattr(employe.base, 'organisation_id', None)
        if organisation_id:
            queryset = queryset.filter(base__organisation_id=organisation_id)
        else:
            queryset = queryset.filter(base_id=employe.base_id)
    elif not getattr(user, 'is_superuser', False):
        queryset = queryset.none()
        
    return queryset.order_by('base__nom_base', 'poste__ordre_affichage', 'poste__nom_poste', 'nom', 'prenom', 'surnom')


def _get_agents_recouvrement_queryset(user):
    """Employes actifs de l'organisation dont le poste est « Agent de recouvrement »."""
    return _get_active_employes_queryset(user).filter(poste__nom_poste__icontains='agent de recouvrement')


def _get_scoped_magasins_queryset(user):
    magasins = Magasin.objects.select_related('base').all()
    employe = getattr(user, 'employe', None)

    if employe and employe.base_id:
        organisation_id = getattr(employe.base, 'organisation_id', None)
        if organisation_id:
            return magasins.filter(base__organisation_id=organisation_id).order_by('base__nom_base', 'nom_magasin')
        return magasins.filter(base_id=employe.base_id).order_by('base__nom_base', 'nom_magasin')
        
    if getattr(user, 'is_superuser', False):
        return magasins.order_by('base__nom_base', 'nom_magasin')
    return magasins.none()


def _get_employee_equipment_fiches_queryset(user):
    return FicheStock.objects.select_related(
        'employee',
        'employee__base',
        'designation',
        'base',
    ).filter(
        operation_type='livraison',
        employee__isnull=False,
        employee__salarie=True,
    )


def _filter_employee_equipment_fiches_by_scope(queryset, user):
    employe = getattr(user, 'employe', None)
    
    if employe and employe.base_id:
        organisation_id = getattr(employe.base, 'organisation_id', None)
        if organisation_id:
            return queryset.filter(employee__base__organisation_id=organisation_id)
        return queryset.filter(employee__base_id=employe.base_id)
        
    if getattr(user, 'is_superuser', False):
        return queryset
    return queryset.none()


def _build_employee_equipment_statuses(employes, fiches, active_moto_affectations_by_employee=None):
    deliveries_by_employee = {}
    now = timezone.localdate()
    active_moto_affectations_by_employee = active_moto_affectations_by_employee or {}

    for fiche in fiches:
        if not _is_employee_equipment_fiche(fiche):
            continue
        equipment_type = _classify_employee_equipment_designation(getattr(getattr(fiche, 'designation', None), 'nom', ''))
        if not equipment_type:
            continue
        deliveries_by_employee.setdefault(str(fiche.employee_id), {}).setdefault(equipment_type, []).append(fiche)

    statuses_by_employee = {}
    for employe in employes:
        employee_key = str(employe.id)
        equipment_statuses = {}
        for equipment_type, rule in EMPLOYEE_EQUIPMENT_RULES.items():
            if not _is_employee_equipment_allowed_for_employe(equipment_type, employe):
                equipment_statuses[equipment_type] = None
                continue

            moto_affectations = active_moto_affectations_by_employee.get(employee_key, [])
            has_active_moto = bool(moto_affectations)
            if rule.get('managed_via_vehicle_assignment'):
                moto_affectation = moto_affectations[0] if moto_affectations else None
                moto_label = 'Affectee' if moto_affectation else 'Aucune'
                equipment_statuses[equipment_type] = {
                    'type': equipment_type,
                    'label': rule['label'],
                    'state': 'info' if moto_affectation else 'none',
                    'state_label': moto_label,
                    'count_in_period': 1 if moto_affectation else 0,
                    'remaining': 0,
                    'period_days': 0,
                    'last_delivery': None,
                    'next_allowed_date': None,
                    'deliveries': [],
                    'vehicle_assignment': moto_affectation,
                }
                continue

            if rule.get('requires_active_moto') and not has_active_moto:
                equipment_statuses[equipment_type] = None
                continue

            deliveries = sorted(
                deliveries_by_employee.get(employee_key, {}).get(equipment_type, []),
                key=lambda fiche: fiche.operation_date or timezone.now(),
                reverse=True,
            )
            period_start = now - datetime.timedelta(days=rule['period_days'])
            deliveries_in_period = []
            for fiche in deliveries:
                operation_date = _resolve_article_date(getattr(fiche, 'operation_date', None))
                if operation_date and operation_date >= period_start:
                    deliveries_in_period.append(fiche)

            count_in_period = len(deliveries_in_period)
            remaining = max(rule['max_quantity'] - count_in_period, 0)
            last_delivery = deliveries[0] if deliveries else None
            next_allowed_date = None
            state = 'eligible'
            state_label = 'Eligible'

            if count_in_period > rule['max_quantity']:
                state = 'depasse'
                state_label = 'Depasse'
            elif count_in_period >= rule['max_quantity']:
                state = 'quota_atteint'
                state_label = 'Quota atteint'

            if last_delivery and getattr(last_delivery, 'operation_date', None):
                last_delivery_date = _resolve_article_date(last_delivery.operation_date)
                if last_delivery_date:
                    next_allowed_date = last_delivery_date + datetime.timedelta(days=rule['period_days'])

            equipment_statuses[equipment_type] = {
                'type': equipment_type,
                'label': rule['label'],
                'state': state,
                'state_label': state_label,
                'count_in_period': count_in_period,
                'remaining': remaining,
                'period_days': rule['period_days'],
                'last_delivery': last_delivery,
                'next_allowed_date': next_allowed_date,
                'deliveries': deliveries[:5],
                'shared_allowed': bool(rule.get('shared_allowed')),
            }
        statuses_by_employee[employee_key] = equipment_statuses

    return statuses_by_employee


def _get_assigned_unique_asset_designation_ids(fiches, exclude_fiche_id=None):
    assigned_ids = set()
    exclude_fiche_id = str(exclude_fiche_id or '')
    for fiche in fiches:
        if not _is_employee_equipment_fiche(fiche):
            continue
        if exclude_fiche_id and str(getattr(fiche, 'id', '')) == exclude_fiche_id:
            continue
        designation = getattr(fiche, 'designation', None)
        equipment_type = _classify_employee_equipment_designation(getattr(designation, 'nom', ''))
        rule = EMPLOYEE_EQUIPMENT_RULES.get(equipment_type) or {}
        if rule.get('unique_asset_assignment') and designation:
            assigned_ids.add(str(designation.id))
    return assigned_ids


def _get_designation_options_by_type(excluded_designation_ids=None):
    excluded_designation_ids = {str(value) for value in (excluded_designation_ids or set())}
    options = {
        equipment_type: []
        for equipment_type, rule in EMPLOYEE_EQUIPMENT_RULES.items()
        if rule.get('show_in_form', True)
    }
    for designation in _get_employee_equipment_designations_queryset():
        if str(designation.id) in excluded_designation_ids:
            continue
        equipment_type = _classify_employee_equipment_designation(designation.nom)
        if equipment_type and equipment_type in options:
            options[equipment_type].append(designation)
    return options


@login_required
def gestion_equipements_employes(request):
    employes = list(_get_active_employes_queryset(request.user))
    magasins = list(_get_scoped_magasins_queryset(request.user))
    active_moto_affectations_by_employee = _get_employee_active_moto_affectations(request.user)
    scoped_fiches = _filter_employee_equipment_fiches_by_scope(
        _get_employee_equipment_fiches_queryset(request.user),
        request.user,
    )
    employee_equipment_fiches = list(
        fiche for fiche in scoped_fiches.order_by('-operation_date', '-created_at')
        if _is_employee_equipment_fiche(fiche)
    )
    assigned_unique_asset_designation_ids = _get_assigned_unique_asset_designation_ids(employee_equipment_fiches)
    designation_options = _get_designation_options_by_type(
        excluded_designation_ids=assigned_unique_asset_designation_ids,
    )
    designation_option_groups = [
        {
            'type': equipment_type,
            'label': EMPLOYEE_EQUIPMENT_RULES[equipment_type]['label'],
            'designations': designation_options.get(equipment_type, []),
        }
        for equipment_type in EMPLOYEE_EQUIPMENT_RULES.keys()
        if designation_options.get(equipment_type)
    ]
    allowed_designation_ids = {
        str(designation.id)
        for designations in designation_options.values()
        for designation in designations
    }
    recent_deliveries = list(
        sorted(
            employee_equipment_fiches,
            key=lambda fiche: (
                getattr(fiche, 'created_at', None) or getattr(fiche, 'operation_date', None) or timezone.now(),
                getattr(fiche, 'operation_date', None) or timezone.now(),
            ),
            reverse=True,
        )[:30]
    )
    for fiche in recent_deliveries:
        fiche.employee_equipment_note_context = _extract_employee_equipment_note_context(getattr(fiche, 'notes', ''))

    statuses_by_employee = _build_employee_equipment_statuses(
        employes,
        employee_equipment_fiches,
        active_moto_affectations_by_employee=active_moto_affectations_by_employee,
    )
    stats = {
        'total_employes': len(employes),
        'equipements': {k: {'label': v['label'], 'count': 0} for k, v in EMPLOYEE_EQUIPMENT_RULES.items()}
    }

    employee_rows = []
    for employe in employes:
        employee_statuses = statuses_by_employee.get(str(employe.id), {})
        row_data = {'employe': employe}
        
        for eq_key in EMPLOYEE_EQUIPMENT_RULES.keys():
            statut = employee_statuses.get(eq_key)
            row_data[eq_key] = statut
            if statut and statut.get('count_in_period', 0) > 0:
                stats['equipements'][eq_key]['count'] += 1
                
        employee_rows.append(row_data)

    employe_user = getattr(request.user, 'employe', None)
    poste_nom_user = _normalize_poste_name(getattr(getattr(employe_user, 'poste', None), 'nom_poste', ''))
    can_edit_dotation = 'directeur' in poste_nom_user or 'caissier' in poste_nom_user or getattr(request.user, 'is_superuser', False)

    if request.method == 'POST':
        if not can_edit_dotation:
            messages.error(request, "Vous n'avez pas l'autorisation d'effectuer cette action sur les dotations.")
            return redirect('planning:gestion_equipements_employes')

        action = (request.POST.get('action') or 'create').strip().lower()
        employe_id = (request.POST.get('employe_id') or '').strip()
        designation_id = (request.POST.get('designation_id') or '').strip()
        magasin_id = (request.POST.get('magasin_id') or '').strip()
        notes = (request.POST.get('notes') or '').strip()
        operation_date_raw = (request.POST.get('operation_date') or '').strip()
        fiche_id = (request.POST.get('fiche_id') or '').strip()

        fiche = None
        if action in {'update', 'delete'}:
            fiche = scoped_fiches.filter(id=fiche_id).select_related('designation', 'employee', 'base').first()
            if not fiche or not _is_employee_equipment_fiche(fiche):
                messages.error(request, "Dotation introuvable ou hors perimetre.")
                return redirect('planning:gestion_equipements_employes')

            fiche_note_context = _extract_employee_equipment_note_context(fiche.notes)
            old_stock = Stock.objects.filter(designation=fiche.designation, base=fiche.base).first()

            if action == 'delete':
                with transaction.atomic():
                    if old_stock:
                        old_stock.current_quantity = Decimal(str(old_stock.current_quantity or 0)) + Decimal(str(fiche.quantity or 0))
                        old_stock.save()
                    fiche.delete()

                messages.success(request, "Dotation supprimee et stock restitue.")
                return redirect('planning:gestion_equipements_employes')

        operation_date = timezone.now()
        if operation_date_raw:
            try:
                dt = datetime.datetime.strptime(operation_date_raw, '%Y-%m-%d')
                operation_date = timezone.make_aware(
                    datetime.datetime.combine(dt.date(), timezone.localtime().time())
                )
            except ValueError:
                pass

        employe = _get_agents_recouvrement_queryset(request.user).filter(id=employe_id).first()
        if not employe:
            messages.error(request, "Employe invalide ou hors perimetre.")
            return redirect('planning:gestion_equipements_employes')

        if designation_id not in allowed_designation_ids:
            messages.error(request, "Designation non autorisee pour la dotation employe.")
            return redirect('planning:gestion_equipements_employes')

        designation = get_object_or_404(Designation, id=designation_id)
        equipment_type = _classify_employee_equipment_designation(designation.nom)
        if not equipment_type:
            messages.error(request, "Cette designation n'est pas classee comme equipement employe.")
            return redirect('planning:gestion_equipements_employes')

        if not _is_employee_equipment_allowed_for_employe(equipment_type, employe):
            messages.error(
                request,
                f"{employe.nom_affichage} n'est pas eligible pour {EMPLOYEE_EQUIPMENT_RULES[equipment_type]['label'].lower()}."
            )
            return redirect('planning:gestion_equipements_employes')

        rule = EMPLOYEE_EQUIPMENT_RULES.get(equipment_type) or {}
        if rule.get('unique_asset_assignment'):
            assigned_elsewhere = next(
                (
                    current_fiche for current_fiche in employee_equipment_fiches
                    if str(getattr(current_fiche, 'designation_id', '')) == designation_id
                    and (action != 'update' or str(getattr(current_fiche, 'id', '')) != str(getattr(fiche, 'id', '')))
                ),
                None,
            )
            if assigned_elsewhere:
                assigned_employee_name = getattr(getattr(assigned_elsewhere, 'employee', None), 'nom_affichage', 'un autre employe')
                messages.error(
                    request,
                    f"{designation.nom} est deja affecte a {assigned_employee_name}."
                )
                return redirect('planning:gestion_equipements_employes')

        statut = statuses_by_employee.get(str(employe.id), {}).get(equipment_type)
        remaining = statut['remaining'] if statut else 0
        if action == 'update' and fiche:
            existing_type = _classify_employee_equipment_designation(getattr(fiche.designation, 'nom', ''))
            if str(getattr(fiche, 'employee_id', '')) == employe_id and existing_type == equipment_type:
                remaining += 1

        if remaining <= 0:
            messages.error(
                request,
                f"{employe.nom_affichage} n'est pas eligible pour {EMPLOYEE_EQUIPMENT_RULES[equipment_type]['label'].lower()}."
            )
            return redirect('planning:gestion_equipements_employes')

        magasin = _get_scoped_magasins_queryset(request.user).filter(id=magasin_id).first()
        if not magasin:
            messages.error(request, "Magasin invalide ou hors perimetre.")
            return redirect('planning:gestion_equipements_employes')

        stock = Stock.objects.filter(designation=designation, base=magasin.base).first()
        stock_disponible = Decimal(str(getattr(stock, 'available_quantity', 0) or 0))
        if stock_disponible < Decimal('1'):
            messages.error(
                request,
                f"Stock insuffisant pour {designation.nom} dans le magasin {magasin.nom_magasin}."
            )
            return redirect('planning:gestion_equipements_employes')

        reference = _build_employee_equipment_reference() if action == 'create' else (fiche.reference or _build_employee_equipment_reference())
        compiled_notes = _build_employee_equipment_note(equipment_type, magasin, employe, notes)

        with transaction.atomic():
            if action == 'update' and fiche:
                if old_stock:
                    old_stock.current_quantity = Decimal(str(old_stock.current_quantity or 0)) + Decimal(str(fiche.quantity or 0))
                    old_stock.save()

                fiche.designation = designation
                fiche.base = magasin.base
                fiche.employee = employe
                fiche.quantity = Decimal('1')
                fiche.operation_type = 'livraison'
                fiche.operation_date = operation_date
                fiche.reference = reference
                fiche.notes = compiled_notes
                fiche.save()
            else:
                FicheStock.objects.create(
                    designation=designation,
                    base=magasin.base,
                    employee=employe,
                    quantity=Decimal('1'),
                    operation_type='livraison',
                    operation_date=operation_date,
                    reference=reference,
                    notes=compiled_notes,
                )
            stock.current_quantity = Decimal(str(stock.current_quantity or 0)) - Decimal('1')
            stock.save()

        if action == 'update':
            messages.success(request, f"Dotation modifiee: {designation.nom} attribuee a {employe.nom_affichage}.")
        else:
            messages.success(
                request,
                f"Dotation enregistree: {designation.nom} livree a {employe.nom_affichage} depuis {magasin.nom_magasin}."
            )
        return redirect('planning:gestion_equipements_employes')

    context = {
        'title': "Dotations d'equipements employes",
        'employes': employes,
        'magasins': magasins,
        'designation_options_by_type': designation_options,
        'designation_option_groups': designation_option_groups,
        'statuses_by_employee': statuses_by_employee,
        'employee_rows': employee_rows,
        'recent_deliveries': recent_deliveries,
        'equipment_rules': EMPLOYEE_EQUIPMENT_RULES,
        'stats': stats,
        'can_edit_dotation': can_edit_dotation,
    }
    return render(request, 'planning/gestion_equipements_employes.html', context)


def _get_organisation_ticket_context(employe):
    organisation = getattr(getattr(employe, 'base', None), 'organisation', None)
    logo_url = ''
    if organisation:
        try:
            logo_field = getattr(organisation, 'logo', None)
            logo_url = logo_field.url if logo_field else ''
        except Exception:
            logo_url = ''
    return {
        'organisation_nom': getattr(organisation, 'nom_organisation', None) or 'HYDRIA',
        'organisation_logo_url': logo_url,
        'organisation_nif': getattr(organisation, 'nif', '') if organisation else '',
        'organisation_stat': getattr(organisation, 'stat', '') if organisation else '',
        'base_telephone': getattr(getattr(employe, 'base', None), 'telephone', '') if employe else '',
    }


def _resolve_display_quantity(quantity, pu, montant):
    quantity_decimal = Decimal(str(quantity or 0))
    if quantity_decimal > 0:
        return quantity_decimal

    pu_decimal = Decimal(str(pu or 0))
    montant_decimal = Decimal(str(montant or 0))
    if pu_decimal > 0 and montant_decimal > 0:
        return montant_decimal / pu_decimal
    return quantity_decimal


def _build_avance_article_from_detail(detail):
    planning = detail.planning
    employe = _get_planning_effective_employe(planning)
    ouvrage = getattr(planning, 'ouvrage', None)
    point_eau = getattr(detail, 'point_eau', None)
    deplacement = getattr(detail, 'deplacement', None)
    organisation_data = _get_organisation_ticket_context(employe)
    point_eau_label = _get_point_eau_label(point_eau)
    designation_nom = detail.designation.nom if detail.designation else 'Sans designation'
    type_avance = getattr(detail.designation, 'type_avance_caissiere', '') or ''
    if deplacement and not type_avance:
        type_avance = 'Avance'

    point_a_nom = getattr(getattr(deplacement, 'point_a', None), 'nom_village', '') if deplacement else ''
    point_b_nom = getattr(getattr(deplacement, 'point_b', None), 'nom_village', '') if deplacement else ''
    trajet = getattr(deplacement, 'trajet', '') if deplacement else ''
    moyen_transport = getattr(deplacement, 'moyen_transport', '') if deplacement else ''
    if deplacement and point_a_nom and point_b_nom:
        designation_pdf = f"{designation_nom} - {trajet or 'Trajet'} {point_a_nom} -> {point_b_nom}"
    else:
        designation_pdf = designation_nom

    pu = detail.pu or detail.montant or 0
    montant = detail.montant or 0
    quantite = _resolve_display_quantity(detail.quantity, pu, montant)

    article = {
        'item_id': str(detail.id),
        'source_type': 'planning_detail',
        'source_label': 'Planning',
        'detail_id': str(detail.id),
        'paiement_id': '',
        'planning_date': _resolve_article_date(getattr(planning, 'date', None)),
        'employe_id': str(employe.id) if employe and getattr(employe, 'id', None) else '',
        'employe_nom': _get_employe_label(employe),
        'employe_initials': _get_employe_initials(employe),
        'ouvrage_id': str(ouvrage.id) if ouvrage and getattr(ouvrage, 'id', None) else '',
        'ouvrage_nom': getattr(ouvrage, 'nom_ouvrage', None) or 'Sans ouvrage',
        'type_designation_id': str(detail.designation.type_designation_id) if detail.designation and detail.designation.type_designation_id else '',
        'designation_nom': designation_nom,
        'designation_description': getattr(detail.designation, 'description', '') or '',
        'designation_unite': getattr(detail.designation, 'unite', '') or '',
        'designation_pdf': designation_pdf,
        'type_avance': type_avance,
        'quantite': float(quantite),
        'pu': float(pu),
        'montant': float(montant),
        'point_eau_label': point_eau_label,
        'point_eau_idxls': getattr(point_eau, 'idxls', '') or '',
        'nom_abonne': getattr(point_eau, 'nomabonne', '') or '',
        'trajet': trajet,
        'point_a_nom': point_a_nom,
        'point_b_nom': point_b_nom,
        'moyen_transport': moyen_transport,
        'base_nom': getattr(getattr(employe, 'base', None), 'nom_base', '') if employe else '',
        'base_telephone': getattr(getattr(employe, 'base', None), 'telephone', '') if employe else '',
        'ticket_numero': getattr(detail, 'numero_bon_avance', '') or '',
        'debug_db': 'PlanningDetail (Avance / Recette / Deplacement)',
        'debug_livraison': 'Oui' if getattr(detail, 'livraison', False) else 'Non',
        'debug_retour': 'Oui' if getattr(detail, 'retour', False) else 'Non',
        'debug_paye': 'N/A',
        'debug_est_valide': 'Oui' if planning and getattr(planning, 'estvalide', False) else 'Non',
    }
    article.update(organisation_data)
    return article


def _frais_mvola_from_paliers(paliers, montant):
    if montant is None:
        return None
    montant_decimal = Decimal(str(montant))
    for palier in paliers:
        if palier.montant_min <= montant_decimal <= palier.montant_max:
            return palier.frais
    return None


def _build_avance_article_from_paiement(paiement, history=None, frais_paliers=None):
    planning = paiement.planning
    employe = _get_planning_effective_employe(planning)
    ouvrage = getattr(planning, 'ouvrage', None) or getattr(getattr(paiement, 'point_eau', None), 'ouvrage', None)
    point_eau = getattr(paiement, 'point_eau', None)
    organisation_data = _get_organisation_ticket_context(employe)
    point_eau_label = _get_point_eau_label(point_eau)
    designation_pdf = 'Paiement forfaitaire'
    if point_eau_label:
        designation_pdf = f"{designation_pdf} - {point_eau_label}"

    montant = paiement.montant or 0
    if frais_paliers is not None:
        frais_mvola = _frais_mvola_from_paliers(frais_paliers, montant)
    else:
        frais_mvola = FraisTransfertMvola.calculer_frais(montant)
    pu = paiement.prix_unitaire or 0
    quantite = _resolve_display_quantity(paiement.quantite, pu, montant)
    tranches_header = _build_forfaitaire_tranches_header(paiement, history=history)
    prochaine_tranche_date, prochaine_tranche_montant = _build_forfaitaire_prochaine_echeance(paiement, history=history)
    pu_decimal = Decimal(str(pu or 0))
    montant_decimal = Decimal(str(montant or 0))
    if pu_decimal <= 0 and quantite > 0 and montant_decimal > 0:
        pu_decimal = montant_decimal / Decimal(str(quantite))

    article = {
        'item_id': str(paiement.id),
        'source_type': 'paiement_forfaitaire',
        'source_label': 'Forfaitaire',
        'detail_id': '',
        'paiement_id': str(paiement.id),
        'planning_date': _resolve_article_date(getattr(planning, 'date', None) or paiement.date_facture),
        'employe_id': str(employe.id) if employe and getattr(employe, 'id', None) else '',
        'employe_nom': _get_employe_label(employe),
        'employe_initials': _get_employe_initials(employe),
        'ouvrage_id': str(ouvrage.id) if ouvrage and getattr(ouvrage, 'id', None) else '',
        'ouvrage_nom': getattr(ouvrage, 'nom_ouvrage', None) or 'Sans ouvrage',
        'type_designation_id': '',
        'designation_nom': 'Paiement forfaitaire',
        'designation_description': point_eau_label or 'Facture forfaitaire',
        'designation_unite': 'tranche(s)',
        'designation_pdf': designation_pdf,
        'type_avance': 'Recette',
        'quantite': float(quantite),
        'pu': float(pu_decimal),
        'montant': float(montant_decimal),
        'frais_mvola': float(frais_mvola) if frais_mvola is not None else '',
        'forfaitaire_tranches_header': tranches_header,
        'forfaitaire_prochaine_date': prochaine_tranche_date,
        'forfaitaire_prochaine_montant': float(prochaine_tranche_montant) if prochaine_tranche_montant is not None else '',
        'point_eau_label': point_eau_label,
        'point_eau_idxls': getattr(point_eau, 'idxls', '') or '',
        'nom_abonne': getattr(point_eau, 'nomabonne', '') or '',
        'base_nom': getattr(getattr(employe, 'base', None), 'nom_base', '') if employe else '',
        'base_telephone': getattr(getattr(employe, 'base', None), 'telephone', '') if employe else '',
        'compte_nom': '',
        'ticket_numero': f"PAY-{str(paiement.id).split('-')[0].upper()}",
        'debug_db': 'PaiementForfaitaire',
        'debug_livraison': 'N/A',
        'debug_retour': 'N/A',
        'debug_paye': 'Oui' if getattr(paiement, 'paye', False) else 'Non',
        'debug_est_valide': 'Oui' if planning and getattr(planning, 'estvalide', False) else 'Non',
    }
    article.update(organisation_data)
    return article


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
        return queryset.filter(
            Q(employe__base__organisation_id=organisation_id) |
            Q(planning_employees__employee__base__organisation_id=organisation_id)
        ).distinct()

    base_id = getattr(employe, 'base_id', None)
    if not base_id:
        return queryset.none()
    return queryset.filter(
        Q(employe__base_id=base_id) |
        Q(planning_employees__employee__base_id=base_id)
    ).distinct()


def _resolve_base_from_magasin_text(magasin_text):
    """Resolve a Base from a free-text magasin/base label."""
    if not magasin_text:
        return None

    label = str(magasin_text).strip()
    if not label:
        return None

    try:
        parsed_uuid = uuid.UUID(label)
        magasin = Magasin.objects.select_related('base').filter(id=parsed_uuid).first()
        if magasin and magasin.base:
            return magasin.base
        base = Base.objects.filter(id=parsed_uuid).first()
        if base:
            return base
    except (ValueError, TypeError, AttributeError):
        pass

    # 1) Exact base name
    base = Base.objects.filter(nom_base__iexact=label).first()
    if base:
        return base

    # 2) Exact magasin name -> base
    magasin = Magasin.objects.select_related('base').filter(nom_magasin__iexact=label).first()
    if magasin and magasin.base:
        return magasin.base

    # 3) Contains patterns
    base = Base.objects.filter(nom_base__icontains=label).first()
    if base:
        return base
    magasin = Magasin.objects.select_related('base').filter(nom_magasin__icontains=label).first()
    if magasin and magasin.base:
        return magasin.base

    return None


def _match_magasin_label(magasin_text, selected_magasin):
    """
    Compare un texte libre de magasin avec un magasin sélectionné.
    Accepte un UUID de magasin et le nom exact du magasin.
    """
    if not selected_magasin or not magasin_text:
        return False

    label = str(magasin_text).strip()
    if not label:
        return False

    try:
        return str(uuid.UUID(label)) == str(selected_magasin.id)
    except (ValueError, TypeError, AttributeError):
        pass

    return label.lower() == (selected_magasin.nom_magasin or '').strip().lower()


def _resolve_magasin_from_magasin_text(magasin_text):
    """Resolve un magasin depuis un texte libre magasin/base label."""
    if not magasin_text:
        return None

    label = str(magasin_text).strip()
    if not label:
        return None

    try:
        parsed_uuid = uuid.UUID(label)
        magasin = Magasin.objects.select_related('base').filter(id=parsed_uuid).first()
        if magasin:
            return magasin
    except (ValueError, TypeError, AttributeError):
        pass

    magasin = Magasin.objects.select_related('base').filter(nom_magasin__iexact=label).first()
    if magasin:
        return magasin

    magasin = Magasin.objects.select_related('base').filter(nom_magasin__icontains=label).first()
    if magasin:
        return magasin

    return None


def _get_magasin_display_label(magasin_text):
    """Retourne un libelle lisible du magasin a partir du texte stocke."""
    magasin_obj = _resolve_magasin_from_magasin_text(magasin_text)
    if magasin_obj:
        label = magasin_obj.nom_magasin or ''
        base_nom = getattr(getattr(magasin_obj, 'base', None), 'nom_base', '') or ''
        if label and base_nom:
            return f"{label} ({base_nom})"
        return label or str(magasin_text or '').strip() or '-'
    return str(magasin_text or '').strip() or '-'


def _compute_stock_avant_pour_bon_livraison(bon):
    """
    Calcule le stock actuel pour une désignation en ventilant par magasin,
    avec la même logique de filtrage que les vues d'inventaire.
    """
    if not bon or not bon.designation_id or not bon.magasin:
        return Decimal('0')

    try:
        magasin_obj = _resolve_magasin_from_magasin_text(bon.magasin)
        base = magasin_obj.base if magasin_obj else _resolve_base_from_magasin_text(bon.magasin)

        if not base:
            return Decimal('0')

        from .models import BonLivraison
        from apps.inventory.models import Purchase, Transfert

        fiches = FicheStock.objects.filter(
            designation_id=bon.designation_id,
            base=base
        ).order_by('operation_date')

        if not magasin_obj:
            stock_cumule = Decimal('0')
            for fiche in fiches:
                qty = Decimal(str(fiche.quantity)) if fiche.quantity else Decimal('0')
                if fiche.operation_type == 'inventaire':
                    stock_cumule = qty
                elif fiche.operation_type in ['achat', 'transfert_entree', 'entree', 'retour_terrain']:
                    stock_cumule += qty
                elif fiche.operation_type in ['livraison', 'transfert_sortie', 'sortie']:
                    stock_cumule -= qty
                elif fiche.operation_type == 'ajustement':
                    stock_cumule += qty
            return stock_cumule

        purchase_ids = {
            str(purchase_id) for purchase_id in Purchase.objects.filter(
                magasin_id=magasin_obj.id
            ).values_list('id', flat=True)
        }
        transfert_sortie_ids = {
            str(transfert_id) for transfert_id in Transfert.objects.filter(
                magasin_origine_id=magasin_obj.id
            ).values_list('id', flat=True)
        }
        transfert_entree_ids = {
            str(transfert_id) for transfert_id in Transfert.objects.filter(
                magasin_destination_id=magasin_obj.id
            ).values_list('id', flat=True)
        }

        bon_ids = set()
        bon_numbers = set()
        for bon_item in BonLivraison.objects.filter(
            designation_id=bon.designation_id,
            planning__employe__base_id=magasin_obj.base_id
        ).only('id', 'numero_bon', 'magasin'):
            if _match_magasin_label(bon_item.magasin, magasin_obj):
                bon_ids.add(str(bon_item.id))
                if bon_item.numero_bon:
                    bon_numbers.add(bon_item.numero_bon.strip())

        bon_id_markers = {f"BonLivraison ID: {bon_id}" for bon_id in bon_ids}
        magasin_id_marker = f"Magasin ID: {magasin_obj.id}"
        magasin_name_marker = f"Magasin: {magasin_obj.nom_magasin}"

        stock_cumule = Decimal('0')
        for fiche in fiches:
            operation = fiche.operation_type
            notes_value = fiche.notes or ''
            reference_value = (fiche.reference or '').strip()

            include = False
            if operation == 'achat':
                include = bool(fiche.purchase_id and str(fiche.purchase_id) in purchase_ids)
            elif operation == 'transfert_sortie':
                include = bool(fiche.transfert_id and str(fiche.transfert_id) in transfert_sortie_ids)
            elif operation == 'transfert_entree':
                include = bool(fiche.transfert_id and str(fiche.transfert_id) in transfert_entree_ids)
            elif operation == 'livraison':
                include = any(marker in notes_value for marker in bon_id_markers)
                if not include and reference_value and bon_numbers:
                    include = reference_value in bon_numbers
                if not include and bon_numbers:
                    include = any(bon_num in notes_value for bon_num in bon_numbers)
            elif operation == 'retour_terrain':
                include = any(marker in notes_value for marker in bon_id_markers)
                if not include and reference_value and bon_numbers:
                    include = reference_value in bon_numbers
                if not include and bon_numbers:
                    include = any(bon_num in notes_value for bon_num in bon_numbers)
                if not include:
                    include = magasin_id_marker in notes_value or magasin_name_marker in notes_value
            elif operation in ['inventaire', 'entree', 'sortie', 'ajustement']:
                include = magasin_id_marker in notes_value or magasin_name_marker in notes_value

            if not include:
                continue

            qty = Decimal(str(fiche.quantity)) if fiche.quantity else Decimal('0')
            if operation == 'inventaire':
                stock_cumule = qty
            elif operation in ['achat', 'transfert_entree', 'entree', 'retour_terrain']:
                stock_cumule += qty
            elif operation in ['livraison', 'transfert_sortie', 'sortie']:
                stock_cumule -= qty
            elif operation == 'ajustement':
                stock_cumule += qty

        return stock_cumule
    except Exception:
        return Decimal('0')


@login_required
def gestion_livraisons(request):
    """Vue principale pour la gestion des livraisons"""
    employe_connecte_id = ''
    employe_connecte = getattr(request.user, 'employe', None)
    if employe_connecte and getattr(employe_connecte, 'id', None):
        employe_connecte_id = str(employe_connecte.id)

    # Récupérer tous les bons de livraison non utilisés (utilise=False)
    # depuis la table BonLivraison (table avec ~2700+ lignes)
    from .models import BonLivraison

    allowed_planning_ids = _filter_plannings_by_scope(Planning.objects.all(), request.user).values_list('id', flat=True)

    bons_livraisons = BonLivraison.objects.filter(
        _get_pending_planning_date_filter(),
        utilise=False,  # Non encore livrés
        planning__estvalide=True,  # Planning validé
        planning_id__in=allowed_planning_ids
    ).filter(
        Q(designation__type_avance_caissiere='bon_livraison') |
        Q(designation__type_avance_caissiere__iexact='Bon de livraison')
    ).select_related(
        'planning',
        'planning__employe',
        'planning__ouvrage',
        'designation',
        'designation__type_designation',
        'point_eau',
        'equipement'
    ).order_by('planning__date', 'designation__nom')

    # Récupérer les plannings validés qui ont des articles à  livrer
    planning_ids = bons_livraisons.values_list('planning_id', flat=True).distinct()
    plannings_valides = _filter_plannings_by_scope(
        Planning.objects.filter(id__in=planning_ids, estvalide=True),
        request.user
    )

    # Récupérer la liste unique des employés ayant des livraisons en attente
    employe_map = {}
    for bon in bons_livraisons:
        effective_employe = _get_planning_effective_employe(getattr(bon, 'planning', None))
        if effective_employe and getattr(effective_employe, 'id', None):
            employe_map[str(effective_employe.id)] = effective_employe

    if employe_connecte and getattr(employe_connecte, 'id', None):
        employe_map.setdefault(str(employe_connecte.id), employe_connecte)

    employes = sorted(
        employe_map.values(),
        key=lambda employe: (
            _normalize_sort_text(
                getattr(employe, 'surnom', None)
                or getattr(employe, 'nom', None)
                or getattr(employe, 'prenom', None)
                or getattr(employe, 'nom_employe', None)
                or ''
            ),
            str(getattr(employe, 'id', ''))
        )
    )

    return render(request, 'planning/gestion_livraisons.html', {
        'plannings_valides': plannings_valides,
        'details_livraisons': bons_livraisons,  # Utiliser BonLivraison au lieu de PlanningDetail
        'employes': employes,
        'employe_connecte_id': employe_connecte_id,
        'current_month': timezone.localdate().strftime('%Y-%m'),
        'title': 'Gestion des Livraisons'
    })

@login_required
def maintenance_livraisons(request):
    """Page temporaire pour nettoyer les bons de livraison (marquer livré/retour)."""
    # Seuls les administrateurs ou responsables peuvent accéder à cette maintenance
    if not request.user.is_superuser and not _get_planning_scope(request.user) in ['all', 'organisation']:
        return render(request, "403.html", status=403)

    from .models import BonLivraison
    
    # Action POST pour le nettoyage
    if request.method == "POST":
        action = request.POST.get('action')
        selected_ids = request.POST.getlist('selected_ids')
        
        if selected_ids:
            # Récupérer les bons concernés
            bons = BonLivraison.objects.filter(id__in=selected_ids)
            now = timezone.now()
            count = 0
            
            # Application de l'action sélectionnée
            if action == 'marquer_livre':
                count = bons.update(utilise=True, date_utilisation=now)
            elif action == 'marquer_retour':
                count = bons.update(retour=True, date_retour=now)
                bons.filter(utilise=False).update(
                    utilise=True,
                    date_utilisation=now,
                )
            elif action == 'marquer_les_deux':
                count = bons.update(utilise=True, date_utilisation=now, retour=True, date_retour=now)
            elif action == 'supprimer':
                count = bons.count()
                bons.delete()
                messages.error(request, f"{count} bon(s) supprimé(s) définitivement.")
                return redirect('planning:maintenance_livraisons')
                
            messages.success(request, f"{count} bon(s) mis à jour avec succès.")
        else:
            messages.warning(request, "Aucun bon n'a été sélectionné.")
            
        return redirect('planning:maintenance_livraisons')

    # Filtrage par défaut : TOUS les bons (pour le nettoyage global)
    allowed_planning_ids = _filter_plannings_by_scope(Planning.objects.all(), request.user).values_list('id', flat=True)
    
    # Récupération des paramètres de filtrage
    q = request.GET.get('q', '')
    ouvrage_id = request.GET.get('ouvrage_id')
    designation_id = request.GET.get('designation_id')
    statut = request.GET.get('statut')
    selected_mois = request.GET.get('mois', '').strip()
    parsed_mois = _parse_month_filter(selected_mois)
    
    bons_queryset = BonLivraison.objects.filter(
        planning_id__in=allowed_planning_ids,
        planning__estvalide=True
    )
    
    # Filtre de recherche globale
    if q:
        bons_queryset = bons_queryset.filter(
            Q(numero_bon__icontains=q) |
            Q(planning__employe__nom__icontains=q) |
            Q(planning__employe__prenom__icontains=q) |
            Q(designation__nom__icontains=q)
        )
    
    # Filtre par Ouvrage
    if ouvrage_id:
        bons_queryset = bons_queryset.filter(planning__ouvrage_id=ouvrage_id)
        
    # Filtre par Désignation
    if designation_id:
        bons_queryset = bons_queryset.filter(designation_id=designation_id)

    # Filtre par Mois
    if parsed_mois:
        bons_queryset = bons_queryset.filter(
            planning__date__year=parsed_mois.year,
            planning__date__month=parsed_mois.month,
        )
        
    # Filtre par Statut
    if statut == 'a_livrer':
        bons_queryset = bons_queryset.filter(utilise=False)
    elif statut == 'a_retourner':
        bons_queryset = bons_queryset.filter(retour=False)
    elif statut == 'en_attente':
        bons_queryset = bons_queryset.filter(Q(utilise=False) | Q(retour=False))
    elif statut == 'termine':
        bons_queryset = bons_queryset.filter(utilise=True, retour=True)
        
    # Récupérer les options pour les dropdowns (uniquement celles présentes dans les résultats possibles)
    from apps.organization.models import Ouvrage
    ouvrages = Ouvrage.objects.filter(id__in=BonLivraison.objects.filter(planning_id__in=allowed_planning_ids).values_list('planning__ouvrage_id', flat=True).distinct()).order_by('nom_ouvrage')
    designations = Designation.objects.filter(id__in=BonLivraison.objects.filter(planning_id__in=allowed_planning_ids).values_list('designation_id', flat=True).distinct()).order_by('nom')
        
    # Statistiques (sur le queryset filtré complet)
    total_count = bons_queryset.count()
    livre_count = bons_queryset.filter(utilise=True).count()
    retour_count = bons_queryset.filter(retour=True).count()
    
    livre_pct = (livre_count / total_count * 100) if total_count > 0 else 0
    retour_pct = (retour_count / total_count * 100) if total_count > 0 else 0
        
    bons_queryset = bons_queryset.select_related(
        'planning', 'planning__employe', 'planning__ouvrage', 'designation', 'point_eau'
    ).order_by('-planning__date')[:500] 

    context = {
        'bons': bons_queryset,
        'ouvrages_liste': ouvrages,
        'designations_liste': designations,
        'title': 'Maintenance des Livraisons (Nettoyage)',
        'search_query': q,
        'selected_ouvrage': ouvrage_id,
        'selected_designation': designation_id,
        'selected_mois': selected_mois,
        'selected_statut': statut,
        'stats': {
            'total': total_count,
            'livre': livre_count,
            'retour': retour_count,
            'livre_pct': round(livre_pct, 1),
            'retour_pct': round(retour_pct, 1),
        }
    }
    return render(request, 'planning/maintenance_livraisons.html', context)


@login_required
def gestion_avances(request):
    """Vue principale pour la gestion des avances et recettes."""
    allowed_planning_ids = list(
        _filter_plannings_by_scope(Planning.objects.all(), request.user).values_list('id', flat=True)
    )
    details_avances = PlanningDetail.objects.filter(
        livraison=False,
        planning_id__in=allowed_planning_ids,
    ).filter(
        (Q(planning__estvalide=True) & _avance_or_recette_designation_q()) |
        Q(deplacement__isnull=False)
    ).exclude(designation__nom__icontains='Paiement forfaitaire').select_related(
        'planning',
        'planning__employe',
        'planning__ouvrage',
        'designation',
        'designation__type_designation',
        'compte',
        'point_eau',
        'deplacement__point_a',
        'deplacement__point_b',
    ).prefetch_related(
        'planning__planning_employees__employee'
    ).order_by('planning__date', 'designation__nom')

    paiements_forfaitaires = PaiementForfaitaire.objects.filter(
        planning_id__in=allowed_planning_ids,
        planning__isnull=False,
        planning__estvalide=True,
        paye=False,
        traite_en_avance=False,
    ).filter(
        Q(numeroDiameX__isnull=True) | Q(numeroDiameX='')
    ).select_related(
        'planning',
        'planning__employe',
        'planning__ouvrage',
        'point_eau',
        'point_eau__ouvrage',
    ).prefetch_related(
        'planning__planning_employees__employee'
    ).order_by('planning__date', 'point_eau__idxls')

    articles_avances = []
    articles_avances_futur = []
    employe_options_map = {}
    ouvrage_options_map = {}
    type_designation_map = {}

    def register_article(article):
        employe_id = article.get('employe_id')
        ouvrage_id = article.get('ouvrage_id')
        type_designation_id = article.get('type_designation_id')

        if employe_id:
            employe_options_map.setdefault(employe_id, {
                'id': employe_id,
                'nom': article.get('employe_nom') or '-',
            })
        if ouvrage_id:
            ouvrage_options_map.setdefault(ouvrage_id, {
                'id': ouvrage_id,
                'nom': article.get('ouvrage_nom') or '-',
            })
        if type_designation_id:
            type_designation_map.setdefault(type_designation_id, {
                'id': type_designation_id,
                'nom': getattr(getattr(article.get('_designation_obj'), 'type_designation', None), 'nom_type_designation', '') or article.get('type_avance') or 'Type',
            })

    # Contrôle RBF : une avance d'indemnité qui ne correspond pas à un paiement pointé (ou qui fait doublon) n'est
    # pas proposée à la caissière. En cas d'erreur du contrôle on n'écarte rien (journalisé).
    try:
        from apps.core import rbf_avance
        rbf_refusees = rbf_avance.ids_refuses()
    except Exception:
        logging.getLogger(__name__).exception("Contrôle des avances RBF indisponible")
        rbf_refusees = set()

    for detail in details_avances:
        if detail.id in rbf_refusees:
            continue
        article = _build_avance_article_from_detail(detail)
        article['_designation_obj'] = getattr(detail, 'designation', None)
        register_article(article)
        if _is_pending_planning_detail_visible(
            article.get('planning_date'),
            livraison=bool(getattr(detail, 'livraison', False)),
            retour=bool(getattr(detail, 'retour', False)),
        ):
            articles_avances.append(article)
        else:
            articles_avances_futur.append(article)

    for paiement in paiements_forfaitaires:
        article = _build_avance_article_from_paiement(paiement)
        register_article(article)
        if _is_pending_planning_detail_visible(article.get('planning_date')):
            articles_avances.append(article)
        else:
            articles_avances_futur.append(article)

    for article in articles_avances + articles_avances_futur:
        article.pop('_designation_obj', None)

    employes_meta = Employe.objects.filter(
        id__in=employe_options_map.keys()
    ).select_related('base', 'poste')
    for employe in employes_meta:
        option = employe_options_map.get(str(employe.id))
        if option is None:
            option = employe_options_map.get(employe.id)
        if option is not None:
            option['base_name'] = employe.base.nom_base if employe.base else 'Sans base'
            option['poste_name'] = employe.poste.nom_poste if employe.poste else 'Sans poste'

    sort_key = lambda article: (
        article.get('planning_date') or datetime.date.max,
        _normalize_sort_text(article.get('employe_nom')),
        _normalize_sort_text(article.get('ouvrage_nom')),
        _normalize_sort_text(article.get('designation_nom')),
    )
    articles_avances.sort(key=sort_key)
    articles_avances_futur.sort(key=sort_key)

    type_designations = sorted(
        type_designation_map.values(),
        key=lambda item: _normalize_sort_text(item.get('nom')),
    )
    employe_options = sorted(
        employe_options_map.values(),
        key=lambda item: _normalize_sort_text(item.get('nom')),
    )
    ouvrage_options = sorted(
        ouvrage_options_map.values(),
        key=lambda item: _normalize_sort_text(item.get('nom')),
    )

    return render(request, 'planning/gestion_avances.html', {
        'details_avances': details_avances,
        'paiements_forfaitaires': paiements_forfaitaires,
        'articles_avances': articles_avances,
        'articles_avances_futur': articles_avances_futur,
        'total_pending_count': len(articles_avances),
        'type_designations': type_designations,
        'employe_options': employe_options,
        'ouvrage_options': ouvrage_options,
        'employes': [],
        'bases': [],
        'is_directeur': request.user.is_superuser,
        'current_month': timezone.localdate().strftime('%Y-%m'),
        'title': 'Gestion des Avances, Recettes & Forfaitaires',
    })


@login_required
def gestion_recettes_forfaitaires(request):
    """Vue dediee a la gestion des recettes forfaitaires."""
    # Sous-requete (pas de liste d'IDs en memoire : evite un IN (...) geant)
    allowed_planning_ids = _filter_plannings_by_scope(Planning.objects.all(), request.user).values('id')

    paiements_forfaitaires = list(PaiementForfaitaire.objects.filter(
        planning_id__in=allowed_planning_ids,
        planning__isnull=False,
        planning__estvalide=True,
        paye=False,
        traite_en_avance=False,
    ).filter(
        Q(numeroDiameX__isnull=True) | Q(numeroDiameX='')
    ).select_related(
        'planning',
        'planning__employe',
        'planning__employe__base',
        'planning__employe__base__organisation',
        'planning__ouvrage',
        'point_eau',
        'point_eau__ouvrage',
    ).defer(
        # Colonnes tres lourdes (photos ~54 Ko/ligne) jamais utilisees sur cette page
        'point_eau__photos',
        'point_eau__problematique_commentaire',
    ).prefetch_related(
        'planning__planning_employees__employee__base__organisation'
    ).order_by('planning__date', 'point_eau__idxls'))

    # Donnees partagees chargees une seule fois (au lieu de ~5 requetes par ligne)
    history = _load_forfaitaire_history({p.point_eau_id for p in paiements_forfaitaires})
    frais_paliers = list(FraisTransfertMvola.objects.filter(actif=True).order_by('montant_min'))

    articles_avances = []
    articles_avances_futur = []
    employe_options_map = {}
    ouvrage_options_map = {}

    def register_article(article):
        employe_id = article.get('employe_id')
        ouvrage_id = article.get('ouvrage_id')

        if employe_id:
            employe_options_map.setdefault(employe_id, {
                'id': employe_id,
                'nom': article.get('employe_nom') or '-',
            })
        if ouvrage_id:
            ouvrage_options_map.setdefault(ouvrage_id, {
                'id': ouvrage_id,
                'nom': article.get('ouvrage_nom') or '-',
            })

    for paiement in paiements_forfaitaires:
        article = _build_avance_article_from_paiement(paiement, history=history, frais_paliers=frais_paliers)
        register_article(article)
        if _is_pending_planning_detail_visible(article.get('planning_date')):
            articles_avances.append(article)
        else:
            articles_avances_futur.append(article)

    sort_key = lambda article: (
        article.get('planning_date') or datetime.date.max,
        _normalize_sort_text(article.get('employe_nom')),
        _normalize_sort_text(article.get('ouvrage_nom')),
        _normalize_sort_text(article.get('designation_nom')),
    )
    articles_avances.sort(key=sort_key)
    articles_avances_futur.sort(key=sort_key)

    employe_options = sorted(
        employe_options_map.values(),
        key=lambda item: _normalize_sort_text(item.get('nom')),
    )
    ouvrage_options = sorted(
        ouvrage_options_map.values(),
        key=lambda item: _normalize_sort_text(item.get('nom')),
    )
    bases_options = list(
        Base.objects.filter(
            employes__plannings__id__in=allowed_planning_ids,
            employes__plannings__paiements_forfaitaires__isnull=False,
        )
        .select_related('organisation')
        .distinct()
        .order_by('nom_base')
    )

    return render(request, 'planning/gestion_avances.html', {
        'details_avances': [],
        'paiements_forfaitaires': paiements_forfaitaires,
        'articles_avances': articles_avances,
        'articles_avances_futur': articles_avances_futur,
        'total_pending_count': len(articles_avances),
        'type_designations': [],
        'employe_options': employe_options,
        'ouvrage_options': ouvrage_options,
        'bases_options': bases_options,
        'employes': [],
        'bases': [],
        'is_directeur': request.user.is_superuser,
        'current_month': timezone.localdate().strftime('%Y-%m'),
        'title': 'Gestion des Recettes Forfaitaires',
        'forfaitaire_only': True,
        'employes_assignables': list(_get_agents_recouvrement_queryset(request.user)),
    })


@login_required
@require_http_methods(["POST"])
def api_changer_employe_recette_forfaitaire(request):
    """Change l'employe d'une recette forfaitaire (porte par son planning)."""
    try:
        if not request.user.is_superuser and _get_planning_scope(request.user) not in ['all', 'organisation']:
            return JsonResponse({'success': False, 'error': 'Acces refuse'}, status=403)

        data = json.loads(request.body or '{}')
        paiement_id = (data.get('paiement_id') or '').strip()
        employe_id = (data.get('employe_id') or '').strip()
        if not paiement_id or not employe_id:
            return JsonResponse({'success': False, 'error': 'paiement_id et employe_id sont obligatoires'}, status=400)

        allowed_planning_ids = list(
            _filter_plannings_by_scope(Planning.objects.all(), request.user).values_list('id', flat=True)
        )
        paiement = PaiementForfaitaire.objects.select_related('planning').filter(
            id=paiement_id,
            planning_id__in=allowed_planning_ids,
        ).first()
        if not paiement or not paiement.planning:
            return JsonResponse({'success': False, 'error': 'Recette forfaitaire introuvable'}, status=404)
        if paiement.paye or (paiement.numeroDiameX or '').strip():
            return JsonResponse({'success': False, 'error': 'Impossible de modifier une recette deja encaissee'}, status=400)

        employe = _get_agents_recouvrement_queryset(request.user).filter(id=employe_id).first()
        if not employe:
            return JsonResponse({'success': False, 'error': 'Employe introuvable ou non autorise'}, status=404)

        planning = paiement.planning
        planning.employe = employe
        planning.save(update_fields=['employe'])
        return JsonResponse({
            'success': True,
            'employe_id': str(employe.id),
            'employe_nom': _get_employe_label(employe),
            'employe_initials': _get_employe_initials(employe),
            # Toutes les recettes du meme planning changent d'employe avec lui
            'paiement_ids': [
                str(pid) for pid in
                PaiementForfaitaire.objects.filter(planning=planning).values_list('id', flat=True)
            ],
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def imprimer_recap_factures_forfaitaires(request):
    """Imprime un recapitulatif des factures forfaitaires par mois et base."""
    selected_month = (request.GET.get('mois') or '').strip()
    base_id = (request.GET.get('base_id') or '').strip()

    parsed_month = _parse_month_filter(selected_month)
    if not parsed_month:
        return HttpResponse('Le parametre mois est obligatoire.', status=400)
    if not base_id:
        return HttpResponse('Le parametre base_id est obligatoire.', status=400)

    allowed_planning_ids = list(
        _filter_plannings_by_scope(Planning.objects.all(), request.user).values_list('id', flat=True)
    )

    paiements_qs = (
        PaiementForfaitaire.objects.filter(
            planning_id__in=allowed_planning_ids,
            planning__isnull=False,
            planning__estvalide=True,
            planning__date__year=parsed_month.year,
            planning__date__month=parsed_month.month,
            paye=False,
        )
        .filter(Q(numeroDiameX__isnull=True) | Q(numeroDiameX=''))
        .select_related(
            'planning',
            'planning__employe',
            'planning__employe__base',
            'planning__employe__base__organisation',
            'planning__ouvrage',
            'point_eau',
            'point_eau__ouvrage',
        )
        .order_by(
            'planning__employe__base__nom_base',
            'planning__date',
            'point_eau__idxls',
            'point_eau__code_point_eau',
        )
    )

    paiements_qs = paiements_qs.filter(planning__employe__base_id=base_id)
    selected_base = Base.objects.select_related('organisation').filter(id=base_id).first()

    paiements = list(paiements_qs)

    total_montant = Decimal('0')
    total_livres = 0
    total_non_livres = 0
    rows = []
    organisation = None

    for paiement in paiements:
        planning = getattr(paiement, 'planning', None)
        employe = getattr(planning, 'employe', None)
        base = getattr(employe, 'base', None)
        point_eau = getattr(paiement, 'point_eau', None)
        ouvrage = getattr(planning, 'ouvrage', None) or getattr(point_eau, 'ouvrage', None)

        if organisation is None and getattr(base, 'organisation', None):
            organisation = base.organisation

        montant = Decimal(str(getattr(paiement, 'montant', 0) or 0))
        total_montant += montant

        if paiement.traite_en_avance:
            total_livres += 1
            statut_livraison = 'Livre'
        else:
            total_non_livres += 1
            statut_livraison = 'Non livre'

        rows.append({
            'date_planning': getattr(planning, 'date', None),
            'date_facture': paiement.date_facture,
            'base_nom': getattr(base, 'nom_base', '') or '-',
            'employe_nom': getattr(employe, 'nom_affichage', None) or '-',
            'point_eau_label': (
                getattr(point_eau, 'idxls', None)
                or getattr(point_eau, 'code_point_eau', None)
                or getattr(point_eau, 'nomabonne', None)
                or 'Sans point d eau'
            ),
            'nom_abonne': getattr(point_eau, 'nomabonne', None) or '',
            'ouvrage_nom': getattr(ouvrage, 'nom_ouvrage', None) or '-',
            'quantite': paiement.quantite,
            'prix_unitaire': paiement.prix_unitaire,
            'montant': montant,
            'statut_livraison': statut_livraison,
            'traite_en_avance': paiement.traite_en_avance,
        })

    # Trier par (employe_nom, ouvrage_nom, date_planning) pour garantir la contiguïté
    # des groupes (évite les répétitions d'en-têtes d'employé/ouvrage dans le récap imprimé)
    import unicodedata

    def _sort_key(r):
        def _norm(s):
            s = (s or '').upper()
            return unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
        return (_norm(r.get('employe_nom', '')), _norm(r.get('ouvrage_nom', '')), r.get('date_planning') or r.get('date_facture') or '')

    rows.sort(key=_sort_key)

    grouped_rows = []
    print_rows = []
    current_employe = None
    current_ouvrage = None
    employe_group = None
    ouvrage_group = None

    for row in rows:
        employe_nom = row['employe_nom']
        ouvrage_nom = row['ouvrage_nom']

        if employe_nom != current_employe:
            employe_group = {
                'employe_nom': employe_nom,
                'ouvrages': [],
            }
            grouped_rows.append(employe_group)
            print_rows.append({
                'type': 'employe',
                'label': employe_nom,
            })
            current_employe = employe_nom
            current_ouvrage = None

        if ouvrage_nom != current_ouvrage:
            ouvrage_group = {
                'ouvrage_nom': ouvrage_nom,
                'rows': [],
            }
            employe_group['ouvrages'].append(ouvrage_group)
            print_rows.append({
                'type': 'ouvrage',
                'label': ouvrage_nom,
            })
            current_ouvrage = ouvrage_nom

        ouvrage_group['rows'].append(row)
        print_rows.append({
            'type': 'item',
            'row': row,
        })

    if organisation is None:
        user_base = getattr(getattr(request.user, 'employe', None), 'base', None)
        organisation = getattr(user_base, 'organisation', None)

    context = {
        'rows': rows,
        'grouped_rows': grouped_rows,
        'print_rows': print_rows,
        'selected_month': parsed_month,
        'selected_month_label': parsed_month.strftime('%m/%Y'),
        'selected_base': selected_base,
        'organisation': organisation,
        'total_lignes': len(rows),
        'total_montant': total_montant,
        'total_livres': total_livres,
        'total_non_livres': total_non_livres,
        'date_impression': timezone.localtime(),
    }
    return render(request, 'planning/recap_factures_forfaitaires_print.html', context)


@login_required
def maintenance_avances(request):
    """Page de nettoyage pour les avances, recettes et paiements forfaitaires."""
    from .views_simple import _get_planning_scope
    if not request.user.is_superuser and not _get_planning_scope(request.user) in ['all', 'organisation']:
        return render(request, "403.html", status=403)

    from .models import PlanningDetail, Designation
    from apps.billing.models import PaiementForfaitaire

    if request.method == "POST":
        action = request.POST.get('action')
        selected_ids = request.POST.getlist('selected_ids')
        source_type = request.POST.get('source_type', 'planning_detail')

        if selected_ids:
            now = timezone.now()
            count = 0

            if source_type == 'paiement_forfaitaire':
                paiements = PaiementForfaitaire.objects.filter(id__in=selected_ids)
                if action == 'supprimer':
                    count = paiements.count()
                    paiements.delete()
                    messages.error(request, f"{count} paiement(s) forfaitaire(s) supprim?(s) d?finitivement.")
                    return redirect('planning:maintenance_avances')
                if action == 'marquer_livre':
                    count = paiements.filter(traite_en_avance=False).update(traite_en_avance=True)
                    messages.success(request, f"{count} paiement(s) forfaitaire(s) marqu?(s) comme trait?(s).")
                    return redirect('planning:maintenance_avances')
                if action == 'annuler_livre':
                    count = paiements.filter(traite_en_avance=True).update(traite_en_avance=False)
                    messages.success(request, f"{count} paiement(s) forfaitaire(s) remis en attente.")
                    return redirect('planning:maintenance_avances')
            else:
                details = PlanningDetail.objects.filter(id__in=selected_ids)
                if action == 'marquer_livre':
                    count = details.update(livraison=True, date_livraison=now.date())
                elif action == 'annuler_livre':
                    count = details.filter(livraison=True).update(livraison=False, date_livraison=None, retour=False, date_retour=None)
                elif action == 'marquer_retour':
                    count = details.update(retour=True, date_retour=now.date())
                    details.filter(livraison=False).update(livraison=True, date_livraison=now.date())
                elif action == 'marquer_les_deux':
                    count = details.update(
                        livraison=True,
                        date_livraison=now.date(),
                        retour=True,
                        date_retour=now.date(),
                    )
                elif action == 'supprimer':
                    count = details.count()
                    details.delete()
                    messages.error(request, f"{count} ligne(s) supprim?e(s) d?finitivement.")
                    return redirect('planning:maintenance_avances')

                messages.success(request, f"{count} ligne(s) mise(s) ? jour avec succ?s.")
        else:
            messages.warning(request, "Aucun ?l?ment n'a ?t? s?lectionn?.")

        return redirect('planning:maintenance_avances')

    allowed_planning_ids = _filter_plannings_by_scope(Planning.objects.all(), request.user).values_list('id', flat=True)

    q = request.GET.get('q', '')
    ouvrage_id = request.GET.get('ouvrage_id')
    designation_id = request.GET.get('designation_id')
    statut = request.GET.get('statut')
    selected_mois = request.GET.get('mois', '').strip()
    parsed_mois = _parse_month_filter(selected_mois)

    avances_queryset = PlanningDetail.objects.filter(
        planning_id__in=allowed_planning_ids,
        planning__estvalide=True,
    ).filter(
        _avance_or_recette_designation_q()
    )
    if q:
        avances_queryset = avances_queryset.filter(
            Q(numero_bon_avance__icontains=q) |
            Q(planning__employe__nom__icontains=q) |
            Q(planning__employe__prenom__icontains=q) |
            Q(designation__nom__icontains=q)
        )
    if ouvrage_id:
        avances_queryset = avances_queryset.filter(planning__ouvrage_id=ouvrage_id)
    if designation_id:
        avances_queryset = avances_queryset.filter(designation_id=designation_id)
    if parsed_mois:
        avances_queryset = avances_queryset.filter(
            planning__date__year=parsed_mois.year,
            planning__date__month=parsed_mois.month,
        )
    if statut == 'a_livrer':
        avances_queryset = avances_queryset.filter(livraison=False)
    elif statut == 'livre':
        avances_queryset = avances_queryset.filter(livraison=True)
    elif statut == 'a_retourner':
        avances_queryset = avances_queryset.filter(retour=False)
    elif statut == 'en_attente':
        avances_queryset = avances_queryset.filter(livraison=False)
    elif statut == 'termine':
        avances_queryset = avances_queryset.filter(livraison=True, retour=True)

    paiements_forfaitaires = PaiementForfaitaire.objects.filter(
        planning_id__in=allowed_planning_ids,
        planning__isnull=False,
        planning__estvalide=True,
        paye=False,
    ).filter(Q(numeroDiameX__isnull=True) | Q(numeroDiameX=''))
    if q:
        paiements_forfaitaires = paiements_forfaitaires.filter(
            Q(planning__employe__nom__icontains=q) |
            Q(planning__employe__prenom__icontains=q) |
            Q(point_eau__nomabonne__icontains=q)
        )
    if ouvrage_id:
        paiements_forfaitaires = paiements_forfaitaires.filter(planning__ouvrage_id=ouvrage_id)
    if parsed_mois:
        paiements_forfaitaires = paiements_forfaitaires.filter(
            planning__date__year=parsed_mois.year,
            planning__date__month=parsed_mois.month,
        )
    if statut == 'a_livrer':
        paiements_forfaitaires = paiements_forfaitaires.filter(traite_en_avance=False)
    elif statut == 'livre':
        paiements_forfaitaires = paiements_forfaitaires.filter(traite_en_avance=True)
    elif statut == 'en_attente':
        paiements_forfaitaires = paiements_forfaitaires.filter(traite_en_avance=False)
    elif statut == 'termine':
        paiements_forfaitaires = paiements_forfaitaires.filter(traite_en_avance=True)

    from apps.organization.models import Ouvrage
    ouvrages = Ouvrage.objects.filter(
        id__in=avances_queryset.values_list('planning__ouvrage_id', flat=True).distinct()
    ).order_by('nom_ouvrage')
    designations = Designation.objects.filter(
        id__in=avances_queryset.values_list('designation_id', flat=True).distinct()
    ).order_by('nom')

    total_count = avances_queryset.count() + paiements_forfaitaires.count()
    livre_count = avances_queryset.filter(livraison=True).count() + paiements_forfaitaires.filter(traite_en_avance=True).count()
    retour_count = avances_queryset.filter(retour=True).count()
    livre_pct = (livre_count / total_count * 100) if total_count > 0 else 0
    retour_pct = (retour_count / total_count * 100) if total_count > 0 else 0

    avances_queryset = avances_queryset.select_related(
        'planning', 'planning__employe', 'planning__ouvrage', 'designation', 'point_eau'
    ).order_by('-planning__date')[:500]
    paiements_forfaitaires = paiements_forfaitaires.select_related(
        'planning', 'planning__employe', 'planning__ouvrage', 'point_eau', 'point_eau__ouvrage'
    ).order_by('-planning__date')

    paiements_forfaitaires_display = []
    for paiement in paiements_forfaitaires:
        point_eau = getattr(paiement, 'point_eau', None)
        label = _get_point_eau_label(point_eau)
        if not label:
            ouvrage = getattr(point_eau, 'ouvrage', None) if point_eau else None
            label = (
                getattr(point_eau, 'nomabonne', None)
                or getattr(point_eau, 'code_point_eau', None)
                or getattr(ouvrage, 'nom_ouvrage', None)
                or 'Sans point d\'eau'
            )
        paiement.point_eau_label = label
        paiement.point_eau_display = label
        paiements_forfaitaires_display.append(paiement)

    context = {
        'avances': avances_queryset,
        'paiements_forfaitaires': paiements_forfaitaires_display,
        'ouvrages_liste': ouvrages,
        'designations_liste': designations,
        'title': 'Maintenance des Avances (Nettoyage)',
        'search_query': q,
        'selected_ouvrage': ouvrage_id,
        'selected_designation': designation_id,
        'selected_mois': selected_mois,
        'selected_statut': statut,
        'stats': {
            'total': total_count,
            'livre': livre_count,
            'retour': retour_count,
            'livre_pct': round(livre_pct, 1),
            'retour_pct': round(retour_pct, 1),
        }
    }
    return render(request, 'planning/maintenance_avances.html', context)


@login_required
def gestion_livraisons(request):
    """Vue principale pour la gestion des livraisons."""
    from .models import BonLivraison
    from apps.employees.models import Employe

    employe_connecte_id = ''
    employe_connecte = getattr(request.user, 'employe', None)
    if employe_connecte and getattr(employe_connecte, 'id', None):
        employe_connecte_id = str(employe_connecte.id)

    allowed_planning_ids = list(_filter_plannings_by_scope(Planning.objects.all(), request.user).values_list('id', flat=True))
    _ensure_pending_bons_livraison_for_allowed_plannings(allowed_planning_ids)
    bons_livraisons = BonLivraison.objects.filter(
        _get_pending_planning_date_filter(),
        planning_id__in=allowed_planning_ids,
        planning__estvalide=True,
        utilise=False,
    ).select_related(
        'planning',
        'planning__employe',
        'planning__ouvrage',
        'designation',
        'designation__type_designation',
        'point_eau',
        'equipement'
    ).prefetch_related(
        'planning__planning_employees__employee'
    ).order_by('planning__date', 'designation__nom')

    effective_employe_ids = set()
    for bon in bons_livraisons:
        effective_employe = _get_planning_effective_employe(getattr(bon, 'planning', None))
        bon.livraison_employe = effective_employe
        bon.livraison_employe_id = str(getattr(effective_employe, 'id', '') or '')
        bon.livraison_employe_label = _get_employe_label(effective_employe)
        bon.livraison_employe_initials = _get_employe_initials(effective_employe)
        if effective_employe and getattr(effective_employe, 'id', None):
            effective_employe_ids.add(str(effective_employe.id))

    employes_queryset = Employe.objects.filter(
        id__in=effective_employe_ids
    ).select_related('base', 'poste')
    if employe_connecte_id:
        employes_queryset = Employe.objects.filter(
            Q(id__in=effective_employe_ids) | Q(id=employe_connecte_id)
        ).select_related('base', 'poste')
    employes = sorted(
        employes_queryset.distinct(),
        key=lambda employe: (
            _normalize_sort_text(
                getattr(employe, 'surnom', None)
                or getattr(employe, 'nom', None)
                or getattr(employe, 'prenom', None)
                or getattr(employe, 'nom_employe', None)
                or ''
            ),
            str(getattr(employe, 'id', ''))
        )
    )

    magasins = Magasin.objects.select_related('base').all()
    user_base_id = getattr(employe_connecte, 'base_id', None) if employe_connecte else None
    if user_base_id:
        magasins = magasins.filter(base_id=user_base_id)
    else:
        magasins = magasins.none()
    magasins = magasins.order_by('base__nom_base', 'nom_magasin')
    return render(request, 'planning/gestion_livraisons.html', {
        'details_livraisons': bons_livraisons,
        'employes': employes,
        'employe_connecte_id': employe_connecte_id,
        'current_month': timezone.localdate().strftime('%Y-%m'),
        'magasins': magasins,
        'title': 'Gestion des Livraisons',
    })


@login_required
def maintenance_livraisons(request):
    """Vue de maintenance des livraisons."""
    from .models import BonLivraison
    allowed_planning_ids = _filter_plannings_by_scope(Planning.objects.all(), request.user).values_list('id', flat=True)

    if request.method == "POST":
        action = request.POST.get('action')
        selected_ids = request.POST.getlist('selected_ids')

        if not selected_ids:
            messages.warning(request, "Aucun bon n'a été sélectionné.")
            return redirect('planning:maintenance_livraisons')

        bons = BonLivraison.objects.filter(id__in=selected_ids, planning_id__in=allowed_planning_ids)
        now = timezone.now()
        count = 0

        if action == 'marquer_livre':
            count = bons.update(utilise=True, date_utilisation=now)
            messages.success(request, f"{count} bon(s) mis à jour avec succès.")
        elif action == 'marquer_retour':
            count = bons.update(retour=True, date_retour=now)
            bons.filter(utilise=False).update(
                utilise=True,
                date_utilisation=now,
            )
            messages.success(request, f"{count} bon(s) mis à jour avec succès.")
        elif action == 'marquer_les_deux':
            count = bons.update(utilise=True, date_utilisation=now, retour=True, date_retour=now)
            messages.success(request, f"{count} bon(s) mis à jour avec succès.")
        elif action == 'supprimer':
            count = bons.count()
            bons.delete()
            messages.error(request, f"{count} bon(s) supprimé(s) définitivement.")
        else:
            messages.warning(request, "Action inconnue.")

        return redirect('planning:maintenance_livraisons')

    q = request.GET.get('q', '')
    ouvrage_id = request.GET.get('ouvrage_id')
    designation_id = request.GET.get('designation_id')
    statut = request.GET.get('statut')
    selected_mois = request.GET.get('mois', '').strip()
    parsed_mois = _parse_month_filter(selected_mois)

    bons_queryset = BonLivraison.objects.filter(
        planning_id__in=allowed_planning_ids,
        planning__estvalide=True
    )
    if q:
        bons_queryset = bons_queryset.filter(
            Q(numero_bon__icontains=q) |
            Q(planning__employe__nom__icontains=q) |
            Q(planning__employe__prenom__icontains=q) |
            Q(designation__nom__icontains=q)
        )
    if ouvrage_id:
        bons_queryset = bons_queryset.filter(planning__ouvrage_id=ouvrage_id)
    if designation_id:
        bons_queryset = bons_queryset.filter(designation_id=designation_id)
    if parsed_mois:
        bons_queryset = bons_queryset.filter(
            planning__date__year=parsed_mois.year,
            planning__date__month=parsed_mois.month,
        )
    if statut == 'a_livrer':
        bons_queryset = bons_queryset.filter(utilise=False)
    elif statut == 'a_retourner':
        bons_queryset = bons_queryset.filter(retour=False)
    elif statut == 'en_attente':
        bons_queryset = bons_queryset.filter(utilise=False)
    elif statut == 'termine':
        bons_queryset = bons_queryset.filter(utilise=True, retour=True)

    return render(request, 'planning/maintenance_livraisons.html', {
        'bons': bons_queryset.select_related('planning', 'planning__employe', 'planning__ouvrage', 'designation', 'point_eau'),
        'ouvrages_liste': [],
        'designations_liste': [],
        'title': 'Maintenance des Livraisons (Nettoyage)',
        'search_query': q,
        'selected_ouvrage': ouvrage_id,
        'selected_designation': designation_id,
        'selected_mois': selected_mois,
        'selected_statut': statut,
        'stats': {
            'total': bons_queryset.count(),
            'livre': bons_queryset.filter(utilise=True).count(),
            'retour': bons_queryset.filter(retour=True).count(),
            'livre_pct': 0,
            'retour_pct': 0,
        },
    })


@login_required
def fiche_stock(request):
    """Point d'entree minimal pour le stock."""
    return HttpResponse("Stock view not implemented in this module.", status=200)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def imprimer_tickets_recettes(request):
    """Point d'entree minimal pour impression des tickets recettes."""
    return JsonResponse({'success': True, 'message': 'Fonction disponible via traiter_avances.'})


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def traiter_avances(request):
    """Traiter les avances/recettes sélectionnées et générer le récapitulatif de départ."""

    try:
        data = json.loads(request.body)
        detail_ids = data.get('detail_ids', [])
        paiement_ids = data.get('paiement_ids', [])
        line_overrides = data.get('line_overrides') or {}

        if not detail_ids and not paiement_ids:
            return JsonResponse({'error': 'Aucun élément sélectionné'}, status=400)

        # Récupérer les détails sélectionnés
        allowed_planning_ids = list(
            _filter_plannings_by_scope(Planning.objects.all(), request.user).values_list('id', flat=True)
        )
        details_selectionnes = PlanningDetail.objects.filter(
            id__in=detail_ids,
            planning__estvalide=True,
            planning_id__in=allowed_planning_ids,
            livraison=False,
        ).filter(
            _avance_or_recette_designation_q()
        ).select_related(
            'planning',
            'planning__employe',
            'planning__employe__base',
            'planning__employe__base__organisation',
            'planning__ouvrage',
            'designation',
            'designation__type_designation',
            'compte',
            'point_eau'
        )

        paiements_selectionnes = PaiementForfaitaire.objects.filter(
            id__in=paiement_ids,
            planning__isnull=False,
            planning__estvalide=True,
            planning_id__in=allowed_planning_ids,
            paye=False,
            traite_en_avance=False
        ).filter(
            Q(numeroDiameX__isnull=True) | Q(numeroDiameX='')
        ).select_related(
            'planning',
            'planning__employe',
            'planning__employe__base',
            'planning__employe__base__organisation',
            'planning__ouvrage',
            'point_eau',
            'point_eau__ouvrage'
        )

        if not details_selectionnes.exists() and not paiements_selectionnes.exists():
            return JsonResponse({'error': 'Aucun élément valide trouvé'}, status=400)

        # Contrôle RBF (bloquant) : pas d'avance d'indemnité sans paiement pointé, ni en doublon, ni au montant modifié.
        from apps.core import rbf_avance
        rbf_selectionnes = list(details_selectionnes.filter(rbf_avance.DESIGNATION_RBF_Q))
        if rbf_selectionnes:
            try:
                refusees = rbf_avance.ids_refuses([d.id for d in rbf_selectionnes])
            except Exception:
                logging.getLogger(__name__).exception("Contrôle des avances RBF indisponible")
                return JsonResponse({'error': "Contrôle des indemnités RBF indisponible : réessayez."}, status=503)
            if refusees:
                noms = ', '.join(sorted({
                    f"{getattr(d.point_eau, 'idxls', '') or 'sans point'} ({d.montant:.0f} Ar)"
                    for d in rbf_selectionnes if d.id in refusees
                }))
                return JsonResponse({
                    'error': f"Avance RBF refusée par le contrôle (paiement non pointé, plafond ou doublon) : {noms}. "
                             "Voir « Contrôle des avances RBF »."}, status=409)
            for d in rbf_selectionnes:
                ov = line_overrides.get(str(d.id)) or {}
                if ov:
                    nouveau = (_parse_positive_decimal_override(ov.get('quantite', d.quantity), 'Quantite')
                               * _parse_positive_decimal_override(ov.get('pu', d.pu or d.montant or 0), 'Prix unitaire'))
                    if nouveau != d.montant:
                        return JsonResponse({'error': "Le montant d'une avance RBF contrôlée ne peut pas être modifié "
                                                      "ici : refaites la demande."}, status=409)

        # Importer la fonction de création de transaction temporaire et génération numéro
        from apps.accounting.views_temporaire import creer_transaction_depuis_planning_detail
        from .utils import generer_numero_bon

        # Marquer comme livrés, enregistrer la date, générer numéro ET créer les transactions temporaires
        articles_recap = []
        for detail in details_selectionnes:
            override = line_overrides.get(str(detail.id)) or {}
            if override:
                quantite = _parse_positive_decimal_override(override.get('quantite', detail.quantity), 'Quantite')
                pu = _parse_positive_decimal_override(override.get('pu', detail.pu or detail.montant or 0), 'Prix unitaire')
                detail.quantity = quantite
                detail.pu = pu
                detail.montant = quantite * pu

            # Auto-cocher livraison et remplir date_livraison
            detail.livraison = True
            detail.date_livraison = timezone.now().date()

            # Générer le numéro de bon avance si non existant
            if not detail.numero_bon_avance:
                detail.numero_bon_avance = generer_numero_bon(type_bon='avance')

            detail.save()

            # Créer la transaction temporaire DiameX
            type_trans = 'avance' if detail.designation.type_avance_caissiere == 'Avance' else 'recette'
            creer_transaction_depuis_planning_detail(
                planning_detail=detail,
                type_transaction=type_trans,
                created_by=request.user.employe if hasattr(request.user, 'employe') else None
            )
            articles_recap.append(_build_avance_article_from_detail(detail))

        # Les paiements forfaitaires sont sortis de la file des avances dès l'impression.
        for paiement in paiements_selectionnes:
            override = line_overrides.get(str(paiement.id)) or {}
            update_fields = ['traite_en_avance']
            if override:
                quantite = _parse_positive_decimal_override(override.get('quantite', paiement.quantite), 'Quantite')
                quantite = quantite.quantize(Decimal('1'))
                if quantite < 0:
                    raise ValueError("Quantite invalide pour un paiement forfaitaire")
                # Le prix unitaire des PaiementForfaitaire ne doit pas etre modifiable depuis l'interface.
                pu = paiement.prix_unitaire or paiement.montant or Decimal('0')
                paiement.quantite = int(quantite)
                paiement.prix_unitaire = pu
                paiement.montant = Decimal(paiement.quantite) * pu
                update_fields.extend(['quantite', 'prix_unitaire', 'montant'])
            paiement.traite_en_avance = True
            paiement.save(update_fields=update_fields)
            articles_recap.append(_build_avance_article_from_paiement(paiement))

        # Générer le PDF du bon de retour
        pdf_buffer = generer_bon_avance_pdf(articles_recap)

        # Retourner le PDF en réponse
        response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename=recap_depart_agent_{timezone.localtime().strftime("%Y%m%d_%H%M")}.pdf'

        return response

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors du traitement: {str(e)}'}, status=500)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def traiter_livraisons(request):
    """Traiter les livraisons selectionnees et generer le bon de livraison."""
    try:
        from .models import BonLivraison
        from apps.inventory.models import FicheStock
        from .utils import generer_numero_bon

        data = json.loads(request.body)
        detail_ids = data.get('detail_ids', [])
        magasin_overrides = data.get('magasin_overrides') or {}
        if not detail_ids:
            return JsonResponse({'error': 'Aucun element selectionne'}, status=400)

        allowed_planning_ids = list(
            _filter_plannings_by_scope(Planning.objects.all(), request.user).values_list('id', flat=True)
        )
        bons_selectionnes = BonLivraison.objects.filter(
            _get_pending_planning_date_filter(),
            id__in=detail_ids,
            planning__estvalide=True,
            planning_id__in=allowed_planning_ids,
            utilise=False
        ).select_related('planning', 'designation', 'designation__type_designation', 'point_eau', 'equipement')

        if not bons_selectionnes.exists():
            return JsonResponse({'error': 'Aucun element valide trouve'}, status=400)

        stocks_avant = {}
        for bon in bons_selectionnes:
            override_magasin = (magasin_overrides.get(str(bon.id)) or '').strip()
            if override_magasin:
                bon.magasin = override_magasin
            stocks_avant[str(bon.id)] = _compute_stock_avant_pour_bon_livraison(bon)

        for bon in bons_selectionnes:
            override_magasin = (magasin_overrides.get(str(bon.id)) or '').strip()
            if override_magasin:
                bon.magasin = override_magasin
            bon.utilise = True
            bon.date_utilisation = timezone.now()
            if not bon.numero_bon:
                bon.numero_bon = generer_numero_bon(type_bon='livraison')
            bon.save()

            if bon.designation and bon.quantite and bon.magasin:
                try:
                    base = _resolve_base_from_magasin_text(bon.magasin)
                    if base:
                        FicheStock.objects.create(
                            designation=bon.designation,
                            base=base,
                            quantity=bon.quantite,
                            operation_type='livraison',
                            operation_date=timezone.now().date(),
                            notes=f"BonLivraison ID: {bon.id} - Livraison terrain - BL {bon.numero_bon or 'N/A'}",
                            reference=bon.numero_bon
                        )
                except Exception as e:
                    print(f"[WARNING] Erreur sortie stock pour {bon.id}: {e}")

        pdf_buffer = generer_bon_livraison_pdf(bons_selectionnes, stocks_avant)
        response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f"attachment; filename=bon_livraison_{timezone.now().strftime('%Y%m%d_%H%M')}.pdf"
        return response
    except Exception as e:
        return JsonResponse({'error': f'Erreur lors du traitement: {str(e)}'}, status=500)


@login_required
@require_http_methods(["GET", "POST"])
def api_details_livraisons(request):
    """API pour recuperer les details de planning concernant les livraisons."""
    try:
        payload = {}
        if request.method == "POST":
            payload = json.loads(request.body or '{}')

        planning_id = request.GET.get('planning_id') or payload.get('planning_id')
        detail_ids = payload.get('detail_ids') or request.GET.getlist('detail_ids[]')
        if not planning_id and not detail_ids:
            return JsonResponse({'success': False, 'error': 'planning_id ou detail_ids manquant'}, status=400)

        allowed_planning_ids = list(
            _filter_plannings_by_scope(Planning.objects.all(), request.user).values_list('id', flat=True)
        )
        from .models import BonLivraison
        bons_livraison = BonLivraison.objects.filter(
            _get_pending_planning_date_filter(),
            planning_id__in=allowed_planning_ids,
            planning__estvalide=True
        )
        if planning_id:
            bons_livraison = bons_livraison.filter(planning_id=planning_id)
        if detail_ids:
            bons_livraison = bons_livraison.filter(id__in=detail_ids)

        bons_livraison = bons_livraison.select_related('planning', 'designation', 'point_eau', 'equipement')

        data = []
        for bon in bons_livraison:
            data.append({
                'id': str(bon.id),
                'planning_id': str(bon.planning_id) if bon.planning_id else '',
                'designation': getattr(bon.designation, 'nom', ''),
                'quantite': bon.quantite,
                'livre': bool(bon.utilise),
                'retour': bool(bon.retour),
                'numero_bon': bon.numero_bon or '',
            })
        return JsonResponse({'success': True, 'results': data})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET", "POST"])
def api_verifier_stock_livraisons(request):
    """API pour verifier le stock disponible pour les livraisons selectionnees."""
    try:
        payload = {}
        if request.method == "POST":
            payload = json.loads(request.body or '{}')

        planning_id = request.GET.get('planning_id') or payload.get('planning_id')
        detail_ids = payload.get('detail_ids') or request.GET.getlist('detail_ids[]')
        magasin_overrides = payload.get('magasin_overrides') or {}
        if not planning_id and not detail_ids:
            return JsonResponse({'success': False, 'error': 'planning_id ou detail_ids manquant'}, status=400)

        allowed_planning_ids = list(
            _filter_plannings_by_scope(Planning.objects.all(), request.user).values_list('id', flat=True)
        )
        from .models import BonLivraison
        bons = BonLivraison.objects.filter(
            _get_pending_planning_date_filter(),
            planning_id__in=allowed_planning_ids,
            planning__estvalide=True
        )
        if planning_id:
            bons = bons.filter(planning_id=planning_id)
        if detail_ids:
            bons = bons.filter(id__in=detail_ids)

        bons = bons.select_related('designation', 'point_eau', 'equipement')

        result = []
        stocks_insuffisants = []
        for bon in bons:
            override_magasin = (magasin_overrides.get(str(bon.id)) or '').strip()
            if override_magasin:
                bon.magasin = override_magasin
            stock_actuel = _compute_stock_avant_pour_bon_livraison(bon)
            quantite_demandee = float(bon.quantite or 0)
            stock_actuel_float = float(stock_actuel or 0)
            stock_apres_livraison = stock_actuel_float - quantite_demandee
            suffisant = stock_actuel_float >= quantite_demandee

            row = {
                'detail_id': str(bon.id),
                'designation': getattr(bon.designation, 'nom', ''),
                'quantite_demandee': quantite_demandee,
                'stock_actuel': stock_actuel_float,
                'stock_apres_livraison': stock_apres_livraison,
                'magasin': bon.magasin or '',
                'suffisant': suffisant,
                'peut_livrer': suffisant,
            }
            result.append(row)
            if not suffisant:
                stocks_insuffisants.append(row)

        return JsonResponse({
            'success': True,
            'peut_livrer': not stocks_insuffisants,
            'resultats': result,
            'stocks_insuffisants': stocks_insuffisants,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def api_delete_avance_source(request):
    """Supprime la source d'une ligne d'avance/recette ou d'un paiement forfaitaire."""
    try:
        if not request.user.is_superuser and _get_planning_scope(request.user) not in ['all', 'organisation']:
            return JsonResponse({'success': False, 'error': 'Acces refuse'}, status=403)

        data = json.loads(request.body or '{}')
        source_type = (data.get('source_type') or '').strip()
        item_id = (data.get('item_id') or '').strip()

        if not source_type or not item_id:
            return JsonResponse({'success': False, 'error': 'source_type et item_id sont obligatoires'}, status=400)

        allowed_planning_ids = list(
            _filter_plannings_by_scope(Planning.objects.all(), request.user).values_list('id', flat=True)
        )

        if source_type == 'paiement_forfaitaire':
            paiement = PaiementForfaitaire.objects.filter(
                id=item_id,
                planning_id__in=allowed_planning_ids,
            ).first()
            if not paiement:
                return JsonResponse({'success': False, 'error': 'Paiement forfaitaire introuvable'}, status=404)
            if paiement.paye or (paiement.numeroDiameX or '').strip():
                return JsonResponse({'success': False, 'error': 'Impossible de supprimer un paiement deja encaisse'}, status=400)
            paiement.delete()
            return JsonResponse({'success': True})

        if source_type == 'livraison':
            livraison = BonLivraison.objects.filter(
                id=item_id,
                planning_id__in=allowed_planning_ids,
            ).first()
            if not livraison:
                return JsonResponse({'success': False, 'error': 'Livraison introuvable'}, status=404)
            if livraison.utilise or livraison.retour:
                return JsonResponse({'success': False, 'error': 'Impossible de supprimer une livraison deja traitee'}, status=400)
            livraison.delete()
            return JsonResponse({'success': True})

        detail = PlanningDetail.objects.filter(
            id=item_id,
            planning_id__in=allowed_planning_ids,
        ).filter(
            _avance_or_recette_designation_q()
        ).first()
        if not detail:
            return JsonResponse({'success': False, 'error': 'Ligne planning introuvable'}, status=404)
        if detail.livraison or detail.retour:
            return JsonResponse({'success': False, 'error': 'Impossible de supprimer une ligne deja traitee'}, status=400)
        detail.delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def generer_bon_avance_pdf(articles_avances):
    """Générer le PDF du récapitulatif de départ agent."""

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []

    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=30,
        alignment=1  # Centré
    )
    org_style = ParagraphStyle(
        'OrgStyle',
        parent=styles['Heading2'],
        fontSize=14,
        spaceAfter=10,
        alignment=1  # Centré
    )
    section_style = ParagraphStyle(
        'RecapSection',
        parent=styles['Heading2'],
        fontSize=12,
        spaceAfter=8,
        alignment=0
    )

    organisation_names = sorted({
        article.get('organisation_nom')
        for article in articles_avances
        if article.get('organisation_nom')
    })
    employe_names = sorted({
        article.get('employe_nom')
        for article in articles_avances
        if article.get('employe_nom') and article.get('employe_nom') != '-'
    })
    organisation_nom = ''
    if len(organisation_names) == 1:
        organisation_nom = organisation_names[0]
    elif len(organisation_names) > 1:
        organisation_nom = 'HYDRIA - Organisations multiples'

    logo_path = None
    logo_urls = [
        (article.get('organisation_logo_url') or '').strip()
        for article in articles_avances
        if (article.get('organisation_logo_url') or '').strip()
    ]
    for logo_url in logo_urls:
        try:
            media_url = str(getattr(settings, 'MEDIA_URL', '') or '')
            if media_url and logo_url.startswith(media_url):
                logo_name = logo_url[len(media_url):].lstrip('/\\')
                candidate_path = os.path.join(settings.MEDIA_ROOT, logo_name)
                if os.path.exists(candidate_path):
                    logo_path = candidate_path
                    break
        except Exception:
            continue

    if logo_path:
        try:
            logo = Image(logo_path, width=140, height=60, kind='proportional')
            logo.hAlign = 'CENTER'
            elements.append(logo)
            elements.append(Spacer(1, 8))
        except Exception:
            logo_path = None

    if not logo_path and organisation_nom:
        org_para = Paragraph(f"<b>{organisation_nom}</b>", org_style)
        elements.append(org_para)
        elements.append(Spacer(1, 10))

    # Titre
    title = Paragraph("RECAPITULATIF DE DEPART AGENT", title_style)
    elements.append(title)
    elements.append(Spacer(1, 20))

    # Informations générales
    date_retour = timezone.localtime().strftime("%d/%m/%Y a %H:%M")
    info_lines = [
        f"<b>Date d'impression:</b> {date_retour}",
        f"<b>Nombre d'elements:</b> {len(articles_avances)}",
    ]
    if len(employe_names) == 1:
        info_lines.append(f"<b>Employe:</b> {employe_names[0]}")
    elif len(employe_names) > 1:
        info_lines.append("<b>Employes:</b> Selection multiple")
    info_para = Paragraph("<br/>".join(info_lines), styles['Normal'])
    elements.append(info_para)
    elements.append(Spacer(1, 20))

    # Regrouper par ouvrage
    from collections import defaultdict
    ouvrages_dict = defaultdict(list)

    for article in articles_avances:
        ouvrage_key = article.get('ouvrage_nom') or 'Sans ouvrage'
        ouvrages_dict[ouvrage_key].append(article)

    data = [['Libelle', 'Type', 'Quantite', 'Montant']]

    total_avances = Decimal('0')
    total_recettes = Decimal('0')

    for ouvrage_nom, details_ouvrage in ouvrages_dict.items():
        data.append(['', '', '', ''])
        data.append([f"OUVRAGE: {ouvrage_nom}", '', '', ''])

        for article in details_ouvrage:
            montant = Decimal(str(article.get('montant') or 0))
            type_avance = article.get('type_avance') or '-'
            if type_avance == 'Avance':
                total_avances += montant
            elif type_avance == 'Recette':
                total_recettes += montant

            quantite = article.get('quantite') or 0
            try:
                quantite_float = float(quantite)
                quantite_label = str(int(quantite_float)) if quantite_float.is_integer() else f"{quantite_float:.1f}"
            except (TypeError, ValueError):
                quantite_label = str(quantite or '-')

            montant_format = f"{float(montant):,.0f}".replace(',', ' ') + " Ar"
            data.append([
                article.get('designation_pdf') or article.get('designation_nom') or '-',
                type_avance,
                quantite_label,
                montant_format
            ])

    avance_a_faire = max(Decimal('0'), total_avances - total_recettes)

    total_avances_format = f"{float(total_avances):,.0f}".replace(',', ' ') + " Ar"
    total_recettes_format = f"{float(total_recettes):,.0f}".replace(',', ' ') + " Ar"
    avance_a_faire_format = f"{float(avance_a_faire):,.0f}".replace(',', ' ') + " Ar"

    data.append(['', '', '', ''])
    data.append(['Total Dépenses', '', '', total_avances_format])
    data.append(['Total Recettes', '', '', total_recettes_format])
    data.append(['Avances', '', '', avance_a_faire_format])

    table = Table(data, colWidths=[240, 65, 55, 75])

    style_list = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]

    for i, row in enumerate(data):
        if i == 0:
            continue
        elif row[0] == '' and row[1] == '' and row[2] == '' and row[3] == '':
            style_list.append(('BACKGROUND', (0, i), (-1, i), colors.white))
            style_list.append(('LINEABOVE', (0, i), (-1, i), 1, colors.white))
        elif row[0].startswith('OUVRAGE:'):
            style_list.append(('BACKGROUND', (0, i), (-1, i), colors.lightgrey))
            style_list.append(('FONTNAME', (0, i), (-1, i), 'Helvetica-Bold'))
            style_list.append(('FONTSIZE', (0, i), (-1, i), 10))
            style_list.append(('SPAN', (0, i), (-1, i)))
            style_list.append(('ALIGN', (0, i), (-1, i), 'LEFT'))
        elif row[0] in ['Total Dépenses', 'Total Recettes', 'Avances']:
            if row[0] == 'Total Dépenses':
                style_list.append(('BACKGROUND', (0, i), (-1, i), colors.lightcoral))
            elif row[0] == 'Total Recettes':
                style_list.append(('BACKGROUND', (0, i), (-1, i), colors.lightgreen))
            elif row[0] == 'Avances':
                style_list.append(('BACKGROUND', (0, i), (-1, i), colors.lightblue))
                style_list.append(('FONTSIZE', (0, i), (-1, i), 12))
            style_list.append(('FONTNAME', (0, i), (-1, i), 'Helvetica-Bold'))
            style_list.append(('SPAN', (0, i), (2, i)))
        else:
            style_list.append(('BACKGROUND', (0, i), (-1, i), colors.beige))

    table.setStyle(TableStyle(style_list))

    elements.append(table)
    elements.append(Spacer(1, 30))

    emargement_title = Paragraph("<b>EMARGEMENT</b>", section_style)
    elements.append(emargement_title)
    elements.append(Spacer(1, 8))

    emargement_data = [
        ['DEPART AGENT', 'REMIS PAR', 'VALIDE PAR'],
        ['Nom: ________________________', 'Nom: ________________________', 'Nom: ________________________'],
        ['Signature: __________________', 'Signature: __________________', 'Signature: __________'],
        ['Date: _______________________', 'Date: _______________________', 'Date: _______________________'],
    ]

    emargement_table = Table(emargement_data, colWidths=[180, 180, 180])
    emargement_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOX', (0, 0), (-1, -1), 1, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.75, colors.grey),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(emargement_table)

    # Construire le PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer


def generer_bon_livraison_pdf(bons_livraisons, stocks_avant=None):
    """Generer le PDF du bon de livraison."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'BonLivraisonTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=18,
        alignment=1,
    )
    section_style = ParagraphStyle(
        'BonLivraisonSection',
        parent=styles['Heading2'],
        fontSize=12,
        spaceAfter=8,
    )

    bons_list = list(bons_livraisons or [])
    stocks_avant = stocks_avant or {}

    organisation = None
    for bon in bons_list:
        planning = getattr(bon, 'planning', None)
        employe = getattr(planning, 'employe', None)
        organisation = getattr(getattr(employe, 'base', None), 'organisation', None)
        if organisation:
            break

    logo_path = None
    if organisation:
        try:
            logo_field = getattr(organisation, 'logo', None)
            logo_name = getattr(logo_field, 'name', '')
            if logo_name:
                candidate_path = os.path.join(settings.MEDIA_ROOT, logo_name)
                if os.path.exists(candidate_path):
                    logo_path = candidate_path
        except Exception:
            logo_path = None

    if logo_path:
        try:
            logo = Image(logo_path, width=120, height=60)
            elements.append(logo)
            elements.append(Spacer(1, 8))
        except Exception:
            pass

    elements.append(Paragraph("BON DE LIVRAISON", title_style))
    elements.append(Spacer(1, 10))

    numeros_bon = sorted({
        (bon.numero_bon or '').strip()
        for bon in bons_list
        if (bon.numero_bon or '').strip()
    })
    info_lines = [
        f"<b>Date d'impression:</b> {timezone.now().strftime('%d/%m/%Y a %H:%M')}",
        f"<b>Nombre de lignes:</b> {len(bons_list)}",
    ]
    if numeros_bon:
        info_lines.append(f"<b>N° bon:</b> {', '.join(numeros_bon)}")
    if organisation:
        info_lines.append(
            f"<b>Organisation:</b> {getattr(organisation, 'nom_organisation', '') or 'HYDRIA'}"
        )
    elements.append(Paragraph("<br/>".join(info_lines), styles['Normal']))
    elements.append(Spacer(1, 14))

    premier_bon = bons_list[0] if bons_list else None
    premier_planning = getattr(premier_bon, 'planning', None)
    premier_employe = getattr(premier_planning, 'employe', None)
    expediteur_magasin = _get_magasin_display_label(getattr(premier_bon, 'magasin', None))
    destinataire = _get_employe_label(premier_employe)
    ouvrage_nom = getattr(getattr(premier_planning, 'ouvrage', None), 'nom_ouvrage', None) or '-'
    base_nom = getattr(getattr(premier_employe, 'base', None), 'nom_base', None) or '-'

    info_table = Table([
        ['EXPEDITEUR', 'DESTINATAIRE'],
        [
            Paragraph(
                "<br/>".join([
                    f"<b>Magasin:</b> {expediteur_magasin}",
                    f"<b>Base:</b> {base_nom}",
                    f"<b>Organisation:</b> {getattr(organisation, 'nom_organisation', 'HYDRIA') if organisation else 'HYDRIA'}",
                ]),
                styles['Normal']
            ),
            Paragraph(
                "<br/>".join([
                    f"<b>Agent:</b> {destinataire}",
                    f"<b>Ouvrage:</b> {ouvrage_nom}",
                    f"<b>Date prevue:</b> {premier_planning.date.strftime('%d/%m/%Y %H:%M') if getattr(premier_planning, 'date', None) else '-'}",
                ]),
                styles['Normal']
            ),
        ]
    ], colWidths=[260, 260])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e5e7eb')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOX', (0, 0), (-1, -1), 0.75, colors.grey),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 14))

    data = [[
        'Date',
        'Employe',
        'Ouvrage',
        'Designation',
        'Qte',
        'Stock avant',
        'Cible',
    ]]

    for bon in bons_list:
        planning = getattr(bon, 'planning', None)
        employe = getattr(planning, 'employe', None)
        ouvrage = getattr(planning, 'ouvrage', None)
        point_eau = getattr(bon, 'point_eau', None)
        equipement = getattr(bon, 'equipement', None)

        employe_nom = _get_employe_label(employe)
        ouvrage_nom = getattr(ouvrage, 'nom_ouvrage', None) or '-'
        designation_nom = getattr(getattr(bon, 'designation', None), 'nom', None) or '-'
        quantite = Decimal(str(getattr(bon, 'quantite', 0) or 0))
        stock_avant_value = Decimal(str(stocks_avant.get(str(bon.id), 0) or 0))

        cible = '-'
        if point_eau:
            cible = _get_point_eau_label(point_eau) or 'Point d eau'
        elif equipement:
            cible = (
                getattr(equipement, 'nom', None)
                or getattr(equipement, 'designation', None)
                or 'Equipement'
            )

        planning_date = getattr(planning, 'date', None)
        date_label = planning_date.strftime('%d/%m/%Y') if planning_date else '-'

        data.append([
            date_label,
            employe_nom,
            ouvrage_nom,
            designation_nom,
            f"{quantite:.2f}",
            f"{stock_avant_value:.2f}",
            str(cible),
        ])

    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f3b73')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.lightgrey]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (4, 1), (5, -1), 'RIGHT'),
    ]))

    elements.append(Paragraph("Details des livraisons", section_style))
    elements.append(table)
    elements.append(Spacer(1, 24))

    signatures = Table([
        ['Signature magasinier', 'Signature destinataire'],
        [
            Paragraph(
                "<br/><br/><br/><br/>____________________________<br/>Nom et signature",
                styles['Normal']
            ),
            Paragraph(
                "<br/><br/><br/><br/>____________________________<br/>Nom et signature",
                styles['Normal']
            ),
        ],
    ], colWidths=[260, 260])
    signatures.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f3f4f6')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOX', (0, 0), (-1, -1), 0.75, colors.grey),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
    ]))
    elements.append(signatures)

    doc.build(elements)
    buffer.seek(0)
    return buffer


@login_required
@require_http_methods(["POST"])
def imprimer_tickets_recettes(request):
    """
    Générer les tickets de caisse pour les recettes paiement forfaitaire (format 80mm)
    1 ticket par ligne de recette
    """
    try:
        data = json.loads(request.body)
        detail_ids = data.get('detail_ids', [])

        if not detail_ids:
            return JsonResponse({'error': 'Aucune recette sélectionnée'}, status=400)

        # Récupérer les détails de recettes sélectionnés
        allowed_planning_ids = _filter_plannings_by_scope(Planning.objects.all(), request.user).values_list('id', flat=True)

        details_recettes = PlanningDetail.objects.filter(
            _get_pending_planning_date_filter(),
            id__in=detail_ids,
            planning_id__in=allowed_planning_ids,
            designation__type_avance_caissiere__iexact='recette'
        ).select_related(
            'planning', 'planning__employe', 'planning__employe__base',
            'planning__employe__base__organisation', 'planning__ouvrage',
            'designation'
        ).order_by('planning__employe__surnom', 'planning__date')

        if not details_recettes.exists():
            return JsonResponse({'error': 'Aucune recette valide trouvée'}, status=400)

        # Récupérer l'organisation
        user_base = getattr(getattr(request.user, 'employe', None), 'base', None)
        organisation = getattr(user_base, 'organisation', None)
        if details_recettes.exists():
            premier_detail = details_recettes.first()
            if organisation is None and premier_detail.planning and premier_detail.planning.employe:
                employe = premier_detail.planning.employe
                if hasattr(employe, 'base') and employe.base:
                    organisation = employe.base.organisation

        # Préparer les données JSON pour chaque recette
        recettes_data = []
        for detail in details_recettes:
            recettes_data.append({
                'id': str(detail.id),
                'numero_bon_avance': detail.numero_bon_avance,
                'date_planning': detail.planning.date.strftime('%d/%m/%Y') if detail.planning else '',
                'employe_surnom': detail.planning.employe.surnom if detail.planning and detail.planning.employe else '',
                'ouvrage_nom': detail.planning.ouvrage.nom_ouvrage if detail.planning and detail.planning.ouvrage else '',
                'point_eau_code': detail.point_eau.idxls if detail.point_eau else '',
                'nom_abonne': detail.point_eau.nomabonne if detail.point_eau else '',
                'base_nom': detail.planning.employe.base.nom_base if detail.planning and detail.planning.employe and detail.planning.employe.base else '',
                'base_telephone': detail.planning.employe.base.telephone if detail.planning and detail.planning.employe and detail.planning.employe.base else '',
                'compte_nom': detail.compte.nom_compte if detail.compte else '',
                'designation_nom': detail.designation.nom if detail.designation else 'Paiement forfaitaire',
                'quantity': float(detail.quantity) if detail.quantity else 1,
                'pu': float(detail.pu) if detail.pu else float(detail.montant or 0),
                'montant': float(detail.montant or 0)
            })

        # Préparer les données de l'organisation
        organisation_data = {
            'nom_organisation': organisation.nom_organisation if organisation else 'HYDRIA',
            'logo_url': organisation.logo.url if organisation and organisation.logo else '',
            'nif': organisation.nif if organisation else '',
            'stat': organisation.stat if organisation else '',
            'telephone': organisation.telephone if organisation else '',
            'base': user_base.nom_base if user_base else '',
            'base_telephone': user_base.telephone if user_base else '',
        }

        # Générer le HTML avec tous les tickets (1 par ligne)
        context = {
            'details_recettes': json.dumps(recettes_data),
            'organisation_json': json.dumps(organisation_data),
            'date_impression': timezone.now(),
        }

        return render(request, 'planning/tickets_recettes_print.html', context)

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de la génération des tickets: {str(e)}'}, status=500)


@login_required
def fiche_stock(request):
    """Ancienne fiche de stock du planning : redirige vers la fiche de stock du module inventaire.

    Ses gabarits (planning/fiche_stock_liste.html et fiche_stock_detail.html) n'existent plus :
    la page répondait une erreur 500.
    """
    return redirect('inventory:fiche_stock_list')


@login_required
def imprimer_planning_agent(request):
    """Générer le PDF du planning d'un agent pour un mois donné"""

    employe_id = request.GET.get('employe_id')
    mois = request.GET.get('mois')  # Format YYYY-MM

    if not employe_id or not mois:
        return JsonResponse({'error': 'Employé et mois requis'}, status=400)

    try:
        employe = get_object_or_404(Employe, id=employe_id)

        # Extraire l'année et le mois
        year, month = mois.split('-')

        # Récupérer les plannings validés de l'employé pour le mois
        plannings = Planning.objects.filter(
            employe_id=employe_id,
            estvalide=True,
            date__year=year,
            date__month=month
        ).select_related(
            'ouvrage', 'fiche_poste', 'type_activite'
        ).prefetch_related(
            'details__designation',
            'details__compte'
        ).order_by('date')

        if not plannings.exists():
            return JsonResponse({'error': 'Aucun planning trouvé pour cet employé ce mois-ci'}, status=404)

        # Générer le PDF
        pdf_buffer = generer_planning_agent_pdf(employe, plannings, mois)

        response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename=planning_{employe.nom}_{mois}.pdf'

        return response

    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de la génération: {str(e)}'}, status=500)


def generer_planning_agent_pdf(employe, plannings, mois):
    """Générer le PDF du planning d'un agent"""

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=1*inch)
    elements = []

    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=20,
        alignment=1  # Centré
    )

    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Heading2'],
        fontSize=12,
        spaceAfter=15,
        alignment=1
    )

    # Titre principal
    title = Paragraph(f"PLANNING MENSUEL", title_style)
    elements.append(title)

    # Informations de l'employé
    employee_info = Paragraph(f"""
    <b>Employé:</b> {employe.nom} {employe.prenom}<br/>
    <b>Période:</b> {mois}<br/>
    <b>Date d'impression:</b> {timezone.now().strftime("%d/%m/%Y à  %H:%M")}
    """, subtitle_style)
    elements.append(employee_info)
    elements.append(Spacer(1, 20))

    # Statistiques
    plannings_valides = plannings.filter(estvalide=True).count()
    total_plannings = plannings.count()

    stats_para = Paragraph(f"""
    <b>Statistiques:</b><br/>
    â€¢ Total plannings: {total_plannings}<br/>
    â€¢ Plannings validés: {plannings_valides}<br/>
    â€¢ Taux de validation: {(plannings_valides/total_plannings*100) if total_plannings > 0 else 0:.1f}%
    """, styles['Normal'])
    elements.append(stats_para)
    elements.append(Spacer(1, 20))

    # Tableau des plannings
    data = [['Date', 'Statut', 'Activité', 'Ouvrage', 'Remarques']]

    for planning in plannings:
        activite_nom = '-'
        if planning.fiche_poste:
            activite_nom = planning.fiche_poste.tache or '-'
        elif planning.type_activite:
            activite_nom = planning.type_activite.nomtype or '-'

        ouvrage_nom = planning.ouvrage.nom_ouvrage if planning.ouvrage else '-'

        # Statut
        statut = " Validé" if planning.estvalide else "â³ En attente"

        data.append([
            planning.date.strftime('%d/%m/%Y'),
            statut,
            activite_nom,
            ouvrage_nom,
            planning.remarque or '-'
        ])

    # Créer le tableau
    table = Table(data, colWidths=[80, 80, 120, 100, 150])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))

    elements.append(table)
    elements.append(Spacer(1, 30))

    # Détails des plannings avec désignations
    if plannings.filter(details__isnull=False).exists():
        elements.append(Paragraph("<b>DéTAILS DES PLANNINGS</b>", styles['Heading3']))
        elements.append(Spacer(1, 10))

        for planning in plannings.filter(details__isnull=False):
            # Titre du planning
            planning_title = Paragraph(f"<b>Planning du {planning.date.strftime('%d/%m/%Y')}</b>", styles['Heading4'])
            elements.append(planning_title)

            # Tableau des détails
            detail_data = [['Désignation', 'Quantité', 'P.U.', 'Montant', 'Compte']]

            total_planning = 0
            for detail in planning.details.all():
                detail_data.append([
                    detail.designation.nom if detail.designation else '-',
                    str(detail.quantity),
                    f"{detail.pu} Ar",
                    f"{detail.montant} Ar",
                    detail.compte.nom_compte if detail.compte else '-'
                ])
                total_planning += detail.montant

            # Ligne de total
            detail_data.append(['<b>TOTAL PLANNING</b>', '', '', f'<b>{total_planning} Ar</b>', ''])

            detail_table = Table(detail_data, colWidths=[150, 60, 80, 80, 100])
            detail_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('FONTSIZE', (0, 1), (-1, -1), 7),
                ('BACKGROUND', (0, -1), (-1, -1), colors.lightblue),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ]))

            elements.append(detail_table)
            elements.append(Spacer(1, 15))

    # Signature
    elements.append(Spacer(1, 30))
    signature_para = Paragraph("""
    <para>
    <b>Signature de l'employé:</b> ________________________&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
    <b>Signature du responsable:</b> ________________________<br/><br/>
    <b>Date:</b> ____________________&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
    <b>Date:</b> ____________________
    </para>
    """, styles['Normal'])
    elements.append(signature_para)

    doc.build(elements)
    buffer.seek(0)
    return buffer
