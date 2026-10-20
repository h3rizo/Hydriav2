import uuid

from django.db import models
from django.db.models import Q


class PointageGPS(models.Model):
    """Pointage de présence géolocalisé d'un employé sur un créneau (matin / après-midi / nuit).

    Toute tentative est enregistrée, acceptée ou refusée, pour l'audit.
    `timestamp` est l'instant retenu pour la fenêtre horaire : heure du serveur
    en ligne, heure de capture de l'appareil en hors ligne (`hors_ligne=True`).
    """

    TYPE_MATIN = 'matin'
    TYPE_APREM = 'aprem'
    TYPE_NUIT = 'nuit'
    TYPE_CHOICES = [
        (TYPE_MATIN, 'Matinée'),
        (TYPE_APREM, 'Après-midi'),
        (TYPE_NUIT, 'Nuitée'),
    ]

    STATUT_VALIDE = 'valide'
    STATUT_REFUSE_DISTANCE = 'refuse_distance'
    STATUT_REFUSE_HORAIRE = 'refuse_horaire'
    STATUT_REFUSE_GPS = 'refuse_gps'
    STATUT_REFUSE_SANS_COORD = 'refuse_sans_coordonnees'
    STATUT_REFUSE_SANS_PLANNING = 'refuse_sans_planning'
    STATUT_CHOICES = [
        (STATUT_VALIDE, 'Valide'),
        (STATUT_REFUSE_DISTANCE, 'Refusé : trop loin du site'),
        (STATUT_REFUSE_HORAIRE, 'Refusé : hors créneau'),
        (STATUT_REFUSE_GPS, 'Refusé : position GPS invalide'),
        (STATUT_REFUSE_SANS_COORD, 'Refusé : village sans coordonnées GPS'),
        (STATUT_REFUSE_SANS_PLANNING, 'Refusé : aucun planning ce jour'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employe = models.ForeignKey('employees.Employe', on_delete=models.CASCADE, related_name='pointages_gps')
    planning = models.ForeignKey(
        'planning.Planning', on_delete=models.SET_NULL, null=True, blank=True, related_name='pointages_gps',
    )
    village_retenu = models.ForeignKey(
        'geography.Village', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
        help_text="Village le plus proche du planning au moment du pointage",
    )

    timestamp = models.DateTimeField(help_text="Instant retenu pour valider la fenêtre horaire")
    recu_le = models.DateTimeField(auto_now_add=True, help_text="Réception par le serveur")
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    precision_m = models.FloatField(null=True, blank=True)
    distance_m = models.FloatField(null=True, blank=True)

    type_pointage = models.CharField(max_length=10, choices=TYPE_CHOICES, null=True, blank=True)
    statut_validation = models.CharField(max_length=30, choices=STATUT_CHOICES)

    hors_ligne = models.BooleanField(default=False, help_text="Capturé sans réseau puis synchronisé")
    position_simulee = models.BooleanField(default=False, help_text="Mock location détectée sur l'appareil")
    local_uuid = models.UUIDField(null=True, blank=True, unique=True, help_text="Idempotence de la synchronisation")

    class Meta:
        db_table = 'pointages_gps'
        verbose_name = 'Pointage GPS'
        verbose_name_plural = 'Pointages GPS'
        ordering = ['-timestamp']
        constraints = [
            models.UniqueConstraint(
                fields=['planning', 'type_pointage'],
                condition=Q(statut_validation='valide'),
                name='uniq_pointage_valide_par_creneau',
            ),
        ]
        indexes = [
            models.Index(fields=['employe', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.employe_id} {self.type_pointage} {self.statut_validation} {self.timestamp:%Y-%m-%d %H:%M}"
