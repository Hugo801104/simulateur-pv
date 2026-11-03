# Benchmark des outils de conseil photovoltaïque

Objectif : situer le mode Conseil par rapport à l'existant, reprendre les
bonnes pratiques et éviter les écueils. Recherche menée le 3 novembre 2026.
Les points tirés de connaissances générales, non revérifiés ce jour-là, sont
marqués *(non revérifié)*.

## 1. Les familles d'outils

| Famille | Exemples | Ce que l'utilisateur fournit | Ce qu'il obtient | Limites |
|---|---|---|---|---|
| **Calculateur de référence public** | [PVGIS](https://re.jrc.ec.europa.eu/pvg_tools/fr/) (Commission européenne) | Position, puissance crête, inclinaison, azimut, pertes | Production mensuelle et annuelle, données météo horaires | Demande de connaître la puissance et la géométrie ; pas de conseil, pas d'économie française. API sans CORS, donc pas appelable depuis un site statique (vérifié). |
| **Cadastres solaires territoriaux** | Cadastres d'agglomération réalisés par In Sun We Trust ou Cythelia ([Toulouse Métropole](https://metropole.toulouse.fr/demarches/tester-le-potentiel-solaire-de-sa-toiture), Landes, Grand Paris) | Adresse, clic sur le toit | Potentiel par pan de toit (ombrage inclus), simulation, orientation vers France Rénov' | Couverture limitée à certains territoires ; doivent être précis et à jour pour être utiles ([Que Choisir](https://www.quechoisir.org/actualite-photovoltaique-des-cadastres-solaires-a-consulter-avant-de-se-lancer-n127134/), [Hellowatt](https://www.hellowatt.fr/panneaux-solaires-photovoltaiques/cadastre-solaire)). |
| **Simulateurs commerciaux** | [La Prime Énergie](https://www.laprimeenergie.fr/les-travaux/le-panneau-solaire/simulateur-simulation), [Hellio](https://particulier.hellio.com/guide-solaire/fonctionnement/rendement-panneau-solaire/simulation), Hellowatt, [Les Énergies Renouvelables](https://www.les-energies-renouvelables.eu/simulation-simulateur-panneau-solaire-photovoltaique) | Adresse (vue satellite), consommation, surface, orientation | Puissance conseillée, prix, économies, scénarios avec ou sans batterie | Souvent des outils de prospection (coordonnées demandées pour le résultat détaillé) ; calculs et hypothèses peu visibles ; tarifs parfois périmés. Ils rappellent eux-mêmes qu'un artisan doit dimensionner. |
| **API d'imagerie de toiture** | Google Solar API *(non revérifié)* | Adresse | Géométrie des pans et ensoleillement depuis l'imagerie aérienne | Payante, clé d'API obligatoire : incompatible avec un site statique gratuit sans serveur. |
| **Logiciels professionnels** | PVsyst, Archelios, CALSOL (INES) *(non revérifié)* | Étude détaillée (calepinage, ombrages, matériel) | Dimensionnement d'ingénierie | Réservés aux bureaux d'études et installateurs. |

## 2. Constats

1. **L'adresse est la porte d'entrée commune.** Tous les outils grand public partent de l'adresse, qui donne l'ensoleillement local.
2. **Peu de questions, mais les bonnes.** Les simulateurs grand public demandent consommation, surface, orientation et inclinaison, rarement plus.
3. **La comparaison avec et sans batterie est attendue** ([La Prime Énergie](https://www.laprimeenergie.fr/les-travaux/le-panneau-solaire/simulateur-simulation)).
4. **Les tarifs publiés en ligne divergent fortement** : le même jour, des sites affichent un rachat du surplus à 4 c€/kWh et d'autres à 1,1 c€/kWh. Le tarif en vigueur depuis le 5 juin 2026 est de **1,1 c€/kWh** (arrêté du 1er juin 2026, [photovoltaique.info](https://www.photovoltaique.info/fr/actualites/detail/arrete-s21-detail-des-modifications-et-nouveau-tarif-unique/)). Un outil qui n'affiche pas la date de ses hypothèses peut induire en erreur.
5. **Les conseils de construction sont rares** dans les simulateurs : état de la charpente, de la couverture, amiante, secteur protégé, démarches. On les trouve dans des guides séparés ([photovoltaique.info](https://www.photovoltaique.info/fr/preparer-un-projet/quel-type-de-projet/photovoltaique-sur-batiment/points-de-vigilance-technique/), [service-public.fr](https://www.service-public.gouv.fr/particuliers/vosdroits/F36798)).
6. **Le résultat est souvent un chiffre unique** (« 6 kWc »), sans dire à quel point il est sensible aux hypothèses.

## 3. Choix retenus pour le mode Conseil

| Bonne pratique observée | Reprise dans le mode Conseil |
|---|---|
| Adresse en entrée, localisation automatique | Autocomplétion par la Géoplateforme IGN (gratuite, sans clé, CORS vérifié) |
| Questions simples | Toit (couverture, boussole d'orientation, pente, surface, ombre), foyer (consommation ou nombre de personnes, chauffage, présence en journée, chauffe-eau, véhicule) ; construction et urbanisme en options repliées |
| Scénarios avec ou sans batterie | Tableau comparatif : recommandée, meilleure sans batterie, meilleure avec batterie, toit complet, meilleure ≤ 9 kWc |

| Écueil observé | Réponse du mode Conseil |
|---|---|
| Tarifs périmés, hypothèses cachées | Base de connaissances unique (`engine/pvsim/knowledge.py`), chaque valeur avec sa source ; date de vérification affichée ; toutes les hypothèses listées sous le résultat |
| Chiffre unique, non discuté | Toutes les tailles sont évaluées au module près ; plage de tailles quasi équivalentes ; graphique de la valeur selon la taille |
| Rentabilité affirmée sans condition | **Prix de devis à viser** : investissement en dessous duquel le projet devient rentable, directement utilisable face aux devis |
| Conseils de construction absents | Pose selon la couverture, charpente (fermettes, toit plat), couverture à refaire, amiante (fibrociment avant 1997), secteur protégé ; étapes administratives avec liens officiels |
| Collecte de coordonnées | Aucune : calcul dans le navigateur, seules l'adresse et les coordonnées partent vers des services publics |
| Estimations présentées comme des mesures | Consommation estimée signalée ; refus d'estimer avec un chauffage électrique (écart trop grand) ; ombrage non modélisé signalé |

## 4. Limites assumées

- **Pas de lecture automatique du toit** (surface, pans, ombrage) : il faudrait une imagerie payante ou un cadastre local. L'utilisateur saisit la surface ; le taux d'occupation (80 %, 55 % sur toit plat) est une hypothèse de pré-dimensionnement.
- **Prix d'installation** : droite ajustée sur des fourchettes publiques (3 000 € + 1 700 €/kWc TTC), valable de 3 à 9 kWc. Les devis réels peuvent s'en écarter fortement, d'où le « prix à viser ».
- **Pas de marques** : le conseil porte sur des classes de modules (TOPCon standard, back-contact haut rendement), pas sur des produits.

## 5. Pistes

- Interroger les cadastres solaires locaux quand ils publient une API ouverte.
- Charger les servitudes d'urbanisme (Géoportail de l'urbanisme) pour détecter automatiquement les secteurs protégés.
- Ajouter l'option heures pleines / heures creuses et le pilotage du chauffe-eau dans le calcul.
