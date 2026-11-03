import pytest

from pvsim.params import ValidationError, defaults, parse_params


def fields_of(exc: pytest.ExceptionInfo) -> set[str]:
    return {e["field"] for e in exc.value.errors}


def test_defaults_are_valid():
    p = parse_params({})
    assert p.pv.peak_power_kwc == 6.0
    assert p.site.timezone == "Europe/Paris"
    assert p.site.altitude is None
    assert not p.battery.enabled


def test_accepts_strings_with_french_decimal_comma():
    p = parse_params({"pv": {"peak_power_kwc": "3,5", "tilt_deg": "20"}})
    assert p.pv.peak_power_kwc == 3.5
    assert p.pv.tilt_deg == 20.0


def test_reports_every_error_at_once():
    with pytest.raises(ValidationError) as exc:
        parse_params({
            "site": {"latitude": 120, "timezone": "Mars/Olympus"},
            "pv": {"tilt_deg": "abc"},
            "economics": {"lifetime_years": 2.5},
        })
    assert fields_of(exc) == {"site.latitude", "site.timezone", "pv.tilt_deg", "economics.lifetime_years"}


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError) as exc:
        parse_params({"pv": {"puissance": 3}, "autre": {}})
    assert fields_of(exc) == {"pv.puissance", "autre"}


def test_battery_capacity_and_power_must_go_together():
    with pytest.raises(ValidationError) as exc:
        parse_params({"battery": {"capacity_kwh": 5, "power_kw": 0}})
    assert "battery.power_kw" in fields_of(exc)


def test_optimisation_bounds_and_size():
    with pytest.raises(ValidationError) as exc:
        parse_params({"optimisation": {"pv_min_kwc": 9, "pv_max_kwc": 3}})
    assert "optimisation.pv_max_kwc" in fields_of(exc)
    with pytest.raises(ValidationError) as exc:
        parse_params({"optimisation": {"pv_min_kwc": 0.1, "pv_max_kwc": 1000, "pv_step_kwc": 0.1}})
    assert "optimisation.pv_step_kwc" in fields_of(exc)


def test_battery_sizes_accept_text_list():
    p = parse_params({"optimisation": {"battery_sizes_kwh": "10; 0 5 5"}})
    assert p.optimisation.battery_sizes_kwh == (0.0, 5.0, 10.0)


def test_choices():
    with pytest.raises(ValidationError):
        parse_params({"optimisation": {"objective": "lcoe"}})


def test_defaults_metadata_is_json_friendly():
    d = defaults()
    assert d["pv"]["tilt_deg"]["min"] == 0
    assert d["optimisation"]["battery_sizes_kwh"]["default"] == [0.0, 5.0, 10.0]
