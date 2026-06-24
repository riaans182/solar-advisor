# tests/test_engine_tariff.py
from solar_advisor.engine.tariff import FlatRateTariff, TariffModel


def test_marginal_rate_is_flat_regardless_of_month_to_date():
    t = FlatRateTariff(energy_rate=3.56, monthly_fixed_charge=600.0)
    assert t.marginal_rate(0.0) == 3.56
    assert t.marginal_rate(1000.0) == 3.56  # no inclining block


def test_monthly_cost_is_fixed_plus_import_times_rate():
    t = FlatRateTariff(energy_rate=3.56, monthly_fixed_charge=600.0)
    assert t.monthly_cost(100.0, days_in_month=30) == 600.0 + 100.0 * 3.56


def test_flat_rate_satisfies_tariff_model_protocol():
    t: TariffModel = FlatRateTariff(energy_rate=3.56, monthly_fixed_charge=600.0)
    assert isinstance(t, TariffModel)
