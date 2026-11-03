"""Profils de consommation électrique.

Deux modes :
  * courbe de charge importée (CSV, par exemple export Enedis) : recommandé ;
  * profil simplifié : forme journalière et saisonnière fixe, normalisée sur la
    consommation annuelle saisie. Ce profil est ILLUSTRATIF (il n'est pas issu
    de mesures) ; l'interface l'indique. Le taux d'autoconsommation dépend
    fortement du profil réel : importez une courbe mesurée pour une étude fiable.
"""

from __future__ import annotations

import io
import warnings as warnings_module

import numpy as np
import pandas as pd

# Coefficients relatifs, heure locale 0 h -> 23 h (pointes du matin et du soir).
DAILY_SHAPE = np.array([
    0.55, 0.45, 0.40, 0.38, 0.38, 0.42, 0.65, 0.95, 1.00, 0.85, 0.75, 0.75,
    0.85, 0.80, 0.70, 0.65, 0.70, 0.90, 1.25, 1.45, 1.40, 1.20, 0.95, 0.70,
])
# Variante « présence en journée » (télétravail, retraite) : consommation de
# milieu de journée plus forte. Également illustrative.
DAILY_SHAPE_DAYTIME = np.array([
    0.55, 0.45, 0.40, 0.38, 0.38, 0.42, 0.60, 0.85, 0.95, 0.95, 0.95, 1.05,
    1.15, 1.05, 0.95, 0.90, 0.90, 1.00, 1.25, 1.40, 1.30, 1.10, 0.90, 0.70,
])
# Coefficients relatifs, janvier -> décembre (consommation hivernale plus forte).
MONTHLY_SHAPE = np.array([1.35, 1.25, 1.10, 0.95, 0.85, 0.75, 0.72, 0.72, 0.80, 0.95, 1.15, 1.40])

MAX_INTERPOLATED_GAP_H = 3
MAX_MISSING_SHARE = 0.01


class LoadError(ValueError):
    """Courbe de charge inutilisable."""


def simplified_profile(
    index_utc: pd.DatetimeIndex, timezone: str, annual_kwh: float, daytime_presence: bool = False
) -> pd.Series:
    """Profil simplifié (kWh par heure) aligné sur l'index météo."""
    local = index_utc.tz_convert(timezone)
    shape = DAILY_SHAPE_DAYTIME if daytime_presence else DAILY_SHAPE
    weights = shape[local.hour] * MONTHLY_SHAPE[local.month - 1]
    # Consommation annuelle ramenée à la durée de la série (8760 ou 8784 h).
    total = annual_kwh * len(index_utc) / 8760.0
    return pd.Series(weights / weights.sum() * total, index=index_utc)


def parse_load_csv(text: str, timezone: str, unit: str) -> tuple[pd.Series, list[str]]:
    """Lit une courbe de charge CSV : 1re colonne date/heure, 2e colonne valeur.

    unit : "kwh" énergie consommée pendant le pas de temps,
           "kw"  puissance moyenne sur le pas de temps (kW),
           "w"   puissance moyenne sur le pas de temps (W, format des exports Enedis).
    Les horodatages sans fuseau sont interprétés dans `timezone` et marquent le
    début du pas de temps. Retourne une série horaire (kWh, index UTC) et des avertissements.
    """
    if unit not in ("kwh", "kw", "w"):
        raise LoadError("Unité attendue : kwh, kw ou w.")
    try:
        df = pd.read_csv(io.StringIO(text.lstrip("﻿")), sep=None, engine="python", comment="#")
    except Exception as exc:
        raise LoadError("Fichier CSV illisible.") from exc
    if df.shape[1] < 2 or len(df) < 24:
        raise LoadError("Le CSV doit contenir au moins deux colonnes (date, valeur) et une journée de données.")

    raw_times = df.iloc[:, 0].astype(str).str.strip()
    values = pd.to_numeric(df.iloc[:, 1].astype(str).str.replace(",", ".").str.strip(), errors="coerce")
    has_offset = raw_times.str.contains(r"(?:[+-]\d{2}:?\d{2}|Z)$", regex=True).all()
    try:
        if has_offset:
            times = pd.to_datetime(raw_times, utc=True)
        else:
            with warnings_module.catch_warnings():
                # Formats de date hétérogènes : pandas prévient qu'il analyse ligne par ligne.
                warnings_module.simplefilter("ignore", UserWarning)
                times = pd.to_datetime(raw_times, dayfirst=_looks_dayfirst(raw_times.iloc[0]))
            times = times.dt.tz_localize(timezone, ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
    except Exception as exc:
        raise LoadError("Dates illisibles dans la première colonne.") from exc

    warnings: list[str] = []
    s = pd.Series(values.to_numpy(), index=pd.DatetimeIndex(times)).dropna()
    s = s[s.index.notna()]
    s = s[~s.index.duplicated(keep="first")].sort_index()
    if (s < 0).any():
        raise LoadError("Valeurs de consommation négatives dans le fichier.")
    if len(s) < 24:
        raise LoadError("Pas assez de valeurs exploitables dans le fichier.")

    step_h = pd.Series(s.index).diff().dt.total_seconds().median() / 3600.0
    if not step_h or step_h <= 0 or step_h > 1:
        raise LoadError("Pas de temps attendu : 1 h ou moins (ex. 30 min).")
    if unit == "kwh":
        energy = s
    else:
        energy = s * step_h / (1000.0 if unit == "w" else 1.0)

    hourly = energy.resample("h").sum(min_count=1)
    expected_per_hour = round(1.0 / step_h)
    counts = energy.resample("h").count()
    incomplete = counts < expected_per_hour
    hourly[incomplete] = np.nan  # heure partiellement couverte -> inconnue
    return hourly, warnings


def _looks_dayfirst(sample: str) -> bool:
    return bool(pd.Series([sample]).str.match(r"^\d{1,2}[/.-]\d{1,2}[/.-]\d{4}").iloc[0])


def align_to_weather(hourly: pd.Series, index_utc: pd.DatetimeIndex) -> tuple[pd.Series, list[str]]:
    """Aligne une courbe de charge horaire sur l'année météo.

    Si les années diffèrent, on associe les heures par (mois, jour, heure UTC).
    Les petits trous (≤ 3 h consécutives) sont interpolés linéairement et signalés ;
    au-delà de 1 % d'heures manquantes, la courbe est refusée.
    """
    warnings: list[str] = []
    key_src = pd.MultiIndex.from_arrays([hourly.index.month, hourly.index.day, hourly.index.hour])
    src = pd.Series(hourly.to_numpy(), index=key_src)
    src = src[~src.index.duplicated(keep="first")]
    key_dst = pd.MultiIndex.from_arrays([index_utc.month, index_utc.day, index_utc.hour])
    aligned = pd.Series(src.reindex(key_dst).to_numpy(), index=index_utc)
    if hourly.index.year.min() != index_utc.year.min():
        warnings.append(
            f"Courbe de charge {hourly.index.year.min()} associée à la météo {index_utc.year.min()} par date et heure."
        )

    missing = int(aligned.isna().sum())
    if missing:
        if missing > MAX_MISSING_SHARE * len(aligned):
            raise LoadError(
                f"Courbe de charge incomplète : {missing} heures manquantes sur {len(aligned)} "
                f"(maximum {MAX_MISSING_SHARE:.0%}). Fournissez une année complète."
            )
        filled = aligned.interpolate(method="linear", limit=MAX_INTERPOLATED_GAP_H, limit_area="inside")
        if filled.isna().any():
            raise LoadError(
                f"Courbe de charge : trous de plus de {MAX_INTERPOLATED_GAP_H} h consécutives ou en bord de période."
            )
        warnings.append(f"{missing} heures de consommation manquantes complétées par interpolation linéaire.")
        aligned = filled
    return aligned, warnings
