import json
import re
import uuid
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth import authenticate
from django.db import models, transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.core.auth_tokens import token_or_session_required
from apps.core.models import MobileRefreshToken, WidgetAuthToken
from apps.inventory import views as inventory_views
from apps.inventory import views_transferts
from apps.inventory.models import FicheStock, Purchase, Stock, Transfert
from apps.inventory.views import (
    _compute_strict_stock_for_magasin,
    _filter_bases_by_scope,
    _get_inventory_scope,
    _sync_purchase_inventory,
)
from apps.inventory.views_purchases import _filter_purchases_by_scope
from apps.inventory.views_transferts import _filter_transferts_by_scope
from apps.organization.models import Base, Magasin
from apps.planning.models import Designation, Planning, TypeDesignation
from apps.planning.repair_classification import normalize_repair_text
from apps.messaging.repair_reminder import reparations_echues


ACCESS_LIFETIME = timedelta(minutes=15)
REFRESH_LIFETIME = timedelta(days=30)
mobile_v1_required = token_or_session_required(scope=WidgetAuthToken.SCOPE_MOBILE)


def _json_body(request):
    try:
        return json.loads(request.body.decode('utf-8') or '{}')
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _decimal_string(value):
    return Decimal(str(value or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP).to_eng_string()


def _cursor_now():
    return timezone.now().isoformat()


def _create_token_pair(user, device_id, device_label=''):
    now = timezone.now()
    access = WidgetAuthToken.objects.create(
        user=user,
        scope=WidgetAuthToken.SCOPE_MOBILE,
        device_label=device_label[:120],
        expires_at=now + ACCESS_LIFETIME,
    )
    refresh = MobileRefreshToken.objects.create(
        user=user,
        device_id=device_id,
        device_label=device_label[:120],
        expires_at=now + REFRESH_LIFETIME,
    )
    return {
        'access_token': access.key,
        'refresh_token': refresh.key,
        'token_type': 'Bearer',
        'expires_in': int(ACCESS_LIFETIME.total_seconds()),
    }


def _capabilities_for(user):
    has_inventory_scope = _get_inventory_scope(user) != 'none'

    def allowed(permission, fallback=False):
        return bool(user.is_superuser or user.has_perm(permission) or fallback)

    values = {
        'stock.read': allowed('inventory.view_stock', has_inventory_scope),
        'movement.read': allowed('inventory.view_stockmovement', has_inventory_scope),
        'purchase.read': allowed('inventory.view_purchase', has_inventory_scope),
        'purchase.create': allowed('inventory.add_purchase'),
        'purchase.receive': allowed('inventory.change_purchase'),
        'transfer.read': allowed('inventory.view_transfert', has_inventory_scope),
        'transfer.create': allowed('inventory.add_transfert'),
        'transfer.send': allowed('inventory.change_transfert'),
        'transfer.receive': allowed('inventory.change_transfert'),
        'transfer.cancel': allowed('inventory.change_transfert'),
        'inventory.create': allowed('inventory.add_fichestock'),
        'stock.adjust': allowed('inventory.change_stock'),
        'field_return.create': allowed('inventory.add_fichestock'),
        'document.read': has_inventory_scope,
    }
    return [{'code': code, 'allowed': value} for code, value in values.items()]


def _profile_payload(user):
    employe = getattr(user, 'employe', None)
    return {
        'id': str(user.pk),
        'username': user.get_username(),
        'display_name': (
            employe.nom_affichage if employe is not None
            else user.get_full_name() or user.get_username()
        ),
        'email': user.email or None,
        'employee_id': str(employe.id) if employe is not None else None,
        'base_id': str(employe.base_id) if employe is not None and employe.base_id else None,
        'inventory_scope': _get_inventory_scope(user),
    }


def _article_payload(designation):
    photo_url = designation.photo_url or None
    return {
        'id': str(designation.id),
        'code': designation.code_materiel or '',
        'designation': designation.nom,
        'description': designation.description or None,
        'type_id': str(designation.type_designation_id) if designation.type_designation_id else None,
        'unit': designation.unite or '',
        'unit_price': _decimal_string(designation.prix_unitaire) if designation.prix_unitaire is not None else None,
        'minimum_level': _decimal_string(designation.seuil_minimum),
        'nature': designation.nature_stock,
        'photo_url': photo_url,
        'active': designation.actif,
        'revision': 1,
        'deleted_at': None,
    }


def _status_for(quantity, minimum):
    if quantity <= 0:
        return 'OUT'
    if minimum is not None and quantity <= minimum:
        return 'LOW'
    return 'OK'


def _stock_positions_for(user, scoped_bases, scoped_magasins, stocks):
    positions = []
    magasins_by_base = {}
    for magasin in scoped_magasins:
        magasins_by_base.setdefault(str(magasin.base_id), []).append(magasin)

    stocks_by_base = {}
    for stock in stocks:
        stocks_by_base.setdefault(str(stock.base_id), []).append(stock)

    for base in scoped_bases:
        base_stocks = stocks_by_base.get(str(base.id), [])
        designation_ids = [stock.designation_id for stock in base_stocks if stock.designation_id]
        ventilated = {str(designation_id): Decimal('0') for designation_id in designation_ids}

        for magasin in magasins_by_base.get(str(base.id), []):
            quantities, inventory_dates, has_movement = _compute_strict_stock_for_magasin(
                user, magasin, designation_ids
            )
            for stock in base_stocks:
                key = str(stock.designation_id)
                if not has_movement.get(key):
                    continue
                quantity = Decimal(str(quantities.get(key, 0)))
                ventilated[key] += quantity
                minimum = stock.designation.seuil_minimum
                positions.append({
                    'id': f'{base.id}:{magasin.id}:{stock.designation_id}',
                    'stock_id': str(stock.id),
                    'article_id': key,
                    'base_id': str(base.id),
                    'magasin_id': str(magasin.id),
                    'current': _decimal_string(quantity),
                    'reserved': '0.00',
                    'available': _decimal_string(quantity),
                    'status': _status_for(quantity, minimum),
                    'inventory_date': inventory_dates.get(key).isoformat() if inventory_dates.get(key) else None,
                    'updated_at': stock.updated_at.isoformat(),
                    'revision': int(stock.updated_at.timestamp() * 1000),
                    'estimated': True,
                    'estimate_reason': 'Réservations non ventilées par magasin dans le schéma actuel',
                    'deleted_at': None,
                })

        for stock in base_stocks:
            key = str(stock.designation_id)
            non_ventile = Decimal(str(stock.current_quantity or 0)) - ventilated.get(key, Decimal('0'))
            if non_ventile == 0:
                continue
            minimum = stock.designation.seuil_minimum
            positions.append({
                'id': f'{base.id}:unallocated:{stock.designation_id}',
                'stock_id': str(stock.id),
                'article_id': key,
                'base_id': str(base.id),
                'magasin_id': None,
                'current': _decimal_string(non_ventile),
                'reserved': '0.00',
                'available': _decimal_string(non_ventile),
                'status': _status_for(non_ventile, minimum),
                'inventory_date': stock.inventory_date.isoformat() if stock.inventory_date else None,
                'updated_at': stock.updated_at.isoformat(),
                'revision': int(stock.updated_at.timestamp() * 1000),
                'estimated': True,
                'estimate_reason': 'Écart base moins mouvements ventilés ; validation requise avant mutation',
                'deleted_at': None,
            })
    return positions


def _movement_payloads(base_ids):
    """Recent canonical stock ledger rows available to the mobile history."""
    rows = (
        FicheStock.objects
        .select_related('designation', 'base')
        .filter(base_id__in=base_ids, designation__isnull=False)
        .order_by('-operation_date', '-created_at')[:500]
    )
    payload = []
    magasin_pattern = re.compile(r'Magasin ID:\s*([0-9a-fA-F-]{36})')
    for row in rows:
        notes = row.notes or ''
        magasin_match = magasin_pattern.search(notes)
        payload.append({
            'id': str(row.id),
            'article_id': str(row.designation_id),
            'base_id': str(row.base_id),
            'magasin_id': magasin_match.group(1) if magasin_match else None,
            'movement_date': row.operation_date.isoformat(),
            'movement_type': row.operation_type,
            'quantity': _decimal_string(row.quantity),
            'reference': row.reference or None,
            'notes': notes or None,
            'sync_status': 'SYNCED',
            'revision': int(row.updated_at.timestamp() * 1000),
            'deleted_at': None,
        })
    return payload


def _purchase_payloads(user):
    purchases = (
        _filter_purchases_by_scope(
            Purchase.objects.select_related(
                'magasin__base', 'fournisseur', 'supplier', 'ordered_by'
            ).prefetch_related('purchase_items__designation'),
            user,
        )
        .exclude(purchase_status__in=['recu', 'annule'])
        .order_by('-purchase_date', '-created_at')[:200]
    )
    can_receive = bool(user.is_superuser or user.has_perm('inventory.change_purchase'))
    payload = []
    for purchase in purchases:
        supplier_name = ''
        if purchase.fournisseur:
            supplier_name = purchase.fournisseur.nom_fournisseur
        elif purchase.supplier:
            supplier_name = purchase.supplier.supplier_name
        payload.append({
            'id': str(purchase.id),
            'number': purchase.purchase_number,
            'purchase_date': purchase.purchase_date.isoformat(),
            'supplier_name': supplier_name,
            'magasin_id': str(purchase.magasin_id) if purchase.magasin_id else None,
            'status': purchase.purchase_status,
            'total_ariary': int(Decimal(str(purchase.total_amount or 0)).quantize(Decimal('1'))),
            'allowed_actions': ['receive'] if can_receive and purchase.magasin_id else [],
            'revision': int(purchase.updated_at.timestamp() * 1000),
            'deleted_at': None,
            'items': [
                {
                    'id': str(item.id),
                    'article_id': str(item.designation_id),
                    'ordered_quantity': _decimal_string(item.quantity_ordered),
                    'received_quantity': _decimal_string(item.quantity_received),
                    'unit_price_ariary': int(Decimal(str(item.unit_price or 0)).quantize(Decimal('1'))),
                    'revision': int(item.updated_at.timestamp() * 1000),
                    'deleted_at': None,
                }
                for item in purchase.purchase_items.all()
                if item.designation_id
            ],
        })
    return payload


def _operation_reference_payloads(user):
    from apps.core.views_ouvrage_interventions import _accessible_intervention_ouvrages
    from apps.inventory.views import _filter_employes_by_scope, _filter_plannings_by_scope_inventory
    from apps.employees.models import Employe

    ouvrages = list(_accessible_intervention_ouvrages(user).order_by('nom_ouvrage')[:1000])
    ouvrage_ids = [item.id for item in ouvrages]
    plannings = list(
        _filter_plannings_by_scope_inventory(
            Planning.objects.select_related('employe').filter(
                ouvrage_id__in=ouvrage_ids,
                date__isnull=False,
            ),
            user,
        ).order_by('-date')[:1000]
    )
    employees = list(
        _filter_employes_by_scope(
            Employe.objects.filter(date_debauchage__isnull=True), user
        ).order_by('surnom', 'nom')[:1000]
    )
    transfers = list(
        _filter_transferts_by_scope(
            Transfert.objects.select_related(
                'magasin_origine', 'magasin_destination'
            ).prefetch_related('items__designation'),
            user,
        ).exclude(status='annule').order_by('-transfer_date')[:300]
    )
    can_change_transfer = bool(user.is_superuser or user.has_perm('inventory.change_transfert'))
    return {
        'employees': [
            {'id': str(item.id), 'display_name': item.nom_affichage, 'revision': 1, 'deleted_at': None}
            for item in employees
        ],
        'ouvrages': [
            {'id': str(item.id), 'name': item.nom_ouvrage, 'revision': 1, 'deleted_at': None}
            for item in ouvrages
        ],
        'plannings': [
            {
                'id': str(item.id),
                'ouvrage_id': str(item.ouvrage_id),
                'employee_id': str(item.employe_id) if item.employe_id else None,
                'business_date': item.date.isoformat(),
                'revision': int(item.updated_at.timestamp() * 1000) if item.updated_at else 1,
                'deleted_at': None,
            }
            for item in plannings
        ],
        'transfers': [
            {
                'id': str(item.id),
                'number': item.transfer_number,
                'transfer_date': item.transfer_date.isoformat(),
                'origin_magasin_id': str(item.magasin_origine_id),
                'destination_magasin_id': str(item.magasin_destination_id),
                'status': item.status,
                'allowed_actions': (
                    (['send', 'cancel'] if item.status == 'en_attente' else [])
                    + (['receive', 'cancel'] if item.status == 'en_cours' else [])
                ) if can_change_transfer else [],
                'revision': int(item.updated_at.timestamp() * 1000),
                'deleted_at': None,
                'items': [
                    {
                        'id': str(line.id),
                        'article_id': str(line.designation_id),
                        'sent_quantity': _decimal_string(line.quantity_sent),
                        'received_quantity': _decimal_string(line.quantity_received),
                        'revision': int(line.updated_at.timestamp() * 1000),
                        'deleted_at': None,
                    }
                    for line in item.items.all()
                ],
            }
            for item in transfers
        ],
    }


def _ensure_purchase_diamex(purchase):
    from apps.accounting.models import DiameXTemporaire

    supplier_name = ''
    supplier_prefix = ''
    if purchase.fournisseur:
        supplier_name = purchase.fournisseur.nom_fournisseur
        supplier_prefix = purchase.fournisseur.nif_ou_isi or (
            'NIF' if purchase.fournisseur.numero_nif else 'ISI'
        )
    elif purchase.supplier:
        supplier_name = purchase.supplier.supplier_name

    items = list(purchase.purchase_items.select_related('designation').all())
    designation_text = ', '.join(
        f"{item.designation.nom} ({item.designation.unite or 'unité'})"
        for item in items[:3] if item.designation
    )
    if len(items) > 3:
        designation_text += '...'
    description = '_'.join(filter(None, [
        supplier_prefix,
        supplier_name,
        designation_text,
        f'{purchase.total_amount:,.0f} Ar',
    ]))[:255]
    account_code = '601'
    if purchase.compte and purchase.compte.compte:
        account_code = purchase.compte.compte
    defaults = {
        'fournisseur': purchase.fournisseur,
        'type_transaction': 'depense',
        'date_m': purchase.actual_delivery_date or timezone.localdate(),
        'description': description,
        'montant_out': float(purchase.total_amount),
        'montant_in': 0.0,
        'compte_code': account_code,
        'prog': purchase.magasin.base.volet if purchase.magasin and purchase.magasin.base else None,
        'activ': purchase.magasin.base.volet if purchase.magasin and purchase.magasin.base else None,
        'info': 'Hydria Achats',
        'statut': 'en_attente',
    }
    transaction_row = DiameXTemporaire.objects.filter(
        purchase=purchase,
        type_transaction='depense',
        info='Hydria Achats',
    ).order_by('id').first()
    if transaction_row is None:
        transaction_row = DiameXTemporaire.objects.create(purchase=purchase, **defaults)
    return transaction_row


def _is_maintenance_activity(planning):
    """Distingue l'entretien au sein du catalogue réparation existant."""
    fiche = getattr(planning, 'fiche_poste', None)
    fiche_type = getattr(fiche, 'type_activites', None) if fiche else None
    planning_type = getattr(planning, 'type_activite', None)
    label = ' '.join(filter(None, [
        getattr(fiche_type, 'nomtype', ''),
        getattr(planning_type, 'nomtype', ''),
        getattr(fiche, 'tache', '') if fiche else '',
    ]))
    normalized = normalize_repair_text(label)
    return any(word in normalized for word in ('entretien', 'maintenance', 'nettoyage'))


def _due_activity_stats(user):
    # Le périmètre ouvrages est celui de la recherche/intervention existante,
    # plus strict et plus fidèle que le seul périmètre de stock par base.
    from apps.core.views_ouvrage_interventions import _accessible_intervention_ouvrages

    accessible_ids = _accessible_intervention_ouvrages(user).values_list('id', flat=True)
    overdue = reparations_echues(timezone.localdate()).filter(
        ouvrage_id__in=accessible_ids,
        ouvrage__isnull=False,
    )
    repair_ouvrage_ids = set()
    maintenance_ouvrage_ids = set()
    for planning in overdue.iterator():
        target = maintenance_ouvrage_ids if _is_maintenance_activity(planning) else repair_ouvrage_ids
        target.add(str(planning.ouvrage_id))

    maintenance_only_ids = maintenance_ouvrage_ids - repair_ouvrage_ids
    return {
        'repair_overdue_works': len(repair_ouvrage_ids),
        'maintenance_only_works': len(maintenance_only_ids),
        'as_of_date': timezone.localdate().isoformat(),
    }


@csrf_exempt
@require_POST
def login(request):
    data = _json_body(request)
    if data is None:
        return JsonResponse({'code': 'INVALID_JSON', 'message': 'Corps JSON invalide.'}, status=400)
    username = str(data.get('username') or '').strip()
    password = str(data.get('password') or '')
    try:
        device_id = uuid.UUID(str(data.get('device_id') or ''))
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({'code': 'INVALID_DEVICE_ID', 'message': 'Identifiant appareil invalide.'}, status=400)
    if not username or not password:
        return JsonResponse({'code': 'MISSING_CREDENTIALS', 'message': 'Identifiant et mot de passe requis.'}, status=400)
    user = authenticate(request, username=username, password=password)
    if user is None or not user.is_active:
        return JsonResponse({'code': 'INVALID_CREDENTIALS', 'message': 'Identifiants invalides.'}, status=401)
    if _get_inventory_scope(user) == 'none':
        return JsonResponse({'code': 'NO_LOGISTICS_SCOPE', 'message': 'Aucun périmètre logistique autorisé.'}, status=403)
    pair = _create_token_pair(user, device_id, str(data.get('device_label') or 'Android Logistique'))
    pair['user'] = _profile_payload(user)
    return JsonResponse(pair)


@csrf_exempt
@require_POST
def refresh(request):
    data = _json_body(request)
    refresh_key = str((data or {}).get('refresh_token') or '').strip()
    if not refresh_key:
        return JsonResponse({'code': 'MISSING_REFRESH_TOKEN', 'message': 'Jeton de renouvellement requis.'}, status=400)
    with transaction.atomic():
        token = MobileRefreshToken.objects.select_for_update().select_related('user').filter(key=refresh_key).first()
        if token is None or not token.is_usable:
            return JsonResponse({'code': 'INVALID_REFRESH_TOKEN', 'message': 'Jeton expiré ou révoqué.'}, status=401)
        token.last_used_at = timezone.now()
        token.revoked_at = timezone.now()
        token.save(update_fields=['last_used_at', 'revoked_at'])
        pair = _create_token_pair(token.user, token.device_id, token.device_label)
    return JsonResponse(pair)


@require_GET
@mobile_v1_required
def me(request):
    return JsonResponse({'user': _profile_payload(request.user), 'capabilities': _capabilities_for(request.user)})


@require_GET
@mobile_v1_required
def bootstrap(request):
    scoped_bases = list(
        _filter_bases_by_scope(Base.objects.select_related('organisation'), request.user)
        .order_by('organisation__nom_organisation', 'nom_base')
    )
    base_ids = [base.id for base in scoped_bases]
    scoped_magasins = list(
        Magasin.objects.select_related('base').filter(base_id__in=base_ids)
        .order_by('base__nom_base', 'nom_magasin')
    )
    stocks = list(
        Stock.objects.select_related('designation', 'designation__type_designation', 'base', 'utilisateur')
        .filter(base_id__in=base_ids, designation__isnull=False)
        .order_by('base__nom_base', 'designation__nom')
    )
    designation_ids = {stock.designation_id for stock in stocks if stock.designation_id}
    articles = list(
        Designation.objects.select_related('type_designation').filter(id__in=designation_ids)
        .order_by('nom')
    )
    type_ids = {article.type_designation_id for article in articles if article.type_designation_id}
    types = TypeDesignation.objects.filter(id__in=type_ids).order_by('nom')
    operation_references = _operation_reference_payloads(request.user)

    payload = {
        'user': _profile_payload(request.user),
        'capabilities': _capabilities_for(request.user),
        'bases': [
            {
                'id': str(base.id), 'name': base.nom_base,
                'organisation_id': str(base.organisation_id),
                'organisation_name': base.organisation.nom_organisation,
                'revision': 1, 'deleted_at': None,
            }
            for base in scoped_bases
        ],
        'magasins': [
            {'id': str(m.id), 'base_id': str(m.base_id), 'name': m.nom_magasin, 'revision': 1, 'deleted_at': None}
            for m in scoped_magasins
        ],
        'article_types': [
            {'id': str(item.id), 'name': item.nom, 'revision': 1, 'deleted_at': None}
            for item in types
        ],
        'articles': [_article_payload(article) for article in articles],
        'stock_positions': _stock_positions_for(request.user, scoped_bases, scoped_magasins, stocks),
        'stock_movements': _movement_payloads(base_ids),
        'purchases': _purchase_payloads(request.user),
        'activity_due_stats': _due_activity_stats(request.user),
        **operation_references,
    }
    now = _cursor_now()
    return JsonResponse({'cursor': now, 'server_time': now, 'payload': payload})


@require_GET
@mobile_v1_required
def changes(request):
    # Les référentiels historiques ne possèdent pas tous updated_at/deleted_at.
    # Tant que ces révisions ne sont pas ajoutées, demander un bootstrap transactionnel
    # évite de prétendre fournir un delta incomplet.
    now = _cursor_now()
    return JsonResponse({
        'cursor': now,
        'has_more': False,
        'full_refresh_required': True,
        'reason': 'REFERENCE_REVISION_UNAVAILABLE',
        'changes': {},
    })


@csrf_exempt
@require_POST
@mobile_v1_required
def receive_purchase(request, purchase_id):
    if not (request.user.is_superuser or request.user.has_perm('inventory.change_purchase')):
        return JsonResponse({'code': 'FORBIDDEN', 'message': "Réception d'achat non autorisée."}, status=403)

    with transaction.atomic():
        purchase = (
            _filter_purchases_by_scope(
                Purchase.objects.select_for_update().select_related(
                    'magasin__base', 'fournisseur', 'supplier', 'compte'
                ).prefetch_related('purchase_items__designation'),
                request.user,
            )
            .filter(id=purchase_id)
            .first()
        )
        if purchase is None:
            return JsonResponse({'code': 'PURCHASE_NOT_FOUND', 'message': 'Achat introuvable ou non autorisé.'}, status=404)
        if purchase.purchase_status == 'annule':
            return JsonResponse({'code': 'PURCHASE_CANCELLED', 'message': 'Un achat annulé ne peut pas être réceptionné.'}, status=409)
        if not purchase.magasin_id:
            return JsonResponse({'code': 'MISSING_MAGASIN', 'message': 'Aucun magasin associé à cet achat.'}, status=409)

        already_received = purchase.purchase_status == 'recu'
        if not already_received:
            purchase.purchase_items.update(quantity_received=models.F('quantity_ordered'))
            purchase.purchase_status = 'recu'
            purchase.actual_delivery_date = timezone.localdate()
            purchase.save(update_fields=['purchase_status', 'actual_delivery_date', 'updated_at'])
            _sync_purchase_inventory(purchase)
        transaction_row = _ensure_purchase_diamex(purchase)

    return JsonResponse({
        'success': True,
        'already_received': already_received,
        'purchase_id': str(purchase.id),
        'status': purchase.purchase_status,
        'message': (
            f'Achat {purchase.purchase_number} déjà réceptionné.' if already_received
            else f'Achat {purchase.purchase_number} réceptionné avec succès.'
        ),
        'transaction_id': transaction_row.id,
    })


def _forbidden_operation():
    return JsonResponse({'code': 'FORBIDDEN', 'message': 'Opération non autorisée.'}, status=403)


@csrf_exempt
@require_POST
@mobile_v1_required
def create_delivery(request):
    if not (request.user.is_superuser or request.user.has_perm('planning.add_bonlivraison')):
        return _forbidden_operation()
    return inventory_views.api_fiche_stock_bon_livraison_save(request)


@csrf_exempt
@require_POST
@mobile_v1_required
def create_transfer(request):
    if not (request.user.is_superuser or request.user.has_perm('inventory.add_transfert')):
        return _forbidden_operation()
    return views_transferts.api_create_transfert(request)


@csrf_exempt
@require_POST
@mobile_v1_required
def update_transfer(request, transfer_id):
    if not (request.user.is_superuser or request.user.has_perm('inventory.change_transfert')):
        return _forbidden_operation()
    return views_transferts.api_update_transfert_status(request, transfer_id)


@csrf_exempt
@require_POST
@mobile_v1_required
def create_inventory(request):
    if not (request.user.is_superuser or request.user.has_perm('inventory.add_fichestock')):
        return _forbidden_operation()
    return inventory_views.api_create_inventaire(request)


@csrf_exempt
@require_POST
@mobile_v1_required
def adjust_stock(request, stock_id):
    if not (request.user.is_superuser or request.user.has_perm('inventory.change_stock')):
        return _forbidden_operation()
    return inventory_views.api_adjust_stock(request, stock_id)


@csrf_exempt
@require_POST
@mobile_v1_required
def create_field_return(request):
    if not (request.user.is_superuser or request.user.has_perm('inventory.add_fichestock')):
        return _forbidden_operation()
    return inventory_views.api_fiche_stock_retour_terrain_save(request)
