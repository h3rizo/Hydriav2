from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q, Sum
from decimal import Decimal
import json
from datetime import datetime

from .models import Purchase, PurchaseItem, Supplier
from apps.billing.models import Fournisseur
from apps.planning.models import Designation
from apps.organization.models import Base
from apps.employees.models import Employe
from .views import _filter_bases_by_scope, _filter_employes_by_scope, _normalize_poste_name, _sync_purchase_inventory


def _is_directeur_inventory(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True

    employe = getattr(user, 'employe', None)
    if not employe:
        return False

    poste_nom = _normalize_poste_name(getattr(getattr(employe, 'poste', None), 'nom_poste', ''))
    return poste_nom == 'directeur'


def _allowed_bases_for_purchases(user):
    """Regle metier page achats: directeur=toutes bases, sinon base de l'utilisateur."""
    if _is_directeur_inventory(user):
        return _filter_bases_by_scope(Base.objects.all(), user)

    employe = getattr(user, 'employe', None)
    base_id = getattr(employe, 'base_id', None)
    if not base_id:
        return Base.objects.none()
    return Base.objects.filter(id=base_id)


def _filter_magasins_by_scope(queryset, user):
    allowed_bases = _allowed_bases_for_purchases(user)
    return queryset.filter(base_id__in=allowed_bases.values('id'))


def _filter_purchases_by_scope(queryset, user):
    allowed_bases = _allowed_bases_for_purchases(user)
    return queryset.filter(
        Q(magasin__base_id__in=allowed_bases.values('id')) |
        Q(base_id__in=allowed_bases.values('id'))
    )


def _resolve_purchase_base(purchase):
    """Retourne la base explicite de l'achat ou celle portée par le magasin."""
    if getattr(purchase, 'base', None):
        return purchase.base

    magasin = getattr(purchase, 'magasin', None)
    if magasin and getattr(magasin, 'base', None):
        return magasin.base

    return None


@login_required
def purchases_list(request):
    """Page principale de gestion des bons de commande"""
    from apps.organization.models import Magasin

    # Récupérer les filtres depuis l'URL
    magasin_id = request.GET.get('magasin_id', '')
    fournisseur_id = request.GET.get('fournisseur_id', '')
    statut = request.GET.get('statut', '')

    # Récupérer les achats avec filtres
    purchases = Purchase.objects.select_related(
        'magasin__base', 'fournisseur', 'supplier', 'ordered_by'
    ).prefetch_related('purchase_items__designation')
    purchases = _filter_purchases_by_scope(purchases, request.user)

    # Appliquer les filtres
    if magasin_id and magasin_id != 'all':
        purchases = purchases.filter(magasin_id=magasin_id)

    if fournisseur_id and fournisseur_id != 'all':
        purchases = purchases.filter(
            Q(fournisseur_id=fournisseur_id) | Q(supplier_id=fournisseur_id)
        )

    if statut and statut != 'all':
        purchases = purchases.filter(purchase_status=statut)

    # Trier par date décroissante
    purchases = purchases.order_by('-purchase_date')

    # Listes pour les dropdowns
    magasins = _filter_magasins_by_scope(
        Magasin.objects.select_related('base__organisation'),
        request.user
    ).order_by('base__nom_base', 'nom_magasin')
    employes = _filter_employes_by_scope(
        Employe.objects.filter(date_debauchage__isnull=True),
        request.user
    ).order_by('surnom')
    fournisseurs = Fournisseur.objects.filter(actif=True).order_by('nom_fournisseur')
    suppliers = Supplier.objects.filter(is_active=True).order_by('supplier_name')
    designations = Designation.objects.filter(actif=True).order_by('nom')

    from apps.organization.models import Compte
    comptes = Compte.objects.filter(achat=True).order_by('nom_compte')

    # Sérialiser les désignations pour JavaScript
    import json
    designations_json = json.dumps([{
        'id': str(d.id),
        'designation_name': d.nom,
        'unit': d.unite or '',
        'unit_price': float(d.prix_unitaire) if d.prix_unitaire else 0
    } for d in designations])

    context = {
        'purchases': purchases,
        'magasins': magasins,
        'employes': employes,
        'employees': employes,  # Alias pour compatibilité template
        'fournisseurs': fournisseurs,
        'suppliers': suppliers,
        'designations': designations,
        'designations_json': designations_json,
        'comptes': comptes,
    }
    return render(request, 'inventory/purchases_list.html', context)


@login_required
@require_http_methods(["GET"])
def api_purchases_list(request):
    """API pour lister les achats avec filtres"""
    # Récupérer les filtres
    statut = request.GET.get('statut', '')
    magasin_id = request.GET.get('magasin_id', '')
    fournisseur_id = request.GET.get('fournisseur_id', '')
    recherche = request.GET.get('recherche', '').strip()

    # Query de base
    purchases = Purchase.objects.select_related(
        'magasin__base', 'fournisseur', 'supplier', 'ordered_by'
    ).prefetch_related('purchase_items__designation')
    purchases = _filter_purchases_by_scope(purchases, request.user)

    # Filtres
    if statut and statut != 'all':
        purchases = purchases.filter(purchase_status=statut)

    if magasin_id and magasin_id != 'all':
        purchases = purchases.filter(magasin_id=magasin_id)

    if fournisseur_id and fournisseur_id != 'all':
        purchases = purchases.filter(
            Q(fournisseur_id=fournisseur_id) | Q(supplier_id=fournisseur_id)
        )

    if recherche:
        purchases = purchases.filter(
            Q(purchase_number__icontains=recherche) |
            Q(notes__icontains=recherche)
        )

    # Trier par date décroissante
    purchases = purchases.order_by('-purchase_date')

    # Construire la réponse
    data = []
    for purchase in purchases:
        # Nom du fournisseur
        fournisseur_nom = ''
        if purchase.fournisseur:
            fournisseur_nom = purchase.fournisseur.nom_fournisseur
        elif purchase.supplier:
            fournisseur_nom = purchase.supplier.supplier_name

        # Nombre d'items
        items_count = purchase.purchase_items.count()

        # Nom du magasin
        magasin_nom = ''
        if purchase.magasin:
            magasin_nom = f"{purchase.magasin.nom_magasin} ({purchase.magasin.base.nom_base})"

        data.append({
            'id': str(purchase.id),
            'purchase_number': purchase.purchase_number,
            'purchase_date': purchase.purchase_date.strftime('%d/%m/%Y'),
            'order_date': purchase.order_date.strftime('%d/%m/%Y') if purchase.order_date else '',
            'actual_delivery_date': purchase.actual_delivery_date.strftime('%d/%m/%Y') if purchase.actual_delivery_date else '',
            'purchase_status': purchase.purchase_status,
            'status_display': purchase.get_purchase_status_display(),
            'magasin': magasin_nom,
            'fournisseur': fournisseur_nom,
            'ordered_by': purchase.ordered_by.surnom if purchase.ordered_by else '',
            'total_amount': float(purchase.total_amount),
            'items_count': items_count,
            'numeroDiameX': purchase.numeroDiameX or '',
        })

    return JsonResponse({
        'success': True,
        'purchases': data
    })


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def api_create_purchase(request):
    """API pour créer un bon de commande"""
    try:
        data = json.loads(request.body)

        # Validation
        purchase_number = data.get('purchase_number', '').strip()
        if not purchase_number:
            return JsonResponse({'success': False, 'error': 'Numéro de commande requis'}, status=400)

        # Vérifier unicité du numéro
        if Purchase.objects.filter(purchase_number=purchase_number).exists():
            return JsonResponse({'success': False, 'error': 'Ce numéro de commande existe déjà'}, status=400)

        base_id = data.get('base_id')
        magasin_id = data.get('magasin_id')
        if not base_id and not magasin_id:
            return JsonResponse({'success': False, 'error': 'Base ou magasin requis'}, status=400)

        allowed_bases = _allowed_bases_for_purchases(request.user)
        from apps.organization.models import Magasin
        magasin = None
        if magasin_id:
            magasin = _filter_magasins_by_scope(Magasin.objects.select_related('base'), request.user).filter(id=magasin_id).first()
            if not magasin:
                return JsonResponse({'success': False, 'error': 'Magasin non autorise'}, status=403)
            base_id = str(magasin.base_id)

        if base_id and not allowed_bases.filter(id=base_id).exists():
            return JsonResponse({'success': False, 'error': 'Base non autorisee'}, status=403)

        # Dates
        purchase_date_str = data.get('purchase_date')
        order_date_str = data.get('order_date')
        delivery_date_str = data.get('actual_delivery_date')

        try:
            purchase_date = datetime.strptime(purchase_date_str, '%Y-%m-%d').date()
        except:
            return JsonResponse({'success': False, 'error': 'Date d\'achat invalide'}, status=400)

        order_date = None
        if order_date_str:
            try:
                order_date = datetime.strptime(order_date_str, '%Y-%m-%d').date()
            except:
                pass

        delivery_date = None
        if delivery_date_str:
            try:
                delivery_date = datetime.strptime(delivery_date_str, '%Y-%m-%d').date()
            except:
                pass

        # Créer l'achat
        ordered_by_id = data.get('ordered_by_id') if data.get('ordered_by_id') else None
        if ordered_by_id:
            allowed_employe = _filter_employes_by_scope(Employe.objects.filter(id=ordered_by_id), request.user).exists()
            if not allowed_employe:
                return JsonResponse({'success': False, 'error': 'Employe non autorise'}, status=403)

        purchase = Purchase.objects.create(
            purchase_number=purchase_number,
            purchase_date=purchase_date,
            order_date=order_date,
            actual_delivery_date=delivery_date,
            base_id=base_id,
            magasin=magasin,
            fournisseur_id=data.get('fournisseur_id') if data.get('fournisseur_id') else None,
            supplier_id=data.get('supplier_id') if data.get('supplier_id') else None,
            ordered_by_id=ordered_by_id,
            notes=data.get('notes', ''),
            purchase_status=data.get('purchase_status', 'brouillon'),
            numeroDiameX=data.get('numeroDiameX', ''),
            baseDiameX=data.get('baseDiameX', ''),
            total_amount=Decimal('0')
        )

        # Ajouter les items et calculer le total
        items = data.get('items', [])
        total_amount = Decimal('0')

        for item_data in items:
            designation_id = item_data.get('designation_id')
            quantity_ordered = item_data.get('quantity_ordered', 0)
            unit_price = item_data.get('unit_price', 0)

            if designation_id and quantity_ordered > 0 and unit_price > 0:
                quantity_ordered_decimal = Decimal(str(quantity_ordered))
                unit_price_decimal = Decimal(str(unit_price))
                total_price = quantity_ordered_decimal * unit_price_decimal

                PurchaseItem.objects.create(
                    purchase=purchase,
                    designation_id=designation_id,
                    quantity_ordered=quantity_ordered_decimal,
                    unit_price=unit_price_decimal,
                    total_price=total_price
                )

                total_amount += total_price

        # Mettre à jour le montant total
        purchase.total_amount = total_amount
        purchase.save()
        if purchase.purchase_status in ['livre', 'recu']:
            _sync_purchase_inventory(purchase)

        return JsonResponse({
            'success': True,
            'message': 'Bon de commande créé avec succès',
            'purchase_id': str(purchase.id)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def api_update_purchase_status(request, purchase_id):
    """API pour mettre à jour le statut d'un achat"""
    try:
        data = json.loads(request.body)
        new_status = data.get('status')

        purchase = _filter_purchases_by_scope(Purchase.objects.all(), request.user).get(id=purchase_id)
        purchase.purchase_status = new_status

        # Si livré/réceptionné, mettre à jour les quantités reçues
        if new_status in ['livre', 'recu']:
            if not purchase.actual_delivery_date:
                purchase.actual_delivery_date = datetime.now().date()

            items_data = data.get('items', [])
            for item_data in items_data:
                item_id = item_data.get('item_id')
                quantity_received = item_data.get('quantity_received', 0)

                if item_id:
                    item = PurchaseItem.objects.get(id=item_id)
                    item.quantity_received = Decimal(str(quantity_received))
                    item.save()

        purchase.save()
        if new_status in ['livre', 'recu']:
            _sync_purchase_inventory(purchase)

        return JsonResponse({
            'success': True,
            'message': 'Statut mis à jour avec succès'
        })

    except Purchase.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Bon de commande non trouvé'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_purchase_detail(request, purchase_id):
    """API pour obtenir les détails d'un achat"""
    try:
        purchase = _filter_purchases_by_scope(
            Purchase.objects.select_related(
            'base', 'magasin__base', 'fournisseur', 'supplier', 'ordered_by'
            ),
            request.user
        ).prefetch_related('purchase_items__designation').get(id=purchase_id)
        purchase_base = _resolve_purchase_base(purchase)
        magasin_nom = purchase.magasin.nom_magasin if purchase.magasin else ''

        items = []
        for item in purchase.purchase_items.all():
            items.append({
                'id': str(item.id),
                'designation_id': str(item.designation.id) if item.designation else '',
                'designation_nom': item.designation.nom if item.designation else '',
                'designation_unite': item.designation.unite if item.designation else '',
                'quantity_ordered': float(item.quantity_ordered),
                'quantity_received': float(item.quantity_received),
                'unit_price': float(item.unit_price),
                'total_price': float(item.total_price),
            })

        fournisseur_nom = ''
        fournisseur_id = ''
        if purchase.fournisseur:
            fournisseur_nom = purchase.fournisseur.nom_fournisseur
            fournisseur_id = str(purchase.fournisseur.id)
        elif purchase.supplier:
            fournisseur_nom = purchase.supplier.supplier_name
            fournisseur_id = str(purchase.supplier.id)

        data = {
            'id': str(purchase.id),
            'purchase_number': purchase.purchase_number,
            'purchase_date': purchase.purchase_date.strftime('%Y-%m-%d'),
            'order_date': purchase.order_date.strftime('%Y-%m-%d') if purchase.order_date else '',
            'actual_delivery_date': purchase.actual_delivery_date.strftime('%Y-%m-%d') if purchase.actual_delivery_date else '',
            'purchase_status': purchase.purchase_status,
            'status_display': purchase.get_purchase_status_display(),
            'purchase_status_display': purchase.get_purchase_status_display(),
            'base_id': str(purchase_base.id) if purchase_base else '',
            'base': purchase_base.nom_base if purchase_base else '',
            'fournisseur_id': fournisseur_id,
            'fournisseur': fournisseur_nom,
            'magasin_id': str(purchase.magasin.id) if purchase.magasin else '',
            'magasin': magasin_nom or (purchase_base.nom_base if purchase_base else ''),
            'ordered_by_id': str(purchase.ordered_by.id) if purchase.ordered_by else '',
            'ordered_by': purchase.ordered_by.surnom if purchase.ordered_by else '',
            'total_amount': float(purchase.total_amount),
            'numeroDiameX': purchase.numeroDiameX or '',
            'baseDiameX': purchase.baseDiameX or '',
            'notes': purchase.notes or '',
            'items': items
        }

        return JsonResponse({
            'success': True,
            'purchase': data
        })

    except Purchase.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Bon de commande non trouvé'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def api_delete_purchase(request, purchase_id):
    """API pour supprimer un bon de commande"""
    try:
        purchase = _filter_purchases_by_scope(Purchase.objects.all(), request.user).get(id=purchase_id)

        # Vérifier que l'achat est en brouillon
        if purchase.purchase_status not in ['brouillon', 'annule']:
            return JsonResponse({
                'success': False,
                'error': 'Impossible de supprimer un bon de commande validé'
            }, status=400)

        purchase_number = purchase.purchase_number
        purchase.delete()

        return JsonResponse({
            'success': True,
            'message': f'Bon de commande {purchase_number} supprimé avec succès'
        })

    except Purchase.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Bon de commande non trouvé'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
