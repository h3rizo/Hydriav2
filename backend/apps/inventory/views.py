from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from django.core.paginator import Paginator
from .models import Product, Stock, Purchase, StockMovement, PurchaseItem, Supplier, Category, FicheStock
from apps.organization.models import Base, Magasin
from apps.employees.models import Employe
from apps.billing.models import Fournisseur
from django.db.models import Sum, F, Prefetch, Q
from django.utils import timezone
from datetime import datetime, date
import calendar
from decimal import Decimal
from collections import defaultdict
import json
import re
import uuid
import unicodedata
from urllib.parse import urlencode
from openpyxl import load_workbook


def _normalize_poste_name(value):
    if not value:
        return ''
    normalized = unicodedata.normalize('NFKD', str(value))
    return normalized.encode('ascii', errors='ignore').decode('ascii').lower().strip()


def _can_delete_fiche_stock_rows(user):
    """Autorise la suppression des lignes de fiche stock pour Directeur / Caissier(e)."""
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True

    poste_nom = _normalize_poste_name(
        getattr(getattr(getattr(user, 'employe', None), 'poste', None), 'nom_poste', '')
    )
    if not poste_nom:
        return False

    return poste_nom == 'directeur' or 'caissier' in poste_nom


def _get_inventory_scope(user):
    """
    Regles de cloisonnement:
    - Superuser / Directeur: tout
    - Directeur adjoint / Responsable administratif (et financier) / RAF: organisation
    - Autres postes: base
    """
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


def _filter_bases_by_scope(queryset, user):
    scope = _get_inventory_scope(user)
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
    scope = _get_inventory_scope(user)
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


def _resolve_stock_utilisateur_from_request(data, user):
    """
    Resolve l'employe choisi dans le formulaire stock.
    Retourne:
    - Employe si un id valide est fourni
    - None si le champ est vide
    - False si un id est fourni mais invalide / hors scope
    """
    utilisateur_id = (
        data.get('utilisateur_id')
        or data.get('utilisateur')
        or data.get('employee_id')
        or ''
    ).strip()

    if not utilisateur_id:
        return None

    try:
        return _filter_employes_by_scope(
            Employe.objects.all(),
            user
        ).get(id=utilisateur_id)
    except Employe.DoesNotExist:
        return False


def _base_has_multiple_magasins(base_id):
    if not base_id:
        return False
    return Magasin.objects.filter(base_id=base_id).count() > 1


def _stock_request_includes_utilisateur(data):
    return any(
        key in data
        for key in ('utilisateur_id', 'utilisateur', 'employee_id')
    )


def _filter_stocks_by_scope(queryset, user):
    scope = _get_inventory_scope(user)
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


def _filter_plannings_by_scope_inventory(queryset, user):
    scope = _get_inventory_scope(user)
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


def _compute_strict_stock_for_magasin(user, magasin_obj, designation_ids):
    from apps.planning.models import BonLivraison, Planning
    from .models import Transfert

    designation_ids = [designation_id for designation_id in designation_ids if designation_id]
    computed_stock_by_designation = defaultdict(lambda: Decimal('0'))
    last_inventory_date_by_designation = {}
    has_magasin_movement = defaultdict(bool)

    if not magasin_obj or not designation_ids:
        return computed_stock_by_designation, last_inventory_date_by_designation, has_magasin_movement

    plannings_scope = _filter_plannings_by_scope_inventory(
        Planning.objects.all(),
        user
    )

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

    bons_qs = BonLivraison.objects.filter(
        designation_id__in=designation_ids,
        planning__employe__base_id=magasin_obj.base_id,
        planning_id__in=plannings_scope.values('id')
    ).only('id', 'designation_id', 'numero_bon', 'magasin')

    bon_ids_by_designation = defaultdict(set)
    bon_nums_by_designation = defaultdict(set)
    for bon in bons_qs:
        if _match_magasin_label(bon.magasin, magasin_obj):
            designation_key = str(bon.designation_id)
            bon_ids_by_designation[designation_key].add(str(bon.id))
            if bon.numero_bon:
                bon_nums_by_designation[designation_key].add(bon.numero_bon.strip())

    fiches_qs = FicheStock.objects.filter(
        designation_id__in=designation_ids,
        base_id=magasin_obj.base_id
    ).only(
        'designation_id',
        'operation_type',
        'quantity',
        'purchase_id',
        'transfert_id',
        'reference',
        'notes',
        'operation_date',
        'created_at'
    ).order_by('designation_id', 'operation_date', 'created_at')

    magasin_id_marker = f"Magasin ID: {magasin_obj.id}"
    magasin_name_marker = f"Magasin: {magasin_obj.nom_magasin}"

    for fiche in fiches_qs:
        designation_key = str(fiche.designation_id)
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
        elif operation in ['livraison', 'retour_terrain']:
            bon_ids = bon_ids_by_designation.get(designation_key, set())
            bon_nums = bon_nums_by_designation.get(designation_key, set())
            include = any(f"BonLivraison ID: {bon_id}" in notes_value for bon_id in bon_ids)
            if not include and reference_value:
                include = reference_value in bon_nums
            if not include and bon_nums:
                include = any(bon_num in notes_value for bon_num in bon_nums)
            if operation == 'retour_terrain' and not include:
                include = magasin_id_marker in notes_value or magasin_name_marker in notes_value
        elif operation in ['inventaire', 'entree', 'sortie', 'ajustement']:
            include = magasin_id_marker in notes_value or magasin_name_marker in notes_value

        if not include:
            continue

        has_magasin_movement[designation_key] = True
        qty = Decimal(str(fiche.quantity or 0))
        if operation == 'inventaire':
            computed_stock_by_designation[designation_key] = qty
            last_inventory_date_by_designation[designation_key] = fiche.operation_date.date()
        elif operation in ['achat', 'transfert_entree', 'entree', 'retour_terrain']:
            computed_stock_by_designation[designation_key] += qty
        elif operation in ['livraison', 'transfert_sortie', 'sortie']:
            computed_stock_by_designation[designation_key] -= qty
        elif operation == 'ajustement':
            computed_stock_by_designation[designation_key] += qty

    return computed_stock_by_designation, last_inventory_date_by_designation, has_magasin_movement


def _resolve_base_from_magasin_text(magasin_text):
    """Resolve une base depuis un texte magasin, un UUID magasin ou un UUID base."""
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

    base = Base.objects.filter(nom_base__iexact=label).first()
    if base:
        return base

    magasin = Magasin.objects.select_related('base').filter(nom_magasin__iexact=label).first()
    if magasin and magasin.base:
        return magasin.base

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
    Accepte:
    - UUID du magasin
    - Nom exact du magasin (insensible à la casse)
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


MAGASIN_ID_PATTERN = re.compile(
    r'Magasin ID\s*:\s*([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})'
)
MAGASIN_NAME_PATTERN = re.compile(r'Magasin\s*:\s*([^|]+)')


def _extract_magasin_from_notes_value(notes_value, magasins_by_id=None, magasins_by_name=None):
    magasins_by_id = magasins_by_id or {}
    magasins_by_name = magasins_by_name or {}

    if not notes_value:
        return None, 'Non ventilé (base)'

    notes_text = str(notes_value)
    magasin_id_match = MAGASIN_ID_PATTERN.search(notes_text)
    if magasin_id_match:
        magasin_id_value = magasin_id_match.group(1)
        magasin_obj = magasins_by_id.get(magasin_id_value)
        if magasin_obj:
            return magasin_obj, magasin_obj.nom_magasin
        return None, 'Non ventilé (base)'

    magasin_name_match = MAGASIN_NAME_PATTERN.search(notes_text)
    if magasin_name_match:
        magasin_label = magasin_name_match.group(1).strip()
        magasin_obj = magasins_by_name.get(magasin_label.lower())
        if magasin_obj:
            return magasin_obj, magasin_obj.nom_magasin
        return None, magasin_label or 'Non ventilé (base)'

    return None, 'Non ventilé (base)'


def _parse_purchase_date_value(value, field_label, required=False):
    """Convertit une valeur JSON en objet date pour les achats."""
    if value in [None, '']:
        if required:
            raise ValueError(f'{field_label} invalide')
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if isinstance(value, str):
        try:
            return datetime.strptime(value, '%Y-%m-%d').date()
        except ValueError as exc:
            raise ValueError(f'{field_label} invalide') from exc

    raise ValueError(f'{field_label} invalide')


def _resolve_fiche_magasin_context(fiche, mapping_context):
    operation = fiche.operation_type

    if operation == 'achat' and fiche.purchase_id:
        magasin_obj = mapping_context['purchase_magasin_by_id'].get(str(fiche.purchase_id))
        if magasin_obj:
            return magasin_obj, magasin_obj.nom_magasin
    elif operation == 'transfert_sortie' and fiche.transfert_id:
        magasin_obj = mapping_context['transfert_sortie_magasin_by_id'].get(str(fiche.transfert_id))
        if magasin_obj:
            return magasin_obj, magasin_obj.nom_magasin
    elif operation == 'transfert_entree' and fiche.transfert_id:
        magasin_obj = mapping_context['transfert_entree_magasin_by_id'].get(str(fiche.transfert_id))
        if magasin_obj:
            return magasin_obj, magasin_obj.nom_magasin
    elif operation in ['livraison', 'retour_terrain']:
        notes_value = fiche.notes or ''
        bon_id_match = re.search(r'BonLivraison ID:\s*([0-9a-fA-F-]+)', notes_value)
        if bon_id_match:
            magasin_obj = mapping_context['bon_magasin_by_id'].get(bon_id_match.group(1))
            if magasin_obj:
                return magasin_obj, magasin_obj.nom_magasin
        if fiche.reference:
            magasin_obj = mapping_context['bon_magasin_by_num'].get((fiche.reference or '').strip())
            if magasin_obj:
                return magasin_obj, magasin_obj.nom_magasin

    return _extract_magasin_from_notes_value(
        fiche.notes or '',
        mapping_context['magasins_by_id'],
        mapping_context['magasins_by_name'],
    )


def _build_grand_livre_articles_rows(user, period_start, period_end, selected_base=None, selected_magasin=None, selected_type_id='', selected_designation_id=''):
    from apps.planning.models import BonLivraison, Planning
    from .models import Purchase, Transfert

    scoped_bases = _filter_bases_by_scope(Base.objects.all(), user)
    scoped_magasins = Magasin.objects.filter(base_id__in=scoped_bases.values('id')).select_related('base')
    if selected_base:
        scoped_magasins = scoped_magasins.filter(base_id=selected_base.id)
    if selected_magasin:
        scoped_magasins = scoped_magasins.filter(id=selected_magasin.id)

    magasins = list(scoped_magasins)
    magasins_by_id = {str(m.id): m for m in magasins}
    magasins_by_name = {(m.nom_magasin or '').strip().lower(): m for m in magasins if m.nom_magasin}

    purchase_qs = Purchase.objects.filter(base_id__in=scoped_bases.values('id')).select_related('magasin', 'ordered_by')
    if selected_base:
        purchase_qs = purchase_qs.filter(base_id=selected_base.id)
    purchase_magasin_by_id = {str(p.id): p.magasin for p in purchase_qs if p.magasin_id}
    purchase_by_id = {str(p.id): p for p in purchase_qs}

    transfert_qs = Transfert.objects.select_related(
        'magasin_origine',
        'magasin_destination',
        'initiated_by',
        'received_by',
    ).filter(
        Q(magasin_origine__base_id__in=scoped_bases.values('id')) |
        Q(magasin_destination__base_id__in=scoped_bases.values('id'))
    )
    if selected_base:
        transfert_qs = transfert_qs.filter(
            Q(magasin_origine__base_id=selected_base.id) |
            Q(magasin_destination__base_id=selected_base.id)
        )
    transfert_sortie_magasin_by_id = {str(t.id): t.magasin_origine for t in transfert_qs if t.magasin_origine_id}
    transfert_entree_magasin_by_id = {str(t.id): t.magasin_destination for t in transfert_qs if t.magasin_destination_id}
    transfert_by_id = {str(t.id): t for t in transfert_qs}

    plannings_scope = _filter_plannings_by_scope_inventory(Planning.objects.all(), user)
    bon_qs = BonLivraison.objects.filter(
        planning_id__in=plannings_scope.values('id')
    ).select_related(
        'planning__ouvrage',
        'planning__employe',
        'planning__fiche_poste',
        'planning__type_activite',
    ).only(
        'id',
        'numero_bon',
        'magasin',
        'planning__ouvrage__nom_ouvrage',
        'planning__employe__nom',
        'planning__employe__prenom',
        'planning__employe__surnom',
        'planning__employe__nom_employe',
        'planning__fiche_poste__tache',
        'planning__type_activite__nomtype',
        'planning__remarque',
    )
    bon_magasin_by_id = {}
    bon_magasin_by_num = {}
    bon_by_id = {}
    bon_by_num = {}
    for bon in bon_qs:
        magasin_value = (bon.magasin or '').strip()
        magasin_obj = None
        for magasin in magasins:
            if _match_magasin_label(magasin_value, magasin):
                magasin_obj = magasin
                break
        if magasin_obj:
            bon_magasin_by_id[str(bon.id)] = magasin_obj
            if bon.numero_bon:
                bon_magasin_by_num[bon.numero_bon.strip()] = magasin_obj
        bon_by_id[str(bon.id)] = bon
        if bon.numero_bon:
            bon_by_num[bon.numero_bon.strip()] = bon

    fiches_qs = FicheStock.objects.filter(
        designation__isnull=False,
        base_id__in=scoped_bases.values('id'),
        operation_date__date__lte=period_end,
    ).select_related(
        'designation',
        'designation__type_designation',
        'base',
        'employee',
    ).order_by('operation_date', 'created_at', 'id')

    if selected_base:
        fiches_qs = fiches_qs.filter(base_id=selected_base.id)
    if selected_type_id:
        fiches_qs = fiches_qs.filter(designation__type_designation_id=selected_type_id)
    if selected_designation_id:
        fiches_qs = fiches_qs.filter(designation_id=selected_designation_id)

    mapping_context = {
        'purchase_magasin_by_id': purchase_magasin_by_id,
        'purchase_by_id': purchase_by_id,
        'transfert_sortie_magasin_by_id': transfert_sortie_magasin_by_id,
        'transfert_entree_magasin_by_id': transfert_entree_magasin_by_id,
        'transfert_by_id': transfert_by_id,
        'bon_magasin_by_id': bon_magasin_by_id,
        'bon_magasin_by_num': bon_magasin_by_num,
        'bon_by_id': bon_by_id,
        'bon_by_num': bon_by_num,
        'magasins_by_id': magasins_by_id,
        'magasins_by_name': magasins_by_name,
    }

    stock_lookup = {
        (str(stock.base_id), str(stock.designation_id)): stock
        for stock in _filter_stocks_by_scope(
            Stock.objects.select_related('utilisateur').filter(
                base_id__in=scoped_bases.values('id'),
                designation__isnull=False,
            ),
            user
        )
    }

    groups = {}
    operation_labels = {
        'achat': 'Achat fournisseur',
        'livraison': 'Sortie terrain',
        'transfert_sortie': 'Transfert sortant',
        'transfert_entree': 'Transfert entrant',
        'retour_terrain': 'Retour terrain',
        'inventaire': 'Inventaire',
        'entree': 'Entrée manuelle',
        'sortie': 'Sortie manuelle',
        'ajustement': 'Ajustement',
    }
    positive_operations = {'achat', 'transfert_entree', 'retour_terrain', 'entree'}
    negative_operations = {'livraison', 'transfert_sortie', 'sortie'}

    def _employee_label(employe):
        if not employe:
            return '-'
        return getattr(employe, 'nom_affichage', None) or getattr(employe, 'nom_complet', None) or (
            getattr(employe, 'surnom', None)
            or getattr(employe, 'prenom', None)
            or getattr(employe, 'nom_employe', None)
            or str(employe)
        )

    def _movement_extra_context(fiche):
        ouvrage_nom = '-'
        initie_par = '-'
        recu_par = '-'
        observation_suffix = ''

        if fiche.operation_type == 'achat':
            purchase_key = str(fiche.purchase_id).strip() if fiche.purchase_id else ''
            purchase = mapping_context['purchase_by_id'].get(purchase_key)
            if purchase:
                initie_par = _employee_label(purchase.ordered_by)
            return ouvrage_nom, initie_par, recu_par, observation_suffix

        if fiche.operation_type in ['transfert_sortie', 'transfert_entree']:
            transfert_key = str(fiche.transfert_id).strip() if fiche.transfert_id else ''
            transfert = mapping_context['transfert_by_id'].get(transfert_key)
            if transfert:
                initie_par = _employee_label(transfert.initiated_by)
                recu_par = _employee_label(transfert.received_by)
            return ouvrage_nom, initie_par, recu_par, observation_suffix

        if fiche.operation_type in ['livraison', 'retour_terrain']:
            bon_id_match = re.search(r'BonLivraison ID:\s*([0-9a-fA-F-]+)', fiche.notes or '')
            bon = None
            if bon_id_match:
                bon = mapping_context['bon_by_id'].get(bon_id_match.group(1))
            if not bon and fiche.reference:
                bon = mapping_context['bon_by_num'].get((fiche.reference or '').strip())
            if bon and bon.planning_id:
                if bon.planning and bon.planning.ouvrage:
                    ouvrage_nom = bon.planning.ouvrage.nom_ouvrage or '-'
                planning_employe = bon.planning.employe if bon.planning else None
                recu_par = _employee_label(planning_employe)
                initie_par = _employee_label(fiche.employee if fiche.employee_id else planning_employe)
                planning_activity = ''
                if bon.planning:
                    if getattr(getattr(bon.planning, 'fiche_poste', None), 'tache', None):
                        planning_activity = str(bon.planning.fiche_poste.tache).strip()
                    elif getattr(getattr(bon.planning, 'type_activite', None), 'nomtype', None):
                        planning_activity = str(bon.planning.type_activite.nomtype).strip()
                planning_remark = str(getattr(bon.planning, 'remarque', '') or '').strip() if bon.planning else ''
                observation_parts = []
                if planning_activity:
                    observation_parts.append(f"Activite reparation: {planning_activity}")
                if planning_remark:
                    observation_parts.append(f"Remarque planning: {planning_remark}")
                observation_suffix = ' | '.join(observation_parts)
            else:
                initie_par = _employee_label(fiche.employee)
            return ouvrage_nom, initie_par, recu_par, observation_suffix

        initie_par = _employee_label(fiche.employee)
        return ouvrage_nom, initie_par, recu_par, observation_suffix

    def get_group(fiche, magasin_obj, magasin_nom):
        designation = fiche.designation
        base = fiche.base
        type_obj = designation.type_designation if designation else None
        key = (
            str(base.id),
            str(magasin_obj.id) if magasin_obj else f'label:{magasin_nom}',
            str(type_obj.id) if type_obj else 'sans-type',
            str(designation.id),
        )
        if key not in groups:
            stock_obj = stock_lookup.get((str(base.id), str(designation.id)))
            groups[key] = {
                'base': base,
                'magasin': magasin_obj,
                'magasin_nom': magasin_nom or 'Non ventilé (base)',
                'type_designation': type_obj,
                'designation': designation,
                'stock_record_id': str(stock_obj.id) if stock_obj else '',
                'stock_current_quantity': stock_obj.current_quantity if stock_obj else Decimal('0'),
                'stock_inventory_date': stock_obj.inventory_date if stock_obj else None,
                'stock_rapproche': bool(stock_obj.rapproche) if stock_obj else False,
                'stock_depart': Decimal('0'),
                'total_entrees': Decimal('0'),
                'total_sorties': Decimal('0'),
                'stock_final': Decimal('0'),
                'mouvements': [],
            }
        return groups[key]

    for fiche in fiches_qs:
        magasin_obj, magasin_nom = _resolve_fiche_magasin_context(fiche, mapping_context)
        if selected_magasin and (not magasin_obj or str(magasin_obj.id) != str(selected_magasin.id)):
            continue

        group = get_group(fiche, magasin_obj, magasin_nom)
        qty = Decimal(str(fiche.quantity or 0))
        movement_date = fiche.operation_date.date()

        if movement_date < period_start:
            if fiche.operation_type == 'inventaire':
                group['stock_depart'] = qty
            elif fiche.operation_type in positive_operations:
                group['stock_depart'] += qty
            elif fiche.operation_type in negative_operations:
                group['stock_depart'] -= qty
            elif fiche.operation_type == 'ajustement':
                group['stock_depart'] += qty
            continue

        entree = Decimal('0')
        sortie = Decimal('0')
        previous_stock = group['stock_depart'] if not group['mouvements'] else group['mouvements'][-1]['stock_cumule']

        if fiche.operation_type == 'inventaire':
            delta = qty - previous_stock
            if delta >= 0:
                entree = delta
            else:
                sortie = abs(delta)
        elif fiche.operation_type in positive_operations:
            entree = qty
        elif fiche.operation_type in negative_operations:
            sortie = qty
        elif fiche.operation_type == 'ajustement':
            if qty >= 0:
                entree = qty
            else:
                sortie = abs(qty)

        stock_cumule = previous_stock + entree - sortie
        ouvrage_nom, initie_par, recu_par, observation_suffix = _movement_extra_context(fiche)
        observation_value = str(fiche.notes or '').strip()
        if observation_suffix:
            observation_value = f"{observation_value} | {observation_suffix}" if observation_value else observation_suffix
        group['total_entrees'] += entree
        group['total_sorties'] += sortie
        group['mouvements'].append({
            'date': fiche.operation_date,
            'reference': fiche.reference or '-',
            'libelle': operation_labels.get(fiche.operation_type, fiche.get_operation_type_display()),
            'ouvrage': ouvrage_nom,
            'initie_par': initie_par,
            'recu_par': recu_par,
            'entree': entree,
            'sortie': sortie,
            'stock_cumule': stock_cumule,
            'observation': observation_value,
        })

    rows = []
    for group in groups.values():
        if group['stock_depart'] == 0 and not group['mouvements']:
            continue
        group['stock_final'] = group['mouvements'][-1]['stock_cumule'] if group['mouvements'] else group['stock_depart']
        group['stock_current_quantity'] = group['stock_final']
        rows.append(group)

    rows.sort(
        key=lambda item: (
            (item['base'].nom_base or '').lower(),
            (item['magasin_nom'] or '').lower(),
            (item['type_designation'].nom if item['type_designation'] else 'sans type').lower(),
            (item['designation'].nom or '').lower(),
        )
    )
    return rows


def _sync_bon_livraison_to_fiche_stock(bon):
    """
    Garantit qu'un BonLivraison livré existe dans la fiche de stock.
    Retourne la FicheStock créée ou existante (ou None si non synchronisable).
    """
    from .models import FicheStock

    if not bon or not bon.designation_id or not bon.quantite:
        return None

    base = _resolve_base_from_magasin_text(bon.magasin)
    if not base and bon.planning and bon.planning.employe and bon.planning.employe.base_id:
        base = bon.planning.employe.base
    if not base:
        return None

    operation_date = bon.date_utilisation or bon.created_at or timezone.now()
    bon_id_marker = f"BonLivraison ID: {bon.id}"

    existing_filters = Q(notes__icontains=bon_id_marker)
    bon_numero = (bon.numero_bon or '').strip()
    if bon_numero:
        existing_filters |= Q(reference=bon_numero) | Q(notes__icontains=bon_numero)

    current_planning = bon.planning
    current_employee = current_planning.employe if current_planning and current_planning.employe_id else None

    def _find_existing(operation_type):
        existing = FicheStock.objects.filter(
            operation_type=operation_type,
            designation_id=bon.designation_id,
            base=base
        ).filter(existing_filters).first()

        if not existing and bon_numero:
            existing = FicheStock.objects.filter(
                operation_type=operation_type,
                designation_id=bon.designation_id,
                base=base,
                quantity=bon.quantite,
                operation_date__date=operation_date.date()
            ).filter(
                Q(reference=bon_numero) | Q(notes__icontains=bon_numero)
            ).first()
        return existing

    def _ensure_bon_fiche(operation_type, libelle):
        existing = _find_existing(operation_type)
        payload = {
            'designation_id': bon.designation_id,
            'base': base,
            'employee': current_employee,
            'quantity': bon.quantite,
            'operation_type': operation_type,
            'operation_date': operation_date,
            'reference': bon_numero,
            'notes': f'{libelle} - BL {bon_numero or "N/A"} - BonLivraison ID: {bon.id}'
        }

        if existing:
            changed = False
            for field, value in payload.items():
                if getattr(existing, field) != value:
                    setattr(existing, field, value)
                    changed = True
            if changed:
                existing.save(update_fields=list(payload.keys()) + ['updated_at'])
            return existing

        return FicheStock.objects.create(**payload)

    # Supprimer les mouvements devenus invalides avant de re-synchroniser
    if not bon.utilise:
        FicheStock.objects.filter(existing_filters, designation_id=bon.designation_id, base=base, operation_type='livraison').delete()
        FicheStock.objects.filter(existing_filters, designation_id=bon.designation_id, base=base, operation_type='retour_terrain').delete()
        return None

    # Sortie terrain
    livraison_fiche = _ensure_bon_fiche('livraison', 'Livraison terrain')

    # Retour terrain = réintégration en stock uniquement si explicitement marqué comme retour
    if bon.retour:
        return_fiche = _ensure_bon_fiche('retour_terrain', 'Retour terrain')
    else:
        FicheStock.objects.filter(
            existing_filters,
            designation_id=bon.designation_id,
            base=base,
            operation_type='retour_terrain'
        ).delete()

    return livraison_fiche


def _resolve_purchase_base(purchase):
    """Retourne la base explicite de l'achat ou celle portée par le magasin."""
    if purchase and purchase.base_id:
        return purchase.base

    if purchase and purchase.magasin and purchase.magasin.base_id:
        return purchase.magasin.base

    return None


def _sync_purchase_to_fiche_stock(purchase):
    """
    Garantit qu'un achat livré/réceptionné existe dans la fiche de stock.
    Retourne la liste des lignes créées.
    """
    from .models import FicheStock

    if not purchase or purchase.purchase_status not in ['livre', 'recu']:
        return []

    base = _resolve_purchase_base(purchase)
    if not base:
        return []

    created_rows = []
    operation_date = purchase.actual_delivery_date or purchase.purchase_date
    if operation_date:
        if isinstance(operation_date, datetime):
            if timezone.is_aware(operation_date):
                operation_date = operation_date.astimezone(timezone.get_current_timezone())
            else:
                operation_date = timezone.make_aware(operation_date, timezone.get_current_timezone())
        else:
            operation_date = timezone.make_aware(
                datetime.combine(operation_date, datetime.min.time()),
                timezone.get_current_timezone()
            )
    else:
        operation_date = timezone.now()
    fournisseur_nom = ''
    if purchase.fournisseur:
        fournisseur_nom = purchase.fournisseur.nom_fournisseur
    elif purchase.supplier:
        fournisseur_nom = purchase.supplier.supplier_name

    purchase_items = purchase.purchase_items.select_related('designation').all()
    current_designation_ids = {
        item.designation_id
        for item in purchase_items
        if item.designation_id
    }
    stale_rows = FicheStock.objects.filter(
        operation_type='achat',
        purchase_id=str(purchase.id)
    )
    if current_designation_ids:
        stale_rows = stale_rows.exclude(designation_id__in=current_designation_ids)
    stale_rows.delete()

    for item in purchase_items:
        if not item.designation_id:
            continue

        quantity = item.quantity_received if item.quantity_received not in [None, 0] else item.quantity_ordered
        if quantity in [None, 0]:
            continue

        existing_rows = FicheStock.objects.filter(
            operation_type='achat',
            purchase_id=str(purchase.id),
            designation_id=item.designation_id
        ).order_by('created_at')
        existing = existing_rows.first()
        if existing:
            existing_rows.exclude(id=existing.id).delete()

        payload = {
            'operation_date': operation_date,
            'operation_type': 'achat',
            'quantity': quantity,
            'unit_price': item.unit_price,
            'purchase_id': str(purchase.id),
            'designation_id': item.designation_id,
            'base': base,
            'employee': purchase.ordered_by,
            'reference': purchase.purchase_number,
            'notes': f'Achat {purchase.purchase_number} - {fournisseur_nom or "N/A"}',
        }

        if existing:
            updates = []
            for field, value in payload.items():
                if getattr(existing, field) != value:
                    setattr(existing, field, value)
                    updates.append(field)
            if updates:
                existing.save(update_fields=updates + ['updated_at'])
            continue

        created_rows.append(FicheStock.objects.create(**payload))

    return created_rows


def _sync_purchase_stock_movement(purchase):
    """Synchronise les mouvements de stock générés par un achat réceptionné."""
    reference = f'Achat #{purchase.purchase_number}'
    existing_qs = StockMovement.objects.filter(
        movement_type='entree',
        reference=reference
    )

    if not purchase or purchase.purchase_status != 'recu':
        existing_qs.delete()
        return

    base = _resolve_purchase_base(purchase)
    if not base:
        return

    movement_date = purchase.actual_delivery_date or purchase.purchase_date
    if movement_date:
        movement_date = datetime.combine(movement_date, datetime.min.time())
    else:
        movement_date = timezone.now()

    current_designation_ids = set()
    for item in purchase.purchase_items.select_related('designation').all():
        if not item.designation_id:
            continue

        quantity = item.quantity_received if item.quantity_received not in [None, 0] else item.quantity_ordered
        if quantity in [None, 0]:
            continue

        current_designation_ids.add(item.designation_id)
        movement = existing_qs.filter(designation_id=item.designation_id).order_by('created_at').first()
        payload = {
            'designation_id': item.designation_id,
            'base': base,
            'movement_type': 'entree',
            'movement_date': movement_date,
            'quantity': quantity,
            'reference': reference,
            'notes': f'Réception achat {purchase.purchase_number}'
        }

        if movement:
            duplicates = existing_qs.filter(designation_id=item.designation_id).exclude(id=movement.id)
            duplicates.delete()
            updates = []
            for field, value in payload.items():
                if getattr(movement, field) != value:
                    setattr(movement, field, value)
                    updates.append(field)
            if updates:
                movement.save(update_fields=updates + ['updated_at'])
            continue

        StockMovement.objects.create(**payload)

    if current_designation_ids:
        existing_qs.exclude(designation_id__in=current_designation_ids).delete()
    else:
        existing_qs.delete()


def _rebuild_stock_from_fiche_stock(designation_id, base_id):
    """Recalcule le stock courant d'une désignation sur une base à partir de la fiche de stock."""
    if not designation_id or not base_id:
        return None

    fiches_qs = FicheStock.objects.filter(
        designation_id=designation_id,
        base_id=base_id
    ).order_by('operation_date', 'created_at')

    stock, _created = Stock.objects.get_or_create(
        designation_id=designation_id,
        base_id=base_id,
        defaults={'current_quantity': Decimal('0')}
    )

    quantity = Decimal('0')
    for fiche in fiches_qs:
        qty = Decimal(str(fiche.quantity or 0))
        if fiche.operation_type == 'inventaire':
            quantity = qty
        elif fiche.operation_type in ['achat', 'transfert_entree', 'entree', 'retour_terrain']:
            quantity += qty
        elif fiche.operation_type in ['livraison', 'transfert_sortie', 'sortie']:
            quantity -= qty
        elif fiche.operation_type == 'ajustement':
            quantity += qty

    if stock.current_quantity != quantity:
        stock.current_quantity = quantity
        stock.save(update_fields=['current_quantity', 'available_quantity', 'last_updated', 'updated_at'])

    return stock


def _sync_purchase_inventory(purchase, impacted_pairs=None):
    """Resynchronise les effets stock d'un achat après réception ou modification."""
    impacted_pairs = set(impacted_pairs or [])
    _sync_purchase_to_fiche_stock(purchase)
    _sync_purchase_stock_movement(purchase)

    base = _resolve_purchase_base(purchase)
    if base:
        impacted_pairs.update(
            (item.designation_id, base.id)
            for item in purchase.purchase_items.all()
            if item.designation_id
        )

    for designation_id, base_id in impacted_pairs:
        _rebuild_stock_from_fiche_stock(designation_id, base_id)


@login_required
def grand_livre_articles(request):
    from apps.planning.models import Designation, TypeDesignation

    today = timezone.localdate()
    annee = int(request.GET.get('annee') or today.year)
    mois = int(request.GET.get('mois') or today.month)
    base_id = (request.GET.get('base') or '').strip()
    magasin_id = (request.GET.get('magasin') or '').strip()
    type_designation_id = (request.GET.get('type_designation') or '').strip()
    designation_id = (request.GET.get('designation') or '').strip()

    period_start = date(annee, mois, 1)
    period_end = date(annee, mois, calendar.monthrange(annee, mois)[1])

    scoped_bases = _filter_bases_by_scope(Base.objects.all(), request.user).order_by('nom_base')
    selected_base = scoped_bases.filter(id=base_id).first() if base_id else None

    scoped_magasins = Magasin.objects.filter(base_id__in=scoped_bases.values('id')).select_related('base').order_by('base__nom_base', 'nom_magasin')
    if selected_base:
        scoped_magasins = scoped_magasins.filter(base_id=selected_base.id)
    selected_magasin = scoped_magasins.filter(id=magasin_id).first() if magasin_id else None

    types_designation = TypeDesignation.objects.filter(is_active=True).order_by('nom')
    designations = Designation.objects.filter(actif=True).select_related('type_designation').order_by('nom')
    if type_designation_id:
        designations = designations.filter(type_designation_id=type_designation_id)

    article_rows = _build_grand_livre_articles_rows(
        request.user,
        period_start,
        period_end,
        selected_base=selected_base,
        selected_magasin=selected_magasin,
        selected_type_id=type_designation_id,
        selected_designation_id=designation_id,
    )

    article_rows.sort(
        key=lambda item: (
            (item['base'].nom_base or '').lower(),
            (item['magasin_nom'] or '').lower(),
            (item['type_designation'].nom if item['type_designation'] else 'sans type').lower(),
            (item['designation'].nom or '').lower(),
        )
    )
    negative_stock_count = sum(1 for row in article_rows if (row.get('stock_final') or Decimal('0')) < 0)

    grouped_rows = []
    grouped_map = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for row in article_rows:
        type_nom = row['type_designation'].nom if row['type_designation'] else 'Sans type'
        grouped_map[row['base'].nom_base][row['magasin_nom']][type_nom].append(row)

    for base_nom, magasins_dict in grouped_map.items():
        magasins_list = []
        for magasin_nom, types_dict in magasins_dict.items():
            types_list = []
            for type_nom, rows in types_dict.items():
                types_list.append({'nom': type_nom, 'articles': rows})
            magasins_list.append({'nom': magasin_nom, 'types': types_list})
        grouped_rows.append({'base': base_nom, 'magasins': magasins_list})

    return render(request, 'inventory/grand_livre_articles.html', {
        'title': 'Grand livre des articles',
        'annee': annee,
        'mois': mois,
        'period_start': period_start,
        'period_end': period_end,
        'bases': scoped_bases,
        'magasins': scoped_magasins,
        'types_designation': types_designation,
        'designations': designations,
        'selected_base': base_id,
        'selected_magasin': magasin_id,
        'selected_type_designation': type_designation_id,
        'selected_designation': designation_id,
        'grouped_rows': grouped_rows,
        'article_count': len(article_rows),
        'negative_stock_count': negative_stock_count,
    })


def stock_dashboard(request):
    try:
        today = timezone.localdate()
        scoped_bases = _filter_bases_by_scope(Base.objects.all(), request.user)

        scoped_stocks = _filter_stocks_by_scope(
            Stock.objects.select_related('designation'),
            request.user
        ).filter(designation__isnull=False)

        total_products = scoped_stocks.values('designation_id').distinct().count()
        low_stock_items = scoped_stocks.filter(
            Q(available_quantity__lte=0) |
            Q(designation__seuil_minimum__isnull=False, available_quantity__lte=F('designation__seuil_minimum'))
        ).count()

        total_purchases_month = Purchase.objects.filter(
            purchase_date__year=today.year,
            purchase_date__month=today.month
        ).filter(
            Q(magasin__base_id__in=scoped_bases.values('id')) |
            Q(base_id__in=scoped_bases.values('id'))
        ).aggregate(total=Sum('total_amount'))['total'] or 0

        stock_movements_today = StockMovement.objects.filter(
            movement_date__date=today,
            base_id__in=scoped_bases.values('id')
        ).count()

        stats = {
            'total_products': total_products,
            'low_stock_items': low_stock_items,
            'total_purchases_month': total_purchases_month,
            'stock_movements_today': stock_movements_today,
        }
    except Exception:
        stats = {
            'total_products': 0,
            'low_stock_items': 0,
            'total_purchases_month': 0,
            'stock_movements_today': 0,
        }
    
    return render(request, 'inventory/dashboard.html', {
        'stats': stats,
        'title': 'Tableau de Bord - Stocks'
    })


@login_required
def products_list(request):
    search = (request.GET.get('search') or '').strip()
    base_id = (request.GET.get('base') or '').strip()

    scoped_bases = _filter_bases_by_scope(Base.objects.all(), request.user).order_by('nom_base')

    # Si l'utilisateur n'a qu'une seule base accessible, on verrouille ce filtre.
    if scoped_bases.count() == 1:
        base_id = str(scoped_bases.first().id)
    elif base_id and not scoped_bases.filter(id=base_id).exists():
        base_id = ''

    stocks = _filter_stocks_by_scope(
        Stock.objects.select_related('designation', 'designation__type_designation', 'base'),
        request.user
    ).filter(designation__isnull=False)

    if base_id:
        stocks = stocks.filter(base_id=base_id)
    if search:
        stocks = stocks.filter(
            Q(designation__nom__icontains=search) |
            Q(designation__code_materiel__icontains=search) |
            Q(designation__type_designation__nom__icontains=search)
        )

    from collections import OrderedDict
    products_map = OrderedDict()
    for stock in stocks.order_by('designation__nom', 'base__nom_base'):
        d = stock.designation
        if not d:
            continue
        key = str(d.id)
        if key not in products_map:
            products_map[key] = {
                'id': key,
                'code': d.code_materiel or str(d.id)[:8].upper(),
                'nom': d.nom,
                'categorie': d.type_designation.nom if d.type_designation else '-',
                'unite': d.unite or '-',
                'prix_unitaire': d.prix_unitaire or 0,
                'seuil_minimum': d.seuil_minimum,
                'stock_total': 0,
                'stock_disponible': 0,
                'stock_bases': 0,
                'actif': bool(d.actif),
            }
        products_map[key]['stock_total'] += float(stock.current_quantity or 0)
        products_map[key]['stock_disponible'] += float(stock.available_quantity or 0)
        products_map[key]['stock_bases'] += 1

    products = list(products_map.values())

    return render(request, 'inventory/products_list.html', {
        'products': products,
        'bases': scoped_bases,
        'single_base': scoped_bases.count() == 1,
        'filters': {
            'search': search,
            'base': base_id,
        },
        'title': 'Liste des Produits'
    })


@login_required
def stocks_list(request):
    from apps.employees.models import Employe
    from apps.planning.models import BonLivraison, Designation, Planning, TypeDesignation
    from .models import FicheStock, Transfert
    from decimal import Decimal
    from collections import defaultdict
    from types import SimpleNamespace

    # Recuperer les filtres
    search = request.GET.get('search', '')
    base_filter = request.GET.get('base', '')
    magasin_filter = request.GET.get('magasin', '')
    type_filter = request.GET.get('type_designation', '')
    view_mode = request.GET.get('view', 'table')
    page_number = request.GET.get('page', '1')
    print_mode = request.GET.get('print', '') == '1'
    if view_mode not in ['table', 'card']:
        view_mode = 'table'

    # Query de base
    scoped_stock_queryset = _filter_stocks_by_scope(
        Stock.objects.select_related(
            'designation',
            'designation__type_designation',
            'base',
            'utilisateur'
        ).all(),
        request.user
    )
    stocks = scoped_stock_queryset
    stocks = stocks.select_related(
        'designation',
        'designation__type_designation',
        'base',
        'utilisateur'
    ).all()

    scoped_bases = _filter_bases_by_scope(Base.objects.all(), request.user)
    scoped_magasins = Magasin.objects.select_related('base').filter(base_id__in=scoped_bases.values('id'))

    # Appliquer les filtres
    if search:
        stocks = stocks.filter(designation__nom__icontains=search)
    if base_filter:
        if scoped_bases.filter(id=base_filter).exists():
            stocks = stocks.filter(base_id=base_filter)
        else:
            base_filter = ''
    selected_magasin = None
    if magasin_filter:
        try:
            selected_magasin = scoped_magasins.get(id=magasin_filter)
            stocks = stocks.filter(base_id=selected_magasin.base_id)
        except Magasin.DoesNotExist:
            magasin_filter = ''
    if type_filter:
        stocks = stocks.filter(designation__type_designation_id=type_filter)

    stocks = list(stocks.order_by('base__nom_base', 'designation__type_designation__nom', 'designation__nom'))
    # Limiter l'index JS aux stocks affichables sur la page courante pour eviter
    # un HTML/JS inutilement massif qui peut figer l'interface.
    stocks_index_source = stocks

    # Index des stocks physiques par base + designation, utilise aussi en mode impression.
    stock_lookup = {}
    for stock in stocks:
        if not stock.designation_id:
            continue
        stock_lookup[(str(stock.base_id), str(stock.designation_id))] = stock

    plannings_scope = _filter_plannings_by_scope_inventory(
        Planning.objects.all(),
        request.user
    )

    # Afficher uniquement les inventaires physiques (sans calcul des mouvements).
    magasins_by_id = {str(m.id): m for m in scoped_magasins}
    magasins_by_name = {
        (m.nom_magasin or '').strip().lower(): m
        for m in scoped_magasins
        if m.nom_magasin
    }
    magasin_id_pattern = re.compile(
        r'Magasin ID\s*:\s*([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})'
    )
    magasin_name_pattern = re.compile(r'Magasin\s*:\s*([^|]+)')

    def _extract_magasin_from_notes(notes_value):
        if not notes_value:
            return '', 'Non ventilé (base)'

        notes_text = str(notes_value)

        magasin_id_match = magasin_id_pattern.search(notes_text)
        if magasin_id_match:
            magasin_id_value = magasin_id_match.group(1)
            magasin_obj = magasins_by_id.get(magasin_id_value)
            if magasin_obj:
                return magasin_id_value, magasin_obj.nom_magasin
            return magasin_id_value, 'Non ventilé (base)'

        magasin_name_match = magasin_name_pattern.search(notes_text)
        if magasin_name_match:
            magasin_label = magasin_name_match.group(1).strip()
            magasin_obj = magasins_by_name.get(magasin_label.lower())
            if magasin_obj:
                return str(magasin_obj.id), magasin_obj.nom_magasin
            return '', magasin_label or 'Non ventilé (base)'

        return '', 'Non ventilé (base)'

    inventaires_qs = FicheStock.objects.filter(
        operation_type__in=['inventaire', 'ajustement'],
        designation__isnull=False,
        base_id__in=scoped_bases.values('id')
    ).select_related(
        'designation',
        'designation__type_designation',
        'base',
        'employee'
    )

    if search:
        inventaires_qs = inventaires_qs.filter(designation__nom__icontains=search)
    if base_filter:
        inventaires_qs = inventaires_qs.filter(base_id=base_filter)
    if type_filter:
        inventaires_qs = inventaires_qs.filter(designation__type_designation_id=type_filter)
    if selected_magasin:
        inventaires_qs = inventaires_qs.filter(
            Q(notes__icontains=f"Magasin ID: {selected_magasin.id}") |
            Q(notes__icontains=f"Magasin: {selected_magasin.nom_magasin}")
        )

    latest_magasin_markers = {}
    fiches_with_magasin_qs = FicheStock.objects.filter(
        designation__isnull=False,
        base_id__in=scoped_bases.values('id')
    ).filter(
        Q(notes__icontains='Magasin ID:') |
        Q(notes__icontains='Magasin:')
    ).select_related('designation', 'base').order_by('-operation_date', '-created_at')

    if search:
        fiches_with_magasin_qs = fiches_with_magasin_qs.filter(designation__nom__icontains=search)
    if base_filter:
        fiches_with_magasin_qs = fiches_with_magasin_qs.filter(base_id=base_filter)
    if type_filter:
        fiches_with_magasin_qs = fiches_with_magasin_qs.filter(designation__type_designation_id=type_filter)
    if selected_magasin:
        fiches_with_magasin_qs = fiches_with_magasin_qs.filter(
            Q(notes__icontains=f"Magasin ID: {selected_magasin.id}") |
            Q(notes__icontains=f"Magasin: {selected_magasin.nom_magasin}")
        )

    for fiche in fiches_with_magasin_qs:
        if not fiche.designation_id:
            continue
        fallback_magasin_uuid, fallback_magasin_label = _extract_magasin_from_notes(fiche.notes or '')
        if not fallback_magasin_uuid and not fallback_magasin_label:
            continue
        fallback_key = (str(fiche.base_id), str(fiche.designation_id))
        if fallback_key not in latest_magasin_markers:
            latest_magasin_markers[fallback_key] = (fallback_magasin_uuid, fallback_magasin_label)

    latest_stock_snapshots = {}
    for fiche in inventaires_qs.order_by('-operation_date', '-created_at'):
        if not fiche.designation_id:
            continue
        designation_nature = getattr(fiche.designation, 'nature_stock', 'consommable') or 'consommable'

        magasin_uuid, magasin_label = _extract_magasin_from_notes(fiche.notes or '')
        if not magasin_uuid and (not magasin_label or magasin_label == 'Non ventilé (base)'):
            magasin_uuid, magasin_label = latest_magasin_markers.get(
                (str(fiche.base_id), str(fiche.designation_id)),
                (magasin_uuid, magasin_label)
            )
        if selected_magasin:
            if magasin_uuid and magasin_uuid != str(selected_magasin.id):
                continue
            if not magasin_uuid and (magasin_label or '').strip().lower() != (selected_magasin.nom_magasin or '').strip().lower():
                continue
            magasin_uuid = str(selected_magasin.id)
            magasin_label = selected_magasin.nom_magasin

        if designation_nature == 'non_consommable':
            key = (str(fiche.base_id), str(fiche.designation_id), '__non_consommable__')
        else:
            key = (str(fiche.base_id), str(fiche.designation_id), magasin_uuid or magasin_label)
        if key in latest_stock_snapshots:
            continue
        latest_stock_snapshots[key] = (fiche, magasin_uuid, magasin_label)

    visible_designation_ids = {
        str(fiche.designation_id)
        for fiche, _magasin_uuid, _magasin_label in latest_stock_snapshots.values()
        if fiche.designation_id
    }
    strict_stock_cache = {}

    def _get_strict_magasin_cache(magasin_uuid):
        if not magasin_uuid:
            return None
        magasin_uuid = str(magasin_uuid)
        magasin_obj = magasins_by_id.get(magasin_uuid)
        if not magasin_obj:
            return None
        if magasin_uuid not in strict_stock_cache:
            try:
                strict_stock_cache[magasin_uuid] = _compute_strict_stock_for_magasin(
                    request.user,
                    magasin_obj,
                    visible_designation_ids
                )
            except Exception:
                strict_stock_cache[magasin_uuid] = None
        return strict_stock_cache[magasin_uuid]

    projected_stocks = []
    for fiche, magasin_uuid, magasin_label in latest_stock_snapshots.values():
        base_key = str(fiche.base_id)
        designation_key = str(fiche.designation_id)
        base_stock = stock_lookup.get((base_key, designation_key))
        qty = Decimal(str(
            base_stock.current_quantity if base_stock is not None else (fiche.quantity or 0)
        ))
        designation_nature = getattr(fiche.designation, 'nature_stock', 'consommable') or 'consommable'
        # Pour un inventaire cible par magasin, la quantite saisie dans la fiche
        # est la source de verite la plus fiable pour l'affichage.
        if magasin_uuid and fiche.operation_type == 'inventaire':
            qty = Decimal(str(fiche.quantity or 0))
        strict_magasin_cache = _get_strict_magasin_cache(magasin_uuid)
        strict_inventory_dates = {}
        if strict_magasin_cache is not None and not (magasin_uuid and fiche.operation_type == 'inventaire'):
            try:
                strict_quantities, strict_inventory_dates, strict_has_movement = strict_magasin_cache
                if strict_has_movement.get(designation_key):
                    qty = Decimal(str(strict_quantities.get(designation_key, 0) or 0))
            except Exception:
                strict_inventory_dates = {}
        reserved_qty = Decimal('0')
        if designation_nature == 'consommable':
            reserved_qty = Decimal(str(
                fiche.designation.seuil_minimum
                if getattr(fiche.designation, 'seuil_minimum', None) is not None
                else (base_stock.reserved_quantity if base_stock is not None else 0)
            ))
        available_qty = qty - reserved_qty
        rapproche_value = bool(base_stock.rapproche) if base_stock else True
        utilisateur_value = base_stock.utilisateur if base_stock and base_stock.utilisateur else fiche.employee

        display_inventory_date = None
        if magasin_uuid and fiche.operation_type == 'inventaire' and fiche.operation_date:
            display_inventory_date = fiche.operation_date.date()
        elif strict_magasin_cache is not None and strict_inventory_dates.get(designation_key):
            display_inventory_date = strict_inventory_dates.get(designation_key)
        elif base_stock and getattr(base_stock, 'inventory_date', None):
            display_inventory_date = base_stock.inventory_date
        elif fiche.operation_date:
            display_inventory_date = fiche.operation_date.date()

        projected_stocks.append(SimpleNamespace(
            id=str(base_stock.id) if base_stock else '',
            fiche_id=str(fiche.id),
            fiche_operation_type=fiche.operation_type,
            designation=fiche.designation,
            base=fiche.base,
            base_id=fiche.base_id,
            magasin_nom=magasin_label or 'Non ventilé (base)',
            magasin_id=magasin_uuid or '',
            current_quantity=qty,
            reserved_quantity=reserved_qty,
            available_quantity=available_qty,
            inventory_date=display_inventory_date,
            rapproche=rapproche_value,
            etat=(base_stock.etat if base_stock and getattr(base_stock, 'etat', None) else 'bon'),
            photo=(base_stock.photo if base_stock and getattr(base_stock, 'photo', None) else None),
            utilisateur=utilisateur_value,
            nature_stock=designation_nature,
        ))

    # Fallback: si aucun inventaire en fiche, afficher les valeurs physiques du stock
    # pour éviter un tableau vide après import ancien format.
    if not projected_stocks:
        for stock in stocks:
            if not stock.inventory_date:
                continue
            marker_magasin_uuid = ''
            marker_magasin_label = ''
            marker_key = (str(stock.base_id), str(stock.designation_id))
            if marker_key in latest_magasin_markers:
                marker_magasin_uuid, marker_magasin_label = latest_magasin_markers[marker_key]
            if selected_magasin:
                selected_magasin_id = str(selected_magasin.id)
                selected_magasin_name = (selected_magasin.nom_magasin or '').strip().lower()
                marker_name_normalized = (marker_magasin_label or '').strip().lower()
                if marker_magasin_uuid:
                    if marker_magasin_uuid != selected_magasin_id:
                        continue
                elif marker_name_normalized != selected_magasin_name:
                    continue
            fallback_magasin_nom = 'Non ventilé (base)'
            fallback_magasin_id = ''
            if marker_magasin_uuid or marker_magasin_label:
                fallback_magasin_nom = marker_magasin_label or 'Non ventilé (base)'
                fallback_magasin_id = marker_magasin_uuid or ''
            elif selected_magasin:
                fallback_magasin_nom = selected_magasin.nom_magasin
                fallback_magasin_id = str(selected_magasin.id)
            designation_nature = getattr(stock.designation, 'nature_stock', 'consommable') or 'consommable'
            reserved_qty = Decimal('0')
            if designation_nature == 'consommable':
                reserved_qty = Decimal(str(
                    stock.designation.seuil_minimum
                    if getattr(stock.designation, 'seuil_minimum', None) is not None
                    else (stock.reserved_quantity or 0)
                ))
            projected_stocks.append(SimpleNamespace(
                id=str(stock.id),
                fiche_id='',
                fiche_operation_type='',
                designation=stock.designation,
                base=stock.base,
                base_id=stock.base_id,
                magasin_nom=fallback_magasin_nom,
                magasin_id=fallback_magasin_id,
                current_quantity=Decimal(str(stock.current_quantity or 0)),
                reserved_quantity=reserved_qty,
                available_quantity=Decimal(str(stock.current_quantity or 0)) - reserved_qty,
                inventory_date=stock.inventory_date,
                rapproche=bool(stock.rapproche),
                etat=stock.etat or 'bon',
                photo=stock.photo,
                utilisateur=stock.utilisateur,
                nature_stock=designation_nature,
            ))

    projected_stocks.sort(
        key=lambda stock: (
            (stock.base.nom_base or '').lower(),
            (getattr(stock, 'magasin_nom', '') or '').lower(),
            (stock.designation.type_designation.nom if stock.designation and stock.designation.type_designation else 'sans type').lower(),
            (stock.designation.nom or '').lower(),
        )
    )
    magasins = list(scoped_magasins.order_by('base__nom_base', 'nom_magasin'))
    magasins_by_base = defaultdict(list)
    for magasin in magasins:
        magasins_by_base[magasin.base_id].append(magasin)

    def _group_projected_stocks(stocks_subset):
        grouped_stocks = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        for stock in stocks_subset:
            base_key = stock.base.nom_base
            base_magasins = magasins_by_base.get(stock.base_id, [])
            magasin_nom_projete = getattr(stock, 'magasin_nom', None)
            magasin_id_projete = str(getattr(stock, 'magasin_id', '') or '')
            if selected_magasin:
                selected_magasin_id = str(selected_magasin.id)
                selected_magasin_name = (selected_magasin.nom_magasin or '').strip().lower()
                projected_magasin_name = (magasin_nom_projete or '').strip().lower()
                if magasin_id_projete:
                    if magasin_id_projete != selected_magasin_id:
                        continue
                elif projected_magasin_name != selected_magasin_name:
                    continue
            if magasin_nom_projete:
                magasin_key = magasin_nom_projete
            elif magasin_filter:
                magasin_obj = next((m for m in base_magasins if str(m.id) == magasin_filter), None)
                magasin_key = magasin_obj.nom_magasin if magasin_obj else 'Sans magasin'
            elif len(base_magasins) == 1:
                magasin_key = base_magasins[0].nom_magasin
            elif len(base_magasins) > 1:
                magasin_key = 'Tous les magasins'
            else:
                magasin_key = 'Sans magasin'

            type_key = stock.designation.type_designation.nom if stock.designation and stock.designation.type_designation else 'Sans type'
            grouped_stocks[base_key][magasin_key][type_key].append(stock)

        grouped_result = []
        for base_nom, magasins_dict in grouped_stocks.items():
            magasins_list = []
            for magasin_nom, types_dict in magasins_dict.items():
                magasin_id = ''
                for stocks_list in types_dict.values():
                    for stock in stocks_list:
                        magasin_id = str(getattr(stock, 'magasin_id', '') or '')
                        if magasin_id:
                            break
                    if magasin_id:
                        break
                types_list = []
                for type_nom, stocks_list in types_dict.items():
                    types_list.append({
                        'nom': type_nom,
                        'stocks': stocks_list,
                        'count': len(stocks_list)
                    })
                magasins_list.append({
                    'id': magasin_id,
                    'nom': magasin_nom,
                    'types': types_list,
                    'total_count': sum(t['count'] for t in types_list)
                })
            grouped_result.append({
                'base': base_nom,
                'magasins': magasins_list,
                'total_count': sum(m['total_count'] for m in magasins_list)
            })
        return grouped_result

    def _group_printable_stocks(stocks_subset):
        grouped_stocks = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(list))))
        latest_inventory_date = None

        for stock in stocks_subset:
            quantity_value = Decimal(str(getattr(stock, 'current_quantity', 0) or 0))
            if quantity_value == Decimal('0'):
                continue

            if selected_magasin:
                selected_magasin_id = str(selected_magasin.id)
                selected_magasin_name = (selected_magasin.nom_magasin or '').strip().lower()
                stock_magasin_id = str(getattr(stock, 'magasin_id', '') or '')
                stock_magasin_name = (getattr(stock, 'magasin_nom', '') or '').strip().lower()
                if stock_magasin_id:
                    if stock_magasin_id != selected_magasin_id:
                        continue
                elif stock_magasin_name != selected_magasin_name:
                    continue

            base_key = stock.base.nom_base
            magasin_key = getattr(stock, 'magasin_nom', None) or 'Sans magasin'
            nature_key = 'Non consommable' if getattr(stock, 'nature_stock', '') == 'non_consommable' else 'Consommable'
            category_key = (
                stock.designation.type_designation.nom
                if getattr(stock.designation, 'type_designation', None)
                else 'Sans categorie'
            )
            grouped_stocks[base_key][magasin_key][nature_key][category_key].append(stock)

            inventory_date = getattr(stock, 'inventory_date', None)
            if inventory_date and (latest_inventory_date is None or inventory_date > latest_inventory_date):
                latest_inventory_date = inventory_date

        grouped_result = []
        for base_nom, magasins_dict in grouped_stocks.items():
            magasins_list = []
            for magasin_nom, nature_dict in magasins_dict.items():
                nature_list = []
                for nature_nom in ['Consommable', 'Non consommable']:
                    category_dict = nature_dict.get(nature_nom, {})
                    if not category_dict:
                        continue
                    categories_list = []
                    for category_nom, stocks_list in sorted(category_dict.items(), key=lambda item: (item[0] or '').lower()):
                        stocks_list = sorted(
                            stocks_list,
                            key=lambda item: (
                                (item.designation.nom or '').lower(),
                                (item.designation.unite or '').lower(),
                            )
                        )
                        categories_list.append({
                            'nom': category_nom,
                            'stocks': stocks_list,
                            'count': len(stocks_list),
                        })
                    nature_list.append({
                        'nom': nature_nom,
                        'categories': categories_list,
                        'count': sum(item['count'] for item in categories_list),
                    })
                if nature_list:
                    magasins_list.append({
                        'nom': magasin_nom,
                        'natures': nature_list,
                        'total_count': sum(item['count'] for item in nature_list),
                    })
            if magasins_list:
                grouped_result.append({
                    'base': base_nom,
                    'magasins': magasins_list,
                    'total_count': sum(item['total_count'] for item in magasins_list),
                })

        return grouped_result, latest_inventory_date

    if print_mode:
        printable_grouped_stocks, latest_inventory_date = _group_printable_stocks(projected_stocks)
        return render(request, 'inventory/print_latest_stock.html', {
            'stocks_grouped': printable_grouped_stocks,
            'selected_magasin': selected_magasin,
            'latest_inventory_date': latest_inventory_date,
            'filters': {
                'search': search,
                'base': base_filter,
                'magasin': magasin_filter,
                'type_designation': type_filter,
            },
            'printed_at': timezone.localtime(),
        })

    paginator = Paginator(projected_stocks, 25)
    page_obj = paginator.get_page(page_number)
    stocks = list(page_obj.object_list)
    stocks_grouped = _group_projected_stocks(stocks)

    employes = _filter_employes_by_scope(
        Employe.objects.filter(date_debauchage__isnull=True),
        request.user
    ).order_by('surnom')
    bases = scoped_bases.order_by('nom_base')
    magasins = scoped_magasins.order_by('base__nom_base', 'nom_magasin')
    types_designation = TypeDesignation.objects.filter(is_active=True).order_by('nom')
    designations = Designation.objects.filter(
        actif=True
    ).filter(
        Q(type_avance_caissiere='bon_livraison') |
        Q(type_avance_caissiere__iexact='Bon de livraison')
    ).order_by('nom')

    pagination_query = urlencode({
        'search': search,
        'base': base_filter,
        'magasin': magasin_filter,
        'type_designation': type_filter,
        'view': view_mode,
    })

    return render(request, 'inventory/stocks_list.html', {
        'stocks': stocks,
        'stocks_index_source': stocks_index_source,
        'stocks_grouped': stocks_grouped,
        'page_obj': page_obj,
        'paginator': paginator,
        'pagination_query': pagination_query,
        'employes': employes,
        'bases': bases,
        'magasins': magasins,
        'designations': designations,
        'types_designation': types_designation,
        'can_delete_fiche_rows': _can_delete_fiche_stock_rows(request.user),
        'filters': {
            'search': search,
            'base': base_filter,
            'magasin': magasin_filter,
            'type_designation': type_filter,
            'view': view_mode,
        },
        'title': 'Etat des Stocks'
    })


@login_required
def api_stock_inventory_history(request):
    from apps.planning.models import Designation

    designation_id = request.GET.get('designation_id', '').strip()
    base_id = request.GET.get('base_id', '').strip()
    magasin_id = request.GET.get('magasin_id', '').strip()

    if not designation_id or not base_id:
        return JsonResponse({
            'success': False,
            'error': 'designation_id et base_id sont requis.'
        }, status=400)

    scoped_bases = _filter_bases_by_scope(Base.objects.all(), request.user)
    if not scoped_bases.filter(id=base_id).exists():
        return JsonResponse({
            'success': False,
            'error': 'Base introuvable ou non autorisée.'
        }, status=403)

    scoped_magasins = Magasin.objects.select_related('base').filter(base_id__in=scoped_bases.values('id'))
    selected_magasin = None
    if magasin_id:
        try:
            selected_magasin = scoped_magasins.get(id=magasin_id)
        except Magasin.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Magasin introuvable ou non autorisé.'
            }, status=404)

    try:
        designation = Designation.objects.get(id=designation_id)
        base = scoped_bases.get(id=base_id)
    except Designation.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Désignation introuvable.'}, status=404)
    except Base.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Base introuvable.'}, status=404)

    magasins_map = {str(m.id): m.nom_magasin for m in scoped_magasins}
    magasins_name_lookup = {
        (m.nom_magasin or '').strip().lower(): m.nom_magasin
        for m in scoped_magasins
        if m.nom_magasin
    }
    base_name_normalized = (base.nom_base or '').strip().lower()
    base_name_with_prefix = f"base {base_name_normalized}" if base_name_normalized else ''

    def _normalize_magasin_display(raw_value):
        if selected_magasin:
            return selected_magasin.nom_magasin
        if not raw_value:
            return 'Non ventilé (base)'

        value = str(raw_value).strip()
        if not value:
            return 'Non ventilé (base)'

        try:
            value_uuid = str(uuid.UUID(value))
            if value_uuid in magasins_map:
                return magasins_map[value_uuid]
        except (ValueError, TypeError):
            pass

        normalized = value.lower().strip()
        if normalized.startswith('base '):
            normalized = normalized[5:].strip()

        if normalized in magasins_name_lookup:
            return magasins_name_lookup[normalized]
        if base_name_normalized and normalized == base_name_normalized:
            return 'Non ventilé (base)'
        if base_name_with_prefix and normalized == base_name_with_prefix:
            return 'Non ventilé (base)'

        return 'Non ventilé (base)'

    def _extract_inventaire_magasin(notes_value):
        if selected_magasin:
            return selected_magasin.nom_magasin
        if not notes_value:
            return 'Non ventilé (base)'

        magasin_id_match = re.search(
            r'Magasin ID\s*:\s*([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})',
            notes_value
        )
        if magasin_id_match:
            magasin_nom = magasins_map.get(magasin_id_match.group(1))
            if magasin_nom:
                return magasin_nom

        magasin_nom_match = re.search(r'Magasin\s*:\s*([^|]+)', notes_value)
        if magasin_nom_match:
            magasin_nom = magasin_nom_match.group(1).strip()
            if magasin_nom:
                return _normalize_magasin_display(magasin_nom)

        return 'Non ventilé (base)'

    inventaires_qs = FicheStock.objects.filter(
        designation_id=designation_id,
        base_id=base_id,
        operation_type='inventaire'
    ).select_related('employee').order_by('-operation_date', '-created_at')

    if selected_magasin:
        inventaires_qs = inventaires_qs.filter(
            Q(notes__icontains=f"Magasin ID: {selected_magasin.id}") |
            Q(notes__icontains=f"Magasin: {selected_magasin.nom_magasin}")
        )

    rows = []
    for inv in inventaires_qs[:50]:
        quantity_value = Decimal(str(inv.quantity or 0))
        rows.append({
            'id': str(inv.id),
            'date': inv.operation_date.strftime('%d/%m/%Y %H:%M') if inv.operation_date else '-',
            'quantity': float(quantity_value),
            'quantity_display': f'{quantity_value:.2f}',
            'employee': inv.employee.nom_complet if inv.employee else '-',
            'reference': inv.reference or '-',
            'magasin': _extract_inventaire_magasin(inv.notes or ''),
            'notes': inv.notes or '-',
        })

    return JsonResponse({
        'success': True,
        'designation': designation.nom,
        'base': base.nom_base,
        'magasin': selected_magasin.nom_magasin if selected_magasin else '',
        'inventaires': rows,
    })


@login_required
def purchases_list(request):
    purchases = Purchase.objects.select_related(
        'supplier', 'fournisseur', 'base', 'ordered_by'
    ).prefetch_related(
        Prefetch('purchase_items', queryset=PurchaseItem.objects.select_related('designation'))
    ).order_by('-purchase_date')

    # Appliquer les filtres si présents
    magasin_id = request.GET.get('magasin')
    fournisseur_id = request.GET.get('fournisseur')
    statut = request.GET.get('statut')

    if magasin_id:
        purchases = purchases.filter(base_id=magasin_id)
    if fournisseur_id:
        purchases = purchases.filter(fournisseur_id=fournisseur_id)
    if statut:
        purchases = purchases.filter(purchase_status=statut)

    bases = Base.objects.all().order_by('nom_base')
    magasins = Magasin.objects.all().order_by('nom_magasin')
    fournisseurs = Fournisseur.objects.filter(actif=True).order_by('nom_fournisseur')
    from apps.planning.models import Designation
    from apps.organization.models import Compte
    designations = Designation.objects.order_by('nom')
    employees = Employe.objects.filter(date_debauchage__isnull=True).order_by('nom_employe')
    comptes = Compte.objects.filter(achat=True).order_by('nom_compte')

    # Sérialiser les désignations pour JavaScript
    designations_json = json.dumps([{
        'id': str(d.id),
        'designation_name': d.nom,
        'unit': d.unite or '',
        'unit_price': float(d.prix_unitaire) if d.prix_unitaire else 0
    } for d in designations])

    return render(request, 'inventory/purchases_list.html', {
        'purchases': purchases,
        'fournisseurs': fournisseurs,
        'bases': bases,
        'magasins': magasins,
        'designations': designations,
        'designations_json': designations_json,
        'employees': employees,
        'comptes': comptes,
        'title': 'Liste des Achats'
    })


@login_required
def purchases_consolidated(request):
    """Vue consolidée des achats par désignation avec filtres"""
    from apps.planning.models import Designation
    from django.db.models import Sum, Count, Q, Min, Max
    from collections import defaultdict

    scoped_bases = _filter_bases_by_scope(Base.objects.all(), request.user)

    # Récupérer tous les items d'achat avec relations (cloisonnés)
    items = PurchaseItem.objects.select_related(
        'designation',
        'designation__type_designation',
        'purchase__fournisseur',
        'purchase__supplier',
        'purchase__base',
        'purchase__magasin__base'
    ).filter(
        Q(purchase__magasin__base_id__in=scoped_bases.values('id')) |
        Q(purchase__base_id__in=scoped_bases.values('id'))
    )

    # Filtres
    designation_search = request.GET.get('designation_search', '').strip()
    fournisseur_id = request.GET.get('fournisseur')
    magasin_id = request.GET.get('magasin')
    date_debut = request.GET.get('date_debut')
    date_fin = request.GET.get('date_fin')

    # Filtre par recherche de désignation (nom contient)
    if designation_search:
        items = items.filter(designation__nom__icontains=designation_search)
    if fournisseur_id:
        items = items.filter(Q(purchase__fournisseur_id=fournisseur_id) | Q(purchase__supplier_id=fournisseur_id))
    scoped_magasins = Magasin.objects.filter(base_id__in=scoped_bases.values('id'))
    if magasin_id:
        if scoped_magasins.filter(id=magasin_id).exists():
            items = items.filter(
                Q(purchase__magasin_id=magasin_id) |
                Q(purchase__base_id=magasin_id)
            )
        else:
            magasin_id = ''
    if date_debut:
        items = items.filter(purchase__purchase_date__gte=date_debut)
    if date_fin:
        items = items.filter(purchase__purchase_date__lte=date_fin)

    # Grouper par désignation avec type, dates et magasin
    consolidated = items.values(
        'designation__id',
        'designation__nom',
        'designation__unite',
        'designation__type_designation__nom',
        'purchase__base__id',
        'purchase__base__nom_base',
        'purchase__magasin__id',
        'purchase__magasin__nom_magasin',
        'purchase__magasin__base__id',
        'purchase__magasin__base__nom_base',
    ).annotate(
        total_quantite_commandee=Sum('quantity_ordered'),
        total_quantite_recue=Sum('quantity_received'),
        total_montant=Sum('total_price'),
        nombre_achats=Count('purchase', distinct=True),
        date_premier_achat=Min('purchase__purchase_date'),
        date_dernier_achat=Max('purchase__purchase_date')
    ).order_by(
        'purchase__magasin__base__nom_base',
        'purchase__base__nom_base',
        'designation__type_designation__nom',
        'designation__nom'
    )

    # Grouper par magasin puis par type de désignation
    consolidated_by_magasin = defaultdict(lambda: defaultdict(list))
    for item in consolidated:
        magasin_nom = (
            item.get('purchase__magasin__base__nom_base')
            or item.get('purchase__base__nom_base')
            or 'Sans magasin'
        )
        type_nom = item['designation__type_designation__nom'] or 'Sans type'
        consolidated_by_magasin[magasin_nom][type_nom].append(item)

    # Convertir en liste triée pour le template
    consolidated_grouped = []
    for magasin_nom in sorted(consolidated_by_magasin.keys()):
        types_dict = consolidated_by_magasin[magasin_nom]
        types_list = sorted(types_dict.items())
        consolidated_grouped.append((magasin_nom, types_list))

    # Pour les filtres
    fournisseurs = Fournisseur.objects.filter(
        actif=True,
        id__in=items.values_list('purchase__fournisseur_id', flat=True)
    ).order_by('nom_fournisseur')
    magasins = scoped_magasins.order_by('nom_magasin')

    context = {
        'consolidated': consolidated,  # Pour les statistiques globales
        'consolidated_grouped': consolidated_grouped,  # Groupé par type
        'fournisseurs': fournisseurs,
        'magasins': magasins,
        'title': 'Achats Consolidés',
        # Conserver les filtres appliqués
        'filter_designation_search': designation_search,
        'filter_fournisseur': fournisseur_id,
        'filter_magasin': magasin_id,
        'filter_date_debut': date_debut,
        'filter_date_fin': date_fin,
    }

    return render(request, 'inventory/purchases_consolidated.html', context)


@require_http_methods(["GET"])
def api_designations_autocomplete(request):
    """API pour l'autocomplétion des désignations"""
    from apps.planning.models import Designation

    query = request.GET.get('q', '').strip()

    if not query or len(query) < 2:
        return JsonResponse({'results': []})

    # Rechercher les désignations dont le nom contient la requàªte
    designations = Designation.objects.filter(
        nom__icontains=query,
        actif=True
    ).order_by('nom')[:20]

    results = [
        {
            'id': str(d.id),
            'text': d.nom,
            'unite': d.unite or '',
            'type': d.type_designation.nom if d.type_designation else ''
        }
        for d in designations
    ]

    return JsonResponse({'results': results})


@require_http_methods(["GET"])
def api_comptes_by_magasin(request, magasin_id):
    """API pour récupérer les comptes d'achat liés à  l'organisation du magasin"""
    from apps.organization.models import Magasin, Compte

    try:
        magasin = Magasin.objects.select_related('base__organisation').get(id=magasin_id)
        organisation = magasin.base.organisation

        # Récupérer les comptes d'achat de cette organisation
        comptes = Compte.objects.filter(
            organisation=organisation,
            achat=True
        ).order_by('nom_compte')

        results = [
            {
                'id': str(c.id),
                'compte': c.compte or '',
                'nom_compte': c.nom_compte
            }
            for c in comptes
        ]

        return JsonResponse({'success': True, 'comptes': results})

    except Magasin.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Magasin introuvable'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def purchase_create(request):
    """Créer un nouvel achat"""
    try:
        data = json.loads(request.body)
        items_data = data.get('items') or []

        if not items_data:
            return JsonResponse({
                'success': False,
                'error': 'Veuillez ajouter au moins un article valide'
            }, status=400)

        with transaction.atomic():
            # Générer automatiquement le numéro d'achat
            from datetime import datetime
            year = datetime.now().year
            last_purchase = Purchase.objects.filter(
                purchase_number__startswith=f'A-{year}-'
            ).order_by('-purchase_number').first()

            if last_purchase:
                last_num = int(last_purchase.purchase_number.split('-')[-1])
                new_num = last_num + 1
            else:
                new_num = 1

            purchase_number = f'A-{year}-{new_num:05d}'
            purchase_date = _parse_purchase_date_value(data.get('purchase_date'), "Date d'achat", required=True)
            actual_delivery_date = _parse_purchase_date_value(data.get('actual_delivery_date'), "Date de réception")

            # Créer l'achat
            purchase = Purchase.objects.create(
                purchase_number=purchase_number,
                purchase_date=purchase_date,
                actual_delivery_date=actual_delivery_date,
                fournisseur_id=data.get('fournisseur_id'),
                magasin_id=data.get('magasin_id'),
                compte_id=data.get('compte_id'),
                ordered_by_id=data.get('ordered_by_id'),
                purchase_status=data.get('purchase_status', 'brouillon'),
                numeroDiameX=data.get('numeroDiameX'),
                baseDiameX=data.get('baseDiameX'),
                notes=data.get('notes', '')
            )

            # Créer les lignes d'achat
            from decimal import Decimal
            total_amount = Decimal('0')
            for idx, item_data in enumerate(items_data, start=1):
                designation_id = item_data.get('designation_id')
                if not designation_id:
                    return JsonResponse({
                        'success': False,
                        'error': f'Désignation manquante pour la ligne {idx}'
                    }, status=400)

                qty = Decimal(str(item_data.get('quantity_ordered', 0)))
                price = Decimal(str(item_data.get('unit_price', 0)))
                if qty <= 0:
                    return JsonResponse({
                        'success': False,
                        'error': f'Quantité invalide pour la ligne {idx}'
                    }, status=400)
                if price < 0:
                    return JsonResponse({
                        'success': False,
                        'error': f'Prix unitaire invalide pour la ligne {idx}'
                    }, status=400)

                total = qty * price

                item = PurchaseItem.objects.create(
                    purchase=purchase,
                    designation_id=designation_id,
                    quantity_ordered=qty,
                    unit_price=price,
                    total_price=total
                )
                total_amount += item.total_price

            # Mettre à  jour le montant total
            purchase.total_amount = total_amount
            purchase.save()

        return JsonResponse({
            'success': True,
            'message': 'Achat créé avec succès',
            'purchase_id': str(purchase.id)
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def purchase_update(request, purchase_id):
    """Modifier un achat"""
    try:
        purchase = get_object_or_404(Purchase, id=purchase_id)
        data = json.loads(request.body)
        old_base = _resolve_purchase_base(purchase)
        impacted_pairs = {
            (item.designation_id, old_base.id)
            for item in purchase.purchase_items.all()
            if item.designation_id and old_base
        }

        with transaction.atomic():
            magasin_id = data.get('magasin_id') or None
            magasin = purchase.magasin
            if magasin_id:
                magasin = Magasin.objects.select_related('base').filter(id=magasin_id).first()
                if not magasin:
                    return JsonResponse({
                        'success': False,
                        'error': 'Magasin introuvable'
                    }, status=404)

                if not _filter_bases_by_scope(Base.objects.filter(id=magasin.base_id), request.user).exists():
                    return JsonResponse({
                        'success': False,
                        'error': 'Magasin non autorisé'
                    }, status=403)

            purchase_date = data.get('purchase_date')
            if purchase_date:
                purchase.purchase_date = _parse_purchase_date_value(
                    purchase_date,
                    "Date d'achat",
                    required=True
                )

            expected_delivery_date = data.get('expected_delivery_date')
            if expected_delivery_date is not None:
                purchase.order_date = _parse_purchase_date_value(
                    expected_delivery_date,
                    'Date de commande'
                )

            actual_delivery_date = data.get('actual_delivery_date')
            if actual_delivery_date is not None:
                purchase.actual_delivery_date = _parse_purchase_date_value(
                    actual_delivery_date,
                    'Date de réception'
                )

            # Mettre à  jour l'achat
            purchase.fournisseur_id = data.get('fournisseur_id', purchase.fournisseur_id)
            purchase.magasin = magasin
            purchase.base = magasin.base if magasin else purchase.base
            purchase.compte_id = data.get('compte_id', purchase.compte_id)
            purchase.ordered_by_id = data.get('ordered_by_id', purchase.ordered_by_id)
            purchase.purchase_status = data.get('purchase_status', purchase.purchase_status)
            purchase.numeroDiameX = data.get('numeroDiameX', purchase.numeroDiameX)
            purchase.baseDiameX = data.get('baseDiameX', purchase.baseDiameX)
            purchase.notes = data.get('notes', purchase.notes)

            # Supprimer les anciennes lignes et en créer de nouvelles
            if 'items' in data:
                items_data = data.get('items') or []
                if not items_data:
                    return JsonResponse({
                        'success': False,
                        'error': 'Veuillez conserver au moins un article valide'
                    }, status=400)

                purchase.purchase_items.all().delete()

                from decimal import Decimal
                total_amount = Decimal('0')
                for idx, item_data in enumerate(items_data, start=1):
                    designation_id = item_data.get('designation_id')
                    if not designation_id:
                        return JsonResponse({
                            'success': False,
                            'error': f'Désignation manquante pour la ligne {idx}'
                        }, status=400)

                    qty = Decimal(str(item_data.get('quantity_ordered', 0)))
                    price = Decimal(str(item_data.get('unit_price', 0)))
                    if qty <= 0:
                        return JsonResponse({
                            'success': False,
                            'error': f'Quantité invalide pour la ligne {idx}'
                        }, status=400)
                    if price < 0:
                        return JsonResponse({
                            'success': False,
                            'error': f'Prix unitaire invalide pour la ligne {idx}'
                        }, status=400)

                    total = qty * price

                    item = PurchaseItem.objects.create(
                        purchase=purchase,
                        designation_id=designation_id,
                        quantity_ordered=qty,
                        quantity_received=qty if purchase.purchase_status in ['livre', 'recu'] else Decimal('0'),
                        unit_price=price,
                        total_price=total
                    )
                    total_amount += item.total_price

                purchase.total_amount = total_amount

            purchase.save()
            _sync_purchase_inventory(purchase, impacted_pairs=impacted_pairs)

        return JsonResponse({'success': True, 'message': 'Achat modifié avec succès'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def purchase_receive(request, purchase_id):
    """Réceptionner un achat et générer une transaction DiameX temporaire"""
    try:
        from apps.accounting.models import DiameXTemporaire
        from datetime import date
        from django.db import transaction as db_transaction

        purchase = get_object_or_404(Purchase, id=purchase_id)

        # Vérifier que l'achat peut àªtre réceptionné
        if purchase.purchase_status == 'recu':
            return JsonResponse({
                'success': False,
                'error': 'Cet achat a déjà  été réceptionné'
            }, status=400)

        # Vérifier qu'il y a un magasin associé
        if not purchase.magasin:
            return JsonResponse({
                'success': False,
                'error': 'Impossible de réceptionner : aucun magasin associé à  cet achat'
            }, status=400)

        # Utiliser une transaction atomique pour garantir la cohérence
        with db_transaction.atomic():
            # Mettre à  jour le statut de l'achat
            purchase.purchase_status = 'recu'
            purchase.actual_delivery_date = date.today()
            purchase.save()

            # Créer les mouvements de stock pour chaque item
            items_received = []
            for item in purchase.purchase_items.select_related('designation').all():
                if item.quantity_ordered and item.quantity_ordered > 0:
                    # Mettre à  jour quantity_received sur l'item
                    item.quantity_received = item.quantity_ordered
                    item.save()

                    # Récupérer ou créer le stock pour cette désignation et cette base
                    stock, created = Stock.objects.get_or_create(
                        designation=item.designation,
                        base=purchase.magasin.base,
                        defaults={'current_quantity': 0}
                    )

                    # Créer le mouvement de stock (entrée)
                    from datetime import datetime
                    movement = StockMovement.objects.create(
                        designation=item.designation,
                        base=purchase.magasin.base,
                        movement_type='entree',
                        movement_date=datetime.combine(purchase.actual_delivery_date or date.today(), datetime.min.time()),
                        quantity=item.quantity_ordered,
                        reference=f'Achat #{purchase.purchase_number}',
                        notes=f'Réception achat {purchase.purchase_number}'
                    )

                    # Mettre à  jour le stock
                    stock.current_quantity += item.quantity_ordered
                    stock.save()

                    items_received.append({
                        'designation': item.designation.nom,
                        'quantity': float(item.quantity_ordered)
                    })

            _sync_purchase_inventory(purchase)

        # Générer la description pour DiameX
        # Format: ISI ou NIF_Nom fournisseur_Nom désignation(s)_Unité_Prix Unitaire_Ar
        fournisseur_name = ''
        fournisseur_prefix = ''
        if purchase.fournisseur:
            fournisseur_name = purchase.fournisseur.nom_fournisseur

            # Déterminer le préfixe NIF ou ISI (sans le numéro)
            if purchase.fournisseur.nif_ou_isi == 'NIF':
                fournisseur_prefix = "NIF"
            elif purchase.fournisseur.nif_ou_isi == 'ISI':
                fournisseur_prefix = "ISI"
            # Si nif_ou_isi est vide mais numero_nif existe, utiliser NIF
            elif purchase.fournisseur.numero_nif:
                fournisseur_prefix = "NIF"
            # Sinon utiliser ISI par défaut
            else:
                fournisseur_prefix = "ISI"
        elif purchase.supplier:
            fournisseur_name = purchase.supplier.supplier_name

        # Récupérer les premières désignations
        items = purchase.purchase_items.select_related('designation').all()[:3]
        designations_str = ', '.join([
            f"{item.designation.nom} ({item.designation.unite or 'unité'})"
            for item in items if item.designation
        ])

        if len(purchase.purchase_items.all()) > 3:
            designations_str += '...'

        # Construction de la description
        description_parts = []
        if fournisseur_prefix:
            description_parts.append(fournisseur_prefix)
        if fournisseur_name:
            description_parts.append(fournisseur_name)
        if designations_str:
            description_parts.append(designations_str)
        description_parts.append(f"{purchase.total_amount:,.0f} Ar")

        description = '_'.join(description_parts)
        if len(description) > 255:
            description = description[:252] + '...'

        # Déterminer le code compte
        compte_code = '601'  # Valeur par défaut
        if purchase.compte and purchase.compte.compte:
            compte_code = purchase.compte.compte

        # Créer la transaction DiameXTemporaire
        transaction = DiameXTemporaire.objects.create(
            purchase=purchase,
            fournisseur=purchase.fournisseur,
            type_transaction='depense',
            date_m=purchase.actual_delivery_date or date.today(),
            description=description,
            montant_out=float(purchase.total_amount),
            montant_in=0.0,
            compte_code=compte_code,  # Utilise le code du compte sélectionné
            prog=purchase.magasin.base.volet if purchase.magasin and purchase.magasin.base else None,
            activ=purchase.magasin.base.volet if purchase.magasin and purchase.magasin.base else None,
            info='Hydria Achats',  # Marqueur pour identifier les achats
            statut='en_attente'
        )

        return JsonResponse({
            'success': True,
            'message': f'Achat {purchase.purchase_number} réceptionné avec succès. {len(items_received)} article(s) ajouté(s) au stock. Transaction DiameX créée.',
            'transaction_id': transaction.id,
            'items_received': items_received
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@require_http_methods(["POST"])
def purchase_delete(request, purchase_id):
    """Supprimer un achat"""
    try:
        purchase = get_object_or_404(Purchase, id=purchase_id)
        purchase_number = purchase.purchase_number
        purchase.delete()
        return JsonResponse({
            'success': True,
            'message': f'Achat {purchase_number} supprimé avec succès'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@require_http_methods(["GET"])
def purchase_detail(request, purchase_id):
    """Obtenir les détails d'un achat"""
    try:
        purchase = Purchase.objects.select_related(
            'supplier', 'fournisseur', 'base', 'ordered_by'
        ).prefetch_related(
            Prefetch('purchase_items', queryset=PurchaseItem.objects.select_related('designation'))
        ).get(id=purchase_id)

        items = []
        for item in purchase.purchase_items.all():
            items.append({
                'id': str(item.id),
                'designation_id': str(item.designation.id) if item.designation else None,
                'designation_name': item.designation.nom if item.designation else '',
                'quantity_ordered': float(item.quantity_ordered),
                'quantity_received': float(item.quantity_received),
                'unit_price': float(item.unit_price),
                'total_price': float(item.total_price),
                'unit': item.designation.unite if item.designation else ''
            })

        # Gérer à  la fois fournisseur et supplier
        fournisseur_id = None
        fournisseur_name = ''
        if purchase.fournisseur:
            fournisseur_id = str(purchase.fournisseur.id)
            fournisseur_name = purchase.fournisseur.nom_fournisseur
        elif purchase.supplier:
            fournisseur_id = str(purchase.supplier.id)
            fournisseur_name = purchase.supplier.supplier_name

        data = {
            'id': str(purchase.id),
            'purchase_number': purchase.purchase_number,
            'purchase_date': purchase.purchase_date.strftime('%Y-%m-%d'),
            'expected_delivery_date': purchase.order_date.strftime('%Y-%m-%d') if purchase.order_date else '',
            'actual_delivery_date': purchase.actual_delivery_date.strftime('%Y-%m-%d') if purchase.actual_delivery_date else '',
            'fournisseur_id': fournisseur_id,
            'fournisseur_name': fournisseur_name,
            'magasin_id': str(purchase.magasin.id) if purchase.magasin else '',
            'magasin_name': purchase.magasin.nom_magasin if purchase.magasin else '',
            'compte_id': str(purchase.compte.id) if purchase.compte else '',
            'compte_code': purchase.compte.compte if purchase.compte else '',
            'compte_name': purchase.compte.nom_compte if purchase.compte else '',
            'ordered_by_id': str(purchase.ordered_by.id) if purchase.ordered_by else '',
            'ordered_by_name': f"{purchase.ordered_by.nom_employe}" if purchase.ordered_by else '',
            'purchase_status': purchase.purchase_status,
            'numeroDiameX': purchase.numeroDiameX or '',
            'baseDiameX': purchase.baseDiameX or '',
            'total_amount': float(purchase.total_amount),
            'notes': purchase.notes or '',
            'items': items
        }

        return JsonResponse({'success': True, 'purchase': data})
    except Purchase.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Achat introuvable'}, status=404)
    except Exception as e:
        import traceback
        print(f"Error in purchase_detail: {str(e)}")
        print(traceback.format_exc())
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
def stock_movements(request):
    search = (request.GET.get('search') or '').strip()
    movement_type = (request.GET.get('movement_type') or '').strip()
    base_id = (request.GET.get('base') or '').strip()

    scoped_bases = _filter_bases_by_scope(Base.objects.all(), request.user)
    if base_id and not scoped_bases.filter(id=base_id).exists():
        base_id = ''

    movements = StockMovement.objects.select_related(
        'designation',
        'base',
        'employee'
    ).filter(base_id__in=scoped_bases.values('id'))

    if movement_type:
        movements = movements.filter(movement_type=movement_type)
    if base_id:
        movements = movements.filter(base_id=base_id)
    if search:
        movements = movements.filter(
            Q(designation__nom__icontains=search) |
            Q(reference__icontains=search) |
            Q(notes__icontains=search)
        )

    movements = movements.order_by('-movement_date', '-created_at')[:500]

    return render(request, 'inventory/movements_list.html', {
        'movements': movements,
        'bases': scoped_bases.order_by('nom_base'),
        'movement_types': StockMovement.MOVEMENT_TYPE_CHOICES,
        'filters': {
            'search': search,
            'movement_type': movement_type,
            'base': base_id,
        },
        'title': 'Mouvements de Stock'
    })


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def api_adjust_stock(request, stock_id):
    """API pour ajuster un stock"""
    try:
        from apps.employees.models import Employe
        # Utiliser request.POST au lieu de json.loads car le formulaire envoie FormData
        data = request.POST
        stock = _filter_stocks_by_scope(
            Stock.objects.select_related('base', 'designation'),
            request.user
        ).get(id=stock_id)

        adjust_type = data.get('adjust_type')
        requested_quantity = Decimal(str(data.get('quantity', 0)))
        reference = data.get('reference', '')
        notes = data.get('notes', '')
        inventory_date = data.get('inventory_date', '')
        nature_stock = (data.get('nature_stock') or '').strip().lower()
        # Convertir la checkbox rapproche en booléen (FormData envoie 'on' si cochée)
        rapproche = data.get('rapproche') == 'on'
        etat = (data.get('etat') or 'bon').strip().lower()
        magasin_id = (data.get('magasin_id') or '').strip()
        photo_file = request.FILES.get('photo')

        if not adjust_type:
            return JsonResponse({'success': False, 'error': 'Type et quantité requis'}, status=400)
        if requested_quantity < 0:
            return JsonResponse({'success': False, 'error': 'La quantité ne peut pas être négative'}, status=400)
        if adjust_type in ('add', 'remove') and requested_quantity == 0:
            return JsonResponse({'success': False, 'error': 'La quantité doit être supérieure à zéro'}, status=400)
        if etat not in dict(Stock.ETAT_CHOICES):
            return JsonResponse({'success': False, 'error': 'État invalide'}, status=400)
        if nature_stock and nature_stock not in {'consommable', 'non_consommable'}:
            return JsonResponse({'success': False, 'error': 'Nature invalide'}, status=400)
        if _base_has_multiple_magasins(stock.base_id) and not magasin_id:
            return JsonResponse({
                'success': False,
                'error': 'Cette base a plusieurs magasins. Sélectionnez un magasin dans le modal avant d’enregistrer.'
            }, status=400)
        effective_nature_stock = nature_stock or (getattr(stock.designation, 'nature_stock', 'consommable') or 'consommable')
        if effective_nature_stock == 'non_consommable':
            requested_quantity = Decimal('1')

        selected_magasin = None
        if magasin_id:
            selected_magasin = Magasin.objects.filter(
                id=magasin_id,
                base_id=stock.base_id
            ).first()
            if not selected_magasin:
                return JsonResponse({'success': False, 'error': 'Magasin introuvable pour cette base'}, status=404)

        old_quantity = stock.current_quantity
        effective_current_quantity = old_quantity
        fiche_operation_type = 'ajustement'
        if selected_magasin:
            try:
                strict_quantities, _strict_inventory_dates, strict_has_movement = _compute_strict_stock_for_magasin(
                    request.user,
                    selected_magasin,
                    [str(stock.designation_id)]
                )
                designation_key = str(stock.designation_id)
                if strict_has_movement.get(designation_key):
                    effective_current_quantity = Decimal(str(strict_quantities.get(designation_key, 0) or 0))
                else:
                    effective_current_quantity = Decimal('0')
            except Exception:
                effective_current_quantity = old_quantity

        fiche_quantity = requested_quantity

        if adjust_type == 'add':
            if not selected_magasin:
                stock.current_quantity += requested_quantity
            movement_type = 'entree'
        elif adjust_type == 'remove':
            if requested_quantity > effective_current_quantity:
                return JsonResponse({'success': False, 'error': 'Quantité insuffisante en stock'}, status=400)
            if not selected_magasin:
                stock.current_quantity -= requested_quantity
            movement_type = 'sortie'
        elif adjust_type == 'set':
            fiche_quantity = requested_quantity - effective_current_quantity
            if not selected_magasin:
                stock.current_quantity = requested_quantity
            else:
                fiche_quantity = requested_quantity
                fiche_operation_type = 'inventaire'
            movement_type = 'ajustement'
        else:
            return JsonResponse({'success': False, 'error': 'Type d\'ajustement invalide'}, status=400)

        # Mettre à  jour la date d'inventaire si fournie
        if inventory_date:
            try:
                stock.inventory_date = datetime.strptime(inventory_date, '%Y-%m-%d').date()
            except ValueError:
                pass  # Ignorer si format invalide

        # Mettre à  jour le champ rapproché
        stock.rapproche = rapproche
        stock.etat = etat
        if photo_file:
            stock.photo = photo_file

        utilisateur = _resolve_stock_utilisateur_from_request(data, request.user)
        if utilisateur is False:
            return JsonResponse({'success': False, 'error': 'Utilisateur invalide'}, status=400)
        if utilisateur is None and not _stock_request_includes_utilisateur(data):
            utilisateur = getattr(request.user, 'employe', None)
        stock.utilisateur = utilisateur
        if nature_stock:
            stock.designation.nature_stock = nature_stock
            stock.designation.save(update_fields=['nature_stock'])

        notes_value = notes or f'Ajustement manuel: {effective_current_quantity} -> {requested_quantity}'
        if selected_magasin:
            notes_value = (
                f'{notes_value} | Magasin ID: {selected_magasin.id} | '
                f'Magasin: {selected_magasin.nom_magasin}'
            )

        stock.save()

        # Créer un mouvement de stock
        StockMovement.objects.create(
            designation=stock.designation,
            base=stock.base,
            movement_type=movement_type,
            quantity=fiche_quantity if adjust_type == 'set' else requested_quantity,
            movement_date=datetime.now(),
            reference=reference,
            notes=notes_value
        )

        FicheStock.objects.create(
            operation_date=datetime.now().date(),
            operation_type=fiche_operation_type,
            quantity=fiche_quantity,
            designation=stock.designation,
            base=stock.base,
            employee=utilisateur,
            notes=notes_value
        )

        stock_photo = getattr(stock, 'photo', None)
        response_quantity = requested_quantity if selected_magasin else stock.current_quantity
        return JsonResponse({
            'success': True,
            'message': 'Stock ajusté avec succès',
            'new_quantity': float(response_quantity),
            'etat': stock.etat,
            'photo_url': stock_photo.url if stock_photo else '',
            'inventory_date': stock.inventory_date.strftime('%d/%m/%Y') if stock.inventory_date else '',
            'rapproche': bool(stock.rapproche),
            'nature_stock': getattr(stock.designation, 'nature_stock', 'consommable') or 'consommable',
            'utilisateur_label': getattr(getattr(stock, 'utilisateur', None), 'surnom', '') or '',
        })

    except Stock.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Stock introuvable'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def api_create_inventaire(request):
    """Créer un inventaire manuel pour une désignation et un magasin (base)."""
    try:
        from decimal import Decimal
        from django.utils import timezone
        from apps.planning.models import Designation
        from .models import FicheStock
        data = request.POST
        designation_id = data.get('designation_id')
        base_id = data.get('base_id')
        magasin_id = data.get('magasin_id')
        quantity = data.get('quantity')
        inventory_date = data.get('inventory_date')
        notes = data.get('notes', '')
        nature_stock = (data.get('nature_stock') or '').strip().lower()
        rapproche = str(data.get('rapproche', '')).lower() in ('1', 'true', 'oui', 'on', 'yes')
        etat = (data.get('etat') or 'bon').strip().lower()
        photo_file = request.FILES.get('photo')

        if not designation_id or not base_id or quantity is None:
            return JsonResponse({'success': False, 'error': 'Désignation, magasin et quantité requis'}, status=400)
        if etat not in dict(Stock.ETAT_CHOICES):
            return JsonResponse({'success': False, 'error': 'État invalide'}, status=400)
        if nature_stock and nature_stock not in {'consommable', 'non_consommable'}:
            return JsonResponse({'success': False, 'error': 'Nature invalide'}, status=400)

        try:
            quantity_val = Decimal(str(quantity))
        except Exception:
            return JsonResponse({'success': False, 'error': 'Quantité invalide'}, status=400)

        designation = Designation.objects.filter(id=designation_id).first()
        base = _filter_bases_by_scope(Base.objects.all(), request.user).filter(id=base_id).first()
        if not designation or not base:
            return JsonResponse({'success': False, 'error': 'Désignation ou magasin introuvable'}, status=404)
        if _base_has_multiple_magasins(base.id) and not magasin_id:
            return JsonResponse({
                'success': False,
                'error': 'Cette base a plusieurs magasins. Sélectionnez un magasin dans le modal avant d’enregistrer.'
            }, status=400)
        effective_nature_stock = nature_stock or (getattr(designation, 'nature_stock', 'consommable') or 'consommable')
        if effective_nature_stock == 'non_consommable':
            quantity_val = Decimal('1')
        if nature_stock:
            designation.nature_stock = nature_stock
            designation.save(update_fields=['nature_stock'])

        selected_magasin = None
        if magasin_id:
            selected_magasin = Magasin.objects.filter(id=magasin_id, base_id=base.id).first()
            if not selected_magasin:
                return JsonResponse({'success': False, 'error': 'Magasin introuvable pour cette base'}, status=404)

        utilisateur = _resolve_stock_utilisateur_from_request(data, request.user)
        if utilisateur is False:
            return JsonResponse({'success': False, 'error': 'Utilisateur invalide'}, status=400)

        stock, _created = Stock.objects.get_or_create(
            designation=designation,
            base=base,
            defaults={'current_quantity': 0}
        )

        if inventory_date:
            from datetime import datetime
            try:
                stock.inventory_date = datetime.strptime(inventory_date, '%Y-%m-%d').date()
            except ValueError:
                pass

        stock.rapproche = rapproche
        stock.etat = etat
        if photo_file:
            stock.photo = photo_file
        stock.utilisateur = utilisateur
        # Ne jamais écraser le stock global de base lorsqu'on enregistre
        # un inventaire ciblé sur un magasin.
        if not selected_magasin:
            stock.current_quantity = quantity_val
        stock.save()

        operation_date = timezone.now()
        if inventory_date:
            from datetime import datetime
            try:
                parsed_date = datetime.strptime(inventory_date, '%Y-%m-%d')
                operation_date = timezone.make_aware(parsed_date, timezone.get_current_timezone())
            except ValueError:
                pass

        notes_value = (notes or 'Inventaire manuel').strip()
        if selected_magasin:
            notes_value = (
                f"{notes_value} | Magasin ID: {selected_magasin.id} | "
                f"Magasin: {selected_magasin.nom_magasin}"
            )

            # Pour un inventaire manuel cible sur un magasin, on remplace les
            # anciens snapshots manuels de ce meme magasin afin d'eviter que
            # des ajustements historiques continuent a brouiller l'affichage.
            FicheStock.objects.filter(
                designation=designation,
                base=base,
                operation_type__in=['inventaire', 'ajustement'],
                notes__icontains=f"Magasin ID: {selected_magasin.id}"
            ).delete()

        FicheStock.objects.create(
            operation_date=operation_date,
            operation_type='inventaire',
            quantity=quantity_val,
            designation=designation,
            base=base,
            employee=utilisateur,
            notes=notes_value
        )

        return JsonResponse({'success': True, 'message': 'Inventaire enregistré'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def api_mark_rapproche(request):
    """Marquer le stock comme rapproché."""
    try:
        designation_id = request.POST.get('designation_id')
        base_id = request.POST.get('base_id')
        if not designation_id or not base_id:
            return JsonResponse({'success': False, 'error': 'Désignation et magasin requis'}, status=400)

        stock = _filter_stocks_by_scope(
            Stock.objects.filter(designation_id=designation_id, base_id=base_id),
            request.user
        ).first()
        if not stock:
            return JsonResponse({'success': False, 'error': 'Stock introuvable'}, status=404)

        stock.rapproche = True
        if hasattr(request.user, 'employe'):
            stock.utilisateur = request.user.employe
        stock.save()

        return JsonResponse({'success': True, 'message': 'Stock rapproché'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


# ========== EXPORT / IMPORT EXCEL ACHATS ==========

@login_required
def export_purchases_excel(request):
    """Exporter les achats en Excel"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from django.http import HttpResponse

    wb = Workbook()
    ws = wb.active
    ws.title = "Achats"

    # En-tàªtes
    headers = [
        'ID Achat', 'N° Achat', 'Date Achat', 'Date Livraison Prévue', 'Date Livraison Réelle',
        'Fournisseur', 'Base', 'Commandé par', 'Statut', 'Montant Total', 'Notes',
        'Créé le', 'Modifié le'
    ]
    ws.append(headers)

    # Style des en-tàªtes
    header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")

    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')

    # Récupérer les achats
    purchases = Purchase.objects.select_related('supplier', 'fournisseur', 'base', 'ordered_by').order_by('-purchase_date')

    for purchase in purchases:
        # Gérer à  la fois fournisseur et supplier
        fournisseur_nom = ''
        if purchase.fournisseur:
            fournisseur_nom = purchase.fournisseur.nom_fournisseur
        elif purchase.supplier:
            fournisseur_nom = purchase.supplier.supplier_name

        ws.append([
            str(purchase.id),
            purchase.purchase_number,
            purchase.purchase_date.strftime('%Y-%m-%d'),
            purchase.actual_delivery_date.strftime('%Y-%m-%d') if purchase.actual_delivery_date else '',
            purchase.actual_delivery_date.strftime('%Y-%m-%d') if purchase.actual_delivery_date else '',
            fournisseur_nom,
            purchase.base.nom_base if purchase.base else '',
            f"{purchase.ordered_by.surnom or purchase.ordered_by.nom_employe}" if purchase.ordered_by else '',
            purchase.get_purchase_status_display(),
            float(purchase.total_amount),
            purchase.notes or '',
            purchase.created_at.strftime('%Y-%m-%d %H:%M'),
            purchase.updated_at.strftime('%Y-%m-%d %H:%M')
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

    # Retourner le fichier
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=achats_export.xlsx'
    wb.save(response)

    return response


@login_required
def export_purchases_details_excel(request):
    """Exporter les achats avec leurs articles en Excel"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from django.http import HttpResponse

    wb = Workbook()
    ws = wb.active
    ws.title = "Achats Détails"

    # En-tàªtes
    headers = [
        'ID Achat', 'N° Achat', 'Date Achat', 'Fournisseur', 'Base', 'Statut',
        'ID Article', 'Désignation', 'Code', 'Quantité Commandée', 'Quantité Reà§ue',
        'Prix Unitaire', 'Total Article', 'Unité'
    ]
    ws.append(headers)

    # Style des en-tàªtes
    header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")

    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')

    # Récupérer les achats avec articles
    purchases = Purchase.objects.select_related('supplier', 'fournisseur', 'base').prefetch_related(
        Prefetch('purchase_items', queryset=PurchaseItem.objects.select_related('designation'))
    ).order_by('-purchase_date')

    for purchase in purchases:
        # Gérer à  la fois fournisseur et supplier
        fournisseur_nom = ''
        if purchase.fournisseur:
            fournisseur_nom = purchase.fournisseur.nom_fournisseur
        elif purchase.supplier:
            fournisseur_nom = purchase.supplier.supplier_name

        for item in purchase.purchase_items.all():
            ws.append([
                str(purchase.id),
                purchase.purchase_number,
                purchase.purchase_date.strftime('%Y-%m-%d'),
                fournisseur_nom,
                purchase.base.nom_base if purchase.base else '',
                purchase.get_purchase_status_display(),
                str(item.id),
                item.designation.nom if item.designation else '',
                item.designation.code if item.designation and hasattr(item.designation, 'code') else '',
                float(item.quantity_ordered),
                float(item.quantity_received),
                float(item.unit_price),
                float(item.total_price),
                item.designation.unite if item.designation else ''
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

    # Retourner le fichier
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=achats_details_export.xlsx'
    wb.save(response)

    return response


@login_required
def template_purchases_excel(request):
    """Générer un template Excel pour l'import d'achats"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from django.http import HttpResponse

    wb = Workbook()
    ws = wb.active
    ws.title = "Template Achats"

    # En-tàªtes avec instructions
    headers = [
        'N° Achat*', 'Date Achat (DD/MM/YYYY)*', 'Date Commande (DD/MM/YYYY)',
        'Date Réception (DD/MM/YYYY)', 'ID Fournisseur (UUID)*', 'ID Magasin (UUID)*',
        'Numéro DiameX', 'Base DiameX', 'Statut', 'Notes'
    ]
    ws.append(headers)

    # Style des en-tàªtes
    header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")

    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')

    # Ajouter des exemples avec IDs des premiers éléments réels
    first_fournisseur = Fournisseur.objects.first()
    first_base = Base.objects.first()

    ws.append([
        'ACH-2025-001',
        '15/01/2025',
        '10/01/2025',
        '20/01/2025',
        str(first_fournisseur.id) if first_fournisseur else '12345678-1234-1234-1234-123456789012',
        str(first_base.id) if first_base else '87654321-4321-4321-4321-210987654321',
        'DX-001',
        'BASE_TANA',
        'commande',
        'Exemple de note'
    ])

    # Commentaires explicatifs
    ws.append([])
    ws.append(['INSTRUCTIONS:'])
    ws.append(['- Les colonnes marquées * sont obligatoires'])
    ws.append(['- Les dates doivent àªtre au format DD/MM/YYYY (ex: 15/01/2025)'])
    ws.append(['- Les ID doivent àªtre des UUID valides (copiez depuis les feuilles de référence ci-dessous)'])
    ws.append(['- Statuts possibles: brouillon, commande, livre, facture, paye, annule'])
    ws.append([])

    # Feuille de référence - Fournisseurs
    ws_suppliers = wb.create_sheet("Fournisseurs")
    ws_suppliers.append(['ID Fournisseur', 'Nom Fournisseur', 'Téléphone'])
    fournisseurs = Fournisseur.objects.filter(actif=True).order_by('nom_fournisseur')[:500]
    for fournisseur in fournisseurs:
        ws_suppliers.append([
            str(fournisseur.id),
            fournisseur.nom_fournisseur,
            fournisseur.telephone or ''
        ])

    # Feuille de référence - Magasins
    ws_magasins = wb.create_sheet("Magasins")
    ws_magasins.append(['ID Magasin', 'Nom Magasin', 'Base'])
    magasins = Magasin.objects.select_related('base').order_by('nom_magasin')
    for magasin in magasins:
        ws_magasins.append([
            str(magasin.id),
            magasin.nom_magasin,
            magasin.base.nom_base if magasin.base else 'Aucune base'
        ])

    # Retourner le fichier
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=template_achats.xlsx'
    wb.save(response)

    return response


@csrf_exempt
@require_http_methods(["POST"])
def import_purchases_excel(request):
    """Importer des achats depuis Excel"""
    if request.method == 'POST' and request.FILES.get('fichier'):
        try:
            fichier = request.FILES['fichier']
            wb = load_workbook(fichier)
            ws = wb.active

            count = 0
            errors = []

            def parse_date(date_value):
                """Parse date in DD/MM/YYYY format"""
                if not date_value:
                    return None
                if isinstance(date_value, datetime):
                    return date_value.date()
                try:
                    return datetime.strptime(str(date_value).strip(), '%d/%m/%Y').date()
                except:
                    try:
                        return datetime.strptime(str(date_value).strip(), '%Y-%m-%d').date()
                    except:
                        return None

            for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                if not row[0]:  # Skip empty rows
                    continue

                try:
                    with transaction.atomic():
                        # Vérifier que le fournisseur existe (colonne 4 - recherche par ID UUID dans Fournisseur)
                        try:
                            supplier_id = str(row[4]).strip() if row[4] else None
                            if not supplier_id:
                                errors.append(f"Ligne {idx}: ID Fournisseur vide")
                                continue
                            supplier = Fournisseur.objects.get(id=supplier_id)
                        except Fournisseur.DoesNotExist:
                            errors.append(f"Ligne {idx}: Fournisseur introuvable ({supplier_id})")
                            continue
                        except (ValueError, AttributeError) as e:
                            errors.append(f"Ligne {idx}: ID Fournisseur invalide ({row[4]})")
                            continue

                        # Rechercher le magasin par ID (colonne 5)
                        try:
                            magasin_id = str(row[5]).strip() if row[5] else None
                            if not magasin_id:
                                errors.append(f"Ligne {idx}: ID Magasin vide")
                                continue

                            try:
                                # Récupérer le magasin et sa base associée
                                from apps.organization.models import Magasin
                                magasin = Magasin.objects.select_related('base').get(id=magasin_id)
                                base = magasin.base
                            except Magasin.DoesNotExist:
                                # Montrer les magasins disponibles pour aider
                                from apps.organization.models import Magasin
                                available = Magasin.objects.select_related('base').all()[:3]
                                suggestions = ', '.join([f"{m.nom_magasin} - {m.base.nom_base} ({str(m.id)[:8]}...)" for m in available])
                                errors.append(f"Ligne {idx}: Magasin introuvable. ID fourni: '{magasin_id}'. Magasins disponibles: {suggestions}. Vérifiez la feuille de référence du template.")
                                continue
                        except (ValueError, AttributeError) as e:
                            errors.append(f"Ligne {idx}: ID Magasin invalide - {str(e)} - Valeur: '{row[5]}'")
                            continue

                        # Parser les dates
                        purchase_date = parse_date(row[1])
                        order_date = parse_date(row[2])
                        delivery_date = parse_date(row[3])

                        if not purchase_date:
                            errors.append(f"Ligne {idx}: Date achat invalide ({row[1]})")
                            continue

                        # Vérifier si l'achat existe déjà 
                        purchase_number = str(row[0]).strip()
                        existing_purchase = Purchase.objects.filter(purchase_number=purchase_number).first()

                        if existing_purchase:
                            # Achat existe déjà , ignorer ou mettre à  jour
                            errors.append(f"Ligne {idx}: Achat {purchase_number} existe déjà  (ignoré)")
                            continue

                        # Créer l'achat
                        Purchase.objects.create(
                            purchase_number=purchase_number,
                            purchase_date=purchase_date,
                            order_date=order_date,
                            actual_delivery_date=delivery_date,
                            fournisseur=supplier,
                            base=base,
                            numeroDiameX=str(row[6]).strip() if row[6] else None,
                            baseDiameX=str(row[7]).strip() if row[7] else None,
                            purchase_status=str(row[8]).strip() if row[8] else 'brouillon',
                            notes=str(row[9]).strip() if row[9] else '',
                            total_amount=0  # Sera mis à  jour quand on ajoutera les articles
                        )
                        count += 1

                except Exception as e:
                    errors.append(f"Ligne {idx}: {str(e)}")

            if errors:
                return JsonResponse({
                    'success': True,
                    'count': count,
                    'errors': errors,
                    'message': f'{count} achat(s) importé(s) avec {len(errors)} erreur(s)'
                })
            else:
                return JsonResponse({
                    'success': True,
                    'count': count,
                    'message': f'{count} achat(s) importé(s) avec succès'
                })

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)

    return JsonResponse({'success': False, 'error': 'Fichier manquant'}, status=400)


@login_required
def template_purchase_details_excel(request):
    """Générer un template Excel pour l'import de détails d'achats"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from django.http import HttpResponse

    wb = Workbook()
    ws = wb.active
    ws.title = "Template Détails Achat"

    # En-tàªtes avec instructions
    headers = [
        'N° Achat*', 'ID Désignation (UUID)*', 'Quantité*', 'Prix Unitaire*'
    ]
    ws.append(headers)

    # Style des en-tàªtes
    header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")

    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')

    # Ajouter des exemples
    ws.append([
        'ACH-2025-001',
        '12345678-1234-1234-1234-123456789012',
        10,
        15000
    ])
    ws.append([
        'ACH-2025-001',
        '87654321-4321-4321-4321-210987654321',
        5,
        25000
    ])

    # Commentaires explicatifs
    ws.append([])
    ws.append(['INSTRUCTIONS:'])
    ws.append(['- Les colonnes marquées * sont obligatoires'])
    ws.append(['- N° Achat: Doit correspondre à  un achat existant'])
    ws.append(['- Le montant total sera calculé automatiquement (Quantité à— Prix Unitaire)'])
    ws.append(['- Copiez les ID désignations depuis la liste de référence ci-dessous'])
    ws.append([])

    # Feuille de référence - Désignations
    from apps.planning.models import Designation
    ws_designations = wb.create_sheet("Désignations")
    ws_designations.append(['ID Désignation', 'Nom', 'Unité', 'Prix Unitaire'])
    designations = Designation.objects.order_by('nom')[:500]
    for designation in designations:
        ws_designations.append([
            str(designation.id),
            designation.nom,
            designation.unite or '',
            float(designation.prix_unitaire) if designation.prix_unitaire else 0
        ])

    # Feuille de référence - Achats récents
    ws_purchases = wb.create_sheet("Achats Récents")
    ws_purchases.append(['N° Achat', 'Date', 'Fournisseur', 'Magasin', 'Statut'])
    purchases = Purchase.objects.select_related('supplier', 'fournisseur', 'base').order_by('-purchase_date')[:50]
    for purchase in purchases:
        # Gérer à  la fois fournisseur et supplier
        fournisseur_nom = ''
        if purchase.fournisseur:
            fournisseur_nom = purchase.fournisseur.nom_fournisseur
        elif purchase.supplier:
            fournisseur_nom = purchase.supplier.supplier_name

        ws_purchases.append([
            purchase.purchase_number,
            purchase.purchase_date.strftime('%d/%m/%Y'),
            fournisseur_nom,
            purchase.base.nom_base if purchase.base else '',
            purchase.get_purchase_status_display()
        ])

    # Retourner le fichier
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=template_details_achat.xlsx'
    wb.save(response)

    return response


@csrf_exempt
@require_http_methods(["POST"])
def import_purchase_details_excel(request):
    """Importer des détails d'achats depuis Excel"""
    if request.method == 'POST' and request.FILES.get('fichier'):
        try:
            fichier = request.FILES['fichier']
            wb = load_workbook(fichier)
            ws = wb.active

            count = 0
            errors = []

            for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                if not row[0]:  # Skip empty rows
                    continue

                try:
                    with transaction.atomic():
                        # Vérifier que l'achat existe (colonne 0)
                        try:
                            purchase_number = str(row[0]).strip()
                            purchase = Purchase.objects.get(purchase_number=purchase_number)
                        except Purchase.DoesNotExist:
                            errors.append(f"Ligne {idx}: Achat introuvable ({purchase_number})")
                            continue

                        # Vérifier que la désignation existe (colonne 1)
                        try:
                            from apps.planning.models import Designation
                            designation = Designation.objects.get(id=str(row[1]).strip())
                        except (Designation.DoesNotExist, ValueError):
                            errors.append(f"Ligne {idx}: Désignation introuvable ({row[1]})")
                            continue

                        # Quantité et prix (colonnes 2 et 3)
                        try:
                            quantity = float(row[2])
                            unit_price = float(row[3])
                        except (ValueError, TypeError):
                            errors.append(f"Ligne {idx}: Quantité ou prix invalide")
                            continue

                        # Créer l'article d'achat
                        item = PurchaseItem.objects.create(
                            purchase=purchase,
                            designation=designation,
                            quantity_ordered=quantity,
                            unit_price=unit_price,
                            total_price=quantity * unit_price
                        )

                        # Mettre à  jour le total de l'achat
                        purchase.total_amount = purchase.purchase_items.aggregate(
                            total=Sum('total_price')
                        )['total'] or 0
                        purchase.save()

                        count += 1

                except Exception as e:
                    errors.append(f"Ligne {idx}: {str(e)}")

            if errors:
                return JsonResponse({
                    'success': True,
                    'count': count,
                    'errors': errors,
                    'message': f'{count} ligne(s) importée(s) avec {len(errors)} erreur(s)'
                })
            else:
                return JsonResponse({
                    'success': True,
                    'count': count,
                    'message': f'{count} ligne(s) d\'achat importée(s) avec succès'
                })

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)

    return JsonResponse({'success': False, 'error': 'Fichier manquant'}, status=400)


# ========== GESTION DES FICHES DE STOCK ==========


@login_required
def fiche_stock_list(request):
    """Vue principale pour consulter les fiches de stock avec article et magasin spécifiques"""
    from .models import FicheStock, Purchase, PurchaseItem, Stock, Transfert, TransfertItem
    from apps.planning.models import Designation, BonLivraison, Planning
    from apps.organization.models import Magasin
    from decimal import Decimal
    from django.db.models import Q

    # Filtres
    designation_id = request.GET.get('designation_id', '')
    base_id = request.GET.get('base_id', '')
    date_debut = request.GET.get('date_debut', '')
    date_fin = request.GET.get('date_fin', '')
    magasin_id = request.GET.get('magasin_id', '')
    accueil_view = request.GET.get('view', 'cards')

    # Listes pour les filtres - Désignations avec prestation=False
    designations = Designation.objects.filter(prestation=False, actif=True).order_by('nom')
    bases = _filter_bases_by_scope(Base.objects.all(), request.user).order_by('nom_base')
    magasins = Magasin.objects.filter(
        base_id__in=bases.values('id')
    ).order_by('base__nom_base', 'nom_magasin')

    if base_id and not bases.filter(id=base_id).exists():
        base_id = ''
    if magasin_id and not magasins.filter(id=magasin_id).exists():
        magasin_id = ''

    # Initialiser les variables
    fiches = []
    designation = None
    base = None
    stock_actuel = None
    dernier_inventaire = None
    inventaires = []
    achats = []
    transferts = []
    bons_livraison = []
    stock_item = None
    selected_magasin = None
    stock_non_ventile = False
    stock_global_base = None
    stock_non_ventile_ecart = None
    carburant_stock_analysis = None
    mode_tous_magasins = False
    fiche_group_count = 0
    accueil_articles = []
    accueil_types_designation = []
    user_poste_nom = _normalize_poste_name(
        getattr(getattr(getattr(request.user, 'employe', None), 'poste', None), 'nom_poste', '')
    )
    is_directeur_poste = request.user.is_superuser or user_poste_nom == 'directeur'
    can_delete_fiche_rows = _can_delete_fiche_stock_rows(request.user)

    # Vue d'accueil: liste des articles et stocks disponibles par base/magasin
    # Charger aussi si un seul des deux filtres est présent (designation/base incomplet)
    if not (designation_id and base_id):
        stocks_accueil = _filter_stocks_by_scope(
            Stock.objects.filter(
                designation__isnull=False,
                designation__actif=True,
                designation__prestation=False
            )
            .select_related('designation', 'designation__type_designation', 'base')
            .order_by('designation__type_designation__nom', 'designation__nom', 'base__nom_base')
            ,
            request.user
        )

        articles_map = {}
        for stock in stocks_accueil:
            designation_obj = stock.designation
            desig_id = str(designation_obj.id)

            if desig_id not in articles_map:
                articles_map[desig_id] = {
                    'id': desig_id,
                    'nom': designation_obj.nom,
                    'unite': designation_obj.unite or '',
                    'photo_url': designation_obj.photo_url or '',
                    'prix_unitaire': designation_obj.prix_unitaire,
                    'date_prix': designation_obj.date_prix,
                    'type_designation_nom': designation_obj.type_designation.nom if designation_obj.type_designation else 'Sans type',
                    'type_designation_id': str(designation_obj.type_designation.id) if designation_obj.type_designation else '',
                    'stock_total': Decimal('0'),
                    'stocks_par_magasin': [],
                }

            qty = stock.available_quantity if stock.available_quantity is not None else Decimal('0')
            qty = Decimal(str(qty))

            articles_map[desig_id]['stock_total'] += qty
            articles_map[desig_id]['stocks_par_magasin'].append({
                'base_id': str(stock.base.id),
                'magasin_nom': stock.base.nom_base,
                'quantite': qty,
            })

        accueil_articles = sorted(articles_map.values(), key=lambda a: (a['nom'] or '').lower())
        accueil_types_designation = sorted(
            { (article.get('type_designation_nom') or 'Sans type').strip() for article in accueil_articles },
            key=lambda v: v.lower()
        )

    # Si une désignation ET un magasin sont sélectionnés
    if designation_id and base_id:
        try:
            designation = Designation.objects.get(id=designation_id)
            base = bases.get(id=base_id)

            selected_magasin = magasins.filter(id=magasin_id).first() if magasin_id else None
            stock_item = None
            if not selected_magasin:
                stock_item = _filter_stocks_by_scope(
                    Stock.objects.filter(designation_id=designation_id, base_id=base_id).select_related('utilisateur'),
                    request.user
                ).first()

            plannings_scope = _filter_plannings_by_scope_inventory(
                Planning.objects.all(),
                request.user
            )
            plannings_scope_id_set = {
                str(planning_id) for planning_id in plannings_scope.values_list('id', flat=True)
            }

            selected_purchase_ids = set()
            selected_transfert_sortie_ids = set()
            selected_transfert_entree_ids = set()
            selected_bon_ids = set()
            selected_bon_numbers = set()
            selected_magasin_marker = ''
            if selected_magasin:
                selected_magasin_marker = f"Magasin ID: {selected_magasin.id}"
                selected_purchase_ids = {
                    str(purchase_id) for purchase_id in Purchase.objects.filter(
                        magasin_id=selected_magasin.id
                    ).values_list('id', flat=True)
                }
                selected_transfert_sortie_ids = {
                    str(transfert_id) for transfert_id in Transfert.objects.filter(
                        magasin_origine_id=selected_magasin.id
                    ).values_list('id', flat=True)
                }
                selected_transfert_entree_ids = {
                    str(transfert_id) for transfert_id in Transfert.objects.filter(
                        magasin_destination_id=selected_magasin.id
                    ).values_list('id', flat=True)
                }
                bons_magasin_qs = BonLivraison.objects.filter(
                    designation_id=designation_id,
                    planning__employe__base_id=base_id,
                    planning_id__in=plannings_scope.values('id')
                ).only('id', 'numero_bon', 'magasin')
                for bon in bons_magasin_qs:
                    if _match_magasin_label(bon.magasin, selected_magasin):
                        selected_bon_ids.add(str(bon.id))
                        if bon.numero_bon:
                            selected_bon_numbers.add(bon.numero_bon.strip())

            # Synchroniser les achats livrés/réceptionnés vers FicheStock (backfill si mouvements manquants)
            purchases_sync_qs = Purchase.objects.filter(
                purchase_items__designation_id=designation_id,
                purchase_status__in=['livre', 'recu']
            ).filter(
                Q(magasin__base_id=base_id) | Q(base_id=base_id)
            ).select_related(
                'magasin__base',
                'base',
                'fournisseur',
                'supplier',
                'ordered_by'
            ).prefetch_related(
                Prefetch(
                    'purchase_items',
                    queryset=PurchaseItem.objects.filter(designation_id=designation_id).select_related('designation')
                )
            ).distinct()

            if date_debut:
                purchases_sync_qs = purchases_sync_qs.filter(
                    Q(actual_delivery_date__gte=date_debut) |
                    Q(actual_delivery_date__isnull=True, purchase_date__gte=date_debut)
                )
            if date_fin:
                purchases_sync_qs = purchases_sync_qs.filter(
                    Q(actual_delivery_date__lte=date_fin) |
                    Q(actual_delivery_date__isnull=True, purchase_date__lte=date_fin)
                )
            if selected_magasin:
                purchases_sync_qs = purchases_sync_qs.filter(magasin_id=selected_magasin.id)

            for purchase in purchases_sync_qs:
                _sync_purchase_to_fiche_stock(purchase)

            # Synchroniser les bons livrés vers FicheStock (backfill si mouvements manquants)
            bons_sync_qs = BonLivraison.objects.filter(
                designation_id=designation_id,
                utilise=True,
                planning_id__in=plannings_scope.values('id')
            ).select_related(
                'planning',
                'planning__employe',
                'planning__ouvrage',
                'designation'
            )

            if date_debut:
                bons_sync_qs = bons_sync_qs.filter(
                    Q(date_utilisation__date__gte=date_debut) |
                    Q(date_utilisation__isnull=True, created_at__date__gte=date_debut)
                )
            if date_fin:
                bons_sync_qs = bons_sync_qs.filter(
                    Q(date_utilisation__date__lte=date_fin) |
                    Q(date_utilisation__isnull=True, created_at__date__lte=date_fin)
                )

            for bon in bons_sync_qs:
                if selected_magasin and not _match_magasin_label(bon.magasin, selected_magasin):
                    continue
                bon_base = _resolve_base_from_magasin_text(bon.magasin)
                if not bon_base and bon.planning and bon.planning.employe and bon.planning.employe.base_id:
                    bon_base = bon.planning.employe.base
                if bon_base and str(bon_base.id) == str(base_id):
                    _sync_bon_livraison_to_fiche_stock(bon)

            # Récupérer les fiches de stock avec les relations
            fiches_stock_base = FicheStock.objects.filter(
                designation_id=designation_id,
                base_id=base_id
            ).select_related(
                'designation',
                'base',
                'employee'
            )
            def _compute_stock_running(fiches_queryset):
                fiches_queryset = fiches_queryset.order_by('operation_date')

                bon_ids = set()
                bon_numbers = set()
                for fiche in fiches_queryset:
                    if fiche.operation_type not in ['livraison', 'retour_terrain']:
                        continue
                    if fiche.notes:
                        match = re.search(
                            r'BonLivraison\s*ID\s*:\s*([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})',
                            fiche.notes
                        )
                        if match:
                            bon_ids.add(match.group(1))
                    if fiche.reference:
                        bon_numbers.add(fiche.reference.strip())

                bons_lookup_by_id = {}
                bons_lookup_by_numero = {}
                if bon_ids or bon_numbers:
                    bons_lookup_qs = BonLivraison.objects.filter(
                        designation_id=designation_id
                    ).filter(
                        Q(id__in=bon_ids) | Q(numero_bon__in=bon_numbers)
                    ).select_related(
                        'planning',
                        'planning__ouvrage'
                    )
                    for bon in bons_lookup_qs:
                        bons_lookup_by_id[str(bon.id)] = bon
                        if bon.numero_bon:
                            bons_lookup_by_numero[bon.numero_bon.strip()] = bon

                stock_cumule_local = Decimal('0')
                fiches_local = []

                for fiche in fiches_queryset:
                    entree = Decimal('0')
                    sortie = Decimal('0')
                    inventaire = None
                    ecart = None

                    if fiche.operation_type == 'inventaire':
                        inventaire = Decimal(str(fiche.quantity)) if fiche.quantity else Decimal('0')
                        ecart = inventaire - stock_cumule_local
                        stock_cumule_local = inventaire
                    elif fiche.operation_type in ['achat', 'transfert_entree', 'entree', 'retour_terrain']:
                        entree = Decimal(str(fiche.quantity)) if fiche.quantity else Decimal('0')
                        stock_cumule_local += entree
                    elif fiche.operation_type in ['livraison', 'transfert_sortie', 'sortie']:
                        sortie = Decimal(str(fiche.quantity)) if fiche.quantity else Decimal('0')
                        stock_cumule_local -= sortie
                    elif fiche.operation_type == 'ajustement':
                        ajustement = Decimal(str(fiche.quantity)) if fiche.quantity else Decimal('0')
                        if ajustement >= 0:
                            entree = ajustement
                            stock_cumule_local += ajustement
                        else:
                            sortie = abs(ajustement)
                            stock_cumule_local -= sortie

                    ouvrage_nom = '-'
                    planning_id = None
                    if fiche.planning_detail_id:
                        try:
                            from apps.planning.models import PlanningDetail
                            planning_detail = PlanningDetail.objects.select_related('planning__ouvrage').get(id=fiche.planning_detail_id)
                            if planning_detail.planning:
                                planning_id = planning_detail.planning.id
                                if planning_detail.planning.ouvrage:
                                    ouvrage_nom = planning_detail.planning.ouvrage.nom_ouvrage or '-'
                        except PlanningDetail.DoesNotExist:
                            pass
                    elif fiche.operation_type in ['livraison', 'retour_terrain']:
                        bon = None
                        if fiche.notes:
                            match = re.search(
                                r'BonLivraison\s*ID\s*:\s*([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})',
                                fiche.notes
                            )
                            if match:
                                bon = bons_lookup_by_id.get(match.group(1))
                        if not bon and fiche.reference:
                            bon = bons_lookup_by_numero.get(fiche.reference.strip())
                        if bon and bon.planning:
                            planning_id = bon.planning.id
                            if bon.planning.ouvrage:
                                ouvrage_nom = bon.planning.ouvrage.nom_ouvrage or '-'

                    employe_nom = '-'
                    if fiche.employee:
                        employe_nom = getattr(fiche.employee, 'surnom', None) or getattr(fiche.employee, 'nom_complet', '-')

                    notes = fiche.notes or ''
                    notes = re.sub(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', '', notes)
                    notes = re.sub(r'(Planning\s*(ID)?|Transfert|Achat)\s*:?\s*', '', notes, flags=re.IGNORECASE)
                    notes = notes.strip() or '-'

                    fiches_local.append({
                        'id': str(fiche.id),
                        'date': fiche.operation_date,
                        'type': fiche.get_operation_type_display() if hasattr(fiche, 'get_operation_type_display') else fiche.operation_type,
                        'reference': fiche.reference or '-',
                        'ouvrage': ouvrage_nom,
                        'employe': employe_nom,
                        'planning_id': str(planning_id) if planning_id else None,
                        'transfert_id': str(fiche.transfert_id) if fiche.transfert_id else None,
                        'purchase_id': str(fiche.purchase_id) if fiche.purchase_id else None,
                        'entree': entree,
                        'sortie': sortie,
                        'inventaire': inventaire,
                        'ecart': ecart,
                        'stock': stock_cumule_local,
                        'notes': notes
                    })

                return fiches_local, stock_cumule_local

            def _build_magasin_filtered_queryset(magasin_obj):
                magasin_purchase_ids = {
                    str(purchase_id) for purchase_id in Purchase.objects.filter(
                        magasin_id=magasin_obj.id
                    ).values_list('id', flat=True)
                }
                magasin_transfert_sortie_ids = {
                    str(transfert_id) for transfert_id in Transfert.objects.filter(
                        magasin_origine_id=magasin_obj.id
                    ).values_list('id', flat=True)
                }
                magasin_transfert_entree_ids = {
                    str(transfert_id) for transfert_id in Transfert.objects.filter(
                        magasin_destination_id=magasin_obj.id
                    ).values_list('id', flat=True)
                }
                magasin_bon_ids = set()
                magasin_bon_numbers = set()
                bons_magasin_qs = BonLivraison.objects.filter(
                    designation_id=designation_id,
                    planning__employe__base_id=base_id,
                    planning_id__in=plannings_scope.values('id')
                ).only('id', 'numero_bon', 'magasin')
                for bon in bons_magasin_qs:
                    if _match_magasin_label(bon.magasin, magasin_obj):
                        magasin_bon_ids.add(str(bon.id))
                        if bon.numero_bon:
                            magasin_bon_numbers.add(bon.numero_bon.strip())

                livraison_q = Q(pk__in=[])
                for bon_id in magasin_bon_ids:
                    livraison_q |= Q(notes__icontains=f"BonLivraison ID: {bon_id}")
                if magasin_bon_numbers:
                    livraison_q |= Q(reference__in=magasin_bon_numbers)
                    for bon_num in magasin_bon_numbers:
                        livraison_q |= Q(notes__icontains=bon_num)

                magasin_marker = f"Magasin ID: {magasin_obj.id}"
                magasin_name_marker = f"Magasin: {magasin_obj.nom_magasin}"
                queryset = fiches_stock_base.filter(
                    (Q(operation_type='achat') & Q(purchase_id__in=magasin_purchase_ids)) |
                    (Q(operation_type='transfert_sortie') & Q(transfert_id__in=magasin_transfert_sortie_ids)) |
                    (Q(operation_type='transfert_entree') & Q(transfert_id__in=magasin_transfert_entree_ids)) |
                    (Q(operation_type='livraison') & livraison_q) |
                    (Q(operation_type='retour_terrain') & (livraison_q | Q(notes__icontains=magasin_marker) | Q(notes__icontains=magasin_name_marker))) |
                    (Q(operation_type='inventaire') & Q(notes__icontains=magasin_marker))
                )
                return queryset, magasin_marker

            fiches_stock = fiches_stock_base
            if selected_magasin:
                fiches_stock, selected_magasin_marker = _build_magasin_filtered_queryset(selected_magasin)

            if date_debut:
                fiches_stock = fiches_stock.filter(operation_date__gte=date_debut)
            if date_fin:
                fiches_stock = fiches_stock.filter(operation_date__lte=date_fin)

            fiches, stock_actuel = _compute_stock_running(fiches_stock)

            if not selected_magasin:
                mode_tous_magasins = True
                fiches_par_magasin = []
                stock_actuel_total = Decimal('0')

                for magasin_obj in magasins.filter(base_id=base_id).order_by('nom_magasin'):
                    magasin_qs, _magasin_marker = _build_magasin_filtered_queryset(magasin_obj)
                    if date_debut:
                        magasin_qs = magasin_qs.filter(operation_date__gte=date_debut)
                    if date_fin:
                        magasin_qs = magasin_qs.filter(operation_date__lte=date_fin)

                    fiches_magasin, stock_magasin = _compute_stock_running(magasin_qs)
                    stock_actuel_total += stock_magasin

                    fiches_par_magasin.append({
                        'is_group_header': True,
                        'magasin': magasin_obj.nom_magasin,
                        'stock_magasin': stock_magasin,
                        'row_count': len(fiches_magasin),
                    })

                    if fiches_magasin:
                        fiches_par_magasin.extend(fiches_magasin)
                    else:
                        fiches_par_magasin.append({
                            'is_group_empty': True,
                            'magasin': magasin_obj.nom_magasin,
                        })
                    fiche_group_count += 1

                fiches = fiches_par_magasin
                stock_actuel = stock_actuel_total

            # Détection de stock non ventilé:
            # on compare le stock global base avec le stock strict du magasin sélectionné.
            if selected_magasin:
                fiches_stock_base_compare = fiches_stock_base
                if date_debut:
                    fiches_stock_base_compare = fiches_stock_base_compare.filter(operation_date__gte=date_debut)
                if date_fin:
                    fiches_stock_base_compare = fiches_stock_base_compare.filter(operation_date__lte=date_fin)

                stock_base_cumule = Decimal('0')
                for fiche_base in fiches_stock_base_compare.order_by('operation_date'):
                    qty_base = Decimal(str(fiche_base.quantity)) if fiche_base.quantity else Decimal('0')

                    if fiche_base.operation_type == 'inventaire':
                        stock_base_cumule = qty_base
                    elif fiche_base.operation_type in ['achat', 'transfert_entree', 'entree', 'retour_terrain']:
                        stock_base_cumule += qty_base
                    elif fiche_base.operation_type in ['livraison', 'transfert_sortie', 'sortie']:
                        stock_base_cumule -= qty_base
                    elif fiche_base.operation_type == 'ajustement':
                        stock_base_cumule += qty_base

                stock_global_base = stock_base_cumule
                stock_non_ventile_ecart = stock_base_cumule - stock_actuel
                stock_non_ventile = stock_non_ventile_ecart != 0

            # Récupérer le dernier inventaire
            dernier_inventaire = FicheStock.objects.filter(
                designation_id=designation_id,
                base_id=base_id,
                operation_type='inventaire'
            )
            if selected_magasin:
                dernier_inventaire = dernier_inventaire.filter(notes__icontains=selected_magasin_marker)
            dernier_inventaire = dernier_inventaire.order_by('-operation_date').first()

            # Inventaires (source)
            inventaires_qs = FicheStock.objects.filter(
                designation_id=designation_id,
                base_id=base_id,
                operation_type='inventaire'
            ).select_related('employee').order_by('-operation_date')
            if selected_magasin:
                inventaires_qs = inventaires_qs.filter(notes__icontains=selected_magasin_marker)

            if date_debut:
                inventaires_qs = inventaires_qs.filter(operation_date__date__gte=date_debut)
            if date_fin:
                inventaires_qs = inventaires_qs.filter(operation_date__date__lte=date_fin)

            magasins_map = {
                str(magasin_obj.id): magasin_obj.nom_magasin
                for magasin_obj in magasins.filter(base_id=base_id)
            }
            magasins_name_lookup = {
                (magasin_nom or '').strip().lower(): magasin_nom
                for magasin_nom in magasins_map.values()
                if magasin_nom
            }
            base_name_normalized = (base.nom_base or '').strip().lower() if base else ''
            base_name_with_prefix = f"base {base_name_normalized}" if base_name_normalized else ''

            def _normalize_magasin_display(raw_value):
                if selected_magasin:
                    return selected_magasin.nom_magasin

                if not raw_value:
                    return 'Non ventilé (base)'

                value = str(raw_value).strip()
                if not value:
                    return 'Non ventilé (base)'

                try:
                    value_uuid = str(uuid.UUID(value))
                    if value_uuid in magasins_map:
                        return magasins_map[value_uuid]
                except (ValueError, TypeError):
                    pass

                normalized = value.lower().strip()
                if normalized.startswith('base '):
                    normalized = normalized[5:].strip()

                if normalized in magasins_name_lookup:
                    return magasins_name_lookup[normalized]
                if base_name_normalized and normalized == base_name_normalized:
                    return 'Non ventilé (base)'
                if base_name_with_prefix and normalized == base_name_with_prefix:
                    return 'Non ventilé (base)'

                return 'Non ventilé (base)'

            def _extract_inventaire_magasin(notes_value):
                if selected_magasin:
                    return selected_magasin.nom_magasin

                if not notes_value:
                    return 'Non ventilé (base)'

                magasin_id_match = re.search(
                    r'Magasin ID\s*:\s*([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})',
                    notes_value
                )
                if magasin_id_match:
                    magasin_nom = magasins_map.get(magasin_id_match.group(1))
                    if magasin_nom:
                        return magasin_nom

                magasin_nom_match = re.search(r'Magasin\s*:\s*([^|]+)', notes_value)
                if magasin_nom_match:
                    magasin_nom = magasin_nom_match.group(1).strip()
                    if magasin_nom:
                        return _normalize_magasin_display(magasin_nom)

                return 'Non ventilé (base)'

            inventaires = [
                {
                    'id': str(inv.id),
                    'date': inv.operation_date,
                    'quantity': inv.quantity,
                    'employee': inv.employee.nom_complet if inv.employee else '-',
                    'reference': inv.reference or '-',
                    'magasin': _extract_inventaire_magasin(inv.notes or ''),
                    'notes': inv.notes or '-',
                }
                for inv in inventaires_qs
            ]

            # Achats (source)
            achats_qs = PurchaseItem.objects.filter(
                designation_id=designation_id
            ).select_related(
                'purchase',
                'purchase__fournisseur',
                'purchase__supplier',
                'purchase__magasin',
                'purchase__base'
            ).filter(
                Q(purchase__magasin__base_id=base_id) | Q(purchase__base_id=base_id)
            )

            if date_debut:
                achats_qs = achats_qs.filter(purchase__purchase_date__gte=date_debut)
            if date_fin:
                achats_qs = achats_qs.filter(purchase__purchase_date__lte=date_fin)
            if magasin_id:
                achats_qs = achats_qs.filter(purchase__magasin_id=magasin_id)

            achats = []
            for item in achats_qs:
                purchase = item.purchase
                fournisseur = '-'
                if purchase:
                    if purchase.fournisseur:
                        fournisseur = purchase.fournisseur.nom_fournisseur
                    elif purchase.supplier:
                        fournisseur = purchase.supplier.supplier_name
                magasin = '-'
                if purchase:
                    if purchase.magasin:
                        magasin = purchase.magasin.nom_magasin
                    else:
                        magasin = 'Non ventilé (base)'
                quantite = item.quantity_received if item.quantity_received else item.quantity_ordered
                achats.append({
                    'date': purchase.purchase_date if purchase else None,
                    'numero': purchase.purchase_number if purchase else '-',
                    'fournisseur': fournisseur,
                    'magasin': magasin,
                    'purchase_id': str(purchase.id) if purchase else None,
                    'quantite': quantite,
                    'pu': item.unit_price,
                    'montant': item.total_price,
                    'statut_code': purchase.purchase_status if purchase else '',
                    'statut': purchase.get_purchase_status_display() if purchase else '-',
                })

            # Transferts (source)
            transferts_qs = TransfertItem.objects.filter(
                designation_id=designation_id
            ).select_related(
                'transfert',
                'transfert__magasin_origine',
                'transfert__magasin_destination'
            ).filter(
                Q(transfert__magasin_origine__base_id=base_id) | Q(transfert__magasin_destination__base_id=base_id)
            )

            if date_debut:
                transferts_qs = transferts_qs.filter(transfert__transfer_date__date__gte=date_debut)
            if date_fin:
                transferts_qs = transferts_qs.filter(transfert__transfer_date__date__lte=date_fin)
            if magasin_id:
                transferts_qs = transferts_qs.filter(
                    Q(transfert__magasin_origine_id=magasin_id) | Q(transfert__magasin_destination_id=magasin_id)
                )

            transferts = []
            for item in transferts_qs:
                transfert = item.transfert
                direction = '-'
                if transfert:
                    if transfert.magasin_origine and str(transfert.magasin_origine.base_id) == str(base_id):
                        direction = 'Sortant'
                    elif transfert.magasin_destination and str(transfert.magasin_destination.base_id) == str(base_id):
                        direction = 'Entrant'
                transferts.append({
                    'date': transfert.transfer_date if transfert else None,
                    'numero': transfert.transfer_number if transfert else '-',
                    'direction': direction,
                    'origine': str(transfert.magasin_origine) if transfert and transfert.magasin_origine else '-',
                    'destination': str(transfert.magasin_destination) if transfert and transfert.magasin_destination else '-',
                    'transfert_id': str(transfert.id) if transfert else None,
                    'quantite_envoyee': item.quantity_sent,
                    'quantite_recue': item.quantity_received,
                    'statut_code': transfert.status if transfert else '',
                    'statut': transfert.get_status_display() if transfert else '-',
                })

            # Bons de livraison planning (source)
            # Inclure aussi les BL détectés depuis les lignes "livraison" déjà visibles
            # pour éviter les écarts entre la table de mouvements et la table source.
            livraison_bon_ids = set()
            livraison_bon_numbers = set()
            # Ne pas utiliser `only(...)` ici car `fiches_stock` hérite déjà d'un
            # `select_related(...)` sur des FK; Django lève un FieldError sinon.
            livraison_fiches_qs = fiches_stock.filter(operation_type__in=['livraison', 'retour_terrain'])
            for fiche_livraison in livraison_fiches_qs:
                if fiche_livraison.notes:
                    match = re.search(
                        r'BonLivraison\s*ID\s*:\s*([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})',
                        fiche_livraison.notes
                    )
                    if match:
                        livraison_bon_ids.add(match.group(1))
                if fiche_livraison.reference:
                    livraison_bon_numbers.add(fiche_livraison.reference.strip())

            bons_qs = BonLivraison.objects.filter(designation_id=designation_id).select_related(
                'planning',
                'planning__employe',
                'planning__ouvrage'
            )
            bons_scope_q = Q(
                planning__employe__base_id=base_id,
                planning_id__in=plannings_scope.values('id')
            )
            if livraison_bon_ids:
                bons_scope_q |= Q(id__in=livraison_bon_ids)
            if livraison_bon_numbers:
                bons_scope_q |= Q(numero_bon__in=livraison_bon_numbers)
            bons_qs = bons_qs.filter(bons_scope_q).distinct()
            if date_debut:
                bons_qs = bons_qs.filter(
                    Q(date_utilisation__date__gte=date_debut) |
                    Q(date_utilisation__isnull=True, created_at__date__gte=date_debut)
                )
            if date_fin:
                bons_qs = bons_qs.filter(
                    Q(date_utilisation__date__lte=date_fin) |
                    Q(date_utilisation__isnull=True, created_at__date__lte=date_fin)
                )

            bons_livraison = []
            bons_seen = set()
            for bon in bons_qs:
                bon_id_str = str(bon.id)
                bon_numero = (bon.numero_bon or '').strip()

                bon_in_scope = False
                if bon.planning_id and str(bon.planning_id) in plannings_scope_id_set:
                    bon_in_scope = bool(
                        bon.planning and bon.planning.employe_id and str(bon.planning.employe.base_id) == str(base_id)
                    )
                if not bon_in_scope:
                    bon_base = _resolve_base_from_magasin_text(bon.magasin)
                    bon_in_scope = bool(bon_base and str(bon_base.id) == str(base_id))
                if bon_id_str in livraison_bon_ids or (bon_numero and bon_numero in livraison_bon_numbers):
                    bon_in_scope = True

                if not bon_in_scope or bon_id_str in bons_seen:
                    continue
                if selected_magasin and not _match_magasin_label(bon.magasin, selected_magasin):
                    continue

                bons_seen.add(bon_id_str)
                date_livraison = bon.date_utilisation or bon.created_at
                ouvrage_nom = bon.planning.ouvrage.nom_ouvrage if bon.planning and bon.planning.ouvrage else '-'
                bons_livraison.append({
                    'id': bon_id_str,
                    'date': date_livraison,
                    'numero': bon.numero_bon or '-',
                    'ouvrage': ouvrage_nom,
                    'quantite': bon.quantite,
                    'magasin': _normalize_magasin_display(bon.magasin),
                    'statut': 'Livré' if bon.utilise else 'En attente',
                    'planning_id': str(bon.planning.id) if bon.planning else None,
                })

            from apps.accounting.models import BaseDiameX
            from .models_vehicles import UtilisationCarburantVehicule, Vehicule
            from .views_vehicles import _build_fuel_compta_map, _is_carburant_designation

            if _is_carburant_designation(designation):
                compta_entries_qs = BaseDiameX.objects.filter(
                    compte_code__in=['606100', '606107']
                )
                if getattr(base, 'volet', None):
                    compta_entries_qs = compta_entries_qs.filter(
                        Q(activ__iexact=base.volet) | Q(prog__iexact=base.volet)
                    )
                if date_debut:
                    compta_entries_qs = compta_entries_qs.filter(date_m__gte=date_debut)
                if date_fin:
                    compta_entries_qs = compta_entries_qs.filter(date_m__lte=date_fin)

                scoped_vehicules = _filter_vehicules_scope(
                    Vehicule.objects.select_related('employe_actuel__base'),
                    request.user
                ).filter(
                    Q(employe_actuel__base_id=base.id) |
                    Q(releves_compteur__employe__base_id=base.id) |
                    Q(utilisations_carburant__magasin__base_id=base.id)
                ).distinct()
                compta_fuel_map = _build_fuel_compta_map(compta_entries_qs, scoped_vehicules)
                compta_stock_entries = compta_fuel_map['stock_entries']

                stock_usage_qs = UtilisationCarburantVehicule.objects.select_related(
                    'vehicule', 'employe', 'magasin'
                ).filter(
                    source_type='stock',
                    designation_id=designation.id,
                ).filter(
                    Q(magasin__base_id=base.id) |
                    Q(employe__base_id=base.id) |
                    Q(vehicule__employe_actuel__base_id=base.id)
                )
                if selected_magasin:
                    stock_usage_qs = stock_usage_qs.filter(magasin_id=selected_magasin.id)
                if date_debut:
                    stock_usage_qs = stock_usage_qs.filter(date_utilisation__gte=date_debut)
                if date_fin:
                    stock_usage_qs = stock_usage_qs.filter(date_utilisation__lte=date_fin)

                compta_direct_by_vehicle = []
                vehicule_map = {veh.id: veh for veh in scoped_vehicules}
                for vehicule_id, row in compta_fuel_map['direct_by_vehicle'].items():
                    compta_direct_by_vehicle.append({
                        'vehicule': vehicule_map.get(vehicule_id),
                        'litres': row['litres'],
                        'montant': row['montant'],
                        'count': row['count'],
                    })

                carburant_stock_analysis = {
                    'enabled': True,
                    'compta_stock_litres': sum((row['litres'] for row in compta_stock_entries), Decimal('0')),
                    'compta_stock_montant': sum((row['montant'] for row in compta_stock_entries), Decimal('0')),
                    'compta_stock_count': len(compta_stock_entries),
                    'fiche_achats_litres': sum((Decimal(str(a.quantity or 0)) for a in achats), Decimal('0')),
                    'redistrib_stock_litres': sum((Decimal(str(row.quantite or 0)) for row in stock_usage_qs), Decimal('0')),
                    'redistrib_stock_montant': sum((Decimal(str(row.montant or 0)) for row in stock_usage_qs), Decimal('0')),
                    'direct_vehicle_litres': sum((row['litres'] for row in compta_direct_by_vehicle), Decimal('0')),
                    'direct_vehicle_montant': sum((row['montant'] for row in compta_direct_by_vehicle), Decimal('0')),
                    'direct_vehicle_count': sum((row['count'] for row in compta_direct_by_vehicle), 0),
                    'stock_usage_rows': list(stock_usage_qs.order_by('-date_utilisation', '-created_at')[:50]),
                    'compta_stock_entries': compta_stock_entries[:20],
                }
                carburant_stock_analysis['ecart_stock_litres'] = (
                    carburant_stock_analysis['compta_stock_litres'] - carburant_stock_analysis['redistrib_stock_litres']
                )

        except (Designation.DoesNotExist, Base.DoesNotExist):
            pass

    # Détecter s'il y a des stocks négatifs
    has_negative_stock = any(
        fiche.get('stock') is not None and fiche.get('stock') < 0
        for fiche in fiches
    )

    context = {
        'fiches': fiches,
        'designations': designations,
        'bases': bases,
        'magasins': magasins,
        'designation': designation,
        'base': base,
        'selected_magasin': selected_magasin,
        'stock_item': stock_item,
        'stock_actuel': stock_actuel,
        'stock_non_ventile': stock_non_ventile,
        'stock_global_base': stock_global_base,
        'stock_non_ventile_ecart': stock_non_ventile_ecart,
        'mode_tous_magasins': mode_tous_magasins,
        'fiche_group_count': fiche_group_count,
        'dernier_inventaire': dernier_inventaire,
        'inventaires': inventaires,
        'achats': achats,
        'transferts': transferts,
        'bons_livraison': bons_livraison,
        'has_negative_stock': has_negative_stock,
        'filters': {
            'designation_id': designation_id,
            'base_id': base_id,
            'magasin_id': magasin_id,
            'date_debut': date_debut,
            'date_fin': date_fin,
        },
        'accueil_articles': accueil_articles,
        'accueil_types_designation': accueil_types_designation,
        'accueil_view': accueil_view,
        'is_directeur_poste': is_directeur_poste,
        'can_delete_fiche_rows': can_delete_fiche_rows,
        'carburant_stock_analysis': carburant_stock_analysis,
        'title': 'Fiches de Stock'
    }

    return render(request, 'inventory/fiche_stock_list.html', context)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def fiche_stock_delete(request, fiche_id):
    """Supprimer une fiche de stock"""
    from .models import FicheStock

    try:
        if not _can_delete_fiche_stock_rows(request.user):
            return JsonResponse({
                'success': False,
                'error': 'Permission refusée pour supprimer cette ligne.'
            }, status=403)

        scoped_bases = _filter_bases_by_scope(Base.objects.all(), request.user)
        fiche = get_object_or_404(
            FicheStock.objects.filter(base_id__in=scoped_bases.values('id')),
            id=fiche_id
        )

        # Sauvegarder les infos avant suppression pour le message
        operation_type = fiche.get_operation_type_display()
        item_name = fiche.designation.nom if fiche.designation else 'Inconnu'

        fiche.delete()

        return JsonResponse({
            'success': True,
            'message': f'Fiche de stock supprimée : {operation_type} - {item_name}'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def stock_summary(request):
    """Vue résumé des stocks par base avec ventilation réelle par magasin"""
    from apps.organization.models import Base, Magasin
    from apps.planning.models import TypeDesignation, Planning, BonLivraison
    from .models import FicheStock, Purchase, Transfert
    from decimal import Decimal
    from collections import defaultdict

    base_id = request.GET.get('base')
    magasin_id = request.GET.get('magasin', '')
    view_mode = request.GET.get('view', 'table')
    search = request.GET.get('search', '').strip()
    type_designation_id = request.GET.get('type_designation', '')

    bases = _filter_bases_by_scope(Base.objects.all(), request.user).order_by('nom_base')
    types_designation = TypeDesignation.objects.all().order_by('nom')

    selected_base = None
    if base_id:
        try:
            selected_base = bases.get(id=base_id)
        except Base.DoesNotExist:
            pass

    if not selected_base and bases.exists():
        selected_base = bases.first()
        base_id = str(selected_base.id)

    magasins = Magasin.objects.none()
    if selected_base:
        magasins = Magasin.objects.filter(base=selected_base).order_by('nom_magasin')

    stocks_by_type = []

    if selected_base:
        stocks_qs = _filter_stocks_by_scope(
            Stock.objects.filter(
                base=selected_base,
                designation__isnull=False
            ),
            request.user
        ).select_related('designation', 'designation__type_designation')

        if search:
            stocks_qs = stocks_qs.filter(
                Q(designation__nom__icontains=search) |
                Q(designation__type_designation__nom__icontains=search)
            )
        if type_designation_id:
            stocks_qs = stocks_qs.filter(designation__type_designation_id=type_designation_id)

        stocks_list = list(
            stocks_qs.order_by('designation__type_designation__nom', 'designation__nom')
        )

        selected_magasin = None
        if magasin_id:
            selected_magasin = magasins.filter(id=magasin_id).first()
            if not selected_magasin:
                magasin_id = ''

        designation_ids = [stock.designation_id for stock in stocks_list if stock.designation_id]
        plannings_scope = _filter_plannings_by_scope_inventory(
            Planning.objects.all(),
            request.user
        )

        def _compute_strict_stock_for_magasin(magasin_obj, designation_ids_local):
            designation_ids_local = [designation_id for designation_id in designation_ids_local if designation_id]
            computed_stock_by_designation = defaultdict(lambda: Decimal('0'))
            has_magasin_movement = defaultdict(bool)

            if not designation_ids_local:
                return computed_stock_by_designation, has_magasin_movement

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

            bons_qs = BonLivraison.objects.filter(
                designation_id__in=designation_ids_local,
                planning__employe__base_id=selected_base.id,
                planning_id__in=plannings_scope.values('id')
            ).only('id', 'designation_id', 'numero_bon', 'magasin')

            bon_ids_by_designation = defaultdict(set)
            bon_nums_by_designation = defaultdict(set)
            for bon in bons_qs:
                if _match_magasin_label(bon.magasin, magasin_obj):
                    designation_key = str(bon.designation_id)
                    bon_ids_by_designation[designation_key].add(str(bon.id))
                    if bon.numero_bon:
                        bon_nums_by_designation[designation_key].add(bon.numero_bon.strip())

            fiches_qs = FicheStock.objects.filter(
                designation_id__in=designation_ids_local,
                base_id=selected_base.id
            ).only(
                'designation_id',
                'operation_type',
                'quantity',
                'purchase_id',
                'transfert_id',
                'reference',
                'notes',
                'operation_date'
            ).order_by('designation_id', 'operation_date')

            magasin_id_marker = f"Magasin ID: {magasin_obj.id}"
            magasin_name_marker = f"Magasin: {magasin_obj.nom_magasin}"

            for fiche in fiches_qs:
                designation_key = str(fiche.designation_id)
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
                    bon_ids = bon_ids_by_designation.get(designation_key, set())
                    bon_nums = bon_nums_by_designation.get(designation_key, set())
                    include = any(f"BonLivraison ID: {bon_id}" in notes_value for bon_id in bon_ids)
                    if not include and reference_value:
                        include = reference_value in bon_nums
                    if not include and bon_nums:
                        include = any(bon_num in notes_value for bon_num in bon_nums)
                elif operation == 'retour_terrain':
                    bon_ids = bon_ids_by_designation.get(designation_key, set())
                    bon_nums = bon_nums_by_designation.get(designation_key, set())
                    include = any(f"BonLivraison ID: {bon_id}" in notes_value for bon_id in bon_ids)
                    if not include and reference_value:
                        include = reference_value in bon_nums
                    if not include and bon_nums:
                        include = any(bon_num in notes_value for bon_num in bon_nums)
                    if not include:
                        include = magasin_id_marker in notes_value or magasin_name_marker in notes_value
                elif operation in ['inventaire', 'entree', 'sortie', 'ajustement']:
                    include = magasin_id_marker in notes_value or magasin_name_marker in notes_value

                if not include:
                    continue

                has_magasin_movement[designation_key] = True
                qty = Decimal(str(fiche.quantity or 0))
                if operation == 'inventaire':
                    computed_stock_by_designation[designation_key] = qty
                elif operation in ['achat', 'transfert_entree', 'entree', 'retour_terrain']:
                    computed_stock_by_designation[designation_key] += qty
                elif operation in ['livraison', 'transfert_sortie', 'sortie']:
                    computed_stock_by_designation[designation_key] -= qty
                elif operation == 'ajustement':
                    computed_stock_by_designation[designation_key] += qty

            return computed_stock_by_designation, has_magasin_movement

        designations_dict = {}
        for stock in stocks_list:
            desig_key = str(stock.designation.id)
            designations_dict[desig_key] = {
                'designation_id': desig_key,
                'designation_nom': stock.designation.nom,
                'designation_unite': stock.designation.unite or '',
                'designation_photo': stock.designation.photo_url or '',
                'type_designation_nom': stock.designation.type_designation.nom if stock.designation.type_designation else 'Sans type',
                'type_designation_id': str(stock.designation.type_designation.id) if stock.designation.type_designation else None,
                'stock_total': float(stock.current_quantity or 0),
                'magasins': []
            }

        if selected_magasin:
            computed_stock, has_movement = _compute_strict_stock_for_magasin(
                selected_magasin,
                designation_ids
            )
            filtered_designations = {}
            for desig_key, desig_data in designations_dict.items():
                if desig_key not in has_movement:
                    continue
                qty = computed_stock.get(desig_key, Decimal('0'))
                desig_data['stock_total'] = float(qty)
                desig_data['magasins'] = [{
                    'magasin_id': str(selected_magasin.id),
                    'magasin_nom': selected_magasin.nom_magasin,
                    'quantite': float(qty),
                }]
                filtered_designations[desig_key] = desig_data
            designations_dict = filtered_designations
        else:
            ventilated_qty_by_designation = defaultdict(lambda: Decimal('0'))
            magasins_by_designation = defaultdict(list)

            for magasin_obj in magasins:
                computed_stock, has_movement = _compute_strict_stock_for_magasin(
                    magasin_obj,
                    designation_ids
                )
                for designation_id in designation_ids:
                    desig_key = str(designation_id)
                    if desig_key not in has_movement:
                        continue

                    qty = computed_stock.get(desig_key, Decimal('0'))
                    ventilated_qty_by_designation[desig_key] += qty
                    magasins_by_designation[desig_key].append({
                        'magasin_id': str(magasin_obj.id),
                        'magasin_nom': magasin_obj.nom_magasin,
                        'quantite': float(qty),
                    })

            for desig_key, desig_data in designations_dict.items():
                base_qty = Decimal(str(desig_data['stock_total'] or 0))
                ventilated_qty = ventilated_qty_by_designation.get(desig_key, Decimal('0'))
                non_ventile_qty = base_qty - ventilated_qty

                magasins_rows = magasins_by_designation.get(desig_key, [])
                if non_ventile_qty != 0:
                    magasins_rows.append({
                        'magasin_id': '',
                        'magasin_nom': 'Non ventilé (base)',
                        'quantite': float(non_ventile_qty),
                    })

                magasins_rows.sort(
                    key=lambda item: (
                        item.get('magasin_nom') == 'Non ventilé (base)',
                        (item.get('magasin_nom') or '').lower(),
                    )
                )
                desig_data['magasins'] = magasins_rows

        stocks_by_type_dict = defaultdict(list)
        for desig_data in designations_dict.values():
            stocks_by_type_dict[desig_data['type_designation_nom']].append(desig_data)

        stocks_by_type = [
            {
                'type_nom': type_nom,
                'stocks': sorted(stocks, key=lambda x: x['designation_nom']),
            }
            for type_nom, stocks in sorted(stocks_by_type_dict.items())
        ]

    context = {
        'stocks_by_type': stocks_by_type,
        'bases': bases,
        'magasins': magasins,
        'selected_base': selected_base,
        'selected_magasin': magasin_id,
        'view_mode': view_mode,
        'search': search,
        'types_designation': types_designation,
        'selected_type_designation': type_designation_id,
        'title': 'Résumé des Stocks'
    }

    return render(request, 'inventory/stock_summary.html', context)


@login_required
def fiche_stock_equipement(request, equipement_id):
    """
    Vue pour afficher la fiche de stock d'un équipement spécifique
    """
    from apps.infrastructure.models import EquipementConstitutif

    # Récupérer l'équipement
    equipement = get_object_or_404(EquipementConstitutif, id=equipement_id)

    # Récupérer ou créer le stock
    stock, created = Stock.objects.get_or_create(
        equipement=equipement,
        defaults={'quantite_actuelle': 0, 'seuil_alerte': 10}
    )

    # Récupérer les mouvements de stock (20 derniers)
    mouvements = StockMovement.objects.filter(
        stock=stock
    ).select_related(
        'effectue_par', 'fournisseur', 'planning_detail'
    ).order_by('-created_at')[:20]

    context = {
        'equipement': equipement,
        'stock': stock,
        'mouvements': mouvements,
        'title': f'Fiche de stock - {equipement.nom}'
    }

    return render(request, 'inventory/fiche_stock_equipement.html', context)


@login_required
@require_http_methods(["GET"])
def api_fiche_stock_ouvrages(request):
    q = (request.GET.get('q') or '').strip()
    from apps.organization.models import Ouvrage
    from apps.planning.models import Planning

    plannings_scope = _filter_plannings_by_scope_inventory(
        Planning.objects.filter(date__isnull=False),
        request.user
    )
    ouvrages = Ouvrage.objects.filter(
        id__in=plannings_scope.values('ouvrage_id')
    ).distinct()
    if q:
        ouvrages = ouvrages.filter(nom_ouvrage__icontains=q)
    ouvrages = ouvrages.order_by('nom_ouvrage')[:50]

    return JsonResponse({
        'success': True,
        'ouvrages': [
            {'id': str(o.id), 'nom': o.nom_ouvrage}
            for o in ouvrages
        ]
    })


@login_required
@require_http_methods(["GET"])
def api_fiche_stock_plannings_for_ouvrage(request, ouvrage_id):
    from apps.planning.models import Planning

    plannings = _filter_plannings_by_scope_inventory(
        Planning.objects.filter(
            ouvrage_id=ouvrage_id,
            date__isnull=False
        ),
        request.user
    ).select_related('employe').order_by('-date')[:100]

    return JsonResponse({
        'success': True,
        'plannings': [
            {
                'id': str(p.id),
                'date': p.date.strftime('%Y-%m-%d') if p.date else '',
                'employe': p.employe.nom_affichage if p.employe else ''
            }
            for p in plannings
        ]
    })


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def api_fiche_stock_bon_livraison_save(request):
    from apps.planning.models import BonLivraison, Planning

    try:
        payload = json.loads(request.body or '{}')
        bon_id = payload.get('id')
        planning_id = payload.get('planning_id')
        designation_id = payload.get('designation_id')
        quantite = payload.get('quantite')
        magasin = payload.get('magasin', '')
        numero_bon = payload.get('numero_bon', '')
        statut = payload.get('statut', 'en_attente')
        date_utilisation = payload.get('date_utilisation')

        if not planning_id or not designation_id or not quantite:
            return JsonResponse({'success': False, 'error': 'planning, designation et quantite requis'}, status=400)

        plannings_scope = _filter_plannings_by_scope_inventory(Planning.objects.all(), request.user)
        planning = plannings_scope.filter(id=planning_id).first()
        if not planning:
            return JsonResponse({'success': False, 'error': 'Planning introuvable ou non autorise'}, status=403)

        if bon_id:
            bon = BonLivraison.objects.filter(
                id=bon_id,
                planning_id__in=plannings_scope.values('id')
            ).first()
            if not bon:
                return JsonResponse({'success': False, 'error': 'Bon de livraison introuvable'}, status=404)
        else:
            bon = BonLivraison()

        bon.planning = planning
        bon.designation_id = designation_id
        bon.quantite = float(quantite)
        bon.magasin = magasin or ''

        if not numero_bon:
            today = datetime.now().strftime('%Y%m%d')
            prefix = f'BL-{today}-'
            last = BonLivraison.objects.filter(numero_bon__startswith=prefix).count() + 1
            numero_bon = f'{prefix}{last:03d}'
        bon.numero_bon = numero_bon

        bon.utilise = (statut == 'livre')
        if bon.utilise and date_utilisation:
            try:
                bon.date_utilisation = datetime.fromisoformat(date_utilisation)
            except ValueError:
                bon.date_utilisation = None
        elif not bon.utilise:
            bon.date_utilisation = None

        bon.save()

        # Synchroniser automatiquement la fiche de stock dès qu'un bon passe en livré
        if bon.utilise:
            _sync_bon_livraison_to_fiche_stock(bon)

        return JsonResponse({'success': True, 'id': str(bon.id)})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def api_fiche_stock_retour_terrain_save(request):
    from apps.planning.models import Designation
    from .models import FicheStock

    try:
        payload = json.loads(request.body or '{}')
        retour_id = payload.get('id')
        designation_id = payload.get('designation_id')
        base_id = payload.get('base_id')
        magasin_id = payload.get('magasin_id')
        quantite = payload.get('quantite')
        date_operation = payload.get('date_operation')
        reference = (payload.get('reference') or '').strip()
        notes_text = (payload.get('notes') or '').strip()

        if not designation_id or not base_id or not quantite:
            return JsonResponse({'success': False, 'error': 'article, base et quantite requis'}, status=400)

        try:
            quantite_val = Decimal(str(quantite))
        except Exception:
            return JsonResponse({'success': False, 'error': 'quantite invalide'}, status=400)

        if quantite_val <= 0:
            return JsonResponse({'success': False, 'error': 'La quantite doit etre positive'}, status=400)

        designation = Designation.objects.filter(id=designation_id).first()
        base = _filter_bases_by_scope(Base.objects.all(), request.user).filter(id=base_id).first()
        if not designation or not base:
            return JsonResponse({'success': False, 'error': 'Article ou base introuvable'}, status=404)

        selected_magasin = None
        if magasin_id:
            selected_magasin = Magasin.objects.filter(
                id=magasin_id,
                base_id=base.id
            ).first()
            if not selected_magasin:
                return JsonResponse({'success': False, 'error': 'Magasin introuvable pour cette base'}, status=404)

        operation_date = timezone.now()
        if date_operation:
            try:
                parsed_date = datetime.fromisoformat(date_operation)
                if timezone.is_naive(parsed_date):
                    parsed_date = timezone.make_aware(parsed_date, timezone.get_current_timezone())
                operation_date = parsed_date
            except ValueError:
                return JsonResponse({'success': False, 'error': 'Date invalide'}, status=400)

        notes = 'Retour terrain (sans bon)'
        if reference:
            notes = f'{notes} | Référence: {reference}'
        if notes_text:
            notes = f'{notes} | {notes_text}'
        if selected_magasin:
            notes = (
                f'{notes} | Magasin ID: {selected_magasin.id} | '
                f'Magasin: {selected_magasin.nom_magasin}'
            )

        if retour_id:
            retour = FicheStock.objects.filter(
                id=retour_id,
                operation_type='retour_terrain',
                designation_id=designation.id,
                base_id=base.id
            ).first()
            if not retour:
                return JsonResponse({'success': False, 'error': 'Retour terrain introuvable'}, status=404)

            retour.operation_date = operation_date
            retour.quantity = quantite_val
            retour.reference = reference or None
            retour.notes = notes
            retour.employee = request.user.employe if hasattr(request.user, 'employe') else None
            retour.save(update_fields=['operation_date', 'quantity', 'reference', 'notes', 'employee', 'updated_at'])
            retour_id_out = str(retour.id)
        else:
            retour = FicheStock.objects.create(
                operation_date=operation_date,
                operation_type='retour_terrain',
                quantity=quantite_val,
                designation=designation,
                base=base,
                reference=reference or None,
                employee=request.user.employe if hasattr(request.user, 'employe') else None,
                notes=notes
            )
            retour_id_out = str(retour.id)

        _rebuild_stock_from_fiche_stock(designation.id, base.id)
        return JsonResponse({'success': True, 'id': retour_id_out})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["GET"])
def api_fiche_stock_bon_livraison_detail(request, bon_id):
    from apps.planning.models import BonLivraison, Planning

    plannings_scope_ids = set(
        _filter_plannings_by_scope_inventory(
            Planning.objects.all(),
            request.user
        ).values_list('id', flat=True)
    )
    scoped_base_ids = set(_filter_bases_by_scope(Base.objects.all(), request.user).values_list('id', flat=True))
    try:
        bon = BonLivraison.objects.select_related(
            'planning__ouvrage',
            'planning__employe',
            'designation'
        ).filter(id=bon_id).first()
        if not bon:
            return JsonResponse({'success': False, 'error': 'Bon de livraison introuvable'}, status=404)

        in_scope = False
        if bon.planning_id and bon.planning_id in plannings_scope_ids:
            in_scope = True
        elif bon.magasin:
            bon_base = _resolve_base_from_magasin_text(bon.magasin)
            if bon_base and bon_base.id in scoped_base_ids:
                in_scope = True
        if not in_scope:
            return JsonResponse({'success': False, 'error': 'Bon de livraison introuvable'}, status=404)

        return JsonResponse({
            'success': True,
            'bon': {
                'id': str(bon.id),
                'ouvrage_id': str(bon.planning.ouvrage_id) if bon.planning and bon.planning.ouvrage_id else '',
                'ouvrage': bon.planning.ouvrage.nom_ouvrage if bon.planning and bon.planning.ouvrage else '',
                'planning_id': str(bon.planning_id) if bon.planning_id else '',
                'designation_id': str(bon.designation_id) if bon.designation_id else '',
                'quantite': bon.quantite,
                'magasin': bon.magasin or '',
                'numero_bon': bon.numero_bon or '',
                'statut': 'livre' if bon.utilise else 'en_attente',
                'date_utilisation': bon.date_utilisation.date().isoformat() if bon.date_utilisation else '',
            }
        })
    except BonLivraison.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Bon de livraison introuvable'}, status=404)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def api_fiche_stock_bon_livraison_delete(request, bon_id):
    from apps.planning.models import BonLivraison, Planning

    if not _can_delete_fiche_stock_rows(request.user):
        return JsonResponse({
            'success': False,
            'error': 'Permission refusée pour supprimer ce bon de livraison.'
        }, status=403)

    plannings_scope_ids = set(
        _filter_plannings_by_scope_inventory(
            Planning.objects.all(),
            request.user
        ).values_list('id', flat=True)
    )
    scoped_base_ids = set(_filter_bases_by_scope(Base.objects.all(), request.user).values_list('id', flat=True))
    try:
        bon = BonLivraison.objects.select_related('planning__employe').filter(id=bon_id).first()
        if not bon:
            return JsonResponse({'success': False, 'error': 'Bon de livraison introuvable'}, status=404)

        in_scope = False
        if bon.planning_id and bon.planning_id in plannings_scope_ids:
            in_scope = True
        elif bon.magasin:
            bon_base = _resolve_base_from_magasin_text(bon.magasin)
            if bon_base and bon_base.id in scoped_base_ids:
                in_scope = True
        if not in_scope:
            return JsonResponse({'success': False, 'error': 'Bon de livraison introuvable'}, status=404)

        bon.delete()
        return JsonResponse({'success': True})
    except BonLivraison.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Bon de livraison introuvable'}, status=404)
