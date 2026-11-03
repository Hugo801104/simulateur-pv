import numpy as np
import pytest

from pvsim.params import Battery
from pvsim.simulation import simulate

RNG = np.random.default_rng(42)
PV = np.clip(np.sin(np.linspace(0, 365 * 2 * np.pi, 8760)) * 4, 0, None)
LOAD = RNG.uniform(0.2, 1.5, 8760)


def test_without_battery():
    f = simulate(PV, LOAD, Battery())
    np.testing.assert_allclose(f.direct, np.minimum(PV, LOAD))
    np.testing.assert_allclose(f.direct + f.export, PV)
    np.testing.assert_allclose(f.direct + f.grid_import, LOAD)


@pytest.mark.parametrize("rte", [100, 90, 70])
def test_energy_conservation_with_battery(rte):
    b = Battery(capacity_kwh=10, power_kw=3, round_trip_efficiency_pct=rte, min_soc_pct=10)
    f = simulate(PV, LOAD, b)
    eta = np.sqrt(rte / 100)
    # Bilan côté production et côté consommation.
    np.testing.assert_allclose(f.direct + f.battery_charge + f.export, PV, atol=1e-9)
    np.testing.assert_allclose(f.direct + f.battery_discharge + f.grid_import, LOAD, atol=1e-9)
    # Bilan de la batterie : stock final = stock initial + charge × η - décharge / η.
    soc_end = 10 * 0.1 + f.battery_charge.sum() * eta - f.battery_discharge.sum() / eta
    assert f.soc[-1] == pytest.approx(soc_end, rel=1e-9)


def test_battery_limits():
    b = Battery(capacity_kwh=5, power_kw=2, min_soc_pct=20)
    f = simulate(PV, LOAD, b)
    assert f.soc.min() >= 1.0 - 1e-9 and f.soc.max() <= 5.0 + 1e-9
    assert f.battery_charge.max() <= 2 + 1e-9 and f.battery_discharge.max() <= 2 + 1e-9
    assert (f.export >= -1e-12).all() and (f.grid_import >= -1e-12).all()
    # Jamais de charge et de décharge dans la même heure.
    assert not np.any((f.battery_charge > 0) & (f.battery_discharge > 0))


def test_battery_increases_self_sufficiency():
    base = simulate(PV, LOAD, Battery()).totals()
    with_b = simulate(PV, LOAD, Battery(capacity_kwh=10, power_kw=5)).totals()
    assert with_b["self_sufficiency_rate"] > base["self_sufficiency_rate"]
    assert with_b["self_consumption_rate"] > base["self_consumption_rate"]


def test_shape_mismatch():
    with pytest.raises(ValueError):
        simulate(PV, LOAD[:10], Battery())
