"""Contours administratifs (shapefiles Region, District, Communes, fokontany) : polygones WGS84 + attributs.

Pas de PostGIS : les géométries sont stockées en JSON (GeoJSON) en deux niveaux de détail, avec leur
rectangle englobant pour filtrer par zone visible. Le lien avec la base (`objet_id`) est facultatif : la
base ne contient qu'une partie des communes et des fokontany du pays.
"""
import uuid

from django.db import models


class ContourAdmin(models.Model):
    NIVEAUX = [
        ('region', 'Région'),
        ('district', 'District'),
        ('commune', 'Commune'),
        ('fokontany', 'Fokontany'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    niveau = models.CharField(max_length=10, choices=NIVEAUX, db_index=True)
    cle = models.CharField(max_length=80, help_text="Clé d'import : P-CODE (région, district) ou OBJECTID (commune, fokontany)")
    nom = models.CharField(max_length=120)
    p_code = models.CharField(max_length=20, blank=True, default='', db_index=True)
    c_code = models.CharField(max_length=15, blank=True, default='')

    # Rattachement administratif (noms et codes du shapefile)
    commune_nom = models.CharField(max_length=80, blank=True, default='')
    district_nom = models.CharField(max_length=80, blank=True, default='')
    district_pcode = models.CharField(max_length=15, blank=True, default='')
    region_nom = models.CharField(max_length=60, blank=True, default='')
    region_pcode = models.CharField(max_length=10, blank=True, default='')

    # Attributs (surtout renseignés pour les communes)
    type_admin = models.CharField(max_length=40, blank=True, default='',
                                  help_text="CR, CU, Chef-lieu District/Région/Province, Capitale, District…")
    inter_aide = models.CharField(max_length=40, blank=True, default='',
                                  help_text="Intervention d'aide : oui / non / Partenariat potentiel")
    enclave = models.CharField(max_length=10, blank=True, default='')
    accessibilite = models.CharField(max_length=60, blank=True, default='')
    statut_soakoja = models.CharField(max_length=60, blank=True, default='',
                                      help_text="Situation de la commune vis-à-vis de Soakoja")
    ouvrages = models.TextField(blank=True, default='', help_text="Ouvrages recensés (texte libre du shapefile)")
    superficie_km2 = models.FloatField(null=True, blank=True)

    geometrie = models.JSONField(help_text="Géométrie GeoJSON détaillée")
    geometrie_simple = models.JSONField(help_text="Géométrie GeoJSON très simplifiée, pour les vues d'ensemble")
    ouest = models.FloatField()
    sud = models.FloatField()
    est = models.FloatField()
    nord = models.FloatField()

    objet_id = models.UUIDField(null=True, blank=True, db_index=True,
                                help_text="Id de la Région / du District / de la Commune / du Fokontany correspondant en base")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'contours_admin'
        verbose_name = 'Contour administratif'
        verbose_name_plural = 'Contours administratifs'
        ordering = ['niveau', 'region_nom', 'district_nom', 'nom']
        unique_together = [('niveau', 'cle')]
        indexes = [models.Index(fields=['niveau', 'ouest', 'est', 'sud', 'nord'])]

    def __str__(self):
        return f"{self.get_niveau_display()} {self.nom}"
