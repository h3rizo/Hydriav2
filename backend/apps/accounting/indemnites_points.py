"""
Compteur d'indemnités RBF (compte 621102) point d'eau par point d'eau, pour la liste des écritures.

Chaque paiement est rattaché à son point d'eau (identifié par l'extracteur de libellé : IDXLS + ouvrage) et on
cumule, pour chaque point d'eau et chaque année, ce qui a été payé. Le plafond est de 40 000 Ar par point d'eau
public et par an (même règle que la tuile des cartes ouvrage).

Le cumul porte sur TOUS les paiements de l'année pour ce point d'eau, quels que soient les filtres de la page
(un filtre sur un mois ne doit pas faire croire qu'un point d'eau est sous le plafond).
"""
import re
from decimal import Decimal

# Année d'exercice écrite dans le libellé, juste après le type d'indemnité : « Indemnité RBF2 2025 », « BF3_2024 »,
# « RBF7_2025 et 2024 ». Le chiffre collé au type est le n° de point (IDXLS), pas une année ; les montants
# (« _Fft_20000_ ») ne suivent jamais directement le type, ils ne sont donc pas pris pour une année.
_ANNEES_APRES_TYPE = re.compile(
    r'(?:RBF|RB|BF|PPMH)\d{0,3}[\s_]+((?:20\d{2})(?:\s*(?:et|&|,|/|-)\s*20\d{2})*)(?!\d)', re.IGNORECASE)
_ANNEE = re.compile(r'20\d{2}')


def annee_exercice(description, annee_paiement):
    """
    Année à laquelle une indemnité se rattache : celle du libellé quand elle diffère de l'année de la compta
    (indemnité de 2025 payée en 2026), sinon l'année du paiement.

    Libellé multi-années (« RBF7_2025 et 2024 ») : on retient la plus récente. Les années absurdes (plus de 5 ans
    avant, ou plus d'un an après le paiement) sont ignorées ; s'il n'en reste aucune, l'année du paiement est gardée.
    """
    if annee_paiement is None:
        return annee_paiement
    match = _ANNEES_APRES_TYPE.search(str(description or ''))
    if not match:
        return annee_paiement
    years = [int(y) for y in _ANNEE.findall(match.group(1))
             if annee_paiement - 5 <= int(y) <= annee_paiement + 1]
    return max(years) if years else annee_paiement


def counter_key(ouvrage_id, point_id, idxls):
    """Clé stable d'un point d'eau : id réel, sinon (ouvrage, IDXLS du libellé), sinon « sans point » par ouvrage."""
    if point_id:
        return f"pe:{point_id}"
    if idxls:
        return f"idxls:{ouvrage_id}:{idxls}"
    return f"none:{ouvrage_id}"


def build_counters(index):
    """
    index : {ouvrage_id: [(id ligne, type, année, montant, id point, idxls), ...]}
    -> (compteurs {(clé, année): {...}}, ligne -> (clé, année))
    """
    counters, by_line = {}, {}
    for ouvrage_id, lines in index.items():
        for line_id, _kind, year, amount, point_id, idxls in lines:
            if year is None:
                continue
            key = counter_key(ouvrage_id, point_id, idxls)
            counter = counters.setdefault((key, year), {
                "key": key, "year": year, "ouvrage_id": ouvrage_id, "point_id": point_id, "idxls": idxls,
                "total": Decimal("0.00"), "count": 0, "identified": not key.startswith("none:"),
            })
            counter["total"] += amount
            counter["count"] += 1
            by_line[line_id] = (key, year)
    return counters, by_line


def line_ids_for_point(index, key, year):
    """Ids des écritures rattachées à un point d'eau (clé de compteur) pour une année : filtre du tableau."""
    _, by_line = build_counters(index)
    return [line_id for line_id, counter_key_year in by_line.items() if counter_key_year == (key, int(year))]


def cap_status(counter, per_point):
    """Situation d'un compteur face au plafond (sans objet pour un paiement dont le point d'eau est inconnu)."""
    if not counter["identified"]:
        return {"cap": None, "over": False, "excess": Decimal("0.00")}
    over = counter["total"] > per_point
    return {"cap": per_point, "over": over, "excess": max(counter["total"] - per_point, Decimal("0.00"))}


def _labels(counters):
    """Libellés (ouvrage, point d'eau) en deux requêtes pour l'ensemble des compteurs affichés."""
    from apps.billing.models import PointEau
    from apps.organization.models import Ouvrage

    point_ids = {c["point_id"] for c in counters if c["point_id"]}
    ouvrage_ids = {c["ouvrage_id"] for c in counters}
    points = {
        str(p.id): p for p in PointEau.objects.filter(id__in=point_ids).select_related("type_point_eau")
    } if point_ids else {}
    ouvrages = {
        str(o.id): o.nom_ouvrage for o in Ouvrage.objects.filter(id__in=ouvrage_ids).only("id", "nom_ouvrage")
    } if ouvrage_ids else {}
    return points, ouvrages


def _describe(counter, points, ouvrages, per_point):
    point = points.get(counter["point_id"]) if counter["point_id"] else None
    idxls = (getattr(point, "idxls", "") or counter["idxls"] or "").strip()
    if point:
        name = (point.nomabonne or point.code_point_eau or "").strip()
        label = f"IDXLS {idxls} — {name}" if idxls and name else (name or (f"IDXLS {idxls}" if idxls else "Point d'eau"))
    elif counter["idxls"]:
        label = f"IDXLS {counter['idxls']} (point d'eau non retrouvé)"
    else:
        label = "Point d'eau non identifié"
    status = cap_status(counter, per_point)
    return {
        "key": counter["key"],
        "year": counter["year"],
        "ouvrage": ouvrages.get(counter["ouvrage_id"], ""),
        "point_label": label,
        "point_type": getattr(getattr(point, "type_point_eau", None), "nom_type", "") or "",
        "identified": counter["identified"],
        "count": counter["count"],
        "total": counter["total"],
        **status,
    }


def build_context(filtered_line_ids, page_entries, index, per_point):
    """
    Compteurs pour la page : rattache `rbf_counter` à chaque écriture de la page et renvoie le tableau récapitulatif
    des points d'eau concernés par les écritures filtrées.

    filtered_line_ids : ids de toutes les écritures filtrées ; page_entries : celles de la page affichée.
    """
    counters, by_line = build_counters(index)
    wanted = {by_line[i] for i in filtered_line_ids if i in by_line}
    for entry in page_entries:
        if entry.id in by_line:
            wanted.add(by_line[entry.id])
    if not wanted:
        return {"rows": [], "summary": {"points": 0, "over": 0, "excess": Decimal("0.00"),
                                        "unidentified_total": Decimal("0.00")}}

    points, ouvrages = _labels([counters[k] for k in wanted])
    described = {k: _describe(counters[k], points, ouvrages, per_point) for k in wanted}

    for entry in page_entries:
        entry.rbf_counter = described.get(by_line.get(entry.id))

    rows = sorted(
        described.values(),
        key=lambda r: (not r["over"], -float(r["excess"]), not r["identified"], -r["year"],
                       -float(r["total"]), r["ouvrage"], r["point_label"]),
    )
    identified = [r for r in rows if r["identified"]]
    return {
        "rows": rows,
        "summary": {
            "points": len(identified),
            "over": sum(1 for r in identified if r["over"]),
            "excess": sum((r["excess"] for r in identified), Decimal("0.00")),
            "unidentified_total": sum((r["total"] for r in rows if not r["identified"]), Decimal("0.00")),
        },
    }
