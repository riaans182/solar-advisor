# src/solar_advisor/explain/guard.py
from __future__ import annotations

import re
from dataclasses import dataclass

# Matches integers/decimals, optionally with thousands separators. Currency/%
# symbols and units are outside the match and ignored.
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def extract_numbers(text: str) -> list[float]:
    """All numeric literals in the text, commas stripped, as floats."""
    out: list[float] = []
    for token in _NUMBER.findall(text):
        try:
            out.append(float(token.replace(",", "")))
        except ValueError:  # pragma: no cover - regex guarantees parseable
            continue
    return out


@dataclass(frozen=True, slots=True)
class ProvenanceResult:
    ok: bool
    unverified: list[float]


def _is_traced(value: float, allowed: list[float], abs_floor: float, rel: float) -> bool:
    return any(abs(value - w) <= max(abs_floor, rel * max(abs(value), abs(w))) for w in allowed)


def check_provenance(
    reply: str, allowed: list[float], *, abs_floor: float = 0.5, rel: float = 0.02
) -> ProvenanceResult:
    """Every number in the reply must trace to an allowed (engine-provided) number
    within tolerance, else it is flagged. This is the runtime form of "the LLM
    never presents a number the engine didn't compute" (spec §8)."""
    unverified = [n for n in extract_numbers(reply) if not _is_traced(n, allowed, abs_floor, rel)]
    return ProvenanceResult(ok=not unverified, unverified=unverified)
