"""Bilan énergétique horaire : autoconsommation, batterie, injection, soutirage.

Stratégie de batterie : autoconsommation maximale (la batterie se charge avec
le surplus PV et se décharge dès que la consommation dépasse la production).
Pas de charge depuis le réseau. Rendement aller-retour réparti à parts égales
entre charge et décharge. La batterie démarre à son état de charge minimal.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .params import Battery


@dataclass
class EnergyFlows:
    """Flux horaires (kWh) et totaux annuels."""

    pv: np.ndarray
    load: np.ndarray
    direct: np.ndarray  # PV consommé directement
    battery_charge: np.ndarray  # énergie prise au PV pour charger (avant pertes)
    battery_discharge: np.ndarray  # énergie fournie à la consommation
    export: np.ndarray
    grid_import: np.ndarray
    soc: np.ndarray  # état de charge en fin d'heure (kWh)

    def totals(self) -> dict[str, float]:
        pv = float(self.pv.sum())
        load = float(self.load.sum())
        export = float(self.export.sum())
        grid_import = float(self.grid_import.sum())
        supplied = load - grid_import  # consommation couverte par le PV (direct + batterie)
        return {
            "pv_kwh": pv,
            "load_kwh": load,
            "direct_kwh": float(self.direct.sum()),
            "battery_charge_kwh": float(self.battery_charge.sum()),
            "battery_discharge_kwh": float(self.battery_discharge.sum()),
            "export_kwh": export,
            "import_kwh": grid_import,
            "self_supplied_kwh": supplied,
            # Part de la production consommée sur place (pertes batterie incluses).
            "self_consumption_rate": (pv - export) / pv if pv > 0 else 0.0,
            # Part de la consommation couverte par le PV.
            "self_sufficiency_rate": supplied / load if load > 0 else 0.0,
        }


def simulate(pv_kwh: np.ndarray, load_kwh: np.ndarray, battery: Battery) -> EnergyFlows:
    pv = np.asarray(pv_kwh, dtype=float)
    load = np.asarray(load_kwh, dtype=float)
    if pv.shape != load.shape:
        raise ValueError("Production et consommation doivent avoir la même longueur.")

    direct = np.minimum(pv, load)
    surplus = pv - direct
    deficit = load - direct
    n = len(pv)

    if not battery.enabled:
        zeros = np.zeros(n)
        return EnergyFlows(pv, load, direct, zeros, zeros.copy(), surplus, deficit, zeros.copy())

    eta = math.sqrt(battery.round_trip_efficiency_pct / 100.0)
    capacity = battery.capacity_kwh
    soc_min = capacity * battery.min_soc_pct / 100.0
    p_max = battery.power_kw  # kWh par heure
    soc = soc_min

    charge = [0.0] * n
    discharge = [0.0] * n
    soc_out = [0.0] * n
    sur = surplus.tolist()
    dem = deficit.tolist()
    # Boucle en flottants Python : plus rapide que des scalaires NumPy, y compris sous Pyodide.
    for i in range(n):
        s = sur[i]
        if s > 0.0:
            c = min(s, p_max, (capacity - soc) / eta)
            if c > 0.0:
                soc += c * eta
                charge[i] = c
        else:
            d = dem[i]
            if d > 0.0:
                out = min(d, p_max, (soc - soc_min) * eta)
                if out > 0.0:
                    soc -= out / eta
                    discharge[i] = out
        soc_out[i] = soc

    charge_a = np.array(charge)
    discharge_a = np.array(discharge)
    return EnergyFlows(
        pv=pv,
        load=load,
        direct=direct,
        battery_charge=charge_a,
        battery_discharge=discharge_a,
        export=surplus - charge_a,
        grid_import=deficit - discharge_a,
        soc=np.array(soc_out),
    )
