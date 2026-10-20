"""Pages d'analyse des coûts par ouvrage / par commune (dépenses vs recettes, modélisable)."""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render

from apps.accounting.services.analyse_couts_ouvrages import (
    ParamsAnalyse,
    construire_analyse,
    construire_analyse_communes,
    construire_detail,
    construire_detail_commune,
    options_geo_soakoja,
)


def _bases_soakoja():
    from apps.organization.models import Base

    return list(
        Base.objects.filter(organisation__nom_organisation__icontains="soakoja")
        .order_by("nom_base")
        .values("id", "nom_base")
    )


def _filtres_contexte(params: ParamsAnalyse) -> dict:
    return {
        "bases": _bases_soakoja(),
        "geo": options_geo_soakoja(),
        "base_selected": params.base_id,
        "region_selected": params.region_id,
        "district_selected": params.district_id,
        "commune_selected": params.commune_id,
    }


@login_required
def analyse_couts_ouvrages(request):
    params = ParamsAnalyse.from_request(request)
    analyse = construire_analyse(params)
    return render(
        request,
        "accounting/analyse_couts_ouvrages.html",
        {"analyse": analyse, **_filtres_contexte(params)},
    )


@login_required
def api_analyse_couts_ouvrages(request):
    params = ParamsAnalyse.from_request(request)
    analyse = construire_analyse(params)
    return JsonResponse(analyse)


@login_required
def api_analyse_couts_ouvrages_detail(request):
    params = ParamsAnalyse.from_request(request)
    ouvrage_id = (request.GET.get("ouvrage_id") or "").strip()
    categorie = (request.GET.get("categorie") or "").strip()
    if not ouvrage_id or not categorie:
        return JsonResponse({"error": "ouvrage_id et categorie requis"}, status=400)
    return JsonResponse(construire_detail(params, ouvrage_id, categorie))


@login_required
def analyse_couts_communes(request):
    params = ParamsAnalyse.from_request(request)
    analyse = construire_analyse_communes(params)
    return render(
        request,
        "accounting/analyse_couts_communes.html",
        {"analyse": analyse, **_filtres_contexte(params)},
    )


@login_required
def api_analyse_couts_communes(request):
    params = ParamsAnalyse.from_request(request)
    analyse = construire_analyse_communes(params)
    return JsonResponse(analyse)


@login_required
def api_analyse_couts_communes_detail(request):
    params = ParamsAnalyse.from_request(request)
    commune_id = (request.GET.get("commune_id") or "").strip()
    categorie = (request.GET.get("categorie") or "").strip()
    if not commune_id or not categorie:
        return JsonResponse({"error": "commune_id et categorie requis"}, status=400)
    return JsonResponse(construire_detail_commune(params, commune_id, categorie))
