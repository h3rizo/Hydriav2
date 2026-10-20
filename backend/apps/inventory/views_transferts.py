from datetime import datetime
from decimal import Decimal
import json

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.employees.models import Employe
from apps.organization.models import Base, Magasin
from apps.planning.models import Designation

from .models import Stock, Transfert, TransfertItem
from .views import _filter_bases_by_scope, _filter_employes_by_scope, _normalize_poste_name


def _filter_magasins_by_scope(queryset, user):
    allowed_bases = _filter_bases_by_scope(Base.objects.all(), user)
    return queryset.filter(base_id__in=allowed_bases.values("id"))


def _is_caissiere_user(user):
    employe = getattr(user, "employe", None)
    poste_nom = getattr(getattr(employe, "poste", None), "nom_poste", "")
    poste_normalized = _normalize_poste_name(poste_nom)
    return "caiss" in poste_normalized


def _filter_destination_magasins_by_scope(queryset, user):
    """
    Le magasin d'origine reste cloisonne par scope standard.
    Exception demandee: une caissiere peut choisir une destination
    dans tous les magasins de son organisation.
    """
    if _is_caissiere_user(user):
        employe = getattr(user, "employe", None)
        organisation_id = getattr(getattr(employe, "base", None), "organisation_id", None)
        if not organisation_id:
            return queryset.none()
        return queryset.filter(base__organisation_id=organisation_id)
    return _filter_magasins_by_scope(queryset, user)


def _filter_transferts_by_scope(queryset, user):
    allowed_bases = _filter_bases_by_scope(Base.objects.all(), user)
    return queryset.filter(
        Q(magasin_origine__base_id__in=allowed_bases.values("id"))
        | Q(magasin_destination__base_id__in=allowed_bases.values("id"))
    )


def _build_transfert_stock_check(magasin_origine, items):
    resultats = []
    stocks_insuffisants = []

    if not magasin_origine or not getattr(magasin_origine, "base_id", None):
        return resultats, stocks_insuffisants

    for item in items:
        designation_id = item.get("designation_id")
        quantity = Decimal(str(item.get("quantity", 0) or 0))
        if not designation_id or quantity <= 0:
            continue

        designation = Designation.objects.filter(id=designation_id).first()
        if not designation:
            continue

        stock = Stock.objects.filter(
            designation_id=designation_id,
            base_id=magasin_origine.base_id,
        ).first()
        stock_actuel = Decimal(str(getattr(stock, "current_quantity", 0) or 0))
        stock_apres_transfert = stock_actuel - quantity
        suffisant = stock_actuel >= quantity

        row = {
            "designation_id": str(designation.id),
            "designation": designation.nom,
            "quantite_demandee": float(quantity),
            "stock_actuel": float(stock_actuel),
            "stock_apres_transfert": float(stock_apres_transfert),
            "magasin_origine": f"{magasin_origine.nom_magasin} ({magasin_origine.base.nom_base})",
            "suffisant": suffisant,
            "peut_transferer": suffisant,
        }
        resultats.append(row)
        if not suffisant:
            stocks_insuffisants.append(row)

    return resultats, stocks_insuffisants


@login_required
def transferts_list(request):
    """Main transfer management page."""
    magasins_origine = _filter_magasins_by_scope(
        Magasin.objects.select_related("base__organisation"),
        request.user,
    ).order_by("base__nom_base", "nom_magasin")

    magasins_destination = _filter_destination_magasins_by_scope(
        Magasin.objects.select_related("base__organisation"),
        request.user,
    ).order_by("base__nom_base", "nom_magasin")

    employes = _filter_employes_by_scope(
        Employe.objects.filter(date_debauchage__isnull=True),
        request.user,
    ).order_by("surnom")

    designations = Designation.objects.filter(actif=True).filter(
        Q(type_avance_caissiere="bon_livraison")
        | Q(type_avance_caissiere__iexact="Bon de livraison")
    ).order_by("nom")

    context = {
        "magasins_origine": magasins_origine,
        "magasins_destination": magasins_destination,
        "employes": employes,
        "designations": designations,
    }
    return render(request, "inventory/transferts_list_consolide.html", context)


@login_required
@require_http_methods(["GET"])
def api_transferts_list(request):
    """List transfers with filters."""
    statut = request.GET.get("statut", "")
    magasin_origine_id = request.GET.get("magasin_origine_id", "")
    magasin_destination_id = request.GET.get("magasin_destination_id", "")
    recherche = request.GET.get("recherche", "").strip()

    transferts = Transfert.objects.select_related(
        "magasin_origine__base__organisation",
        "magasin_destination__base__organisation",
        "initiated_by",
        "received_by",
    ).prefetch_related("items__designation")
    transferts = _filter_transferts_by_scope(transferts, request.user)

    if statut and statut != "all":
        transferts = transferts.filter(status=statut)
    if magasin_origine_id and magasin_origine_id != "all":
        transferts = transferts.filter(magasin_origine_id=magasin_origine_id)
    if magasin_destination_id and magasin_destination_id != "all":
        transferts = transferts.filter(magasin_destination_id=magasin_destination_id)
    if recherche:
        transferts = transferts.filter(
            Q(transfer_number__icontains=recherche) | Q(notes__icontains=recherche)
        )

    transferts = transferts.order_by("-transfer_date")

    data = []
    for t in transferts:
        items = []
        for item in t.items.all():
            items.append(
                {
                    "id": str(item.id),
                    "designation_id": str(item.designation.id),
                    "designation_nom": item.designation.nom,
                    "designation_unite": item.designation.unite or "",
                    "quantity_sent": float(item.quantity_sent),
                    "quantity_received": float(item.quantity_received) if item.quantity_received else 0,
                }
            )

        data.append(
            {
                "id": str(t.id),
                "transfer_number": t.transfer_number,
                "transfer_date": t.transfer_date.strftime("%Y-%m-%d %H:%M"),
                "expected_arrival_date": t.expected_arrival_date.strftime("%Y-%m-%d %H:%M") if t.expected_arrival_date else None,
                "actual_arrival_date": t.actual_arrival_date.strftime("%Y-%m-%d %H:%M") if t.actual_arrival_date else None,
                "status": t.status,
                "status_display": t.get_status_display(),
                "magasin_origine_id": str(t.magasin_origine.id),
                "magasin_origine": f"{t.magasin_origine.nom_magasin} ({t.magasin_origine.base.nom_base})",
                "magasin_destination_id": str(t.magasin_destination.id),
                "magasin_destination": f"{t.magasin_destination.nom_magasin} ({t.magasin_destination.base.nom_base})",
                "initiated_by": t.initiated_by.nom_complet if t.initiated_by else None,
                "received_by": t.received_by.nom_complet if t.received_by else None,
                "notes": t.notes or "",
                "nb_items": len(items),
                "items": items,
            }
        )

    return JsonResponse({"success": True, "transferts": data})


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def api_verifier_stock_transfert(request):
    """Verify stock availability for a proposed transfer."""
    try:
        data = json.loads(request.body or "{}")
        magasin_origine_id = data.get("magasin_origine_id")
        items = data.get("items", [])

        if not magasin_origine_id:
            return JsonResponse({"success": False, "error": "Magasin origine requis"}, status=400)
        if not items:
            return JsonResponse({"success": False, "error": "Aucun article a verifier"}, status=400)

        magasin_origine = _filter_magasins_by_scope(
            Magasin.objects.select_related("base"),
            request.user,
        ).filter(id=magasin_origine_id).first()
        if not magasin_origine:
            return JsonResponse({"success": False, "error": "Magasin origine non autorise"}, status=403)

        resultats, stocks_insuffisants = _build_transfert_stock_check(magasin_origine, items)
        return JsonResponse(
            {
                "success": True,
                "peut_transferer": not stocks_insuffisants,
                "resultats": resultats,
                "stocks_insuffisants": stocks_insuffisants,
            }
        )
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def api_create_transfert(request):
    """Create a transfer."""
    try:
        data = json.loads(request.body or "{}")

        today = datetime.now().strftime("%Y%m%d")
        prefix = f"TRANS-{today}-"
        from django.db.models import Max

        last_transfer = Transfert.objects.filter(
            transfer_number__startswith=prefix
        ).aggregate(Max("transfer_number"))

        if last_transfer["transfer_number__max"]:
            last_num = int(last_transfer["transfer_number__max"].split("-")[-1])
            next_num = last_num + 1
        else:
            next_num = 1

        transfer_number = f"{prefix}{next_num:03d}"

        magasin_origine_id = data.get("magasin_origine_id")
        magasin_destination_id = data.get("magasin_destination_id")

        if not magasin_origine_id or not magasin_destination_id:
            return JsonResponse({"success": False, "error": "Magasins origine et destination requis"}, status=400)
        if magasin_origine_id == magasin_destination_id:
            return JsonResponse({"success": False, "error": "Origine et destination doivent etre differents"}, status=400)

        allowed_magasins_origine = _filter_magasins_by_scope(Magasin.objects.all(), request.user)
        allowed_magasins_destination = _filter_destination_magasins_by_scope(
            Magasin.objects.all(),
            request.user,
        )
        magasin_origine = allowed_magasins_origine.filter(id=magasin_origine_id).first()
        magasin_destination = allowed_magasins_destination.filter(id=magasin_destination_id).first()
        if not magasin_origine or not magasin_destination:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Magasin origine ou destination non autorise",
                },
                status=403,
            )

        items = data.get("items", [])
        resultats_stock, stocks_insuffisants = _build_transfert_stock_check(magasin_origine, items)
        if stocks_insuffisants:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Stock insuffisant pour un ou plusieurs articles",
                    "peut_transferer": False,
                    "resultats": resultats_stock,
                    "stocks_insuffisants": stocks_insuffisants,
                },
                status=400,
            )

        transfert = Transfert.objects.create(
            transfer_number=transfer_number,
            transfer_date=datetime.now(),
            expected_arrival_date=datetime.fromisoformat(data["expected_arrival_date"]) if data.get("expected_arrival_date") else None,
            magasin_origine=magasin_origine,
            magasin_destination=magasin_destination,
            initiated_by=request.user.employe if hasattr(request.user, "employe") else None,
            notes=data.get("notes", ""),
        )

        for item in items:
            designation_id = item.get("designation_id")
            quantity = Decimal(str(item.get("quantity", 0)))
            if designation_id and quantity > 0:
                designation = Designation.objects.filter(id=designation_id).first()
                if designation:
                    TransfertItem.objects.create(
                        transfert=transfert,
                        designation=designation,
                        quantity_sent=quantity,
                    )

        return JsonResponse(
            {
                "success": True,
                "message": "Transfert cree avec succes",
                "transfert_id": str(transfert.id),
            }
        )

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def api_transfert_detail(request, transfert_id):
    """Get transfer details."""
    try:
        transfert = _filter_transferts_by_scope(
            Transfert.objects.select_related(
                "magasin_origine__base",
                "magasin_destination__base",
                "initiated_by",
                "received_by",
            ),
            request.user,
        ).prefetch_related("items__designation").get(id=transfert_id)

        items = []
        for item in transfert.items.all():
            items.append(
                {
                    "id": str(item.id),
                    "designation_id": str(item.designation.id),
                    "designation_nom": item.designation.nom,
                    "designation_unite": item.designation.unite or "",
                    "quantity_sent": float(item.quantity_sent),
                    "quantity_received": float(item.quantity_received),
                }
            )

        data = {
            "id": str(transfert.id),
            "transfer_number": transfert.transfer_number,
            "transfer_date": transfert.transfer_date.strftime("%Y-%m-%d %H:%M"),
            "expected_arrival_date": transfert.expected_arrival_date.strftime("%Y-%m-%d %H:%M") if transfert.expected_arrival_date else None,
            "actual_arrival_date": transfert.actual_arrival_date.strftime("%Y-%m-%d %H:%M") if transfert.actual_arrival_date else None,
            "status": transfert.status,
            "status_display": transfert.get_status_display(),
            "magasin_origine": f"{transfert.magasin_origine.nom_magasin} ({transfert.magasin_origine.base.nom_base})",
            "magasin_destination": f"{transfert.magasin_destination.nom_magasin} ({transfert.magasin_destination.base.nom_base})",
            "initiated_by": transfert.initiated_by.nom_complet if transfert.initiated_by else None,
            "received_by": transfert.received_by.nom_complet if transfert.received_by else None,
            "notes": transfert.notes or "",
            "items": items,
        }

        return JsonResponse({"success": True, "transfert": data})

    except Transfert.DoesNotExist:
        return JsonResponse({"success": False, "error": "Transfert non trouve"}, status=404)
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def api_update_transfert_status(request, transfert_id):
    """Update transfer status."""
    try:
        data = json.loads(request.body or "{}")
        action = data.get("action")

        transfert = _filter_transferts_by_scope(Transfert.objects.all(), request.user).get(id=transfert_id)

        if action == "envoyer":
            transfert.status = "en_cours"
        elif action == "recevoir":
            transfert.status = "recu"
            transfert.actual_arrival_date = datetime.now()
            transfert.received_by = request.user.employe if hasattr(request.user, "employe") else None

            quantities = data.get("quantities", {})
            for item in transfert.items.all():
                item_id = str(item.id)
                if item_id in quantities:
                    item.quantity_received = Decimal(str(quantities[item_id]))
                    item.save()
        elif action == "annuler":
            transfert.status = "annule"
        else:
            return JsonResponse({"success": False, "error": "Action invalide"}, status=400)

        transfert.save()
        return JsonResponse({"success": True, "message": "Statut mis a jour"})

    except Transfert.DoesNotExist:
        return JsonResponse({"success": False, "error": "Transfert non trouve"}, status=404)
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@csrf_exempt
@login_required
@require_http_methods(["POST"])
def api_delete_transfert(request, transfert_id):
    """Delete one transfer."""
    try:
        transfert = _filter_transferts_by_scope(Transfert.objects.all(), request.user).get(id=transfert_id)

        if transfert.status != "en_attente":
            return JsonResponse(
                {
                    "success": False,
                    "error": "Seuls les transferts en attente peuvent etre supprimes",
                },
                status=400,
            )

        transfert.delete()
        return JsonResponse({"success": True, "message": "Transfert supprime"})

    except Transfert.DoesNotExist:
        return JsonResponse({"success": False, "error": "Transfert non trouve"}, status=404)
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
def print_bon_livraison(request, transfert_id):
    """Print delivery note for a transfer."""
    try:
        transfert = _filter_transferts_by_scope(
            Transfert.objects.select_related(
                "magasin_origine__base__organisation",
                "magasin_destination__base__organisation",
                "initiated_by",
                "received_by",
            ),
            request.user,
        ).prefetch_related("items__designation").get(id=transfert_id)

        total_items = sum(float(item.quantity_sent) for item in transfert.items.all())

        context = {
            "transfert": transfert,
            "total_items": total_items,
            "date_impression": datetime.now().strftime("%d/%m/%Y %H:%M"),
        }
        return render(request, "inventory/bon_livraison_print.html", context)

    except Transfert.DoesNotExist:
        return render(request, "inventory/bon_livraison_print.html", {"error": "Transfert non trouve"})
