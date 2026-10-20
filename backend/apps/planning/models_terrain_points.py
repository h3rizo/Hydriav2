"""Registre des points gagnes en renseignant les donnees de base (app Terrain).

Un point n'est accorde qu'UNE seule fois par (cible, champ), a vie : effacer puis
re-saisir une donnee ne rapporte rien, car la ligne du registre existe deja.
"""
import uuid

from django.db import models


class TerrainContribution(models.Model):
    CIBLE_POINT_EAU = 'point_eau'
    CIBLE_EQUIPEMENT = 'equipement'
    CIBLES = [(CIBLE_POINT_EAU, "Point d'eau"), (CIBLE_EQUIPEMENT, 'Equipement')]

    CHAMP_GPS = 'gps'
    CHAMP_PHOTO = 'photo'
    CHAMP_NOM = 'nom_abonne'
    CHAMP_TELEPHONE = 'telephone'
    CHAMPS = [
        (CHAMP_GPS, 'Coordonnees GPS'),
        (CHAMP_PHOTO, 'Photo'),
        (CHAMP_NOM, "Nom d'abonne"),
        (CHAMP_TELEPHONE, 'Telephone'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employe = models.ForeignKey(
        'employees.Employe', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='terrain_contributions',
    )
    cible_type = models.CharField(max_length=20, choices=CIBLES)
    cible_id = models.CharField(max_length=64)
    champ = models.CharField(max_length=20, choices=CHAMPS)
    points = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'terrain_contributions'
        constraints = [
            models.UniqueConstraint(
                fields=['cible_type', 'cible_id', 'champ'],
                name='uniq_terrain_contribution_cible_champ',
            ),
        ]
        indexes = [models.Index(fields=['employe', 'created_at'])]
