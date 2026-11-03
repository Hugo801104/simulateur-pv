import json

import numpy as np
import pytest

from conftest import read_fixture
from pvsim import physics, weather
from pvsim.params import PVSystem, Site

SITE = Site(latitude=45.76, longitude=4.84)
PV = PVSystem(peak_power_kwc=1.0, tilt_deg=30, azimuth_deg=180, system_losses_pct=14)


@pytest.fixture(scope="module")
def tmy(pvgis_csv_raw):
    return weather.parse("pvgis_tmy", pvgis_csv_raw)


def test_matches_pvgis_reference(tmy):
    """Validation contre PVGIS PVcalc (même site, 30° sud, 14 % de pertes).

    PVGIS intègre l'ombrage du relief et les effets spectraux, que ce moteur ne
    modélise pas : on accepte ±5 % sur la production et l'irradiation.
    """
    ref = json.loads(read_fixture("pvgis_pvcalc_lyon_30S.json"))["outputs"]["totals"]["fixed"]
    profile = physics.compute_pv_profile(tmy, SITE, PV)
    assert profile.annual_yield() == pytest.approx(ref["E_y"], rel=0.05)
    assert profile.annual_poa_kwh_m2() == pytest.approx(ref["H(i)_y"], rel=0.05)


def test_sources_agree(tmy, openmeteo_raw, nasapower_raw):
    yields = [
        physics.compute_pv_profile(w, SITE, PV).annual_yield()
        for w in (tmy, weather.parse("openmeteo", openmeteo_raw), weather.parse("nasapower", nasapower_raw))
    ]
    assert max(yields) / min(yields) < 1.05


def test_orientation_physics(tmy):
    south = physics.compute_pv_profile(tmy, SITE, PV).annual_yield()
    north = physics.compute_pv_profile(tmy, SITE, PVSystem(tilt_deg=30, azimuth_deg=0)).annual_yield()
    east = physics.compute_pv_profile(tmy, SITE, PVSystem(tilt_deg=30, azimuth_deg=90)).annual_yield()
    assert south > east > north


def test_no_production_at_night_and_clipping(tmy):
    profile = physics.compute_pv_profile(tmy, SITE, PVSystem(dc_ac_ratio=1.5))
    night = tmy.data["ghi"].to_numpy() == 0
    assert np.all(profile.ac_kwh_per_kwc.to_numpy()[night] == 0)
    # La puissance AC ne dépasse jamais la puissance nominale de l'onduleur.
    assert profile.ac_kwh_per_kwc.max() <= 1 / 1.5 + 1e-9


def test_temperature_reduces_output(tmy):
    base = physics.compute_pv_profile(tmy, SITE, PV).annual_yield()
    hot = physics.compute_pv_profile(tmy, SITE, PVSystem(gamma_pdc_pct_per_c=-0.6)).annual_yield()
    assert hot < base


def test_losses_are_proportional(tmy):
    a = physics.compute_pv_profile(tmy, SITE, PVSystem(system_losses_pct=0, dc_ac_ratio=0.8)).annual_yield()
    b = physics.compute_pv_profile(tmy, SITE, PVSystem(system_losses_pct=10, dc_ac_ratio=0.8)).annual_yield()
    assert b / a == pytest.approx(0.9, rel=0.01)
