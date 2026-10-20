"""
Contrôle d'une demande d'avance pour une indemnité RBF (point d'eau par point d'eau).

Une avance n'est autorisée que si les trois contrôles passent :

  1. pointé    : l'indemnité est couverte par des paiements forfaitaires POINTÉS (numeroDiameX renseigné) de
                 l'exercice, à raison de 10 000 Ar par période de 3 mois pointée (même règle que le widget) ;
  2. plafond   : le cumul de l'exercice ne dépasse pas le plafond annuel par point d'eau public (40 000 Ar) ;
  3. doublon   : le point n'a pas déjà une indemnité RBF pour la même période de 3 mois (trimestre civil) de
                 l'exercice, que ce soit dans DiameX (621102) ou en avance pas encore retournée.

Le cumul « déjà utilisé » = indemnités déjà payées dans DiameX + avances RBF non retournées à la caissière (une
avance retournée est comptabilisée dans DiameX : la compter deux fois bloquerait à tort).
"""
from decimal import Decimal

import pytz
from django.db.models import Q

from apps.core import widget_rbf

TZ_MADAGASCAR = pytz.timezone("Indian/Antananarivo")
DESIGNATION_RBF_Q = Q(designation__nom__icontains="indemnit") & Q(designation__nom__icontains="RBF")


def trimestre(d):
    """Trimestre civil (1-4) d'une date."""
    return (d.month - 1) // 3 + 1


def _local_date(dt):
    if dt is None:
        return None
    if hasattr(dt, "astimezone") and getattr(dt, "tzinfo", None):
        dt = dt.astimezone(TZ_MADAGASCAR)
    return dt.date() if hasattr(dt, "date") else dt


def avances_en_cours(point, annee, exclude_ids=()):
    """Avances RBF du point pour l'exercice, pas encore retournées : [(montant, date du planning)]."""
    from apps.planning.models import PlanningDetail

    qs = (
        PlanningDetail.objects.filter(DESIGNATION_RBF_Q, point_eau=point, retour=False)
        .exclude(Q(numeroDiameX__isnull=False))
        .exclude(id__in=list(exclude_ids))
        .select_related("planning")
    )
    result = []
    for detail in qs:
        d = _local_date(getattr(detail.planning, "date", None))
        if d and d.year == annee:
            result.append((Decimal(detail.montant or 0), d))
    return result


def lignes_diamex(point, annee, cache=None):
    """Indemnités RBF déjà payées pour le point sur l'exercice : [(montant, date du mouvement ou None)]."""
    from apps.accounting.models import BaseDiameX
    from apps.core.views_ouvrage_interventions import _rbf_indemnity_lines_by_ouvrage

    if cache is not None:
        if "lines" not in cache:
            cache["lines"] = _rbf_indemnity_lines_by_ouvrage()
        by_ouvrage = cache["lines"]
    else:
        by_ouvrage = _rbf_indemnity_lines_by_ouvrage()
    pid = str(point.id)
    lines = [line for line in by_ouvrage.get(str(point.ouvrage_id), []) if line[4] == pid and line[2] == annee]
    dates = dict(BaseDiameX.objects.filter(id__in=[l[0] for l in lines]).values_list("id", "date_m"))
    return [(l[3], _local_date(dates.get(l[0]))) for l in lines]


def evaluer(point, montant, date_ref, exclude_ids=(), extra_en_cours=(), cache=None):
    """
    Verdict pour une avance de `montant` Ar sur `point`, rattachée à la date `date_ref` (date du planning visé).

    `exclude_ids` : lignes d'avance à ne pas compter comme « déjà avancées » (celles que l'on contrôle en lot) ;
    `extra_en_cours` : [(montant, date)] des lignes du lot déjà autorisées avant celle-ci.
    Retourne {"autorise": bool, "controles": [{code, ok, titre, detail}], "chiffres": {...}}.
    """
    from apps.core.views_ouvrage_interventions import PLAFOND_INDEMNITE_PAR_POINT_EAU_PUBLIC

    montant = Decimal(montant or 0)
    annee = date_ref.year
    t = trimestre(date_ref)

    ck = ("periodes", str(point.id), annee)
    if cache is not None and ck in cache:
        periodes = cache[ck]
    else:
        periodes = widget_rbf.effective_payment_counts({str(point.id)}, annee).get(str(point.id), 0)
        if cache is not None:
            cache[ck] = periodes
    capacite = widget_rbf.INDEMNITE_PAR_PAIEMENT_EFFECTIF * periodes
    payees = lignes_diamex(point, annee, cache)
    en_cours = avances_en_cours(point, annee, exclude_ids) + list(extra_en_cours)
    deja_payee = sum((m for m, _ in payees), Decimal("0"))
    deja_avancee = sum((m for m, _ in en_cours), Decimal("0"))
    utilise = deja_payee + deja_avancee
    plafond = PLAFOND_INDEMNITE_PAR_POINT_EAU_PUBLIC

    def ar(v):
        return f"{Decimal(v):,.0f}".replace(",", " ") + " Ar"

    controles = []
    if montant <= 0:
        controles.append({"code": "montant", "ok": False, "titre": "Montant",
                          "detail": "Le montant demandé doit être positif."})

    reste = capacite - utilise
    controles.append({
        "code": "pointe", "ok": periodes > 0 and montant <= reste, "titre": "Paiement forfaitaire pointé",
        "detail": (
            f"Aucun paiement forfaitaire pointé en {annee} pour ce point d'eau : aucune avance possible."
            if periodes == 0 else
            f"{periodes} période{'s' if periodes > 1 else ''} de 3 mois pointée{'s' if periodes > 1 else ''} en {annee} "
            f"= {ar(capacite)} autorisés ; déjà utilisés {ar(utilise)} (payés {ar(deja_payee)} + avancés "
            f"{ar(deja_avancee)}) ; reste {ar(max(reste, 0))}"
            + ("" if montant <= reste else f" : la demande de {ar(montant)} dépasse de {ar(montant - reste)}.")
        ),
    })
    controles.append({
        "code": "plafond", "ok": utilise + montant <= plafond, "titre": "Plafond annuel",
        "detail": f"Cumul {ar(utilise)} + demande {ar(montant)} = {ar(utilise + montant)} pour un plafond de {ar(plafond)}.",
    })

    doublons = [("DiameX", d) for _, d in payees if d and d.year == annee and trimestre(d) == t]
    doublons += [("avance en cours", d) for _, d in en_cours if trimestre(d) == t]
    controles.append({
        "code": "doublon", "ok": not doublons, "titre": "Pas de doublon",
        "detail": (
            f"Aucune indemnité RBF déjà enregistrée pour le trimestre T{t} {annee}."
            if not doublons else
            f"Ce point a déjà une indemnité RBF pour T{t} {annee} : "
            + ", ".join(f"{src} du {d.strftime('%d/%m/%Y')}" for src, d in doublons) + "."
        ),
    })
    return {
        "autorise": all(c["ok"] for c in controles),
        "controles": controles,
        "chiffres": {
            "annee": annee, "trimestre": t, "periodes_pointees": periodes, "capacite": capacite,
            "deja_payee": deja_payee, "deja_avancee": deja_avancee, "reste": max(reste, Decimal("0")),
        },
    }


# ---------------------------------------------------------------------------------------------------------------
# Contrôle en lot : les lignes d'avance « Indemnité RBF » de PlanningDetail, évaluées d'un coup
# ---------------------------------------------------------------------------------------------------------------
FENETRE_JOURS = 45  # seules les lignes dont le planning date de moins de 45 jours (ou à venir) sont contrôlées


def lignes_a_controler(jours=FENETRE_JOURS):
    """Lignes d'avance RBF pas encore traitées par la caissière, dans la fenêtre de contrôle."""
    from datetime import datetime, timedelta

    from django.utils import timezone

    from apps.planning.models import PlanningDetail

    today = timezone.now().astimezone(TZ_MADAGASCAR).date()
    start = TZ_MADAGASCAR.localize(datetime(today.year, today.month, today.day)) - timedelta(days=jours)
    return list(
        PlanningDetail.objects.filter(
            DESIGNATION_RBF_Q, retour=False, livraison=False, planning__estvalide=True, planning__date__gte=start,
        ).filter(Q(numeroDiameX__isnull=True)).select_related(
            "planning", "planning__employe", "planning__ouvrage", "point_eau", "designation",
        )
    )


def evaluer_lot(details):
    """
    {detail.id: verdict} pour un lot de lignes. Ordre déterministe (date du planning, création, id) : une ligne
    autorisée compte pour les suivantes du même point, une ligne refusée ne compte pas. Une ligne sans point d'eau
    ne peut pas être rattachée à un paiement pointé : refusée.
    """
    from collections import defaultdict

    ordered = sorted(details, key=lambda d: (d.planning.date, d.created_at, str(d.id)))
    ids = {d.id for d in ordered}
    cache, acceptees, result = {}, defaultdict(list), {}
    for d in ordered:
        date_ref = _local_date(d.planning.date)
        if not d.point_eau_id:
            result[d.id] = {"autorise": False, "chiffres": {}, "controles": [{
                "code": "point", "ok": False, "titre": "Point d'eau",
                "detail": "Aucun point d'eau sur la ligne : impossible de la rattacher à un paiement pointé."}]}
            continue
        verdict = evaluer(d.point_eau, d.montant, date_ref, exclude_ids=ids,
                          extra_en_cours=acceptees[d.point_eau_id], cache=cache)
        result[d.id] = verdict
        if verdict["autorise"]:
            acceptees[d.point_eau_id].append((Decimal(d.montant or 0), date_ref))
    return result


def ids_refuses(detail_ids=None):
    """Ids des lignes d'avance RBF refusées par le contrôle (optionnellement restreints à `detail_ids`)."""
    details = lignes_a_controler()
    verdicts = evaluer_lot(details)
    wanted = None if detail_ids is None else {str(i) for i in detail_ids}
    return {d.id for d in details
            if not verdicts[d.id]["autorise"] and (wanted is None or str(d.id) in wanted)}
