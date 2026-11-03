import numpy as np
import pytest

from pvsim import economics
from pvsim.params import Economics

TOTALS = {"pv_kwh": 1000.0, "load_kwh": 2000.0, "self_supplied_kwh": 600.0, "export_kwh": 400.0, "import_kwh": 1400.0}


def flat(**kw) -> Economics:
    base = dict(
        pv_capex_eur_per_kwc=1000, battery_capex_eur_per_kwh=0, fixed_capex_eur=0, opex_pct_of_capex=0, inverter_replacement_year=0,
        battery_lifetime_years=0, electricity_price_eur_per_kwh=0.2, electricity_price_escalation_pct=0,
        export_tariff_eur_per_kwh=0.1, discount_rate_pct=0, lifetime_years=10, degradation_pct_per_year=0,
    )
    base.update(kw)
    return Economics(**base)


def test_hand_computed_case():
    # Gains annuels : 600 × 0,2 + 400 × 0,1 = 160 € ; investissement 1000 €.
    r = economics.evaluate(flat(), 1.0, 0.0, TOTALS)
    assert r["year1_savings_eur"] == pytest.approx(160)
    assert r["npv_eur"] == pytest.approx(10 * 160 - 1000)
    assert r["payback_years"] == pytest.approx(1000 / 160)
    assert r["lcoe_eur_per_kwh"] == pytest.approx(1000 / 10000)


def test_irr_zeroes_npv():
    econ = flat(discount_rate_pct=0)
    r = economics.evaluate(econ, 1.0, 0.0, TOTALS)
    at_irr = economics.evaluate(flat(discount_rate_pct=r["irr"] * 100), 1.0, 0.0, TOTALS)
    assert at_irr["npv_eur"] == pytest.approx(0, abs=1e-6)
    # Valeur connue : annuité de 160 sur 10 ans pour 1000 -> TRI ≈ 9,6 %.
    assert r["irr"] == pytest.approx(0.0961, abs=5e-4)


def test_unprofitable_project():
    r = economics.evaluate(flat(pv_capex_eur_per_kwc=100000), 1.0, 0.0, TOTALS)
    assert r["npv_eur"] < 0
    assert r["payback_years"] is None


def test_discounting_and_degradation_reduce_value():
    base = economics.evaluate(flat(), 1.0, 0.0, TOTALS)["npv_eur"]
    assert economics.evaluate(flat(discount_rate_pct=5), 1.0, 0.0, TOTALS)["npv_eur"] < base
    assert economics.evaluate(flat(degradation_pct_per_year=1), 1.0, 0.0, TOTALS)["npv_eur"] < base


def test_replacements_and_subsidy():
    econ = flat(lifetime_years=25, inverter_replacement_year=15, inverter_replacement_eur_per_kwc=150,
                battery_capex_eur_per_kwh=500, battery_lifetime_years=10, battery_replacement_pct=50, subsidy_eur=300)
    r = economics.evaluate(econ, 2.0, 4.0, TOTALS)
    rep = np.array(r["yearly"]["replacements_eur"])
    assert rep[14] == pytest.approx(300)  # onduleur, année 15
    assert rep[9] == pytest.approx(1000) and rep[19] == pytest.approx(1000)  # batterie, années 10 et 20
    assert r["capex_eur"] == pytest.approx(2 * 1000 + 4 * 500 - 300)


def test_bills():
    r = economics.evaluate(flat(), 1.0, 0.0, TOTALS)
    assert r["year1_bill_without_pv_eur"] == pytest.approx(400)
    assert r["year1_bill_with_pv_eur"] == pytest.approx(1400 * 0.2 - 40)
