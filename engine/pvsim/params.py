"""Collecte et validation des paramètres.

Chaque groupe de paramètres est une dataclass dont les champs portent leurs
bornes dans `metadata`. `parse_params` convertit un dictionnaire (issu du JSON
envoyé par l'interface) en objets typés, ou lève `ValidationError` avec la
liste complète des erreurs (champ + message en français).
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field
from typing import Any


class ValidationError(Exception):
    """Erreurs de saisie : liste de {"field": "groupe.champ", "message": str}."""

    def __init__(self, errors: list[dict[str, str]]):
        super().__init__("; ".join(f"{e['field']}: {e['message']}" for e in errors))
        self.errors = errors


def _num(default: float, lo: float, hi: float, label: str, *, integer: bool = False):
    return field(default=default, metadata={"min": lo, "max": hi, "label": label, "integer": integer})


@dataclass(frozen=True)
class Site:
    latitude: float = _num(45.76, -90, 90, "Latitude (°)")
    longitude: float = _num(4.84, -180, 180, "Longitude (°)")
    # None : altitude reprise des données météo.
    altitude: float | None = field(default=None, metadata={"min": -500, "max": 9000, "label": "Altitude (m)", "optional": True})
    timezone: str = field(default="Europe/Paris", metadata={"label": "Fuseau horaire"})


@dataclass(frozen=True)
class PVSystem:
    peak_power_kwc: float = _num(6.0, 0.1, 1000, "Puissance crête (kWc)")
    tilt_deg: float = _num(30.0, 0, 90, "Inclinaison (°)")
    # Convention pvlib : 0 = nord, 90 = est, 180 = sud, 270 = ouest.
    azimuth_deg: float = _num(180.0, 0, 360, "Azimut (°)")
    system_losses_pct: float = _num(14.0, 0, 50, "Pertes système (%)")
    gamma_pdc_pct_per_c: float = _num(-0.37, -1.0, 0.0, "Coefficient de température (%/°C)")
    dc_ac_ratio: float = _num(1.1, 0.5, 2.0, "Ratio DC/AC")
    inverter_efficiency_pct: float = _num(96.0, 80, 99.5, "Rendement onduleur (%)")
    albedo: float = _num(0.2, 0, 1, "Albédo")
    faiman_u0: float = _num(25.0, 1, 100, "Faiman U0 (W/m²K)")
    faiman_u1: float = _num(6.84, 0, 50, "Faiman U1 (W/m³sK)")


@dataclass(frozen=True)
class Battery:
    capacity_kwh: float = _num(0.0, 0, 1000, "Capacité batterie (kWh)")
    power_kw: float = _num(0.0, 0, 1000, "Puissance batterie (kW)")
    round_trip_efficiency_pct: float = _num(90.0, 50, 100, "Rendement aller-retour (%)")
    min_soc_pct: float = _num(10.0, 0, 90, "État de charge minimal (%)")

    @property
    def enabled(self) -> bool:
        return self.capacity_kwh > 0 and self.power_kw > 0


@dataclass(frozen=True)
class Load:
    # "profile" : profil simplifié normalisé sur la consommation annuelle.
    # "csv" : courbe de charge importée (voir api.set_load_csv).
    mode: str = field(default="profile", metadata={"label": "Mode de consommation", "choices": ("profile", "csv")})
    annual_kwh: float = _num(4500.0, 1, 10_000_000, "Consommation annuelle (kWh)")


@dataclass(frozen=True)
class Economics:
    # Ordres de grandeur indicatifs (résidentiel), à remplacer par des devis.
    pv_capex_eur_per_kwc: float = _num(1700.0, 0, 20000, "Coût PV (€/kWc)")
    battery_capex_eur_per_kwh: float = _num(600.0, 0, 10000, "Coût batterie (€/kWh)")
    fixed_capex_eur: float = _num(2000.0, 0, 1e8, "Coûts fixes (€)")
    subsidy_eur: float = _num(0.0, 0, 1e8, "Aides (€)")
    opex_pct_of_capex: float = _num(1.0, 0, 20, "Maintenance (% de l'investissement / an)")
    inverter_replacement_year: int = _num(15, 0, 60, "Remplacement onduleur (année, 0 = jamais)", integer=True)
    inverter_replacement_eur_per_kwc: float = _num(150.0, 0, 5000, "Coût remplacement onduleur (€/kWc)")
    battery_lifetime_years: int = _num(12, 0, 60, "Durée de vie batterie (ans, 0 = pas de remplacement)", integer=True)
    battery_replacement_pct: float = _num(70.0, 0, 200, "Coût remplacement batterie (% du coût initial)")
    electricity_price_eur_per_kwh: float = _num(0.2016, 0, 5, "Prix de l'électricité achetée (€/kWh)")
    electricity_price_escalation_pct: float = _num(2.0, -10, 20, "Évolution du prix (%/an)")
    export_tariff_eur_per_kwh: float = _num(0.04, 0, 5, "Tarif de revente (€/kWh)")
    export_tariff_escalation_pct: float = _num(0.0, -10, 20, "Évolution du tarif de revente (%/an)")
    discount_rate_pct: float = _num(4.0, -5, 30, "Taux d'actualisation (%)")
    lifetime_years: int = _num(25, 1, 60, "Durée d'étude (ans)", integer=True)
    degradation_pct_per_year: float = _num(0.5, 0, 5, "Dégradation des modules (%/an)")


@dataclass(frozen=True)
class Optimisation:
    pv_min_kwc: float = _num(1.0, 0.1, 1000, "Puissance min (kWc)")
    pv_max_kwc: float = _num(9.0, 0.1, 1000, "Puissance max (kWc)")
    pv_step_kwc: float = _num(0.5, 0.05, 100, "Pas (kWc)")
    battery_sizes_kwh: tuple[float, ...] = field(default=(0.0, 5.0, 10.0), metadata={"label": "Capacités batterie testées (kWh)"})
    battery_c_rate: float = _num(0.5, 0.05, 5, "Puissance batterie / capacité (h⁻¹)")
    objective: str = field(default="npv", metadata={"label": "Critère", "choices": ("npv", "irr")})


@dataclass(frozen=True)
class Params:
    site: Site
    pv: PVSystem
    battery: Battery
    load: Load
    economics: Economics
    optimisation: Optimisation


_GROUPS: dict[str, type] = {
    "site": Site,
    "pv": PVSystem,
    "battery": Battery,
    "load": Load,
    "economics": Economics,
    "optimisation": Optimisation,
}

MAX_OPTIMISATION_RUNS = 2000


def _parse_group(cls: type, raw: Any, prefix: str, errors: list[dict[str, str]]):
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        errors.append({"field": prefix, "message": "doit être un objet"})
        return None
    unknown = set(raw) - {f.name for f in dataclasses.fields(cls)}
    for name in sorted(unknown):
        errors.append({"field": f"{prefix}.{name}", "message": "paramètre inconnu"})

    values: dict[str, Any] = {}
    for f in dataclasses.fields(cls):
        meta = f.metadata
        key = f"{prefix}.{f.name}"
        if f.name not in raw or raw[f.name] is None or raw[f.name] == "":
            if meta.get("optional"):
                values[f.name] = None
            continue  # valeur par défaut
        value = raw[f.name]

        if "choices" in meta:
            if value not in meta["choices"]:
                errors.append({"field": key, "message": f"valeur attendue parmi {', '.join(meta['choices'])}"})
            else:
                values[f.name] = value
            continue

        if f.name == "timezone":
            if not isinstance(value, str) or not _is_valid_timezone(value):
                errors.append({"field": key, "message": "fuseau horaire inconnu (ex. Europe/Paris)"})
            else:
                values[f.name] = value
            continue

        if f.name == "battery_sizes_kwh":
            sizes = _parse_number_list(value)
            if sizes is None or not sizes or any(s < 0 or s > 1000 for s in sizes):
                errors.append({"field": key, "message": "liste de capacités entre 0 et 1000 kWh attendue"})
            else:
                values[f.name] = tuple(sorted(set(sizes)))
            continue

        number = _to_number(value)
        if number is None:
            errors.append({"field": key, "message": "nombre attendu"})
            continue
        if meta.get("integer"):
            if number != int(number):
                errors.append({"field": key, "message": "nombre entier attendu"})
                continue
            number = int(number)
        lo, hi = meta.get("min"), meta.get("max")
        if lo is not None and number < lo or hi is not None and number > hi:
            errors.append({"field": key, "message": f"doit être compris entre {lo:g} et {hi:g}"})
            continue
        values[f.name] = number

    try:
        return cls(**values)
    except TypeError as exc:  # pragma: no cover - garde-fou
        errors.append({"field": prefix, "message": str(exc)})
        return None


def _to_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip().replace(",", "."))
        except ValueError:
            return None
    else:
        return None
    return number if math.isfinite(number) else None


def _parse_number_list(value: Any) -> list[float] | None:
    if isinstance(value, str):
        parts = [p for p in value.replace(";", " ").split() if p]
    elif isinstance(value, (list, tuple)):
        parts = list(value)
    else:
        return None
    numbers = [_to_number(p) for p in parts]
    if any(n is None for n in numbers):
        return None
    return [float(n) for n in numbers]  # type: ignore[arg-type]


def _is_valid_timezone(name: str) -> bool:
    try:
        import zoneinfo

        zoneinfo.ZoneInfo(name)
        return True
    except Exception:
        return False


def parse_params(raw: dict[str, Any]) -> Params:
    """Valide l'ensemble des paramètres. Lève ValidationError si une saisie est invalide."""
    if not isinstance(raw, dict):
        raise ValidationError([{"field": "", "message": "objet de paramètres attendu"}])
    errors: list[dict[str, str]] = []
    for name in sorted(set(raw) - set(_GROUPS)):
        errors.append({"field": name, "message": "groupe de paramètres inconnu"})
    groups = {name: _parse_group(cls, raw.get(name), name, errors) for name, cls in _GROUPS.items()}

    # Contrôles croisés.
    battery: Battery | None = groups["battery"]
    if battery and (battery.capacity_kwh > 0) != (battery.power_kw > 0):
        errors.append({"field": "battery.power_kw", "message": "capacité et puissance doivent être toutes deux nulles ou toutes deux positives"})
    opt: Optimisation | None = groups["optimisation"]
    if opt:
        if opt.pv_min_kwc > opt.pv_max_kwc:
            errors.append({"field": "optimisation.pv_max_kwc", "message": "doit être supérieure ou égale à la puissance min"})
        else:
            runs = (math.floor((opt.pv_max_kwc - opt.pv_min_kwc) / opt.pv_step_kwc + 1e-9) + 1) * len(opt.battery_sizes_kwh)
            if runs > MAX_OPTIMISATION_RUNS:
                errors.append({"field": "optimisation.pv_step_kwc", "message": f"trop de combinaisons ({runs}), maximum {MAX_OPTIMISATION_RUNS} : augmentez le pas"})

    if errors:
        raise ValidationError(errors)
    return Params(**groups)  # type: ignore[arg-type]


def defaults() -> dict[str, dict[str, Any]]:
    """Valeurs par défaut et métadonnées, pour l'interface et la documentation."""
    out: dict[str, dict[str, Any]] = {}
    for name, cls in _GROUPS.items():
        out[name] = {}
        for f in dataclasses.fields(cls):
            default = f.default
            if isinstance(default, tuple):
                default = list(default)
            out[name][f.name] = {"default": default, **{k: (list(v) if isinstance(v, tuple) else v) for k, v in f.metadata.items()}}
    return out
