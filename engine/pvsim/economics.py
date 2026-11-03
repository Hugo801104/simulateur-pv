"""Calcul économique sur la durée d'étude.

Hypothèses (documentées dans docs/ARCHITECTURE.md) :
  * Année 1 = résultat de la simulation horaire. Les années suivantes, la
    production diminue de la dégradation annuelle ; l'énergie autoconsommée et
    l'énergie injectée sont réduites dans la même proportion.
  * Gains annuels = électricité non achetée × prix + énergie injectée × tarif.
  * Les flux sont comptés en fin d'année et actualisés au taux choisi.
  * Coûts : investissement initial (net des aides), maintenance annuelle,
    remplacement de l'onduleur et de la batterie aux années indiquées.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.optimize import brentq

from .params import Economics


def capex(econ: Economics, pv_kwc: float, battery_kwh: float) -> float:
    gross = pv_kwc * econ.pv_capex_eur_per_kwc + battery_kwh * econ.battery_capex_eur_per_kwh + econ.fixed_capex_eur
    return gross - econ.subsidy_eur


def evaluate(econ: Economics, pv_kwc: float, battery_kwh: float, totals: dict[str, float]) -> dict:
    n_years = econ.lifetime_years
    years = np.arange(1, n_years + 1)
    r = econ.discount_rate_pct / 100.0
    deg = (1.0 - econ.degradation_pct_per_year / 100.0) ** (years - 1)
    price = econ.electricity_price_eur_per_kwh * (1 + econ.electricity_price_escalation_pct / 100.0) ** (years - 1)
    tariff = econ.export_tariff_eur_per_kwh * (1 + econ.export_tariff_escalation_pct / 100.0) ** (years - 1)

    production = totals["pv_kwh"] * deg
    savings = totals["self_supplied_kwh"] * deg * price
    sales = totals["export_kwh"] * deg * tariff

    invest = capex(econ, pv_kwc, battery_kwh)
    gross_invest = invest + econ.subsidy_eur
    opex = np.full(n_years, gross_invest * econ.opex_pct_of_capex / 100.0)
    replacements = np.zeros(n_years)
    if 0 < econ.inverter_replacement_year < n_years:
        replacements[econ.inverter_replacement_year - 1] += pv_kwc * econ.inverter_replacement_eur_per_kwc
    if battery_kwh > 0 and econ.battery_lifetime_years > 0:
        battery_cost = battery_kwh * econ.battery_capex_eur_per_kwh * econ.battery_replacement_pct / 100.0
        for y in range(econ.battery_lifetime_years, n_years, econ.battery_lifetime_years):
            replacements[y - 1] += battery_cost

    cashflow = savings + sales - opex - replacements
    discount = (1.0 + r) ** -years
    npv = -invest + float(np.sum(cashflow * discount))
    cumulative = -invest + np.cumsum(cashflow)
    cumulative_disc = -invest + np.cumsum(cashflow * discount)

    disc_production = float(np.sum(production * discount))
    lcoe = (invest + float(np.sum((opex + replacements) * discount))) / disc_production if disc_production > 0 else None

    bill_without = totals["load_kwh"] * econ.electricity_price_eur_per_kwh
    bill_with = totals["import_kwh"] * econ.electricity_price_eur_per_kwh - totals["export_kwh"] * econ.export_tariff_eur_per_kwh

    return {
        "capex_eur": invest,
        "npv_eur": npv,
        "irr": irr(invest, cashflow),
        "payback_years": _payback(invest, cashflow),
        "discounted_payback_years": _payback(invest, cashflow * discount),
        "lcoe_eur_per_kwh": lcoe,
        "year1_savings_eur": float(savings[0] + sales[0]),
        "year1_bill_without_pv_eur": bill_without,
        "year1_bill_with_pv_eur": bill_with,
        "yearly": {
            "year": years.tolist(),
            "production_kwh": production.tolist(),
            "savings_eur": savings.tolist(),
            "sales_eur": sales.tolist(),
            "opex_eur": opex.tolist(),
            "replacements_eur": replacements.tolist(),
            "cashflow_eur": cashflow.tolist(),
            "cumulative_eur": cumulative.tolist(),
            "cumulative_discounted_eur": cumulative_disc.tolist(),
        },
    }


def irr(invest: float, cashflow: np.ndarray) -> float | None:
    """Taux de rentabilité interne, ou None s'il n'existe pas (pas de changement de signe)."""
    if invest <= 0:
        return None
    years = np.arange(1, len(cashflow) + 1)

    def npv_at(rate: float) -> float:
        return -invest + float(np.sum(cashflow / (1.0 + rate) ** years))

    lo, hi = -0.99, 1.0
    f_lo, f_hi = npv_at(lo), npv_at(hi)
    if math.isnan(f_lo) or math.isnan(f_hi) or f_lo * f_hi > 0:
        return None
    return float(brentq(npv_at, lo, hi, xtol=1e-10))


def _payback(invest: float, cashflow: np.ndarray) -> float | None:
    """Année (fractionnaire) où le cumul des flux couvre l'investissement."""
    if invest <= 0:
        return 0.0
    cumulative = -invest
    for i, cf in enumerate(cashflow):
        nxt = cumulative + cf
        if nxt >= 0 and cf > 0:
            return i + (-cumulative) / cf
        cumulative = nxt
    return None
