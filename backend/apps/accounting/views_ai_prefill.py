"""
Phase 4 - endpoint de pre-remplissage des ecritures a partir d'un justificatif.

POST /comptabilite/justificatifs/scan/
  - multipart : champ fichier `scan` (+ `base_id` optionnel)   -> extraction Claude + retrieval
  - JSON      : {"texte": "...", "base_id": "..."}              -> retrieval seul (aucun appel API)

Reponse : JSON de suggestions (cf. pipeline.Suggestion.as_dict()).
"""
import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .ai_prefill.pipeline import suggest_from_scan, suggest_from_text

_MAX_TEXTE = 20000


@login_required
@require_http_methods(["POST"])
def justificatif_scan(request):
    base_id = (request.POST.get("base_id") or request.GET.get("base_id") or "").strip() or None

    fichier = request.FILES.get("scan") or request.FILES.get("fichier") or request.FILES.get("file")
    if fichier is not None:
        data = fichier.read()
        if not data:
            return JsonResponse({"status": "error", "error": "Fichier vide"}, status=400)
        sugg = suggest_from_scan(data, filename=getattr(fichier, "name", "") or "scan", base_id=base_id)
        code = 200 if sugg.status == "ok" else 200  # erreurs metier -> 200 + status
        return JsonResponse(sugg.as_dict(), status=code)

    # chemin texte (JSON ou form)
    texte = ""
    if request.content_type and "application/json" in request.content_type:
        try:
            payload = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"status": "error", "error": "JSON invalide"}, status=400)
        texte = (payload.get("texte") or payload.get("description") or "").strip()
        base_id = (payload.get("base_id") or base_id or "") or None
    else:
        texte = (request.POST.get("texte") or request.POST.get("description") or "").strip()

    if not texte:
        return JsonResponse(
            {"status": "error", "error": "Fournir un fichier `scan` ou un champ `texte`."},
            status=400,
        )

    sugg = suggest_from_text(texte[:_MAX_TEXTE], base_id=base_id)
    return JsonResponse(sugg.as_dict(), status=200)
