"""
Contrôle d'une saisie comptable au compte 621102 (indemnités RBF) avant validation.

Deux règles, déjà appliquées à la liste des écritures (`indemnites_points` / `pointage_ecritures`) :

* plafond de 40 000 Ar d'indemnités par point d'eau et par an ;
* le point d'eau doit avoir assez de paiements forfaitaires pointés (10 000 Ar d'indemnité au plus par unité de
  forfait pointée).

Le cumul tient compte de ce qui est déjà dans DiameX (`BaseDiameX`) ET des saisies du workflow déjà validées, pas
encore importées, pour qu'on ne puisse pas contourner le plafond en saisissant deux fois le même jour.

Ces contrôles ne sont pas des erreurs de format : un Directeur ou un Responsable opérationnel peut valider malgré eux
(voir `apps.employees.permissions.can_override_saisie_controls`).
"""
from decimal import Decimal

from .indemnites_points import build_counters, counter_key
from .pointage_ecritures import COMPTE_INDEMNITES, _forfait_summary, classer_recoupement


def _ar(value):
    return f"{Decimal(value):,.0f}".replace(",", " ") + " Ar"


def _resolve_point(description, compte_code, sole_point_cache):
    """(ouvrage_id, id point, IDXLS) lus dans le libellé ; ouvrage_id vide si le libellé ne désigne pas un ouvrage."""
    from apps.accounting.extracteurs_description import extraire_ouvrage_et_mois_generique
    from apps.core.views_ouvrage_interventions import _indemnity_point_id

    extraction = extraire_ouvrage_et_mois_generique(description or "", compte_code)
    if not extraction or isinstance(extraction, list):
        return "", "", ""
    ouvrage = extraction.get("ouvrage_obj")
    if not ouvrage:
        return "", "", ""
    point_id, idxls = _indemnity_point_id(extraction, ouvrage, sole_point_cache)
    return str(ouvrage.id), point_id, idxls


def controler_indemnite_saisie(description, date_m, montant_out, compte_code=COMPTE_INDEMNITES):
    """
    Renvoie {"derogeables": [messages], "warnings": [messages]}.

    `derogeables` : la saisie n'est pas valide en l'état mais un directeur peut la valider ;
    `warnings`    : contrôle impossible (ouvrage / point d'eau non reconnu dans le libellé).
    """
    from apps.accounting.models import SaisieComptable
    from apps.core.views_ouvrage_interventions import (
        PLAFOND_INDEMNITE_PAR_POINT_EAU_PUBLIC, _rbf_indemnity_lines_by_ouvrage,
    )

    result = {"derogeables": [], "warnings": []}
    montant_out = Decimal(montant_out or 0)
    if montant_out <= 0 or not date_m:
        return result

    sole_point_cache = {}
    ouvrage_id, point_id, idxls = _resolve_point(description, compte_code, sole_point_cache)
    if not ouvrage_id:
        result["warnings"].append(
            "Indemnité : ouvrage non reconnu dans la description, plafond annuel et forfaitaire non contrôlés.")
        return result
    if not point_id and not idxls:
        result["warnings"].append(
            "Indemnité : point d'eau non identifié dans la description (IDXLS manquant), "
            "plafond annuel et forfaitaire non contrôlés.")
        return result

    year = date_m.year
    key = counter_key(ouvrage_id, point_id, idxls)

    counters, _ = build_counters(_rbf_indemnity_lines_by_ouvrage())
    already_in_diamex = counters.get((key, year), {}).get("total", Decimal("0.00"))

    already_entered = Decimal("0.00")
    for saisie in SaisieComptable.objects.filter(
        compte_code=compte_code, statut="valide", date_m__year=year, montant_out__gt=0,
    ).only("description", "montant_out"):
        other = _resolve_point(saisie.description, compte_code, sole_point_cache)
        if counter_key(other[0], other[1], other[2]) == key:
            already_entered += Decimal(saisie.montant_out)

    paid_before = already_in_diamex + already_entered
    total = paid_before + montant_out

    if total > PLAFOND_INDEMNITE_PAR_POINT_EAU_PUBLIC:
        result["derogeables"].append(
            f"Plafond annuel dépassé : {_ar(paid_before)} déjà payés en {year} sur ce point d'eau + {_ar(montant_out)} "
            f"= {_ar(total)}, pour un plafond de {_ar(PLAFOND_INDEMNITE_PAR_POINT_EAU_PUBLIC)} par point d'eau et par an."
        )

    if point_id:
        forfait = _forfait_summary([point_id], [year])[(point_id, year)]
        status, allowed = classer_recoupement(
            total, forfait["units"], True, unites_non_pointees=forfait["unpointed_units"])
        if status == "sans_forfait":
            extra = (f" ({forfait['unpointed_units']} unité(s) facturée(s) mais pas encore pointée(s))"
                     if forfait["unpointed_units"] else "")
            result["derogeables"].append(
                f"Aucun paiement forfaitaire pointé en {year} pour ce point d'eau{extra} : "
                f"les indemnités cumulées ({_ar(total)}) ne sont pas couvertes.")
        elif status == "depasse":
            result["derogeables"].append(
                f"Paiements forfaitaires insuffisants : {forfait['units']} unité(s) pointée(s) en {year} autorisent "
                f"{_ar(allowed)} d'indemnités, cumul après cette saisie {_ar(total)}.")
    else:
        result["warnings"].append(
            f"Indemnité : point d'eau IDXLS {idxls} non retrouvé, contrôle des paiements forfaitaires impossible.")

    return result
