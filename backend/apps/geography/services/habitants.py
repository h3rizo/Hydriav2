"""
Agrégation de la population par zone géographique.

Les habitants ne sont saisis qu'au niveau des parcelles (`Parcelle.nombre_habitants`).
Pour afficher un compteur d'habitants au-dessus de chaque tableau de la page
`/geography/` (régions, districts, communes, fokontanys, villages), il faut donc
remonter la cascade village -> fokontany -> commune -> district -> région -> ex-province.

Une seule requête groupée suffit pour tout un niveau, ce qui évite une requête par zone.
"""
from django.db import models

from ..models import Parcelle

# Chemin ORM depuis Parcelle vers chaque niveau de la cascade géographique.
CHEMINS_HABITANTS = {
    'ex_province': 'village__fokontany__commune__district__region__ex_province',
    'region': 'village__fokontany__commune__district__region',
    'district': 'village__fokontany__commune__district',
    'commune': 'village__fokontany__commune',
    'fokontany': 'village__fokontany',
    'village': 'village',
}


def habitants_par_zone(zones, niveau):
    """
    Somme des habitants des parcelles pour chaque zone d'un niveau de la cascade.

    `zones` : queryset de zones (ExProvince, Region, District, Commune, Fokontany, Village)
    `niveau` : cle de CHEMINS_HABITANTS

    Retourne un dict {id_zone: total_habitants}. Les parcelles des villages sans
    fokontany sont exclues (jointure interne) et une valeur NULL de
    `nombre_habitants` est ignoree par SUM.
    """
    chemin = CHEMINS_HABITANTS[niveau]
    lignes = (
        Parcelle.objects
        .filter(**{f'{chemin}__in': zones.values('id')})
        .values(chemin)
        .annotate(total=models.Sum('nombre_habitants'))
        .order_by()
    )
    return {ligne[chemin]: (ligne['total'] or 0) for ligne in lignes}
