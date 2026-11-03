"""Lecture et normalisation des données météorologiques.

Le réseau est géré par l'interface (fetch du navigateur) : ce module ne reçoit
que le texte brut des réponses ou des fichiers. Il le convertit dans un format
commun et vérifie qu'il est complet. Aucune valeur manquante n'est inventée :
une série incomplète est refusée avec un message explicite.

Format commun (`WeatherData.data`) :
    index        début de chaque heure, UTC, pas horaire régulier
    ghi, dni, dhi  irradiances moyennes (W/m²)
    temp_air     température à 2 m (°C)
    wind_speed   vent à 10 m (m/s)

`solar_offset_min` donne l'instant représentatif de chaque valeur, en minutes
après le début de l'heure. Il sert au calcul de la position du soleil :
    Open-Meteo   valeur moyenne sur l'heure précédant l'horodatage -> début = horodatage - 1 h, décalage 30 min
    NASA POWER   valeur moyenne sur l'heure suivant l'horodatage   -> début = horodatage, décalage 30 min
    PVGIS (TMY)  valeur instantanée décalée de « Irradiance Time Offset » (fourni dans le fichier)
Ces conventions ont été vérifiées sur données réelles (corrélation avec un ciel clair, voir tests).
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

COLUMNS = ["ghi", "dni", "dhi", "temp_air", "wind_speed"]

SOURCES = {
    "openmeteo": "Open-Meteo (réanalyse ERA5)",
    "nasapower": "NASA POWER",
    "pvgis_tmy": "PVGIS – année météorologique type (fichier importé)",
}


class WeatherError(ValueError):
    """Données météo inutilisables (format inattendu, valeurs manquantes…)."""


@dataclass
class WeatherData:
    data: pd.DataFrame
    source: str
    latitude: float
    longitude: float
    elevation: float | None
    solar_offset_min: float
    notes: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        idx = self.data.index
        return {
            "source": self.source,
            "source_label": SOURCES.get(self.source, self.source),
            "latitude": self.latitude,
            "longitude": self.longitude,
            "elevation": self.elevation,
            "start": idx[0].isoformat(),
            "end": idx[-1].isoformat(),
            "hours": int(len(idx)),
            # Irradiation annuelle moyenne (la série peut couvrir plusieurs années).
            "ghi_kwh_m2": float(self.data["ghi"].sum() / 1000.0 * 8760.0 / len(idx)),
            "years": round(len(idx) / 8766.0, 1),
            "temp_mean_c": float(self.data["temp_air"].mean()),
            "notes": list(self.notes),
        }


def parse(source: str, raw: str) -> WeatherData:
    """Lit le texte brut d'une source connue."""
    parsers = {
        "openmeteo": parse_openmeteo,
        "nasapower": parse_nasapower,
        "pvgis_tmy": parse_pvgis_tmy,
    }
    if source not in parsers:
        raise WeatherError(f"Source météo inconnue : {source}")
    return parsers[source](raw)


def _load_json(raw: str, source: str) -> dict:
    try:
        return json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise WeatherError(f"Réponse {source} illisible (JSON invalide).") from exc


def parse_openmeteo(raw: str) -> WeatherData:
    doc = _load_json(raw, "Open-Meteo")
    if doc.get("error"):
        raise WeatherError(f"Open-Meteo a renvoyé une erreur : {doc.get('reason', 'inconnue')}")
    hourly = doc.get("hourly") or {}
    mapping = {
        "shortwave_radiation": "ghi",
        "direct_normal_irradiance": "dni",
        "diffuse_radiation": "dhi",
        "temperature_2m": "temp_air",
        "wind_speed_10m": "wind_speed",
    }
    missing = [k for k in ["time", *mapping] if k not in hourly]
    if missing:
        raise WeatherError(f"Réponse Open-Meteo incomplète : variables absentes {', '.join(missing)}.")
    if doc.get("utc_offset_seconds", 0) != 0:
        raise WeatherError("Réponse Open-Meteo attendue en UTC (paramètre timezone=GMT).")
    units = doc.get("hourly_units", {})
    if units.get("wind_speed_10m") not in (None, "m/s"):
        raise WeatherError("Vitesse du vent Open-Meteo attendue en m/s (paramètre wind_speed_unit=ms).")

    labels = pd.to_datetime(hourly["time"]).tz_localize("UTC")
    df = pd.DataFrame({dst: pd.to_numeric(pd.Series(hourly[src]), errors="coerce").to_numpy(dtype=float) for src, dst in mapping.items()})
    df.index = labels - pd.Timedelta(hours=1)  # horodatage = fin de l'intervalle
    df = _check(df, "Open-Meteo")
    return WeatherData(
        data=df,
        source="openmeteo",
        latitude=float(doc["latitude"]),
        longitude=float(doc["longitude"]),
        elevation=float(doc["elevation"]) if doc.get("elevation") is not None else None,
        solar_offset_min=30.0,
        notes=["Point de grille Open-Meteo le plus proche : coordonnées légèrement différentes du site."],
    )


def parse_nasapower(raw: str) -> WeatherData:
    doc = _load_json(raw, "NASA POWER")
    if "messages" in doc and "properties" not in doc:
        raise WeatherError("NASA POWER a renvoyé une erreur : " + "; ".join(map(str, doc.get("messages") or ["inconnue"])))
    try:
        params = doc["properties"]["parameter"]
        lon, lat, *rest = doc["geometry"]["coordinates"]
    except (KeyError, TypeError, ValueError) as exc:
        raise WeatherError("Réponse NASA POWER au format inattendu.") from exc
    header = doc.get("header", {})
    if header.get("time_standard", "UTC").upper() != "UTC":
        raise WeatherError("Réponse NASA POWER attendue en UTC (paramètre time-standard=UTC).")
    fill = header.get("fill_value", -999.0)
    mapping = {
        "ALLSKY_SFC_SW_DWN": "ghi",
        "ALLSKY_SFC_SW_DNI": "dni",
        "ALLSKY_SFC_SW_DIFF": "dhi",
        "T2M": "temp_air",
        "WS10M": "wind_speed",
    }
    missing = [k for k in mapping if k not in params]
    if missing:
        raise WeatherError(f"Réponse NASA POWER incomplète : variables absentes {', '.join(missing)}.")
    keys = list(params["ALLSKY_SFC_SW_DWN"].keys())
    index = pd.to_datetime(keys, format="%Y%m%d%H").tz_localize("UTC")
    df = pd.DataFrame(
        {dst: [params[src].get(k, np.nan) for k in keys] for src, dst in mapping.items()},
        index=index,
        dtype=float,
    )
    df = df.mask(df <= fill + 1e-9)  # valeurs de remplissage -> manquantes
    df = _check(df, "NASA POWER")
    return WeatherData(
        data=df,
        source="nasapower",
        latitude=float(lat),
        longitude=float(lon),
        elevation=float(rest[0]) if rest else None,
        solar_offset_min=30.0,
        notes=["Résolution spatiale NASA POWER d'environ 0,5° : à réserver aux études préliminaires."],
    )


def parse_pvgis_tmy(raw: str) -> WeatherData:
    """Fichier TMY PVGIS (CSV ou JSON) lu avec le lecteur officiel de pvlib."""
    from pvlib.iotools import read_pvgis_tmy

    text = raw.lstrip("﻿")
    fmt = "json" if text.lstrip().startswith("{") else "csv"
    try:
        # pvlib lit le CSV en binaire et le JSON en texte.
        buffer = io.BytesIO(text.encode("utf-8")) if fmt == "csv" else io.StringIO(text)
        data, meta = read_pvgis_tmy(buffer, pvgis_format=fmt, map_variables=True)
    except Exception as exc:
        raise WeatherError("Fichier PVGIS illisible : seul l'export « TMY » (CSV ou JSON) est pris en charge.") from exc

    inputs = meta.get("inputs", {})
    loc = inputs.get("location", inputs)  # JSON : inputs.location ; CSV : inputs
    offset_h = loc.get("irradiance_time_offset", loc.get("irradiance time offset", 0.0)) or 0.0
    df = data[COLUMNS].astype(float).copy()
    # Une TMY assemble des mois d'années différentes : on la ramène sur une
    # année non bissextile commune pour obtenir une série continue.
    year = 2023
    idx = df.index
    df.index = pd.DatetimeIndex(
        [pd.Timestamp(year=year, month=t.month, day=t.day, hour=t.hour, tz="UTC") for t in idx]
    )
    df = df.sort_index()
    df = _check(df, "PVGIS")
    months = meta.get("months_selected", [])
    notes = ["Année type (TMY) ramenée sur un calendrier 2023 non bissextile."]
    if months:
        notes.append("Mois sélectionnés : " + ", ".join(f"{m['month']}/{m['year']}" for m in months))
    return WeatherData(
        data=df,
        source="pvgis_tmy",
        latitude=float(loc["latitude"]),
        longitude=float(loc["longitude"]),
        elevation=float(loc["elevation"]) if loc.get("elevation") is not None else None,
        solar_offset_min=float(offset_h) * 60.0,
        notes=notes,
    )


def _check(df: pd.DataFrame, label: str) -> pd.DataFrame:
    """Vérifie qu'une série horaire est complète et physiquement plausible."""
    df = df[COLUMNS]
    if df.index.has_duplicates:
        raise WeatherError(f"Données {label} : horodatages en double.")
    df = df.sort_index()
    if len(df) < 24 * 365:
        raise WeatherError(f"Données {label} : {len(df)} heures reçues, une année complète (8760 h) est nécessaire.")
    expected = pd.date_range(df.index[0], df.index[-1], freq="h")
    if len(expected) != len(df):
        raise WeatherError(f"Données {label} : {len(expected) - len(df)} heures absentes de la série.")
    n_missing = int(df.isna().any(axis=1).sum())
    if n_missing:
        raise WeatherError(
            f"Données {label} : {n_missing} heures sans valeur. Aucune valeur n'est inventée ; "
            "choisissez une autre année ou une autre source."
        )
    # Petites valeurs négatives (bruit numérique des réanalyses) ramenées à 0.
    for col in ("ghi", "dni", "dhi"):
        if (df[col] < -5).any():
            raise WeatherError(f"Données {label} : irradiance {col} négative.")
        df[col] = df[col].clip(lower=0.0)
    if (df["ghi"] > 1500).any() or (df["dni"] > 1400).any():
        raise WeatherError(f"Données {label} : irradiances physiquement impossibles (> 1500 W/m²).")
    if ((df["temp_air"] < -90) | (df["temp_air"] > 65)).any():
        raise WeatherError(f"Données {label} : températures hors plage plausible.")
    df.index.freq = "h"
    return df
