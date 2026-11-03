import numpy as np

from pvsim import optimisation
from pvsim.params import Battery, Economics, Optimisation

PV_PER_KWC = np.clip(np.sin(np.linspace(0, 365 * 2 * np.pi, 8760)) * 0.45, 0, None)
LOAD = np.full(8760, 0.5)


def test_grid_and_best():
    opt = Optimisation(pv_min_kwc=1, pv_max_kwc=6, pv_step_kwc=1, battery_sizes_kwh=(0.0, 5.0))
    r = optimisation.run(PV_PER_KWC, LOAD, Battery(), Economics(), opt)
    assert len(r["rows"]) == 12
    assert optimisation.pv_sizes(opt) == [1, 2, 3, 4, 5, 6]
    assert r["best"]["npv_eur"] == max(row["npv_eur"] for row in r["rows"])


def test_irr_objective():
    opt = Optimisation(pv_min_kwc=1, pv_max_kwc=4, pv_step_kwc=1, battery_sizes_kwh=(0.0,), objective="irr")
    r = optimisation.run(PV_PER_KWC, LOAD, Battery(), Economics(), opt)
    irrs = [row["irr"] for row in r["rows"] if row["irr"] is not None]
    assert r["best"]["irr"] == max(irrs)


def test_free_export_makes_bigger_better():
    # Si la revente paie autant que l'achat, la plus grande installation est la meilleure.
    econ = Economics(export_tariff_eur_per_kwh=0.2016)
    opt = Optimisation(pv_min_kwc=1, pv_max_kwc=5, pv_step_kwc=1, battery_sizes_kwh=(0.0,))
    r = optimisation.run(PV_PER_KWC, LOAD, Battery(), econ, opt)
    assert r["best"]["pv_kwc"] == 5
