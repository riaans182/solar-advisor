# src/solar_advisor/explain/guard.py
from __future__ import annotations

import re
from dataclasses import dataclass

# Matches integers/decimals (optionally with thousands separators) and scientific
# notation, so the real magnitude is extracted ("1e3" -> 1000.0, not 1 and 3).
# Currency/% symbols and units are outside the match and ignored.
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?")

# Spelled-out numbers the model might use to smuggle an unverifiable figure past
# the digit-based extractor. We don't try to parse them — their mere presence is
# disqualifying, because the model was instructed to write numbers as digits.
_NUMBER_WORDS = frozenset(
    {
        "zero",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "eleven",
        "twelve",
        "twenty",
        "thirty",
        "forty",
        "fifty",
        "sixty",
        "seventy",
        "eighty",
        "ninety",
        "hundred",
        "thousand",
        "million",
    }
)
_WORD_TOKEN = re.compile(r"[a-zA-Z]+")


def extract_numbers(text: str) -> list[float]:
    """All numeric literals in the text, commas stripped, as floats. Scientific
    notation is resolved to its magnitude so it cannot hide a real number."""
    out: list[float] = []
    for token in _NUMBER.findall(text):
        try:
            out.append(float(token.replace(",", "")))
        except ValueError:  # pragma: no cover - regex guarantees parseable
            continue
    return out


def contains_number_word(text: str) -> bool:
    """True if the text contains a spelled-out number word (case-insensitive,
    word-boundary). Such numbers can't be traced to engine values, so their
    presence forces the guard to withhold."""
    return any(tok.lower() in _NUMBER_WORDS for tok in _WORD_TOKEN.findall(text))


@dataclass(frozen=True, slots=True)
class ProvenanceResult:
    ok: bool
    unverified: list[float]
    flagged_words: bool = False


def _is_traced(value: float, allowed: list[float], abs_floor: float, rel: float) -> bool:
    # Tolerance is keyed off the FACT (w), not max(|n|,|w|): an allowed value
    # admits only a tight band around itself, so a fabricated number cannot ride
    # a corridor between two distant facts.
    return any(abs(value - w) <= max(abs_floor, rel * abs(w)) for w in allowed)


def check_provenance(
    reply: str, allowed: list[float], *, abs_floor: float = 0.05, rel: float = 0.01
) -> ProvenanceResult:
    """Every number in the reply must trace to an allowed (engine-provided) number
    within a fact-keyed tolerance, else it is flagged. A spelled-out number word
    anywhere in the reply also fails the check, since it can't be verified. This is
    the runtime form of "the LLM never presents a number the engine didn't
    compute" (spec §8)."""
    unverified = [n for n in extract_numbers(reply) if not _is_traced(n, allowed, abs_floor, rel)]
    flagged_words = contains_number_word(reply)
    ok = not unverified and not flagged_words
    return ProvenanceResult(ok=ok, unverified=unverified, flagged_words=flagged_words)
