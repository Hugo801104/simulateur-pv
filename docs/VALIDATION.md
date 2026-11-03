# Validation par rapport aux estimations publiées

Comparaison menée le 3 novembre 2026 entre les résultats du simulateur et les
estimations trouvables en ligne, puis ajustements du modèle là où un écart
était justifié. Les écarts sans justification n'ont pas été « corrigés » par
un coefficient : ils sont documentés ici.

## 1. Production : comparaison avec PVGIS sur 10 villes

Référence : [PVGIS](https://re.jrc.ec.europa.eu/pvg_tools/fr/) (Commission européenne, base SARAH3,
2005–2023), installation de 1 kWc, 30° plein sud, 14 % de pertes. Résultats du simulateur en kWh/kWc par an.

| Ville | PVGIS | Notre moteur, TMY PVGIS | Notre moteur, Open-Meteo moyenne 2016–2025 | Open-Meteo 2025 seule | Selon l'année (2016–2025) |
|---|---|---|---|---|---|
| Lille | 1 062 | 1 060 (−0,2 %) | 1 113 (+4,8 %) | 1 182 | 1 011–1 200 |
| Brest | 1 128 | 1 106 (−1,9 %) | 1 183 (+4,9 %) | 1 250 | 1 083–1 274 |
| Paris | 1 137 | 1 155 (+1,6 %) | 1 147 (+0,9 %) | 1 203 | 1 037–1 226 |
| Strasbourg | 1 133 | 1 110 (−2,0 %) | 1 187 (+4,8 %) | 1 224 | 1 121–1 269 |
| Nantes | 1 214 | 1 194 (−1,7 %) | 1 234 (+1,6 %) | 1 294 | 1 116–1 296 |
| Lyon | 1 281 | 1 291 (+0,8 %) | 1 299 (+1,4 %) | 1 316 | 1 230–1 386 |
| Bordeaux | 1 270 | 1 247 (−1,8 %) | 1 270 (+0,1 %) | 1 336 | 1 213–1 336 |
| Toulouse | 1 305 | 1 244 (−4,7 %) | 1 308 (+0,3 %) | 1 361 | 1 272–1 361 |
| Marseille | 1 611 | 1 559 (−3,2 %) | 1 572 (−2,4 %) | 1 557 | 1 485–1 608 |
| Nice | 1 520 | 1 528 (+0,5 %) | 1 491 (−1,9 %) | 1 498 | 1 380–1 540 |
| **Écart moyen** | | **−1,3 %** | **+1,5 %** | **+3,5 % vs moyenne 10 ans** | |

Constats :

- **Modèle physique** : sur les mêmes données météo que PVGIS, l'écart moyen est de −1,3 %
  (PVGIS ajoute l'ombrage du relief et les effets spectraux). Pas de correction.
- **Une seule année de météo est trompeuse** : 2025 était ensoleillée (+3,5 % en moyenne,
  jusqu'à +6 %), et la production varie d'environ ±8 % d'une année à l'autre.
  → **Corrigé** : le mode Conseil télécharge 10 ans, retient l'année la plus proche de la moyenne
  et ramène sa production à cette moyenne. La plage selon l'année est affichée.
- **Open-Meteo (ERA5) sur 10 ans vs PVGIS** : +1,5 % en moyenne, jusqu'à +5 % dans le Nord et l'Ouest.
  Les deux bases diffèrent (réanalyse contre satellite) et ne couvrent pas la même période
  (2016–2025 contre 2005–2023). Aucun coefficient correctif n'est appliqué ; l'écart reste dans la
  variabilité d'une année à l'autre.

## 2. Autoconsommation

| Situation | Publié | Simulateur (Lyon, 3 kWc, 4 500 kWh/an) |
|---|---|---|
| Sans batterie, sans pilotage | ≈ 40 % ([Hello Watt](https://www.hellowatt.fr/blog/autoconsommation-electrique-photovoltaique)), 30 à 50 % selon d'autres sites | 39 % |
| Avec batterie | 70 à 80 % (sites vendant des batteries) | 72 % avec 5 kWh |
| Avec pilotage du chauffe-eau | 60 à 65 % dans les simulations publiées après la réforme de juin 2026 | **63 %** (26 % si chauffé la nuit) |

→ **Ajouté** : modèle de pilotage du chauffe-eau électrique. Consommation 600 kWh par personne et
par an (milieu de la fourchette 400–800 kWh, [Selectra](https://selectra.info/energie/guides/conso/chauffe-eau-electrique)),
chauffé la nuit sans pilotage ; avec pilotage, d'abord sur le surplus solaire de la journée.
Le pilotage est supposé en place quand il y a un chauffe-eau électrique, car un système de gestion
de l'énergie est exigé pour la TVA à 5,5 %. Le gain est affiché.

## 3. Prix

| Puissance | Potentiel Solaire | La Prime Énergie (milieu) | EDF Solutions Solaires (milieu) | Simulateur |
|---|---|---|---|---|
| 3 kWc | 6 752 € | 8 250 € | 9 000 € | 8 100 € |
| 6 kWc | 10 867 € | 13 250 € | 16 000 € | 13 200 € |
| 9 kWc | 14 032 € | 18 500 € | 19 000 € | 18 300 € |

Sources : [Potentiel Solaire](https://www.potentielsolaire.com/prix-panneaux-solaires),
[La Prime Énergie](https://www.laprimeenergie.fr/les-travaux/le-panneau-solaire/simulateur-simulation),
[EDF Solutions Solaires](https://www.edf-solutions-solaires.com/guide-solaire/prix-panneau-solaire-3kwc-6kwc-9kwc/).

→ Le modèle (3 000 € + 1 700 €/kWc) correspond à la médiane des sources : **pas de changement**.
**Ajouté** : la fourchette publiée est affichée à côté de l'estimation, et le « prix de devis à viser »
indique si la cible est atteignable.

| Poste | Avant | Publié | Après |
|---|---|---|---|
| Batterie | 600 €/kWh | 600 à 1 000 €/kWh installé ([Selectra](https://selectra.info/energie/actualites/renovation-energetique/batterie-domestique-rentable-apres-reforme-2026)) | **800 €/kWh** |
| Remplacement de l'onduleur | 150 €/kWc la 15e année (≈ 460 € pour 3 kWc) | 800 à 1 200 € après 10 à 12 ans ([Prix-pose](https://www.prix-pose.com/panneaux-solaires-apercu/prix-pour-maison-100m2)) | **1 000 € la 12e année** |

## 4. Rentabilité

| Scénario publié (après la réforme de juin 2026) | Retour publié | Simulateur, cas comparable |
|---|---|---|
| Autoconsommation ≈ 60–65 % grâce au pilotage | 12 à 17 ans | 16 à 18 ans (Lyon, Paris, Marseille, 3 kWc, chauffe-eau piloté) |
| Sans pilotage | plus de 20 ans | non atteint sur 25 ans |

Le simulateur est un peu plus prudent que la moyenne des sites, car il compte la maintenance
(1 %/an de l'investissement) et le remplacement de l'onduleur, souvent omis, et il ne valorise plus
le surplus après les 20 ans du contrat de rachat. Les sources publiées sont surtout des sites
d'installateurs ou de comparateurs ([Bourse Inside](https://bourseinside.fr/economie/panneaux-solaires-la-reforme-2026-met-fin-aux-aides-voici-la-seule-condition-pour-que-votre-installation-reste-rentable/),
[Solarock](https://solarock.fr/blog/rentabilite-panneaux-solaires),
[Frexolaire](https://www.frexolaire.com/blog/fin-prime-autoconsommation-rachat-1-centime-2026/)).

## 5. Reproduire

- Production : `engine/tests/test_physics.py` compare automatiquement le moteur à PVGIS pour Lyon (±5 %).
- Année représentative, chauffe-eau, prix : `engine/tests/test_advisor.py`.
- Le tableau des 10 villes a été obtenu avec les API PVGIS (`PVcalc`, `tmy`) et Open-Meteo (2016–2025).
