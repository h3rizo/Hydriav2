"""AJAX de la liste des écritures : détail du pointage (748411 / 707401) et recoupement des indemnités (621102)."""
import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from . import pointage_ecritures as pe

EXPLICATION_LONGUEUR_MIN = 10
EXPLICATION_LONGUEUR_MAX = 2000


def _get_entry(request, entry_id):
    """Écriture visible par l'utilisateur (même périmètre que la liste), ou None."""
    from .views import _exclude_sensitive_diamex_lines_for_non_privileged, _get_diamex_entries_scope_queryset

    qs = _get_diamex_entries_scope_queryset(request)
    qs = _exclude_sensitive_diamex_lines_for_non_privileged(qs, request.user)
    return qs.filter(id=entry_id).first()


def _can_see_indemnities(user):
    """Les indemnités nomment des bénéficiaires : réservées aux utilisateurs internes (pas aux comptes clients)."""
    return not bool(getattr(user, "client", None)) or user.is_staff


@login_required
@require_GET
def entry_pointage_detail(request, entry_id):
    entry = _get_entry(request, entry_id)
    if entry is None:
        return JsonResponse({"success": False, "error": "Écriture introuvable."}, status=404)
    if entry.compte_code in pe.EXPECTED_SOURCE:
        return JsonResponse({"success": True, **pe.pointage_detail(entry)})
    if entry.compte_code == pe.COMPTE_INDEMNITES:
        if not _can_see_indemnities(request.user):
            return JsonResponse({"success": False, "error": "Accès réservé aux utilisateurs internes."}, status=403)
        from apps.core.views_ouvrage_interventions import _rbf_indemnity_lines_by_ouvrage
        return JsonResponse({"success": True, **pe.recoupement_detail(entry, _rbf_indemnity_lines_by_ouvrage())})
    return JsonResponse({"success": False, "error": "Aucun pointage pour ce compte."}, status=400)


@login_required
@require_POST
def entry_explication_indemnite(request, entry_id):
    """Enregistre l'explication d'un point d'eau dont les indemnités RBF de l'année sont en alerte."""
    from apps.core.models import ExplicationEcartIndemnitePoint
    from apps.core.views_ouvrage_interventions import _rbf_indemnity_lines_by_ouvrage

    if not _can_see_indemnities(request.user):
        return JsonResponse({"success": False, "error": "Accès réservé aux utilisateurs internes."}, status=403)
    entry = _get_entry(request, entry_id)
    if entry is None or entry.compte_code != pe.COMPTE_INDEMNITES:
        return JsonResponse({"success": False, "error": "Écriture introuvable."}, status=404)
    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Données JSON invalides."}, status=400)
    text = str(data.get("explication") or "").strip()
    if len(text) < EXPLICATION_LONGUEUR_MIN:
        return JsonResponse({
            "success": False, "error": f"L'explication doit contenir au moins {EXPLICATION_LONGUEUR_MIN} caractères."}, status=400)
    if len(text) > EXPLICATION_LONGUEUR_MAX:
        return JsonResponse({
            "success": False, "error": f"L'explication ne doit pas dépasser {EXPLICATION_LONGUEUR_MAX} caractères."}, status=400)

    entry.rbf_recoupement = None
    pe.attach_recoupement_indemnites([entry], _rbf_indemnity_lines_by_ouvrage())
    situation = entry.rbf_recoupement
    if not situation or not situation["identified"]:
        return JsonResponse({"success": False, "error": "Point d'eau non identifié : rien à expliquer ici."}, status=400)
    if not situation["alert"]:
        return JsonResponse({"success": False, "error": "Aucune alerte pour ce point d'eau : pas d'explication nécessaire."}, status=400)

    from .indemnites_points import build_counters
    counters, by_line = build_counters(_rbf_indemnity_lines_by_ouvrage())
    point_id = counters[by_line[entry.id]]["point_id"]
    item = ExplicationEcartIndemnitePoint.objects.create(
        point_eau_id=point_id, annee=situation["year"], motif=situation["status"],
        montant_paye=situation["rbf_total"], plafond=situation["allowed"] or 0,
        unites_forfait=situation["units"], explication=text, created_by=request.user)
    return JsonResponse({"success": True, "explication": pe.serialize_explanation(item)})
