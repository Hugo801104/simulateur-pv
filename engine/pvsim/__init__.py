"""Moteur de simulation photovoltaïque (autoconsommation, batterie, économie).

Le moteur est indépendant de l'interface : il s'exécute à l'identique sous
CPython (tests, scripts) et dans le navigateur via Pyodide.

Modules :
    params        collecte et validation des paramètres
    weather       lecture des données météo (Open-Meteo, NASA POWER, PVGIS)
    physics       modèles physiques (pvlib)
    load          profils de consommation
    simulation    bilan énergétique horaire et batterie
    economics     calcul économique (VAN, TRI, LCOE, temps de retour)
    optimisation  recherche de la meilleure taille d'installation
    api           point d'entrée JSON utilisé par l'interface
"""

__version__ = "1.0.0"
