"""Modèles physiques de la chaîne photovoltaïque, tous issus de pvlib.

Chaîne de calcul, pour chaque heure :
    1. Position du soleil (NREL SPA)                       pvlib.solarposition
    2. Irradiance dans le plan des modules (Perez 1990)   pvlib.irradiance.get_total_irradiance
    3. Pertes optiques par angle d'incidence (Fresnel)    pvlib.iam.physical / marion_diffuse
    4. Température des cellules (Faiman)                  pvlib.temperature.faiman
    5. Puissance DC (PVWatts)                             pvlib.pvsystem.pvwatts_dc
    6. Pertes système (salissures, câblage, mismatch…)    pourcentage global, comme PVGIS
    7. Onduleur avec écrêtage (PVWatts)                   pvlib.inverter.pvwatts

Toute la chaîne est linéaire en puissance crête quand le ratio DC/AC est
constant : on calcule donc une production « par kWc » une seule fois, puis
l'optimisation la multiplie par chaque taille testée.

Non modélisé (voir docs/ARCHITECTURE.md) : ombrage du relief et proche,
effets spectraux, neige.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import pvlib

from .params import PVSystem, Site
from .weather import WeatherData


@dataclass
class PVProfile:
    """Résultat physique horaire pour 1 kWc installé."""

    ac_kwh_per_kwc: pd.Series  # énergie AC par heure (kWh/kWc)
    poa_global: pd.Series  # irradiance dans le plan (W/m²)
    temp_cell: pd.Series  # température des cellules (°C)

    def annual_yield(self) -> float:
        """Productible spécifique (kWh/kWc), ramené à 365 jours."""
        return float(self.ac_kwh_per_kwc.sum() * 8760.0 / len(self.ac_kwh_per_kwc))

    def annual_poa_kwh_m2(self) -> float:
        return float(self.poa_global.sum() / 1000.0 * 8760.0 / len(self.poa_global))


def compute_pv_profile(weather: WeatherData, site: Site, pv: PVSystem) -> PVProfile:
    df = weather.data
    altitude = site.altitude if site.altitude is not None else (weather.elevation or 0.0)
    times = df.index + pd.Timedelta(minutes=weather.solar_offset_min)

    solpos = pvlib.solarposition.get_solarposition(times, site.latitude, site.longitude, altitude=altitude)
    dni_extra = pvlib.irradiance.get_extra_radiation(times).to_numpy()
    airmass = pvlib.atmosphere.get_relative_airmass(solpos["apparent_zenith"].to_numpy())

    ghi = df["ghi"].to_numpy()
    dhi = df["dhi"].to_numpy()
    dni = df["dni"].to_numpy()
    zenith = solpos["apparent_zenith"].to_numpy()
    azimuth = solpos["azimuth"].to_numpy()
    # Soleil sous l'horizon : pas de composante directe.
    dni = np.where(zenith >= 90.0, 0.0, dni)

    poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=pv.tilt_deg,
        surface_azimuth=pv.azimuth_deg,
        solar_zenith=zenith,
        solar_azimuth=azimuth,
        dni=dni,
        ghi=ghi,
        dhi=dhi,
        dni_extra=dni_extra,
        airmass=airmass,
        albedo=pv.albedo,
        model="perez",
    )
    poa_direct = np.nan_to_num(np.asarray(poa["poa_direct"], dtype=float), nan=0.0)
    poa_sky = np.nan_to_num(np.asarray(poa["poa_sky_diffuse"], dtype=float), nan=0.0)
    poa_ground = np.nan_to_num(np.asarray(poa["poa_ground_diffuse"], dtype=float), nan=0.0)
    poa_global = np.clip(poa_direct + poa_sky + poa_ground, 0.0, None)

    aoi = pvlib.irradiance.aoi(pv.tilt_deg, pv.azimuth_deg, zenith, azimuth)
    iam_beam = np.nan_to_num(np.asarray(pvlib.iam.physical(aoi), dtype=float), nan=0.0)
    iam_diffuse = pvlib.iam.marion_diffuse("physical", pv.tilt_deg)
    effective = np.clip(
        poa_direct * iam_beam + poa_sky * float(iam_diffuse["sky"]) + poa_ground * float(iam_diffuse["ground"]),
        0.0,
        None,
    )

    temp_cell = pvlib.temperature.faiman(
        poa_global, df["temp_air"].to_numpy(), df["wind_speed"].to_numpy(), u0=pv.faiman_u0, u1=pv.faiman_u1
    )

    pdc0 = 1000.0  # 1 kWc, en W
    pdc = pvlib.pvsystem.pvwatts_dc(effective, temp_cell, pdc0, pv.gamma_pdc_pct_per_c / 100.0)
    pdc = np.clip(np.asarray(pdc, dtype=float), 0.0, None) * (1.0 - pv.system_losses_pct / 100.0)

    eta = pv.inverter_efficiency_pct / 100.0
    pac0 = pdc0 / pv.dc_ac_ratio  # puissance AC nominale de l'onduleur (W)
    pac = pvlib.inverter.pvwatts(pdc, pdc0=pac0 / eta, eta_inv_nom=eta)
    pac = np.clip(np.nan_to_num(np.asarray(pac, dtype=float), nan=0.0), 0.0, None)

    index = df.index
    return PVProfile(
        ac_kwh_per_kwc=pd.Series(pac / 1000.0, index=index),  # W moyens sur 1 h -> kWh
        poa_global=pd.Series(poa_global, index=index),
        temp_cell=pd.Series(np.asarray(temp_cell, dtype=float), index=index),
    )
