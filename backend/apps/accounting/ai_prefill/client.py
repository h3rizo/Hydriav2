"""Appel de l'API Claude pour l'extraction structuree d'un justificatif."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from django.conf import settings

from .images import build_content_blocks
from .pricing import estimate_cost_usd
from .prompts import SYSTEM_PROMPT, USER_INSTRUCTION
from .schema import ReceiptExtraction

try:
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None


class AnthropicNotConfigured(Exception):
    pass


class ApiAccountError(Exception):
    """Probleme au niveau du compte Anthropic (credits epuises, clef invalide,
    permission refusee) - inutile de reessayer sur les lignes suivantes."""


_ACCOUNT_ERROR_MARKERS = ("credit balance", "plans & billing", "billing", "purchase credits")


def _is_account_error(exc) -> bool:
    code = getattr(exc, "status_code", None)
    if code in (401, 403):
        return True
    if code == 400:
        msg = str(getattr(exc, "message", "") or exc).lower()
        return any(m in msg for m in _ACCOUNT_ERROR_MARKERS)
    return False


@dataclass
class CallResult:
    status: str                       # ok | refusal | error
    extraction: Optional[ReceiptExtraction] = None
    model: str = ""
    stop_reason: str = ""
    request_id: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_cache_read: int = 0
    tokens_cache_write: int = 0
    cout_usd: float = 0.0
    latence_ms: int = 0
    erreur: str = ""
    raw: dict = field(default_factory=dict)


def _effort_supported(model: str) -> bool:
    m = model or ""
    return m.startswith("claude-opus") or m == "claude-sonnet-5" or m.startswith("claude-fable")


def _client():
    if anthropic is None:
        raise AnthropicNotConfigured("Le paquet 'anthropic' n'est pas installe (pip install anthropic).")
    key = (getattr(settings, "ANTHROPIC_API_KEY", "") or "").strip()
    if not key:
        raise AnthropicNotConfigured("ANTHROPIC_API_KEY absent (voir .env / .env.production).")
    return anthropic.Anthropic(api_key=key)


def call_claude(file_bytes: bytes, filename: str = "") -> CallResult:
    """Envoie le scan a Claude et renvoie l'extraction structuree + comptabilite tokens."""
    model = (getattr(settings, "ANTHROPIC_MODEL", "claude-opus-5") or "claude-opus-5").strip()
    effort = (getattr(settings, "ANTHROPIC_EFFORT", "low") or "").strip()

    blocks = build_content_blocks(file_bytes, filename)
    content = list(blocks) + [{"type": "text", "text": USER_INSTRUCTION}]

    output_config: dict = {}
    if effort and _effort_supported(model):
        output_config["effort"] = effort

    client = _client()
    kwargs = dict(
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
        output_format=ReceiptExtraction,
    )
    if output_config:
        kwargs["output_config"] = output_config

    t0 = time.monotonic()
    try:
        resp = client.messages.parse(**kwargs)
    except anthropic.APIStatusError as exc:  # 4xx / 5xx
        if _is_account_error(exc):
            raise ApiAccountError(str(getattr(exc, "message", "") or exc)) from exc
        return CallResult(status="error", model=model,
                          latence_ms=int((time.monotonic() - t0) * 1000),
                          erreur=f"{type(exc).__name__} {getattr(exc, 'status_code', '')}: {exc}")
    except anthropic.APIError as exc:
        return CallResult(status="error", model=model,
                          latence_ms=int((time.monotonic() - t0) * 1000),
                          erreur=f"{type(exc).__name__}: {exc}")

    latence_ms = int((time.monotonic() - t0) * 1000)
    usage = getattr(resp, "usage", None)
    tin = getattr(usage, "input_tokens", 0) or 0
    tout = getattr(usage, "output_tokens", 0) or 0
    tcr = getattr(usage, "cache_read_input_tokens", 0) or 0
    tcw = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cost = estimate_cost_usd(model, tin, tout, tcr, tcw)
    req_id = getattr(resp, "_request_id", "") or ""
    stop = getattr(resp, "stop_reason", "") or ""

    if stop == "refusal":
        details = getattr(resp, "stop_details", None)
        return CallResult(
            status="refusal", model=model, stop_reason=stop, request_id=req_id,
            tokens_in=tin, tokens_out=tout, tokens_cache_read=tcr, tokens_cache_write=tcw,
            cout_usd=cost, latence_ms=latence_ms,
            erreur=f"refus ({getattr(details, 'category', None)}): {getattr(details, 'explanation', '')}",
        )

    extraction = resp.parsed_output
    if extraction is None:
        text = next((b.text for b in resp.content if getattr(b, "type", "") == "text"), "")
        return CallResult(
            status="error", model=model, stop_reason=stop, request_id=req_id,
            tokens_in=tin, tokens_out=tout, tokens_cache_read=tcr, tokens_cache_write=tcw,
            cout_usd=cost, latence_ms=latence_ms,
            erreur="Sortie non parsable en ReceiptExtraction",
            raw={"text": text[:2000]},
        )

    return CallResult(
        status="ok", extraction=extraction, model=model, stop_reason=stop, request_id=req_id,
        tokens_in=tin, tokens_out=tout, tokens_cache_read=tcr, tokens_cache_write=tcw,
        cout_usd=cost, latence_ms=latence_ms,
        raw={"extracted": extraction.model_dump()},
    )
