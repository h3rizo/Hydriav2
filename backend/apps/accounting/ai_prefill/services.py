"""Orchestration : hash -> cache -> garde-fou budget -> appel Claude -> persistance."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional, Union

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from .client import ApiAccountError, call_claude  # noqa: F401  (re-export)
from .models_ai_prefill import ScanExtraction
from .schema import ReceiptExtraction


class BudgetExceeded(Exception):
    """Le plafond mensuel AI_PREFILL_MONTHLY_BUDGET_USD est atteint."""


@dataclass
class ExtractionOutcome:
    status: str                       # ok | refusal | error
    extraction: Optional[ReceiptExtraction]
    record: ScanExtraction
    from_cache: bool = False
    erreur: str = ""


def _read_bytes(file_or_bytes) -> bytes:
    if isinstance(file_or_bytes, (bytes, bytearray)):
        return bytes(file_or_bytes)
    # objet fichier (Django File, open(), BytesIO...)
    try:
        file_or_bytes.seek(0)
    except Exception:  # noqa: BLE001
        pass
    return file_or_bytes.read()


def month_spend_usd(when: Optional[date] = None) -> Decimal:
    when = when or timezone.now().date()
    agg = ScanExtraction.objects.filter(
        created_at__year=when.year, created_at__month=when.month
    ).aggregate(t=Sum("cout_usd"))
    return agg["t"] or Decimal("0")


def check_budget() -> None:
    cap = Decimal(str(getattr(settings, "AI_PREFILL_MONTHLY_BUDGET_USD", 25.0) or 0))
    if cap <= 0:
        return
    spent = month_spend_usd()
    if spent >= cap:
        raise BudgetExceeded(
            f"Plafond mensuel atteint : {spent:.2f} / {cap:.2f} USD. "
            f"Relever AI_PREFILL_MONTHLY_BUDGET_USD pour continuer."
        )


def extract_receipt(
    file_or_bytes: Union[bytes, object],
    *,
    filename: str = "",
    force: bool = False,
) -> ExtractionOutcome:
    """
    Extrait les champs bruts d'un justificatif.

    - Idempotent : cache par sha256 du contenu (sauf `force=True`).
    - `check_budget()` est evalue AVANT tout appel API (les hits de cache sont gratuits).
    """
    data = _read_bytes(file_or_bytes)
    sha = hashlib.sha256(data).hexdigest()

    existing = ScanExtraction.objects.filter(file_sha256=sha).first()
    if existing and existing.status == "ok" and not force:
        return ExtractionOutcome(
            status="ok",
            extraction=ReceiptExtraction.model_validate(existing.extracted or {}),
            record=existing,
            from_cache=True,
        )

    check_budget()

    result = call_claude(data, filename)

    defaults = dict(
        source_name=(filename or "")[:500],
        model=result.model,
        status=result.status,
        stop_reason=result.stop_reason,
        extracted=(result.extraction.model_dump() if result.extraction else None),
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        tokens_cache_read=result.tokens_cache_read,
        cout_usd=Decimal(str(result.cout_usd)),
        latence_ms=result.latence_ms,
        request_id=result.request_id[:64],
        erreur=result.erreur,
    )
    record, _ = ScanExtraction.objects.update_or_create(file_sha256=sha, defaults=defaults)

    return ExtractionOutcome(
        status=result.status,
        extraction=result.extraction,
        record=record,
        from_cache=False,
        erreur=result.erreur,
    )
