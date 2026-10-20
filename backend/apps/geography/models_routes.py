"""Réseau routier : tronçons (polylignes) et nœuds (intersections / extrémités).

Le réseau sert de base au calcul d'itinéraires entre villages (graphe networkx
construit en mémoire à partir de ces deux tables). La géométrie est stockée en
JSON ([[lon, lat], ...]) : pas besoin de PostGIS.
"""
import uuid

from django.db import models


class NoeudRoute(models.Model):
    """Point du réseau où des tronçons se rejoignent (ou s'arrêtent)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    longitude = models.DecimalField(max_digits=10, decimal_places=7)
    latitude = models.DecimalField(max_digits=10, decimal_places=7)

    class Meta:
        db_table = 'routes_noeuds'
        verbose_name = 'Noeud routier'
        verbose_name_plural = 'Noeuds routiers'
        constraints = [
            models.UniqueConstraint(fields=['longitude', 'latitude'], name='unique_noeud_route_coord'),
        ]

    def __str__(self):
        return f"({self.latitude}, {self.longitude})"


class TronconRoute(models.Model):
    """Portion de voie entre deux nœuds, avec sa géométrie réelle (courbe)."""
    SOURCE_CHOICES = [
        ('shapefile', 'Shapefile voies'),
        ('raccord', 'Raccord automatique'),
        ('manuel', 'Tracé manuel'),
    ]
    CATEGORIE_CHOICES = [
        ('nationale', 'Route nationale'),
        ('provinciale', "Route d'intérêt provincial"),
        ('communale', "Chemin d'intérêt provincial/communal"),
        ('route', 'Route'),
        ('piste', 'Piste'),
        ('sentier', 'Sentier'),
        ('autre', 'Autre / non renseigné'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom = models.CharField(max_length=255, blank=True, default='')
    type_voie = models.CharField(max_length=80, blank=True, default='',
                                 help_text="Valeur brute du champ TYPE du shapefile")
    categorie = models.CharField(max_length=20, choices=CATEGORIE_CHOICES, default='autre')
    interet = models.CharField(max_length=20, blank=True, default='',
                               help_text="Village / Fokontany / Commune / District")
    commune_nom = models.CharField(max_length=60, blank=True, default='')
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='shapefile')

    noeud_debut = models.ForeignKey(NoeudRoute, on_delete=models.CASCADE, related_name='troncons_debut')
    noeud_fin = models.ForeignKey(NoeudRoute, on_delete=models.CASCADE, related_name='troncons_fin')
    geometrie = models.JSONField(help_text="Liste de points [[lon, lat], ...] du début à la fin")
    longueur_m = models.FloatField(help_text="Longueur géodésique réelle en mètres")

    vitesse_kmh = models.FloatField(null=True, blank=True,
                                    help_text="Vitesse moyenne ; vide = valeur par défaut de la catégorie")
    praticable = models.BooleanField(default=True, help_text="Décocher pour exclure des itinéraires")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'routes_troncons'
        verbose_name = 'Tronçon de route'
        verbose_name_plural = 'Tronçons de route'
        indexes = [models.Index(fields=['source']), models.Index(fields=['categorie'])]

    def __str__(self):
        return f"{self.nom or self.type_voie or 'Tronçon'} ({self.longueur_m:.0f} m)"


class VillageAccesRoute(models.Model):
    """Point d'accès d'un village au réseau routier (projection sur le tronçon le plus proche).

    Pour router depuis/vers un village : nœud virtuel au point `fraction` du tronçon,
    relié aux deux extrémités du tronçon, plus la distance `distance_m` de la route
    au village (parcours à pied).
    """
    village = models.OneToOneField('geography.Village', on_delete=models.CASCADE,
                                   related_name='acces_route')
    troncon = models.ForeignKey(TronconRoute, on_delete=models.CASCADE, related_name='villages_acces')
    fraction = models.FloatField(help_text="Position sur le tronçon, 0 = nœud de début, 1 = nœud de fin")
    distance_m = models.FloatField(help_text="Distance du village au réseau, en mètres")
    longitude = models.DecimalField(max_digits=10, decimal_places=7, help_text="Point projeté sur la route")
    latitude = models.DecimalField(max_digits=10, decimal_places=7)
    reseau_principal = models.BooleanField(
        default=True, help_text="False si le tronçon est dans un morceau de réseau isolé du réseau principal")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'routes_villages_acces'
        verbose_name = "Accès route d'un village"
        verbose_name_plural = "Accès route des villages"
        indexes = [models.Index(fields=['distance_m'])]

    def __str__(self):
        return f"{self.village_id} -> {self.distance_m:.0f} m"
