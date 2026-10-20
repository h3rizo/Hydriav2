"""
Anomalies d'indemnités RBF par point d'eau, pour les tuiles « Forfaitaire » du widget.

Deux contrôles, sur l'année en cours et pour les points d'eau identifiés dans le libellé DiameX (compte 621102) :
  - dépassement du plafond annuel (40 000 Ar par point d'eau, même règle que la page des ouvrages) ;
  - indemnité sans paiement effectif : le RBF de l'année dépasse 10 000 Ar x le nombre de périodes de 3 mois payées
    de façon effective (numeroDiameX renseigné, somme des quantités) sur l'année : un paiement de 4 x le tarif
    forfaitaire (quantité 4) justifie donc 40 000 Ar. Sans aucun paiement effectif, tout RBF est anormal.
"""
from collections import defaultdict
from decimal import Decimal

INDEMNITE_PAR_PAIEMENT_EFFECTIF = Decimal("10000")


def totals_by_point(lines_by_ouvrage, year, allowed_point_ids):
    """{point_id: total RBF de l'année} pour les points d'eau autorisés (lignes sans point identifié ignorées)."""
    totals = defaultdict(lambda: Decimal("0.00"))
    for lines in lines_by_ouvrage.values():
        for _line_id, _kind, line_year, amount, point_id, _idxls in lines:
            if line_year == year and point_id and point_id in allowed_point_ids:
                totals[point_id] += amount
    return dict(totals)


def periods_of(quantite):
    """Périodes de 3 mois payées par un paiement forfaitaire : sa quantité (au moins 1 pour un paiement effectif)."""
    return max(int(quantite or 0), 1)


def effective_payment_counts(point_ids, year):
    """
    {point_id: périodes de 3 mois payées de façon effective (numeroDiameX renseigné) sur l'année}.

    Un paiement de 4 x le tarif forfaitaire (quantité 4) compte pour 4 périodes, donc justifie 40 000 Ar de RBF.
    """
    from django.db.models import Q

    from apps.billing.models import PaiementForfaitaire

    if not point_ids:
        return {}
    rows = (
        PaiementForfaitaire.objects
        .filter(point_eau_id__in=list(point_ids), numeroDiameX__isnull=False)
        .exclude(numeroDiameX__exact="")
        .filter(Q(date_paiement__year=year) | Q(date_paiement__isnull=True, date_facture__year=year))
        .order_by()
        .values_list("point_eau_id", "quantite")
    )
    counts = defaultdict(int)
    for point_id, quantite in rows:
        counts[str(point_id)] += periods_of(quantite)
    return dict(counts)


def classify(totals, payment_counts, cap_per_point):
    """(points au-dessus du plafond, points sans paiement effectif suffisant), triés par excédent décroissant."""
    over_cap, unpaid = [], []
    for point_id, total in totals.items():
        paid = payment_counts.get(point_id, 0)
        if total > cap_per_point:
            over_cap.append({"point_id": point_id, "total": total, "paid": paid,
                             "excess": total - cap_per_point})
        justified = INDEMNITE_PAR_PAIEMENT_EFFECTIF * paid
        if total > justified:
            unpaid.append({"point_id": point_id, "total": total, "paid": paid,
                           "excess": total - justified})
    key = lambda item: -item["excess"]
    return sorted(over_cap, key=key), sorted(unpaid, key=key)


def compute(allowed_point_ids, year):
    """Point d'entrée : (over_cap, unpaid) pour l'année, sur l'ensemble de points d'eau autorisés (ids en str)."""
    from apps.core.views_ouvrage_interventions import (
        PLAFOND_INDEMNITE_PAR_POINT_EAU_PUBLIC,
        _rbf_indemnity_lines_by_ouvrage,
    )

    totals = totals_by_point(_rbf_indemnity_lines_by_ouvrage(), year, allowed_point_ids)
    counts = effective_payment_counts(set(totals), year)
    return classify(totals, counts, PLAFOND_INDEMNITE_PAR_POINT_EAU_PUBLIC)
