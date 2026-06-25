# tests/test_explain_guard.py
from solar_advisor.explain.guard import check_provenance, extract_numbers


def test_extract_numbers_handles_currency_percent_commas():
    nums = extract_numbers("Slot 1 costs R46.28, draws 1,140 W, holds 90% over 7 hours.")
    assert 46.28 in nums
    assert 1140.0 in nums
    assert 90.0 in nums
    assert 7.0 in nums


def test_provenance_passes_when_all_numbers_traced():
    facts = "cost R46.28, reserve 100%, 13.0 kWh"
    reply = "It grid-charges to 100%, importing 13.0 kWh at a cost of R46.28."
    result = check_provenance(reply, allowed=extract_numbers(facts))
    assert result.ok is True
    assert result.unverified == []


def test_provenance_flags_a_fabricated_number():
    facts = "cost R46.28, reserve 100%"
    reply = "This will save you R512 per month."  # 512 is nowhere in the facts
    result = check_provenance(reply, allowed=extract_numbers(facts))
    assert result.ok is False
    assert 512.0 in result.unverified


def test_provenance_tolerates_rounding():
    facts = "expected daily cost R42.72"
    reply = "Roughly R42.70 a day."  # within tolerance of 42.72
    assert check_provenance(reply, allowed=extract_numbers(facts)).ok is True


def test_provenance_ignores_when_no_numbers():
    assert check_provenance("Grid-charging at night is pure cost here.", allowed=[]).ok is True
