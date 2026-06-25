# tests/test_explain_client.py
from solar_advisor.explain.client import (
    _UNAVAILABLE_MESSAGE,
    Explainer,
    ExplanationResult,
)
from tests.test_explain_context import _dashboard_data

WITHHELD_MARKER = "could not be verified"


def _ctx():
    from solar_advisor.explain.context import build_context

    return build_context(_dashboard_data())


def test_kill_switch_returns_canned_without_calling_model():
    calls = []

    def fake_complete(system, user):
        calls.append((system, user))
        return "should not be called"

    explainer = Explainer(complete=fake_complete, enabled=False, min_interval_s=0.0)
    result = explainer.explain(_ctx())
    assert isinstance(result, ExplanationResult)
    assert result.generated is False
    assert calls == []  # model never invoked


def test_clean_reply_passes_guard_and_is_returned():
    def fake_complete(system, user):
        # Uses only numbers present in the facts.
        return "Your battery grid-charges to 100% overnight, importing 13.0 kWh at R46.28."

    explainer = Explainer(complete=fake_complete, enabled=True, min_interval_s=0.0)
    result = explainer.explain(_ctx())
    assert result.generated is True
    assert result.guard_ok is True
    assert "46.28" in result.text


def test_fabricated_number_is_withheld():
    def fake_complete(system, user):
        return "You will save R512 every month by switching this off."  # 512 not in facts

    explainer = Explainer(complete=fake_complete, enabled=True, min_interval_s=0.0)
    result = explainer.explain(_ctx())
    assert result.generated is True
    assert result.guard_ok is False
    assert 512.0 in result.unverified
    assert WITHHELD_MARKER in result.text.lower()
    assert "512" not in result.text  # the hallucinating reply is not shown


def test_rate_limit_blocks_second_call_within_interval():
    clock = [100.0]

    def fake_complete(system, user):
        return "Grid-charging at night is pure cost here."  # no numbers

    explainer = Explainer(
        complete=fake_complete, enabled=True, min_interval_s=10.0, now=lambda: clock[0]
    )
    first = explainer.explain(_ctx())
    assert first.generated is True
    clock[0] = 105.0  # 5s later, inside the 10s window
    second = explainer.explain(_ctx())
    assert second.generated is False
    assert "too frequently" in second.text.lower() or "rate" in second.text.lower()


def test_completion_failure_degrades_gracefully():
    def boom(s, u):
        raise RuntimeError("anthropic down")

    explainer = Explainer(complete=boom, enabled=True, min_interval_s=0.0)
    result = explainer.explain(_ctx())  # must not raise
    assert result.generated is False
    assert result.guard_ok is True
    assert result.text == _UNAVAILABLE_MESSAGE


def test_empty_reply_degrades_gracefully():
    def blank(s, u):
        return "   \n  "  # whitespace-only

    explainer = Explainer(complete=blank, enabled=True, min_interval_s=0.0)
    result = explainer.explain(_ctx())
    assert result.generated is False
    assert result.guard_ok is True
    assert result.text == _UNAVAILABLE_MESSAGE
