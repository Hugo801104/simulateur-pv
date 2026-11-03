"""Mode Conseil : recommandations à partir des seules informations sur la maison.

Démarche :
  1. Géométrie : orientation et pente du toit -> plan des modules ; surface du
     pan -> nombre maximal de modules (taux d'occupation, voir knowledge.py).
  2. Consommation : relevé de facture, ou ordre de grandeur selon le foyer.
  3. Production horaire par kWc (pvlib, météo réelle du site), une seule fois.
  4. Évaluation de toutes les tailles possibles (au module près) avec et sans
     batterie : bilan horaire + économie avec les prix et tarifs en vigueur
     (TVA réduite ≤ 9 kWc, rachat du surplus, durée du contrat).
  5. Recommandation (meilleure VAN, budget éventuel) et conseils : modules,
     onduleur, batterie, pose, structure, démarches. Chaque conseil cite ses sources.

Rien n'est inventé : les points non modélisés (ombrage, état de la charpente)
sont signalés comme tels et renvoyés à une visite technique.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import economics, knowledge as K, load, physics
from .params import Battery, Economics, PVSystem, Site, ValidationError, _parse_group
from .simulation import simulate
from .weather import WeatherData

MIN_PANELS = 2
MAX_PANELS = 80  # ≈ 35 kWc : au-delà, on sort du résidentiel
# Le modèle de prix est ajusté sur des fourchettes publiées de 3 à 9 kWc : on
# ne recommande pas en dessous de 3 kWc (extrapolation des frais fixes non fiable),
# sauf si le toit ne permet pas plus.
PRICE_MODEL_MIN_KWC = 3.0
PRICE_MODEL_MAX_KWC = 9.0
BATTERY_SIZES_KWH = (0.0, 5.0, 10.0)
BATTERY_C_RATE = 0.5
PLATEAU_TOLERANCE_EUR = 300.0


def _int(x: float) -> str:
    """Entier à la française : 12 345 (espace insécable fine)."""
    return f"{x:,.0f}".replace(",", " ")


def _pct(ratio: float) -> str:
    return f"{ratio * 100:.0f} %"


def _fr(x: float, digits: int = 2) -> str:
    """Nombre décimal à la française, sans zéros inutiles : 3,08 ; 5."""
    text = f"{x:.{digits}f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _choice(default: str, choices, label: str):
    return field(default=default, metadata={"choices": tuple(choices), "label": label})


def _num(default, lo, hi, label, *, integer=False, optional=False):
    return field(default=default, metadata={"min": lo, "max": hi, "label": label, "integer": integer, "optional": optional})


@dataclass(frozen=True)
class House:
    latitude: float = _num(45.76, -90, 90, "Latitude")
    longitude: float = _num(4.84, -180, 180, "Longitude")
    timezone: str = field(default="Europe/Paris", metadata={"label": "Fuseau horaire"})
    # Toiture
    roof_type: str = _choice("tuiles_mecaniques", K.ROOF_TYPES, "Type de couverture")
    orientation: str = _choice("S", [*K.ORIENTATIONS, "EO"], "Orientation du pan")
    slope: str = _choice("moyenne", K.SLOPES, "Pente du toit")
    tilt_deg: float | None = _num(None, 0, 90, "Inclinaison exacte (°)", optional=True)
    roof_area_m2: float = _num(30.0, 2, 2000, "Surface du pan disponible (m²)")
    shading: str = _choice("aucun", ("aucun", "partiel", "important"), "Ombrage")
    roof_age: str = _choice("inconnu", ("recente", "moyenne", "ancienne", "inconnu"), "Âge de la couverture")
    structure: str = _choice("inconnu", ("traditionnelle", "fermettes", "beton_metal", "inconnu"), "Charpente")
    construction_period: str = _choice("inconnu", ("avant_1997", "apres_1997", "inconnu"), "Construction")
    protected_area: str = _choice("inconnu", ("oui", "non", "inconnu"), "Secteur protégé")
    # Foyer
    annual_kwh: float | None = _num(None, 100, 100_000, "Consommation annuelle (kWh)", optional=True)
    occupants: int = _num(3, 1, 12, "Nombre de personnes", integer=True)
    heating: str = _choice("autre", ("electrique", "pac", "autre"), "Chauffage")
    daytime_presence: str = _choice("non", ("oui", "non"), "Présence en journée")
    electric_water_heater: str = _choice("non", ("oui", "non"), "Chauffe-eau électrique")
    electric_vehicle: str = _choice("non", ("oui", "non"), "Véhicule électrique")
    budget_eur: float | None = _num(None, 500, 1_000_000, "Budget maximal (€)", optional=True)


def parse_house(raw: dict) -> House:
    errors: list[dict[str, str]] = []
    house = _parse_group(House, raw, "house", errors)
    if house is not None and house.annual_kwh is None and house.heating in ("electrique", "pac"):
        errors.append({
            "field": "house.annual_kwh",
            "message": "avec un chauffage électrique ou une pompe à chaleur, indiquez la consommation de votre facture "
            "(elle varie trop selon le logement pour être estimée)",
        })
    if errors:
        raise ValidationError(errors)
    return house  # type: ignore[return-value]


# --- Étapes de calcul ----------------------------------------------------------

def estimate_consumption(house: House) -> tuple[float, bool, str]:
    """Consommation annuelle : facture si fournie, sinon ordre de grandeur selon le foyer."""
    if house.annual_kwh is not None:
        return house.annual_kwh, False, "consommation indiquée (facture)"
    pts = sorted(K.CONSUMPTION_BY_OCCUPANTS_KWH.items())
    n = house.occupants
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    if n <= xs[-1]:
        kwh = float(np.interp(n, xs, ys))
    else:  # extrapolation linéaire au-delà de 4 personnes
        slope = (ys[-1] - ys[-2]) / (xs[-1] - xs[-2])
        kwh = ys[-1] + slope * (n - xs[-1])
    return kwh, True, f"ordre de grandeur pour un foyer de {n} personne{'s' if n > 1 else ''}, hors chauffage électrique"


@dataclass
class Geometry:
    tilt: float
    azimuths: list[float]
    occupation: float
    flat: bool


def geometry(house: House) -> Geometry:
    flat = house.slope == "plat" or house.roof_type == "toit_plat"
    tilt = K.SLOPES["plat"] if flat else (house.tilt_deg if house.tilt_deg is not None else K.SLOPES[house.slope])
    if flat:
        # Sur toit plat, les modules sont orientés au sud sur supports inclinés.
        azimuths = [180.0]
    elif house.orientation == "EO":
        azimuths = [90.0, 270.0]
    else:
        azimuths = [K.ORIENTATIONS[house.orientation]]
    return Geometry(tilt=tilt, azimuths=azimuths, occupation=K.OCCUPATION["plat" if flat else "incline"], flat=flat)


def pv_profile_per_kwc(weather: WeatherData, site: Site, geo: Geometry, module: K.ModuleClass,
                       solar_position_method: str = "nrel_numpy") -> np.ndarray:
    """Production AC horaire par kWc ; pour deux pans, moyenne des deux orientations (moitié de la puissance sur chacun)."""
    profiles = []
    for az in geo.azimuths:
        pv = PVSystem(tilt_deg=geo.tilt, azimuth_deg=az, gamma_pdc_pct_per_c=module.gamma_pdc_pct_per_c)
        profiles.append(physics.compute_pv_profile(weather, site, pv, solar_position_method).ac_kwh_per_kwc.to_numpy())
    return np.mean(profiles, axis=0)


@dataclass
class RepresentativeYear:
    """Météo d'une année « représentative » et production par kWc ramenée à la moyenne pluriannuelle."""

    weather: WeatherData
    pv_per_kwc: np.ndarray
    yearly_yield: dict[int, float]  # productible de chaque année (kWh/kWc)
    year: int
    scale: float


def representative_year(weather: WeatherData, site: Site, geo: Geometry, module: K.ModuleClass) -> RepresentativeYear:
    """Choisit, parmi les années complètes, celle dont la production est la plus proche de la moyenne,
    puis ajuste sa production à cette moyenne.

    Une seule année météo peut s'écarter de ±8 % de la moyenne (mesuré sur 10 villes, 2016–2025) ;
    garder le profil horaire d'une année réelle conserve la forme de la production (utile au
    bilan heure par heure), et la mise à l'échelle corrige le niveau annuel.
    """
    idx = weather.data.index
    if len(idx) < 2 * 8700:  # une seule année : calcul de référence direct
        pv = pv_profile_per_kwc(weather, site, geo, module)
        y = int(pd.Series(idx.year).mode()[0])
        return RepresentativeYear(weather, pv, {y: float(pv.sum() * 8760.0 / len(pv))}, y, 1.0)
    # Comparaison des années avec l'algorithme solaire rapide (voir physics.compute_pv_profile).
    pv_all = pv_profile_per_kwc(weather, site, geo, module, "ephemeris")
    years = {}
    year_of = np.asarray(idx.year)
    for y in np.unique(year_of):
        mask = year_of == y
        if mask.sum() >= 8700:  # année complète (à une heure près, selon la convention d'horodatage)
            years[int(y)] = float(pv_all[mask].sum() * 8760.0 / mask.sum())
    if len(years) <= 1:
        y = next(iter(years), int(idx[0].year))
        return RepresentativeYear(weather, pv_all, years or {y: float(pv_all.sum() * 8760.0 / len(pv_all))}, y, 1.0)
    mean = float(np.mean(list(years.values())))
    chosen = min(years, key=lambda y: abs(years[y] - mean))
    mask = year_of == chosen
    sub = dataclasses.replace(weather, data=weather.data[mask])
    scale = mean / years[chosen]
    # Profil de l'année retenue recalculé avec l'algorithme de référence (SPA), puis mis à l'échelle.
    pv_ref = pv_profile_per_kwc(sub, site, geo, module)
    return RepresentativeYear(sub, pv_ref * scale, years, chosen, scale)


class LoadModel:
    """Consommation horaire, avec ou sans pilotage du chauffe-eau électrique.

    Sans pilotage, le chauffe-eau chauffe la nuit en heures creuses. Avec pilotage
    (routeur ou gestionnaire d'énergie), son énergie quotidienne est d'abord prise sur
    le surplus solaire de la journée, dans la limite de sa puissance ; le complément
    est chauffé la nuit. L'énergie quotidienne est supposée constante sur l'année.
    """

    def __init__(self, index, house: "House", annual_kwh: float):
        self.ecs_annual = water_heater_kwh(house, annual_kwh)
        presence = house.daytime_presence == "oui"
        self.base = load.simplified_profile(index, house.timezone, annual_kwh - self.ecs_annual, presence).to_numpy()
        local = index.tz_convert(house.timezone)
        dates = np.asarray(local.date)
        self.day = np.unique(dates, return_inverse=True)[1]
        n_days = int(self.day.max()) + 1
        self.first_of_day = np.r_[True, self.day[1:] != self.day[:-1]]
        offpeak = np.isin(local.hour, K.OFFPEAK_HOURS)
        self.offpeak_count = np.bincount(self.day, weights=offpeak.astype(float), minlength=n_days)
        self.offpeak = offpeak
        self.daily = self.ecs_annual * len(index) / 8760.0 / n_days
        self.n_days = n_days

    @property
    def has_water_heater(self) -> bool:
        return self.ecs_annual > 0

    def _night(self, per_day: np.ndarray) -> np.ndarray:
        share = np.divide(per_day, self.offpeak_count, out=np.zeros_like(per_day), where=self.offpeak_count > 0)
        return np.where(self.offpeak, share[self.day], 0.0)

    def profile(self, pv_kwh: np.ndarray | None = None, piloted: bool = False) -> np.ndarray:
        if not self.has_water_heater:
            return self.base
        if not piloted or pv_kwh is None:
            return self.base + self._night(np.full(self.n_days, self.daily))
        surplus = np.clip(pv_kwh - self.base, 0.0, K.WATER_HEATER_POWER_KW)
        cum = np.cumsum(surplus)
        start = np.r_[0.0, cum][np.flatnonzero(self.first_of_day)]
        cum_day = cum - start[self.day]
        taken_cum = np.minimum(cum_day, self.daily)
        prev = np.r_[0.0, taken_cum[:-1]]
        prev[self.first_of_day] = 0.0
        absorbed = taken_cum - prev
        remaining = self.daily - np.bincount(self.day, weights=absorbed, minlength=self.n_days)
        return self.base + absorbed + self._night(np.clip(remaining, 0.0, None))


def water_heater_kwh(house: "House", annual_kwh: float) -> float:
    if house.electric_water_heater != "oui":
        return 0.0
    return min(K.WATER_HEATER_KWH_PER_PERSON * house.occupants, K.WATER_HEATER_MAX_SHARE * annual_kwh)


def economics_for(kwc: float, module: K.ModuleClass) -> Economics:
    """Hypothèses économiques en vigueur, TVA selon la puissance."""
    factor = 1.0
    if kwc > K.VAT_REDUCED_MAX_KWC:
        factor = (1 + K.VAT_NORMAL_PCT / 100) / (1 + K.VAT_REDUCED_PCT / 100)
    return Economics(
        pv_capex_eur_per_kwc=K.INSTALL_EUR_PER_KWC * factor,
        fixed_capex_eur=K.INSTALL_FIXED_EUR * factor,
        battery_capex_eur_per_kwh=K.BATTERY_EUR_PER_KWH,
        degradation_pct_per_year=module.degradation_pct_per_year,
        inverter_replacement_year=K.INVERTER_REPLACEMENT_YEAR,
        inverter_replacement_eur_per_kwc=K.INVERTER_REPLACEMENT_EUR / kwc,
    )


def break_even_capex(row: dict, module: K.ModuleClass) -> float | None:
    """Investissement total en dessous duquel la VAN devient positive (VAN linéaire en investissement)."""
    kwc, battery_kwh = row["pv_kwc"], row["battery_kwh"]
    base = economics_for(kwc, module)
    totals = row["totals"]
    npv0 = economics.evaluate(base, kwc, battery_kwh, totals)["npv_eur"]
    shifted = dataclasses.replace(base, fixed_capex_eur=base.fixed_capex_eur + 1000.0)
    npv1 = economics.evaluate(shifted, kwc, battery_kwh, totals)["npv_eur"]
    slope = (npv1 - npv0) / 1000.0  # € de VAN par € d'investissement (négatif)
    if slope >= 0:
        return None
    capex = row["capex_eur"] - npv0 / slope
    return capex if capex > 0 else None


def panel_range(module: K.ModuleClass, n_max: int, pans: int) -> range:
    n_min = max(MIN_PANELS, math.ceil(PRICE_MODEL_MIN_KWC * 1000.0 / module.power_wc - 1e-9))
    n_min = min(n_min, n_max)
    step = pans  # même nombre de modules par pan
    n_min += (-n_min) % step
    return range(n_min, n_max + 1, step)


def evaluate_grid(pv_per_kwc: np.ndarray, loads: LoadModel, module: K.ModuleClass, sizes: range, piloted: bool) -> list[dict]:
    rows = []
    for battery_kwh in BATTERY_SIZES_KWH:
        battery = Battery(capacity_kwh=battery_kwh, power_kw=battery_kwh * BATTERY_C_RATE)
        for n in sizes:
            kwc = round(n * module.power_wc / 1000.0, 3)
            pv_kwh = pv_per_kwc * kwc
            flows = simulate(pv_kwh, loads.profile(pv_kwh, piloted), battery)
            totals = flows.totals()
            eco = economics.evaluate(economics_for(kwc, module), kwc, battery_kwh, totals)
            rows.append({
                "panels": n,
                "pv_kwc": kwc,
                "battery_kwh": battery_kwh,
                "battery_kw": battery.power_kw,
                "totals": totals,
                "capex_eur": eco["capex_eur"],
                "npv_eur": eco["npv_eur"],
                "irr": eco["irr"],
                "payback_years": eco["payback_years"],
                "lcoe_eur_per_kwh": eco["lcoe_eur_per_kwh"],
                "year1_savings_eur": eco["year1_savings_eur"],
                "year1_bill_without_pv_eur": eco["year1_bill_without_pv_eur"],
                "year1_bill_with_pv_eur": eco["year1_bill_with_pv_eur"],
                "cumulative_eur": eco["yearly"]["cumulative_eur"],
            })
    return rows


def _best(rows: list[dict]) -> dict | None:
    return max(rows, key=lambda r: r["npv_eur"]) if rows else None


# --- Conseils -----------------------------------------------------------------

def _item(category: str, title: str, text: str, level: str = "conseil", sources: tuple[str, ...] = ()) -> dict:
    return {"category": category, "title": title, "text": text, "level": level, "sources": list(sources)}


def build_advice(house: House, geo: Geometry, module: K.ModuleClass, rec: dict, best_no_batt: dict, best_batt: dict | None,
                 n_max: int, orientation_ratio: float, consumption_estimated: bool) -> list[dict]:
    a: list[dict] = []
    kwc = rec["pv_kwc"]

    # Orientation
    label = K.ORIENTATION_LABELS.get(house.orientation, house.orientation)
    if geo.flat:
        a.append(_item("toiture", "Toit plat", f"Modules posés sur supports inclinés à {geo.tilt:g}° orientés au sud. "
                       "Les rangées doivent être espacées pour éviter qu'elles s'ombragent : moins de modules qu'en toiture inclinée.", "info"))
    elif orientation_ratio < 0.75:
        a.append(_item("toiture", "Orientation peu favorable",
                       f"Un pan orienté {label} produit environ {_pct(orientation_ratio)} de ce que produirait un pan plein sud incliné à 30° "
                       "au même endroit. Le projet est rarement rentable dans ce cas : vérifiez s'il existe un autre pan mieux exposé.", "attention"))
    elif house.orientation == "EO":
        a.append(_item("toiture", "Deux pans est et ouest",
                       f"Production répartie entre le matin et le soir ({_pct(orientation_ratio)} d'un pan plein sud), "
                       "ce qui colle mieux aux heures de consommation qu'un seul pan sud.", "info"))
    else:
        a.append(_item("toiture", "Orientation", f"Pan orienté {label} : {_pct(orientation_ratio)} de la production d'un pan plein sud incliné à 30°.", "info"))

    # Ombrage
    if house.shading == "partiel":
        a.append(_item("ombrage", "Ombrage partiel non modélisé",
                       "Le calcul suppose un toit sans ombre : la production réelle sera plus faible. Demandez une étude d'ombrage à "
                       "l'installateur et privilégiez des micro-onduleurs ou des optimiseurs.", "attention", ("onduleurs",)))
    elif house.shading == "important":
        a.append(_item("ombrage", "Ombrage important",
                       "Avec un ombrage important, les résultats ci-dessous sont surestimés et peu fiables. Faites réaliser une étude "
                       "d'ombrage avant tout engagement.", "attention"))

    # Modules
    roof_limited = rec["panels"] >= n_max
    text = (f"{module.label} : environ {module.power_wc:g} Wc par module ({module.length_m:.2f} × {module.width_m:.2f} m), "
            f"rendement de l'ordre de {module.efficiency_pct:g} %. C'est la technologie la plus répandue en 2026, au meilleur rapport prix/puissance.")
    a.append(_item("panneaux", "Type de panneaux", text, "conseil", ("modules_2026", "fiche_topcon")))
    if roof_limited and rec["npv_eur"] > 0:
        bc = K.MODULES["back_contact"]
        gain = bc.power_wc / module.power_wc - 1
        a.append(_item("panneaux", "Toit entièrement utilisé",
                       f"La meilleure option occupe toute la surface disponible. Des modules back-contact (≈ {bc.power_wc:g} Wc, "
                       f"rendement ≈ {bc.efficiency_pct:g} %) apporteraient environ {_pct(gain)} de puissance en plus sur la même surface, "
                       "pour un prix plus élevé : à comparer sur devis.", "conseil", ("modules_2026",)))
    if house.protected_area in ("oui", "inconnu"):
        a.append(_item("panneaux", "Aspect des modules",
                       "En secteur protégé, la mairie et l'architecte des Bâtiments de France peuvent imposer des exigences d'aspect "
                       "(couleur, alignement). Des modules entièrement noirs sont plus discrets.", "conseil", ("dp_toiture",)))

    # Onduleur
    if house.shading != "aucun" or house.orientation == "EO":
        inv = ("Micro-onduleurs ou optimiseurs : chaque module produit indépendamment, ce qui limite les pertes dues à "
               "l'ombrage ou aux orientations multiples.")
    else:
        inv = ("Onduleur central (« string ») : pour un toit homogène, bien exposé et sans ombre, c'est la solution la plus "
               "économique. Les micro-onduleurs restent possibles, avec un surcoût.")
    if rec["battery_kwh"] > 0:
        inv += " Avec batterie : onduleur hybride, ou batterie couplée côté courant alternatif."
    a.append(_item("onduleur", "Onduleur", inv, "conseil", ("onduleurs",)))

    # Batterie
    if best_batt is not None:
        delta = best_batt["npv_eur"] - best_no_batt["npv_eur"]
        if rec["battery_kwh"] > 0:
            a.append(_item("batterie", "Batterie recommandée",
                           f"Une batterie de {_fr(rec['battery_kwh'])} kWh améliore la valeur du projet de {_int(delta)} € sur la durée d'étude, "
                           "car le surplus injecté n'est presque plus rémunéré.", "conseil"))
        else:
            a.append(_item("batterie", "Batterie non recommandée pour l'instant",
                           f"Avec un prix de batterie d'environ {K.BATTERY_EUR_PER_KWH:g} €/kWh, la meilleure option avec batterie vaut "
                           f"{_int(-delta)} € de moins que sans batterie. À réévaluer si les prix baissent ; prévoir un onduleur compatible "
                           "permet d'en ajouter une plus tard.", "info"))

    # Autoconsommation
    tips = ["Faites tourner lave-linge, lave-vaisselle et chauffe-eau en journée"]
    if house.electric_water_heater == "oui":
        tips.append("un routeur solaire ou une programmation du chauffe-eau électrique en milieu de journée absorbe une grande partie du surplus")
    if house.electric_vehicle == "oui":
        tips.append("rechargez le véhicule électrique en journée quand c'est possible")
    a.append(_item("autoconsommation", "Consommer sa production",
                   f"Le surplus injecté n'est payé que {K.EXPORT_TARIFF_EUR_PER_KWH * 100:.1f} c€/kWh, contre "
                   f"{K.ELECTRICITY_PRICE_EUR_PER_KWH * 100:.2f} c€/kWh pour l'électricité achetée : chaque kWh consommé sur place vaut "
                   f"environ {K.ELECTRICITY_PRICE_EUR_PER_KWH / K.EXPORT_TARIFF_EUR_PER_KWH:.0f} fois plus qu'un kWh vendu. "
                   + " ; ".join(tips) + ".", "conseil", ("arrete_s21_2026", "trv_aout_2026")))

    # TVA et seuil de 9 kWc
    if kwc <= K.VAT_REDUCED_MAX_KWC:
        a.append(_item("finances", "TVA à 5,5 %",
                       "Jusqu'à 9 kWc, la TVA réduite s'applique si toutes les conditions sont réunies (modules à faible empreinte "
                       "carbone, système de gestion de l'énergie…). Faites-les inscrire sur le devis. Le calcul suppose qu'elles le sont.",
                       "attention", ("tva_55",)))
    else:
        a.append(_item("finances", "Au-delà de 9 kWc",
                       "TVA à 20 % (contre 5,5 % jusqu'à 9 kWc), prise en compte dans le calcul.", "info", ("tva_55",)))

    # Pose et structure
    roof = house.roof_type
    pose = {
        "tuiles_mecaniques": "Pose en surimposition sur crochets de toit : solution standard, sans toucher à l'étanchéité.",
        "tuiles_canal": "Pose en surimposition avec crochets adaptés aux tuiles canal ; ces tuiles se cassent facilement, à prévoir au devis.",
        "ardoise": "Pose en surimposition avec crochets spécifiques à l'ardoise : intervention délicate, à confier à un couvreur habitué.",
        "bac_acier": "Fixation directe sur les nervures du bac acier : pose rapide et légère.",
        "fibrociment": "Fixations adaptées au fibrociment, plaques fragiles : ne jamais marcher directement dessus.",
        "toit_plat": "Supports inclinés lestés ou fixés : vérifier la charge admissible et préserver l'étanchéité.",
        "autre": "Faire valider le système de fixation par l'installateur selon la couverture.",
    }[roof]
    a.append(_item("pose", "Mode de pose", pose + " La surimposition est aujourd'hui la règle ; l'intégration au bâti "
                   "n'est à envisager qu'en cas de réfection complète de la couverture.", "conseil"))
    lo, hi = K.SURIMPOSITION_LOAD_KG_M2
    struct = f"Une pose en surimposition ajoute environ {lo} à {hi} kg/m² à la toiture."
    if geo.flat:
        struct += " Sur toit plat, les supports lestés sont bien plus lourds : une vérification par un bureau d'études structure est nécessaire."
        level = "attention"
    elif house.structure in ("fermettes", "inconnu"):
        struct += (" Les charpentes en fermettes industrielles sont dimensionnées au plus juste : faites vérifier la charpente "
                   "(installateur qualifié en charpente ou bureau d'études) avant la pose.")
        level = "attention"
    else:
        struct += " Une charpente traditionnelle en bon état le supporte généralement ; l'installateur doit le confirmer."
        level = "conseil"
    a.append(_item("structure", "Charpente", struct, level, ("structure",)))
    if house.roof_age in ("ancienne",):
        a.append(_item("structure", "Couverture à refaire d'abord",
                       "Refaites la couverture avant d'installer les panneaux : les déposer puis les reposer pour une réfection "
                       "ultérieure coûte cher.", "attention"))
    elif house.roof_age == "inconnu":
        a.append(_item("structure", "État de la couverture",
                       "Faites vérifier l'état de la couverture : les panneaux resteront en place 25 ans ou plus.", "conseil"))
    if roof == "fibrociment" and house.construction_period in ("avant_1997", "inconnu"):
        a.append(_item("structure", "Risque d'amiante",
                       "Le fibrociment posé avant 1997 peut contenir de l'amiante : faites réaliser un diagnostic amiante avant "
                       "toute intervention sur la toiture.", "attention"))

    # Secteur protégé
    if house.protected_area in ("oui", "inconnu"):
        a.append(_item("demarches", "Secteur protégé",
                       ("Vérifiez sur le Géoportail de l'urbanisme si la maison est en secteur protégé (abords de monument "
                        "historique, site patrimonial). " if house.protected_area == "inconnu" else "")
                       + "En secteur protégé, la déclaration préalable est soumise à l'avis de l'architecte des Bâtiments de France "
                       "et le délai d'instruction est plus long.", "attention", ("geoportail_urbanisme", "dp_toiture")))

    if consumption_estimated:
        a.append(_item("consommation", "Consommation estimée",
                       "La consommation est un ordre de grandeur. Indiquez celle de votre facture (ou de votre espace client Enedis) "
                       "pour un dimensionnement fiable.", "attention", ("conso_moyenne",)))
    return a


def steps(house: House, kwc: float) -> list[dict]:
    out = [
        {"title": "Comparer plusieurs devis",
         "text": "Auprès d'installateurs qualifiés (RGE). Chaque devis doit préciser modules, onduleur, fixations, puissance "
                 "et conditions de TVA.", "sources": ["dp_toiture"]},
        {"title": "Déclaration préalable en mairie",
         "text": "Obligatoire pour des panneaux sur le toit, car ils modifient l'aspect extérieur (Cerfa 13703). "
                 "Renseignez-vous d'abord en mairie sur les règles locales (PLU, couleur)." +
                 (" Avis de l'architecte des Bâtiments de France en secteur protégé." if house.protected_area == "oui" else ""),
         "sources": ["dp_toiture", "cerfa_13703"]},
        {"title": "Raccordement et contrat de rachat",
         "text": "Demande de raccordement auprès d'Enedis (convention d'autoconsommation), puis contrat de rachat du surplus "
                 f"avec EDF OA : {K.EXPORT_TARIFF_EUR_PER_KWH * 100:.1f} c€/kWh, +{K.EXPORT_TARIFF_INDEXATION_PCT:g} %/an, "
                 f"{K.EXPORT_CONTRACT_YEARS} ans. Il n'y a plus de prime à l'autoconsommation." +
                 (" Jusqu'à 9 kWc, seule la vente du surplus est possible." if kwc <= K.SURPLUS_ONLY_MAX_KWC else ""),
         "sources": ["raccordement", "arrete_s21_2026", "tarif_rachat_detail"]},
        {"title": "Pose et attestation de conformité",
         "text": "Après la pose, l'attestation de conformité électrique (Consuel) permet la mise en service.",
         "sources": ["raccordement"]},
        {"title": "Assurance",
         "text": "Déclarez l'installation à votre assureur habitation.", "sources": []},
    ]
    return out


# --- Point d'entrée -------------------------------------------------------------

def advise(house: House, weather: WeatherData) -> dict:
    site = Site(latitude=house.latitude, longitude=house.longitude, timezone=house.timezone)
    geo = geometry(house)
    module = K.MODULES["topcon"]

    n_fit = int(math.floor(house.roof_area_m2 * geo.occupation / module.area_m2))
    if geo.azimuths and len(geo.azimuths) == 2:
        n_fit -= n_fit % 2  # même nombre de modules sur chaque pan
    if n_fit < MIN_PANELS:
        raise ValueError(
            f"Surface insuffisante : {house.roof_area_m2:g} m² permettent moins de {MIN_PANELS} modules "
            f"({module.area_m2:.2f} m² chacun, taux d'occupation {_pct(geo.occupation)})."
        )
    n_max = min(n_fit, MAX_PANELS)

    annual_kwh, estimated, consumption_basis = estimate_consumption(house)

    rep = representative_year(weather, site, geo, module)
    weather = rep.weather
    pv_per_kwc = rep.pv_per_kwc
    index = weather.data.index
    loads = LoadModel(index, house, annual_kwh)
    piloted = loads.has_water_heater  # le gestionnaire d'énergie est requis pour la TVA à 5,5 %

    ideal = physics.compute_pv_profile(weather, site, PVSystem(tilt_deg=30, azimuth_deg=180,
                                                                gamma_pdc_pct_per_c=module.gamma_pdc_pct_per_c))
    specific_yield = float(pv_per_kwc.sum() * 8760.0 / len(pv_per_kwc))
    orientation_ratio = (specific_yield / rep.scale) / ideal.annual_yield()

    sizes = panel_range(module, n_max, len(geo.azimuths))
    rows = evaluate_grid(pv_per_kwc, loads, module, sizes, piloted)
    notes: list[str] = []
    if sizes.start * module.power_wc / 1000.0 < PRICE_MODEL_MIN_KWC:
        notes.append("Le toit ne permet pas 3 kWc : les prix sont extrapolés hors des fourchettes publiées, "
                     "le résultat économique est donc moins fiable.")
    candidates = rows
    if house.budget_eur is not None:
        candidates = [r for r in rows if r["capex_eur"] <= house.budget_eur]
        if not candidates:
            raise ValueError(f"Aucune configuration ne tient dans le budget de {_int(house.budget_eur)} € "
                             f"(la plus petite coûte {_int(min(r['capex_eur'] for r in rows))} €).")
    rec = _best(candidates)
    assert rec is not None
    best_no_batt = _best([r for r in candidates if r["battery_kwh"] == 0]) or rec
    with_batt = [r for r in candidates if r["battery_kwh"] > 0]
    best_batt = _best(with_batt)

    # Plage de tailles quasi équivalentes (même batterie) : utile pour discuter les devis.
    same = [r for r in candidates if r["battery_kwh"] == rec["battery_kwh"]]
    tol = max(PLATEAU_TOLERANCE_EUR, 0.05 * abs(rec["npv_eur"]))
    near = [r["pv_kwc"] for r in same if r["npv_eur"] >= rec["npv_eur"] - tol]
    plateau = {"min_kwc": min(near), "max_kwc": max(near)}

    if rec["panels"] == sizes.start and sizes.start > MIN_PANELS and len(sizes) > 1:
        notes.append(f"La recommandation est la plus petite taille étudiée ({_fr(rec['pv_kwc'])} kWc). Les installations "
                     "plus petites ne sont pas évaluées, faute de prix publiés fiables : demandez un devis si vous les envisagez.")
    target_capex = break_even_capex(rec, module)
    profitable = rec["npv_eur"] >= 0
    if not profitable:
        notes.append("Avec ces hypothèses de prix, aucune configuration n'est rentable sur 25 ans : la recommandation est "
                     "l'option la moins défavorable. Voir le prix de devis à viser.")

    options = []
    def add_option(key: str, label: str, row: dict | None):
        if row is not None and not any(o["row"] is row for o in options):
            options.append({"key": key, "label": label, "row": row})
    add_option("recommandee", "Recommandée", rec)
    add_option("sans_batterie", "Meilleure sans batterie", best_no_batt)
    add_option("avec_batterie", "Meilleure avec batterie", best_batt)
    roof_full = _best([r for r in rows if r["panels"] == n_max and r["battery_kwh"] == 0])
    add_option("toit_complet", "Toit complet, sans batterie", roof_full)
    if rec["pv_kwc"] > K.VAT_REDUCED_MAX_KWC:
        add_option("max_9kwc", "Meilleure jusqu'à 9 kWc", _best([r for r in candidates if r["pv_kwc"] <= K.VAT_REDUCED_MAX_KWC]))

    advice = build_advice(house, geo, module, rec, best_no_batt, best_batt, n_max, orientation_ratio, estimated)

    # Fourchette des prix publiés pour la puissance recommandée (hors batterie).
    price_range = K.observed_price_range(rec["pv_kwc"])
    battery_cost = rec["battery_kwh"] * K.BATTERY_EUR_PER_KWH
    if target_capex is not None:
        verb = "reste rentable" if profitable else "devient rentable"
        text = (f"Pour {_fr(rec['pv_kwc'])} kWc{f' avec {_fr(rec['battery_kwh'])} kWh de batterie' if rec['battery_kwh'] else ''}, "
                f"le projet {verb} (VAN positive sur 25 ans) si le devis total est inférieur à environ "
                f"{_int(target_capex)} € TTC. Estimation retenue : {_int(rec['capex_eur'])} €.")
        level = "attention" if not profitable else "conseil"
        if price_range is not None:
            lo, hi = (p + battery_cost for p in price_range)
            text += f" Les prix publiés pour cette puissance vont de {_int(lo)} à {_int(hi)} €"
            if target_capex < lo:
                text += " : la cible est sous les prix les plus bas observés, la rentabilité est donc peu probable aujourd'hui."
            elif target_capex < hi:
                text += " : la cible est atteignable en comparant plusieurs devis."
            else:
                text += " : même un devis élevé resterait rentable."
        advice.insert(0, _item("finances", "Prix de devis à viser", text, level,
                               ("prix_installation", "prix_potentiel_solaire", "prix_edf_solutions")))

    # Pilotage du chauffe-eau : gain mesuré par rapport à un chauffage la nuit.
    pilot_gain = None
    if loads.has_water_heater:
        rec_pv0 = pv_per_kwc * rec["pv_kwc"]
        battery0 = Battery(capacity_kwh=rec["battery_kwh"], power_kw=rec["battery_kw"])
        night = simulate(rec_pv0, loads.profile(rec_pv0, piloted=False), battery0).totals()
        eco_night = economics.evaluate(economics_for(rec["pv_kwc"], module), rec["pv_kwc"], rec["battery_kwh"], night)
        pilot_gain = {
            "self_consumption_without": night["self_consumption_rate"],
            "self_consumption_with": rec["totals"]["self_consumption_rate"],
            "year1_gain_eur": rec["year1_savings_eur"] - eco_night["year1_savings_eur"],
            "npv_gain_eur": rec["npv_eur"] - eco_night["npv_eur"],
        }
        advice.insert(1, _item(
            "autoconsommation", "Piloter le chauffe-eau électrique",
            f"Faire chauffer l'eau avec le surplus solaire (routeur ou gestionnaire d'énergie) plutôt que la nuit fait passer "
            f"l'autoconsommation de {_pct(pilot_gain['self_consumption_without'])} à {_pct(pilot_gain['self_consumption_with'])} "
            f"et rapporte environ {_int(pilot_gain['year1_gain_eur'])} € de plus par an. Les résultats ci-dessus supposent ce "
            f"pilotage, exigé de toute façon pour la TVA à 5,5 % (gestion de l'énergie). Chauffe-eau estimé à "
            f"{_int(loads.ecs_annual)} kWh/an.", "conseil", ("conso_chauffe_eau", "tva_55")))

    values = list(rep.yearly_yield.values())
    if len(values) > 1:
        advice.append(_item(
            "production", "Variations d'une année à l'autre",
            f"Production calculée sur {len(values)} années de météo ({min(rep.yearly_yield)}–{max(rep.yearly_yield)}) : "
            f"{_int(specific_yield)} kWh/kWc en moyenne, de {_int(min(values))} à {_int(max(values))} kWh/kWc selon l'année. "
            f"Les résultats utilisent l'année {rep.year}, la plus proche de la moyenne, ramenée à cette moyenne.",
            "info"))
    used = sorted({s for item in advice for s in item["sources"]} | {s for st in steps(house, rec["pv_kwc"]) for s in st["sources"]})

    def slim(r: dict) -> dict:
        return {k: v for k, v in r.items() if k != "cumulative_eur"}

    # Production mensuelle de la recommandation (heure locale).
    rec_pv = pv_per_kwc * rec["pv_kwc"]
    rec_battery = Battery(capacity_kwh=rec["battery_kwh"], power_kw=rec["battery_kw"])
    rec_flows = simulate(rec_pv, loads.profile(rec_pv, piloted), rec_battery)
    month = index.tz_convert(house.timezone).month
    monthly = {"month": list(range(1, 13))}
    for name, arr in (("pv_kwh", rec_flows.pv), ("load_kwh", rec_flows.load), ("direct_kwh", rec_flows.direct),
                      ("battery_discharge_kwh", rec_flows.battery_discharge), ("export_kwh", rec_flows.export),
                      ("import_kwh", rec_flows.grid_import)):
        monthly[name] = [float(arr[month == m].sum()) for m in range(1, 13)]

    return {
        "recommendation": {
            **slim(rec),
            "module": dataclasses.asdict(module) | {"area_m2": module.area_m2},
            "tilt_deg": geo.tilt,
            "azimuths_deg": geo.azimuths,
            "occupied_area_m2": rec["panels"] * module.area_m2,
            "cumulative_eur": rec["cumulative_eur"],
            "plateau": plateau,
            "break_even_capex_eur": target_capex,
            "profitable": profitable,
            "observed_price_range_eur": (None if price_range is None else [p + battery_cost for p in price_range]),
            "water_heater_piloting": pilot_gain,
        },
        "roof": {"max_panels": n_max, "max_kwc": n_max * module.power_wc / 1000.0, "fit_panels": n_fit,
                 "occupation": geo.occupation, "flat": geo.flat},
        "production": {"specific_yield_kwh_per_kwc": specific_yield, "ideal_yield_kwh_per_kwc": ideal.annual_yield(),
                       "orientation_ratio": orientation_ratio, "yearly_yield": {str(k): v for k, v in rep.yearly_yield.items()},
                       "representative_year": rep.year},
        "consumption": {"annual_kwh": annual_kwh, "estimated": estimated, "basis": consumption_basis},
        "options": [{"key": o["key"], "label": o["label"], **slim(o["row"])} for o in options],
        "grid": [{"panels": r["panels"], "pv_kwc": r["pv_kwc"], "battery_kwh": r["battery_kwh"], "npv_eur": r["npv_eur"],
                  "capex_eur": r["capex_eur"]} for r in rows],
        "monthly": monthly,
        "advice": advice,
        "steps": steps(house, rec["pv_kwc"]),
        "notes": notes,
        "assumptions": assumptions(geo),
        "sources": {k: K.SOURCES[k] for k in used},
        "verified_on": K.VERIFIED_ON,
    }


def assumptions(geo: Geometry) -> list[str]:
    return [
        f"Prix d'installation : {_int(K.INSTALL_FIXED_EUR)} € + {_int(K.INSTALL_EUR_PER_KWC)} €/kWc TTC (TVA 5,5 %), "
        f"ajusté sur les fourchettes de prix publiées en 2026 ; TVA 20 % au-delà de 9 kWc. Batterie : {K.BATTERY_EUR_PER_KWH:g} €/kWh.",
        f"Électricité achetée : {K.ELECTRICITY_PRICE_EUR_PER_KWH} €/kWh (tarif réglementé Base), +2 %/an.",
        f"Surplus vendu {K.EXPORT_TARIFF_EUR_PER_KWH * 100:.1f} c€/kWh, +{K.EXPORT_TARIFF_INDEXATION_PCT:g} %/an pendant "
        f"{K.EXPORT_CONTRACT_YEARS} ans, puis non valorisé. Étude sur 25 ans, actualisation 4 %, "
        f"maintenance 1 %/an de l'investissement, remplacement de l'onduleur ({_int(K.INVERTER_REPLACEMENT_EUR)} €) "
        f"la {K.INVERTER_REPLACEMENT_YEAR}e année.",
        f"Tailles étudiées à partir de {PRICE_MODEL_MIN_KWC:g} kWc (domaine des prix publiés) jusqu'au toit complet.",
        f"Occupation du pan : {_pct(geo.occupation)} de la surface indiquée (marges, espacements), à confirmer par le calepinage de l'installateur.",
        f"Météo : {K.WEATHER_YEARS} dernières années complètes ; année la plus proche de la moyenne, ramenée à la moyenne. "
        "Profil de consommation simplifié ; ombrage non modélisé ; pertes système 14 %.",
        f"Chauffe-eau électrique : {_int(K.WATER_HEATER_KWH_PER_PERSON)} kWh par personne et par an (au plus "
        f"{_pct(K.WATER_HEATER_MAX_SHARE)} de la consommation), chauffé la nuit (22 h–6 h) sans pilotage, sur le surplus "
        f"solaire avec pilotage (puissance {_fr(K.WATER_HEATER_POWER_KW)} kW).",
    ]
