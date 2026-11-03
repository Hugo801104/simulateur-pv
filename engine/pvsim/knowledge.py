"""Base de connaissances du mode Conseil : réglementation, marché, règles de pose.

Toutes les valeurs chiffrées et règles de conseil sont regroupées ici, chacune
avec sa source et la date de vérification, pour pouvoir être relues et mises à
jour sans toucher aux calculs. Les « ordres de grandeur » sont signalés comme
tels dans l'interface.

Dernière vérification complète : voir VERIFIED_ON.
"""

from __future__ import annotations

from dataclasses import dataclass

VERIFIED_ON = "2026-11-03"

# --- Sources -----------------------------------------------------------------
SOURCES: dict[str, dict[str, str]] = {
    "arrete_s21_2026": {
        "title": "Arrêté du 1er juin 2026 modifiant l'arrêté tarifaire S21 (NOR ECOR2609281A, JO du 4 juin 2026)",
        "url": "https://www.photovoltaique.info/fr/actualites/detail/arrete-s21-detail-des-modifications-et-nouveau-tarif-unique/",
    },
    "tarif_rachat_detail": {
        "title": "Les Énergies Renouvelables – Arrêté S21 : rachat à 1,1 c€/kWh, prime supprimée",
        "url": "https://www.les-energies-renouvelables.eu/article/actualites/energies/solaire-la-fin-des-aides-a-la-revente-voici-le-nouveau-calcul-1035/",
    },
    "trv_aout_2026": {
        "title": "Tarif réglementé Base au 1er août 2026 (délibération CRE 2026-147), synthèse Selectra",
        "url": "https://selectra.info/energie/electricite/prix/trv",
    },
    "tva_55": {
        "title": "TVA à 5,5 % pour le photovoltaïque résidentiel ≤ 9 kWc (arrêté du 8 septembre 2025), synthèse Hellowatt",
        "url": "https://www.hellowatt.fr/blog/tva-5-5-solaire/",
    },
    "prix_installation": {
        "title": "La Prime Énergie – fourchettes de prix 2026 (3, 6 et 9 kWc)",
        "url": "https://www.laprimeenergie.fr/les-travaux/le-panneau-solaire/simulateur-simulation",
    },
    "dp_toiture": {
        "title": "Service-public.fr – Faut-il une autorisation d'urbanisme pour des panneaux solaires sur le toit ?",
        "url": "https://www.service-public.gouv.fr/particuliers/vosdroits/F36798",
    },
    "cerfa_13703": {
        "title": "Cerfa 13703 – Déclaration préalable (maison individuelle)",
        "url": "https://www.formulaires.service-public.gouv.fr/gf/showFormulaireSignaletiqueConsulter.do?numCerfa=13703",
    },
    "raccordement": {
        "title": "Photovoltaique.info – Se déclarer au gestionnaire de réseau",
        "url": "https://www.photovoltaique.info/fr/preparer-un-projet/quelles-demarches-realiser/comprendre-les/se-declarer-au-gestionnaire-de-reseau/",
    },
    "structure": {
        "title": "Photovoltaique.info – Points de vigilance technique (charpente, surcharge)",
        "url": "https://www.photovoltaique.info/fr/preparer-un-projet/quel-type-de-projet/photovoltaique-sur-batiment/points-de-vigilance-technique/",
    },
    "onduleurs": {
        "title": "Les Énergies Renouvelables – Onduleur central ou micro-onduleur (2026)",
        "url": "https://www.les-energies-renouvelables.eu/conseils/photovoltaique/onduleur/onduleur-central-ou-micro-onduleur/",
    },
    "modules_2026": {
        "title": "Comparatif des panneaux 2026 (TOPCon, back-contact), Les Énergies Renouvelables",
        "url": "https://www.les-energies-renouvelables.eu/conseils/photovoltaique/comparatif-meilleurs-panneaux-solaires-photovoltaique/",
    },
    "fiche_topcon": {
        "title": "Fiche technique type d'un module TOPCon 54 cellules 425–445 Wc (1762 × 1134 mm)",
        "url": "https://masterenergy.eu/wp-content/uploads/2025/02/JKM420-440N-54HL4R-BDV-1.pdf",
    },
    "conso_moyenne": {
        "title": "Ordres de grandeur de consommation par taille de foyer (comparateurs d'énergie)",
        "url": "https://www.fournisseurs-electricite.com/compteur/consommation-electrique/2-personnes",
    },
    "prix_potentiel_solaire": {
        "title": "Potentiel Solaire – prix 2026 d'une installation posée (3, 6, 9 kWc)",
        "url": "https://www.potentielsolaire.com/prix-panneaux-solaires",
    },
    "prix_edf_solutions": {
        "title": "EDF Solutions Solaires – prix 2026 pour 3, 6 et 9 kWc",
        "url": "https://www.edf-solutions-solaires.com/guide-solaire/prix-panneau-solaire-3kwc-6kwc-9kwc/",
    },
    "prix_batterie": {
        "title": "Selectra – batterie domestique après la réforme 2026 (≈ 700 à 1 000 €/kWh installé)",
        "url": "https://selectra.info/energie/actualites/renovation-energetique/batterie-domestique-rentable-apres-reforme-2026",
    },
    "onduleur_remplacement": {
        "title": "Prix-pose – remplacement de l'onduleur après 10 à 12 ans (800 à 1 200 € TTC)",
        "url": "https://www.prix-pose.com/panneaux-solaires-apercu/prix-pour-maison-100m2",
    },
    "conso_chauffe_eau": {
        "title": "Selectra – consommation d'un chauffe-eau électrique (400 à 800 kWh par personne et par an)",
        "url": "https://selectra.info/energie/guides/conso/chauffe-eau-electrique",
    },
    "autoconsommation_typique": {
        "title": "Hello Watt – taux d'autoconsommation typique sans batterie (≈ 40 %)",
        "url": "https://www.hellowatt.fr/blog/autoconsommation-electrique-photovoltaique",
    },
    "pvgis_tool": {
        "title": "PVGIS – Commission européenne (référence de production)",
        "url": "https://re.jrc.ec.europa.eu/pvg_tools/fr/",
    },
    "geoportail_urbanisme": {
        "title": "Géoportail de l'urbanisme – vérifier PLU et servitudes (secteur protégé)",
        "url": "https://www.geoportail-urbanisme.gouv.fr/",
    },
}

# --- Réglementation et prix (France métropolitaine) --------------------------
EXPORT_TARIFF_EUR_PER_KWH = 0.011  # tarif unique du surplus, demandes complètes depuis le 5 juin 2026
EXPORT_TARIFF_INDEXATION_PCT = 2.0  # indexation fixe annuelle
EXPORT_CONTRACT_YEARS = 20
SURPLUS_ONLY_MAX_KWC = 9.0  # ≤ 9 kWc : vente du surplus uniquement (plus de vente totale)
ELECTRICITY_PRICE_EUR_PER_KWH = 0.2001  # TRV Base ≤ 6 kVA TTC, depuis le 1er août 2026
VAT_REDUCED_PCT = 5.5
VAT_NORMAL_PCT = 20.0
VAT_REDUCED_MAX_KWC = 9.0

# Prix d'installation : droite ajustée sur les fourchettes publiées
# (3 kWc : 6 000–10 500 € ; 6 kWc : 9 500–17 000 € ; 9 kWc : 13 000–24 000 €).
# 3 000 € + 1 700 €/kWc reste dans chaque fourchette. Prix TTC supposés au
# taux réduit (≤ 9 kWc) ; au-delà de 9 kWc, la TVA à 20 % est appliquée.
INSTALL_FIXED_EUR = 3000.0
INSTALL_EUR_PER_KWC = 1700.0
# Comparaison (novembre 2026) : cette droite donne 8 100 / 13 200 / 18 300 € pour
# 3 / 6 / 9 kWc, soit la médiane des trois sources ci-dessous.
# Prix TTC centraux relevés (3, 6, 9 kWc) ; milieu de fourchette quand seule une fourchette est publiée.
PRICE_REFERENCES = {
    "prix_potentiel_solaire": (6752.0, 10867.0, 14032.0),
    "prix_installation": (8250.0, 13250.0, 18500.0),  # La Prime Énergie, milieux de fourchettes
    "prix_edf_solutions": (9000.0, 16000.0, 19000.0),  # EDF Solutions Solaires, milieux de fourchettes
}
PRICE_REFERENCE_KWC = (3.0, 6.0, 9.0)

BATTERY_EUR_PER_KWH = 800.0  # milieu de la fourchette 600–1 000 €/kWh installé

# Remplacement de l'onduleur central : 800 à 1 200 € TTC après 10 à 12 ans.
INVERTER_REPLACEMENT_EUR = 1000.0
INVERTER_REPLACEMENT_YEAR = 12

# Chauffe-eau électrique : 400 à 800 kWh par personne et par an selon les sources ;
# valeur centrale retenue, plafonnée à une part de la consommation totale.
WATER_HEATER_KWH_PER_PERSON = 600.0
WATER_HEATER_MAX_SHARE = 0.5
# Hypothèses de modélisation (non sourcées, usuelles) : puissance d'un cumulus
# et plage d'heures creuses nocturnes pendant laquelle il chauffe sans pilotage.
WATER_HEATER_POWER_KW = 2.4
OFFPEAK_HOURS = (22, 23, 0, 1, 2, 3, 4, 5)

# Météo : nombre d'années utilisées pour l'année représentative du mode Conseil.
WEATHER_YEARS = 10


def observed_price_range(kwc: float) -> tuple[float, float] | None:
    """Fourchette des prix relevés pour une puissance (interpolation linéaire, 3 à 9 kWc)."""
    lo_k, hi_k = PRICE_REFERENCE_KWC[0], PRICE_REFERENCE_KWC[-1]
    if not lo_k <= kwc <= hi_k:
        return None
    import numpy as np

    values = [float(np.interp(kwc, PRICE_REFERENCE_KWC, pts)) for pts in PRICE_REFERENCES.values()]
    return min(values), max(values)

# Surcharge typique d'une pose en surimposition (modules + fixations).
SURIMPOSITION_LOAD_KG_M2 = (15, 20)


# --- Modules : classes génériques (pas de marque) ----------------------------
@dataclass(frozen=True)
class ModuleClass:
    key: str
    label: str
    technology: str
    power_wc: float
    width_m: float
    length_m: float
    efficiency_pct: float
    gamma_pdc_pct_per_c: float
    degradation_pct_per_year: float

    @property
    def area_m2(self) -> float:
        return self.width_m * self.length_m


MODULES = {
    "topcon": ModuleClass(
        key="topcon",
        label="Monocristallin N-type TOPCon (standard 2026)",
        technology="TOPCon",
        power_wc=440.0,
        width_m=1.134,
        length_m=1.762,
        efficiency_pct=22.0,
        gamma_pdc_pct_per_c=-0.29,
        degradation_pct_per_year=0.4,
    ),
    "back_contact": ModuleClass(
        key="back_contact",
        label="Monocristallin back-contact (haut rendement)",
        technology="Back-contact (ABC / HPBC / IBC)",
        power_wc=470.0,
        width_m=1.134,
        length_m=1.762,
        efficiency_pct=23.2,
        gamma_pdc_pct_per_c=-0.26,
        degradation_pct_per_year=0.35,
    ),
}

# --- Géométrie de toiture ------------------------------------------------------
ORIENTATIONS = {  # convention pvlib : 0 = nord, 90 = est, 180 = sud, 270 = ouest
    "N": 0.0, "NE": 45.0, "E": 90.0, "SE": 135.0, "S": 180.0, "SO": 225.0, "O": 270.0, "NO": 315.0,
}
ORIENTATION_LABELS = {
    "N": "nord", "NE": "nord-est", "E": "est", "SE": "sud-est", "S": "sud",
    "SO": "sud-ouest", "O": "ouest", "NO": "nord-ouest", "EO": "est + ouest",
}
SLOPES = {  # inclinaison retenue (°)
    "plat": 10.0,  # toit plat : modules sur supports inclinés
    "faible": 15.0,
    "moyenne": 30.0,
    "forte": 45.0,
}
# Part de la surface de pan réellement couverte par les modules (marges de
# rive, espacements, rangées). Hypothèse de pré-dimensionnement, à remplacer
# par le calepinage de l'installateur.
OCCUPATION = {"incline": 0.80, "plat": 0.55}

# --- Consommation -----------------------------------------------------------
# Ordres de grandeur hors chauffage électrique (comparateurs, voir source).
CONSUMPTION_BY_OCCUPANTS_KWH = {1: 2200.0, 2: 3500.0, 4: 5500.0}

ROOF_TYPES = {
    "tuiles_mecaniques": "tuiles mécaniques",
    "tuiles_canal": "tuiles canal / romanes",
    "ardoise": "ardoise",
    "bac_acier": "bac acier",
    "fibrociment": "fibrociment",
    "toit_plat": "toit plat (membrane, gravillons)",
    "autre": "autre",
}
