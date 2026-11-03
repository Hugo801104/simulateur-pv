"""Le formulaire HTML et le moteur doivent utiliser exactement les mêmes noms de paramètres."""

import re
from pathlib import Path

from pvsim.params import defaults

INDEX = Path(__file__).resolve().parents[2] / "index.html"


def test_every_form_field_is_an_engine_parameter_and_vice_versa():
    html = INDEX.read_text(encoding="utf-8")
    names = set(re.findall(r'name="([a-z_]+\.[a-z0-9_]+)"', html))
    form_params = {n for n in names if not n.startswith(("ui.", "house."))}
    engine_params = {f"{group}.{name}" for group, fields in defaults().items() for name in fields}
    assert form_params - engine_params == set(), "champs du formulaire inconnus du moteur"
    assert engine_params - form_params == set(), "paramètres du moteur absents du formulaire"


def test_form_defaults_match_engine_defaults():
    html = INDEX.read_text(encoding="utf-8")
    d = defaults()
    for name, value in re.findall(r'name="([a-z_]+\.[a-z0-9_]+)" type="number"[^>]*value="([^"]+)"', html):
        group, field = name.split(".")
        if group == "house":
            continue  # mode Conseil : vérifié par test_house_form_matches_advisor
        if group == "battery":
            continue  # valeurs proposées quand on active la batterie (désactivée par défaut)
        assert float(value) == float(d[group][field]["default"]), name


def test_house_form_matches_advisor():
    import dataclasses

    from pvsim.advisor import House

    html = INDEX.read_text(encoding="utf-8")
    names = {n.split(".", 1)[1] for n in re.findall(r'name="(house\.[a-z0-9_]+)"', html)}
    fields = {f.name for f in dataclasses.fields(House)}
    assert names == fields
    # Chaque option proposée dans le formulaire doit être acceptée par le moteur.
    for f in dataclasses.fields(House):
        if "choices" in f.metadata:
            values = set(re.findall(rf'name="house\.{f.name}"[^>]*value="([^"]+)"', html))
            block = re.search(rf'<select name="house\.{f.name}">(.*?)</select>', html, re.S)
            if block:
                values |= set(re.findall(r'value="([^"]+)"', block.group(1)))
            assert values and values <= set(f.metadata["choices"]), f.name
