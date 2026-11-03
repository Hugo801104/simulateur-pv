import json
from pathlib import Path

import pandas as pd
import pytest

import reference_case
from pvsim.api import Engine


def call(fn, *args) -> dict:
    return json.loads(fn(*args))


@pytest.fixture
def engine(openmeteo_raw) -> Engine:
    e = Engine()
    assert call(e.set_weather, "openmeteo", openmeteo_raw)["ok"]
    return e


def test_info():
    r = call(Engine().info)
    assert r["ok"] and r["pvlib"] == "0.16.1"
    assert "pv" in r["defaults"]


def test_simulation_without_weather():
    r = call(Engine().simulate, "{}")
    assert not r["ok"] and "météo" in r["errors"][0]["message"]


def test_validation_errors_are_structured(engine):
    r = call(engine.simulate, json.dumps({"pv": {"tilt_deg": 120}}))
    assert r == {"ok": False, "errors": [{"field": "pv.tilt_deg", "message": "doit être compris entre 0 et 90"}]}


def test_weather_error_is_structured():
    r = call(Engine().set_weather, "openmeteo", "not json")
    assert not r["ok"] and "illisible" in r["errors"][0]["message"]


def test_full_simulation(engine):
    r = call(engine.simulate, json.dumps({"pv": {"peak_power_kwc": 3}}))
    assert r["ok"]
    t = r["totals"]
    assert t["pv_kwh"] == pytest.approx(3 * r["specific_yield_kwh_per_kwc"], rel=1e-6)
    assert 0 < t["self_consumption_rate"] <= 1
    assert len(r["monthly"]["month"]) == 12
    assert sum(r["monthly"]["pv_kwh"]) == pytest.approx(t["pv_kwh"])
    assert len(r["economics"]["yearly"]["year"]) == 25
    assert any("profil simplifié" in n for n in r["notes"])
    assert r["warnings"] == []


def test_optimisation_warns_when_best_is_on_grid_edge(engine):
    params = {"optimisation": {"pv_min_kwc": 1, "pv_max_kwc": 2, "pv_step_kwc": 1, "battery_sizes_kwh": [0]},
              "economics": {"export_tariff_eur_per_kwh": 0.2016, "fixed_capex_eur": 0}}
    r = call(engine.optimise, json.dumps(params))
    assert r["ok"] and r["optimisation"]["best"]["pv_kwc"] == 2
    assert any("puissance maximale testée" in w for w in r["warnings"])


def test_distance_warning(engine):
    r = call(engine.simulate, json.dumps({"site": {"latitude": 48.85, "longitude": 2.35}}))
    assert any("km du site" in w for w in r["warnings"])


def test_csv_load_flow(engine):
    times = pd.date_range("2023-01-01", periods=8760, freq="h", tz="UTC")
    text = "date,kwh\n" + "\n".join(f"{t.isoformat()},0.5" for t in times)
    r = call(engine.set_load_csv, text, "Europe/Paris", "kwh")
    assert r["ok"] and r["load"]["total_kwh"] == pytest.approx(4380)
    sim = call(engine.simulate, json.dumps({"load": {"mode": "csv"}}))
    assert sim["ok"]
    assert sim["totals"]["load_kwh"] == pytest.approx(4380, rel=1e-3)


def test_csv_mode_requires_file(engine):
    r = call(engine.simulate, json.dumps({"load": {"mode": "csv"}}))
    assert not r["ok"] and "courbe de charge" in r["errors"][0]["message"]


def test_hourly_export(engine):
    assert not call(engine.hourly_csv)["ok"]
    call(engine.simulate, "{}")
    csv = call(engine.hourly_csv)["csv"]
    assert csv.splitlines()[0].startswith("debut_heure_utc;pv_kwh")
    assert len(csv.splitlines()) == 8761


def test_reference_case_is_up_to_date():
    """Les résultats figés (utilisés aussi par le test Pyodide) doivent être reproduits."""
    stored = json.loads((Path(__file__).parent / "reference_case.json").read_text(encoding="utf-8"))
    assert stored["params"] == reference_case.CASE["params"]
    computed = reference_case.compute()
    for key, value in stored["expected"].items():
        assert computed[key] == pytest.approx(value, rel=1e-6), key
