"""Point d'entrée du moteur pour l'interface (texte JSON en entrée et en sortie).

Toutes les fonctions publiques renvoient une chaîne JSON de la forme
    {"ok": true, ...résultat}   ou   {"ok": false, "errors": [{"field", "message"}]}
afin que l'interface n'ait jamais à interpréter une exception Python.

L'état (météo et courbe de charge chargées) est conservé dans `Engine`, une
instance par Web Worker.
"""

from __future__ import annotations

import dataclasses
import io
import json
import math
from typing import Any, Callable

import numpy as np
import pandas as pd

from . import __version__, economics, load, optimisation, physics, weather
from .params import Params, ValidationError, defaults, parse_params
from .simulation import simulate

DISTANCE_WARNING_KM = 25.0


def _clean(value: Any) -> Any:
    """Rend un objet sérialisable en JSON strict (NaN/inf -> null)."""
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, (np.floating, float)):
        f = float(value)
        return f if math.isfinite(f) else None
    if isinstance(value, np.integer):
        return int(value)
    return value


def _respond(fn: Callable[[], dict]) -> str:
    try:
        result = fn()
        return json.dumps(_clean({"ok": True, **result}), ensure_ascii=False)
    except ValidationError as exc:
        return json.dumps({"ok": False, "errors": exc.errors}, ensure_ascii=False)
    except (weather.WeatherError, load.LoadError, ValueError) as exc:
        return json.dumps({"ok": False, "errors": [{"field": "", "message": str(exc)}]}, ensure_ascii=False)
    except Exception as exc:  # erreur inattendue : message technique explicite
        return json.dumps(
            {"ok": False, "errors": [{"field": "", "message": f"Erreur interne du moteur : {type(exc).__name__}: {exc}"}]},
            ensure_ascii=False,
        )


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))


class Engine:
    def __init__(self) -> None:
        self.weather: weather.WeatherData | None = None
        self.load_hourly: pd.Series | None = None
        self.load_warnings: list[str] = []
        self.last_hourly: pd.DataFrame | None = None
        self._profile_key: tuple | None = None
        self._profile: physics.PVProfile | None = None

    # -- Données d'entrée -------------------------------------------------
    def info(self) -> str:
        import pvlib
        import scipy

        return _respond(lambda: {
            "engine_version": __version__,
            "pvlib": pvlib.__version__,
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scipy": scipy.__version__,
            "defaults": defaults(),
        })

    def set_weather(self, source: str, raw: str) -> str:
        def run() -> dict:
            self.weather = weather.parse(source, raw)
            self._profile_key = None
            return {"weather": self.weather.summary()}

        return _respond(run)

    def set_load_csv(self, text: str, timezone: str, unit: str) -> str:
        def run() -> dict:
            hourly, warnings = load.parse_load_csv(text, timezone, unit)
            self.load_hourly, self.load_warnings = hourly, warnings
            valid = hourly.dropna()
            return {
                "load": {
                    "start": valid.index[0].isoformat(),
                    "end": valid.index[-1].isoformat(),
                    "hours": int(len(valid)),
                    "total_kwh": float(valid.sum()),
                    "warnings": warnings,
                }
            }

        return _respond(run)

    def clear_load_csv(self) -> str:
        self.load_hourly = None
        return _respond(lambda: {})

    # -- Calculs ----------------------------------------------------------
    def _prepare(self, params_json: str) -> tuple[Params, physics.PVProfile, np.ndarray, list[str], list[str]]:
        """Valide les paramètres et prépare production par kWc et consommation.

        Renvoie aussi deux listes de messages : `warnings` (à vérifier par
        l'utilisateur) et `notes` (informations sur les données utilisées).
        """
        try:
            raw = json.loads(params_json)
        except ValueError as exc:
            raise ValidationError([{"field": "", "message": "paramètres JSON invalides"}]) from exc
        p = parse_params(raw)
        if self.weather is None:
            raise ValueError("Aucune donnée météo chargée : téléchargez-les ou importez un fichier PVGIS.")
        notes: list[str] = list(self.weather.notes)
        warnings: list[str] = []
        dist = _distance_km(p.site.latitude, p.site.longitude, self.weather.latitude, self.weather.longitude)
        if dist > DISTANCE_WARNING_KM:
            warnings.append(f"Les données météo correspondent à un point situé à {dist:.0f} km du site saisi.")

        # Le profil par kWc ne dépend pas de la puissance crête : on le met en cache.
        key = (p.site, dataclasses.replace(p.pv, peak_power_kwc=1.0), id(self.weather))
        if key != self._profile_key:
            self._profile = physics.compute_pv_profile(self.weather, p.site, p.pv)
            self._profile_key = key
        assert self._profile is not None

        index = self.weather.data.index
        if p.load.mode == "csv":
            if self.load_hourly is None:
                raise ValueError("Aucune courbe de charge importée.")
            load_series, load_warn = load.align_to_weather(self.load_hourly, index)
            warnings += self.load_warnings + load_warn
        else:
            load_series = load.simplified_profile(index, p.site.timezone, p.load.annual_kwh)
            notes.append("Consommation : profil simplifié illustratif. Importez votre courbe de charge pour un résultat fiable.")
        return p, self._profile, load_series.to_numpy(dtype=float), warnings, notes

    def simulate(self, params_json: str) -> str:
        def run() -> dict:
            p, profile, load_kwh, warnings, notes = self._prepare(params_json)
            pv_kwh = profile.ac_kwh_per_kwc.to_numpy() * p.pv.peak_power_kwc
            flows = simulate(pv_kwh, load_kwh, p.battery)
            totals = flows.totals()
            eco = economics.evaluate(p.economics, p.pv.peak_power_kwc, p.battery.capacity_kwh if p.battery.enabled else 0.0, totals)

            index = self.weather.data.index  # type: ignore[union-attr]
            frame = pd.DataFrame({
                "pv_kwh": flows.pv,
                "load_kwh": flows.load,
                "direct_kwh": flows.direct,
                "battery_charge_kwh": flows.battery_charge,
                "battery_discharge_kwh": flows.battery_discharge,
                "export_kwh": flows.export,
                "import_kwh": flows.grid_import,
                "battery_soc_kwh": flows.soc,
                "poa_w_m2": profile.poa_global.to_numpy(),
                "temp_cell_c": profile.temp_cell.to_numpy(),
            }, index=index)
            self.last_hourly = frame
            local_month = index.tz_convert(p.site.timezone).month
            monthly = frame.drop(columns=["battery_soc_kwh", "poa_w_m2", "temp_cell_c"]).groupby(local_month).sum()

            # Journée type (moyenne par heure locale) pour le graphique journalier.
            local_hour = index.tz_convert(p.site.timezone).hour
            daily = frame[["pv_kwh", "load_kwh", "import_kwh", "export_kwh"]].groupby(local_hour).mean()

            return {
                "warnings": warnings,
                "notes": notes,
                "weather": self.weather.summary(),  # type: ignore[union-attr]
                "specific_yield_kwh_per_kwc": profile.annual_yield(),
                "poa_kwh_m2": profile.annual_poa_kwh_m2(),
                "totals": totals,
                "economics": eco,
                "monthly": {"month": monthly.index.tolist(), **{c: monthly[c].tolist() for c in monthly.columns}},
                "daily_profile": {"hour": daily.index.tolist(), **{c: daily[c].tolist() for c in daily.columns}},
            }

        return _respond(run)

    def optimise(self, params_json: str) -> str:
        def run() -> dict:
            p, profile, load_kwh, warnings, notes = self._prepare(params_json)
            result = optimisation.run(profile.ac_kwh_per_kwc.to_numpy(), load_kwh, p.battery, p.economics, p.optimisation)
            return {"warnings": result.pop("notes") + warnings, "notes": notes, "optimisation": result}

        return _respond(run)

    def hourly_csv(self) -> str:
        def run() -> dict:
            if self.last_hourly is None:
                raise ValueError("Lancez une simulation avant d'exporter.")
            buf = io.StringIO()
            out = self.last_hourly.copy()
            out.index.name = "debut_heure_utc"
            out.round(4).to_csv(buf, sep=";", decimal=",")
            return {"csv": buf.getvalue()}

        return _respond(run)


ENGINE = Engine()
