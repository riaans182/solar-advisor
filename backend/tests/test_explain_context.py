# tests/test_explain_context.py
from datetime import UTC, datetime, time

from solar_advisor.domain.schedule import Slot
from solar_advisor.engine.optimize import Recommendation
from solar_advisor.engine.schedule_eval import SlotAssessment, SlotBehavior
from solar_advisor.explain.context import ExplanationContext, build_context
from solar_advisor.explain.prompt import build_messages
from solar_advisor.services.recommendation import ADVISORY_DISCLAIMER, DashboardData
from tests.conftest import make_telemetry


def _dashboard_data():
    slot = Slot(start=time(0, 0), end=time(5, 0), target_soc=90, grid_charge=True, gen_charge=False)
    assessment = SlotAssessment(
        slot=slot,
        behavior=SlotBehavior.GRID_CHARGING,
        end_soc=90.0,
        grid_import_kwh=13.0,
        cost=46.28,
    )
    rec = Recommendation(
        reserve_target_soc=100.0,
        enable_overnight_grid_charge=True,
        grid_charge_kwh=10.5,
        expected_daily_grid_import_kwh=22.5,
        expected_daily_cost=80.1,
        backup_hours=30.0,
        monthly_cost_so_far=956.0,
    )
    return DashboardData(
        telemetry=make_telemetry(datetime(2026, 6, 22, 8, 0, tzinfo=UTC), battery_soc=30.0),
        objective=0.5,
        slot_assessments=[assessment],
        recommendation=rec,
        usable_kwh=15.0,
        usable_kwh_confidence=0.6,
        daily_consumption_kwh=20.0,
        daily_consumption_confidence=0.5,
        tariff_rate=3.56,
        expected_pv_kwh_today=8.0,
        expected_pv_kwh_tomorrow=8.0,
        disclaimer=ADVISORY_DISCLAIMER,
    )


def test_build_context_carries_facts():
    ctx = build_context(_dashboard_data())
    assert isinstance(ctx, ExplanationContext)
    assert ctx.tariff_rate == 3.56
    assert ctx.objective == 0.5
    assert len(ctx.slots) == 1
    assert ctx.slots[0].behavior == "grid_charging"
    assert ctx.slots[0].cost == 46.28
    assert ctx.recommendation.expected_daily_cost == 80.1


def test_to_facts_is_text_and_includes_key_numbers():
    facts = build_context(_dashboard_data()).to_facts()
    assert isinstance(facts, str)
    # Engine numbers must appear verbatim so the guard can whitelist them.
    assert "3.56" in facts
    assert "46.28" in facts
    assert "80.1" in facts
    assert "grid_charging" in facts
    # The disclaimer travels with the facts.
    assert "read-only" in facts.lower()


def test_allowed_numbers_is_curated_from_engine_values_not_prose():
    ctx = build_context(_dashboard_data())
    allowed = ctx.allowed_numbers()
    # Engine quantities are present.
    assert 3.56 in allowed  # tariff rate
    assert 46.28 in allowed  # slot cost
    assert 80.1 in allowed  # expected daily cost
    # Structural references the model may legitimately name.
    assert 1.0 in allowed  # slot index 1
    assert 90.0 in allowed  # slot target SOC
    # Slot start hour (00:00 -> 0) must NOT leak in as a free integer; the
    # whitelist is curated, not scraped from the time-bearing prose. No engine
    # value in this fixture is 0.0, so 0.0 would only appear via a slot time.
    facts = ctx.to_facts()
    assert "00:00" in facts  # times still shown for context
    assert 0.0 not in allowed


def test_allowed_numbers_includes_confidence_as_percent():
    # usable_kwh_confidence is 0.6; "60%" is a legitimate restatement.
    ctx = build_context(_dashboard_data())
    assert 60.0 in ctx.allowed_numbers()


def test_build_messages_returns_system_and_facts():
    ctx = build_context(_dashboard_data())
    system, user = build_messages(ctx)
    assert "only use numbers" in system.lower() or "do not invent" in system.lower()
    assert "advisory" in system.lower()
    # The user message is the fact block — the guard whitelists exactly this.
    assert user == ctx.to_facts()
