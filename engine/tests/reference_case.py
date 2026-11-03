"""Cas de référence partagé entre CPython (pytest) et Pyodide (tests/pyodide/smoke.mjs).

    python engine/tests/reference_case.py      régénère reference_case.json

Le fichier JSON fige les résultats calculés sous CPython. Le test Pyodide
vérifie que le moteur exécuté dans le navigateur (WebAssembly) donne les mêmes
valeurs : c'est la preuve que les deux environnements sont équivalents.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))

CASE = {
    "weather_source": "openmeteo",
    "weather_fixture": "openmeteo_lyon_2023.json",
    "params": {
        "site": {"latitude": 45.76, "longitude": 4.84, "timezone": "Europe/Paris"},
        "pv": {"peak_power_kwc": 6, "tilt_deg": 30, "azimuth_deg": 180},
        "battery": {"capacity_kwh": 5, "power_kw": 2.5},
        "load": {"mode": "profile", "annual_kwh": 4500},
        "optimisation": {"pv_min_kwc": 2, "pv_max_kwc": 8, "pv_step_kwc": 1, "battery_sizes_kwh": [0, 5]},
    },
}

KEYS = [
    ("specific_yield_kwh_per_kwc",),
    ("totals", "pv_kwh"),
    ("totals", "export_kwh"),
    ("totals", "import_kwh"),
    ("totals", "self_consumption_rate"),
    ("economics", "npv_eur"),
    ("economics", "irr"),
    ("economics", "lcoe_eur_per_kwh"),
]


def compute() -> dict:
    from pvsim.api import Engine

    engine = Engine()
    raw = (HERE / "fixtures" / CASE["weather_fixture"]).read_text(encoding="utf-8")
    assert json.loads(engine.set_weather(CASE["weather_source"], raw))["ok"]
    sim = json.loads(engine.simulate(json.dumps(CASE["params"])))
    opt = json.loads(engine.optimise(json.dumps(CASE["params"])))
    assert sim["ok"] and opt["ok"], (sim, opt)
    expected = {}
    for path in KEYS:
        value = sim
        for k in path:
            value = value[k]
        expected[".".join(path)] = value
    best = opt["optimisation"]["best"]
    expected["optimisation.best.pv_kwc"] = best["pv_kwc"]
    expected["optimisation.best.battery_kwh"] = best["battery_kwh"]
    return expected


if __name__ == "__main__":
    out = {**CASE, "expected": compute()}
    (HERE / "reference_case.json").write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(out["expected"], indent=2))
