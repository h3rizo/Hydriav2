from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from apps.infrastructure.models import EquipementConstitutif, TypeEquipement
from apps.organization.models import Ouvrage
from apps.billing.models import TypePointEau
from apps.employees.models import Employe
from apps.filemanager.models import FileUpload
import uuid

# Import du modèle AnalyseEau
from .models_analyse_eau import AnalyseEau


class PointDeControle(models.Model):
    """Catalogue de toutes les vérifications possibles."""
    
    class ResultatType(models.TextChoices):
        BOOLEAN = 'BOOL', 'Booléen (Bon / Pas Bon)'
        NUMERIC = 'NUM', 'Numérique'
        TEXT = 'TEXT', 'Texte libre'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom = models.CharField(max_length=255, help_text="Ex: Pression du manomètre")
    description = models.TextField(blank=True, help_text="Explication détaillée de ce qu'il faut faire.")
    type_resultat = models.CharField(max_length=4, choices=ResultatType.choices)
    
    # Valeurs de référence pour les contrôles numériques
    valeur_min = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Valeur minimale acceptable")
    valeur_max = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Valeur maximale acceptable")
    unite = models.CharField(max_length=50, blank=True, help_text="Unité de mesure (ex: bar, l/min)")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'points_de_controle'
        verbose_name = 'Point de Contrôle'
        verbose_name_plural = 'Points de Contrôle'
        ordering = ['nom']

    def __str__(self):
        return self.nom

    def get_activites_correctives_possibles(self):
        """Retourne la liste des activités correctives possibles pour ce point de contrôle."""
        from apps.planning.models import Activite
        activites_ids = self.activites_correctives_possibles.values_list('activite_id', flat=True)
        return Activite.objects.filter(id__in=activites_ids, is_active=True).order_by('nom')


class ComposantTypeEquipement(models.Model):
    """Composants standards d'un type d'équipement (ex: Captage -> Bassin versant, Clôture, etc.)"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom_composant = models.CharField(max_length=100, verbose_name="Nom du composant")
    description = models.TextField(blank=True, verbose_name="Description")
    type_equipement = models.ForeignKey(TypeEquipement, on_delete=models.CASCADE, related_name='composants')
    ordre_affichage = models.IntegerField(default=1, verbose_name="Ordre d'affichage")
    est_obligatoire = models.BooleanField(default=True, verbose_name="Composant obligatoire")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'composants_types_equipements'
        verbose_name = 'Composant de Type d\'Équipement'
        verbose_name_plural = 'Composants de Types d\'Équipements'
        unique_together = ['type_equipement', 'nom_composant']
        ordering = ['ordre_affichage', 'nom_composant']

    def __str__(self):
        return f"{self.type_equipement.nom_type} - {self.nom_composant}"


class ComposantTypePointEau(models.Model):
    """Composants standards d'un type de point d'eau (ex: Borne fontaine -> Maçonnerie, Plomberie, etc.)"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom_composant = models.CharField(max_length=100, verbose_name="Nom du composant")
    description = models.TextField(blank=True, verbose_name="Description")
    type_point_eau = models.ForeignKey(TypePointEau, on_delete=models.CASCADE, related_name='composants')
    ordre_affichage = models.IntegerField(default=1, verbose_name="Ordre d'affichage")
    est_obligatoire = models.BooleanField(default=True, verbose_name="Composant obligatoire")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'composants_types_points_eau'
        verbose_name = 'Composant de Type de Point d\'Eau'
        verbose_name_plural = 'Composants de Types de Points d\'Eau'
        unique_together = ['type_point_eau', 'nom_composant']
        ordering = ['ordre_affichage', 'nom_composant']

    def __str__(self):
        return f"{self.type_point_eau.nom_type} - {self.nom_composant}"


class PointDeControleComposant(models.Model):
    """Liaison entre points de contrôle et composants - définit quels points contrôler pour chaque composant"""

    class TypeVisite(models.TextChoices):
        ROUTINIERE = 'ROUTINIERE', 'Visite Routinière (Entretien)'
        ANNUELLE = 'ANNUELLE', 'Visite Annuelle (Complète)'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    point_de_controle = models.ForeignKey(PointDeControle, on_delete=models.CASCADE, related_name='composants_lies')
    composant_equipement = models.ForeignKey(ComposantTypeEquipement, on_delete=models.CASCADE, null=True, blank=True, related_name='points_controle')
    composant_point_eau = models.ForeignKey(ComposantTypePointEau, on_delete=models.CASCADE, null=True, blank=True, related_name='points_controle')

    # Type de visite : routinière (inclus dans les deux) ou annuelle (seulement visite annuelle)
    type_visite = models.CharField(
        max_length=20,
        choices=TypeVisite.choices,
        default=TypeVisite.ROUTINIERE,
        verbose_name="Type de visite",
        help_text="Routinière = inclus dans visites routinières ET annuelles, Annuelle = seulement visites annuelles"
    )

    est_obligatoire = models.BooleanField(default=True, verbose_name="Point de contrôle obligatoire")
    ordre_affichage = models.IntegerField(default=1, verbose_name="Ordre d'affichage")

    # Photo de référence pour comparaison lors de l'inspection
    photo_reference = models.ForeignKey(FileUpload, on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name='points_controle_reference',
                                      verbose_name="Photo de référence")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'points_controle_composants'
        verbose_name = 'Point de Contrôle de Composant'
        verbose_name_plural = 'Points de Contrôle de Composants'
        ordering = ['ordre_affichage']

    def clean(self):
        """Validation : un seul type de composant doit être défini"""
        from django.core.exceptions import ValidationError
        if not self.composant_equipement and not self.composant_point_eau:
            raise ValidationError("Un composant d'équipement ou de point d'eau doit être spécifié")
        if self.composant_equipement and self.composant_point_eau:
            raise ValidationError("Un seul type de composant peut être spécifié")

    def __str__(self):
        composant = self.composant_equipement or self.composant_point_eau
        type_badge = "📅" if self.type_visite == self.TypeVisite.ROUTINIERE else "📆"
        return f"{type_badge} {composant} - {self.point_de_controle.nom}"


class PointDeControleSpecifique(models.Model):
    """Points de contrôle spécifiques à un équipement individuel (non communs au type)"""

    class TypeVisite(models.TextChoices):
        ROUTINIERE = 'ROUTINIERE', 'Visite Routinière (Entretien)'
        ANNUELLE = 'ANNUELLE', 'Visite Annuelle (Complète)'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Équipement spécifique (pas le type, mais l'équipement individuel)
    equipement = models.ForeignKey(
        EquipementConstitutif,
        on_delete=models.CASCADE,
        related_name='points_controle_specifiques',
        verbose_name="Équipement concerné"
    )

    # Point de contrôle à appliquer
    point_de_controle = models.ForeignKey(
        PointDeControle,
        on_delete=models.CASCADE,
        related_name='equipements_specifiques',
        verbose_name="Point de contrôle"
    )

    # Type de visite
    type_visite = models.CharField(
        max_length=20,
        choices=TypeVisite.choices,
        default=TypeVisite.ROUTINIERE,
        verbose_name="Type de visite",
        help_text="Routinière = inclus dans visites routinières ET annuelles, Annuelle = seulement visites annuelles"
    )

    # Paramètres spécifiques à cet équipement (peuvent surcharger les valeurs du point de contrôle générique)
    valeur_min_specifique = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name="Valeur min spécifique (surcharge)",
        help_text="Si défini, remplace la valeur min du point de contrôle générique"
    )
    valeur_max_specifique = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name="Valeur max spécifique (surcharge)",
        help_text="Si défini, remplace la valeur max du point de contrôle générique"
    )

    est_obligatoire = models.BooleanField(default=True, verbose_name="Point de contrôle obligatoire")
    ordre_affichage = models.IntegerField(default=1, verbose_name="Ordre d'affichage")

    # Remarques spécifiques à cet équipement
    remarques = models.TextField(
        blank=True,
        verbose_name="Remarques spécifiques",
        help_text="Particularités propres à cet équipement"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'points_controle_specifiques'
        verbose_name = 'Point de Contrôle Spécifique'
        verbose_name_plural = 'Points de Contrôle Spécifiques'
        unique_together = ['equipement', 'point_de_controle', 'type_visite']
        ordering = ['ordre_affichage', 'point_de_controle__nom']

    def __str__(self):
        type_badge = "📅" if self.type_visite == self.TypeVisite.ROUTINIERE else "📆"
        return f"{type_badge} {self.equipement.nom} - {self.point_de_controle.nom}"

    @property
    def valeur_min_effective(self):
        """Retourne la valeur min effective (spécifique si définie, sinon générique)"""
        return self.valeur_min_specifique if self.valeur_min_specifique is not None else self.point_de_controle.valeur_min

    @property
    def valeur_max_effective(self):
        """Retourne la valeur max effective (spécifique si définie, sinon générique)"""
        return self.valeur_max_specifique if self.valeur_max_specifique is not None else self.point_de_controle.valeur_max


class PointDeControleSpecifiquePointEau(models.Model):
    """Points de controle specifiques a un point d'eau individuel (non communs au type)"""

    class TypeVisite(models.TextChoices):
        ROUTINIERE = 'ROUTINIERE', 'Visite Routiniere (Entretien)'
        ANNUELLE = 'ANNUELLE', 'Visite Annuelle (Complete)'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Point d'eau specifique (pas le type, mais le point d'eau individuel)
    point_eau = models.ForeignKey(
        'billing.PointEau',
        on_delete=models.CASCADE,
        related_name='points_controle_specifiques',
        verbose_name="Point d'eau concerne"
    )

    # Point de controle a appliquer
    point_de_controle = models.ForeignKey(
        PointDeControle,
        on_delete=models.CASCADE,
        related_name='points_eau_specifiques',
        verbose_name="Point de controle"
    )

    # Type de visite
    type_visite = models.CharField(
        max_length=20,
        choices=TypeVisite.choices,
        default=TypeVisite.ROUTINIERE,
        verbose_name="Type de visite",
        help_text="Routiniere = inclus dans visites routinieres ET annuelles, Annuelle = seulement visites annuelles"
    )

    # Parametres specifiques a ce point d'eau (peuvent surcharger les valeurs du point de controle generique)
    valeur_min_specifique = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name="Valeur min specifique (surcharge)",
        help_text="Si defini, remplace la valeur min du point de controle generique"
    )
    valeur_max_specifique = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name="Valeur max specifique (surcharge)",
        help_text="Si defini, remplace la valeur max du point de controle generique"
    )

    est_obligatoire = models.BooleanField(default=True, verbose_name="Point de controle obligatoire")
    ordre_affichage = models.IntegerField(default=1, verbose_name="Ordre d'affichage")

    # Remarques specifiques a ce point d'eau
    remarques = models.TextField(
        blank=True,
        verbose_name="Remarques specifiques",
        help_text="Particularites propres a ce point d'eau"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'points_controle_specifiques_points_eau'
        verbose_name = 'Point de Controle Specifique Point Eau'
        verbose_name_plural = 'Points de Controle Specifiques Points Eau'
        unique_together = ['point_eau', 'point_de_controle', 'type_visite']
        ordering = ['ordre_affichage', 'point_de_controle__nom']

    def __str__(self):
        type_badge = "R" if self.type_visite == self.TypeVisite.ROUTINIERE else "A"
        return f"[{type_badge}] {self.point_eau.nomabonne} - {self.point_de_controle.nom}"

    @property
    def valeur_min_effective(self):
        """Retourne la valeur min effective (specifique si definie, sinon generique)"""
        return self.valeur_min_specifique if self.valeur_min_specifique is not None else self.point_de_controle.valeur_min

    @property
    def valeur_max_effective(self):
        """Retourne la valeur max effective (specifique si definie, sinon generique)"""
        return self.valeur_max_specifique if self.valeur_max_specifique is not None else self.point_de_controle.valeur_max


class Checklist(models.Model):
    """Template de visite: définit les points à contrôler pour un type d'équipement et de visite."""

    class TypeVisite(models.TextChoices):
        ENTRETIEN = 'ENTRETIEN', 'Entretien'
        CONTROLE_COMPLET = 'COMPLET', 'Contrôle Complet'
        INSPECTION_URGENTE = 'URGENTE', 'Inspection Urgente'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom = models.CharField(max_length=255, help_text="Nom de la checklist")
    equipement_constitutif = models.ForeignKey(EquipementConstitutif, on_delete=models.CASCADE, related_name='checklists')
    type_visite = models.CharField(max_length=20, choices=TypeVisite.choices)
    points_de_controle = models.ManyToManyField(PointDeControle, through='ChecklistPointControle')

    # Fréquence recommandée
    frequence_jours = models.IntegerField(null=True, blank=True, help_text="Fréquence recommandée en jours")

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'checklists'
        verbose_name = 'Checklist'
        verbose_name_plural = 'Checklists'
        unique_together = ['equipement_constitutif', 'type_visite']

    def __str__(self):
        return f"Checklist {self.get_type_visite_display()} pour {self.equipement_constitutif}"


class ChecklistPointControle(models.Model):
    """Table de liaison avec ordre des points de contrôle dans une checklist."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    checklist = models.ForeignKey(Checklist, on_delete=models.CASCADE)
    point_de_controle = models.ForeignKey(PointDeControle, on_delete=models.CASCADE)
    ordre = models.PositiveIntegerField(default=0, help_text="Ordre d'affichage du point de contrôle")
    est_obligatoire = models.BooleanField(default=True, help_text="Ce point de contrôle est-il obligatoire?")
    
    class Meta:
        db_table = 'checklist_points_controle'
        verbose_name = 'Point de Contrôle de Checklist'
        verbose_name_plural = 'Points de Contrôle de Checklists'
        ordering = ['ordre']
        unique_together = ['checklist', 'point_de_controle']

    def __str__(self):
        return f"{self.checklist.nom} - {self.point_de_controle.nom}"


class Visite(models.Model):
    """Enregistrement d'une visite sur le terrain (rapport de visite)."""
    
    STATUS_CHOICES = [
        ('en_cours', 'En cours'),
        ('terminee', 'Terminée'),
        ('abandonnee', 'Abandonnée'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ouvrage = models.ForeignKey(Ouvrage, on_delete=models.PROTECT, related_name='visites', null=True, blank=True)
    agent = models.ForeignKey(Employe, on_delete=models.PROTECT, related_name='visites_effectuees')
    date_visite = models.DateTimeField(default=timezone.now)
    type_visite = models.CharField(max_length=20, choices=Checklist.TypeVisite.choices)
    statut = models.CharField(max_length=20, choices=STATUS_CHOICES, default='en_cours')
    
    commentaires_generaux = models.TextField(blank=True)
    
    # Géolocalisation (optionnel)
    latitude = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True)
    longitude = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True)
    
    # Conditions météorologiques
    conditions_meteo = models.CharField(max_length=100, blank=True, help_text="Conditions météorologiques lors de la visite")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'visites'
        verbose_name = 'Visite'
        verbose_name_plural = 'Visites'
        ordering = ['-date_visite']

    def __str__(self):
        return f"Visite de {self.ouvrage} par {self.agent} le {self.date_visite.date()}"
        
    # Alias pour compatibilité
    @property
    def infrastructure(self):
        return self.ouvrage

    @property
    def duree_visite(self):
        """Calcule la durée de la visite si terminée."""
        if self.statut == 'terminee' and hasattr(self, 'date_fin'):
            return self.date_fin - self.date_visite
        return None

    @property
    def nombre_anomalies(self):
        """Compte le nombre d'anomalies détectées."""
        return self.resultats.filter(
            models.Q(resultat_bool=False) | 
            models.Q(point_de_controle__type_resultat='NUM', resultat_numeric__lt=models.F('point_de_controle__valeur_min')) |
            models.Q(point_de_controle__type_resultat='NUM', resultat_numeric__gt=models.F('point_de_controle__valeur_max'))
        ).count()


class InspectionPhoto(models.Model):
    """Photo collectée durant une visite et pouvant lier plusieurs résultats."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    visite = models.ForeignKey(Visite, on_delete=models.CASCADE, related_name='inspection_photos')
    file_upload = models.ForeignKey(FileUpload, on_delete=models.CASCADE, related_name='inspection_photos')
    equipement = models.ForeignKey(
        EquipementConstitutif,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inspection_photos'
    )
    point_eau = models.ForeignKey(
        'billing.PointEau',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inspection_photos'
    )
    description = models.CharField(max_length=255, blank=True)
    pris_le = models.DateTimeField(default=timezone.now, verbose_name="Date de prise de vue")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'inspection_photos'
        verbose_name = 'Photo d\'inspection'
        verbose_name_plural = 'Photos d\'inspection'
        ordering = ['-pris_le']

    def __str__(self):
        objet = self.equipement or self.point_eau or self.visite.ouvrage
        objet_nom = getattr(objet, 'nom', getattr(objet, 'nomabonne', str(objet)))
        return f"Photo {self.file_upload.filename} ({objet_nom})"


class ResultatControle(models.Model):
    """Donnée brute collectée pour un point de contrôle durant une visite."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    visite = models.ForeignKey(Visite, on_delete=models.CASCADE, related_name="resultats")
    equipement = models.ForeignKey(EquipementConstitutif, on_delete=models.PROTECT)
    point_de_controle = models.ForeignKey(PointDeControle, on_delete=models.PROTECT)
    
    # Résultats selon le type de contrôle
    resultat_bool = models.BooleanField(null=True, blank=True)
    resultat_numeric = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Informations complémentaires
    commentaire = models.TextField(blank=True)
    inspection_photos = models.ManyToManyField(
        InspectionPhoto,
        blank=True,
        related_name='resultats_controle'
    )
    
    # Horodatage du contrôle
    heure_controle = models.DateTimeField(default=timezone.now)
    
    # Indique si ce résultat nécessite une action corrective
    necessite_action = models.BooleanField(default=False)

    # Nouveaux champs pour les actions correctives (quand resultat_bool = False)
    activite_id = models.UUIDField(null=True, blank=True, verbose_name="ID de l'activité corrective")
    date_action = models.DateField(null=True, blank=True, verbose_name="Date prévue de l'action corrective")
    remarque_action = models.TextField(blank=True, verbose_name="Remarque sur l'action corrective")

    # Champs de vérification GPS lors de l'inspection
    gps_verifie = models.BooleanField(default=False, verbose_name="GPS vérifié", help_text="Indique si la position GPS a été vérifiée lors de l'inspection")
    gps_latitude_inspecteur = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True, verbose_name="Latitude inspecteur", help_text="Latitude GPS de l'inspecteur au moment du contrôle")
    gps_longitude_inspecteur = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True, verbose_name="Longitude inspecteur", help_text="Longitude GPS de l'inspecteur au moment du contrôle")
    gps_precision = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, verbose_name="Précision GPS (m)", help_text="Précision de la mesure GPS en mètres")
    gps_distance_equipement = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name="Distance à l'équipement (m)", help_text="Distance calculée entre l'inspecteur et l'équipement en mètres")
    gps_proximite_ok = models.BooleanField(default=False, verbose_name="Proximité validée", help_text="Indique si l'inspecteur était à proximité de l'équipement (< 50m)")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'resultats_controle'
        verbose_name = 'Résultat de Contrôle'
        verbose_name_plural = 'Résultats de Contrôle'
        unique_together = ['visite', 'equipement', 'point_de_controle']
        ordering = ['heure_controle']

    def __str__(self):
        return f"{self.point_de_controle.nom} - {self.equipement.nom} ({self.visite.date_visite.date()})"

    def clean(self):
        """Validation des données selon le type de résultat attendu."""
        from django.core.exceptions import ValidationError
        
        if self.point_de_controle.type_resultat == 'BOOL':
            if self.resultat_bool is None:
                raise ValidationError("Résultat booléen requis pour ce point de contrôle")
            self.resultat_numeric = None
        elif self.point_de_controle.type_resultat == 'NUM':
            if self.resultat_numeric is None:
                raise ValidationError("Résultat numérique requis pour ce point de contrôle")
            self.resultat_bool = None

    def save(self, *args, **kwargs):
        self.clean()
        
        # Vérifier automatiquement si une action est nécessaire
        if self.point_de_controle.type_resultat == 'BOOL' and self.resultat_bool is False:
            self.necessite_action = True
        elif self.point_de_controle.type_resultat == 'NUM' and self.resultat_numeric is not None:
            if (self.point_de_controle.valeur_min and self.resultat_numeric < self.point_de_controle.valeur_min) or \
               (self.point_de_controle.valeur_max and self.resultat_numeric > self.point_de_controle.valeur_max):
                self.necessite_action = True
                
        super().save(*args, **kwargs)

    @property
    def resultat_display(self):
        """Affiche le résultat de manière lisible."""
        if self.point_de_controle.type_resultat == 'BOOL':
            return "✓ Bon" if self.resultat_bool else "✗ Pas Bon"
        elif self.point_de_controle.type_resultat == 'NUM':
            unite = self.point_de_controle.unite or ""
            return f"{self.resultat_numeric} {unite}".strip()
        return "Non renseigné"

    @property
    def est_conforme(self):
        """Indique si le résultat est conforme aux attentes."""
        if self.point_de_controle.type_resultat == 'BOOL':
            return self.resultat_bool is True
        elif self.point_de_controle.type_resultat == 'NUM' and self.resultat_numeric is not None:
            conforme = True
            if self.point_de_controle.valeur_min and self.resultat_numeric < self.point_de_controle.valeur_min:
                conforme = False
            if self.point_de_controle.valeur_max and self.resultat_numeric > self.point_de_controle.valeur_max:
                conforme = False
            return conforme
        return None


class PointControleActiviteCorrectible(models.Model):
    """Table de liaison pour définir quelles activités correctives sont possibles pour chaque point de contrôle."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    point_de_controle = models.ForeignKey(PointDeControle, on_delete=models.CASCADE, related_name='activites_correctives_possibles')
    activite_id = models.UUIDField(verbose_name="ID de l'activité corrective")

    # Optionnel : priorité ou ordre de préférence
    priorite = models.PositiveIntegerField(default=1, help_text="Ordre de priorité (1 = plus prioritaire)")

    # Optionnel : condition d'application
    condition_application = models.TextField(blank=True, help_text="Condition spécifique pour appliquer cette activité corrective")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'point_controle_activites_correctives'
        verbose_name = 'Activité Corrective Possible'
        verbose_name_plural = 'Activités Correctives Possibles'
        unique_together = ['point_de_controle', 'activite_id']
        ordering = ['priorite', 'activite_id']

    def __str__(self):
        return f"{self.point_de_controle.nom} → Activité {self.activite_id}"

    @property
    def activite(self):
        """Récupère l'activité via son UUID depuis l'app planning."""
        from apps.planning.models import Activite
        try:
            return Activite.objects.get(id=self.activite_id)
        except Activite.DoesNotExist:
            return None


class ResultatControlePointEau(models.Model):
    """Résultat de contrôle spécifique aux points d'eau durant une visite."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    visite = models.ForeignKey(Visite, on_delete=models.CASCADE, related_name="resultats_points_eau")
    point_eau = models.ForeignKey('billing.PointEau', on_delete=models.PROTECT)
    point_de_controle = models.ForeignKey(PointDeControle, on_delete=models.PROTECT)

    # Résultats selon le type de contrôle
    resultat_bool = models.BooleanField(null=True, blank=True)
    resultat_numeric = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    resultat_text = models.TextField(blank=True, help_text="Résultat sous forme de texte libre")

    # Informations complémentaires
    commentaire = models.TextField(blank=True)
    inspection_photos = models.ManyToManyField(
        InspectionPhoto,
        blank=True,
        related_name='resultats_points_eau'
    )

    # Horodatage du contrôle
    heure_controle = models.DateTimeField(default=timezone.now)

    # Indique si ce résultat nécessite une action corrective
    necessite_action = models.BooleanField(default=False)

    # Actions correctives (quand resultat_bool = False)
    activite_id = models.UUIDField(null=True, blank=True, verbose_name="ID de l'activité corrective")
    date_action = models.DateField(null=True, blank=True, verbose_name="Date prévue de l'action corrective")
    remarque_action = models.TextField(blank=True, verbose_name="Remarque sur l'action corrective")

    # Champs de vérification GPS lors de l'inspection
    gps_verifie = models.BooleanField(default=False, verbose_name="GPS vérifié", help_text="Indique si la position GPS a été vérifiée lors de l'inspection")
    gps_latitude_inspecteur = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True, verbose_name="Latitude inspecteur", help_text="Latitude GPS de l'inspecteur au moment du contrôle")
    gps_longitude_inspecteur = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True, verbose_name="Longitude inspecteur", help_text="Longitude GPS de l'inspecteur au moment du contrôle")
    gps_precision = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, verbose_name="Précision GPS (m)", help_text="Précision de la mesure GPS en mètres")
    gps_distance_point_eau = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name="Distance au point d'eau (m)", help_text="Distance calculée entre l'inspecteur et le point d'eau en mètres")
    gps_proximite_ok = models.BooleanField(default=False, verbose_name="Proximité validée", help_text="Indique si l'inspecteur était à proximité du point d'eau (< 50m)")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'resultats_controle_points_eau'
        verbose_name = 'Résultat de Contrôle Point d\'Eau'
        verbose_name_plural = 'Résultats de Contrôle Points d\'Eau'
        unique_together = ['visite', 'point_eau', 'point_de_controle']
        ordering = ['heure_controle']

    def __str__(self):
        return f"{self.point_de_controle.nom} - {self.point_eau.nomabonne} ({self.visite.date_visite.date()})"

    def clean(self):
        """Validation des données selon le type de résultat attendu."""
        from django.core.exceptions import ValidationError

        if self.point_de_controle.type_resultat == 'BOOL':
            if self.resultat_bool is None:
                raise ValidationError("Résultat booléen requis pour ce point de contrôle")
            self.resultat_numeric = None
            self.resultat_text = ''
        elif self.point_de_controle.type_resultat == 'NUM':
            if self.resultat_numeric is None:
                raise ValidationError("Résultat numérique requis pour ce point de contrôle")
            self.resultat_bool = None
            self.resultat_text = ''
        elif self.point_de_controle.type_resultat == 'TEXT':
            if not self.resultat_text:
                raise ValidationError("Résultat texte requis pour ce point de contrôle")
            self.resultat_bool = None
            self.resultat_numeric = None

    def save(self, *args, **kwargs):
        self.clean()

        # Vérifier automatiquement si une action est nécessaire
        if self.point_de_controle.type_resultat == 'BOOL' and self.resultat_bool is False:
            self.necessite_action = True
        elif self.point_de_controle.type_resultat == 'NUM' and self.resultat_numeric is not None:
            if (self.point_de_controle.valeur_min and self.resultat_numeric < self.point_de_controle.valeur_min) or \
               (self.point_de_controle.valeur_max and self.resultat_numeric > self.point_de_controle.valeur_max):
                self.necessite_action = True

        super().save(*args, **kwargs)

    @property
    def resultat_display(self):
        """Affiche le résultat de manière lisible."""
        if self.point_de_controle.type_resultat == 'BOOL':
            return "✓ Bon" if self.resultat_bool else "✗ Pas Bon"
        elif self.point_de_controle.type_resultat == 'NUM':
            unite = self.point_de_controle.unite or ""
            return f"{self.resultat_numeric} {unite}".strip()
        elif self.point_de_controle.type_resultat == 'TEXT':
            return self.resultat_text or "Non renseigné"
        return "Non renseigné"

    @property
    def est_conforme(self):
        """Indique si le résultat est conforme aux attentes."""
        if self.point_de_controle.type_resultat == 'BOOL':
            return self.resultat_bool is True
        elif self.point_de_controle.type_resultat == 'NUM' and self.resultat_numeric is not None:
            conforme = True
            if self.point_de_controle.valeur_min and self.resultat_numeric < self.point_de_controle.valeur_min:
                conforme = False
            if self.point_de_controle.valeur_max and self.resultat_numeric > self.point_de_controle.valeur_max:
                conforme = False
            return conforme
        elif self.point_de_controle.type_resultat == 'TEXT':
            # Pour les résultats texte, considérer comme conforme si rempli
            return bool(self.resultat_text.strip()) if self.resultat_text else False
        return None


# ============================================
# NOUVEAUX MODÈLES POUR INSPECTIONS PAR COMPOSANTS
# ============================================

class Inspection(models.Model):
    """Session d'inspection globale d'un équipement ou point d'eau"""

    STATUS_CHOICES = [
        ('en_cours', 'En cours'),
        ('terminee', 'Terminée'),
        ('validee', 'Validée'),
        ('suspendue', 'Suspendue'),
    ]

    TYPE_INSPECTION_CHOICES = [
        ('normale', 'Inspection Normale'),
        ('express', 'Inspection Express'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    numero_inspection = models.CharField(max_length=50, unique=True, verbose_name="Numéro d'inspection")
    type_inspection = models.CharField(
        max_length=20,
        choices=TYPE_INSPECTION_CHOICES,
        default='normale',
        verbose_name="Type d'inspection",
        help_text="Normale (tous les points) ou Express (points spécifiques)"
    )

    # Objet inspecté (UN SEUL des deux)
    equipement = models.ForeignKey(EquipementConstitutif, on_delete=models.CASCADE, null=True, blank=True, related_name='inspections')
    point_eau = models.ForeignKey('billing.PointEau', on_delete=models.CASCADE, null=True, blank=True, related_name='inspections')

    # Métadonnées de l'inspection
    date_inspection = models.DateTimeField(verbose_name="Date et heure d'inspection")
    inspecteur = models.ForeignKey(User, on_delete=models.CASCADE, related_name='inspections_effectuees')
    statut = models.CharField(max_length=20, choices=STATUS_CHOICES, default='en_cours')

    # Conditions générales
    conditions_meteo = models.CharField(max_length=100, blank=True, verbose_name="Conditions météorologiques")
    temperature = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Température (°C)")
    observations_generales = models.TextField(blank=True, verbose_name="Observations générales")

    # Résultats globaux (calculés automatiquement)
    conforme_global = models.BooleanField(null=True, verbose_name="Conformité globale")
    score_global = models.IntegerField(null=True, verbose_name="Score de conformité (%)")

    # Suivi
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'inspections'
        verbose_name = 'Inspection'
        verbose_name_plural = 'Inspections'
        ordering = ['-date_inspection']

    def clean(self):
        """Validation : un seul objet inspecté doit être défini"""
        from django.core.exceptions import ValidationError
        if not self.equipement and not self.point_eau:
            raise ValidationError("Un équipement ou un point d'eau doit être spécifié")
        if self.equipement and self.point_eau:
            raise ValidationError("Un seul objet peut être inspecté à la fois")

    def save(self, *args, **kwargs):
        # Générer automatiquement le numéro d'inspection
        if not self.numero_inspection:
            from datetime import datetime
            prefix = "INS"
            year = self.date_inspection.year if self.date_inspection else datetime.now().year
            count = Inspection.objects.filter(date_inspection__year=year).count() + 1
            self.numero_inspection = f"{prefix}-{year}-{count:04d}"
        super().save(*args, **kwargs)

    def __str__(self):
        objet = self.equipement or self.point_eau
        return f"Inspection {self.numero_inspection} - {objet}"

    @property
    def objet_inspecte(self):
        """Retourne l'objet inspecté (équipement ou point d'eau)"""
        return self.equipement or self.point_eau

    def calculer_conformite(self):
        """Calcule la conformité globale basée sur les résultats des composants"""
        resultats = self.resultats.all()
        if not resultats.exists():
            return None, None

        total = resultats.count()
        conformes = resultats.filter(conforme=True).count()

        score = int((conformes / total) * 100) if total > 0 else 0
        conforme = score >= 80  # Seuil de conformité à 80%

        # Mettre à jour les champs
        self.score_global = score
        self.conforme_global = conforme
        self.save(update_fields=['score_global', 'conforme_global'])

        return conforme, score


class ResultatInspectionComposant(models.Model):
    """Résultats détaillés d'inspection par composant et point de contrôle"""

    NIVEAU_GRAVITE_CHOICES = [
        ('info', 'Information'),
        ('mineur', 'Problème mineur'),
        ('majeur', 'Problème majeur'),
        ('critique', 'Problème critique'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Lien vers l'inspection principale
    inspection = models.ForeignKey(Inspection, on_delete=models.CASCADE, related_name='resultats')

    # Composant inspecté (UN SEUL des deux)
    composant_equipement = models.ForeignKey(ComposantTypeEquipement, on_delete=models.CASCADE, null=True, blank=True)
    composant_point_eau = models.ForeignKey(ComposantTypePointEau, on_delete=models.CASCADE, null=True, blank=True)

    # Point de contrôle spécifique
    point_de_controle = models.ForeignKey(PointDeControle, on_delete=models.CASCADE)

    # Résultats de mesure
    valeur_mesuree = models.CharField(max_length=255, blank=True, verbose_name="Valeur mesurée")
    valeur_numerique = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True, verbose_name="Valeur numérique")
    unite = models.CharField(max_length=20, blank=True, verbose_name="Unité")

    # Évaluation
    conforme = models.BooleanField(null=True, verbose_name="Conforme")
    niveau_gravite = models.CharField(max_length=20, choices=NIVEAU_GRAVITE_CHOICES, blank=True, verbose_name="Niveau de gravité")

    # Contexte
    methode_mesure = models.CharField(max_length=100, blank=True, verbose_name="Méthode de mesure")
    equipement_mesure = models.CharField(max_length=100, blank=True, verbose_name="Équipement de mesure")
    conditions_mesure = models.TextField(blank=True, verbose_name="Conditions de mesure")

    # Observations
    observations = models.TextField(blank=True, verbose_name="Observations")
    photos = models.JSONField(default=list, blank=True, verbose_name="Photos (URLs)")

    # Suivi
    date_mesure = models.DateTimeField(verbose_name="Date et heure de mesure")
    operateur = models.ForeignKey(User, on_delete=models.CASCADE, related_name='mesures_effectuees')

    class Meta:
        db_table = 'resultats_inspections_composants'
        verbose_name = 'Résultat d\'Inspection de Composant'
        verbose_name_plural = 'Résultats d\'Inspections de Composants'
        unique_together = ['inspection', 'composant_equipement', 'composant_point_eau', 'point_de_controle']
        ordering = ['composant_equipement__ordre_affichage', 'composant_point_eau__ordre_affichage', 'point_de_controle__nom']

    def clean(self):
        """Validation : un seul type de composant doit être défini"""
        from django.core.exceptions import ValidationError
        if not self.composant_equipement and not self.composant_point_eau:
            raise ValidationError("Un composant d'équipement ou de point d'eau doit être spécifié")
        if self.composant_equipement and self.composant_point_eau:
            raise ValidationError("Un seul type de composant peut être spécifié")

    def save(self, *args, **kwargs):
        # Évaluer automatiquement la conformité selon le type de point de contrôle
        if self.point_de_controle.type_resultat == 'BOOL':
            # Pour les booléens, conforme = True si valeur_mesuree contient "oui", "true", "bon", etc.
            if self.valeur_mesuree:
                valeur_lower = self.valeur_mesuree.lower()
                self.conforme = any(word in valeur_lower for word in ['oui', 'true', 'bon', 'ok', 'conforme', '✓'])

        elif self.point_de_controle.type_resultat == 'NUM' and self.valeur_numerique is not None:
            # Pour les numériques, vérifier les bornes min/max
            conforme = True
            if self.point_de_controle.valeur_min and self.valeur_numerique < self.point_de_controle.valeur_min:
                conforme = False
            if self.point_de_controle.valeur_max and self.valeur_numerique > self.point_de_controle.valeur_max:
                conforme = False
            self.conforme = conforme

        super().save(*args, **kwargs)

        # Recalculer la conformité globale de l'inspection
        self.inspection.calculer_conformite()

    def __str__(self):
        composant = self.composant_equipement or self.composant_point_eau
        return f"{composant} - {self.point_de_controle.nom}"

    @property
    def composant(self):
        """Retourne le composant (équipement ou point d'eau)"""
        return self.composant_equipement or self.composant_point_eau


class ActionCorrective(models.Model):
    """Actions correctives à prendre suite aux non-conformités"""

    PRIORITE_CHOICES = [
        ('basse', 'Basse'),
        ('normale', 'Normale'),
        ('haute', 'Haute'),
        ('urgente', 'Urgente'),
    ]

    STATUS_CHOICES = [
        ('planifiee', 'Planifiée'),
        ('en_cours', 'En cours'),
        ('terminee', 'Terminée'),
        ('reportee', 'Reportée'),
        ('annulee', 'Annulée'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    resultat_inspection = models.ForeignKey(ResultatInspectionComposant, on_delete=models.CASCADE, related_name='actions_correctives')

    # Description de l'action
    titre = models.CharField(max_length=200, verbose_name="Titre de l'action")
    description = models.TextField(verbose_name="Description détaillée")
    priorite = models.CharField(max_length=20, choices=PRIORITE_CHOICES, default='normale', verbose_name="Priorité")

    # Planification
    date_prevue = models.DateField(verbose_name="Date prévue")
    responsable = models.ForeignKey(User, on_delete=models.CASCADE, related_name='actions_responsables')
    cout_estime = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Coût estimé")

    # Suivi
    statut = models.CharField(max_length=20, choices=STATUS_CHOICES, default='planifiee', verbose_name="Statut")
    date_realisation = models.DateField(null=True, blank=True, verbose_name="Date de réalisation")
    cout_reel = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Coût réel")
    commentaires = models.TextField(blank=True, verbose_name="Commentaires")

    # Lien vers le planning généré (si synchronisé)
    planning_genere = models.ForeignKey('planning.Planning', on_delete=models.SET_NULL, null=True, blank=True, related_name='actions_correctives_liees', verbose_name="Planning généré")
    activite = models.ForeignKey('planning.Activite', on_delete=models.SET_NULL, null=True, blank=True, related_name='actions_correctives_liees', verbose_name="Activité liée")

    # Suivi
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'actions_correctives'
        verbose_name = 'Action Corrective'
        verbose_name_plural = 'Actions Correctives'
        ordering = ['priorite', 'date_prevue']

    def __str__(self):
        return f"{self.titre} ({self.get_priorite_display()})"

    @property
    def est_en_retard(self):
        """Indique si l'action est en retard"""
        from datetime import date
        return (self.statut in ['planifiee', 'en_cours'] and
                self.date_prevue < date.today())

    def creer_planning_automatique(self):
        """Crée automatiquement une entrée dans le planning pour cette action corrective"""
        from apps.planning.models import Planning, Activite
        from apps.employees.models import Employe
        from datetime import datetime

        # Ne créer un planning que si on a une activité définie
        if not self.activite:
            return None

        # Ne pas créer de doublon si le planning existe déjà
        if self.planning_genere:
            return self.planning_genere

        # Récupérer l'ouvrage depuis l'inspection
        inspection = self.resultat_inspection.inspection
        ouvrage = None

        if inspection.equipement:
            # Récupérer l'ouvrage depuis l'équipement constitutif
            ouvrage = inspection.equipement.ouvrage
        elif inspection.point_eau:
            # Pour un point d'eau, récupérer l'ouvrage lié si existant
            if hasattr(inspection.point_eau, 'ouvrage'):
                ouvrage = inspection.point_eau.ouvrage

        # Récupérer l'employé depuis le responsable (User → Employe)
        try:
            employe = Employe.objects.get(user=self.responsable)
        except Employe.DoesNotExist:
            # Si le responsable n'est pas lié à un employé, on ne peut pas créer le planning
            return None

        # Créer l'entrée de planning
        planning = Planning.objects.create(
            date=datetime.combine(self.date_prevue, datetime.min.time()),
            activite=self.activite,
            type_activite=self.activite.type_activite if self.activite.type_activite else None,
            employe=employe,
            ouvrage=ouvrage,
            remarque=f"Action corrective suite à inspection du {inspection.date_inspection.strftime('%d/%m/%Y')}\n{self.description}",
            statut='en_cours',
            createdat=datetime.now(),
            updatedat=datetime.now(),
        )

        # Lier le planning à cette action corrective
        self.planning_genere = planning
        self.save(update_fields=['planning_genere'])

        return planning


class NonConformite(models.Model):
    """Détails complets d'une non-conformité avec narratif, solution et planification"""

    PRIORITE_CHOICES = [
        ('basse', 'Basse - Pas de gêne particulière'),
        ('moyenne', 'Moyenne - Gênante pour le fonctionnement'),
        ('haute', 'Haute - Occasionne des pannes'),
    ]

    NIVEAU_SOLUTION_CHOICES = [
        ('mpikojakoja', 'Niveau Mpikojakoja ifotony'),
        ('st', 'Niveau ST (Superviseur Technique)'),
        ('social', 'Niveau Social'),
        ('projet', 'Niveau Projet'),
    ]

    ECHEANCE_CHOICES = [
        ('immediat', 'Immédiatement - Outils disponibles'),
        ('3_mois', 'Dans 3 mois - Commande de matériaux nécessaire'),
        ('6_mois', 'Dans 6 mois - Planification avec autres employés'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Lien vers le résultat d'inspection non conforme
    resultat_inspection = models.OneToOneField(
        ResultatInspectionComposant,
        on_delete=models.CASCADE,
        related_name='non_conformite'
    )

    # NARRATIF DU PROBLÈME
    narratif_probleme = models.TextField(
        verbose_name="Narratif du problème",
        help_text="Description détaillée du problème avec mesures précises (ex: clôture défectueuse - 3 piquets cassés de 1.2m, grillage déchiré sur 50cm)"
    )

    # SOLUTION PROPOSÉE
    solution_detaillee = models.TextField(
        verbose_name="Solution détaillée",
        help_text="Description explicite de la solution avec quantités exactes (ex: Remplacer 3 piquets en bois de 1.2m, réparer 50cm de grillage avec 2m de fil de fer)"
    )

    # Matériaux/désignations nécessaires (JSON)
    materiaux_necessaires = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Matériaux nécessaires",
        help_text="Liste des désignations avec quantités: [{'designation': 'Petit bois 1.2m', 'quantite': 3, 'unite': 'pièces'}, ...]"
    )

    # PLANIFICATION
    besoin_superviseur = models.BooleanField(
        default=False,
        verbose_name="Besoin d'un superviseur technique"
    )

    niveau_solution = models.CharField(
        max_length=20,
        choices=NIVEAU_SOLUTION_CHOICES,
        verbose_name="Niveau de la solution"
    )

    priorite = models.CharField(
        max_length=20,
        choices=PRIORITE_CHOICES,
        verbose_name="Priorité"
    )

    echeance = models.CharField(
        max_length=20,
        choices=ECHEANCE_CHOICES,
        verbose_name="Échéance de réalisation"
    )

    # MÉTADONNÉES
    cout_estime = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Coût estimé (Ar)"
    )

    photos = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Photos du problème (URLs)"
    )

    # SUIVI
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    creee_par = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='non_conformites_creees'
    )

    class Meta:
        db_table = 'non_conformites'
        verbose_name = 'Non-Conformité'
        verbose_name_plural = 'Non-Conformités'
        ordering = ['-date_creation']

    def __str__(self):
        return f"NC-{self.resultat_inspection.point_de_controle.nom} ({self.get_priorite_display()})"

    @property
    def delai_jours(self):
        """Retourne le délai en jours selon l'échéance"""
        mapping = {
            'immediat': 0,
            '3_mois': 90,
            '6_mois': 180,
        }
        return mapping.get(self.echeance, 90)

    def generer_action_corrective(self):
        """Génère automatiquement une ActionCorrective basée sur cette non-conformité"""
        from datetime import date, timedelta

        # Éviter les doublons
        if hasattr(self.resultat_inspection, 'actions_correctives') and self.resultat_inspection.actions_correctives.exists():
            return self.resultat_inspection.actions_correctives.first()

        # Mapper la priorité
        priorite_mapping = {
            'basse': 'basse',
            'moyenne': 'normale',
            'haute': 'urgente',
        }

        # Calculer la date prévue
        date_prevue = date.today() + timedelta(days=self.delai_jours)

        # Créer l'action corrective
        action = ActionCorrective.objects.create(
            resultat_inspection=self.resultat_inspection,
            titre=f"Correction: {self.resultat_inspection.point_de_controle.nom}",
            description=f"{self.narratif_probleme}\n\nSOLUTION:\n{self.solution_detaillee}",
            priorite=priorite_mapping.get(self.priorite, 'normale'),
            date_prevue=date_prevue,
            responsable=self.creee_par,
            cout_estime=self.cout_estime,
        )

        return action
