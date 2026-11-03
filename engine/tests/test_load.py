import numpy as np
import pandas as pd
import pytest

from pvsim import load

INDEX = pd.date_range("2023-01-01", periods=8760, freq="h", tz="UTC")


def test_simplified_profile_sums_to_annual():
    s = load.simplified_profile(INDEX, "Europe/Paris", 4500)
    assert s.sum() == pytest.approx(4500)
    local = s.index.tz_convert("Europe/Paris")
    by_hour = s.groupby(local.hour).mean()
    assert by_hour.idxmax() == 19  # pointe du soir
    assert s[local.month == 1].sum() > s[local.month == 7].sum()


def _csv(times, values, header="date;valeur"):
    return header + "\n" + "\n".join(f"{t};{v}" for t, v in zip(times, values))


def test_parse_enedis_like_half_hourly_watts():
    times = pd.date_range("2023-01-01", periods=48 * 365, freq="30min")
    text = _csv([t.strftime("%Y-%m-%dT%H:%M:%S+01:00") for t in times], ["1000"] * len(times))
    hourly, _ = load.parse_load_csv(text, "Europe/Paris", "w")
    # 1000 W pendant 1 h = 1 kWh
    assert hourly.dropna().iloc[5] == pytest.approx(1.0)
    assert hourly.index.tz is not None


def test_parse_kwh_local_times_with_comma_decimal():
    times = pd.date_range("2023-03-01", periods=48, freq="h")
    text = _csv([t.strftime("%d/%m/%Y %H:%M") for t in times], ["0,5"] * 48)
    hourly, _ = load.parse_load_csv(text, "Europe/Paris", "kwh")
    assert hourly.dropna().sum() == pytest.approx(24.0)
    assert hourly.index[0] == pd.Timestamp("2023-02-28 23:00", tz="UTC")


def test_align_interpolates_small_gaps_and_warns():
    hourly = pd.Series(1.0, index=INDEX)
    hourly.iloc[100:102] = np.nan
    aligned, warnings = load.align_to_weather(hourly, INDEX)
    assert aligned.isna().sum() == 0
    assert "2 heures" in warnings[0]


def test_align_refuses_large_gaps():
    hourly = pd.Series(1.0, index=INDEX)
    hourly.iloc[100:300] = np.nan
    with pytest.raises(load.LoadError, match="incomplète"):
        load.align_to_weather(hourly, INDEX)


def test_align_other_year_by_calendar_date():
    hourly = pd.Series(np.arange(8760.0), index=pd.date_range("2021-01-01", periods=8760, freq="h", tz="UTC"))
    aligned, warnings = load.align_to_weather(hourly, INDEX)
    assert aligned.iloc[0] == 0 and aligned.iloc[-1] == 8759
    assert "2021" in warnings[0]


@pytest.mark.parametrize("text", ["", "a\n1", "date;valeur\n" + "x;y\n" * 30])
def test_bad_csv(text):
    with pytest.raises(load.LoadError):
        load.parse_load_csv(text, "Europe/Paris", "kwh")


def test_negative_values_refused():
    times = pd.date_range("2023-01-01", periods=48, freq="h")
    with pytest.raises(load.LoadError, match="négatives"):
        load.parse_load_csv(_csv([str(t) for t in times], ["-1"] * 48), "Europe/Paris", "kwh")
