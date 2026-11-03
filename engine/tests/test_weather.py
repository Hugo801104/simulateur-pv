import json

import numpy as np
import pandas as pd
import pvlib
import pytest

from pvsim import weather


def test_openmeteo(openmeteo_raw):
    w = weather.parse("openmeteo", openmeteo_raw)
    assert len(w.data) == 8760
    assert list(w.data.columns) == weather.COLUMNS
    # Horodatage Open-Meteo = fin d'heure : la 1re heure commence le 31/12 à 23 h UTC.
    assert w.data.index[0] == pd.Timestamp("2022-12-31 23:00", tz="UTC")
    assert w.solar_offset_min == 30
    assert 1300 < w.summary()["ghi_kwh_m2"] < 1500


def test_nasapower(nasapower_raw):
    w = weather.parse("nasapower", nasapower_raw)
    assert len(w.data) == 8760
    assert w.data.index[0] == pd.Timestamp("2023-01-01 00:00", tz="UTC")
    assert 1300 < w.summary()["ghi_kwh_m2"] < 1500


@pytest.mark.parametrize("fixture", ["pvgis_csv_raw", "pvgis_json_raw"])
def test_pvgis_tmy(fixture, request):
    w = weather.parse("pvgis_tmy", request.getfixturevalue(fixture))
    assert len(w.data) == 8760
    assert w.data.index.year.unique().tolist() == [2023]
    assert w.solar_offset_min == pytest.approx(0.1771 * 60)
    assert w.latitude == pytest.approx(45.76)


@pytest.mark.parametrize("source, fixture, offset", [
    ("openmeteo", "openmeteo_raw", 30),
    ("nasapower", "nasapower_raw", 30),
])
def test_timestamp_convention_matches_sun(source, fixture, offset, request):
    """La convention retenue doit être celle qui colle le mieux à un ciel clair."""
    w = weather.parse(source, request.getfixturevalue(fixture))
    loc = pvlib.location.Location(w.latitude, w.longitude)
    scores = {}
    for candidate in (offset - 60, offset, offset + 60):
        times = w.data.index + pd.Timedelta(minutes=candidate)
        cs = loc.get_clearsky(times)["ghi"].to_numpy()
        mask = cs > 50
        scores[candidate] = np.corrcoef(w.data["ghi"].to_numpy()[mask], cs[mask])[0, 1]
    assert max(scores, key=scores.get) == offset


def _openmeteo_doc(raw: str) -> dict:
    return json.loads(raw)


def test_missing_values_are_refused_never_invented(openmeteo_raw):
    doc = _openmeteo_doc(openmeteo_raw)
    doc["hourly"]["shortwave_radiation"][100] = None
    with pytest.raises(weather.WeatherError, match="Aucune valeur n'est inventée"):
        weather.parse("openmeteo", json.dumps(doc))


def test_incomplete_year_is_refused(openmeteo_raw):
    doc = _openmeteo_doc(openmeteo_raw)
    for k in doc["hourly"]:
        doc["hourly"][k] = doc["hourly"][k][:1000]
    with pytest.raises(weather.WeatherError, match="année complète"):
        weather.parse("openmeteo", json.dumps(doc))


def test_api_error_message_is_forwarded():
    with pytest.raises(weather.WeatherError, match="Parameter"):
        weather.parse("openmeteo", json.dumps({"error": True, "reason": "Parameter 'hourly' is invalid"}))


def test_nasa_fill_values_are_missing(nasapower_raw):
    doc = json.loads(nasapower_raw)
    first = next(iter(doc["properties"]["parameter"]["T2M"]))
    doc["properties"]["parameter"]["T2M"][first] = -999.0
    with pytest.raises(weather.WeatherError, match="1 heures sans valeur"):
        weather.parse("nasapower", json.dumps(doc))


def test_garbage_inputs():
    with pytest.raises(weather.WeatherError):
        weather.parse("openmeteo", "<html>")
    with pytest.raises(weather.WeatherError):
        weather.parse("pvgis_tmy", "pas un fichier pvgis")
    with pytest.raises(weather.WeatherError):
        weather.parse("inconnue", "{}")
