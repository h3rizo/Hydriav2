"""

Vues pour la gestion du parc automobile

"""

from django.shortcuts import render, get_object_or_404, redirect

from django.http import JsonResponse

from django.views.decorators.csrf import csrf_exempt

from django.views.decorators.http import require_http_methods

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse

from django.db.models import Sum, Q, F, DecimalField, ExpressionWrapper, Count

from django.db import transaction

from django.db.models.functions import Coalesce, TruncMonth

from decimal import Decimal

from datetime import datetime, timedelta, date
from collections import defaultdict
import re

import json

import pytz



from .models_vehicles import (

    Vehicule,

    AffectationVehicule,

    ReparationVehicule,

    RelevéCompteur,

    UtilisationPieceVehicule,

    UtilisationCarburantVehicule,

    UtilisationPersoVehicule,
    ClotureCarburantMois,
    CarnetBordMensuelScan,
    RapportConsommationCarburantScan,
    RapportConsommationCarburantRemarque,

)

from .models import Stock, StockMovement, PurchaseItem, Purchase



from apps.employees.models import Employe

from apps.organization.models import Magasin, Base, Compte

from apps.billing.models import Fournisseur
from apps.accounting.models import BaseDiameX

from apps.planning.models import PlanningDetail, Designation

from django.utils import timezone
from .views import _filter_bases_by_scope, _filter_employes_by_scope





def _is_piece_vehicule(designation):

    type_nom = (getattr(designation.type_designation, 'nom', '') or '').lower()

    type_nom = (
        type_nom.replace('é', 'e')
        .replace('è', 'e')
        .replace('ê', 'e')
        .replace('à', 'a')
        .replace('ù', 'u')
        .replace('ô', 'o')
    )

    return 'piece' in type_nom and 'vehicule' in type_nom





def _normalize_name(value):

    value = (value or '').lower()

    value = (
        value.replace('é', 'e')
        .replace('è', 'e')
        .replace('ê', 'e')
        .replace('à', 'a')
        .replace('ù', 'u')
        .replace('ô', 'o')
        .replace('î', 'i')
        .replace('ï', 'i')
        .replace('ç', 'c')
    )

    return value





def _is_carburant_designation(designation):

    name = _normalize_name(getattr(designation, 'nom', '') or '')

    return any(token in name for token in ['carburant', 'gasoil', 'gazole', 'essence'])





def _find_employe_by_poste(base, keywords):

    if not base:

        return None

    qs = Employe.objects.filter(

        base=base,

        date_debauchage__isnull=True,

        poste__isnull=False

    )

    for key in keywords:

        emp = qs.filter(poste__nom_poste__icontains=key).first()

        if emp:

            return emp

    return None





def _get_directeur_for_base(base):

    return _find_employe_by_poste(base, ['directeur', 'direction', 'dir'])





def _get_chef_for_base(base):

    # Priorit: Responsable oprationnel > Directeur adjoint > Directeur

    emp = _find_employe_by_poste(base, ['responsable oprationnel', 'responsable operationnel'])

    if emp:

        return emp

    emp = _find_employe_by_poste(base, ['directeur adjoint', 'adjoint'])

    if emp:

        return emp

    return _find_employe_by_poste(base, ['directeur', 'direction', 'dir'])





def _is_directeur_user(user):

    emp = getattr(user, 'employe', None)

    if not emp or not emp.poste:

        return False

    poste = _normalize_name(getattr(emp.poste, 'nom_poste', ''))

    return 'directeur' in poste or 'direction' in poste or poste.startswith('dir')





def _is_chef_user(user):

    emp = getattr(user, 'employe', None)

    if not emp or not emp.poste:

        return False

    poste = _normalize_name(getattr(emp.poste, 'nom_poste', ''))

    return 'responsable operationnel' in poste or 'responsable oprationnel' in poste or 'directeur adjoint' in poste


def _allowed_base_ids(user):
    return list(_filter_bases_by_scope(Base.objects.all(), user).values_list('id', flat=True))


def _filter_magasins_scope(queryset, user):
    return queryset.filter(base_id__in=_allowed_base_ids(user))


def _filter_vehicules_scope(queryset, user):
    if getattr(user, 'is_superuser', False) or _is_directeur_user(user):
        return queryset
    base_ids = _allowed_base_ids(user)
    if not base_ids:
        return queryset.none()
    return queryset.filter(
        affectations__date_fin__isnull=True,
        affectations__employe__base_id__in=base_ids
    ).distinct()


def _scoped_vehicules_qs(user):
    return _filter_vehicules_scope(Vehicule.objects.all(), user)


def _scoped_employes_qs(user):
    return _filter_employes_by_scope(Employe.objects.all(), user)


def _scoped_magasins_qs(user):
    return _filter_magasins_scope(Magasin.objects.all(), user)


def _scoped_usages_perso_qs(user):
    base_ids = _allowed_base_ids(user)
    return UtilisationPersoVehicule.objects.filter(
        Q(employe__base_id__in=base_ids) |
        Q(vehicule__affectations__date_fin__isnull=True, vehicule__affectations__employe__base_id__in=base_ids)
    ).distinct()


def _scoped_purchase_items_qs(user):
    base_ids = _allowed_base_ids(user)
    return PurchaseItem.objects.filter(
        Q(purchase__magasin__base_id__in=base_ids) |
        Q(purchase__base_id__in=base_ids)
    )


MONTH_CHOICES = [
    (1, "Janvier"),
    (2, "Fevrier"),
    (3, "Mars"),
    (4, "Avril"),
    (5, "Mai"),
    (6, "Juin"),
    (7, "Juillet"),
    (8, "Aout"),
    (9, "Septembre"),
    (10, "Octobre"),
    (11, "Novembre"),
    (12, "Decembre"),
]


def _parse_int(value, default):
    try:
        return int(value)
    except Exception:
        return default


def _month_bounds(annee, mois):
    month_start = date(annee, mois, 1)
    if mois == 12:
        next_month_start = date(annee + 1, 1, 1)
    else:
        next_month_start = date(annee, mois + 1, 1)
    month_end = next_month_start - timedelta(days=1)
    prev_month_end = month_start - timedelta(days=1)
    return month_start, month_end, prev_month_end


def _normalize_plate(value):
    if not value:
        return ""
    return re.sub(r'[^A-Z0-9]', '', str(value).upper())


def _extract_liters_from_text(*values):
    text = " ".join([str(v or "") for v in values])
    matches = re.findall(r'(\d+(?:[.,]\d+)?)\s*(?:l|litre|litres)\b', text, flags=re.IGNORECASE)
    total = Decimal('0')
    for item in matches:
        try:
            total += Decimal(str(item).replace(',', '.'))
        except Exception:
            continue
    return total


def _get_usage_base_id(usage):
    if getattr(getattr(usage, 'employe', None), 'base_id', None):
        return usage.employe.base_id
    if getattr(getattr(usage, 'magasin', None), 'base_id', None):
        return usage.magasin.base_id
    purchase = getattr(getattr(usage, 'purchase_item', None), 'purchase', None)
    if getattr(getattr(purchase, 'magasin', None), 'base_id', None):
        return purchase.magasin.base_id
    if getattr(purchase, 'base_id', None):
        return purchase.base_id
    return None


def _build_usage_compta_candidates(usage, scoped_entries_qs, vehicule=None, limit=20):
    if not usage:
        return []

    qs = scoped_entries_qs.filter(
        date_rec__year=usage.date_utilisation.year,
        date_rec__month=usage.date_utilisation.month,
        compte_code__in=['606100', '606107'],
    )

    base_id = _get_usage_base_id(usage)
    if base_id:
        base = Base.objects.filter(id=base_id).first()
        if base and getattr(base, 'volet', None):
            qs = qs.filter(Q(activ__iexact=base.volet) | Q(prog__iexact=base.volet))

    montant_usage = Decimal(str(usage.montant or 0))
    if montant_usage > 0:
        tolerance = max(Decimal('5000'), montant_usage * Decimal('0.15'))
        qs = qs.filter(montant_out__gte=montant_usage - tolerance, montant_out__lte=montant_usage + tolerance)

    plate = _normalize_plate(getattr(vehicule or usage.vehicule, 'immatriculation', ''))
    candidates = []
    for entry in qs.order_by('-date_rec', '-id')[:100]:
        detail_text = str(getattr(entry, 'detail', '') or '')
        description_text = str(getattr(entry, 'description', '') or '')
        matched_plate = bool(plate and plate in _normalize_plate(detail_text + ' ' + description_text))
        candidates.append({
            'id': entry.id,
            'date': entry.date_rec,
            'description': description_text,
            'detail': detail_text,
            'montant': Decimal(str(entry.montant_out or 0)),
            'compte_code': str(getattr(entry, 'compte_code', '') or ''),
            'matched_plate': matched_plate,
            'already_linked': entry.utilisations_carburant_vehicules.exclude(id=usage.id).exists(),
        })

    candidates.sort(
        key=lambda item: (
            not item['matched_plate'],
            item['already_linked'],
            abs((item['montant'] or Decimal('0')) - montant_usage),
            -(item['id'] or 0),
        )
    )
    return candidates[:limit]


def _extract_liters_from_structured_libelle(libelle):
    """
    Extraction ciblee pour les libelles type:
    NIF_[Fournisseur]_[Essence/Gasoil]_L_[Prix unitaire]_[x quantite en litre] moto [Numero]
    """
    raw_text = str(libelle or "").strip()
    if not raw_text:
        return Decimal('0'), False, "libelle vide"

    # 1) Extraction prioritaire apres le token x
    m_x = re.search(r'\bx\s*([0-9]+(?:[.,][0-9]+)?)', raw_text, flags=re.IGNORECASE)
    if m_x:
        try:
            return Decimal(m_x.group(1).replace(',', '.')), True, "extrait via token x"
        except Exception:
            pass

    # 2) Extraction via structure underscore (token apres prix unitaire)
    tokens = [t.strip() for t in raw_text.split('_') if str(t).strip()]
    if len(tokens) >= 6 and tokens[3].lower() == 'l':
        quantity_chunk = "_".join(tokens[5:])
        m_qty = re.search(r'([0-9]+(?:[.,][0-9]+)?)', quantity_chunk)
        if m_qty:
            try:
                return Decimal(m_qty.group(1).replace(',', '.')), True, "extrait via pattern underscore"
            except Exception:
                pass

    # 3) Fallback generic litre
    fallback = _extract_liters_from_text(raw_text)
    if fallback > 0:
        return fallback, True, "extrait via fallback litre"

    return Decimal('0'), False, "quantite non detectee"


def _is_stock_fuel_entry(entry):
    text = " ".join([
        str(getattr(entry, 'description', '') or ''),
        str(getattr(entry, 'detail', '') or ''),
        str(getattr(entry, 'info', '') or ''),
    ])
    normalized = _normalize_name(text)
    stock_tokens = ['stock', 'magasin', 'cuve', 'reserve']
    return any(token in normalized for token in stock_tokens)


def _build_fuel_compta_map(entries_qs, vehicules_qs):
    plate_by_vehicle = {veh.id: _normalize_plate(veh.immatriculation) for veh in vehicules_qs}
    sorted_plate_items = sorted(
        [(veh_id, plate) for veh_id, plate in plate_by_vehicle.items() if plate],
        key=lambda item: len(item[1]),
        reverse=True,
    )
    direct_by_vehicle = defaultdict(lambda: {'litres': Decimal('0'), 'montant': Decimal('0'), 'count': 0})
    direct_entries_by_vehicle = defaultdict(list)
    stock_entries = []

    for entry in entries_qs:
        raw_match_text = f"{entry.detail or ''} {entry.description or ''} {entry.info or ''}"
        normalized_text = _normalize_plate(raw_match_text)
        matched_vehicle_id = None
        for veh_id, plate in sorted_plate_items:
            if plate and plate in normalized_text:
                matched_vehicle_id = veh_id
                break

        extracted_liters, extracted_ok, extract_reason = _extract_liters_from_structured_libelle(entry.description)
        if not extracted_ok:
            extracted_liters, extracted_ok, extract_reason = _extract_liters_from_structured_libelle(entry.info)

        montant = Decimal(str(entry.montant_out or 0))
        account_code = str(getattr(entry, 'compte_code', '') or '')
        vehicle_type = 'moto' if account_code.startswith('606100') else 'voiture' if account_code.startswith('606107') else ''
        is_stock = _is_stock_fuel_entry(entry)

        row = {
            'entry': entry,
            'matched_vehicle_id': matched_vehicle_id,
            'litres': extracted_liters,
            'montant': montant,
            'extracted_ok': extracted_ok,
            'extract_reason': extract_reason,
            'vehicle_type': vehicle_type,
            'is_stock': is_stock,
        }

        if matched_vehicle_id and not is_stock:
            direct_by_vehicle[matched_vehicle_id]['litres'] += extracted_liters
            direct_by_vehicle[matched_vehicle_id]['montant'] += montant
            direct_by_vehicle[matched_vehicle_id]['count'] += 1
            direct_entries_by_vehicle[matched_vehicle_id].append(row)
        else:
            stock_entries.append(row)

    return {
        'direct_by_vehicle': direct_by_vehicle,
        'direct_entries_by_vehicle': direct_entries_by_vehicle,
        'stock_entries': stock_entries,
    }


def _analyse_consommation(vehicule_type, litres_total, distance_km):
    if litres_total > 0 and distance_km <= 0:
        return ('critical', "Distance nulle avec carburant: verifier compteur / risques de detournement.")
    if distance_km <= 0:
        return ('empty', "Aucune donnee exploitable.")

    conso = (litres_total / distance_km) * Decimal('100')
    if vehicule_type == 'moto':
        normal_max = Decimal('5')
        high_max = Decimal('8')
    else:
        normal_max = Decimal('12')
        high_max = Decimal('16')

    if conso > high_max:
        return ('critical', "Consommation anormale: verifier etat vehicule et possible fuite/vol.")
    if conso > normal_max:
        return ('warning', "Consommation elevee: surveillance recommandee.")
    return ('ok', "Consommation normale.")





@csrf_exempt

@login_required

@require_http_methods(["POST", "DELETE"])

def api_releve_delete(request, releve_id):

    """API pour supprimer un relevé compteur."""

    try:
        releve = get_object_or_404(
            RelevéCompteur.objects.select_related('vehicule', 'employe').filter(
                vehicule_id__in=_scoped_vehicules_qs(request.user).values_list('id', flat=True)
            ),
            id=releve_id
        )

        if not (getattr(request.user, 'is_superuser', False) or _is_directeur_user(request.user)):
            return JsonResponse({
                'success': False,
                'error': 'Suppression réservée au Directeur'
            }, status=403)

        with transaction.atomic():
            for carburant in releve.carburants.select_related('magasin').all():
                designation = getattr(getattr(carburant, 'stock_movement', None), 'designation', None)
                if carburant.source_type == 'stock' and carburant.magasin and designation:
                    stock, _created = Stock.objects.get_or_create(
                        designation=designation,
                        base=carburant.magasin.base,
                        defaults={'current_quantity': Decimal('0')}
                    )
                    stock.current_quantity = (stock.current_quantity or Decimal('0')) + (carburant.quantite or Decimal('0'))
                    stock.save(update_fields=['current_quantity'])
                    StockMovement.objects.create(
                        designation=designation,
                        base=stock.base,
                        movement_type='entree',
                        quantity=carburant.quantite or Decimal('0'),
                        movement_date=datetime.now(),
                        reference=f"Annulation relevé {releve.id}",
                        notes='Restitution carburant suite à suppression du relevé',
                        employee=carburant.employe
                    )
                carburant.delete()

            vehicule_label = getattr(releve.vehicule, 'immatriculation', '') or 'Véhicule'
            date_label = releve.date_releve.strftime('%d/%m/%Y') if releve.date_releve else '-'
            releve.delete()

        return JsonResponse({
            'success': True,
            'message': f'Relevé supprimé : {vehicule_label} / {date_label}'
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)




@csrf_exempt

@login_required

@require_http_methods(["POST", "DELETE"])

def api_achat_piece_delete(request, purchase_item_id):

    """API pour supprimer une ligne d'achat de pièce non encore utilisée."""

    try:
        purchase_item = get_object_or_404(_scoped_purchase_items_qs(request.user), id=purchase_item_id)

        if not (getattr(request.user, 'is_superuser', False) or _is_directeur_user(request.user)):
            return JsonResponse({
                'success': False,
                'error': 'Suppression réservée au Directeur'
            }, status=403)

        if (purchase_item.quantity_received or Decimal('0')) > 0:
            return JsonResponse({
                'success': False,
                'error': 'Suppression impossible : quantité déjà reçue'
            }, status=400)

        if purchase_item.utilisations_pieces_vehicules.exists() or purchase_item.utilisations_carburant_vehicules.exists():
            return JsonResponse({
                'success': False,
                'error': 'Suppression impossible : ligne déjà utilisée'
            }, status=400)

        purchase_number = getattr(purchase_item.purchase, 'purchase_number', '') or 'Achat'
        designation_nom = getattr(purchase_item.designation, 'nom', '') or 'Pièce'
        purchase_item.delete()

        return JsonResponse({
            'success': True,
            'message': f'Ligne d\'achat supprimée : {purchase_number} / {designation_nom}'
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)




@csrf_exempt

@login_required

@require_http_methods(["POST", "DELETE"])

def api_utilisation_piece_delete(request, utilisation_id):

    """API pour supprimer une utilisation de pièce et restituer le stock."""

    try:
        utilisation = get_object_or_404(
            UtilisationPieceVehicule.objects.select_related('vehicule', 'designation', 'magasin', 'employe').filter(
                Q(vehicule_id__in=_scoped_vehicules_qs(request.user).values_list('id', flat=True)) |
                Q(employe__in=_scoped_employes_qs(request.user)) |
                Q(magasin__in=_scoped_magasins_qs(request.user))
            ),
            id=utilisation_id
        )

        if not (getattr(request.user, 'is_superuser', False) or _is_directeur_user(request.user)):
            return JsonResponse({
                'success': False,
                'error': 'Suppression réservée au Directeur'
            }, status=403)

        with transaction.atomic():
            if utilisation.magasin and utilisation.designation:
                stock, _created = Stock.objects.get_or_create(
                    designation=utilisation.designation,
                    base=utilisation.magasin.base,
                    defaults={'current_quantity': Decimal('0')}
                )
                stock.current_quantity = (stock.current_quantity or Decimal('0')) + (utilisation.quantite or Decimal('0'))
                stock.save(update_fields=['current_quantity'])
                StockMovement.objects.create(
                    designation=utilisation.designation,
                    base=stock.base,
                    movement_type='entree',
                    quantity=utilisation.quantite or Decimal('0'),
                    movement_date=datetime.now(),
                    reference=f"Annulation utilisation pièce {utilisation.id}",
                    notes='Restitution pièce suite à suppression de l\'utilisation',
                    employee=utilisation.employe
                )

            vehicule_label = getattr(utilisation.vehicule, 'immatriculation', '') or 'Véhicule'
            designation_nom = getattr(utilisation.designation, 'nom', '') or 'Pièce'
            utilisation.delete()

        return JsonResponse({
            'success': True,
            'message': f'Utilisation supprimée : {vehicule_label} / {designation_nom}'
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)




@login_required

def gestion_vehicules(request):

    """Page principale de gestion des vhicules"""

    vehicules = _filter_vehicules_scope(
        Vehicule.objects.select_related().prefetch_related('affectations__employe'),
        request.user
    )

    # Employs actifs = ceux qui n'ont pas de date de dbauche

    employes = _filter_employes_by_scope(
        Employe.objects.filter(date_debauchage__isnull=True),
        request.user
    ).order_by('nom', 'prenom')

    def get_base_name_from_vehicule(vehicule):

        employe = getattr(vehicule, 'employe_actuel', None)

        if employe and getattr(employe, 'base', None) and getattr(employe.base, 'nom_base', None):

            return employe.base.nom_base

        return 'Non affecte'

    def get_base_name_from_employe(employe):

        if employe and getattr(employe, 'base', None) and getattr(employe.base, 'nom_base', None):

            return employe.base.nom_base

        return 'Non affecte'





    # Calculer les statistiques

    total_vehicules = vehicules.count()

    vehicules_actifs = vehicules.filter(actif=True).count()



    # Vhicules affects (avec une affectation active)

    vehicules_affectes = vehicules.filter(affectations__date_fin__isnull=True).distinct().count()



    # Vhicules disponibles (actifs mais sans affectation active)

    vehicules_disponibles = vehicules_actifs - vehicules_affectes



    # Listes pour les onglets (evite les chargements infinis)

    affectations = AffectationVehicule.objects.select_related('vehicule', 'employe').filter(
        vehicule_id__in=vehicules.values_list('id', flat=True)
    ).order_by('-date_debut')[:200]

    releves = RelevéCompteur.objects.select_related('vehicule', 'employe').filter(
        vehicule_id__in=vehicules.values_list('id', flat=True)
    ).order_by('-date_releve')[:200]
    last_arrivee_by_vehicule = {}
    for releve in RelevéCompteur.objects.filter(
        vehicule_id__in=vehicules.values_list('id', flat=True)
    ).order_by('vehicule_id', '-date_releve', '-created_at'):
        vehicule_id = str(releve.vehicule_id)
        if vehicule_id in last_arrivee_by_vehicule:
            continue
        last_arrivee_by_vehicule[vehicule_id] = releve.lieu_arrivee or ''

    reparations = ReparationVehicule.objects.select_related(

        'vehicule',

        'purchase'

    ).filter(
        vehicule_id__in=vehicules.values_list('id', flat=True)
    ).order_by('-date_prevue', '-date_reparation', '-created_at')[:200]

    reparations_planifiees_ids = set(

        ReparationVehicule.objects.filter(

            vehicule_id__in=vehicules.values_list('id', flat=True),

            statut__in=['planifiee', 'commande', 'commande_recue'],

            date_reparation__isnull=True,

        ).values_list('vehicule_id', flat=True).distinct()

    )

    for affectation in affectations:

        base_name = get_base_name_from_employe(affectation.employe)

        if base_name == 'Non affecte' and affectation.vehicule:

            base_name = get_base_name_from_vehicule(affectation.vehicule)

        affectation.base_group = base_name

    affectations = sorted(
        affectations,
        key=lambda item: (
            _normalize_name(getattr(item, 'base_group', '') or 'Non affecte'),
            0 if item.est_active else 1,
            -(item.date_debut.toordinal() if item.date_debut else 0),
            _normalize_name(getattr(item.vehicule, 'immatriculation', '') or ''),
            _normalize_name(getattr(item.employe, 'surnom', '') or getattr(item.employe, 'nom_complet', '') or ''),
        )
    )

    for releve in releves:

        base_name = get_base_name_from_employe(releve.employe)

        if base_name == 'Non affecte' and releve.vehicule:

            base_name = get_base_name_from_vehicule(releve.vehicule)

        releve.base_group = base_name

    releves = sorted(
        releves,
        key=lambda item: (
            _normalize_name(getattr(item, 'base_group', '') or 'Non affecte'),
            -(item.date_releve.toordinal() if item.date_releve else 0),
            _normalize_name(getattr(item.vehicule, 'immatriculation', '') or ''),
            _normalize_name(getattr(item.employe, 'surnom', '') or getattr(item.employe, 'nom_complet', '') or ''),
        )
    )

    for rep in reparations:

        rep.base_group = get_base_name_from_vehicule(rep.vehicule)

    reparations = sorted(
        reparations,
        key=lambda item: (
            _normalize_name(getattr(item, 'base_group', '') or 'Non affecte'),
            0 if getattr(item, 'statut', '') in ['planifiee', 'commande', 'commande_recue'] else 1,
            -(
                (item.date_prevue or item.date_reparation).toordinal()
                if (item.date_prevue or item.date_reparation) else 0
            ),
            _normalize_name(getattr(item.vehicule, 'immatriculation', '') or ''),
            _normalize_name(getattr(item, 'libelle', '') or ''),
        )
    )

    commandes_reparations_grouped_map = {}
    reparations_with_purchase = ReparationVehicule.objects.select_related(
        'vehicule',
        'purchase',
        'purchase__magasin__base',
        'purchase__base',
        'purchase__fournisseur',
        'purchase__supplier',
    ).prefetch_related(
        'purchase__purchase_items__designation'
    ).filter(
        vehicule_id__in=vehicules.values_list('id', flat=True),
        purchase__isnull=False,
    ).order_by('-date_prevue', '-created_at')[:200]

    for rep in reparations_with_purchase:
        purchase = getattr(rep, 'purchase', None)
        if not purchase:
            continue

        base_name = 'Non affecte'
        if getattr(getattr(purchase, 'magasin', None), 'base', None) and getattr(purchase.magasin.base, 'nom_base', None):
            base_name = purchase.magasin.base.nom_base
        elif getattr(purchase, 'base', None) and getattr(purchase.base, 'nom_base', None):
            base_name = purchase.base.nom_base
        elif getattr(rep, 'base_group', None):
            base_name = rep.base_group

        fournisseur_nom = ''
        if getattr(purchase, 'fournisseur', None) and getattr(purchase.fournisseur, 'nom_fournisseur', None):
            fournisseur_nom = purchase.fournisseur.nom_fournisseur
        elif getattr(purchase, 'supplier', None):
            fournisseur_nom = str(purchase.supplier)

        for item in purchase.purchase_items.select_related('designation').all():
            if not getattr(item, 'designation', None):
                continue

            designation_nom = item.designation.nom or 'Designation'
            key = (base_name, designation_nom)
            row = commandes_reparations_grouped_map.setdefault(key, {
                'base_name': base_name,
                'designation_nom': designation_nom,
                'unite': getattr(item.designation, 'unite', '') or '',
                'quantite_totale': Decimal('0'),
                'montant_total': Decimal('0'),
                'fournisseurs': set(),
                'references': set(),
                'vehicules': set(),
                'reparations': set(),
            })
            qty = Decimal(str(getattr(item, 'quantity_ordered', None) or 0))
            price = Decimal(str(getattr(item, 'unit_price', None) or 0))
            row['quantite_totale'] += qty
            row['montant_total'] += qty * price
            if fournisseur_nom:
                row['fournisseurs'].add(fournisseur_nom)
            purchase_number = getattr(purchase, 'purchase_number', '') or ''
            if purchase_number:
                row['references'].add(purchase_number)
            vehicule_label = getattr(getattr(rep, 'vehicule', None), 'immatriculation', '') or ''
            if vehicule_label:
                row['vehicules'].add(vehicule_label)
            reparation_label = getattr(rep, 'libelle', '') or ''
            if reparation_label:
                row['reparations'].add(reparation_label)

    commandes_reparations_groupes = []
    if commandes_reparations_grouped_map:
        base_groups = defaultdict(list)
        for (_base_name, _designation_nom), row in commandes_reparations_grouped_map.items():
            row['fournisseurs'] = sorted(row['fournisseurs'])
            row['references'] = sorted(row['references'])
            row['vehicules'] = sorted(row['vehicules'])
            row['reparations'] = sorted(row['reparations'])
            base_groups[row['base_name']].append(row)

        for base_name, rows in base_groups.items():
            rows.sort(key=lambda row: _normalize_name(row['designation_nom']))
            commandes_reparations_groupes.append({
                'base': base_name,
                'items': rows,
                'count': len(rows),
            })

        commandes_reparations_groupes.sort(key=lambda row: _normalize_name(row['base']))



    # Pices vhicules (achats filtrs par type de dsignation)

    base_ids_scope = _allowed_base_ids(request.user)

    pieces_designations = [
        d for d in Designation.objects.filter(actif=True) if _is_piece_vehicule(d)
    ]
    pieces_designations.sort(key=lambda d: d.nom or '')

    achats_pieces = PurchaseItem.objects.select_related(

        'purchase',

        'designation',

        'purchase__magasin',

        'purchase__fournisseur',

        'purchase__supplier'

    ).filter(

        designation__in=pieces_designations

    ).filter(
        Q(purchase__magasin__base_id__in=base_ids_scope) | Q(purchase__base_id__in=base_ids_scope)
    ).order_by('-purchase__purchase_date')[:200]

    for item in achats_pieces:

        base_name = 'Non affecte'

        if item.purchase:

            if item.purchase.magasin and getattr(item.purchase.magasin, 'base', None) and getattr(item.purchase.magasin.base, 'nom_base', None):

                base_name = item.purchase.magasin.base.nom_base

            elif item.purchase.base and getattr(item.purchase.base, 'nom_base', None):

                base_name = item.purchase.base.nom_base

        item.base_group = base_name

    achats_pieces = sorted(
        achats_pieces,
        key=lambda item: (
            _normalize_name(getattr(item, 'base_group', '') or 'Non affecte'),
            -(item.purchase.purchase_date.toordinal() if getattr(item.purchase, 'purchase_date', None) else 0),
            _normalize_name(getattr(item.purchase, 'purchase_number', '') or ''),
            _normalize_name(getattr(item.designation, 'nom', '') or ''),
        )
    )

    utilisations_pieces = UtilisationPieceVehicule.objects.select_related(

        'vehicule',

        'designation',

        'purchase_item',

        'purchase_item__purchase',

        'employe',

        'magasin',

        'reparation'

    ).filter(
        Q(vehicule_id__in=vehicules.values_list('id', flat=True)) |
        Q(employe__base_id__in=base_ids_scope) |
        Q(magasin__base_id__in=base_ids_scope)
    ).order_by('-date_utilisation')[:200]

    for util in utilisations_pieces:

        base_name = 'Non affecte'

        if util.vehicule:

            base_name = get_base_name_from_vehicule(util.vehicule)

        elif util.employe and getattr(util.employe, 'base', None) and getattr(util.employe.base, 'nom_base', None):

            base_name = util.employe.base.nom_base

        elif util.magasin and getattr(util.magasin, 'base', None) and getattr(util.magasin.base, 'nom_base', None):

            base_name = util.magasin.base.nom_base

        util.base_group = base_name

    utilisations_pieces = sorted(
        utilisations_pieces,
        key=lambda item: (
            _normalize_name(getattr(item, 'base_group', '') or 'Non affecte'),
            -(item.date_utilisation.toordinal() if item.date_utilisation else 0),
            _normalize_name(getattr(item.vehicule, 'immatriculation', '') or ''),
            _normalize_name(getattr(item.designation, 'nom', '') or ''),
        )
    )



    # Carburant (achats et stocks)

    carburant_designations = [d for d in Designation.objects.filter(actif=True) if _is_carburant_designation(d)]

    achats_carburant = PurchaseItem.objects.select_related(
        'purchase',
        'designation',
        'purchase__magasin',
        'purchase__fournisseur',
        'purchase__supplier'
    ).filter(
        designation__in=carburant_designations
    ).filter(
        Q(purchase__magasin__base_id__in=base_ids_scope) | Q(purchase__base_id__in=base_ids_scope)
    ).order_by('-purchase__purchase_date')[:200]

    achats_carburant_non_relie = UtilisationCarburantVehicule.objects.select_related(
        'vehicule',
        'employe',
        'base_diamex_entry'
    ).filter(
        source_type='achat',
        base_diamex_entry__isnull=True
    ).filter(
        Q(vehicule_id__in=vehicules.values_list('id', flat=True)) |
        Q(employe__base_id__in=base_ids_scope)
    ).order_by('-date_utilisation', '-created_at')[:50]

    compta_entries_scope = BaseDiameX.objects.all()
    achats_carburant_non_relie_rows = []
    for usage in achats_carburant_non_relie:
        achats_carburant_non_relie_rows.append({
            'usage': usage,
            'candidates': _build_usage_compta_candidates(usage, compta_entries_scope, vehicule=usage.vehicule),
        })

    # Analyse carburant par vehicule sur un mois isole
    today = timezone.localdate()
    analyse_mois = _parse_int(request.GET.get('analyse_mois'), today.month)
    analyse_annee = _parse_int(request.GET.get('analyse_annee'), today.year)
    if analyse_mois < 1 or analyse_mois > 12:
        analyse_mois = today.month
    if analyse_annee < 2000 or analyse_annee > 2100:
        analyse_annee = today.year
    analyse_since, analyse_until, _analyse_prev_end = _month_bounds(analyse_annee, analyse_mois)
    vehicule_ids = list(vehicules.values_list('id', flat=True))
    carburant_recent = UtilisationCarburantVehicule.objects.filter(
        vehicule_id__in=vehicule_ids,
        date_utilisation__gte=analyse_since,
        date_utilisation__lte=analyse_until,
    ).select_related('vehicule', 'employe')
    releves_recent = RelevéCompteur.objects.filter(
        vehicule_id__in=vehicule_ids,
        date_releve__gte=analyse_since,
        date_releve__lte=analyse_until,
    ).select_related('vehicule')
    compta_carburant_recent_qs = BaseDiameX.objects.filter(
        date_rec__gte=analyse_since,
        date_rec__lte=analyse_until,
        compte_code__in=['606100', '606107'],
    )
    compta_fuel_map = _build_fuel_compta_map(compta_carburant_recent_qs, vehicules)
    analyse_years_available = sorted({
        today.year,
        *[y for y in UtilisationCarburantVehicule.objects.filter(vehicule_id__in=vehicule_ids).values_list('date_utilisation__year', flat=True) if y],
        *[y for y in RelevéCompteur.objects.filter(vehicule_id__in=vehicule_ids).values_list('date_releve__year', flat=True) if y],
        *[y for y in BaseDiameX.objects.values_list('date_rec__year', flat=True) if y],
    }, reverse=True)

    carburant_by_vehicule = {}
    carburant_events_by_vehicule = defaultdict(list)
    for usage in carburant_recent.order_by('vehicule_id', 'date_utilisation', 'created_at'):
        key = str(usage.vehicule_id)
        row = carburant_by_vehicule.setdefault(key, {
            'litres_total': Decimal('0'),
            'montant_total': Decimal('0'),
            'nb_pleins': 0,
            'last_carburant_date': None,
            'last_source_type': '',
            'last_employe_nom': '',
        })
        quantite = usage.quantite or Decimal('0')
        montant = usage.montant or Decimal('0')
        row['litres_total'] += quantite
        row['montant_total'] += montant
        row['nb_pleins'] += 1
        carburant_events_by_vehicule[key].append(usage)
        if not row['last_carburant_date'] or usage.date_utilisation > row['last_carburant_date']:
            row['last_carburant_date'] = usage.date_utilisation
            row['last_source_type'] = usage.get_source_type_display() if getattr(usage, 'source_type', None) else ''
            employe_nom = ''
            if getattr(usage, 'employe', None):
                employe_nom = usage.employe.surnom or usage.employe.nom_complet
            row['last_employe_nom'] = employe_nom

    releves_by_vehicule = {}
    releve_events_by_vehicule = defaultdict(list)
    for releve in releves_recent.order_by('vehicule_id', 'date_releve', 'created_at'):
        key = str(releve.vehicule_id)
        row = releves_by_vehicule.setdefault(key, {
            'distance_total': Decimal('0'),
            'last_releve_date': None,
            'last_index': None,
        })
        row['distance_total'] += releve.distance_parcourue or Decimal('0')
        releve_events_by_vehicule[key].append(releve)
        if not row['last_releve_date'] or releve.date_releve > row['last_releve_date']:
            row['last_releve_date'] = releve.date_releve
            row['last_index'] = releve.index_compteur

    vehicules_carburant_analyse = []
    for v in vehicules:
        vehicule_key = str(v.id)
        carburant_data = carburant_by_vehicule.get(vehicule_key, {})
        releve_data = releves_by_vehicule.get(vehicule_key, {})
        user_entries = []
        for usage in carburant_events_by_vehicule.get(vehicule_key, []):
            user_entries.append({
                'date': usage.date_utilisation.strftime('%d/%m/%Y') if usage.date_utilisation else '-',
                'quantite': float(usage.quantite or 0),
                'montant': float(usage.montant or 0),
                'source': usage.get_source_type_display() if getattr(usage, 'source_type', None) else '',
                'employe': usage.employe.surnom or usage.employe.nom_complet if getattr(usage, 'employe', None) else '-',
                'notes': usage.notes or '',
            })
        litres_total = carburant_data.get('litres_total', Decimal('0'))
        montant_total = carburant_data.get('montant_total', Decimal('0'))
        compta_direct = compta_fuel_map['direct_by_vehicle'].get(v.id, {})
        compta_direct_entries = []
        for item in compta_fuel_map['direct_entries_by_vehicle'].get(v.id, []):
            entry = item['entry']
            compta_direct_entries.append({
                'date': entry.date_rec.strftime('%d/%m/%Y') if getattr(entry, 'date_rec', None) else '-',
                'compte': str(getattr(entry, 'compte_code', '') or ''),
                'detail': str(getattr(entry, 'detail', '') or ''),
                'description': str(getattr(entry, 'description', '') or ''),
                'litres': float(item['litres'] or 0),
                'montant': float(item['montant'] or 0),
            })
        compta_direct_litres = compta_direct.get('litres', Decimal('0'))
        compta_direct_montant = compta_direct.get('montant', Decimal('0'))
        if litres_total <= 0 and compta_direct.get('litres', Decimal('0')) > 0:
            litres_total = compta_direct_litres
            montant_total = compta_direct_montant
        distance_total = Decimal('0')
        cout_par_litre = None
        litres_100km = None
        compta_direct_100km = None
        if litres_total > 0:
            cout_par_litre = montant_total / litres_total if montant_total else Decimal('0')
        carburant_events = carburant_events_by_vehicule.get(vehicule_key, [])
        releve_events = releve_events_by_vehicule.get(vehicule_key, [])

        if len(carburant_events) >= 2 and releve_events:
            def _last_index_before(target_date):
                selected_index = None
                for releve in releve_events:
                    if releve.date_releve and releve.date_releve <= target_date and releve.index_compteur is not None:
                        selected_index = Decimal(str(releve.index_compteur))
                    elif releve.date_releve and releve.date_releve > target_date:
                        break
                return selected_index

            litres_between_fulls = Decimal('0')
            distance_between_fulls = Decimal('0')
            for previous_usage, current_usage in zip(carburant_events, carburant_events[1:]):
                previous_index = _last_index_before(previous_usage.date_utilisation)
                current_index = _last_index_before(current_usage.date_utilisation)
                if previous_index is None or current_index is None:
                    continue
                delta_index = current_index - previous_index
                if delta_index <= 0:
                    continue
                distance_between_fulls += delta_index
                litres_between_fulls += current_usage.quantite or Decimal('0')

            distance_total = distance_between_fulls
            if litres_between_fulls > 0 and distance_between_fulls > 0:
                litres_100km = (litres_between_fulls * Decimal('100')) / distance_between_fulls
        if compta_direct_litres > 0 and distance_total > 0:
            compta_direct_100km = (compta_direct_litres * Decimal('100')) / distance_total

        analyse_message = "Aucune consommation carburant recente"
        if litres_total > 0 and litres_100km:
            if litres_100km > Decimal('12'):
                analyse_message = "Consommation elevee a surveiller"
            elif litres_100km > Decimal('7'):
                analyse_message = "Consommation dans la norme"
            else:
                analyse_message = "Tres bon rendement carburant"
        elif litres_total > 0:
            analyse_message = "Carburant saisi, mais ecart d'index insuffisant entre deux pleins"

        vehicules_carburant_analyse.append({
            'vehicule': v,
            'litres_total': litres_total,
            'montant_total': montant_total,
            'distance_total': distance_total,
            'nb_pleins': carburant_data.get('nb_pleins', 0),
            'cout_par_litre': cout_par_litre,
            'litres_100km': litres_100km,
            'last_carburant_date': carburant_data.get('last_carburant_date'),
            'last_source_type': carburant_data.get('last_source_type', ''),
            'last_employe_nom': carburant_data.get('last_employe_nom', ''),
            'last_releve_date': releve_data.get('last_releve_date'),
            'last_index': releve_data.get('last_index'),
            'analyse_message': analyse_message,
            'compta_direct_count': compta_direct.get('count', 0),
            'compta_direct_litres': compta_direct_litres,
            'compta_direct_100km': compta_direct_100km,
            'details_json': json.dumps({
                'vehicule': v.immatriculation or '',
                'periode': f"{dict(MONTH_CHOICES).get(analyse_mois, analyse_mois)} {analyse_annee}",
                'compta_entries': compta_direct_entries,
                'user_entries': user_entries,
            }),
        })

    vehicules_carburant_analyse.sort(
        key=lambda row: (
            row['vehicule'].employe_actuel.base.nom_base if getattr(getattr(row['vehicule'], 'employe_actuel', None), 'base', None) and getattr(row['vehicule'].employe_actuel.base, 'nom_base', None) else 'Non affecte',
            row['vehicule'].immatriculation or '',
        )
    )



    stocks_carburant = Stock.objects.select_related('designation', 'base').filter(

        designation__in=carburant_designations

    ).filter(base_id__in=base_ids_scope).order_by('designation__nom')



    magasins = _filter_magasins_scope(
        Magasin.objects.select_related('base'),
        request.user
    ).order_by('nom_magasin')



    utilisations_perso = UtilisationPersoVehicule.objects.select_related(

        'vehicule',

        'employe',

        'directeur',

        'chef',

        'carburant_avant',

        'carburant_apres'

    ).filter(
        Q(vehicule_id__in=vehicules.values_list('id', flat=True)) |
        Q(employe__base_id__in=base_ids_scope)
    ).order_by('-created_at')[:200]

    fournisseurs = Fournisseur.objects.filter(actif=True).order_by('nom_fournisseur')

    fournisseurs_mecaniciens = fournisseurs.filter(type_fournisseur='mecanicien')

    comptes = Compte.objects.filter(achat=True).order_by('nom_compte')



    # Regrouper les vehicules par base (selon l'employe affecte)

    vehicules_groupes = {}

    for v in vehicules:

        employe = getattr(v, 'employe_actuel', None)

        v.has_reparation_planifiee = v.id in reparations_planifiees_ids

        base_name = 'Non affecte'

        if employe and getattr(employe, 'base', None) and getattr(employe.base, 'nom_base', None):

            base_name = employe.base.nom_base

        vehicules_groupes.setdefault(base_name, []).append(v)



    vehicules_groupes_list = [

        {'base': name, 'vehicules': items}

        for name, items in vehicules_groupes.items()

    ]

    vehicules_groupes_list.sort(key=lambda x: x['base'])



    context = {

        'vehicules_groupes': vehicules_groupes_list,

        'vehicules': vehicules,

        'employes': employes,

        'total_vehicules': total_vehicules,

        'vehicules_actifs': vehicules_actifs,

        'vehicules_affectes': vehicules_affectes,

        'vehicules_disponibles': vehicules_disponibles,

        'affectations': affectations,

        'releves': releves,
        'last_arrivee_by_vehicule_json': json.dumps(last_arrivee_by_vehicule),

        'reparations': reparations,
        'commandes_reparations_groupes': commandes_reparations_groupes,

        'pieces_designations': pieces_designations,

        'achats_pieces': achats_pieces,

        'utilisations_pieces': utilisations_pieces,

        'carburant_designations': carburant_designations,

        'achats_carburant': achats_carburant,
        'achats_carburant_non_relie': achats_carburant_non_relie,
        'achats_carburant_non_relie_rows': achats_carburant_non_relie_rows,
        'vehicules_carburant_analyse': vehicules_carburant_analyse,
        'carburant_analyse_since': analyse_since,
        'carburant_analyse_until': analyse_until,
        'month_choices': MONTH_CHOICES,
        'analyse_mois': analyse_mois,
        'analyse_annee': analyse_annee,
        'analyse_years_available': analyse_years_available,

        'stocks_carburant': stocks_carburant,

        'utilisations_perso': utilisations_perso,

        'magasins': magasins,

        'fournisseurs': fournisseurs,

        'fournisseurs_mecaniciens': fournisseurs_mecaniciens,

        'comptes': comptes,

        'is_directeur_user': _is_directeur_user(request.user),

        'is_chef_user': _is_chef_user(request.user),

        'current_employe_id': request.user.employe.id if getattr(request.user, 'employe', None) else None,

    }

    return render(request, 'inventory/vehicules/gestion.html', context)



@login_required
def vehicules_carnets_scans(request):
    """Enregistrement des scans mensuels des carnets de bord vehicules."""
    vehicules_qs = _scoped_vehicules_qs(request.user).order_by('immatriculation').distinct()
    today = timezone.localdate()

    selected_annee = _parse_int(request.GET.get('annee'), today.year)
    selected_vehicule_id = (request.GET.get('vehicule') or '').strip()
    search = (request.GET.get('search') or '').strip()
    prefill_mois = _parse_int(request.GET.get('prefill_mois'), today.month)

    if search:
        vehicules_qs = vehicules_qs.filter(
            Q(immatriculation__icontains=search)
            | Q(marque__icontains=search)
            | Q(modele__icontains=search)
        )

    if request.method == 'POST':
        vehicule_id = (request.POST.get('vehicule_id') or '').strip()
        annee = _parse_int(request.POST.get('annee'), today.year)
        mois = _parse_int(request.POST.get('mois'), 0)
        commentaire = (request.POST.get('commentaire') or '').strip()
        fichier_scan = request.FILES.get('fichier_scan')

        vehicule = vehicules_qs.filter(id=vehicule_id).first()
        if not vehicule:
            messages.error(request, "Vehicule invalide ou non autorise.")
        elif mois < 1 or mois > 12:
            messages.error(request, "Mois invalide.")
        elif annee < 2000 or annee > 2100:
            messages.error(request, "Annee invalide.")
        else:
            existing = CarnetBordMensuelScan.objects.filter(
                vehicule=vehicule,
                annee=annee,
                mois=mois,
            ).first()

            if existing and not fichier_scan:
                existing.commentaire = commentaire
                existing.uploaded_by = request.user
                existing.save(update_fields=['commentaire', 'uploaded_by', 'updated_at'])
                messages.success(request, "Commentaire mis a jour.")
            elif not existing and not fichier_scan:
                messages.error(request, "Le fichier scan est obligatoire pour un nouvel enregistrement.")
            else:
                if existing:
                    existing.fichier_scan = fichier_scan
                    existing.commentaire = commentaire
                    existing.uploaded_by = request.user
                    existing.save()
                    messages.success(request, "Scan mis a jour avec succes.")
                else:
                    CarnetBordMensuelScan.objects.create(
                        vehicule=vehicule,
                        annee=annee,
                        mois=mois,
                        fichier_scan=fichier_scan,
                        commentaire=commentaire,
                        uploaded_by=request.user,
                    )
                    messages.success(request, "Scan enregistre avec succes.")

        redirect_url = reverse('inventory:vehicules_carnets_scans')
        params = [f"annee={selected_annee}"]
        if selected_vehicule_id:
            params.append(f"vehicule={selected_vehicule_id}")
        if search:
            params.append(f"search={search}")
        return redirect(f"{redirect_url}?{'&'.join(params)}")

    scans_qs = CarnetBordMensuelScan.objects.select_related('vehicule', 'uploaded_by').filter(
        vehicule_id__in=vehicules_qs.values_list('id', flat=True),
        annee=selected_annee,
    )
    if selected_vehicule_id:
        scans_qs = scans_qs.filter(vehicule_id=selected_vehicule_id)
    scans_qs = scans_qs.order_by('-updated_at', 'vehicule__immatriculation', '-mois')

    nb_vehicules = vehicules_qs.count()
    total_attendu = nb_vehicules * 12
    total_scans = scans_qs.count()
    taux_couverture = int(round((total_scans / total_attendu) * 100)) if total_attendu > 0 else 0

    months_by_num = dict(MONTH_CHOICES)
    counts_by_month = {m: 0 for m, _ in MONTH_CHOICES}
    for row in scans_qs.values('mois').annotate(total=Count('id')):
        counts_by_month[int(row['mois'])] = int(row['total'])

    stats_mensuelles = [
        {
            'mois': m,
            'label': months_by_num[m],
            'count': counts_by_month[m],
            'pct': int(round((counts_by_month[m] / nb_vehicules) * 100)) if nb_vehicules > 0 else 0,
        }
        for m, _ in MONTH_CHOICES
    ]

    years_available = set(
        CarnetBordMensuelScan.objects.filter(
            vehicule_id__in=vehicules_qs.values_list('id', flat=True)
        ).values_list('annee', flat=True)
    )
    years_available.add(today.year)
    years_available = sorted(years_available, reverse=True)

    context = {
        'vehicules': vehicules_qs,
        'scans': scans_qs,
        'month_choices': MONTH_CHOICES,
        'selected_annee': selected_annee,
        'selected_vehicule_id': selected_vehicule_id,
        'search_query': search,
        'prefill_mois': prefill_mois if 1 <= prefill_mois <= 12 else today.month,
        'years_available': years_available,
        'stats_mensuelles': stats_mensuelles,
        'nb_vehicules': nb_vehicules,
        'total_scans': total_scans,
        'taux_couverture': taux_couverture,
    }
    return render(request, 'inventory/vehicules/carnets_scans.html', context)


@login_required
def vehicules_carnets_suivi(request):
    """Suivi matriciel mensuel des scans carnets de bord vehicules."""
    vehicules_qs = _scoped_vehicules_qs(request.user).order_by('immatriculation').distinct()
    today = timezone.localdate()
    selected_annee = _parse_int(request.GET.get('annee'), today.year)
    search = (request.GET.get('search') or '').strip()

    if search:
        vehicules_qs = vehicules_qs.filter(
            Q(immatriculation__icontains=search)
            | Q(marque__icontains=search)
            | Q(modele__icontains=search)
        )

    scans_qs = CarnetBordMensuelScan.objects.select_related('vehicule').filter(
        vehicule_id__in=vehicules_qs.values_list('id', flat=True),
        annee=selected_annee,
    )

    scans_map = {}
    for scan in scans_qs:
        scans_map[(str(scan.vehicule_id), int(scan.mois))] = scan

    matrix_rows = []
    month_totals = {m: 0 for m, _ in MONTH_CHOICES}
    for vehicule in vehicules_qs:
        month_cells = []
        uploaded_count = 0
        for month_num, _month_label in MONTH_CHOICES:
            scan = scans_map.get((str(vehicule.id), month_num))
            month_cells.append({'mois': month_num, 'scan': scan})
            if scan:
                uploaded_count += 1
                month_totals[month_num] += 1

        matrix_rows.append(
            {
                'vehicule': vehicule,
                'month_cells': month_cells,
                'uploaded_count': uploaded_count,
                'missing_count': 12 - uploaded_count,
                'coverage_pct': int(round((uploaded_count / 12) * 100)),
            }
        )

    nb_vehicules = vehicules_qs.count()
    total_cases = nb_vehicules * 12
    total_scans = scans_qs.count()
    taux_global = int(round((total_scans / total_cases) * 100)) if total_cases > 0 else 0

    month_summaries = [
        {
            'mois': month_num,
            'label': month_label,
            'count': month_totals[month_num],
            'pct': int(round((month_totals[month_num] / nb_vehicules) * 100)) if nb_vehicules > 0 else 0,
        }
        for month_num, month_label in MONTH_CHOICES
    ]

    years_available = set(
        CarnetBordMensuelScan.objects.filter(
            vehicule_id__in=vehicules_qs.values_list('id', flat=True)
        ).values_list('annee', flat=True)
    )
    years_available.add(today.year)
    years_available = sorted(years_available, reverse=True)

    context = {
        'matrix_rows': matrix_rows,
        'month_choices': MONTH_CHOICES,
        'month_summaries': month_summaries,
        'selected_annee': selected_annee,
        'search_query': search,
        'years_available': years_available,
        'nb_vehicules': nb_vehicules,
        'total_scans': total_scans,
        'taux_global': taux_global,
    }
    return render(request, 'inventory/vehicules/carnets_suivi.html', context)





@csrf_exempt

@login_required

@require_http_methods(["POST", "DELETE"])

def api_vehicule_delete(request, vehicule_id):

    """API pour supprimer un véhicule saisi en doublon."""

    try:

        vehicule = get_object_or_404(_scoped_vehicules_qs(request.user), id=vehicule_id)

        if not (getattr(request.user, 'is_superuser', False) or _is_directeur_user(request.user)):
            return JsonResponse({'success': False, 'error': 'Suppression réservée au Directeur'}, status=403)

        linked_counts = {
            'affectations': vehicule.affectations.count(),
            'releves': vehicule.releves_compteur.count(),
            'reparations': vehicule.reparations.count(),
            'utilisations_pieces': vehicule.utilisations_pieces.count(),
            'utilisations_carburant': vehicule.utilisations_carburant.count(),
            'utilisations_perso': vehicule.utilisations_perso.count(),
            'carnets_scans': vehicule.carnets_bord_scans.count(),
        }

        if sum(linked_counts.values()) > 0:
            return JsonResponse(
                {
                    'success': False,
                    'error': "Impossible de supprimer ce véhicule car il possède déjà un historique.",
                    'details': linked_counts,
                },
                status=400,
            )

        if vehicule.photo:
            vehicule.photo.delete(save=False)
        if vehicule.carte_grise:
            vehicule.carte_grise.delete(save=False)

        immatriculation = vehicule.immatriculation
        vehicule.delete()

        return JsonResponse({'success': True, 'message': f'Véhicule {immatriculation} supprimé avec succès'})

    except Exception as e:

        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt

@login_required

@require_http_methods(["POST"])

def api_vehicule_create(request):

    """API pour crer un vhicule"""

    try:

        def parse_bool(value, default=False):

            if value is None:

                return default

            if isinstance(value, bool):

                return value

            return str(value).lower() in ['1', 'true', 'on', 'yes']



        files = request.FILES if request.FILES else None
        if request.content_type and request.content_type.startswith('multipart/form-data'):

            data = request.POST

        else:

            data = json.loads(request.body or '{}')



        # Validation des champs obligatoires

        required_fields = ['type_vehicule', 'immatriculation', 'marque', 'modele', 'date_mise_circulation']

        for field in required_fields:

            if not data.get(field):

                return JsonResponse({'success': False, 'error': f'Le champ {field} est obligatoire'}, status=400)



        # Vrifier unicit immatriculation

        if Vehicule.objects.filter(immatriculation=data['immatriculation']).exists():

            return JsonResponse({

                'success': False,

                'error': f"Un vhicule avec l'immatriculation {data['immatriculation']} existe dj"

            }, status=400)



        # Convertir la date

        date_mise_circulation = datetime.strptime(data['date_mise_circulation'], '%Y-%m-%d').date()



        # Crer le vhicule

        vehicule = Vehicule.objects.create(

            type_vehicule=data['type_vehicule'],

            immatriculation=data['immatriculation'],

            marque=data['marque'],

            modele=data['modele'],

            date_mise_circulation=date_mise_circulation,

            numero_chassis=data.get('numero_chassis', ''),

            couleur=data.get('couleur', ''),

            annee_fabrication=int(data['annee_fabrication']) if data.get('annee_fabrication') else None,

            compteur_fonctionnel=parse_bool(data.get('compteur_fonctionnel', True), True),

            notes=data.get('notes', '')

        )

        if files and files.get('carte_grise'):

            vehicule.carte_grise = files.get('carte_grise')

            vehicule.save(update_fields=['carte_grise'])

        if files and files.get('photo'):

            vehicule.photo = files.get('photo')

            vehicule.save(update_fields=['photo'])



        return JsonResponse({

            'success': True,

            'message': 'Vhicule cr avec succs',

            'vehicule_id': str(vehicule.id)

        })



    except Exception as e:

        return JsonResponse({'success': False, 'error': str(e)}, status=500)





@csrf_exempt

@login_required

@require_http_methods(["POST"])

def api_vehicule_update(request, vehicule_id):

    """API pour mettre  jour un vhicule"""

    try:

        vehicule = get_object_or_404(_scoped_vehicules_qs(request.user), id=vehicule_id)

        def parse_bool(value, default=False):

            if value is None:

                return default

            if isinstance(value, bool):

                return value

            return str(value).lower() in ['1', 'true', 'on', 'yes']



        files = request.FILES if request.FILES else None
        if request.content_type and request.content_type.startswith('multipart/form-data'):

            data = request.POST

        else:

            data = json.loads(request.body or '{}')



        # Mise  jour des champs

        if 'type_vehicule' in data:

            vehicule.type_vehicule = data['type_vehicule']

        if 'immatriculation' in data:

            # Vrifier unicit sauf pour ce vhicule

            if Vehicule.objects.filter(immatriculation=data['immatriculation']).exclude(id=vehicule_id).exists():

                return JsonResponse({

                    'success': False,

                    'error': f"Un autre vhicule avec l'immatriculation {data['immatriculation']} existe dj"

                }, status=400)

            vehicule.immatriculation = data['immatriculation']

        if 'marque' in data:

            vehicule.marque = data['marque']

        if 'modele' in data:

            vehicule.modele = data['modele']

        if 'date_mise_circulation' in data:

            vehicule.date_mise_circulation = datetime.strptime(data['date_mise_circulation'], '%Y-%m-%d').date()

        if 'numero_chassis' in data:

            vehicule.numero_chassis = data['numero_chassis']

        if 'couleur' in data:

            vehicule.couleur = data['couleur']

        if 'annee_fabrication' in data:

            vehicule.annee_fabrication = int(data['annee_fabrication']) if data['annee_fabrication'] else None

        if 'compteur_fonctionnel' in data:

            vehicule.compteur_fonctionnel = parse_bool(data['compteur_fonctionnel'], vehicule.compteur_fonctionnel)

        if 'actif' in data:

            vehicule.actif = parse_bool(data['actif'], vehicule.actif)

        if 'notes' in data:

            vehicule.notes = data['notes']
        if files and files.get('carte_grise'):

            vehicule.carte_grise = files.get('carte_grise')
        if files and files.get('photo'):

            vehicule.photo = files.get('photo')

        elif data.get('delete_photo') == '1':

            if vehicule.photo:

                vehicule.photo.delete(save=False)

            vehicule.photo = None

        vehicule.save()



        return JsonResponse({'success': True, 'message': 'Vhicule mis  jour avec succs'})



    except Exception as e:

        return JsonResponse({'success': False, 'error': str(e)}, status=500)





@csrf_exempt

@login_required

@require_http_methods(["POST"])

def api_affectation_create(request):

    """API pour crer une affectation de vhicule"""

    try:

        data = json.loads(request.body)



        # Validation

        vehicule = get_object_or_404(_scoped_vehicules_qs(request.user), id=data['vehicule_id'])

        employe = get_object_or_404(_scoped_employes_qs(request.user), id=data['employe_id'])

        date_debut = datetime.strptime(data['date_debut'], '%Y-%m-%d').date()



        # Vrifier qu'il n'y a pas dj une affectation active

        affectation_active = AffectationVehicule.objects.filter(

            vehicule=vehicule,

            date_fin__isnull=True

        ).first()



        if affectation_active:

            # Terminer l'ancienne affectation

            affectation_active.date_fin = date_debut - timedelta(days=1)

            affectation_active.save()



        # Crer la nouvelle affectation

        affectation = AffectationVehicule.objects.create(

            vehicule=vehicule,

            employe=employe,

            date_debut=date_debut,

            notes=data.get('notes', '')

        )



        return JsonResponse({

            'success': True,

            'message': 'Affectation cre avec succs',

            'affectation_id': str(affectation.id)

        })



    except Exception as e:

        return JsonResponse({'success': False, 'error': str(e)}, status=500)





@csrf_exempt

@login_required

@require_http_methods(["POST"])

def api_affectation_terminer(request, affectation_id):

    """API pour terminer une affectation"""

    try:

        affectation = get_object_or_404(
            AffectationVehicule.objects.filter(
                vehicule_id__in=_scoped_vehicules_qs(request.user).values_list('id', flat=True)
            ),
            id=affectation_id
        )

        data = json.loads(request.body)



        date_fin = datetime.strptime(data['date_fin'], '%Y-%m-%d').date()

        affectation.date_fin = date_fin

        if 'notes' in data:

            affectation.notes = data['notes']

        affectation.save()



        return JsonResponse({'success': True, 'message': 'Affectation termine avec succs'})



    except Exception as e:

        return JsonResponse({'success': False, 'error': str(e)}, status=500)





@csrf_exempt

@login_required

@require_http_methods(["POST", "DELETE"])

def api_affectation_delete(request, affectation_id):

    """API pour supprimer une affectation."""

    try:

        affectation = get_object_or_404(
            AffectationVehicule.objects.select_related('vehicule', 'employe').filter(
                vehicule_id__in=_scoped_vehicules_qs(request.user).values_list('id', flat=True)
            ),
            id=affectation_id
        )

        if not (getattr(request.user, 'is_superuser', False) or _is_directeur_user(request.user)):
            return JsonResponse({
                'success': False,
                'error': 'Suppression réservée au Directeur'
            }, status=403)

        vehicule_label = getattr(affectation.vehicule, 'immatriculation', '') or 'Véhicule'
        employe_label = getattr(affectation.employe, 'surnom', '') or getattr(affectation.employe, 'nom_complet', '') or 'Employé'
        affectation.delete()

        return JsonResponse({
            'success': True,
            'message': f'Affectation supprimée : {vehicule_label} / {employe_label}'
        })

    except Exception as e:

        return JsonResponse({'success': False, 'error': str(e)}, status=500)




@csrf_exempt

@login_required

@require_http_methods(["POST"])

def api_releve_create(request):

    """API pour crer un relev de compteur"""

    try:

        if request.content_type and 'application/json' in request.content_type:
            data = json.loads(request.body)
        else:
            data = request.POST



        vehicule = get_object_or_404(_scoped_vehicules_qs(request.user), id=data['vehicule_id'])

        employe = get_object_or_404(_scoped_employes_qs(request.user), id=data['employe_id']) if data.get('employe_id') else None



        date_releve = datetime.strptime(data['date_releve'], '%Y-%m-%d').date()

        saisie_manuelle = str(data.get('saisie_manuelle', '')).lower() in ['on', 'true', '1', 'yes']



        # Valider l'index ou la distance

        index_compteur = Decimal(str(data['index_compteur'])) if data.get('index_compteur') else None

        distance_parcourue = Decimal(str(data['distance_parcourue']))



        releve = RelevéCompteur.objects.create(

            vehicule=vehicule,

            employe=employe,

            date_releve=date_releve,

            index_compteur=index_compteur,

            lieu_depart=data.get('lieu_depart', ''),

            lieu_arrivee=data.get('lieu_arrivee', ''),

            distance_parcourue=distance_parcourue,

            saisie_manuelle=saisie_manuelle,

            notes=data.get('notes', ''),
            photo_compteur=request.FILES.get('photo_compteur')

        )



        # Carburant optionnel lie au releve

        carburant_source = data.get('carburant_source_type')

        carburant_quantite = data.get('carburant_quantite')

        carburant_montant = data.get('carburant_montant')

        if carburant_source and carburant_quantite:

            qte = Decimal(str(carburant_quantite))

            if qte > 0:

                if carburant_source == 'achat':

                    purchase_item_id = data.get('carburant_purchase_item_id')
                    purchase_item = None
                    notes = data.get('carburant_notes', '') or ''

                    if purchase_item_id:
                        purchase_item = get_object_or_404(_scoped_purchase_items_qs(request.user), id=purchase_item_id)
                    else:
                        notes = notes or "Achat carburant non relié à la compta"

                    UtilisationCarburantVehicule.objects.create(

                        vehicule=vehicule,

                        employe=employe,

                        date_utilisation=date_releve,

                        quantite=qte,

                        montant=Decimal(str(carburant_montant)) if carburant_montant else None,

                        source_type='achat',

                        purchase_item=purchase_item,

                        releve=releve,

                        is_personnel=False,

                        notes=notes,

                        created_by=request.user if request.user.is_authenticated else None

                    )

                elif carburant_source == 'stock':

                    magasin_id = data.get('carburant_magasin_id')

                    designation_id = data.get('carburant_designation_id')

                    if not magasin_id or not designation_id:

                        raise ValueError('Magasin et designation requis')

                    magasin = get_object_or_404(_scoped_magasins_qs(request.user), id=magasin_id)

                    designation = get_object_or_404(Designation, id=designation_id)

                    stock = Stock.objects.filter(base=magasin.base, designation=designation).first()

                    if stock is None:

                        raise ValueError('Stock carburant introuvable')

                    if qte > stock.current_quantity:

                        raise ValueError('Quantite insuffisante en stock')

                    stock.current_quantity = stock.current_quantity - qte

                    stock.save()

                    movement = StockMovement.objects.create(

                        designation=designation,

                        base=stock.base,

                        movement_type='sortie',

                        quantity=qte,

                        movement_date=datetime.now(),

                        reference=f"Carburant releve {releve.id}",

                        notes='Carburant utilise lors du releve',

                        employee=employe

                    )

                    UtilisationCarburantVehicule.objects.create(

                        vehicule=vehicule,

                        employe=employe,

                        date_utilisation=date_releve,

                        quantite=qte,

                        montant=Decimal(str(carburant_montant)) if carburant_montant else None,

                        source_type='stock',

                        stock_movement=movement,

                        magasin=magasin,

                        releve=releve,

                        is_personnel=False,

                        created_by=request.user if request.user.is_authenticated else None

                    )



        return JsonResponse({

            'success': True,

            'message': 'Relev cr avec succs',

            'releve_id': str(releve.id)

        })



    except Exception as e:

        return JsonResponse({'success': False, 'error': str(e)}, status=500)





@csrf_exempt

@login_required

@require_http_methods(["POST"])

def api_reparation_create(request):

    """API pour crer une rparation"""

    try:

        data = json.loads(request.body)



        vehicule = get_object_or_404(_scoped_vehicules_qs(request.user), id=data['vehicule_id'])

        mode = data.get('mode', 'valider')

        pieces_list = data.get('pieces', []) or []

        pieces_commande = data.get('pieces_commande', []) or []

        reparation_id = data.get('reparation_id')



        with transaction.atomic():

            if mode == 'planifier':

                if not data.get('date_prevue'):

                    return JsonResponse({'success': False, 'error': 'Date Prévue obligatoire'}, status=400)

                if not data.get('libelle'):

                    return JsonResponse({'success': False, 'error': 'Libell? obligatoire'}, status=400)



                date_prevue = datetime.strptime(data['date_prevue'], '%Y-%m-%d').date()



                reparation = ReparationVehicule.objects.create(

                    vehicule=vehicule,

                    date_prevue=date_prevue,

                    type_reparation=data.get('type_reparation', 'reparation'),

                    libelle=data.get('libelle', ''),

                    description=data.get('description', ''),

                    statut='planifiee',

                    notes=data.get('notes', '')

                )



                purchase = None

                if pieces_commande:

                    from datetime import datetime as dt_now



                    year = dt_now.now().year

                    last_purchase = Purchase.objects.filter(

                        purchase_number__startswith=f'A-{year}-'

                    ).order_by('-purchase_number').first()



                    if last_purchase:

                        last_num = int(last_purchase.purchase_number.split('-')[-1])

                        new_num = last_num + 1

                    else:

                        new_num = 1



                    purchase_number = f'A-{year}-{new_num:05d}'



                    purchase = Purchase.objects.create(

                        purchase_number=purchase_number,

                        purchase_date=date_prevue,

                        order_date=date_prevue,

                        purchase_status='commande',

                        fournisseur_id=data.get('fournisseur_id') or None,

                        magasin_id=data.get('magasin_id') or None,

                        compte_id=data.get('compte_id') or None,

                        ordered_by_id=data.get('ordered_by_id') or None,

                        notes=data.get('purchase_notes', '') or f"Commande lie  la rparation {reparation.libelle}"

                    )



                    total_amount = Decimal('0')

                    for piece in pieces_commande:

                        designation_id = piece.get('designation_id')

                        quantite = Decimal(str(piece.get('quantite', '0') or '0'))

                        unit_price = Decimal(str(piece.get('unit_price', '0') or '0'))

                        if not designation_id or quantite <= 0 or unit_price < 0:

                            raise ValueError('Pice  commander invalide')



                        designation = get_object_or_404(Designation, id=designation_id)

                        if not _is_piece_vehicule(designation):

                            raise ValueError('Piece vehicule introuvable')



                        item_total = quantite * unit_price

                        PurchaseItem.objects.create(

                            purchase=purchase,

                            designation=designation,

                            quantity_ordered=quantite,

                            unit_price=unit_price,

                            total_price=item_total

                        )

                        total_amount += item_total



                    purchase.total_amount = total_amount

                    purchase.save(update_fields=['total_amount'])



                    reparation.purchase = purchase

                    reparation.statut = 'commande'

                    reparation.save(update_fields=['purchase', 'statut'])



                return JsonResponse({

                    'success': True,

                    'message': 'Rparation planifie avec succ?s',

                    'reparation_id': str(reparation.id),

                    'purchase_id': str(purchase.id) if purchase else None

                })



            # Mode validation / rparation ralise

            if not data.get('date_reparation'):

                return JsonResponse({'success': False, 'error': 'Date de r?paration obligatoire'}, status=400)



            date_reparation = datetime.strptime(data['date_reparation'], '%Y-%m-%d').date()



            if reparation_id:

                reparation = get_object_or_404(ReparationVehicule, id=reparation_id)

                if reparation.statut == 'terminee':

                    return JsonResponse({'success': False, 'error': 'R?paration d?j? valid?e'}, status=400)

                reparation.date_reparation = date_reparation

                reparation.type_reparation = data.get('type_reparation', reparation.type_reparation)

                reparation.libelle = data.get('libelle', reparation.libelle)

                reparation.description = data.get('description', reparation.description or '')

                reparation.nom_mecanicien = data.get('nom_mecanicien', reparation.nom_mecanicien or '')

                reparation.garage = data.get('garage', reparation.garage or '')

                reparation.pieces_utilisees = data.get('pieces_utilisees', reparation.pieces_utilisees or '')

                reparation.cout_pieces = Decimal(str(data.get('cout_pieces', reparation.cout_pieces or 0)))

                reparation.cout_main_oeuvre = Decimal(str(data.get('cout_main_oeuvre', reparation.cout_main_oeuvre or 0)))

                reparation.index_compteur = Decimal(str(data['index_compteur'])) if data.get('index_compteur') else None

                reparation.notes = data.get('notes', reparation.notes or '')

                reparation.statut = 'terminee'

                reparation.save()

            else:

                if not data.get('libelle'):

                    return JsonResponse({'success': False, 'error': 'Libell? obligatoire'}, status=400)

                reparation = ReparationVehicule.objects.create(

                    vehicule=vehicule,

                    date_reparation=date_reparation,

                    type_reparation=data.get('type_reparation', 'reparation'),

                    libelle=data.get('libelle', ''),

                    description=data.get('description', ''),

                    nom_mecanicien=data.get('nom_mecanicien', ''),

                    garage=data.get('garage', ''),

                    pieces_utilisees=data.get('pieces_utilisees', ''),

                    cout_pieces=Decimal(str(data.get('cout_pieces', 0))),

                    cout_main_oeuvre=Decimal(str(data.get('cout_main_oeuvre', 0))),

                    index_compteur=Decimal(str(data['index_compteur'])) if data.get('index_compteur') else None,

                    notes=data.get('notes', ''),

                    statut='terminee'

                )



            # Creer les utilisations de pieces et impacter le stock

            for piece in pieces_list:

                designation_id = piece.get('designation_id')

                magasin_id = piece.get('magasin_id')

                purchase_item_id = piece.get('purchase_item_id')

                quantite = Decimal(str(piece.get('quantite', '0') or '0'))



                if not designation_id or not magasin_id or not purchase_item_id or quantite <= 0:

                    raise ValueError('Piece invalide dans la liste')



                designation = get_object_or_404(Designation, id=designation_id)

                if not _is_piece_vehicule(designation):

                    raise ValueError('Piece vehicule introuvable')

                purchase_item = get_object_or_404(_scoped_purchase_items_qs(request.user), id=purchase_item_id)

                if purchase_item.designation_id != designation.id:

                    raise ValueError('Achat invalide pour cette piece')

                magasin = get_object_or_404(_scoped_magasins_qs(request.user), id=magasin_id)



                stock = Stock.objects.filter(base=magasin.base, designation=designation).first()

                if stock is None:

                    raise ValueError('Stock introuvable pour cette piece')

                if quantite > stock.current_quantity:

                    raise ValueError('Quantite insuffisante en stock')



                stock.current_quantity = stock.current_quantity - quantite

                stock.save()



                StockMovement.objects.create(

                    designation=designation,

                    base=stock.base,

                    movement_type='sortie',

                    quantity=quantite,

                    movement_date=datetime.now(),

                    reference=f"Utilisation pieces reparation {reparation.id}",

                    notes='Pieces utilisees dans une reparation',

                )



                UtilisationPieceVehicule.objects.create(

                    vehicule=vehicule,

                    designation=designation,

                    purchase_item=purchase_item,

                    magasin=magasin,

                    quantite=quantite,

                    date_utilisation=date_reparation,

                    motif=piece.get('motif', ''),

                    notes=piece.get('notes', ''),

                    reparation=reparation,

                    created_by=request.user if request.user.is_authenticated else None

                )



        return JsonResponse({

            'success': True,

            'message': 'Reparation enregistree avec succes',

            'reparation_id': str(reparation.id)

        })



    except Exception as e:

        return JsonResponse({'success': False, 'error': str(e)}, status=500)





@csrf_exempt

@login_required

@require_http_methods(["POST", "DELETE"])

def api_reparation_delete(request, reparation_id):

    """API pour supprimer une réparation."""

    try:

        reparation = get_object_or_404(
            ReparationVehicule.objects.select_related('vehicule').filter(
                vehicule_id__in=_scoped_vehicules_qs(request.user).values_list('id', flat=True)
            ),
            id=reparation_id
        )

        if not (getattr(request.user, 'is_superuser', False) or _is_directeur_user(request.user)):
            return JsonResponse({
                'success': False,
                'error': 'Suppression réservée au Directeur'
            }, status=403)

        vehicule_label = getattr(reparation.vehicule, 'immatriculation', '') or 'Véhicule'
        libelle = getattr(reparation, 'libelle', '') or 'Réparation'
        reparation.delete()

        return JsonResponse({
            'success': True,
            'message': f'Réparation supprimée : {vehicule_label} / {libelle}'
        })

    except Exception as e:

        return JsonResponse({'success': False, 'error': str(e)}, status=500)




@login_required

@require_http_methods(["GET"])

def api_reparation_planifiee_detail(request, reparation_id):

    """API pour rcuprer le dtail d'une rparation planifie"""

    reparation = get_object_or_404(

        ReparationVehicule.objects.select_related('vehicule', 'purchase').prefetch_related('purchase__purchase_items__designation'),

        id=reparation_id

    )



    purchase = reparation.purchase

    purchase_data = None

    pieces_commande = []



    if purchase:

        purchase_data = {

            'id': str(purchase.id),

            'fournisseur_id': str(purchase.fournisseur_id) if purchase.fournisseur_id else '',

            'magasin_id': str(purchase.magasin_id) if purchase.magasin_id else '',

            'compte_id': str(purchase.compte_id) if purchase.compte_id else '',

            'ordered_by_id': str(purchase.ordered_by_id) if purchase.ordered_by_id else '',

            'notes': purchase.notes or '',

        }



        for item in purchase.purchase_items.select_related('designation').all():

            pieces_commande.append({

                'designation_id': str(item.designation_id) if item.designation_id else '',

                'designation_name': item.designation.nom if item.designation else '',

                'quantite': str(item.quantity_ordered),

                'unit_price': str(item.unit_price),

            })



    rep_data = {

        'id': str(reparation.id),

        'vehicule_id': str(reparation.vehicule_id),

        'vehicule_immatriculation': reparation.vehicule.immatriculation if reparation.vehicule else '',

        'date_prevue': reparation.date_prevue.isoformat() if reparation.date_prevue else '',

        'date_reparation': reparation.date_reparation.isoformat() if reparation.date_reparation else '',

        'type_reparation': reparation.type_reparation,

        'libelle': reparation.libelle,

        'description': reparation.description or '',

        'notes': reparation.notes or '',

        'statut': reparation.statut,

    }



    return JsonResponse({

        'success': True,

        'reparation': rep_data,

        'purchase': purchase_data,

        'pieces_commande': pieces_commande,

    })





@login_required

def reparation_planifiee_detail(request, reparation_id):

    """D?tail d'une r?paration planifi?e avec suivi de la commande"""

    reparation = get_object_or_404(

        ReparationVehicule.objects.select_related('vehicule', 'purchase').prefetch_related('purchase__purchase_items__designation'),

        id=reparation_id

    )



    purchase = reparation.purchase

    purchase_items = []

    if purchase:

        purchase_items = purchase.purchase_items.select_related('designation').all()



    utilisations = UtilisationPieceVehicule.objects.select_related(

        'designation', 'magasin', 'purchase_item', 'employe'

    ).filter(reparation=reparation).order_by('-date_utilisation')



    context = {

        'reparation': reparation,

        'purchase': purchase,

        'purchase_items': purchase_items,

        'utilisations': utilisations,

    }



    return render(request, 'inventory/vehicules/reparation_detail.html', context)





@login_required

def details_vehicule(request, vehicule_id):

    """Page de dtails d'un vhicule avec rparations et consommation"""

    vehicule = get_object_or_404(_scoped_vehicules_qs(request.user), id=vehicule_id)

    affectations = list(
        AffectationVehicule.objects.select_related('employe')
        .filter(vehicule=vehicule)
        .order_by('-date_debut')
    )

    reparations = list(
        ReparationVehicule.objects.select_related('purchase')
        .filter(vehicule=vehicule)
        .order_by('-date_reparation', '-date_prevue', '-created_at')
    )

    releves = list(
        RelevéCompteur.objects.select_related('employe')
        .filter(vehicule=vehicule)
        .order_by('-date_releve', '-created_at')
    )

    carburant_qs = UtilisationCarburantVehicule.objects.select_related('employe').filter(
        vehicule=vehicule
    ).order_by('-date_utilisation', '-created_at')

    carburant_data = []
    consommation_totale = Decimal('0')
    distance_totale = Decimal('0')

    for carb in carburant_qs:
        quantite = carb.quantite or Decimal('0')
        montant = carb.montant or Decimal('0')
        carburant_data.append({
            'date': carb.date_utilisation,
            'employe': carb.employe.nom_complet if getattr(carb, 'employe', None) else '-',
            'quantite': quantite,
            'montant': montant,
            'source_type': carb.get_source_type_display() if getattr(carb, 'source_type', None) else '',
            'notes': carb.notes or '',
        })
        consommation_totale += quantite

    distance_totale = sum((releve.distance_parcourue or Decimal('0')) for releve in releves)



    # Calculer consommation au 100 km

    consommation_100km = Decimal('0')

    if distance_totale > 0:

        consommation_100km = (consommation_totale / distance_totale) * 100



    # Cot total des rparations

    cout_total_reparations = sum(
        ((reparation.cout_pieces or Decimal('0')) + (reparation.cout_main_oeuvre or Decimal('0')))
        for reparation in reparations
    )



    context = {

        'vehicule': vehicule,

        'affectations': affectations,

        'reparations': reparations,

        'releves': releves,

        'carburant_data': carburant_data,

        'consommation_totale': consommation_totale,

        'distance_totale': distance_totale,

        'consommation_100km': consommation_100km,

        'cout_total_reparations': cout_total_reparations,

    }



    return render(request, 'inventory/vehicules/details.html', context)





@login_required

def recap_mensuel_carburant(request):

    """Rapport mensuel de suivi consommation carburant par base."""
    today = timezone.localdate()
    mois = _parse_int(request.GET.get('mois'), today.month)
    annee = _parse_int(request.GET.get('annee'), today.year)
    if mois < 1 or mois > 12:
        mois = today.month
    if annee < 2000 or annee > 2100:
        annee = today.year

    month_start, month_end, prev_month_end = _month_bounds(annee, mois)

    scoped_bases = _filter_bases_by_scope(Base.objects.all(), request.user)
    user_org_id = getattr(getattr(getattr(request.user, 'employe', None), 'base', None), 'organisation_id', None)
    if user_org_id:
        scoped_bases = scoped_bases.filter(organisation_id=user_org_id)
    scoped_bases = scoped_bases.order_by('nom_base')
    selected_base_id = (request.GET.get('base') or '').strip()
    if selected_base_id and not scoped_bases.filter(id=selected_base_id).exists():
        selected_base_id = ''
    selected_base = scoped_bases.filter(id=selected_base_id).first() if selected_base_id else scoped_bases.first()
    selected_base_id = str(selected_base.id) if selected_base else ''

    def _build_redirect_url(base_id, year_value, month_value):
        redirect_url = reverse('inventory:recap_mensuel_carburant')
        params = [f"annee={year_value}", f"mois={month_value}"]
        if base_id:
            params.append(f"base={base_id}")
        return f"{redirect_url}?{'&'.join(params)}"

    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        post_annee = _parse_int(request.POST.get('annee'), annee)
        post_mois = _parse_int(request.POST.get('mois'), mois)
        post_base_id = (request.POST.get('base') or selected_base_id or '').strip()

        if post_mois < 1 or post_mois > 12:
            post_mois = mois
        if post_annee < 2000 or post_annee > 2100:
            post_annee = annee
        if post_base_id and not scoped_bases.filter(id=post_base_id).exists():
            post_base_id = selected_base_id

        post_base = scoped_bases.filter(id=post_base_id).first() if post_base_id else None
        scoped_vehicule_ids = {
            str(v) for v in _scoped_vehicules_qs(request.user).values_list('id', flat=True)
        }

        if action == 'save_remarques':
            if not post_base:
                messages.error(request, "Base invalide pour enregistrer les remarques.")
            else:
                saved_count = 0
                removed_count = 0
                for key, value in request.POST.items():
                    if not key.startswith('remark__'):
                        continue
                    vehicule_id = key.split('__', 1)[1].strip()
                    if not vehicule_id or vehicule_id not in scoped_vehicule_ids:
                        continue
                    remarque = (value or '').strip()
                    if remarque:
                        RapportConsommationCarburantRemarque.objects.update_or_create(
                            base=post_base,
                            vehicule_id=vehicule_id,
                            annee=post_annee,
                            mois=post_mois,
                            defaults={'remarque': remarque, 'updated_by': request.user},
                        )
                        saved_count += 1
                    else:
                        deleted, _ = RapportConsommationCarburantRemarque.objects.filter(
                            base=post_base,
                            vehicule_id=vehicule_id,
                            annee=post_annee,
                            mois=post_mois,
                        ).delete()
                        if deleted:
                            removed_count += 1
                messages.success(
                    request,
                    f"Remarques mises a jour ({saved_count} enregistrees, {removed_count} supprimees).",
                )
        elif action == 'upload_rapport_scan':
            if not post_base:
                messages.error(request, "Base invalide pour enregistrer le scan.")
            else:
                fichier_scan = request.FILES.get('rapport_scan')
                commentaire = (request.POST.get('commentaire_scan') or '').strip()
                existing = RapportConsommationCarburantScan.objects.filter(
                    base=post_base,
                    annee=post_annee,
                    mois=post_mois,
                ).first()
                if existing and not fichier_scan:
                    existing.commentaire = commentaire
                    existing.uploaded_by = request.user
                    existing.save(update_fields=['commentaire', 'uploaded_by', 'updated_at'])
                    messages.success(request, "Commentaire du scan mis a jour.")
                elif not existing and not fichier_scan:
                    messages.error(request, "Le fichier scan est obligatoire pour un nouvel enregistrement.")
                else:
                    if existing:
                        existing.fichier_scan = fichier_scan
                        existing.commentaire = commentaire
                        existing.uploaded_by = request.user
                        existing.save()
                        messages.success(request, "Scan du rapport remplace avec succes.")
                    else:
                        RapportConsommationCarburantScan.objects.create(
                            base=post_base,
                            annee=post_annee,
                            mois=post_mois,
                            fichier_scan=fichier_scan,
                            commentaire=commentaire,
                            uploaded_by=request.user,
                        )
                        messages.success(request, "Scan du rapport enregistre avec succes.")
        else:
            messages.error(request, "Action non reconnue.")

        return redirect(_build_redirect_url(post_base_id, post_annee, post_mois))

    blocked_message = None
    last_cloture = ClotureCarburantMois.objects.order_by('-annee', '-mois').first()
    if last_cloture:
        selected_key = annee * 12 + mois
        allowed_key = last_cloture.annee * 12 + last_cloture.mois + 1
        if selected_key > allowed_key:
            annee = (allowed_key - 1) // 12
            mois = (allowed_key - 1) % 12 + 1
            month_start, month_end, prev_month_end = _month_bounds(annee, mois)
            blocked_message = (
                f"Cloturez d'abord le mois {last_cloture.mois:02d}/{last_cloture.annee} "
                "avant de passer au mois suivant."
            )

    cloture_mois = ClotureCarburantMois.objects.filter(mois=mois, annee=annee).first()
    unlinked_count = UtilisationCarburantVehicule.objects.filter(
        source_type='achat',
        base_diamex_entry__isnull=True,
        date_utilisation__year=annee,
        date_utilisation__month=mois
    ).count()

    scoped_vehicules = _scoped_vehicules_qs(request.user).distinct()
    scoped_vehicule_ids = list(scoped_vehicules.values_list('id', flat=True))
    base_ids = [selected_base.id] if selected_base else list(scoped_bases.values_list('id', flat=True))

    vehicle_ids = set()
    latest_affectation_by_vehicle = {}
    affectations_qs = AffectationVehicule.objects.select_related('vehicule', 'employe', 'employe__base').filter(
        vehicule_id__in=scoped_vehicule_ids,
        employe__base_id__in=base_ids,
        date_debut__lte=month_end,
    ).filter(
        Q(date_fin__isnull=True) | Q(date_fin__gte=month_start)
    ).order_by('vehicule_id', '-date_debut', '-created_at')

    for aff in affectations_qs:
        vehicle_ids.add(aff.vehicule_id)
        if aff.vehicule_id not in latest_affectation_by_vehicle:
            latest_affectation_by_vehicle[aff.vehicule_id] = aff

    active_affectations = list(AffectationVehicule.objects.filter(
        vehicule_id__in=scoped_vehicule_ids,
        employe__base_id__in=base_ids,
        date_fin__isnull=True,
    ).values_list('vehicule_id', flat=True))
    vehicle_ids.update(active_affectations)

    releves_mois_scope_qs = RelevéCompteur.objects.filter(
        vehicule_id__in=scoped_vehicule_ids,
        date_releve__gte=month_start,
        date_releve__lte=month_end,
        employe__base_id__in=base_ids,
    ).values_list('vehicule_id', flat=True)
    vehicle_ids.update(releves_mois_scope_qs)

    usages_scope_qs = UtilisationCarburantVehicule.objects.filter(
        vehicule_id__in=scoped_vehicule_ids,
        date_utilisation__gte=month_start,
        date_utilisation__lte=month_end,
    ).filter(
        Q(employe__base_id__in=base_ids)
        | Q(magasin__base_id__in=base_ids)
        | Q(purchase_item__purchase__magasin__base_id__in=base_ids)
        | Q(purchase_item__purchase__base_id__in=base_ids)
    ).values_list('vehicule_id', flat=True)
    vehicle_ids.update(usages_scope_qs)

    vehicules_qs = scoped_vehicules.filter(id__in=list(vehicle_ids)).order_by('immatriculation')
    vehicule_ids_list = list(vehicules_qs.values_list('id', flat=True))

    usages_mois_qs = UtilisationCarburantVehicule.objects.filter(
        vehicule_id__in=vehicule_ids_list,
        date_utilisation__gte=month_start,
        date_utilisation__lte=month_end,
    ).filter(
        Q(employe__base_id__in=base_ids)
        | Q(magasin__base_id__in=base_ids)
        | Q(purchase_item__purchase__magasin__base_id__in=base_ids)
        | Q(purchase_item__purchase__base_id__in=base_ids)
        | Q(vehicule_id__in=active_affectations)
    )

    usage_by_vehicle = defaultdict(lambda: {
        'achat_litres': Decimal('0'),
        'achat_montant': Decimal('0'),
        'stock_litres': Decimal('0'),
        'stock_montant': Decimal('0'),
    })
    for usage in usages_mois_qs:
        vid = usage.vehicule_id
        quantite = Decimal(str(usage.quantite or 0))
        montant = Decimal(str(usage.montant or 0))
        if usage.source_type == 'stock':
            usage_by_vehicle[vid]['stock_litres'] += quantite
            usage_by_vehicle[vid]['stock_montant'] += montant
        else:
            usage_by_vehicle[vid]['achat_litres'] += quantite
            usage_by_vehicle[vid]['achat_montant'] += montant

    releves_up_to_end = RelevéCompteur.objects.filter(
        vehicule_id__in=vehicule_ids_list,
        date_releve__lte=month_end,
    ).order_by('vehicule_id', 'date_releve', 'created_at')
    releves_by_vehicle = defaultdict(list)
    for rel in releves_up_to_end:
        releves_by_vehicle[rel.vehicule_id].append(rel)

    distance_mois_map = {
        item['vehicule_id']: Decimal(str(item['total'] or 0))
        for item in RelevéCompteur.objects.filter(
            vehicule_id__in=vehicule_ids_list,
            date_releve__gte=month_start,
            date_releve__lte=month_end,
        ).values('vehicule_id').annotate(total=Sum('distance_parcourue'))
    }

    def _last_index(records, limit_date):
        for rel in reversed(records):
            if rel.date_releve and rel.date_releve <= limit_date and rel.index_compteur is not None:
                try:
                    return Decimal(str(rel.index_compteur))
                except Exception:
                    return None
        return None

    compta_entries_qs = BaseDiameX.objects.filter(
        date_rec__gte=month_start,
        date_rec__lte=month_end,
        compte_code__in=['606100', '606107'],
    )
    if selected_base and getattr(selected_base, 'volet', None):
        compta_entries_qs = compta_entries_qs.filter(
            Q(activ__iexact=selected_base.volet) | Q(prog__iexact=selected_base.volet)
        )
    compta_fuel_map = _build_fuel_compta_map(compta_entries_qs, vehicules_qs)
    compta_by_vehicle = compta_fuel_map['direct_by_vehicle']
    compta_stock_litres = sum((row['litres'] for row in compta_fuel_map['stock_entries']), Decimal('0'))
    compta_stock_montant = sum((row['montant'] for row in compta_fuel_map['stock_entries']), Decimal('0'))

    remarques_map = {}
    if selected_base:
        remarques_map = {
            row.vehicule_id: (row.remarque or '')
            for row in RapportConsommationCarburantRemarque.objects.filter(
                base=selected_base,
                annee=annee,
                mois=mois,
                vehicule_id__in=vehicule_ids_list,
            )
        }

    recap_data = []
    for vehicule in vehicules_qs:
        records = releves_by_vehicle.get(vehicule.id, [])
        index_prev = _last_index(records, prev_month_end)
        index_curr = _last_index(records, month_end)
        if index_prev is not None and index_curr is not None and index_curr >= index_prev:
            distance = index_curr - index_prev
        else:
            distance = distance_mois_map.get(vehicule.id, Decimal('0'))
        if distance < 0:
            distance = Decimal('0')

        usage_data = usage_by_vehicle.get(vehicule.id, {})
        achat_litres_usage = usage_data.get('achat_litres', Decimal('0'))
        stock_litres = usage_data.get('stock_litres', Decimal('0'))
        achat_montant_usage = usage_data.get('achat_montant', Decimal('0'))
        stock_montant = usage_data.get('stock_montant', Decimal('0'))

        compta_data = compta_by_vehicle.get(vehicule.id, {})
        achat_litres_compta = compta_data.get('litres', Decimal('0'))
        achat_montant_compta = compta_data.get('montant', Decimal('0'))

        achat_litres = achat_litres_usage if achat_litres_usage > 0 else achat_litres_compta
        achat_montant = achat_montant_usage if achat_montant_usage > 0 else achat_montant_compta

        total_litres = achat_litres + stock_litres
        total_montant = achat_montant + stock_montant
        conso_100km = (total_litres / distance * Decimal('100')) if distance > 0 else Decimal('0')
        analyse_level, analyse_message = _analyse_consommation(
            vehicule.type_vehicule,
            total_litres,
            distance,
        )

        affectation = latest_affectation_by_vehicle.get(vehicule.id)
        employe = affectation.employe if affectation else None
        base_label = selected_base.nom_base if selected_base else (
            employe.base.nom_base if employe and employe.base else 'Non affecte'
        )

        recap_data.append({
            'vehicule': vehicule,
            'employe': employe,
            'base_nom': base_label,
            'index_prev': index_prev,
            'index_curr': index_curr,
            'distance': distance,
            'achat_litres': achat_litres,
            'stock_litres': stock_litres,
            'carburant_litres': total_litres,
            'carburant_montant': total_montant,
            'consommation_100km': conso_100km,
            'analyse_level': analyse_level,
            'analyse_message': analyse_message,
            'remark': remarques_map.get(vehicule.id, ''),
            'compta_fallback_used': achat_litres_usage <= 0 and achat_litres_compta > 0,
        })

    recap_data.sort(key=lambda row: row['vehicule'].immatriculation or '')

    total_distance = sum((row['distance'] for row in recap_data), Decimal('0'))
    total_achats = sum((row['achat_litres'] for row in recap_data), Decimal('0'))
    total_stock = sum((row['stock_litres'] for row in recap_data), Decimal('0'))
    total_carburant = sum((row['carburant_litres'] for row in recap_data), Decimal('0'))
    total_montant = sum((row['carburant_montant'] for row in recap_data), Decimal('0'))
    anomalies = [row for row in recap_data if row['analyse_level'] in ('warning', 'critical')]

    scan_current = None
    scans_year = RapportConsommationCarburantScan.objects.none()
    if selected_base:
        scan_current = RapportConsommationCarburantScan.objects.filter(
            base=selected_base,
            annee=annee,
            mois=mois,
        ).first()
        scans_year = RapportConsommationCarburantScan.objects.filter(
            base=selected_base,
            annee=annee,
        ).order_by('-mois')

    years_available = {today.year, annee}
    years_available.update(RapportConsommationCarburantScan.objects.values_list('annee', flat=True))
    years_available.update(
        RelevéCompteur.objects.filter(vehicule_id__in=vehicule_ids_list).values_list('date_releve__year', flat=True)
    )
    years_available.update(
        UtilisationCarburantVehicule.objects.filter(
            vehicule_id__in=vehicule_ids_list
        ).values_list('date_utilisation__year', flat=True)
    )
    years_available = sorted([y for y in years_available if y], reverse=True)

    context = {
        'mois': mois,
        'annee': annee,
        'month_choices': MONTH_CHOICES,
        'years_available': years_available or [today.year],
        'mois_nom': datetime(annee, mois, 1).strftime('%B %Y'),
        'bases': scoped_bases,
        'selected_base': selected_base,
        'selected_base_id': selected_base_id,
        'recap_data': recap_data,
        'total_distance': total_distance,
        'total_achats': total_achats,
        'total_stock': total_stock,
        'total_carburant': total_carburant,
        'total_montant': total_montant,
        'anomalies': anomalies,
        'scan_current': scan_current,
        'scans_year': scans_year,
        'cloture_mois': cloture_mois,
        'unlinked_count': unlinked_count,
        'blocked_message': blocked_message,
        'can_cloturer': _is_directeur_user(request.user),
        'compta_stock_litres': compta_stock_litres,
        'compta_stock_montant': compta_stock_montant,
        'compta_stock_entries_count': len(compta_fuel_map['stock_entries']),
    }
    return render(request, 'inventory/vehicules/recap_mensuel.html', context)


@login_required
def vehicules_carburant_extraction_controle(request):
    """Controle extraction carburant depuis les lignes comptables 606100 et 606107."""
    today = timezone.localdate()
    mois = _parse_int(request.GET.get('mois'), today.month)
    annee = _parse_int(request.GET.get('annee'), today.year)
    if mois < 1 or mois > 12:
        mois = today.month
    if annee < 2000 or annee > 2100:
        annee = today.year

    scoped_bases = _filter_bases_by_scope(Base.objects.all(), request.user)
    user_org_id = getattr(getattr(getattr(request.user, 'employe', None), 'base', None), 'organisation_id', None)
    if user_org_id:
        scoped_bases = scoped_bases.filter(organisation_id=user_org_id)
    scoped_bases = scoped_bases.order_by('nom_base')

    selected_base_id = (request.GET.get('base') or '').strip()
    if selected_base_id and not scoped_bases.filter(id=selected_base_id).exists():
        selected_base_id = ''
    selected_base = scoped_bases.filter(id=selected_base_id).first() if selected_base_id else scoped_bases.first()
    selected_base_id = str(selected_base.id) if selected_base else ''

    month_start, month_end, _prev_month_end = _month_bounds(annee, mois)

    def _build_redirect_url(base_id, year_value, month_value):
        redirect_url = reverse('inventory:vehicules_carburant_extraction_controle')
        params = [f"annee={year_value}", f"mois={month_value}"]
        if base_id:
            params.append(f"base={base_id}")
        return f"{redirect_url}?{'&'.join(params)}"

    def _entries_queryset(base_obj):
        qs = BaseDiameX.objects.filter(
            date_rec__gte=month_start,
            date_rec__lte=month_end,
            compte_code__in=['606100', '606107'],
        )
        if base_obj and getattr(base_obj, 'volet', None):
            qs = qs.filter(
                Q(activ__iexact=base_obj.volet) | Q(prog__iexact=base_obj.volet)
            )
        return qs

    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        post_annee = _parse_int(request.POST.get('annee'), annee)
        post_mois = _parse_int(request.POST.get('mois'), mois)
        post_base_id = (request.POST.get('base') or selected_base_id or '').strip()
        if post_base_id and not scoped_bases.filter(id=post_base_id).exists():
            post_base_id = selected_base_id
        post_base = scoped_bases.filter(id=post_base_id).first() if post_base_id else None

        if action == 'update_entry':
            entry_id = _parse_int(request.POST.get('entry_id'), None)
            new_libelle = (request.POST.get('description') or '').strip()
            new_detail = (request.POST.get('detail') or '').strip()
            if not entry_id:
                messages.error(request, "Ligne comptable invalide.")
            else:
                entry_qs = _entries_queryset(post_base)
                entry = entry_qs.filter(id=entry_id).first()
                if not entry:
                    messages.error(request, "Ligne comptable non autorisee.")
                else:
                    entry.description = new_libelle
                    entry.detail = new_detail
                    entry.save(update_fields=['description', 'detail'])
                    messages.success(request, f"Ligne {entry_id} mise a jour.")
        else:
            messages.error(request, "Action non reconnue.")

        return redirect(_build_redirect_url(post_base_id, post_annee, post_mois))

    scoped_vehicules = _scoped_vehicules_qs(request.user).order_by('immatriculation')
    plate_by_vehicle = {veh.id: _normalize_plate(veh.immatriculation) for veh in scoped_vehicules}
    sorted_plate_items = sorted(
        [(veh_id, plate) for veh_id, plate in plate_by_vehicle.items() if plate],
        key=lambda item: len(item[1]),
        reverse=True,
    )
    vehicle_by_id = {veh.id: veh for veh in scoped_vehicules}

    entries = _entries_queryset(selected_base).order_by('-date_rec', '-id')[:500]
    rows = []
    for entry in entries:
        detail_text = str(entry.detail or '')
        normalized_detail = _normalize_plate(detail_text)
        matched_vehicle = None
        for veh_id, plate in sorted_plate_items:
            if plate and plate in normalized_detail:
                matched_vehicle = vehicle_by_id.get(veh_id)
                break

        liters, ok, reason = _extract_liters_from_structured_libelle(entry.description)
        source = 'description'
        if not ok:
            liters, ok, reason = _extract_liters_from_structured_libelle(entry.info)
            source = 'info'

        rows.append({
            'entry': entry,
            'matched_vehicle': matched_vehicle,
            'liters': liters,
            'extracted_ok': ok,
            'extract_reason': reason,
            'extract_source': source,
        })

    total_rows = len(rows)
    matched_rows = sum(1 for row in rows if row['matched_vehicle'] is not None)
    extracted_rows = sum(1 for row in rows if row['extracted_ok'])
    unresolved_rows = sum(1 for row in rows if (row['matched_vehicle'] is None) or (not row['extracted_ok']))

    years_available = {today.year, annee}
    years_available.update(BaseDiameX.objects.values_list('date_rec__year', flat=True))
    years_available = sorted([y for y in years_available if y], reverse=True)

    context = {
        'rows': rows,
        'total_rows': total_rows,
        'matched_rows': matched_rows,
        'extracted_rows': extracted_rows,
        'unresolved_rows': unresolved_rows,
        'bases': scoped_bases,
        'selected_base': selected_base,
        'selected_base_id': selected_base_id,
        'month_choices': MONTH_CHOICES,
        'mois': mois,
        'annee': annee,
        'years_available': years_available,
    }
    return render(request, 'inventory/vehicules/carburant_extraction_controle.html', context)


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_carburant_pointer_compta(request, usage_id):
    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        data = {}

    entry_id = data.get('entry_id')
    if not entry_id:
        return JsonResponse({'success': False, 'error': 'entry_id requis'}, status=400)

    usage = get_object_or_404(
        UtilisationCarburantVehicule.objects.select_related('vehicule', 'employe', 'magasin', 'purchase_item__purchase'),
        id=usage_id,
        source_type='achat',
    )

    if usage.vehicule_id and not _scoped_vehicules_qs(request.user).filter(id=usage.vehicule_id).exists():
        return JsonResponse({'success': False, 'error': 'Usage hors perimetre'}, status=403)

    candidate_qs = BaseDiameX.objects.filter(id=entry_id, compte_code__in=['606100', '606107'])
    candidates = _build_usage_compta_candidates(usage, candidate_qs, vehicule=usage.vehicule, limit=1)
    if not candidates:
        return JsonResponse({'success': False, 'error': 'Ligne comptable non autorisee pour ce pointage'}, status=400)

    entry = candidate_qs.first()
    if entry.utilisations_carburant_vehicules.exclude(id=usage.id).exists():
        return JsonResponse({'success': False, 'error': 'Cette ligne comptable est deja pointee sur un autre usage'}, status=400)

    usage.base_diamex_entry = entry
    if usage.notes:
        usage.notes = usage.notes.replace("Achat carburant non relié à la compta", "").strip(" |-\n")
    if not usage.notes or 'Pointage compta' not in usage.notes:
        extra_note = f"Pointage compta ID {entry.id}"
        usage.notes = f"{usage.notes} | {extra_note}" if usage.notes else extra_note
        usage.notes = usage.notes.strip(' |')
    usage.save(update_fields=['base_diamex_entry', 'notes'])
    return JsonResponse({'success': True, 'message': 'Pointage comptable enregistre'})


@csrf_exempt
@require_http_methods(["POST"])
@login_required
def api_cloturer_carburant_mois(request):
    if not _is_directeur_user(request.user):
        return JsonResponse({'success': False, 'error': 'Acces refuse'}, status=403)

    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        data = {}

    mois = int(data.get('mois', 0))
    annee = int(data.get('annee', 0))
    override = bool(data.get('override'))
    commentaire = data.get('commentaire', '') or ''

    if not mois or not annee:
        return JsonResponse({'success': False, 'error': 'Mois et annee requis'}, status=400)

    if ClotureCarburantMois.objects.filter(mois=mois, annee=annee).exists():
        return JsonResponse({'success': False, 'error': 'Mois deja cloture'}, status=400)

    unlinked_count = UtilisationCarburantVehicule.objects.filter(
        source_type='achat',
        base_diamex_entry__isnull=True,
        date_utilisation__year=annee,
        date_utilisation__month=mois
    ).count()

    if unlinked_count > 0 and not override:
        return JsonResponse(
            {'success': False, 'error': 'Achats non relies', 'unlinked_count': unlinked_count},
            status=400
        )

    ClotureCarburantMois.objects.create(
        mois=mois,
        annee=annee,
        override_directeur=override,
        commentaire=commentaire,
        cloture_par=request.user
    )

    return JsonResponse({'success': True, 'unlinked_count': unlinked_count, 'override': override})





@login_required

@csrf_exempt

@require_http_methods(["POST"])

def api_utilisation_piece_create(request):

    """API pour enregistrer l'utilisation de pieces et impacter le stock"""

    try:

        data = json.loads(request.body)



        vehicule_id = data.get('vehicule_id')

        designation_id = data.get('designation_id')

        magasin_id = data.get('magasin_id')

        purchase_item_id = data.get('purchase_item_id')

        quantite = Decimal(str(data.get('quantite', '0') or '0'))

        date_utilisation = datetime.strptime(data.get('date_utilisation'), '%Y-%m-%d').date() if data.get('date_utilisation') else None



        if not vehicule_id or not designation_id or not date_utilisation or not purchase_item_id:

            return JsonResponse({'success': False, 'error': 'Vhicule, pice, achat et date sont obligatoires'}, status=400)

        if quantite <= 0:

            return JsonResponse({'success': False, 'error': 'Quantit invalide'}, status=400)



        vehicule = get_object_or_404(_scoped_vehicules_qs(request.user), id=vehicule_id)

        designation = get_object_or_404(Designation, id=designation_id, type_designation__nom="Pice vhicule")

        magasin = get_object_or_404(_scoped_magasins_qs(request.user), id=magasin_id) if magasin_id else None

        purchase_item = get_object_or_404(_scoped_purchase_items_qs(request.user), id=purchase_item_id)

        if purchase_item.designation_id != designation.id:

            return JsonResponse({'success': False, 'error': 'Achat invalide pour cette pice'}, status=400)

        employe = get_object_or_404(_scoped_employes_qs(request.user), id=data.get('employe_id')) if data.get('employe_id') else None



        stock = None

        if magasin and magasin.base_id:

            stock = Stock.objects.filter(base=magasin.base, designation=designation).first()

        if stock is None:

            stock = Stock.objects.filter(designation=designation).first()

        if stock is None:

            return JsonResponse({'success': False, 'error': 'Stock introuvable pour cette pice'}, status=400)

        if quantite > stock.current_quantity:

            return JsonResponse({'success': False, 'error': 'Quantit insuffisante en stock'}, status=400)



        with transaction.atomic():

            stock.current_quantity = stock.current_quantity - quantite

            stock.save()



            StockMovement.objects.create(

                designation=designation,

                base=stock.base,

                movement_type='sortie',

                quantity=quantite,

                movement_date=datetime.now(),

                reference=f"Utilisation pices vhicule {vehicule.immatriculation}",

                notes=data.get('motif') or 'Utilisation pices vhicule',

                employee=employe

            )



            utilisation = UtilisationPieceVehicule.objects.create(

                vehicule=vehicule,

                designation=designation,

                purchase_item=purchase_item,

                magasin=magasin,

                employe=employe,

                quantite=quantite,

                date_utilisation=date_utilisation,

                motif=data.get('motif', ''),

                notes=data.get('notes', ''),

                created_by=request.user if request.user.is_authenticated else None

            )



        return JsonResponse({'success': True, 'message': 'Utilisation enregistre', 'utilisation_id': str(utilisation.id)})



    except Exception as e:

        return JsonResponse({'success': False, 'error': str(e)}, status=500)





def _create_carburant_usage(data, vehicule, employe, date_utilisation, is_personnel, releve=None, created_by=None):

    source = data.get('carburant_source_type')

    quantite = data.get('carburant_quantite')

    montant = data.get('carburant_montant')

    if not source or not quantite:

        return None

    qte = Decimal(str(quantite))

    if qte <= 0:

        raise ValueError('Quantite carburant invalide')



    if source == 'achat':

        purchase_item_id = data.get('carburant_purchase_item_id')
        purchase_item = None
        notes = data.get('carburant_notes', '') or ''

        if purchase_item_id:
            purchase_item = get_object_or_404(_scoped_purchase_items_qs(created_by), id=purchase_item_id)
        else:
            notes = notes or "Achat carburant non relié à la compta"

        return UtilisationCarburantVehicule.objects.create(

            vehicule=vehicule,

            employe=employe,

            date_utilisation=date_utilisation,

            quantite=qte,

            montant=Decimal(str(montant)) if montant else None,

            source_type='achat',

            purchase_item=purchase_item,

            releve=releve,

            is_personnel=is_personnel,

            notes=notes,

            created_by=created_by

        )



    if source == 'stock':

        magasin_id = data.get('carburant_magasin_id')

        designation_id = data.get('carburant_designation_id')

        if not magasin_id or not designation_id:

            raise ValueError('Magasin et designation requis')

        magasin_qs = _scoped_magasins_qs(created_by) if created_by and getattr(created_by, 'is_authenticated', False) else Magasin.objects.all()
        magasin = get_object_or_404(magasin_qs, id=magasin_id)

        designation = get_object_or_404(Designation, id=designation_id)

        stock = Stock.objects.filter(base=magasin.base, designation=designation).first()

        if stock is None:

            raise ValueError('Stock carburant introuvable')

        if qte > stock.current_quantity:

            raise ValueError('Quantite insuffisante en stock')

        stock.current_quantity = stock.current_quantity - qte

        stock.save()

        movement = StockMovement.objects.create(

            designation=designation,

            base=stock.base,

            movement_type='sortie',

            quantity=qte,

            movement_date=datetime.now(),

            reference=f"Carburant usage {vehicule.immatriculation}",

            notes='Carburant utilise',

            employee=employe

        )

        return UtilisationCarburantVehicule.objects.create(

            vehicule=vehicule,

            employe=employe,

            date_utilisation=date_utilisation,

            quantite=qte,

            montant=Decimal(str(montant)) if montant else None,

            source_type='stock',

            stock_movement=movement,

            magasin=magasin,

            releve=releve,

            is_personnel=is_personnel,

            created_by=created_by

        )

    return None





@login_required

@csrf_exempt

@require_http_methods(["POST"])

def api_utilisation_perso_create(request):

    try:

        data = json.loads(request.body)

        vehicule_id = data.get('vehicule_id')

        if not vehicule_id:

            return JsonResponse({'success': False, 'error': 'Vhicule requis'}, status=400)

        vehicule = get_object_or_404(_scoped_vehicules_qs(request.user), id=vehicule_id)

        employe = getattr(request.user, 'employe', None)

        if data.get('employe_id') and (request.user.is_staff or request.user.is_superuser):

            employe = get_object_or_404(_scoped_employes_qs(request.user), id=data.get('employe_id'))

        if not employe:

            return JsonResponse({'success': False, 'error': 'Employ requis'}, status=400)



        # Vrifier affectation active si non admin

        if not (request.user.is_staff or request.user.is_superuser):

            has_affect = AffectationVehicule.objects.filter(

                vehicule=vehicule,

                employe=employe,

                date_fin__isnull=True

            ).exists()

            if not has_affect:

                return JsonResponse({'success': False, 'error': 'Vous n\'tes pas affect  ce vhicule'}, status=403)



        date_debut = datetime.strptime(data['date_debut'], '%Y-%m-%d').date()

        date_fin = datetime.strptime(data['date_fin'], '%Y-%m-%d').date()

        if date_fin < date_debut:

            return JsonResponse({'success': False, 'error': 'Date fin invalide'}, status=400)

        if not data.get('regles_acceptees'):

            return JsonResponse({'success': False, 'error': 'Rgles d\'utilisation  accepter'}, status=400)



        usage = UtilisationPersoVehicule.objects.create(

            vehicule=vehicule,

            employe=employe,

            date_debut=date_debut,

            date_fin=date_fin,

            motif=data.get('motif', ''),

            statut='demande',

            regles_acceptees=bool(data.get('regles_acceptees')),

            casque_obligatoire=bool(data.get('casque_obligatoire')),

            created_by=request.user if request.user.is_authenticated else None

        )

        return JsonResponse({'success': True, 'message': 'Demande enregistre', 'id': str(usage.id)})

    except Exception as e:

        return JsonResponse({'success': False, 'error': str(e)}, status=500)





@login_required

@csrf_exempt

@require_http_methods(["POST"])

def api_utilisation_perso_decision(request, usage_id):

    try:

        data = json.loads(request.body)

        usage = get_object_or_404(_scoped_usages_perso_qs(request.user), id=usage_id)

        if not (_is_directeur_user(request.user) or request.user.is_superuser or request.user.is_staff):

            return JsonResponse({'success': False, 'error': 'Accs refus'}, status=403)

        if usage.statut != 'demande':

            return JsonResponse({'success': False, 'error': 'Demande dj traite'}, status=400)

        avis = data.get('avis')

        if avis is None:

            return JsonResponse({'success': False, 'error': 'Avis requis'}, status=400)

        usage.directeur = getattr(request.user, 'employe', None)

        usage.directeur_avis = True if avis in [True, 'true', '1', 1, 'oui', 'OUI'] else False

        usage.directeur_commentaire = data.get('commentaire', '')

        usage.date_avis_directeur = timezone.now()

        usage.statut = 'approuvee' if usage.directeur_avis else 'refusee'

        usage.save()

        return JsonResponse({'success': True, 'message': 'Avis enregistr'})

    except Exception as e:

        return JsonResponse({'success': False, 'error': str(e)}, status=500)





@login_required

@csrf_exempt

@require_http_methods(["POST"])

def api_utilisation_perso_carburant_avant(request, usage_id):

    try:

        data = json.loads(request.body)

        usage = get_object_or_404(_scoped_usages_perso_qs(request.user), id=usage_id)

        employe = getattr(request.user, 'employe', None)

        if not employe or usage.employe_id != employe.id:

            return JsonResponse({'success': False, 'error': 'Accs refus'}, status=403)

        if usage.statut != 'approuvee' or usage.directeur_avis is not True:

            return JsonResponse({'success': False, 'error': 'Demande non approuve'}, status=400)



        carburant = _create_carburant_usage(

            data=data,

            vehicule=usage.vehicule,

            employe=employe,

            date_utilisation=usage.date_debut,

            is_personnel=False,

            created_by=request.user if request.user.is_authenticated else None

        )

        if not carburant:

            return JsonResponse({'success': False, 'error': 'Carburant requis'}, status=400)

        usage.carburant_avant = carburant

        usage.statut = 'en_cours'

        usage.save()

        return JsonResponse({'success': True, 'message': 'Carburant avant enregistr'})

    except Exception as e:

        return JsonResponse({'success': False, 'error': str(e)}, status=500)





@login_required

@csrf_exempt

@require_http_methods(["POST"])

def api_utilisation_perso_retour(request, usage_id):

    try:

        data = json.loads(request.body)

        usage = get_object_or_404(_scoped_usages_perso_qs(request.user), id=usage_id)

        employe = getattr(request.user, 'employe', None)

        if not employe or usage.employe_id != employe.id:

            return JsonResponse({'success': False, 'error': 'Accs refus'}, status=403)

        if usage.statut != 'en_cours':

            return JsonResponse({'success': False, 'error': 'Retour non autoris'}, status=400)



        carburant = _create_carburant_usage(

            data=data,

            vehicule=usage.vehicule,

            employe=employe,

            date_utilisation=usage.date_fin,

            is_personnel=True,

            created_by=request.user if request.user.is_authenticated else None

        )

        if not carburant:

            return JsonResponse({'success': False, 'error': 'Carburant requis'}, status=400)

        usage.carburant_apres = carburant

        usage.statut = 'retour_soumis'

        usage.save()

        return JsonResponse({'success': True, 'message': 'Retour soumis'})

    except Exception as e:

        return JsonResponse({'success': False, 'error': str(e)}, status=500)





@login_required

@csrf_exempt

@require_http_methods(["POST"])

def api_utilisation_perso_valider_retour(request, usage_id):

    try:

        usage = get_object_or_404(_scoped_usages_perso_qs(request.user), id=usage_id)

        if not (_is_chef_user(request.user) or request.user.is_superuser or request.user.is_staff):

            return JsonResponse({'success': False, 'error': 'Accs refus'}, status=403)

        if usage.statut != 'retour_soumis':

            return JsonResponse({'success': False, 'error': 'Retour non soumis'}, status=400)

        usage.chef = getattr(request.user, 'employe', None)

        usage.chef_commentaire = (json.loads(request.body).get('commentaire', '') if request.body else '')

        usage.date_validation_chef = timezone.now()

        usage.statut = 'retour_valide'

        usage.save()

        return JsonResponse({'success': True, 'message': 'Retour valid'})

    except Exception as e:

        return JsonResponse({'success': False, 'error': str(e)}, status=500)





@login_required

def utilisation_perso_pdf(request, usage_id):

    usage = get_object_or_404(_scoped_usages_perso_qs(request.user), id=usage_id)

    from reportlab.lib.pagesizes import A4

    from reportlab.lib.styles import getSampleStyleSheet

    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    from reportlab.lib import colors

    from django.http import HttpResponse



    response = HttpResponse(content_type='application/pdf')

    response['Content-Disposition'] = f'attachment; filename="utilisation_perso_{usage.id}.pdf"'



    doc = SimpleDocTemplate(response, pagesize=A4)

    styles = getSampleStyleSheet()

    elements = []



    elements.append(Paragraph("Demande d'utilisation personnelle de vhicule", styles['Title']))

    elements.append(Spacer(1, 12))



    data = [

        ['Vhicule', usage.vehicule.nom_complet],

        ['Employ', usage.employe.nom_complet],

        ['Priode', f"{usage.date_debut}  {usage.date_fin}"],

        ['Motif', usage.motif or '-'],

        ['Statut', usage.statut],

    ]

    table = Table(data, colWidths=[120, 380])

    table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey)]))

    elements.append(table)

    elements.append(Spacer(1, 12))



    rules = (

        "Rgles: Avant utilisation perso, replein  la charge de l'organisation. "

        "Aprs utilisation, replein  la charge de l'utilisateur. "

        "Casque obligatoire pour conducteur et passagers (moto). "

        "Le directeur peut donner un avis favorable ou non. Le retour est valid par le chef."

    )

    elements.append(Paragraph(rules, styles['BodyText']))

    elements.append(Spacer(1, 18))

    elements.append(Paragraph("Signature employ:", styles['BodyText']))

    elements.append(Spacer(1, 36))

    elements.append(Paragraph("Signature directeur:", styles['BodyText']))

    elements.append(Spacer(1, 36))

    elements.append(Paragraph("Signature chef:", styles['BodyText']))



    doc.build(elements)

    return response





@login_required

def pieces_utilisation_analytics(request):

    """Analyse des utilisations de pices par vhicule et global organisation"""

    utilisations = UtilisationPieceVehicule.objects.select_related(

        'vehicule', 'designation', 'magasin', 'purchase_item__purchase'

    )



    date_debut = request.GET.get('date_debut')

    date_fin = request.GET.get('date_fin')

    magasin_id = request.GET.get('magasin_id')

    base_id = request.GET.get('base_id')

    vehicule_id = request.GET.get('vehicule_id')



    if date_debut:

        utilisations = utilisations.filter(date_utilisation__gte=date_debut)

    if date_fin:

        utilisations = utilisations.filter(date_utilisation__lte=date_fin)

    if magasin_id:

        utilisations = utilisations.filter(magasin_id=magasin_id)

    if base_id:

        utilisations = utilisations.filter(magasin__base_id=base_id)

    if vehicule_id:

        utilisations = utilisations.filter(vehicule_id=vehicule_id)



    total_quantite = utilisations.aggregate(total=Sum('quantite'))['total'] or Decimal('0')



    par_vehicule = utilisations.values(

        'vehicule__id',

        'vehicule__immatriculation',

        'vehicule__marque',

        'vehicule__modele'

    ).annotate(total=Sum('quantite')).order_by('-total')



    par_piece = utilisations.values(

        'designation__id',

        'designation__nom',

        'designation__unite'

    ).annotate(total=Sum('quantite')).order_by('-total')



    par_vehicule_mois = utilisations.annotate(mois=TruncMonth('date_utilisation')).values(

        'mois',

        'vehicule__immatriculation',

        'vehicule__marque',

        'vehicule__modele'

    ).annotate(total=Sum('quantite')).order_by('-mois', 'vehicule__immatriculation')



    # Dtail par vhicule et pice

    details = utilisations.values(

        'vehicule__immatriculation',

        'vehicule__marque',

        'vehicule__modele',

        'designation__nom',

        'designation__unite'

    ).annotate(total=Sum('quantite')).order_by('vehicule__immatriculation', '-total')



    bases = Base.objects.all().order_by('nom_base')

    vehicules = Vehicule.objects.all().order_by('immatriculation')



    context = {

        'total_quantite': total_quantite,

        'par_vehicule': par_vehicule,

        'par_piece': par_piece,

        'par_vehicule_mois': par_vehicule_mois,

        'details': details,

        'bases': bases,

        'magasins': magasins,

        'vehicules': vehicules,

        'filters': {

            'date_debut': date_debut or '',

            'date_fin': date_fin or '',

            'magasin_id': magasin_id or '',

            'base_id': base_id or '',

            'vehicule_id': vehicule_id or '',

        }

    }



    return render(request, 'inventory/vehicules/pieces_analyses.html', context)
