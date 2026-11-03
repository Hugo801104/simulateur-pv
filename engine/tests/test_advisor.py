import json

import pytest

from pvsim import advisor, knowledge as K, weather
from pvsim.api import Engine
from pvsim.params import ValidationError


@pytest.fixture(scope="module")
def wx(openmeteo_raw):
    return weather.parse("openmeteo", openmeteo_raw)


def house(**kw) -> advisor.House:
    base = {"latitude": 45.76, "longitude": 4.84, "annual_kwh": 4500, "roof_area_m2": 30}
    base.update(kw)
    return advisor.parse_house(base)


def test_parse_and_validation():
    h = house()
    assert h.orientation == "S" and h.tilt_deg is None
    with pytest.raises(ValidationError) as exc:
        advisor.parse_house({"orientation": "Z", "roof_area_m2": -1})
    assert {e["field"] for e in exc.value.errors} == {"house.orientation", "house.roof_area_m2"}


def test_electric_heating_requires_bill():
    with pytest.raises(ValidationError, match="facture"):
        advisor.parse_house({"heating": "electrique"})
    advisor.parse_house({"heating": "electrique", "annual_kwh": 9000})


def test_consumption_estimate_is_flagged():
    kwh, estimated, basis = advisor.estimate_consumption(advisor.parse_house({"occupants": 3}))
    assert estimated and kwh == pytest.approx(4500) and "ordre de grandeur" in basis
    kwh5, _, _ = advisor.estimate_consumption(advisor.parse_house({"occupants": 5}))
    assert kwh5 == pytest.approx(6500)


def test_geometry():
    assert advisor.geometry(house(orientation="EO")).azimuths == [90.0, 270.0]
    flat = advisor.geometry(house(roof_type="toit_plat", orientation="N"))
    assert flat.flat and flat.azimuths == [180.0] and flat.tilt == K.SLOPES["plat"]
    assert advisor.geometry(house(tilt_deg=22)).tilt == 22


def test_vat_above_9kwc():
    m = K.MODULES["topcon"]
    small, big = advisor.economics_for(9.0, m), advisor.economics_for(9.24, m)
    assert big.pv_capex_eur_per_kwc / small.pv_capex_eur_per_kwc == pytest.approx(1.20 / 1.055)
    assert small.export_tariff_eur_per_kwh == K.EXPORT_TARIFF_EUR_PER_KWH


def test_recommendation_is_consistent(wx):
    r = advisor.advise(house(), wx)
    rec = r["recommendation"]
    assert rec["npv_eur"] == max(row["npv_eur"] for row in r["grid"])
    assert rec["panels"] <= r["roof"]["max_panels"]
    assert rec["pv_kwc"] == pytest.approx(rec["panels"] * 0.44)
    assert 0.98 < r["production"]["orientation_ratio"] <= 1.01  # pan sud à 30° = référence
    assert r["options"][0]["key"] == "recommandee"
    assert sum(r["monthly"]["pv_kwh"]) == pytest.approx(rec["totals"]["pv_kwh"])
    cats = {a["category"] for a in r["advice"]}
    assert {"panneaux", "onduleur", "batterie", "pose", "structure", "autoconsommation"} <= cats
    for key in r["sources"]:
        assert r["sources"][key]["url"].startswith("https://")
    for item in r["advice"]:
        assert set(item["sources"]) <= set(r["sources"])


def test_roof_limits_size(wx):
    r = advisor.advise(house(roof_area_m2=10), wx)
    assert r["roof"]["max_panels"] == 4  # 10 m² × 80 % / 2,0 m²
    assert r["recommendation"]["panels"] <= 4


def test_north_roof_is_flagged(wx):
    r = advisor.advise(house(orientation="N"), wx)
    assert r["production"]["orientation_ratio"] < 0.75
    assert any(a["title"] == "Orientation peu favorable" for a in r["advice"])


def test_shading_and_east_west_recommend_micro_inverters(wx):
    for h in (house(shading="partiel"), house(orientation="EO")):
        inv = next(a for a in advisor.advise(h, wx)["advice"] if a["category"] == "onduleur")
        assert "Micro-onduleurs" in inv["text"]
    inv = next(a for a in advisor.advise(house(), wx)["advice"] if a["category"] == "onduleur")
    assert "Onduleur central" in inv["text"]


def test_construction_warnings(wx):
    r = advisor.advise(house(roof_type="fibrociment", construction_period="avant_1997", structure="fermettes",
                             roof_age="ancienne", protected_area="oui"), wx)
    titles = {a["title"] for a in r["advice"]}
    assert {"Risque d'amiante", "Couverture à refaire d'abord", "Secteur protégé"} <= titles
    charpente = next(a for a in r["advice"] if a["title"] == "Charpente")
    assert charpente["level"] == "attention" and "fermettes" in charpente["text"]


def test_budget_constraint(wx):
    r = advisor.advise(house(budget_eur=10000), wx)
    assert r["recommendation"]["capex_eur"] <= 10000
    with pytest.raises(ValueError, match="budget"):
        advisor.advise(house(budget_eur=500), wx)


def test_too_small_roof(wx):
    with pytest.raises(ValueError, match="Surface insuffisante"):
        advisor.advise(house(roof_area_m2=3), wx)


def test_api_advise(openmeteo_raw):
    e = Engine()
    assert not json.loads(e.advise("{}"))["ok"]  # pas de météo
    e.set_weather("openmeteo", openmeteo_raw)
    r = json.loads(e.advise(json.dumps({"latitude": 45.76, "longitude": 4.84, "occupants": 2, "roof_area_m2": 25})))
    assert r["ok"] and r["advice"]["consumption"]["estimated"]
    bad = json.loads(e.advise(json.dumps({"roof_area_m2": "x"})))
    assert bad == {"ok": False, "errors": [{"field": "house.roof_area_m2", "message": "nombre attendu"}]}


def test_sizes_start_at_price_model_minimum(wx):
    r = advisor.advise(house(roof_area_m2=60), wx)
    assert min(row["pv_kwc"] for row in r["grid"]) >= 3.0
    small = advisor.advise(house(roof_area_m2=10), wx)
    assert any("extrapolés" in n for n in small["notes"])


def test_break_even_capex_zeroes_npv(wx):
    r = advisor.advise(house(), wx)
    rec = r["recommendation"]
    target = rec["break_even_capex_eur"]
    assert target is not None
    # Rejouer l'évaluation avec l'investissement cible : VAN ≈ 0.
    m = K.MODULES["topcon"]
    base = advisor.economics_for(rec["pv_kwc"], m)
    import dataclasses
    from pvsim import economics
    shifted = dataclasses.replace(base, fixed_capex_eur=base.fixed_capex_eur + (target - rec["capex_eur"]))
    assert economics.evaluate(shifted, rec["pv_kwc"], rec["battery_kwh"], rec["totals"])["npv_eur"] == pytest.approx(0, abs=1)
    assert r["advice"][0]["title"] == "Prix de devis à viser"


def test_east_west_uses_even_panel_counts(wx):
    r = advisor.advise(house(orientation="EO", roof_area_m2=50), wx)
    assert all(row["panels"] % 2 == 0 for row in r["grid"])
