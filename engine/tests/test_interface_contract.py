"""Le formulaire HTML et le moteur doivent utiliser exactement les mêmes noms de paramètres."""

import re
from pathlib import Path

from pvsim.params import defaults

INDEX = Path(__file__).resolve().parents[2] / "index.html"


def test_every_form_field_is_an_engine_parameter_and_vice_versa():
    html = INDEX.read_text(encoding="utf-8")
    names = set(re.findall(r'name="([a-z_]+\.[a-z0-9_]+)"', html))
    form_params = {n for n in names if not n.startswith("ui.")}
    engine_params = {f"{group}.{name}" for group, fields in defaults().items() for name in fields}
    assert form_params - engine_params == set(), "champs du formulaire inconnus du moteur"
    assert engine_params - form_params == set(), "paramètres du moteur absents du formulaire"


def test_form_defaults_match_engine_defaults():
    html = INDEX.read_text(encoding="utf-8")
    d = defaults()
    for name, value in re.findall(r'name="([a-z_]+\.[a-z0-9_]+)" type="number"[^>]*value="([^"]+)"', html):
        group, field = name.split(".")
        if group == "battery":
            continue  # valeurs proposées quand on active la batterie (désactivée par défaut)
        assert float(value) == float(d[group][field]["default"]), name
