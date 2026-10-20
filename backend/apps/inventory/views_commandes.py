"""Views for command quantity calculation workflow."""
from collections import defaultdict
from decimal import Decimal
from datetime import timedelta
import json
import uuid
from io import BytesIO

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from apps.planning.models import Designation

from apps.inventory.models import FicheStock, PurchaseItem, Stock
from apps.inventory.models_demande_devis import DemandeDevis, DemandeDevisItem
from apps.organization.models import Base, Magasin
from apps.planning.models import BonLivraison, Designation, Planning

from .views import (
    _filter_bases_by_scope,
    _filter_plannings_by_scope_inventory,
    _resolve_base_from_magasin_text,
)


CALCUL_MODE_LABELS = {
    "auto": "Auto: priorite bons, secours historique",
    "bons_livraison": "Bons de livraison uniquement",
    "historique_stock_achats": "Historique stock + achats uniquement",
}


def _connected_organisation_id(user):
    employe = getattr(user, "employe", None)
    return getattr(getattr(employe, "base", None), "organisation_id", None)


def _normalize_calcul_mode(value):
    if value in CALCUL_MODE_LABELS:
        return value
    return "auto"


def _resolve_quantite_retenue(mode_calcul, quantite_bons, quantite_historique):
    if mode_calcul == "bons_livraison":
        return quantite_bons, "bons_livraison"
    if mode_calcul == "historique_stock_achats":
        return quantite_historique, "historique_stock_achats"
    if quantite_bons > 0:
        return quantite_bons, "bons_livraison"
    return quantite_historique, "historique_stock_achats"


def _filter_bases_for_commandes(queryset, user):
    """
    Restriction demandee pour le workflow commandes:
    limiter la liste des bases a l'organisation de l'utilisateur connecte.
    """
    scoped = _filter_bases_by_scope(queryset, user)
    organisation_id = _connected_organisation_id(user)
    if organisation_id:
        return scoped.filter(organisation_id=organisation_id)
    return scoped


def _is_bon_from_base_magasins(bon, base, magasin_ids, magasin_names):
    """Vrai si le BonLivraison est associe a un magasin de la base selectionnee."""
    magasin_label = (getattr(bon, "magasin", None) or "").strip()
    if not magasin_label:
        return False

    try:
        parsed_uuid = str(uuid.UUID(magasin_label))
        if parsed_uuid in magasin_ids or parsed_uuid == str(base.id):
            return True
    except (ValueError, TypeError, AttributeError):
        pass

    normalized_label = magasin_label.lower()
    if normalized_label in magasin_names:
        return True

    base_name = (getattr(base, "nom_base", "") or "").strip().lower()
    if base_name and normalized_label == base_name:
        return True

    resolved_base = _resolve_base_from_magasin_text(magasin_label)
    return bool(resolved_base and str(resolved_base.id) == str(base.id))


def _local_date(value):
    if value is None:
        return None
    if hasattr(value, "tzinfo"):
        if timezone.is_aware(value):
            return timezone.localtime(value).date()
        return value.date()
    return value


def _pick_inventory_snapshot(snapshot_rows, target_date, max_gap_days):
    if not snapshot_rows:
        return None

    sorted_rows = sorted(
        snapshot_rows,
        key=lambda row: (
            abs((row["date"] - target_date).days),
            0 if row["date"] <= target_date else 1,
            -row["date"].toordinal(),
        ),
    )
    best = sorted_rows[0]
    if abs((best["date"] - target_date).days) > max_gap_days:
        return None
    return best


def _build_historical_estimates(base, nb_jours, stocks_base_by_id):
    """
    Estime les sorties terrain à partir d'un stock précédent, des achats reçus,
    et du stock courant:
        stock_precedent + achats - stock_dernier
    """
    end_date = timezone.localdate()
    target_start_date = end_date - timedelta(days=nb_jours)
    max_gap_days = max(30, nb_jours // 2)

    inventory_totals = defaultdict(lambda: defaultdict(Decimal))
    inventory_names = {}
    inventaires_qs = (
        FicheStock.objects.filter(
            base=base,
            operation_type="inventaire",
            designation__isnull=False,
            designation__concerne_livraison=True,
        )
        .select_related("designation")
        .only("designation_id", "designation__nom", "quantity", "operation_date")
        .order_by("designation_id", "operation_date")
    )
    for fiche in inventaires_qs:
        if not fiche.designation_id:
            continue
        designation_id = str(fiche.designation_id)
        inventory_names[designation_id] = (fiche.designation.nom if fiche.designation else "") or inventory_names.get(designation_id, "")
        inventory_date = _local_date(fiche.operation_date)
        if not inventory_date:
            continue
        inventory_totals[designation_id][inventory_date] += Decimal(str(fiche.quantity or 0))

    purchase_events = defaultdict(list)
    purchase_items_qs = (
        PurchaseItem.objects.filter(
            designation__isnull=False,
            designation__concerne_livraison=True,
            purchase__purchase_status__in=["livre", "recu"],
        )
        .filter(Q(purchase__magasin__base_id=base.id) | Q(purchase__base_id=base.id))
        .select_related("designation", "purchase")
        .only(
            "designation_id",
            "designation__nom",
            "quantity_ordered",
            "quantity_received",
            "purchase__purchase_date",
            "purchase__actual_delivery_date",
        )
    )
    for item in purchase_items_qs:
        if not item.designation_id:
            continue
        effective_date = item.purchase.actual_delivery_date or item.purchase.purchase_date
        if not effective_date:
            continue
        qty = item.quantity_received if item.quantity_received not in [None, 0] else item.quantity_ordered
        qty = Decimal(str(qty or 0))
        if qty <= 0:
            continue

        designation_id = str(item.designation_id)
        purchase_events[designation_id].append(
            {
                "date": effective_date,
                "quantity": qty,
            }
        )
        inventory_names.setdefault(designation_id, (item.designation.nom if item.designation else "") or "")

    estimates = {}
    designation_ids = set(inventory_totals.keys()) | set(purchase_events.keys()) | set(stocks_base_by_id.keys())
    for designation_id in designation_ids:
        snapshots = [
            {"date": snap_date, "quantity": qty}
            for snap_date, qty in inventory_totals.get(designation_id, {}).items()
        ]
        snapshot = _pick_inventory_snapshot(snapshots, target_start_date, max_gap_days)
        if not snapshot:
            continue

        achats_periode = sum(
            (
                event["quantity"]
                for event in purchase_events.get(designation_id, [])
                if snapshot["date"] <= event["date"] <= end_date
            ),
            Decimal("0"),
        )
        stock_current_info = stocks_base_by_id.get(designation_id, {})
        stock_dernier_physique = stock_current_info.get("stock_physique", Decimal("0"))
        quantite_estimee = snapshot["quantity"] + achats_periode - stock_dernier_physique

        estimates[designation_id] = {
            "designation_id": designation_id,
            "designation_nom": inventory_names.get(designation_id, ""),
            "stock_precedent": float(snapshot["quantity"]),
            "date_stock_precedent": snapshot["date"].strftime("%d/%m/%Y"),
            "achats_periode": float(achats_periode),
            "stock_dernier": float(stock_dernier_physique),
            "date_stock_dernier": end_date.strftime("%d/%m/%Y"),
            "quantite_estimee": float(max(quantite_estimee, Decimal("0"))),
            "ecart_jours_inventaire": abs((snapshot["date"] - target_start_date).days),
        }

    return estimates


def _load_catalog_designations():
    """Retourne les designations livraison actives pour saisie manuelle si besoin."""
    catalog = {}
    queryset = (
        Designation.objects.select_related('type_designation').filter(
            concerne_livraison=True,
            actif=True,
            nature_stock='consommable',
        )
        .only("id", "nom", "unite", "seuil_minimum", "type_designation__nom", "nature_stock")
        .order_by("type_designation__nom", "nom")
    )
    for designation in queryset:
        catalog[str(designation.id)] = {
            "designation_nom": designation.nom or "",
            "unite": designation.unite or "",
            "seuil_minimum": float(designation.seuil_minimum or 0),
            "designation_type_nom": designation.type_designation.nom if designation.type_designation else "Sans catégorie",
        }
    return catalog


@login_required
def calcul_commandes(request):
    """Command quantity calculation page."""
    bases = _filter_bases_for_commandes(Base.objects.all(), request.user).order_by("nom_base")

    context = {
        "bases": bases,
        "title": "Calcul des Commandes",
    }
    return render(request, "inventory/calcul_commandes.html", context)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def api_calculer_quantites(request):
    """Calculate quantities to order for one base."""
    try:
        data = json.loads(request.body or "{}")
        base_id = data.get("base_id")
        nb_jours = int(data.get("nb_jours", 30))
        mode_calcul = _normalize_calcul_mode(data.get("mode_calcul"))

        if not base_id:
            return JsonResponse({"success": False, "error": "Base requise"}, status=400)

        base = _filter_bases_for_commandes(Base.objects.all(), request.user).get(id=base_id)
        date_debut = timezone.now() - timedelta(days=nb_jours)

        plannings_scope = _filter_plannings_by_scope_inventory(
            Planning.objects.all(),
            request.user
        )

        magasins_base_qs = Magasin.objects.filter(base_id=base.id).only("id", "nom_magasin")
        magasin_ids = {str(magasin.id) for magasin in magasins_base_qs}
        magasin_names = {
            (magasin.nom_magasin or "").strip().lower()
            for magasin in magasins_base_qs
            if (magasin.nom_magasin or "").strip()
        }

        demandes_qs = BonLivraison.objects.filter(
            designation__concerne_livraison=True,
            planning_id__in=plannings_scope.values("id"),
        ).filter(
            Q(date_utilisation__gte=date_debut) |
            Q(date_utilisation__isnull=True, created_at__gte=date_debut)
        ).filter(
            Q(utilise=False) | Q(retour=False)
        ).select_related("designation")

        aggregated = defaultdict(lambda: {
            "designation_id": None,
            "designation_nom": "",
            "quantite_demandee": 0.0,
            "nb_lignes": 0,
        })
        total_bons_scanned = 0
        total_bons_matching = 0

        for bon in demandes_qs:
            total_bons_scanned += 1
            if not bon.designation_id:
                continue
            if not _is_bon_from_base_magasins(bon, base, magasin_ids, magasin_names):
                continue

            total_bons_matching += 1
            key = str(bon.designation_id)
            row = aggregated[key]
            row["designation_id"] = key
            row["designation_nom"] = (bon.designation.nom if bon.designation else row["designation_nom"]) or ""
            row["quantite_demandee"] += float(bon.quantite or 0)
            row["nb_lignes"] += 1

        demandes = sorted(
            aggregated.values(),
            key=lambda item: item["quantite_demandee"],
            reverse=True
        )

        stocks_base_by_id = {}
        stocks_base_by_name = {}
        stocks = Stock.objects.filter(base=base, designation__isnull=False).select_related("designation")
        for stock in stocks:
            if not stock.designation:
                continue
            designation_id = str(stock.designation.id)
            stock_payload = {
                "stock_actuel": float(stock.available_quantity),
                "stock_reserve": float(stock.reserved_quantity),
                "designation_id": designation_id,
                "designation_nom": (stock.designation.nom if stock.designation else "") or "",
                "stock_physique": Decimal(str(stock.current_quantity or 0)),
            }
            stocks_base_by_id[designation_id] = stock_payload
            designation_name_key = (stock.designation.nom or "").strip().lower()
            if designation_name_key:
                stocks_base_by_name[designation_name_key] = stock_payload

        historiques = _build_historical_estimates(base, nb_jours, stocks_base_by_id)
        catalog_designations = _load_catalog_designations()

        demandes_by_id = {
            str(demande["designation_id"]): demande
            for demande in demandes
            if demande.get("designation_id")
        }

        all_designation_ids = (
            set(demandes_by_id.keys())
            | set(historiques.keys())
            | set(stocks_base_by_id.keys())
            | set(catalog_designations.keys())
        )
        resultats = []
        total_articles_historique = 0
        total_articles_bons = 0
        total_articles_retenus = 0

        for designation_id in all_designation_ids:
            demande = demandes_by_id.get(designation_id, {})
            historique = historiques.get(designation_id, {})
            catalog_info = catalog_designations.get(designation_id, {})
            designation_nom = (
                demande.get("designation_nom")
                or historique.get("designation_nom")
                or catalog_info.get("designation_nom")
                or ""
            )
            quantite_bons = float(demande.get("quantite_demandee") or 0)
            quantite_historique = float(historique.get("quantite_estimee") or 0)
            quantite_max_compare = max(quantite_bons, quantite_historique)
            sans_mouvement = quantite_max_compare <= 0

            stock_info = stocks_base_by_id.get(designation_id) or stocks_base_by_name.get(
                (designation_nom or "").strip().lower(),
                {
                    "stock_actuel": 0,
                    "stock_reserve": 0,
                    "designation_id": None,
                    "designation_nom": "",
                    "stock_physique": Decimal("0"),
                },
            )
            if not designation_nom:
                designation_nom = stock_info.get("designation_nom") or designation_nom

            stock_actuel = stock_info["stock_actuel"]
            quantite_retenue, methode_calcul = _resolve_quantite_retenue(
                mode_calcul,
                quantite_bons,
                quantite_historique,
            )
            quantite_a_commander = max(0, quantite_retenue - stock_actuel)
            if sans_mouvement:
                methode_calcul = "catalogue_manuel"

            if quantite_bons > 0:
                total_articles_bons += 1
            if quantite_historique > 0:
                total_articles_historique += 1
            if quantite_retenue > 0:
                total_articles_retenus += 1

            resultats.append(
                {
                    "designation_id": designation_id,
                    "designation_nom": designation_nom,
                    "designation_type_nom": catalog_info.get("designation_type_nom") or "Sans catégorie",
                    "quantite_demandee": quantite_retenue,
                    "quantite_comparee": quantite_max_compare,
                    "quantite_demandee_bons": quantite_bons,
                    "quantite_estimee_historique": quantite_historique,
                    "stock_actuel": stock_actuel,
                    "stock_reserve": stock_info["stock_reserve"],
                    "quantite_a_commander": quantite_a_commander,
                    "nb_lignes": int(demande.get("nb_lignes") or 0),
                    "product_id": stock_info["designation_id"] or designation_id,
                    "methode_calcul": methode_calcul,
                    "mode_calcul_selectionne": mode_calcul,
                    "historique_details": historique,
                    "sans_mouvement": sans_mouvement,
                    "seuil_minimum": catalog_info.get("seuil_minimum") or 0,
                    "unite": catalog_info.get("unite") or "",
                }
            )

        resultats.sort(
            key=lambda item: (
                item["quantite_a_commander"],
                item["quantite_demandee"],
                item["quantite_comparee"],
            ),
            reverse=True,
        )

        return JsonResponse(
            {
                "success": True,
                "base_nom": base.nom_base,
                "periode": f"{nb_jours} jours (~ {int(nb_jours)//30} mois)",
                "date_debut": date_debut.strftime("%d/%m/%Y"),
                "mode_calcul": mode_calcul,
                "mode_calcul_label": CALCUL_MODE_LABELS[mode_calcul],
                "resultats": resultats,
                "total_lignes": len(resultats),
                "total_articles_retenus": total_articles_retenus,
                "total_bons_analyzes": total_bons_scanned,
                "total_bons_concernes": total_bons_matching,
                "total_articles_bons": total_articles_bons,
                "total_articles_historique": total_articles_historique,
                "magasins_base": sorted(list(magasin_names)),
            }
        )

    except Base.DoesNotExist:
        return JsonResponse({"success": False, "error": "Base non trouvee"}, status=404)
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def api_generer_bon_commande(request):
    """Prepare quote request payload from calculated quantities and persist it."""
    try:
        data = json.loads(request.body or "{}")
        base_id = data.get("base_id")
        items = data.get("items", [])
        nb_jours = data.get("nb_jours")
        mode_calcul = data.get("mode_calcul")
        date_debut_str = data.get("date_debut")

        if not base_id:
            return JsonResponse({"success": False, "error": "Base requise"}, status=400)
        
        base = _filter_bases_for_commandes(Base.objects.all(), request.user).filter(id=base_id).first()
        if not base:
            return JsonResponse({"success": False, "error": "Base non autorisee ou introuvable"}, status=403)
        
        if not items:
            return JsonResponse({"success": False, "error": "Aucun article selectionne"}, status=400)

        # Generate unique request number
        now = timezone.now()
        timestamp = now.strftime("%Y%m%d%H%M")
        short_uuid = str(uuid.uuid4())[:8]
        numero_demande = f"DD-{timestamp}-{short_uuid}"

        # Get creator
        employe = getattr(request.user, "employe", None)

        # Calculate analysis month
        periode_analyse = None
        if nb_jours:
            try:
                periode_analyse = int(nb_jours) // 30
            except (ValueError, TypeError):
                pass

        # Create the DemandeDevis
        demande = DemandeDevis.objects.create(
            numero_demande=numero_demande,
            base=base,
            creee_par=employe,
            statut='brouillon',
            periode_analyse=periode_analyse,
            mode_calcul=mode_calcul,
            total_articles=len(items)
        )

        # Create items
        created_count = 0
        total_devis_estime = Decimal('0')
        
        for item in items:
            designation_id = item.get("designation_id")
            if not designation_id:
                continue
            
            try:
                designation = Designation.objects.get(id=designation_id)
            except Designation.DoesNotExist:
                continue

            qte_finale = Decimal(str(item.get("quantite_finale", 0)))
            prix_u = designation.prix_unitaire or Decimal('0')
            montant_ligne = qte_finale * prix_u
            total_devis_estime += montant_ligne

            DemandeDevisItem.objects.create(
                demande_devis=demande,
                designation=designation,
                besoin_retenu=Decimal(str(item.get("quantite_demandee", 0))),
                estimation_historique=Decimal(str(item.get("quantite_estimee_historique", 0))),
                stock_actuel=Decimal(str(item.get("stock_actuel", 0))),
                quantite_a_commander=Decimal(str(item.get("quantite_a_commander", 0))),
                quantite_finale=qte_finale,
                prix_unitaire_estime=prix_u,
                nb_lignes_bl=int(item.get("nb_lignes", 0)),
                source_calcul=item.get("methode_calcul", mode_calcul)
            )
            created_count += 1

        # Update totals on header
        demande.total_articles = created_count
        demande.montant_estime = total_devis_estime
        demande.save()

        return JsonResponse(
            {
                "success": True,
                "message": f"{created_count} article(s) enregistrés dans la demande {numero_demande}",
                "demande_id": str(demande.id),
                "numero_demande": numero_demande,
                "montant_estime": float(total_devis_estime)
            }
        )

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required
def demande_devis_list(request):
    """List of generated quote requests."""
    bases = _filter_bases_for_commandes(Base.objects.all(), request.user)
    demandes = DemandeDevis.objects.filter(base__in=bases).select_related('base', 'creee_par').order_by('-date_creation')

    context = {
        "demandes": demandes,
        "title": "Demandes de Devis (Calculs)",
    }
    return render(request, "inventory/demande_devis_list.html", context)


@login_required
def demande_devis_detail(request, demande_id):
    """Detailed view of a quote request with the calculated quantities."""
    bases_scope = _filter_bases_for_commandes(Base.objects.all(), request.user)
    try:
        demande = DemandeDevis.objects.select_related('base', 'creee_par').get(id=demande_id, base__in=bases_scope)
    except DemandeDevis.DoesNotExist:
        return render(request, "404.html", status=404)

    items = demande.items.select_related('designation', 'designation__type_designation').order_by('designation__type_designation__nom', 'designation__nom')

    context = {
        "demande": demande,
        "items": items,
        "title": f"Détails Demande {demande.numero_demande}",
    }
    return render(request, "inventory/demande_devis_detail.html", context)


@login_required
def demande_devis_delete(request, demande_id):
    """
    Supprime une demande de devis
    """
    demande = get_object_or_404(DemandeDevis, id=demande_id)
    
    # Seul l'auteur ou un admin peut supprimer (ou selon vos règles métier)
    if not request.user.is_staff and demande.creee_par and demande.creee_par.user != request.user:
        messages.error(request, "Vous n'avez pas l'autorisation de supprimer cette demande.")
        return redirect('inventory:demande_devis_list')
        
    numero = demande.numero_demande
    demande.delete()
    messages.success(request, f"La demande {numero} a été supprimée avec succès.")
    return redirect('inventory:demande_devis_list')


@login_required
def export_demande_devis_excel(request, demande_id):
    """
    Exporte une demande de devis au format Excel
    """
    bases_scope = _filter_bases_for_commandes(Base.objects.all(), request.user)
    try:
        demande = DemandeDevis.objects.select_related('base', 'creee_par').get(id=demande_id, base__in=bases_scope)
    except DemandeDevis.DoesNotExist:
        return HttpResponse("Demande introuvable ou accès refusé", status=404)

    # Créer le classeur
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Demande {demande.numero_demande[:15]}"

    # Styles
    title_font = Font(bold=True, size=14)
    header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
    alignment_center = Alignment(horizontal='center')
    alignment_right = Alignment(horizontal='right')

    # Informations de l'en-tête
    ws['A1'] = f"DEMANDE DE DEVIS N° {demande.numero_demande}"
    ws['A1'].font = title_font
    ws.merge_cells('A1:G1')

    ws['A3'] = "Base :"
    ws['B3'] = demande.base.nom_base
    ws['A4'] = "Date générée :"
    ws['B4'] = demande.date_creation.strftime("%d/%m/%Y %H:%M")
    ws['D3'] = "Générée par :"
    ws['E3'] = demande.creee_par.surnom if demande.creee_par else "Système"
    ws['D4'] = "Période d'analyse :"
    ws['E4'] = f"{demande.periode_analyse} mois" if demande.periode_analyse else "-"

    # En-têtes du tableau
    headers = ["Désignation", "Unité", "Stock", "Besoin", "Qté Finale", "P.U. (Ar)", "Total (Ar)"]
    start_row = 6
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=start_row, column=col)
        cell.value = header
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = alignment_center
        cell.border = border

    # Données regroupées
    items = demande.items.select_related('designation', 'designation__type_designation').order_by('designation__type_designation__nom', 'designation__nom')
    current_row = start_row + 1
    total_budget = Decimal('0')
    last_type = None

    for item in items:
        # Gérer le changement de groupe
        current_type = item.designation.type_designation.nom if item.designation.type_designation else "Sans catégorie"
        if current_type != last_type:
            # Ligne de séparation de groupe
            ws.cell(row=current_row, column=1, value=current_type.upper()).font = Font(bold=True, italic=True)
            ws.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=7)
            for col in range(1, 8):
                ws.cell(row=current_row, column=col).fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
                ws.cell(row=current_row, column=col).border = border
            current_row += 1
            last_type = current_type

        ws.cell(row=current_row, column=1, value=item.designation.nom).border = border
        ws.cell(row=current_row, column=2, value=item.designation.unite or "").border = border
        
        ws.cell(row=current_row, column=3, value=float(item.stock_actuel or 0)).border = border
        ws.cell(row=current_row, column=3).alignment = alignment_center
        
        ws.cell(row=current_row, column=4, value=float(item.besoin_retenu or 0)).border = border
        ws.cell(row=current_row, column=4).alignment = alignment_center
        
        ws.cell(row=current_row, column=5, value=float(item.quantite_finale or 0)).border = border
        ws.cell(row=current_row, column=5).alignment = alignment_center
        ws.cell(row=current_row, column=5).font = Font(bold=True)

        pu = item.prix_unitaire_estime or Decimal('0')
        ws.cell(row=current_row, column=6, value=float(pu)).border = border
        ws.cell(row=current_row, column=6).number_format = '#,##0'
        ws.cell(row=current_row, column=6).alignment = alignment_right

        total_line = (item.quantite_finale or 0) * pu
        ws.cell(row=current_row, column=7, value=float(total_line)).border = border
        ws.cell(row=current_row, column=7).number_format = '#,##0'
        ws.cell(row=current_row, column=7).alignment = alignment_right
        
        total_budget += total_line
        current_row += 1

    # Pied de page (Total)
    ws.cell(row=current_row, column=5, value="ESTIMATION TOTALE :").font = Font(bold=True)
    ws.cell(row=current_row, column=7, value=float(total_budget)).font = Font(bold=True)
    ws.cell(row=current_row, column=7).number_format = '#,##0 "Ar"'
    ws.cell(row=current_row, column=7).alignment = alignment_right

    # Ajustement largeur colonnes
    col_widths = [40, 10, 10, 10, 12, 15, 20]
    for i, width in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = width

    # Préparer la réponse
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    filename = f"Demande_Devis_{demande.numero_demande}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    wb.save(response)
    return response


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def api_export_calcul_excel(request):
    """
    Exporte les résultats du calcul (non encore enregistrés) au format Excel
    """
    try:
        data = json.loads(request.body or "{}")
        base_id = data.get("base_id")
        items = data.get("items", [])
        nb_jours = data.get("nb_jours", 30)
        mode_calcul = data.get("mode_calcul", "auto")
        base_nom = data.get("base_nom", "")

        if not items:
            return JsonResponse({"success": False, "error": "Aucun article à exporter"}, status=400)

        # Créer le classeur
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Calcul Commande"

        # Styles
        title_font = Font(bold=True, size=14)
        header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF")
        border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
        alignment_center = Alignment(horizontal='center')
        alignment_right = Alignment(horizontal='right')

        # Informations de l'en-tête
        ws['A1'] = f"PREVISIONNEL DE COMMANDE {base_nom}".upper()
        ws['A1'].font = title_font
        ws.merge_cells('A1:I1')

        ws['A3'] = "Base :"
        ws['B3'] = base_nom
        ws['A4'] = "Date calcul :"
        ws['B4'] = timezone.now().strftime("%d/%m/%Y %H:%M")
        ws['D3'] = "Mode :"
        ws['E3'] = mode_calcul
        ws['D4'] = "Période d'analyse :"
        ws['E4'] = f"{nb_jours} jours (~ {int(nb_jours)//30} mois)"

        # En-têtes du tableau
        headers = [
            "Désignation", "Unité", "Stock Précéden", "Achats Période", 
            "Estim. Historique", "Bons Attente", "Stock Actuel", 
            "A Commander", "Quantité Finale"
        ]
        start_row = 6
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=start_row, column=col)
            cell.value = header
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = alignment_center
            cell.border = border

        # Données triées par type puis par nom
        items.sort(key=lambda x: (
            (x.get("designation_type_nom") or "").lower(),
            (x.get("designation_nom") or "").lower()
        ))

        current_row = start_row + 1
        last_type = None

        for item in items:
            # Gérer le changement de groupe
            current_type = item.get("designation_type_nom") or "SANS CATEGORIE"
            if current_type != last_type:
                # Ligne de séparation de groupe dans l'Excel prévisionnel
                ws.cell(row=current_row, column=1, value=current_type.upper()).font = Font(bold=True, italic=True)
                ws.merge_cells(start_row=current_row, start_column=1, end_row=current_row, end_column=9)
                for col in range(1, 10):
                    ws.cell(row=current_row, column=col).fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
                    ws.cell(row=current_row, column=col).border = border
                current_row += 1
                last_type = current_type

            ws.cell(row=current_row, column=1, value=item.get("designation_nom", "")).border = border
            ws.cell(row=current_row, column=2, value=item.get("unite", "")).border = border
            
            ws.cell(row=current_row, column=3, value=float(hist.get("stock_precedent", 0))).border = border
            ws.cell(row=current_row, column=4, value=float(hist.get("achats_periode", 0))).border = border
            ws.cell(row=current_row, column=5, value=float(item.get("quantite_estimee_historique", 0))).border = border
            ws.cell(row=current_row, column=6, value=float(item.get("quantite_demandee_bons", 0))).border = border
            ws.cell(row=current_row, column=7, value=float(item.get("stock_actuel", 0))).border = border
            
            ws.cell(row=current_row, column=8, value=float(item.get("quantite_a_commander", 0))).border = border
            ws.cell(row=current_row, column=8).font = Font(bold=True, color="FF0000" if float(item.get("quantite_a_commander", 0)) > 0 else "000000")
            
            ws.cell(row=current_row, column=9, value=float(item.get("quantite_finale", 0))).border = border
            ws.cell(row=current_row, column=9).font = Font(bold=True)

            # Alignements
            for col in range(3, 10):
                ws.cell(row=current_row, column=col).alignment = alignment_center
                
            current_row += 1

        # Ajustement largeur colonnes
        col_widths = [40, 10, 15, 15, 15, 15, 15, 15, 15]
        for i, width in enumerate(col_widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = width

        # Sauvegarder en mémoire et retourner en base64 (car c'est un call POST AJAX)
        output = BytesIO()
        wb.save(output)
        output.seek(0)
        
        # Vu que c'est un JsonResponse attendu par le JS ou un blob, 
        # on va plutôt retourner directement le flux si on peut le gérer en JS
        response = HttpResponse(
            output.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="Calcul_Commande_{base_nom}.xlsx"'
        return response

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)
