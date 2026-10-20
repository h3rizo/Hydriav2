from django.db import models
import uuid


class Region(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom_region = models.CharField(max_length=255)

    class Meta:
        db_table = 'regions'
        verbose_name = 'Région'
        verbose_name_plural = 'Régions'
        ordering = ['nom_region']

    def __str__(self):
        return self.nom_region


class District(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom_district = models.CharField(max_length=255)
    region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name='districts', null=True, blank=True)

    class Meta:
        db_table = 'districts'
        verbose_name = 'District'
        verbose_name_plural = 'Districts'
        ordering = ['nom_district']

    def __str__(self):
        return self.nom_district


class Commune(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom_commune = models.CharField(max_length=255)
    district = models.ForeignKey(District, on_delete=models.CASCADE, related_name='communes', null=True, blank=True)

    class Meta:
        db_table = 'communes'
        verbose_name = 'Commune'
        verbose_name_plural = 'Communes'
        ordering = ['nom_commune']

    def __str__(self):
        return self.nom_commune


class Fokontany(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom_fokontany = models.CharField(max_length=255)
    commune = models.ForeignKey(Commune, on_delete=models.CASCADE, related_name='fokontanys', null=True, blank=True)

    class Meta:
        db_table = 'fokontanys'
        verbose_name = 'Fokontany'
        verbose_name_plural = 'Fokontanys'
        ordering = ['nom_fokontany']

    def __str__(self):
        return self.nom_fokontany


class Village(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom_village = models.CharField(max_length=255)
    fokontany = models.ForeignKey(Fokontany, on_delete=models.CASCADE, related_name='villages', null=True, blank=True)

    class Meta:
        db_table = 'villages'
        verbose_name = 'Village'
        verbose_name_plural = 'Villages'
        ordering = ['nom_village']

    def __str__(self):
        return self.nom_village


class Parcelle(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference_parcelle = models.CharField(max_length=255, unique=True)
    village = models.ForeignKey(Village, on_delete=models.CASCADE, related_name='parcelles')
    nombre_habitants = models.IntegerField(null=True, blank=True)
    nombre_menages = models.IntegerField(null=True, blank=True)
    source_donnees = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = 'parcelles'
        verbose_name = 'Parcelle'
        verbose_name_plural = 'Parcelles'
        ordering = ['reference_parcelle']

    def __str__(self):
        return self.reference_parcelle
