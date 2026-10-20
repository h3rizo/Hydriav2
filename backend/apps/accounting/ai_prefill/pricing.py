"""Tarifs API Claude (USD / million de tokens) - cache 2026-06, cf. skill claude-api."""
from __future__ import annotations

# (input, output) par million de tokens
_RATES = {
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-fable-5-1": (10.0, 50.0),
    "claude-fable-5": (10.0, 50.0),
}
_DEFAULT = (5.0, 25.0)  # repli prudent : tarif Opus

# multiplicateurs cache
_CACHE_READ = 0.1
_CACHE_WRITE = 1.25


def rates_for(model: str) -> tuple[float, float]:
    return _RATES.get(model, _DEFAULT)


def estimate_cost_usd(
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float:
    r_in, r_out = rates_for(model)
    cost = (
        input_tokens * r_in
        + output_tokens * r_out
        + cache_read_tokens * r_in * _CACHE_READ
        + cache_write_tokens * r_in * _CACHE_WRITE
    ) / 1_000_000
    return round(cost, 6)
