# Architecture et choix techniques

## 1. Contraintes

- Hébergement **GitLab Pages** : fichiers statiques uniquement, pas de serveur Python ni Node.
- Calculs côté client, aucun service payant ni backend obligatoire.
- Site servi sous un sous-chemin (`https://<utilisateur>.gitlab.io/<projet>/`).
- Moteur de calcul indépendant de l'interface et testable séparément.
- Données météo publiques, sans jamais inventer de valeurs en cas d'échec.

## 2. Comparaison des architectures

Deux architectures ont été comparées, avec des vérifications concrètes plutôt que des hypothèses.

### Vérifications préalables (novembre 2026)

| Point vérifié | Résultat |
|---|---|
| pvlib dans Pyodide | pvlib 0.16.1 est une roue 100 % Python (`py3-none-any`). Toutes ses dépendances (NumPy 2.4.6, SciPy 1.18.0, pandas 3.0.2, h5py, requests, pytz, tzdata) sont fournies par Pyodide 314.0.7. |
| Exécution réelle | Le moteur complet tourne dans Pyodide (test `tests/pyodide/smoke.mjs`), avec des résultats **identiques à la dernière décimale** à CPython. |
| CORS de l'API PVGIS | **Bloquant** : aucune en-tête `Access-Control-Allow-Origin`. Le navigateur refuse la réponse. |
| CORS d'Open-Meteo et de NASA POWER | Autorisé (`Access-Control-Allow-Origin: *`). |

### Évaluation

| Critère | A. Pyodide + pvlib | B. Tout en TypeScript |
|---|---|---|
| Précision scientifique | Modèles de référence utilisés tels quels (pvlib, maintenu et validé par la communauté) | Réimplémentation de chaque modèle (SPA, Perez, Faiman, PVWatts…), avec un risque d'écart silencieux |
| Compatibilité PV | pvlib complet, y compris les lecteurs de fichiers PVGIS | Aucune bibliothèque TypeScript de niveau équivalent |
| Performances | Démarrage de 20 à 30 s au premier chargement. Ensuite : simulation horaire en 0,3 s, 51 combinaisons d'optimisation en 0,5 s | Démarrage immédiat, calcul plus rapide |
| Téléchargement | ≈ 57 Mo une fois, puis cache (service worker) | ≈ 0,3 Mo |
| Maintenance | Mises à jour de pvlib récupérées directement ; un seul langage pour la science | Toute évolution scientifique à reporter et revalider à la main |
| Tests indépendants | pytest sous CPython, et le même code vérifié dans Pyodide | Tests possibles, mais des valeurs de référence pvlib restent nécessaires pour valider |
| Déploiement | Statique, compatible GitLab Pages | Statique, compatible GitLab Pages |

### Choix : A, avec une interface en TypeScript

La précision et la traçabilité scientifique priment : B obligerait à réécrire
des modèles qui existent déjà, testés et documentés. Les coûts de A sont maîtrisés :

- le calcul tourne dans un **Web Worker** : l'interface reste fluide pendant le démarrage ;
- Pyodide est **auto-hébergé** dans le site (aucun CDN à l'exécution) et mis en cache par un service worker ;
- les sorties physiques sont linéaires en puissance crête : l'optimisation réutilise un profil calculé une seule fois.

Le **TypeScript** est réservé à ce que Python ne peut pas faire dans le navigateur, ou fait moins bien :
l'interface, les appels réseau (`fetch`), le cache et les graphiques. Aucun
calcul scientifique n'y est fait, donc il n'y a pas de double implémentation à maintenir cohérente.

## 3. Organisation

```
Navigateur
├── Thread principal (TypeScript)
│   ├── ui/       formulaire, résultats, graphiques (Chart.js)
│   ├── data/     API météo : délai maximal, nouvelle tentative, repli, cache local
│   └── engine/client.ts  ── messages JSON ──┐
└── Web Worker                               │
    └── Pyodide (Python 3.14 en WebAssembly) ◄┘
        └── pvsim (engine/pvsim)
            params → weather → physics → load → simulation → economics → optimisation
                                   api.py : entrée et sortie JSON
```

Séparation des responsabilités :

| Couche | Module | Rôle |
|---|---|---|
| Interface | `src/ui`, `src/main.ts` | Saisie, affichage, aucun calcul |
| Collecte et validation | `src/ui/form.ts` → `pvsim/params.py` | Le formulaire rassemble les valeurs ; Python valide et renvoie toutes les erreurs par champ |
| Données externes | `src/data` → `pvsim/weather.py` | Le navigateur télécharge ; Python lit, contrôle et normalise |
| Modèles physiques | `pvsim/physics.py` | Chaîne pvlib |
| Simulation énergétique | `pvsim/simulation.py` | Bilan horaire, batterie |
| Optimisation | `pvsim/optimisation.py` | Grille puissance × batterie |
| Économie | `pvsim/economics.py` | Flux de trésorerie, VAN, TRI, LCOE |
| Restitution | `pvsim/api.py` → `src/ui/results.ts`, `charts.ts` | Agrégats mensuels et journaliers, export CSV horaire |

Le contrat entre interface et moteur est vérifié par un test
(`engine/tests/test_interface_contract.py`) : chaque champ du formulaire
correspond à un paramètre du moteur, avec la même valeur par défaut.

## 4. Modèles physiques

Pour chaque heure, dans `pvsim/physics.py` :

1. **Position du soleil** : `pvlib.solarposition.get_solarposition` (NREL SPA), à l'instant représentatif de la valeur météo (voir § 5).
2. **Irradiance dans le plan** : `pvlib.irradiance.get_total_irradiance`, modèle de ciel **Perez 1990** (DNI extraterrestre, masse d'air relative), albédo réglable.
3. **Pertes optiques** : `pvlib.iam.physical` (Fresnel) sur le direct ; `pvlib.iam.marion_diffuse` sur le diffus du ciel et du sol.
4. **Température des cellules** : `pvlib.temperature.faiman` (U0 = 25 W/m²K et U1 = 6,84 W·s/m³K par défaut, réglables).
5. **Puissance DC** : `pvlib.pvsystem.pvwatts_dc`, coefficient de température réglable (−0,37 %/°C par défaut).
6. **Pertes système** : pourcentage global (14 % par défaut, comme PVGIS) pour salissures, câblage, mismatch et disponibilité.
7. **Onduleur** : `pvlib.inverter.pvwatts`, courbe de rendement et écrêtage selon le ratio DC/AC.

### Validation

| Comparaison (Lyon, 30° plein sud, 14 % de pertes) | PVGIS PVcalc | Ce moteur (même TMY PVGIS) | Écart |
|---|---|---|---|
| Production annuelle (kWh/kWc) | 1 281 | 1 291 | +0,8 % |
| Irradiation dans le plan (kWh/m²) | 1 623 | 1 676 | +3,3 % |

L'écart d'irradiation vient surtout de l'ombrage du relief, que PVGIS prend en
compte et que ce moteur ne modélise pas. Les trois sources météo donnent des
productions cohérentes entre elles (1 291 à 1 296 kWh/kWc). Ces comparaisons
sont des tests automatisés (`engine/tests/test_physics.py`, tolérance ±5 %).

### Non modélisé

- Ombrage du relief et des obstacles proches. L'API d'horizon PVGIS n'est pas accessible depuis le navigateur.
- Effets spectraux, neige, modules bifaces, suivi solaire.
- Dégradation au sein de l'année 1 (la dégradation est appliquée d'une année sur l'autre, § 7).

## 5. Données météorologiques

| Source | Accès | Contenu | Convention horaire (vérifiée) |
|---|---|---|---|
| Open-Meteo, archive ERA5 | API, CORS autorisé | GHI, DNI, DHI, température, vent | Moyenne sur l'heure **précédant** l'horodatage |
| NASA POWER | API, CORS autorisé | GHI, DNI, DHI, température, vent | Moyenne sur l'heure **suivant** l'horodatage |
| PVGIS TMY | **Import de fichier** (pas de CORS) | Année météorologique type | Valeur instantanée, décalage fourni dans le fichier (« Irradiance Time Offset ») |

Les conventions horaires ont été vérifiées sur données réelles, en mesurant la
corrélation avec un modèle de ciel clair pour plusieurs décalages. Ce contrôle est
automatisé (`test_timestamp_convention_matches_sun`). Un décalage de 30 minutes
fausserait sinon la position du soleil, donc la production matin et soir.

**Robustesse réseau** (`src/data`) :

- délai maximal de 45 s, une nouvelle tentative sur erreur réseau ou 5xx, message dédié en cas de limite de requêtes (429) ;
- mode automatique : Open-Meteo, puis NASA POWER en cas d'échec ; chaque tentative est rapportée à l'utilisateur ;
- cache local (Cache API) des réponses valides, sans expiration (données historiques) : une étude déjà faite fonctionne hors connexion ;
- coordonnées arrondies à 0,01° (environ 1 km) pour mieux réutiliser le cache ;
- en cas d'échec complet : erreur explicite, avec suggestion d'importer un fichier PVGIS. **Aucune valeur n'est inventée.**

**Contrôles à la lecture** (`pvsim/weather.py`) : année complète (au moins 8 760 h),
aucune heure manquante (sinon refus), valeurs physiquement plausibles, unités
attendues (UTC, vent en m/s). Les valeurs de remplissage NASA (−999) sont traitées comme manquantes.

## 6. Consommation

- **Courbe de charge importée** (recommandé) : CSV à deux colonnes (date, valeur), pas de temps d'une heure ou moins, en W, kW ou kWh, dates avec ou sans fuseau. Si l'année diffère de la météo, l'association se fait par date et heure. Les trous de 3 h ou moins sont interpolés et signalés ; au-delà de 1 % d'heures manquantes, le fichier est refusé.
- **Profil simplifié** : forme journalière (pointes matin et soir) et saisonnière fixe, normalisée sur la consommation annuelle. Ce profil est **illustratif**, il n'est pas issu de mesures, et l'interface l'indique à chaque résultat.

## 7. Simulation et économie

**Batterie** (`simulation.py`) : charge avec le surplus PV, décharge dès que la
consommation dépasse la production, sans charge depuis le réseau. Limites de puissance et
d'état de charge minimal ; rendement aller-retour réparti également entre charge
et décharge ; démarrage à l'état de charge minimal. Le bilan énergétique est
vérifié par les tests (production = direct + charge + injection, etc.).

**Économie** (`economics.py`) :

- année 1 = simulation horaire ; les années suivantes, production, autoconsommation et injection sont réduites de la dégradation annuelle ;
- gains = électricité non achetée × prix (évolution annuelle) + injection × tarif de revente ;
- coûts = investissement net des aides, maintenance annuelle (% de l'investissement), remplacement de l'onduleur et de la batterie ;
- flux de fin d'année actualisés : VAN, TRI (`scipy.optimize.brentq`), temps de retour simple et actualisé, LCOE.

Les coûts par défaut (2 000 € de frais fixes + 1 700 €/kWc, batterie 600 €/kWh, achat
0,2016 €/kWh, revente 0,04 €/kWh) sont des **ordres de grandeur indicatifs** à
remplacer par des devis et les tarifs en vigueur.

**Optimisation** (`optimisation.py`) : recherche exhaustive sur la grille
puissance × batterie (2 000 combinaisons au maximum), critère VAN ou TRI. Une
grille est préférée à un optimiseur numérique : le problème est petit, non lisse
(écrêtage, batterie), et l'utilisateur voit toutes les options. Si l'optimum
tombe sur une borne de la grille, un avertissement invite à l'élargir.

## 8. Déploiement

- **Vite** construit un site statique avec `base: './'` : tous les chemins sont relatifs, donc compatibles avec n'importe quel sous-chemin.
- Les sources Python sont intégrées au bundle du worker au moment du build (`import.meta.glob`).
- `scripts/fetch-pyodide.mjs` télécharge Pyodide et les paquets nécessaires (dépendances résolues depuis `pyodide-lock.json`, empreintes SHA-256 vérifiées) dans `static/pyodide/`.
- Le pipeline GitLab : tests Python, tests TypeScript, téléchargement de Pyodide et test du moteur dans Pyodide, construction, publication.

### Tailles

| Élément | Taille |
|---|---|
| Interface (JS + CSS + HTML) | ≈ 75 ko compressés |
| Worker (moteur Python inclus) | 55 ko |
| Pyodide + NumPy + SciPy + pandas + pvlib | ≈ 57 Mo (une seule fois, puis cache) |

Le plus gros fichier est la roue pvlib (19 Mo), dont l'essentiel est constitué
de fichiers de données que ce moteur n'utilise pas (bases de modules,
turbidité de Linke). Une roue allégée réduirait le premier chargement d'environ
un tiers. Elle n'est pas fournie, pour garder la distribution officielle de pvlib intacte.

## 9. Pistes d'évolution

- Import d'un fichier d'horizon PVGIS pour l'ombrage lointain.
- Tarifs heures pleines / heures creuses et pilotage de la batterie en conséquence.
- Plusieurs orientations de toiture (est-ouest).
- Roue pvlib allégée pour accélérer le premier chargement.
