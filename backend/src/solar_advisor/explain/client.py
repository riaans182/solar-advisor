# src/solar_advisor/explain/client.py
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from solar_advisor.explain.context import ExplanationContext
from solar_advisor.explain.guard import check_provenance
from solar_advisor.explain.prompt import build_messages

CompleteFn = Callable[[str, str], str]

_DISABLED_MESSAGE = (
    "AI explanations are turned off. The figures above come straight from the deterministic engine."
)
_RATE_LIMITED_MESSAGE = (
    "Explanations are being requested too frequently — please wait a moment. The "
    "engine figures above are current."
)
_WITHHELD_MESSAGE = (
    "An explanation was generated but could not be verified against the engine's "
    "numbers, so it was withheld. Read the engine figures above directly."
)


@dataclass(frozen=True, slots=True)
class ExplanationResult:
    text: str
    generated: bool  # True iff the model was actually called
    guard_ok: bool
    unverified: list[float] = field(default_factory=list)


class Explainer:
    """Calls the LLM to render the engine's facts as prose, behind a kill-switch
    and a rate limit, and enforces numeric provenance: a reply that cites a number
    not in the facts is withheld (spec §8)."""

    def __init__(
        self,
        complete: CompleteFn,
        *,
        enabled: bool = True,
        min_interval_s: float = 10.0,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._complete = complete
        self._enabled = enabled
        self._min_interval_s = min_interval_s
        self._now = now
        self._last_call: float | None = None

    def explain(self, ctx: ExplanationContext) -> ExplanationResult:
        if not self._enabled:
            return ExplanationResult(text=_DISABLED_MESSAGE, generated=False, guard_ok=True)

        now = self._now()
        if self._last_call is not None and (now - self._last_call) < self._min_interval_s:
            return ExplanationResult(text=_RATE_LIMITED_MESSAGE, generated=False, guard_ok=True)
        self._last_call = now

        system, user = build_messages(ctx)
        reply = self._complete(system, user)
        result = check_provenance(reply, allowed=ctx.allowed_numbers())
        if not result.ok:
            return ExplanationResult(
                text=_WITHHELD_MESSAGE,
                generated=True,
                guard_ok=False,
                unverified=result.unverified,
            )
        return ExplanationResult(text=reply, generated=True, guard_ok=True)


def anthropic_complete(model: str, max_tokens: int = 1024) -> CompleteFn:
    """Production completion: the Anthropic SDK with a server-side key
    (ANTHROPIC_API_KEY). Imported lazily so tests never need the SDK or a key."""
    import anthropic

    client = anthropic.Anthropic()

    def _complete(system: str, user: str) -> str:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(
            block.text for block in response.content if isinstance(block, anthropic.types.TextBlock)
        )

    return _complete
