"""Paramètres métier du réseau routier : catégories et vitesses moyennes par profil de déplacement."""

# Valeur brute du champ TYPE du shapefile (en minuscules) -> catégorie normalisée.
CATEGORIE_PAR_TYPE = {
    'rn': 'nationale',
    'rnc': 'nationale',
    'rip': 'provinciale',
    'cip': 'communale',
    'route': 'route',
    'piste': 'piste',
    'piste secondaire ou sentier': 'sentier',
    'sentier': 'sentier',
    'vers source': 'sentier',
}

# Priorité quand plusieurs tracés se superposent : le plus "important" gagne.
RANG_CATEGORIE = ['nationale', 'provinciale', 'communale', 'route', 'piste', 'sentier', 'autre']

# --- Vitesses moyennes (km/h) par profil de déplacement et par catégorie de voie ---------------------
# Ce sont des vitesses MOYENNES de bout en bout (arrêts, villages traversés, état de la voie compris),
# pas des vitesses de pointe. Elles servent quand TronconRoute.vitesse_kmh est vide.
#
# Calibration (2026-10-10), sur les 561 trajets GPS continus (0,5-10 min) des agents de l'année :
#   - un pic de MARCHE à 2-6 km/h (≈ 37 % des trajets) ;
#   - une longue traîne de déplacements motorisés de 20 à 120 km/h (médiane 10,7 ; p75 28 ; p90 66).
# Les données GPS sont trop clairsemées pour se ventiler par type de voie : les valeurs ci-dessous
# sont des estimations raisonnables pour Madagascar, à affiner avec le retour terrain.
PROFILS = {
    # Moto : le déplacement de référence des agents terrain (profil par défaut).
    'moto': {
        'nationale': 45, 'provinciale': 35, 'communale': 25, 'route': 30,
        'piste': 18, 'sentier': 6, 'autre': 14, 'raccord': 5,
    },
    # Voiture / 4x4 / taxi-brousse : plus rapide sur le bitume, impossible sur un sentier (donc marche).
    'voiture': {
        'nationale': 55, 'provinciale': 40, 'communale': 28, 'route': 35,
        'piste': 15, 'sentier': 4, 'autre': 11, 'raccord': 5,
    },
    # À pied : indépendant du revêtement ; un peu plus lent sur les sentiers (relief).
    'pied': {
        'nationale': 4.5, 'provinciale': 4.5, 'communale': 4.5, 'route': 4.5,
        'piste': 4.5, 'sentier': 4.0, 'autre': 4.0, 'raccord': 4.0,
    },
}
PROFIL_DEFAUT = 'moto'
PROFILS_LIBELLES = {'moto': 'Moto', 'voiture': 'Voiture / 4x4', 'pied': 'À pied'}

# Champ LiaisonVillage.moyen_acces -> profil de calcul (pirogue : non routier, ignoré en amont).
PROFIL_PAR_MOYEN_ACCES = {'moto': 'moto', 'voiture': 'voiture', 'pied': 'pied'}

# Compatibilité : ancienne table unique = profil par défaut.
VITESSE_DEFAUT_KMH = PROFILS[PROFIL_DEFAUT]

# Tolérance pour rattacher une extrémité isolée à un tracé voisin (mètres).
TOLERANCE_RACCORD_M = 8.0

# Vitesse de marche entre un village et la route qui le dessert (km/h).
VITESSE_MARCHE_KMH = 4.0
