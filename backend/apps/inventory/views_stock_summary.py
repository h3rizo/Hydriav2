"""
Views for stock summary pending-delivery actions.
"""
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from apps.organization.models import Base
from apps.planning.models import Designation, PlanningDetail

from .views import _filter_bases_by_scope, _filter_plannings_by_scope_inventory


@login_required
@require_http_methods(["GET"])
def api_planning_details_en_attente(request, designation_id):
    """
    Return pending PlanningDetail rows for one designation, scoped by user.
    """
    try:
        designation = Designation.objects.get(id=designation_id)
        base_id = (request.GET.get("base_id") or "").strip()

        details = PlanningDetail.objects.filter(
            designation=designation,
            livraison=False,
        ).select_related(
            "planning",
            "planning__employe",
            "planning__ouvrage",
            "magasin_achat",
        )

        details = _filter_plannings_by_scope_inventory(details, request.user)

        if base_id:
            base_allowed = _filter_bases_by_scope(Base.objects.all(), request.user).filter(id=base_id).exists()
            if base_allowed:
                details = details.filter(planning__employe__base_id=base_id)

        details = details.order_by("-planning__date")[:50]

        results = [
            {
                "id": str(detail.id),
                "planning_id": str(detail.planning.id) if detail.planning else None,
                "employe": detail.planning.employe.surnom if detail.planning and detail.planning.employe else "N/A",
                "ouvrage": detail.planning.ouvrage.nom_ouvrage if detail.planning and detail.planning.ouvrage else "N/A",
                "date": detail.planning.date.strftime("%Y-%m-%d") if detail.planning and detail.planning.date else None,
                "quantite": float(detail.quantite) if detail.quantite else 0,
                "prix": float(detail.pu) if detail.pu else 0,
                "montant": float(detail.montant) if detail.montant else 0,
                "magasin_achat": detail.magasin_achat.nom_magasin if detail.magasin_achat else "N/A",
                "date_livraison": detail.date_livraison.strftime("%Y-%m-%d") if detail.date_livraison else None,
            }
            for detail in details
        ]

        return JsonResponse(
            {
                "success": True,
                "designation_nom": designation.nom,
                "designation_unite": designation.unite or "",
                "details": results,
                "count": len(results),
            }
        )

    except Designation.DoesNotExist:
        return JsonResponse({"success": False, "error": "Designation non trouvee"}, status=404)
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def api_livrer_planning_detail(request, detail_id):
    """
    Mark one PlanningDetail as delivered, scoped by user.
    """
    try:
        from datetime import date as dt_date

        detail = _filter_plannings_by_scope_inventory(
            PlanningDetail.objects.select_related("designation"),
            request.user,
        ).filter(id=detail_id).first()
        if not detail:
            return JsonResponse({"success": False, "error": "Planning detail non trouve"}, status=404)

        if detail.livraison:
            return JsonResponse(
                {"success": False, "error": "Ce planning detail est deja marque comme livre"},
                status=400,
            )

        detail.livraison = True
        if not detail.date_livraison:
            detail.date_livraison = dt_date.today()
        detail.save()

        return JsonResponse(
            {
                "success": True,
                "message": f"Article livre avec succes ({detail.designation.nom})",
                "detail_id": str(detail.id),
            }
        )

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)

