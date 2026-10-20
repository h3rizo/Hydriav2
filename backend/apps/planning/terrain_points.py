"""Points de contribution Terrain + garde-fous sur les coordonnees GPS.

- Bareme : 10 pts par GPS ou photo, 5 pts par nom d'abonne ou telephone.
- Anti-triche : un champ ne rapporte des points que s'il etait VIDE sur le
  serveur, et une seule fois a vie (registre TerrainContribution).
- Distance : un point d'eau doit etre a moins de 2 km de son village, un
  equipement a moins de 3 km du village le plus proche desservi par l'ouvrage.
  Directeur et Responsable operationnel peuvent autoriser une exception.
"""
from django.db import IntegrityError, transaction
from django.db.models import Sum

from apps.employees.permissions import can_override_saisie_controls
from apps.geography.services.reseau_routier import haversine_m
from apps.planning.models_terrain_points import TerrainContribution

BAREME = {
    TerrainContribution.CHAMP_GPS: 10,
    TerrainContribution.CHAMP_PHOTO: 10,
    TerrainContribution.CHAMP_NOM: 5,
    TerrainContribution.CHAMP_TELEPHONE: 5,
}

DISTANCE_MAX_POINT_EAU_M = 2000
DISTANCE_MAX_EQUIPEMENT_M = 3000


def attribuer(employe, cible_type, cible_id, champs):
    """Accorde les points des `champs` (deja filtres : vides avant l'envoi).

    Retourne le nombre de points reellement gagnes (0 si deja accordes).
    """
    if employe is None:
        return 0
    gagnes = 0
    for champ in champs:
        try:
            with transaction.atomic():
                TerrainContribution.objects.create(
                    employe=employe, cible_type=cible_type, cible_id=str(cible_id),
                    champ=champ, points=BAREME[champ],
                )
            gagnes += BAREME[champ]
        except IntegrityError:
            continue  # deja accorde : effacer puis re-saisir ne rapporte rien
    return gagnes


def total_points(employe):
    if employe is None:
        return 0
    return TerrainContribution.objects.filter(employe=employe).aggregate(t=Sum('points'))['t'] or 0


def infos_points(employe, gagnes):
    return {'points_gagnes': gagnes, 'points_total': total_points(employe)}


def _distance_m(lat1, lon1, lat2, lon2):
    return haversine_m(float(lon1), float(lat1), float(lon2), float(lat2))


def _villages_de_reference(cible_type, cible):
    from apps.billing.models import PointEau
    if cible_type == TerrainContribution.CIBLE_POINT_EAU:
        village = getattr(getattr(cible, 'parcelle', None), 'village', None)
        return [village] if village else []
    if not getattr(cible, 'ouvrage_id', None):
        return []
    points = PointEau.objects.filter(ouvrage_id=cible.ouvrage_id).select_related('parcelle__village')
    seen, villages = set(), []
    for point in points:
        village = getattr(getattr(point, 'parcelle', None), 'village', None)
        if village and village.id not in seen:
            seen.add(village.id)
            villages.append(village)
    return villages


def controle_distance_gps(user, cible_type, cible, latitude, longitude):
    """Message d'erreur si les coordonnees sont trop loin du village, sinon None.

    Sans coordonnees de village connues, on ne peut pas controler : on laisse passer.
    """
    if can_override_saisie_controls(user):
        return None
    limite = DISTANCE_MAX_POINT_EAU_M if cible_type == TerrainContribution.CIBLE_POINT_EAU else DISTANCE_MAX_EQUIPEMENT_M
    distances = [
        _distance_m(latitude, longitude, v.latitude, v.longitude)
        for v in _villages_de_reference(cible_type, cible)
        if v.latitude is not None and v.longitude is not None
    ]
    if not distances:
        return None
    plus_proche = min(distances)
    if plus_proche <= limite:
        return None
    return (
        f"Coordonnees refusees : {plus_proche / 1000:.1f} km du village desservi "
        f"(maximum {limite // 1000} km). Si cette position est correcte, demandez a votre "
        f"responsable ou au directeur de l'enregistrer."
    )
