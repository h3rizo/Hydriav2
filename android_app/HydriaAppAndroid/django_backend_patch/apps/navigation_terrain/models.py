import uuid

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models


hex_color = RegexValidator(r'^#[0-9A-Fa-f]{6}$', 'Couleur hexadécimale invalide.')


class TypeRepere(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    icone = models.CharField(max_length=50, default='autre')
    couleur = models.CharField(max_length=7, default='#58D594', validators=[hex_color])
    ordre_affichage = models.PositiveIntegerField(default=0)
    actif = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'navigation_types_reperes'
        ordering = ('ordre_affichage', 'nom')

    def __str__(self):
        return self.nom


class Repere(models.Model):
    CAPTURE_CHOICES = (('gps', 'GPS'), ('carte', 'Carte'))
    MARKER_CATEGORY_CHOICES = (
        ('landmark', 'Repere'),
        ('water_point', "Point d'eau"),
        ('equipment', 'Equipement'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom = models.CharField(max_length=255)
    marker_category = models.CharField(max_length=20, choices=MARKER_CATEGORY_CHOICES, default='landmark')
    type_repere = models.ForeignKey(TypeRepere, on_delete=models.PROTECT, related_name='reperes')
    latitude = models.DecimalField(max_digits=10, decimal_places=7)
    longitude = models.DecimalField(max_digits=10, decimal_places=7)
    altitude = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    accuracy_m = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    remarques = models.TextField(blank=True)
    capture_method = models.CharField(max_length=10, choices=CAPTURE_CHOICES)
    captured_at = models.DateTimeField()
    createur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='reperes_terrain')
    village = models.ForeignKey('geography.Village', on_delete=models.SET_NULL, null=True, blank=True, related_name='reperes_terrain')
    ouvrage = models.ForeignKey('organization.Ouvrage', on_delete=models.SET_NULL, null=True, blank=True, related_name='reperes_terrain')
    organisation = models.ForeignKey('organization.Organisation', on_delete=models.SET_NULL, null=True, blank=True, related_name='reperes_terrain')
    version = models.PositiveIntegerField(default=1)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'navigation_reperes'
        indexes = [
            models.Index(fields=('ouvrage', 'archived_at'), name='nav_rep_ouv_arch'),
            models.Index(fields=('organisation', 'updated_at'), name='nav_rep_org_upd'),
        ]

    def __str__(self):
        return self.nom


class ReperePhoto(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    local_uuid = models.UUIDField(unique=True)
    repere = models.ForeignKey(Repere, on_delete=models.CASCADE, related_name='photos')
    fichier = models.FileField(upload_to='navigation-terrain/reperes/')
    nom = models.CharField(max_length=180)
    mime_type = models.CharField(max_length=80)
    taille = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)
    ordre = models.PositiveIntegerField(default=0)
    legende = models.CharField(max_length=255, blank=True)
    createur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='photos_reperes_terrain')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'navigation_reperes_photos'
        ordering = ('ordre', 'created_at')


class GeoPositionAudit(models.Model):
    ENTITY_CHOICES = (
        ('village', 'Village'), ('water_point', "Point d'eau"),
        ('equipment', 'Équipement'), ('landmark', 'Repère'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    local_uuid = models.UUIDField(unique=True)
    entity_kind = models.CharField(max_length=20, choices=ENTITY_CHOICES)
    entity_uuid = models.UUIDField(db_index=True)
    old_latitude = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True)
    old_longitude = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True)
    new_latitude = models.DecimalField(max_digits=11, decimal_places=8)
    new_longitude = models.DecimalField(max_digits=11, decimal_places=8)
    old_altitude = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    new_altitude = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    accuracy_m = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    capture_method = models.CharField(max_length=10, choices=Repere.CAPTURE_CHOICES)
    captured_at = models.DateTimeField()
    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='audits_positions_terrain')
    received_at = models.DateTimeField(auto_now_add=True)
    appareil = models.CharField(max_length=160, blank=True)
    motif = models.CharField(max_length=255, blank=True)
    technical_data = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'navigation_geo_position_audits'
        indexes = [models.Index(fields=('entity_kind', 'entity_uuid', '-received_at'), name='nav_audit_entity')]
