"""Optimisation du dimensionnement (puissance PV × capacité batterie).

Recherche exhaustive sur une grille : chaque combinaison est simulée heure par
heure puis évaluée économiquement. La production est proportionnelle à la
puissance crête (voir physics.py), on réutilise donc le profil par kWc.
Une grille exhaustive est préférée à un optimiseur numérique : le problème est
petit, non lisse (écrêtage, batterie) et l'utilisateur voit toutes les options.
"""

from __future__ import annotations

import math

import numpy as np

from . import economics
from .params import Battery, Economics, Optimisation
from .simulation import simulate


def pv_sizes(opt: Optimisation) -> list[float]:
    count = math.floor((opt.pv_max_kwc - opt.pv_min_kwc) / opt.pv_step_kwc + 1e-9) + 1
    return [round(opt.pv_min_kwc + i * opt.pv_step_kwc, 6) for i in range(count)]


def run(
    pv_kwh_per_kwc: np.ndarray,
    load_kwh: np.ndarray,
    battery_template: Battery,
    econ: Economics,
    opt: Optimisation,
) -> dict:
    rows = []
    for battery_kwh in opt.battery_sizes_kwh:
        battery = Battery(
            capacity_kwh=battery_kwh,
            power_kw=battery_kwh * opt.battery_c_rate,
            round_trip_efficiency_pct=battery_template.round_trip_efficiency_pct,
            min_soc_pct=battery_template.min_soc_pct,
        )
        for kwc in pv_sizes(opt):
            totals = simulate(pv_kwh_per_kwc * kwc, load_kwh, battery).totals()
            eco = economics.evaluate(econ, kwc, battery_kwh, totals)
            rows.append({
                "pv_kwc": kwc,
                "battery_kwh": battery_kwh,
                "battery_kw": battery.power_kw,
                "pv_kwh": totals["pv_kwh"],
                "self_consumption_rate": totals["self_consumption_rate"],
                "self_sufficiency_rate": totals["self_sufficiency_rate"],
                "capex_eur": eco["capex_eur"],
                "npv_eur": eco["npv_eur"],
                "irr": eco["irr"],
                "payback_years": eco["payback_years"],
                "lcoe_eur_per_kwh": eco["lcoe_eur_per_kwh"],
            })

    if opt.objective == "irr":
        def score(row: dict) -> float:
            return row["irr"] if row["irr"] is not None else -math.inf
    else:
        def score(row: dict) -> float:
            return row["npv_eur"]

    best = max(rows, key=score)
    if score(best) == -math.inf:
        best = None

    notes = []
    if best is not None:
        sizes = pv_sizes(opt)
        if len(sizes) > 1 and best["pv_kwc"] in (sizes[0], sizes[-1]):
            bound = "minimale" if best["pv_kwc"] == sizes[0] else "maximale"
            notes.append(
                f"L'optimum est à la puissance {bound} testée ({best['pv_kwc']:g} kWc) : "
                "élargissez la plage pour vérifier qu'il ne se trouve pas au-delà."
            )
        batteries = opt.battery_sizes_kwh
        if len(batteries) > 1 and best["battery_kwh"] == batteries[-1] and batteries[-1] > 0:
            notes.append("L'optimum utilise la plus grande batterie testée : ajoutez des capacités supérieures.")
    return {"objective": opt.objective, "rows": rows, "best": best, "notes": notes}
