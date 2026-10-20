"""
Rapprochement des écritures DiameX avec ce qui a été « pointé » dessus, pour la liste des écritures.

* 748411 (vente eau au forfait, entrées) : lignes `PaiementForfaitaire` pointées sur l'écriture.
* 707401 (vente eau au volume, entrées)  : lignes `Releve` pointées sur l'écriture.
  Le pointage recopie (id_access, prog) de l'écriture vers (numeroDiameX, baseDiameX) de chaque ligne ; c'est donc
  ce couple qui fait le lien, exactement comme dans les modals de pointage des tableaux de bord.
* 621102 (indemnités RBF, sorties) : recoupement, point d'eau par point d'eau et par an, entre les indemnités payées
  et les paiements forfaitaires pointés du même point d'eau. Une indemnité correspond au plus à
  `PLAFOND_INDEMNITE_PAR_UNITE_FORFAIT` Ar par unité de forfait pointée (1 unité = 1 quantité = 1 tarif forfaitaire).
"""
from collections import defaultdict
from decimal import Decimal

from django.db.models import Count, Sum

from .indemnites_points import build_counters

COMPTE_FORFAIT = "748411"
COMPTE_VOLUME = "707401"
COMPTE_INDEMNITES = "621102"

# Une indemnité RBF ne doit pas dépasser 10 000 Ar pour chaque paiement d'une valeur de tarif forfaitaire.
PLAFOND_INDEMNITE_PAR_UNITE_FORFAIT = Decimal("10000")
TOLERANCE = Decimal("0.01")

SOURCE_LABELS = {"forfaitaire": "Paiement forfaitaire", "releve": "Relevé"}
EXPECTED_SOURCE = {COMPTE_FORFAIT: "forfaitaire", COMPTE_VOLUME: "releve"}


def _money(value):
    return Decimal(str(value or 0))


def _key(entry):
    """Couple de pointage (numeroDiameX, baseDiameX) de l'écriture, ou None si elle ne peut pas être pointée."""
    if entry.id_access is None or not str(entry.prog or "").strip():
        return None
    return str(entry.id_access).strip(), str(entry.prog).strip()


# --------------------------------------------------------------------------------------------------------------
# 748411 / 707401 : lignes pointées sur l'écriture
# --------------------------------------------------------------------------------------------------------------

def _pointed_totals(numeros):
    """{(source, numero, base): (nombre, total)} pour les numéros donnés, dans les deux tables."""
    from apps.billing.models import PaiementForfaitaire, Releve

    result = {}
    for source, model in (("forfaitaire", PaiementForfaitaire), ("releve", Releve)):
        rows = (
            model.objects.filter(numeroDiameX__in=numeros)
            .exclude(baseDiameX__isnull=True).exclude(baseDiameX="")
            .order_by().values("numeroDiameX", "baseDiameX")
            .annotate(n=Count("id"), total=Sum("montant"))
        )
        for row in rows:
            result[(source, str(row["numeroDiameX"]).strip(), str(row["baseDiameX"]).strip())] = (
                row["n"], _money(row["total"]))
    return result


def _verdict(expected, montant, found):
    """found : {source: (n, total)} pour cette écriture. Renvoie (verdict, source retenue, n, total, écart)."""
    on_expected = found.get(expected)
    other = next((s for s in found if s != expected), None)
    if on_expected:
        n, total = on_expected
        gap = total - montant
        return ("ok" if abs(gap) <= TOLERANCE else "ecart"), expected, n, total, gap
    if other:
        n, total = found[other]
        return "mauvaise_source", other, n, total, total - montant
    return "non_pointe", expected, 0, Decimal("0.00"), -montant


def attach_pointage(entries):
    """Ajoute `entry.pointage` (dict) aux écritures 748411 / 707401 de la page ; None pour les autres comptes."""
    targets = [e for e in entries if e.compte_code in EXPECTED_SOURCE]
    for entry in entries:
        entry.pointage = None
    keyed = [(e, _key(e)) for e in targets]
    numeros = {k[0] for _, k in keyed if k}
    totals = _pointed_totals(numeros) if numeros else {}
    for entry, key in keyed:
        expected = EXPECTED_SOURCE[entry.compte_code]
        montant = _money(entry.montant_in)
        found = {}
        if key:
            for source in SOURCE_LABELS:
                if (source, *key) in totals:
                    found[source] = totals[(source, *key)]
        verdict, source, n, total, gap = _verdict(expected, montant, found)
        entry.pointage = {
            "verdict": verdict, "expected": expected, "source": source,
            "source_label": SOURCE_LABELS[source], "expected_label": SOURCE_LABELS[expected],
            "count": n, "total": total, "montant": montant, "gap": gap,
            "pointable": key is not None,
        }
    return entries


def _point_label(point):
    if not point:
        return "Point d'eau introuvable"
    name = (point.nomabonne or point.code_point_eau or "").strip()
    idxls = (point.idxls or "").strip()
    return f"IDXLS {idxls} — {name}" if idxls and name else (name or (f"IDXLS {idxls}" if idxls else "Point d'eau"))


def _idxls_sort(row):
    text = row["idxls"]
    return (0, int(text), row["date"]) if text.isdigit() else (1, 0, row["date"])


def pointage_detail(entry):
    """Contenu du modal pour une écriture 748411 / 707401 : les lignes pointées, avec le contrôle de montant."""
    from apps.billing.models import PaiementForfaitaire, Releve

    expected = EXPECTED_SOURCE[entry.compte_code]
    key = _key(entry)
    montant = _money(entry.montant_in)
    rows, found = [], {}
    if key:
        numero, base = key
        for source, model in (("forfaitaire", PaiementForfaitaire), ("releve", Releve)):
            qs = model.objects.filter(numeroDiameX=numero, baseDiameX=base).select_related(
                "point_eau", "point_eau__type_point_eau", "point_eau__ouvrage")
            count, total = 0, Decimal("0.00")
            for item in qs:
                point = item.point_eau
                if source == "forfaitaire":
                    day, extra = item.date_facture, {
                        "quantite": item.quantite, "prix_unitaire": float(item.prix_unitaire or 0)}
                else:
                    from apps.billing.views_facturation import _build_facture_qr_payload

                    day = item.datereleve
                    # La facture porte le mois SUIVANT le relevé (même règle que le QR du talon imprimé).
                    fy, fm = (day.year + (day.month == 12), day.month % 12 + 1) if day else (None, None)
                    extra = {
                        "volume": float(item.volume_facture if item.volume_facture is not None else item.consommation or 0),
                        "ancien_index": item.ancienindex, "nouvel_index": item.nouvelindex,
                        # Données du talon (vue « cartes » du modal)
                        "abonne": (point.nomabonne or "").strip() if point else "",
                        "numero_facture": item.numero_facture or f"PROV-{str(item.id)[:8]}",
                        "facture_ym": f"{fy:04d}-{fm:02d}" if fy else "",
                        "qr_payload": _build_facture_qr_payload(item, fy, fm),
                    }
                rows.append({
                    "source": source, "id": str(item.id), "idxls": (point.idxls or "").strip() if point else "",
                    "point": _point_label(point),
                    "type": point.type_point_eau.nom_type if point and point.type_point_eau else "",
                    "ouvrage": point.ouvrage.nom_ouvrage if point and point.ouvrage else "",
                    "date": day.isoformat() if day else "", "amount": float(item.montant or 0), **extra,
                })
                count += 1
                total += _money(item.montant)
            if count:
                found[source] = (count, total)
    verdict, source, n, total, gap = _verdict(expected, montant, found)
    rows.sort(key=lambda r: (r["source"] != expected, *_idxls_sort(r)))
    return {
        "kind": "pointage", "compte": entry.compte_code, "verdict": verdict,
        "expected": expected, "expected_label": SOURCE_LABELS[expected],
        "source": source, "source_label": SOURCE_LABELS[source],
        "entry": {
            "id": entry.id, "id_access": entry.id_access, "prog": entry.prog or "",
            "date": entry.date_m.isoformat() if entry.date_m else "", "description": entry.description or "",
            "montant": float(montant),
        },
        "pointable": key is not None,
        "count": n, "total": float(total), "gap": float(gap),
        "rows": rows,
    }


# --------------------------------------------------------------------------------------------------------------
# 621102 : indemnités RBF face au forfaitaire pointé du point d'eau
# --------------------------------------------------------------------------------------------------------------

def classer_recoupement(rbf_total, unites_pointees, identified=True, per_unit=PLAFOND_INDEMNITE_PAR_UNITE_FORFAIT,
                        unites_non_pointees=0):
    """
    Situation d'un point d'eau pour une année : (statut, plafond autorisé).

    * `non_identifie` : point d'eau inconnu, aucun contrôle possible ;
    * `sans_forfait`  : des indemnités sont payées mais aucun forfaitaire n'est pointé ;
    * `depasse`       : les indemnités dépassent 10 000 Ar par unité de forfait pointée ;
    * `ok`            : dans la limite.
    """
    allowed = per_unit * unites_pointees
    if not identified:
        return "non_identifie", None
    if unites_pointees <= 0:
        # Décision (2026-10-05) : on garde l'alerte même si des forfaitaires sont facturés mais pas encore pointés
        # (`unites_non_pointees` > 0). Seul le forfaitaire pointé ouvre droit à l'indemnité ; le badge et le modal
        # précisent combien de forfaitaires attendent leur pointage.
        return ("sans_forfait" if rbf_total > 0 else "ok"), allowed
    return ("depasse" if rbf_total > allowed else "ok"), allowed


def _is_pointed(value_num, value_base):
    return bool(str(value_num or "").strip() and str(value_base or "").strip())


def _forfait_summary(point_ids, years):
    """{(point_id, année): {"units", "total", "unpointed_units", "unpointed_total", "pointed_count"}}."""
    from apps.billing.models import PaiementForfaitaire

    summary = defaultdict(lambda: {
        "units": 0, "total": Decimal("0.00"), "pointed_count": 0, "unpointed_units": 0, "unpointed_total": Decimal("0.00")})
    if not point_ids:
        return summary
    rows = PaiementForfaitaire.objects.filter(
        point_eau_id__in=point_ids, date_facture__year__in=years, montant__gt=0,
    ).values("point_eau_id", "date_facture", "quantite", "montant", "numeroDiameX", "baseDiameX")
    for row in rows:
        bucket = summary[(str(row["point_eau_id"]), row["date_facture"].year)]
        units = int(row["quantite"] or 0)
        if _is_pointed(row["numeroDiameX"], row["baseDiameX"]):
            bucket["units"] += units
            bucket["total"] += _money(row["montant"])
            bucket["pointed_count"] += 1
        else:
            bucket["unpointed_units"] += units
            bucket["unpointed_total"] += _money(row["montant"])
    return summary


def _latest_point_explanations(point_ids, years):
    from apps.core.models import ExplicationEcartIndemnitePoint

    latest = {}
    if not point_ids:
        return latest
    for item in ExplicationEcartIndemnitePoint.objects.filter(
        point_eau_id__in=point_ids, annee__in=years).order_by("-created_at"):
        latest.setdefault((str(item.point_eau_id), item.annee), item)
    return latest


def _situation(counter, forfait, explanation):
    identified = bool(counter["point_id"])
    rbf_total = counter["total"]
    status, allowed = classer_recoupement(
        rbf_total, forfait["units"], identified, unites_non_pointees=forfait["unpointed_units"])
    alert = status in ("depasse", "sans_forfait")
    # Une explication couvre l'alerte tant que le montant payé n'a pas augmenté depuis sa saisie.
    explained = bool(alert and explanation and explanation.montant_paye >= rbf_total)
    return {
        "status": status, "alert": alert, "explained": explained, "needs_explanation": alert and not explained,
        "identified": identified, "year": counter["year"], "rbf_total": rbf_total, "rbf_count": counter["count"],
        "units": forfait["units"], "allowed": allowed, "per_unit": PLAFOND_INDEMNITE_PAR_UNITE_FORFAIT,
        "excess": max(rbf_total - allowed, Decimal("0.00")) if allowed is not None else Decimal("0.00"),
        "forfait_total": forfait["total"], "forfait_count": forfait["pointed_count"],
        "unpointed_units": forfait["unpointed_units"], "unpointed_total": forfait["unpointed_total"],
        "explanation": explanation if explained else None,
    }


def attach_recoupement_indemnites(entries, index):
    """
    Ajoute `entry.rbf_recoupement` (dict) aux écritures 621102 de la page ; `index` vient de
    `_rbf_indemnity_lines_by_ouvrage()`.
    """
    for entry in entries:
        entry.rbf_recoupement = None
        entry.rbf_exercice_decale = None
    counters, by_line = build_counters(index)
    wanted = {by_line[e.id] for e in entries if e.id in by_line}
    if not wanted:
        return entries
    point_ids = {counters[k]["point_id"] for k in wanted if counters[k]["point_id"]}
    years = {k[1] for k in wanted}
    forfaits = _forfait_summary(point_ids, years)
    explanations = _latest_point_explanations(point_ids, years)
    situations = {}
    for k in wanted:
        counter = counters[k]
        pid = counter["point_id"]
        forfait = forfaits[(pid, counter["year"])] if pid else forfaits.default_factory()
        situations[k] = _situation(counter, forfait, explanations.get((pid, counter["year"])))
    for entry in entries:
        if entry.id in by_line:
            entry.rbf_recoupement = situations[by_line[entry.id]]
            year = by_line[entry.id][1]
            # Indemnite d'un autre exercice que celui de la compta (libelle « RBF2 2025 » payee en 2026).
            entry.rbf_exercice_decale = year if entry.date_m and entry.date_m.year != year else None
    return entries


def recoupement_detail(entry, index):
    """Contenu du modal pour une écriture 621102 : indemnités du point d'eau, forfaitaire pointé, explications."""
    from apps.billing.models import PaiementForfaitaire, PointEau
    from apps.accounting.models import BaseDiameX
    from apps.core.models import ExplicationEcartIndemnitePoint

    counters, by_line = build_counters(index)
    if entry.id not in by_line:
        return {"kind": "recoupement", "linked": False, "entry_id": entry.id}
    key_year = by_line[entry.id]
    counter = counters[key_year]
    year, point_id = counter["year"], counter["point_id"]
    point = (PointEau.objects.select_related("type_point_eau", "ouvrage").filter(id=point_id).first()
             if point_id else None)

    # Toutes les indemnités de l'année pour ce point d'eau (ou ce libellé non résolu).
    line_meta = {}
    for ouvrage_id, lines in index.items():
        for line_id, kind, line_year, amount, pid, idxls in lines:
            if by_line.get(line_id) == key_year:
                line_meta[line_id] = (kind, amount)
    entries_by_id = {e.id: e for e in BaseDiameX.objects.filter(id__in=list(line_meta))}
    indemnities = sorted((
        {"id": line_id, "id_access": getattr(entries_by_id.get(line_id), "id_access", None),
         "date": entries_by_id[line_id].date_m.isoformat() if line_id in entries_by_id and entries_by_id[line_id].date_m else "",
         "type": kind, "amount": float(amount),
         "paid_year": entries_by_id[line_id].date_m.year if line_id in entries_by_id and entries_by_id[line_id].date_m else None,
         "description": getattr(entries_by_id.get(line_id), "description", "") or "",
         "current": line_id == entry.id}
        for line_id, (kind, amount) in line_meta.items()), key=lambda r: (r["date"], r["id"]))

    forfaits, explanations = [], []
    if point_id:
        for item in PaiementForfaitaire.objects.filter(
            point_eau_id=point_id, date_facture__year=year, montant__gt=0).order_by("date_facture", "id"):
            forfaits.append({
                "id": str(item.id), "date": item.date_facture.isoformat(), "quantite": item.quantite,
                "amount": float(item.montant), "prix_unitaire": float(item.prix_unitaire or 0),
                "pointed": _is_pointed(item.numeroDiameX, item.baseDiameX),
                "numero_diamex": str(item.numeroDiameX or "").strip(), "base_diamex": str(item.baseDiameX or "").strip(),
            })
        explanations = list(ExplicationEcartIndemnitePoint.objects.filter(
            point_eau_id=point_id, annee=year).select_related("created_by")[:10])
    forfait = {"units": 0, "total": Decimal("0.00"), "pointed_count": 0, "unpointed_units": 0, "unpointed_total": Decimal("0.00")}
    for f in forfaits:
        if f["pointed"]:
            forfait["units"] += f["quantite"] or 0
            forfait["total"] += _money(f["amount"])
            forfait["pointed_count"] += 1
        else:
            forfait["unpointed_units"] += f["quantite"] or 0
            forfait["unpointed_total"] += _money(f["amount"])
    latest = explanations[0] if explanations else None
    situation = _situation(counter, forfait, latest)
    return {
        "kind": "recoupement", "linked": True, "entry_id": entry.id, "year": year,
        "point": {
            "id": point_id, "label": _point_label(point) if point else (
                f"IDXLS {counter['idxls']} (point d'eau non retrouvé)" if counter["idxls"] else "Point d'eau non identifié"),
            "type": point.type_point_eau.nom_type if point and point.type_point_eau else "",
            "ouvrage": point.ouvrage.nom_ouvrage if point and point.ouvrage else "",
            "tarif_forfaitaire": point.tarifforfaitaire if point else None,
        },
        "situation": {
            "status": situation["status"], "alert": situation["alert"], "explained": situation["explained"],
            "needs_explanation": situation["needs_explanation"], "rbf_total": float(situation["rbf_total"]),
            "units": situation["units"], "per_unit": float(situation["per_unit"]),
            "allowed": float(situation["allowed"]) if situation["allowed"] is not None else None,
            "excess": float(situation["excess"]), "forfait_total": float(situation["forfait_total"]),
            "unpointed_units": situation["unpointed_units"], "unpointed_total": float(situation["unpointed_total"]),
        },
        "indemnities": indemnities, "forfaits": forfaits,
        "explanations": [serialize_explanation(item) for item in explanations],
    }


def serialize_explanation(item):
    from django.utils import timezone

    user = item.created_by
    employe = getattr(user, "employe", None) if user else None
    author = ((getattr(employe, "nom_affichage", "") if employe else "")
              or (user.get_full_name() or user.get_username() if user else "Utilisateur supprimé"))
    return {
        "id": str(item.id), "date": timezone.localtime(item.created_at).strftime("%d/%m/%Y %H:%M"),
        "author": author, "text": item.explication, "amount": float(item.montant_paye),
        "allowed": float(item.plafond), "motif": item.motif,
    }
