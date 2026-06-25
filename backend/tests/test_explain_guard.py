# tests/test_explain_guard.py
from solar_advisor.explain.guard import (
    check_provenance,
    contains_number_word,
    extract_numbers,
)


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


# --- Closed holes -----------------------------------------------------------


def test_extract_numbers_reads_scientific_notation_magnitude():
    # "1e3" must extract as 1000.0, not as the digits 1 and 3.
    nums = extract_numbers("That is 1e3 kWh.")
    assert 1000.0 in nums
    assert nums == [1000.0]


def test_contains_number_word_detects_spelled_out_numbers():
    assert contains_number_word("about five hundred rand") is True
    assert contains_number_word("THIRTY percent") is True
    assert contains_number_word("the forty-two slot") is True  # word-boundary hit on 'forty'
    # No false positive on substrings inside ordinary words.
    assert contains_number_word("the tones of the inverter hum") is False
    assert contains_number_word("a oneness of purpose") is False


def test_provenance_flags_spelled_out_number():
    # The model was told to use digits; a spelled-out number can't be verified.
    result = check_provenance("This will save you five hundred rand.", allowed=[500.0])
    assert result.ok is False


def test_provenance_flags_scientific_notation_not_in_allowed():
    # "1e3" is 1000, which is not in the allowed set -> flagged.
    result = check_provenance("Imports 1e3 kWh tonight.", allowed=[13.0, 46.28])
    assert result.ok is False
    assert 1000.0 in result.unverified


def test_provenance_closes_corridor_between_two_facts():
    # Old tolerance keyed off max(|n|,|w|) + any-match let a fabricated 1100 pass
    # between facts 1086 and 1140. Fact-keyed tolerance must flag it.
    result = check_provenance("Draws 1100 W steady.", allowed=[1086.0, 1140.0])
    assert result.ok is False
    assert 1100.0 in result.unverified


def test_provenance_still_tolerates_legitimate_rounding():
    # 42.70 vs allowed 42.72 stays within tolerance.
    assert check_provenance("Roughly R42.70 a day.", allowed=[42.72]).ok is True
