from django.core.exceptions import ValidationError
from django.db import models
import uuid


class ExProvince(models.Model):
    """Modele representant les ex-provinces administratives de Madagascar."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom_ex_province = models.CharField(max_length=255, unique=True, verbose_name="Nom de l'ex-province")

    class Meta:
        db_table = 'ex_provinces'
        verbose_name = 'Ex-province'
        verbose_name_plural = 'Ex-provinces'
        ordering = ['nom_ex_province']

    def __str__(self):
        return self.nom_ex_province


class Region(models.Model):
    """Modèle représentant les régions administratives de Madagascar"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom_region = models.CharField(max_length=255, verbose_name="Nom de la région")
    photo = models.TextField(null=True, blank=True, verbose_name="Photo")
    ex_province = models.ForeignKey(
        ExProvince,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='regions',
        db_column='ex_province_id',
        verbose_name="Ex-province"
    )

    class Meta:
        db_table = 'regions'
        verbose_name = 'Région'
        verbose_name_plural = 'Régions'
        ordering = ['nom_region']

    def __str__(self):
        return self.nom_region


class District(models.Model):
    """Modèle représentant les districts rattachés aux régions"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom_district = models.CharField(max_length=255, verbose_name="Nom du district")
    photo = models.TextField(null=True, blank=True, verbose_name="Photo")
    region = models.ForeignKey(
        Region,
        on_delete=models.CASCADE,
        related_name='districts',
        db_column='region_id'
    )

    class Meta:
        db_table = 'districts'
        verbose_name = 'District'
        verbose_name_plural = 'Districts'
        ordering = ['region__nom_region', 'nom_district']
        unique_together = [['nom_district', 'region']]

    def __str__(self):
        return f"{self.nom_district} ({self.region.nom_region})"


class Commune(models.Model):
    """Modèle représentant les communes rattachées aux districts"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom_commune = models.CharField(max_length=255, verbose_name="Nom de la commune")
    photo = models.TextField(null=True, blank=True, verbose_name="Photo")
    district = models.ForeignKey(
        District,
        on_delete=models.CASCADE,
        related_name='communes',
        db_column='district_id'
    )

    class Meta:
        db_table = 'communes'
        verbose_name = 'Commune'
        verbose_name_plural = 'Communes'
        ordering = ['district__nom_district', 'nom_commune']
        unique_together = [['nom_commune', 'district']]

    def __str__(self):
        return f"{self.nom_commune} ({self.district.nom_district})"

    @property
    def region(self):
        """Accès direct à la région via le district"""
        return self.district.region


class Fokontany(models.Model):
    """Modèle représentant les fokontany rattachés aux communes"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom_fokontany = models.CharField(max_length=255, verbose_name="Nom du fokontany")
    photo = models.TextField(null=True, blank=True, verbose_name="Photo")
    commune = models.ForeignKey(
        Commune,
        on_delete=models.CASCADE,
        related_name='fokontanys',
        db_column='commune_id'
    )

    class Meta:
        db_table = 'fokontanys'
        verbose_name = 'Fokontany'
        verbose_name_plural = 'Fokontanys'
        ordering = ['commune__nom_commune', 'nom_fokontany']
        unique_together = [['nom_fokontany', 'commune']]

    def __str__(self):
        return f"{self.nom_fokontany} ({self.commune.nom_commune})"

    @property
    def district(self):
        """Accès direct au district via la commune"""
        return self.commune.district

    @property
    def region(self):
        """Accès direct à la région via la commune et le district"""
        return self.commune.district.region


class Village(models.Model):
    """Modèle représentant les villages rattachés aux fokontanys"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom_village = models.CharField(max_length=255, verbose_name="Nom du village")
    photo = models.TextField(null=True, blank=True, verbose_name="Photo")
    # Relation avec fokontany (parent direct)
    fokontany = models.ForeignKey(
        Fokontany,
        on_delete=models.CASCADE,
        related_name='villages',
        db_column='fokontany_id',
        null=True,
        blank=True
    )

    # Coordonnées GPS du village
    latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        verbose_name="Latitude",
        help_text="Latitude GPS du village (ex: -18.9332847)"
    )
    longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        verbose_name="Longitude",
        help_text="Longitude GPS du village (ex: 47.5360256)"
    )
    altitude = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Altitude (m)",
        help_text="Altitude en mètres"
    )

    # Accessibilité du village
    ACCESSIBILITE_CHOICES = [
        ('pied', 'À pied'),
        ('moto', 'Moto'),
        ('voiture', 'Voiture'),
        ('pirogue', 'Pirogue'),
        ('goudron', 'Route goudronnée'),
    ]

    accessibilite = models.CharField(
        max_length=50,
        choices=ACCESSIBILITE_CHOICES,
        null=True,
        blank=True,
        verbose_name="Accessibilité",
        help_text="Moyen d'accès principal au village"
    )
    distance_dernier_point = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Distance depuis dernier point accessible (km)",
        help_text="Distance en km depuis le dernier point accessible en véhicule"
    )

    class Meta:
        db_table = 'villages'
        verbose_name = 'Village'
        verbose_name_plural = 'Villages'
        ordering = ['fokontany__nom_fokontany', 'nom_village']
        unique_together = [['nom_village', 'fokontany']]

    def __str__(self):
        return f"{self.nom_village} ({self.fokontany.nom_fokontany})"

    @property
    def commune(self):
        """Accès direct à la commune via le fokontany"""
        return self.fokontany.commune

    @property
    def district(self):
        """Accès direct au district via la hiérarchie"""
        return self.fokontany.commune.district

    @property
    def region(self):
        """Accès direct à la région via la hiérarchie complète"""
        return self.fokontany.commune.district.region

    @property
    def enclavement(self):
        """
        Calcule le niveau d'enclavement du village selon les critères:
        - Route goudronnée (distance = 0)
        - Accessible en pirogue
        - Accessible en moto
        - Accessible en voiture
        - Moins de 3h de marche (distance < 15 km)
        - Plus de 3h de marche (distance >= 15 km)
        """
        if not self.accessibilite:
            return "Non renseigné"

        if self.accessibilite == 'goudron' or (self.accessibilite == 'voiture' and self.distance_dernier_point == 0):
            return "Route goudronnée"
        elif self.accessibilite == 'pirogue':
            return "Accessible en pirogue"
        elif self.accessibilite == 'moto':
            return "Accessible en moto"
        elif self.accessibilite == 'voiture':
            return "Accessible en voiture"
        elif self.accessibilite == 'pied':
            if self.distance_dernier_point is not None:
                if self.distance_dernier_point < 15:
                    return "Moins de 3h de marche"
                else:
                    return "Plus de 3h de marche"
            return "Accessible à pied"

        return "Non défini"

    def get_enclavement_badge_class(self):
        """Retourne la classe CSS du badge selon le niveau d'enclavement"""
        enclavement = self.enclavement
        if enclavement == "Route goudronnée":
            return "badge-success"
        elif enclavement in ["Accessible en voiture", "Accessible en moto"]:
            return "badge-info"
        elif enclavement == "Accessible en pirogue":
            return "badge-warning"
        elif enclavement == "Moins de 3h de marche":
            return "badge-warning"
        elif enclavement == "Plus de 3h de marche":
            return "badge-error"
        else:
            return "badge-ghost"


class LiaisonVillage(models.Model):
    """Relation orientee entre deux villages pour representer un organigramme."""
    TYPE_LIAISON_CHOICES = [
        ('desserte', 'Desserte'),
        ('proximite', 'Proximite'),
        ('dependance', 'Dependance'),
    ]
    TYPE_ROUTE_CHOICES = [
        ('route', 'Route'),
        ('piste', 'Piste'),
        ('sentier', 'Sentier'),
        ('riviere', 'Riviere'),
    ]
    MOYEN_ACCES_CHOICES = [
        ('voiture', 'Voiture'),
        ('moto', 'Moto'),
        ('pied', 'Pied'),
        ('pirogue', 'Pirogue'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    village_source = models.ForeignKey(
        Village,
        on_delete=models.CASCADE,
        related_name='liaisons_sortantes',
        db_column='village_source_id',
    )
    village_cible = models.ForeignKey(
        Village,
        on_delete=models.CASCADE,
        related_name='liaisons_entrantes',
        db_column='village_cible_id',
    )
    type_liaison = models.CharField(
        max_length=30,
        choices=TYPE_LIAISON_CHOICES,
        default='desserte',
        verbose_name="Type de liaison",
    )
    type_route = models.CharField(
        max_length=20,
        choices=TYPE_ROUTE_CHOICES,
        null=True,
        blank=True,
        verbose_name="Type de route",
    )
    distance_km = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Distance (km)",
    )
    temps_acces_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Temps d'acces (minutes)",
    )
    moyen_acces = models.CharField(
        max_length=20,
        choices=MOYEN_ACCES_CHOICES,
        null=True,
        blank=True,
        verbose_name="Moyen d'acces",
    )
    # Itinéraire calculé sur le réseau routier (services/liaisons_routes.py). Les valeurs saisies
    # à la main (distance_km, temps_acces_minutes) ne sont jamais écrasées automatiquement.
    ROUTE_STATUT_CHOICES = [
        ('', 'Non calculé'),
        ('ok', 'Calculé'),
        ('introuvable', 'Aucun chemin'),
        ('ignore', 'Hors route (pirogue / rivière)'),
    ]
    trace_route = models.JSONField(null=True, blank=True, verbose_name="Tracé routier",
                                   help_text="Liste de points [[lon, lat], ...] de village à village")
    distance_route_km = models.FloatField(null=True, blank=True, verbose_name="Distance par la route (km)")
    duree_route_min = models.PositiveIntegerField(null=True, blank=True, verbose_name="Durée par la route (min)")
    route_statut = models.CharField(max_length=12, choices=ROUTE_STATUT_CHOICES, blank=True, default='')
    route_calculee_le = models.DateTimeField(null=True, blank=True)

    ordre = models.PositiveIntegerField(default=0, verbose_name="Ordre")
    actif = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'liaisons_villages'
        verbose_name = 'Liaison entre villages'
        verbose_name_plural = 'Liaisons entre villages'
        ordering = ['ordre', 'village_source__nom_village', 'village_cible__nom_village']
        constraints = [
            models.UniqueConstraint(
                fields=['village_source', 'village_cible', 'type_liaison'],
                name='unique_liaison_village_source_cible_type',
            ),
        ]

    def __str__(self):
        return f"{self.village_source.nom_village} -> {self.village_cible.nom_village} ({self.get_type_liaison_display()})"

    def clean(self):
        if self.village_source_id and self.village_cible_id and self.village_source_id == self.village_cible_id:
            raise ValidationError("Un village ne peut pas etre relie a lui-meme.")
        if self.distance_km is not None and self.distance_km < 0:
            raise ValidationError("La distance ne peut pas etre negative.")


class Parcelle(models.Model):
    """Modèle représentant les parcelles rattachées aux villages"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference_parcelle = models.CharField(max_length=255, verbose_name="Référence de la parcelle")
    photo = models.TextField(null=True, blank=True, verbose_name="Photo")
    village = models.ForeignKey(
        Village,
        on_delete=models.CASCADE,
        related_name='parcelles',
        db_column='village_id'
    )
    # Nouveaux champs démographiques
    nombre_habitants = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Nombre d'habitants"
    )
    nombre_menages = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Nombre de ménages"
    )
    source_donnees = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Source des données",
        help_text="Source des données démographiques (ex: Recensement 2018, Enquête locale 2023)"
    )

    class Meta:
        db_table = 'parcelles'
        verbose_name = 'Parcelle'
        verbose_name_plural = 'Parcelles'
        ordering = ['village__nom_village', 'reference_parcelle']
        unique_together = [['reference_parcelle', 'village']]

    def __str__(self):
        return f"{self.reference_parcelle} ({self.village.nom_village})"

    @property
    def fokontany(self):
        """Accès direct au fokontany via le village"""
        return self.village.fokontany

    @property
    def commune(self):
        """Accès direct à la commune via le village et le fokontany"""
        return self.village.fokontany.commune

    @property
    def district(self):
        """Accès direct au district via la hiérarchie complète"""
        return self.village.fokontany.commune.district

    @property
    def region(self):
        """Accès direct à la région via la hiérarchie complète"""
        return self.village.fokontany.commune.district.region


class DonneeMeteo(models.Model):
    """Modèle pour stocker les données météorologiques (pluviométrie) par village"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    village = models.ForeignKey(
        Village,
        on_delete=models.CASCADE,
        related_name='donnees_meteo',
        db_column='village_id',
        verbose_name="Village"
    )
    date = models.DateField(
        verbose_name="Date",
        help_text="Date de la mesure météo",
        db_index=True
    )

    # Données pluviométriques
    precipitation = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Précipitations (mm)",
        help_text="Précipitations en millimètres"
    )

    # Autres données météo optionnelles
    temperature_min = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Température min (°C)"
    )
    temperature_max = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Température max (°C)"
    )
    humidite = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Humidité (%)"
    )

    # Métadonnées
    source_api = models.CharField(
        max_length=100,
        default='open-meteo',
        verbose_name="Source API",
        help_text="API utilisée pour récupérer les données"
    )
    recupere_le = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Récupéré le",
        help_text="Date et heure de récupération des données"
    )
    mise_a_jour_le = models.DateTimeField(
        auto_now=True,
        verbose_name="Mis à jour le"
    )

    class Meta:
        db_table = 'donnees_meteo'
        verbose_name = 'Donnée météo'
        verbose_name_plural = 'Données météo'
        ordering = ['-date', 'village__nom_village']
        unique_together = [['village', 'date']]
        indexes = [
            models.Index(fields=['village', 'date']),
            models.Index(fields=['date']),
        ]

    def __str__(self):
        precip = f"{self.precipitation}mm" if self.precipitation else "N/A"
        return f"{self.village.nom_village} - {self.date} - {precip}"


# Réseau routier (import shapefile voies)
from .models_routes import NoeudRoute, TronconRoute, VillageAccesRoute  # noqa: E402,F401

# Contours administratifs (import shapefiles Region, District, Communes, fokontany)
from .models_contours import ContourAdmin  # noqa: E402,F401
