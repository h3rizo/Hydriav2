"""Tache Celery : extraction IA d'un justificatif deja copie sur le serveur."""
from __future__ import annotations

from celery import shared_task


@shared_task(name="apps.accounting.ai_prefill.extract_basediamex_scan", bind=True, max_retries=2)
def extract_basediamex_scan(self, basediamex_id: int, force: bool = False):
    """
    Lance l'extraction pour la copie serveur (`scan_importe`) d'une ligne BaseDiameX.
    Retourne un petit dict de statut (le detail est persiste dans ScanExtraction).
    """
    from apps.accounting.models import BaseDiameX

    from .services import ApiAccountError, BudgetExceeded, extract_receipt

    entry = BaseDiameX.objects.filter(pk=basediamex_id).first()
    if entry is None:
        return {"ok": False, "erreur": f"BaseDiameX {basediamex_id} introuvable"}

    name = getattr(entry.scan_importe, "name", "") or ""
    if not name:
        return {"ok": False, "erreur": "Pas de scan_importe pour cette ligne"}

    try:
        with entry.scan_importe.open("rb") as fh:
            data = fh.read()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "erreur": f"Lecture scan impossible : {exc}"}

    try:
        outcome = extract_receipt(data, filename=name, force=force)
    except BudgetExceeded as exc:
        return {"ok": False, "erreur": str(exc), "budget": True}
    except ApiAccountError as exc:
        return {"ok": False, "erreur": str(exc), "compte": True}  # pas de retry : credits/clef
    except Exception as exc:  # noqa: BLE001
        raise self.retry(exc=exc, countdown=30)

    return {
        "ok": outcome.status == "ok",
        "status": outcome.status,
        "from_cache": outcome.from_cache,
        "extraction_id": str(outcome.record.id),
        "cout_usd": float(outcome.record.cout_usd),
    }
