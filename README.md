# Simulateur PV

Simulation d'une installation photovoltaïque en autoconsommation, entièrement
dans le navigateur : production horaire (modèles **pvlib**), batterie, bilan
économique et recherche du meilleur dimensionnement.

Le site est **100 % statique** : il se déploie gratuitement sur GitLab Pages,
sans serveur à administrer. Le moteur de calcul est écrit en Python et
s'exécute dans le navigateur grâce à **Pyodide** (Python compilé en WebAssembly).

Deux modes :

- **Conseil** (par défaut) : l'utilisateur décrit seulement sa maison (adresse, toit, foyer). L'application recommande
  le nombre et le type de panneaux, la puissance, l'onduleur, l'intérêt d'une batterie, le prix de devis à viser,
  les points de construction à vérifier et les démarches. Chaque conseil cite sa source ; voir [docs/BENCHMARK.md](docs/BENCHMARK.md).
- **Expert** : tous les paramètres techniques et économiques sont réglables.

Fonctionnalités :

- Météo horaire téléchargée depuis **Open-Meteo** (ERA5) ou **NASA POWER**, ou importée depuis un fichier **PVGIS**.
- Chaîne physique pvlib : position du soleil, transposition Perez, pertes optiques, température Faiman, PVWatts, onduleur.
- Batterie (autoconsommation maximale), courbe de charge importée (export Enedis) ou profil simplifié.
- VAN, TRI, temps de retour, LCOE, trésorerie sur la durée d'étude.
- Optimisation puissance × batterie sur une grille.
- Fonctionne hors connexion une fois chargé (données météo en cache ou fichier PVGIS).

Les choix d'architecture, les modèles et les hypothèses sont décrits dans
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) ; la comparaison avec PVGIS et les estimations
publiées (production sur 10 villes, autoconsommation, prix, rentabilité) dans
[docs/VALIDATION.md](docs/VALIDATION.md).

## Démarrage rapide

Prérequis : **Node.js 20.19 ou plus récent**. Python n'est nécessaire que pour
lancer les tests du moteur sous CPython.

```bash
git clone https://gitlab.com/<utilisateur>/simulateur-pv.git
cd simulateur-pv
npm ci
npm run setup
npm run dev
```

`npm run setup` télécharge Pyodide et les paquets Python (environ 57 Mo) dans
`static/pyodide/`. Il suffit de le relancer après une mise à jour de
`pyodide.config.json`. Le site s'ouvre ensuite sur http://localhost:5173/.
Au premier chargement, le moteur met 20 à 30 secondes à démarrer (indicateur
en haut à droite) ; le formulaire reste utilisable pendant ce temps.

## Tests

| Commande | Ce qui est testé |
|---|---|
| `npm test` | Interface : accès aux API, cache, repli entre sources, formulaire (Vitest) |
| `npm run typecheck` | Types TypeScript |
| `npm run test:pyodide` | Le moteur exécuté **dans Pyodide** donne les mêmes résultats que sous CPython |
| `cd engine && python -m pytest` | Moteur Python : validation, météo, physique (comparaison PVGIS), batterie, économie, optimisation |

Pour les tests Python, avec les mêmes versions que dans le navigateur :

```bash
python -m venv .venv
.venv/bin/pip install -r engine/requirements-dev.txt   # Windows : .venv\Scripts\pip
cd engine
../.venv/bin/python -m pytest
```

## Tester comme sur GitLab Pages

GitLab Pages sert le site sous un sous-chemin (`https://<utilisateur>.gitlab.io/<projet>/`).
Pour vérifier le site construit dans les mêmes conditions :

```bash
npm run build
npm run preview:pages
```

Le site est alors servi sur http://localhost:8090/simulateur-pv/.

## Déploiement sur GitHub Pages

Le site est publié sur **https://hugo801104.github.io/simulateur-pv/**.

Le workflow [.github/workflows/pages.yml](.github/workflows/pages.yml) s'exécute à chaque push sur `main` :
tests du moteur et de l'interface, téléchargement de Pyodide, test du moteur dans Pyodide, construction,
puis publication. Pour un autre dépôt : **Settings > Pages > Source = GitHub Actions**, aucun secret nécessaire.
Les pull requests lancent les tests et la construction, sans publier.

## Déploiement sur GitLab Pages

1. Créez un projet GitLab et poussez ce dépôt sur sa branche par défaut (`main`).
2. Le pipeline défini dans [.gitlab-ci.yml](.gitlab-ci.yml) s'exécute automatiquement :
   - `test:engine` : tests du moteur sous Python 3.14 (même version que Pyodide) ;
   - `test:frontend` : vérification des types et tests de l'interface ;
   - `build` : téléchargement de Pyodide, test du moteur dans Pyodide, construction du site ;
   - `pages` : publication du dossier `public/` (branche par défaut uniquement).
3. L'adresse du site apparaît dans **Déploiement > Pages** du projet. Si le projet est privé,
   réglez la visibilité de Pages dans **Paramètres > Général > Visibilité**.

**Variables CI/CD : aucune n'est nécessaire.** Les autres branches exécutent les
tests et la construction, sans publier.

Les chemins du site sont relatifs : il fonctionne aussi bien sous un sous-chemin
qu'à la racine d'un domaine (option « domaine unique » de GitLab Pages, domaine personnalisé).

## Mise à jour

**Tarifs, prix et règles du mode Conseil** : tout est regroupé dans
[engine/pvsim/knowledge.py](engine/pvsim/knowledge.py) (tarif de rachat, prix de l'électricité, TVA,
prix d'installation, classes de modules, sources). Mettez à jour les valeurs et `VERIFIED_ON`,
puis lancez les tests et régénérez le cas de référence si besoin. Les valeurs par défaut du mode expert
en dépendent aussi (gardez `index.html` aligné : un test le vérifie).

**Application** : poussez sur `main`. Le service worker revalide la page à
chaque visite, donc la nouvelle version s'affiche dès le rechargement suivant.

**Pyodide ou pvlib** :

1. Modifiez `pyodide.config.json` : `pyodideVersion` et/ou l'entrée `pvlib`
   (URL et empreinte SHA-256 de la roue, disponibles sur https://pypi.org/project/pvlib/#files).
2. Alignez `engine/requirements-dev.txt` sur les versions de NumPy, SciPy et pandas
   fournies par cette version de Pyodide (fichier `static/pyodide/pyodide-lock.json`),
   et `PYTHON_IMAGE` dans `.gitlab-ci.yml` sur sa version de Python.
3. Lancez `npm run setup`, puis les tests. Si les résultats de référence évoluent légitimement,
   régénérez-les avec `python engine/tests/reference_case.py` et vérifiez l'écart.

Le cache du navigateur est renouvelé automatiquement (le service worker lit les
versions dans `static/pyodide/manifest.json`).

## Structure du dépôt

```
engine/                 Moteur de calcul Python (indépendant de l'interface)
  pvsim/params.py         paramètres et validation
  pvsim/weather.py        lecture des données météo (Open-Meteo, NASA POWER, PVGIS)
  pvsim/physics.py        modèles physiques pvlib
  pvsim/load.py           profils de consommation
  pvsim/simulation.py     bilan horaire et batterie
  pvsim/economics.py      calcul économique
  pvsim/optimisation.py   dimensionnement optimal
  pvsim/advisor.py        mode Conseil (recommandations)
  pvsim/knowledge.py      tarifs, prix, règles et sources du mode Conseil
  pvsim/api.py            point d'entrée JSON utilisé par l'interface
  tests/                  tests pytest et données réelles de référence (Lyon)
src/
  engine/                 Web Worker qui héberge Pyodide, client et types
  data/                   accès aux API météo, cache, gestion des erreurs réseau
  ui/                     formulaire, résultats, graphiques
  main.ts                 orchestration
static/                 fichiers copiés tels quels (service worker, icône, Pyodide)
scripts/                téléchargement de Pyodide, serveur de test « GitLab Pages »
tests/unit/             tests Vitest de l'interface
tests/pyodide/          test du moteur dans Pyodide
```

## Données et conditions d'utilisation

- **Adresses** : Géoplateforme de l'IGN (géocodage gratuit, sans clé).
- **Open-Meteo** : licence CC BY 4.0, API gratuite **pour un usage non commercial**
  (environ 10 000 appels par jour). Pour un usage commercial, un abonnement Open-Meteo est requis.
- **NASA POWER** : données publiques de la NASA.
- **PVGIS** : © Union européenne. L'API PVGIS n'accepte pas les appels depuis un navigateur ;
  téléchargez l'année type (TMY) sur le site PVGIS puis importez le fichier.

Aucune donnée météo n'est jamais inventée : en cas d'échec ou de série
incomplète, l'application affiche l'erreur et propose une autre source.
