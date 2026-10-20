from collections import defaultdict
from apps.billing.tarifs_forfaitaires import tarif_pour_annee
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.urls import reverse
from django.shortcuts import render
from django.utils import timezone

from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_generique
from apps.accounting.models import BaseDiameX
from apps.billing.models import ConsoCarteSociale, PaiementForfaitaire, PointEau, Releve
from apps.geography.models import Commune, District, Region
from apps.organization.models import Ouvrage

from .views import (
    _build_coupure_periods_by_point,
    _get_gestionnaire_organisations_for_filter,
    _get_ouvrages_ids_by_effective_gestionnaire_ids,
    _is_releve_during_coupure,
    _resolve_effective_gestionnaire_scope,
    diviser_paiement_volume_multi,
    extraire_ouvrage_et_mois_generique as extraire_ouvrage_et_mois_generique_views,
)
from .views_dashboard_forfaitaire import (
    _get_modalite_active_map,
    _get_ouvrages_ids_by_organisation_for_annee,
    _resolve_gestionnaire_scope,
    _trimestres_exigibles_depuis_date_debut,
    calculer_decote_coupures,
)


def _safe_int(value, fallback):
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _get_filter_params(request):
    current_year = datetime.now().year
    return {
        "annee": _safe_int(request.GET.get("annee", str(current_year)), current_year),
        "filter_organisation": (request.GET.get("organisation", "") or "").strip(),
        "filter_region": (request.GET.get("region", "") or "").strip(),
        "filter_district": (request.GET.get("district", "") or "").strip(),
        "filter_commune": (request.GET.get("commune", "") or "").strip(),
        "filter_ouvrage": (request.GET.get("ouvrage", "") or "").strip(),
    }


def _build_ouvrage_geo_data(ouvrage_ids):
    ouvrages_geo = defaultdict(
        lambda: {
            "region_ids": set(),
            "district_ids": set(),
            "commune_ids": set(),
            "region_id": "",
            "district_id": "",
            "commune_id": "",
            "region_nom": "Sans region",
            "district_nom": "Sans district",
            "commune_nom": "Sans commune",
        }
    )
    regions_map = {}
    districts_map = {}
    communes_map = {}

    if not ouvrage_ids:
        return {
            "regions_map": regions_map,
            "districts_map": districts_map,
            "communes_map": communes_map,
            "ouvrages_geo": ouvrages_geo,
        }

    point_eau_scope = PointEau.objects.filter(
        ouvrage_id__in=list(ouvrage_ids)
    ).select_related(
        "ouvrage",
        "parcelle__village__fokontany__commune__district__region",
    ).order_by("ouvrage_id", "id")

    for point_eau in point_eau_scope:
        ouvrage = point_eau.ouvrage
        if not ouvrage:
            continue

        commune = None
        district = None
        region = None
        if point_eau.parcelle and point_eau.parcelle.village and point_eau.parcelle.village.fokontany:
            commune = point_eau.parcelle.village.fokontany.commune
            if commune and commune.district:
                district = commune.district
                if district.region:
                    region = district.region

        ouvrage_key = str(ouvrage.id)
        geo = ouvrages_geo[ouvrage_key]

        if commune:
            commune_id = str(commune.id)
            communes_map[commune_id] = commune
            geo["commune_ids"].add(commune_id)
            if not geo["commune_id"]:
                geo["commune_id"] = commune_id
                geo["commune_nom"] = commune.nom_commune
        if district:
            district_id = str(district.id)
            districts_map[district_id] = district
            geo["district_ids"].add(district_id)
            if not geo["district_id"]:
                geo["district_id"] = district_id
                geo["district_nom"] = district.nom_district
        if region:
            region_id = str(region.id)
            regions_map[region_id] = region
            geo["region_ids"].add(region_id)
            if not geo["region_id"]:
                geo["region_id"] = region_id
                geo["region_nom"] = region.nom_region

    return {
        "regions_map": regions_map,
        "districts_map": districts_map,
        "communes_map": communes_map,
        "ouvrages_geo": ouvrages_geo,
    }


def _build_geo_filter_options(annee, effective_gestionnaire_ids, filter_region, filter_district, filter_commune):
    ouvrage_ids = set(_get_ouvrages_ids_by_effective_gestionnaire_ids(effective_gestionnaire_ids))
    ouvrage_ids |= set(_get_ouvrages_ids_by_organisation_for_annee(effective_gestionnaire_ids, annee))

    if not ouvrage_ids:
        return {
            "regions": Region.objects.none(),
            "districts": District.objects.none(),
            "communes": Commune.objects.none(),
            "ouvrages": Ouvrage.objects.none(),
            "ouvrages_geo": {},
        }

    geo_data = _build_ouvrage_geo_data(ouvrage_ids)
    regions_map = geo_data["regions_map"]
    districts_map = geo_data["districts_map"]
    communes_map = geo_data["communes_map"]
    ouvrages_geo = geo_data["ouvrages_geo"]

    regions = sorted(regions_map.values(), key=lambda region: region.nom_region)
    districts = sorted(
        [
            district
            for district in districts_map.values()
            if not filter_region or str(district.region_id) == filter_region
        ],
        key=lambda district: district.nom_district,
    )
    communes = sorted(
        [
            commune
            for commune in communes_map.values()
            if (
                (not filter_district or str(commune.district_id) == filter_district)
                and (not filter_region or str(commune.district.region_id) == filter_region)
            )
        ],
        key=lambda commune: commune.nom_commune,
    )

    ouvrages = []
    for ouvrage in Ouvrage.objects.filter(id__in=list(ouvrage_ids)).order_by("nom_ouvrage"):
        geo = ouvrages_geo.get(str(ouvrage.id), {"region_ids": set(), "district_ids": set(), "commune_ids": set()})
        if filter_region and filter_region not in geo["region_ids"]:
            continue
        if filter_district and filter_district not in geo["district_ids"]:
            continue
        if filter_commune and filter_commune not in geo["commune_ids"]:
            continue
        ouvrages.append(ouvrage)

    return {
        "regions": regions,
        "districts": districts,
        "communes": communes,
        "ouvrages": ouvrages,
        "ouvrages_geo": ouvrages_geo,
    }


def _compute_volume_summary(annee, effective_gestionnaire_ids, filter_region, filter_district, filter_commune, filter_ouvrage):
    recouvrement_par_ouvrage_mois = {}
    recouvrement_par_ouvrage_annee = {}

    releves_qs = Releve.objects.filter(
        montant__isnull=False,
        montant__gt=0,
        point_eau__ouvrage__isnull=False,
    ).filter(
        Q(datereleve__year__gte=2025) | Q(datereleve__year=2024, datereleve__month=12)
    ).exclude(
        remarque__icontains="coupé"
    ).select_related(
        "point_eau",
        "point_eau__ouvrage",
        "point_eau__parcelle__village__fokontany__commune__district__region",
    )

    releves_filtered = []
    for releve in releves_qs:
        if not releve.datereleve:
            continue
        if releve.datereleve.year == annee:
            releves_filtered.append(releve)
            continue
        if releve.datereleve.year == (annee - 1) and releve.datereleve.month == 12:
            releves_filtered.append(releve)
    releves_qs = releves_filtered

    ouvrages_scope_ids = _get_ouvrages_ids_by_effective_gestionnaire_ids(effective_gestionnaire_ids)
    if effective_gestionnaire_ids is not None:
        releves_qs = [
            releve
            for releve in releves_qs
            if releve.point_eau and releve.point_eau.ouvrage and releve.point_eau.ouvrage.id in ouvrages_scope_ids
        ]

    if filter_region:
        releves_qs = [
            releve
            for releve in releves_qs
            if releve.point_eau
            and releve.point_eau.parcelle
            and releve.point_eau.parcelle.village
            and releve.point_eau.parcelle.village.fokontany
            and releve.point_eau.parcelle.village.fokontany.commune
            and releve.point_eau.parcelle.village.fokontany.commune.district
            and releve.point_eau.parcelle.village.fokontany.commune.district.region
            and str(releve.point_eau.parcelle.village.fokontany.commune.district.region.id) == filter_region
        ]
    if filter_district:
        releves_qs = [
            releve
            for releve in releves_qs
            if releve.point_eau
            and releve.point_eau.parcelle
            and releve.point_eau.parcelle.village
            and releve.point_eau.parcelle.village.fokontany
            and releve.point_eau.parcelle.village.fokontany.commune
            and releve.point_eau.parcelle.village.fokontany.commune.district
            and str(releve.point_eau.parcelle.village.fokontany.commune.district.id) == filter_district
        ]
    if filter_commune:
        releves_qs = [
            releve
            for releve in releves_qs
            if releve.point_eau
            and releve.point_eau.parcelle
            and releve.point_eau.parcelle.village
            and releve.point_eau.parcelle.village.fokontany
            and releve.point_eau.parcelle.village.fokontany.commune
            and str(releve.point_eau.parcelle.village.fokontany.commune.id) == filter_commune
        ]
    if filter_ouvrage:
        releves_qs = [
            releve
            for releve in releves_qs
            if releve.point_eau and releve.point_eau.ouvrage and str(releve.point_eau.ouvrage.id) == filter_ouvrage
        ]

    point_eau_ids = {str(releve.point_eau.id) for releve in releves_qs if releve.point_eau}
    periodes_coupure = _build_coupure_periods_by_point(point_eau_ids)
    releves_qs = [
        releve
        for releve in releves_qs
        if not _is_releve_during_coupure(releve, periodes_coupure, check_facturation_month=True)
    ]

    for releve in releves_qs:
        if not releve.point_eau or not releve.point_eau.ouvrage:
            continue

        ouvrage = releve.point_eau.ouvrage
        ouvrage_id = str(ouvrage.id)
        mois_source = releve.datereleve.month
        if mois_source == 12:
            mois = 1
            annee_cible = releve.datereleve.year + 1
        else:
            mois = mois_source + 1
            annee_cible = releve.datereleve.year

        if annee_cible != annee:
            continue

        cle_mois = f"{ouvrage_id}_{annee}_{mois:02d}"
        if cle_mois not in recouvrement_par_ouvrage_mois:
            recouvrement_par_ouvrage_mois[cle_mois] = {
                "ouvrage_id": ouvrage_id,
                "mois": mois,
                "total_prevu": Decimal("0"),
                "total_paye": Decimal("0"),
            }
        if ouvrage_id not in recouvrement_par_ouvrage_annee:
            recouvrement_par_ouvrage_annee[ouvrage_id] = {
                "total_prevu": Decimal("0"),
                "total_paye": Decimal("0"),
            }

        montant = Decimal(str(releve.montant or 0))
        recouvrement_par_ouvrage_mois[cle_mois]["total_prevu"] += montant
        recouvrement_par_ouvrage_annee[ouvrage_id]["total_prevu"] += montant

    ouvrages_filtres_ids = {str(releve.point_eau.ouvrage.id) for releve in releves_qs if releve.point_eau and releve.point_eau.ouvrage}
    if ouvrages_filtres_ids:
        diamex_707401 = BaseDiameX.objects.filter(compte_code="707401")
        for entry in diamex_707401:
            segments = []
            if entry.description and ";" in entry.description:
                segments = diviser_paiement_volume_multi(
                    entry.description,
                    entry.compte_code,
                    entry.montant_in if entry.montant_in else 0,
                )

            if segments:
                for segment in segments:
                    extraction = segment["extraction"]
                    ouvrage_obj = extraction.get("ouvrage_obj")
                    mois = extraction.get("mois")
                    annee_entry = extraction.get("annee")
                    if not ouvrage_obj or not mois or annee_entry != annee:
                        continue
                    ouvrage_id = str(ouvrage_obj.id)
                    if ouvrage_id not in ouvrages_filtres_ids:
                        continue

                    cle_mois = f"{ouvrage_id}_{annee}_{mois:02d}"
                    recouvrement_par_ouvrage_mois.setdefault(
                        cle_mois,
                        {
                            "ouvrage_id": ouvrage_id,
                            "mois": mois,
                            "total_prevu": Decimal("0"),
                            "total_paye": Decimal("0"),
                        },
                    )
                    recouvrement_par_ouvrage_annee.setdefault(
                        ouvrage_id,
                        {"total_prevu": Decimal("0"), "total_paye": Decimal("0")},
                    )
                    montant = Decimal(str(segment["montant"]))
                    recouvrement_par_ouvrage_mois[cle_mois]["total_paye"] += montant
                    recouvrement_par_ouvrage_annee[ouvrage_id]["total_paye"] += montant
            else:
                extraction = extraire_ouvrage_et_mois_generique_views(entry.description or "", entry.compte_code)
                ouvrage_obj = extraction.get("ouvrage_obj")
                mois = extraction.get("mois")
                annee_entry = extraction.get("annee")
                if not ouvrage_obj or not mois or annee_entry != annee:
                    continue
                ouvrage_id = str(ouvrage_obj.id)
                if ouvrage_id not in ouvrages_filtres_ids:
                    continue

                cle_mois = f"{ouvrage_id}_{annee}_{mois:02d}"
                recouvrement_par_ouvrage_mois.setdefault(
                    cle_mois,
                    {
                        "ouvrage_id": ouvrage_id,
                        "mois": mois,
                        "total_prevu": Decimal("0"),
                        "total_paye": Decimal("0"),
                    },
                )
                recouvrement_par_ouvrage_annee.setdefault(
                    ouvrage_id,
                    {"total_prevu": Decimal("0"), "total_paye": Decimal("0")},
                )
                montant = Decimal(str(entry.montant_in or 0))
                recouvrement_par_ouvrage_mois[cle_mois]["total_paye"] += montant
                recouvrement_par_ouvrage_annee[ouvrage_id]["total_paye"] += montant

    total_prevu = sum((item["total_prevu"] for item in recouvrement_par_ouvrage_annee.values()), Decimal("0"))
    total_paye = sum((item["total_paye"] for item in recouvrement_par_ouvrage_annee.values()), Decimal("0"))

    return {
        "key": "volume",
        "label": "Paiements au volume",
        "description": "Prevu = releves. Paye = comptabilite DiameX 707401.",
        "prevision_label": "Prevu",
        "prevision": total_prevu,
        "paye": total_paye,
        "ecart": total_prevu - total_paye,
        "taux": int((total_paye / total_prevu) * 100) if total_prevu > 0 else 0,
        "nb_ouvrages": len(recouvrement_par_ouvrage_annee),
        "ouvrage_ids": set(recouvrement_par_ouvrage_annee.keys()),
        "rows_by_ouvrage": {
            ouvrage_id: {
                "prevision": data["total_prevu"],
                "paye": data["total_paye"],
            }
            for ouvrage_id, data in recouvrement_par_ouvrage_annee.items()
        },
        "detail_url_name": "accounting:dashboard_paiements_volume",
    }


def _compute_cartes_sociales_summary(
    annee,
    effective_gestionnaire_ids,
    filter_region,
    filter_district,
    filter_commune,
    filter_ouvrage,
):
    ouvrages_scope_qs = Ouvrage.objects.filter(
        cartes_sociales_infra__isnull=False,
        modalites_gestion__date_fin__isnull=True,
        modalites_gestion__modalitepaiement__in=["au_volume", "mixte"],
    )
    if effective_gestionnaire_ids is not None:
        if effective_gestionnaire_ids:
            ouvrages_scope_qs = ouvrages_scope_qs.filter(
                modalites_gestion__gestionnaire_id__in=effective_gestionnaire_ids
            )
        else:
            ouvrages_scope_qs = ouvrages_scope_qs.none()
    ouvrages_scope_qs = ouvrages_scope_qs.distinct()

    point_eau_scope = PointEau.objects.filter(
        cartes_sociales__ouvrage_id__in=ouvrages_scope_qs.values_list("id", flat=True)
    ).select_related(
        "ouvrage",
        "parcelle__village__fokontany__commune__district__region",
    ).distinct()

    ouvrages_geo = defaultdict(lambda: {"region_ids": set(), "district_ids": set(), "commune_ids": set()})

    for point_eau in point_eau_scope:
        ouvrage = point_eau.ouvrage
        if not ouvrage:
            continue
        ouvrage_key = str(ouvrage.id)

        if point_eau.parcelle and point_eau.parcelle.village and point_eau.parcelle.village.fokontany:
            commune = point_eau.parcelle.village.fokontany.commune
            if commune:
                ouvrages_geo[ouvrage_key]["commune_ids"].add(str(commune.id))
                if commune.district:
                    ouvrages_geo[ouvrage_key]["district_ids"].add(str(commune.district.id))
                    if commune.district.region:
                        ouvrages_geo[ouvrage_key]["region_ids"].add(str(commune.district.region.id))

    ouvrages_filtres_ids = set(str(ouvrage.id) for ouvrage in ouvrages_scope_qs)
    if filter_region:
        ouvrages_filtres_ids = {
            ouvrage_id
            for ouvrage_id in ouvrages_filtres_ids
            if filter_region in ouvrages_geo.get(ouvrage_id, {}).get("region_ids", set())
        }
    if filter_district:
        ouvrages_filtres_ids = {
            ouvrage_id
            for ouvrage_id in ouvrages_filtres_ids
            if filter_district in ouvrages_geo.get(ouvrage_id, {}).get("district_ids", set())
        }
    if filter_commune:
        ouvrages_filtres_ids = {
            ouvrage_id
            for ouvrage_id in ouvrages_filtres_ids
            if filter_commune in ouvrages_geo.get(ouvrage_id, {}).get("commune_ids", set())
        }
    if filter_ouvrage:
        ouvrages_filtres_ids = {ouvrage_id for ouvrage_id in ouvrages_filtres_ids if ouvrage_id == filter_ouvrage}

    recouvrement_par_ouvrage = {}

    consos_qs = ConsoCarteSociale.objects.filter(
        date__year=annee,
        carte_sociale__ouvrage__isnull=False,
        carte_sociale__ouvrage_id__in=list(ouvrages_filtres_ids),
    ).select_related("carte_sociale__ouvrage")

    for conso in consos_qs:
        ouvrage = conso.carte_sociale.ouvrage
        if not ouvrage:
            continue
        ouvrage_id = str(ouvrage.id)
        recouvrement_par_ouvrage.setdefault(
            ouvrage_id,
            {"total_prevu": Decimal("0"), "total_paye": Decimal("0")},
        )
        recouvrement_par_ouvrage[ouvrage_id]["total_prevu"] += Decimal(str(conso.montant_paye or 0))

    diamex_748415 = BaseDiameX.objects.filter(compte_code="748415")
    for entry in diamex_748415:
        extraction = extraire_ouvrage_et_mois_generique(entry.description or "", entry.compte_code)
        ouvrage_obj = extraction.get("ouvrage_obj")
        mois = extraction.get("mois")
        annee_entry = extraction.get("annee")
        if not ouvrage_obj or not mois or annee_entry != annee:
            continue

        ouvrage_id = str(ouvrage_obj.id)
        if ouvrage_id not in ouvrages_filtres_ids:
            continue

        recouvrement_par_ouvrage.setdefault(
            ouvrage_id,
            {"total_prevu": Decimal("0"), "total_paye": Decimal("0")},
        )
        recouvrement_par_ouvrage[ouvrage_id]["total_paye"] += Decimal(str(entry.montant_in or 0))

    total_prevu = sum((item["total_prevu"] for item in recouvrement_par_ouvrage.values()), Decimal("0"))
    total_paye = sum((item["total_paye"] for item in recouvrement_par_ouvrage.values()), Decimal("0"))

    return {
        "key": "cartes_sociales",
        "label": "Paiements cartes sociales",
        "description": "Prevu = consommations cartes sociales. Paye = comptabilite DiameX 748415.",
        "prevision_label": "Prevu",
        "prevision": total_prevu,
        "paye": total_paye,
        "ecart": total_prevu - total_paye,
        "taux": int((total_paye / total_prevu) * 100) if total_prevu > 0 else 0,
        "nb_ouvrages": len(recouvrement_par_ouvrage),
        "ouvrage_ids": set(recouvrement_par_ouvrage.keys()),
        "rows_by_ouvrage": {
            ouvrage_id: {
                "prevision": data["total_prevu"],
                "paye": data["total_paye"],
            }
            for ouvrage_id, data in recouvrement_par_ouvrage.items()
        },
        "detail_url_name": "accounting:dashboard_paiements_cartes_sociales",
    }


def _compute_forfaitaire_summary(
    request,
    annee,
    filter_organisation,
    filter_region,
    filter_district,
    filter_commune,
    filter_ouvrage,
):
    accessible_gestionnaire_ids = _resolve_effective_gestionnaire_scope(
        request.user,
        filter_organisation,
    )["accessible_gestionnaire_ids"]
    gestionnaire_ids, _selected_organisation = _resolve_gestionnaire_scope(
        accessible_gestionnaire_ids,
        filter_organisation,
    )

    transactions_qs = BaseDiameX.objects.filter(
        compte_code="748411",
        date_m__year=annee,
    )
    ouvrages_scope_ids = _get_ouvrages_ids_by_organisation_for_annee(gestionnaire_ids, annee)

    transactions_avec_ouvrage = []
    for transaction in transactions_qs:
        extraction = extraire_ouvrage_et_mois_generique(transaction.description or "", "748411")
        ouvrage_obj = extraction.get("ouvrage_obj")
        if not ouvrage_obj:
            continue
        if gestionnaire_ids is not None and ouvrage_obj.id not in ouvrages_scope_ids:
            continue
        transactions_avec_ouvrage.append(
            {
                "ouvrage": ouvrage_obj,
                "montant": Decimal(str(transaction.montant_in or 0)),
            }
        )

    paiements_forfaitaires_qs = PaiementForfaitaire.objects.filter(
        date_facture__year=annee,
        date_facture__lte=timezone.localdate(),
    ).select_related(
        "point_eau",
        "point_eau__ouvrage",
    )
    if gestionnaire_ids is not None:
        paiements_forfaitaires_qs = paiements_forfaitaires_qs.filter(
            point_eau__ouvrage_id__in=ouvrages_scope_ids
        )

    montant_facture_par_ouvrage = defaultdict(lambda: Decimal("0"))
    for paiement in paiements_forfaitaires_qs:
        ouvrage = paiement.point_eau.ouvrage if paiement.point_eau else None
        if not ouvrage:
            continue
        montant_facture_par_ouvrage[ouvrage.id] += Decimal(str(paiement.montant or 0))

    ouvrages_ids = set(item["ouvrage"].id for item in transactions_avec_ouvrage) | set(montant_facture_par_ouvrage.keys())
    points_eau_forfait_qs = PointEau.objects.filter(
        tarifforfaitaire__isnull=False,
        tarifforfaitaire__gt=0,
    )
    if gestionnaire_ids is not None:
        points_eau_forfait_qs = points_eau_forfait_qs.filter(ouvrage_id__in=ouvrages_scope_ids)
    ouvrages_ids |= set(points_eau_forfait_qs.values_list("ouvrage_id", flat=True).distinct())

    ouvrages_qs = Ouvrage.objects.filter(id__in=ouvrages_ids)
    if filter_ouvrage:
        ouvrages_qs = ouvrages_qs.filter(id=filter_ouvrage)
    if filter_commune:
        ouvrages_qs = ouvrages_qs.filter(
            id__in=PointEau.objects.filter(
                parcelle__village__fokontany__commune_id=filter_commune
            ).values_list("ouvrage_id", flat=True).distinct()
        )
    if filter_district:
        ouvrages_qs = ouvrages_qs.filter(
            id__in=PointEau.objects.filter(
                parcelle__village__fokontany__commune__district_id=filter_district
            ).values_list("ouvrage_id", flat=True).distinct()
        )
    if filter_region:
        ouvrages_qs = ouvrages_qs.filter(
            id__in=PointEau.objects.filter(
                parcelle__village__fokontany__commune__district__region_id=filter_region
            ).values_list("ouvrage_id", flat=True).distinct()
        )

    ouvrages_filtre = list(ouvrages_qs)
    modalite_active_map = _get_modalite_active_map(
        [ouvrage.id for ouvrage in ouvrages_filtre],
        annee=annee,
        gestionnaire_ids=gestionnaire_ids,
    )

    total_a_collecter = Decimal("0")
    total_facture = Decimal("0")
    total_paye = Decimal("0")
    rows_by_ouvrage = {}

    for ouvrage in ouvrages_filtre:
        points_eau = PointEau.objects.filter(
            ouvrage_id=ouvrage.id,
            tarifforfaitaire__isnull=False,
        )

        modalite_active = modalite_active_map.get(ouvrage.id)
        trimestres_exigibles = _trimestres_exigibles_depuis_date_debut(
            annee,
            getattr(modalite_active, "date_debut", None),
        )

        montant_brut = Decimal("0")
        for point_eau in points_eau:
            tarif = tarif_pour_annee(point_eau, annee)
            montant_brut += tarif * Decimal(str(trimestres_exigibles))

        decote = calculer_decote_coupures(points_eau, annee)
        montant_collectable = montant_brut - decote
        if montant_collectable < 0:
            montant_collectable = Decimal("0")

        montant_facture = montant_facture_par_ouvrage.get(ouvrage.id, Decimal("0"))
        montant_encaisse = sum(
            item["montant"]
            for item in transactions_avec_ouvrage
            if item["ouvrage"].id == ouvrage.id
        )

        total_a_collecter += montant_collectable
        total_facture += montant_facture
        total_paye += montant_encaisse
        rows_by_ouvrage[str(ouvrage.id)] = {
            "prevision": montant_collectable,
            "paye": montant_encaisse,
            "prevision_secondaire": montant_facture,
        }

    return {
        "key": "forfaitaire",
        "label": "Paiements forfaitaires",
        "description": "Prevu retenu = a collecter apres decotes. Paye = comptabilite DiameX 748411.",
        "prevision_label": "A collecter",
        "prevision": total_a_collecter,
        "paye": total_paye,
        "ecart": total_a_collecter - total_paye,
        "taux": int((total_paye / total_a_collecter) * 100) if total_a_collecter > 0 else 0,
        "nb_ouvrages": len(ouvrages_filtre),
        "ouvrage_ids": {str(ouvrage.id) for ouvrage in ouvrages_filtre},
        "rows_by_ouvrage": rows_by_ouvrage,
        "detail_url_name": "accounting:dashboard_paiements_forfaitaire",
        "prevision_secondaire_label": "Facture",
        "prevision_secondaire": total_facture,
    }


def _build_communes_breakdown(categories):
    def _init_commune_row(region_nom, district_nom, commune_nom, commune_id):
        return {
            "region_nom": region_nom,
            "district_nom": district_nom,
            "commune_nom": commune_nom,
            "commune_id": commune_id,
            "forfaitaire_prevision": Decimal("0"),
            "forfaitaire_paye": Decimal("0"),
            "volume_prevision": Decimal("0"),
            "volume_paye": Decimal("0"),
            "cartes_sociales_prevision": Decimal("0"),
            "cartes_sociales_paye": Decimal("0"),
            "total_prevu": Decimal("0"),
            "total_paye": Decimal("0"),
            "ouvrage_ids": set(),
        }

    def _build_totals(rows):
        totals = {
            "forfaitaire_prevision": sum((Decimal(str(row["forfaitaire_prevision"] or 0)) for row in rows), Decimal("0")),
            "forfaitaire_paye": sum((Decimal(str(row["forfaitaire_paye"] or 0)) for row in rows), Decimal("0")),
            "volume_prevision": sum((Decimal(str(row["volume_prevision"] or 0)) for row in rows), Decimal("0")),
            "volume_paye": sum((Decimal(str(row["volume_paye"] or 0)) for row in rows), Decimal("0")),
            "cartes_sociales_prevision": sum((Decimal(str(row["cartes_sociales_prevision"] or 0)) for row in rows), Decimal("0")),
            "cartes_sociales_paye": sum((Decimal(str(row["cartes_sociales_paye"] or 0)) for row in rows), Decimal("0")),
            "total_prevu": sum((Decimal(str(row["total_prevu"] or 0)) for row in rows), Decimal("0")),
            "total_paye": sum((Decimal(str(row["total_paye"] or 0)) for row in rows), Decimal("0")),
            "nb_communes": len(rows),
            "nb_ouvrages": len(set().union(*(row["ouvrage_ids"] for row in rows))) if rows else 0,
        }
        totals["ecart"] = totals["total_prevu"] - totals["total_paye"]
        totals["taux"] = int((totals["total_paye"] / totals["total_prevu"]) * 100) if totals["total_prevu"] > 0 else 0
        return totals

    ouvrage_ids = set().union(*(category.get("ouvrage_ids", set()) for category in categories))
    geo_data = _build_ouvrage_geo_data(ouvrage_ids)
    ouvrages_geo = geo_data["ouvrages_geo"]
    rows_by_commune = {}

    for category in categories:
        category_key = category["key"]
        for ouvrage_id, row_data in category.get("rows_by_ouvrage", {}).items():
            ouvrage_key = str(ouvrage_id)
            geo = ouvrages_geo.get(ouvrage_key, {})
            region_nom = geo.get("region_nom") or "Sans region"
            district_nom = geo.get("district_nom") or "Sans district"
            commune_nom = geo.get("commune_nom") or "Sans commune"
            commune_id = geo.get("commune_id") or commune_nom
            key = (region_nom, district_nom, commune_id)
            commune_row = rows_by_commune.setdefault(
                key,
                _init_commune_row(region_nom, district_nom, commune_nom, commune_id),
            )

            prevision = Decimal(str(row_data.get("prevision") or 0))
            paye = Decimal(str(row_data.get("paye") or 0))
            commune_row[f"{category_key}_prevision"] += prevision
            commune_row[f"{category_key}_paye"] += paye
            commune_row["total_prevu"] += prevision
            commune_row["total_paye"] += paye
            commune_row["ouvrage_ids"].add(ouvrage_key)

    sorted_rows = sorted(
        rows_by_commune.values(),
        key=lambda row: (
            (row["region_nom"] or "").lower(),
            (row["district_nom"] or "").lower(),
            (row["commune_nom"] or "").lower(),
        ),
    )

    grouped_rows = defaultdict(lambda: defaultdict(list))
    for row in sorted_rows:
        row["nb_ouvrages"] = len(row["ouvrage_ids"])
        row["ecart"] = row["total_prevu"] - row["total_paye"]
        row["taux"] = int((row["total_paye"] / row["total_prevu"]) * 100) if row["total_prevu"] > 0 else 0
        grouped_rows[row["region_nom"]][row["district_nom"]].append(row)

    grouped = []
    for region_nom in sorted(grouped_rows.keys(), key=lambda value: value.lower()):
        districts = []
        for district_nom in sorted(grouped_rows[region_nom].keys(), key=lambda value: value.lower()):
            district_rows = grouped_rows[region_nom][district_nom]
            districts.append(
                {
                    "district_nom": district_nom,
                    "rows": district_rows,
                    "totals": _build_totals(district_rows),
                }
            )
        region_rows = [row for district in districts for row in district["rows"]]
        grouped.append(
            {
                "region_nom": region_nom,
                "districts": districts,
                "totals": _build_totals(region_rows),
            }
        )

    for group in grouped:
        for district in group["districts"]:
            district["totals"] = {
                key: (float(value) if isinstance(value, Decimal) else value)
                for key, value in district["totals"].items()
            }
            for row in district["rows"]:
                row["ouvrage_ids"] = sorted(row["ouvrage_ids"])
                for field in (
                    "forfaitaire_prevision",
                    "forfaitaire_paye",
                    "volume_prevision",
                    "volume_paye",
                    "cartes_sociales_prevision",
                    "cartes_sociales_paye",
                    "total_prevu",
                    "total_paye",
                    "ecart",
                ):
                    row[field] = float(row[field])
        group["totals"] = {
            key: (float(value) if isinstance(value, Decimal) else value)
            for key, value in group["totals"].items()
        }

    global_totals = _build_totals(sorted_rows)
    global_totals = {
        key: (float(value) if isinstance(value, Decimal) else value)
        for key, value in global_totals.items()
    }

    return {
        "groups": grouped,
        "totals": global_totals,
    }


@login_required
def dashboard_recettes_globales(request):
    filters = _get_filter_params(request)

    scope_info = _resolve_effective_gestionnaire_scope(request.user, filters["filter_organisation"])
    organisation_user = scope_info["organisation_user"]
    accessible_gestionnaire_ids = scope_info["accessible_gestionnaire_ids"]
    effective_gestionnaire_ids = scope_info["effective_gestionnaire_ids"]
    selected_organisation_id = scope_info["selected_organisation_id"]

    filter_options = _build_geo_filter_options(
        filters["annee"],
        effective_gestionnaire_ids,
        filters["filter_region"],
        filters["filter_district"],
        filters["filter_commune"],
    )

    categories = [
        _compute_forfaitaire_summary(
            request,
            filters["annee"],
            selected_organisation_id,
            filters["filter_region"],
            filters["filter_district"],
            filters["filter_commune"],
            filters["filter_ouvrage"],
        ),
        _compute_volume_summary(
            filters["annee"],
            effective_gestionnaire_ids,
            filters["filter_region"],
            filters["filter_district"],
            filters["filter_commune"],
            filters["filter_ouvrage"],
        ),
        _compute_cartes_sociales_summary(
            filters["annee"],
            effective_gestionnaire_ids,
            filters["filter_region"],
            filters["filter_district"],
            filters["filter_commune"],
            filters["filter_ouvrage"],
        ),
    ]

    total_prevu_global = sum((category["prevision"] for category in categories), Decimal("0"))
    total_paye_global = sum((category["paye"] for category in categories), Decimal("0"))
    total_ecart_global = total_prevu_global - total_paye_global
    ouvrages_couverts = set().union(*(category.get("ouvrage_ids", set()) for category in categories))
    communes_breakdown = _build_communes_breakdown(categories)

    query_string = request.GET.urlencode()
    for category in categories:
        detail_href = reverse(category["detail_url_name"])
        category["detail_href"] = f"{detail_href}?{query_string}" if query_string else detail_href
        category.pop("rows_by_ouvrage", None)
        category.pop("ouvrage_ids", None)
        category["prevision"] = float(category["prevision"])
        category["paye"] = float(category["paye"])
        category["ecart"] = float(category["ecart"])
        if "prevision_secondaire" in category:
            category["prevision_secondaire"] = float(category["prevision_secondaire"])

    context = {
        "title": "Synthese Recettes Eau",
        "annee": filters["annee"],
        "filter_organisation": selected_organisation_id,
        "filter_region": filters["filter_region"],
        "filter_district": filters["filter_district"],
        "filter_commune": filters["filter_commune"],
        "filter_ouvrage": filters["filter_ouvrage"],
        "organisations": _get_gestionnaire_organisations_for_filter(accessible_gestionnaire_ids),
        "show_organisation_filter": bool(
            organisation_user and getattr(organisation_user, "is_partenaire", False)
        ),
        "regions": filter_options["regions"],
        "districts": filter_options["districts"],
        "communes": filter_options["communes"],
        "ouvrages": filter_options["ouvrages"],
        "categories": categories,
        "communes_breakdown": communes_breakdown["groups"],
        "communes_totals": communes_breakdown["totals"],
        "stats_global": {
            "total_prevu": float(total_prevu_global),
            "total_paye": float(total_paye_global),
            "ecart": float(total_ecart_global),
            "taux_recouvrement": int((total_paye_global / total_prevu_global) * 100) if total_prevu_global > 0 else 0,
            "nb_categories": len(categories),
            "nb_ouvrages_total": len(ouvrages_couverts),
        },
        "current_query_string": query_string,
    }
    return render(request, "accounting/dashboard_recettes_globales.html", context)
