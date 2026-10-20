from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, StepValueValidator
from django.db import models
from django.contrib.auth.models import User
from apps.organization.models import Base, Organisation, Ouvrage as OrgOuvrage
from apps.employees.models import Employe
from decimal import Decimal
import uuid


class TypeOuvrage(models.Model):
    """Modèle pour les types d'ouvrages existants dans Supabase"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nomtype = models.CharField(max_length=255, verbose_name="Nom du type")
    createdat = models.DateTimeField(auto_now_add=True)
    updatedat = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'typesouvrages'
        verbose_name = 'Type d\'ouvrage'
        verbose_name_plural = 'Types d\'ouvrages'

    def __str__(self):
        return self.nomtype


class TypeEquipement(models.Model):
    """Modèle pour les types d'équipements"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom_type = models.CharField(max_length=255, verbose_name="Nom du type d'équipement", unique=True)
    description = models.TextField(null=True, blank=True, verbose_name="Description")
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'types_equipements'
        verbose_name = 'Type d\'équipement'
        verbose_name_plural = 'Types d\'équipements'
        ordering = ['nom_type']

    def __str__(self):
        return self.nom_type


# Modèle Ouvrage supprimé - utiliser organization.Ouvrage à la place
# La table ouvrages_infrastructure est obsolète


class MaintenanceTask(models.Model):
    TASK_TYPE_CHOICES = [
        ('preventive', 'Préventive'),
        ('corrective', 'Corrective'),
        ('urgente', 'Urgente'),
        ('inspection', 'Inspection'),
    ]
    
    STATUS_CHOICES = [
        ('planifiee', 'Planifiée'),
        ('en_cours', 'En cours'),
        ('terminee', 'Terminée'),
        ('reportee', 'Reportée'),
        ('annulee', 'Annulée'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task_title = models.CharField(max_length=255)
    task_description = models.TextField(null=True, blank=True)
    task_type = models.CharField(max_length=50, choices=TASK_TYPE_CHOICES)
    scheduled_date = models.DateField()
    completed_date = models.DateField(null=True, blank=True)
    estimated_duration = models.DurationField(null=True, blank=True)
    actual_duration = models.DurationField(null=True, blank=True)
    task_status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='planifiee')
    priority_level = models.IntegerField(default=1)
    cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    
    ouvrage = models.ForeignKey('organization.Ouvrage', on_delete=models.CASCADE, related_name='maintenance_tasks')
    assigned_employee = models.ForeignKey(Employe, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_maintenance_tasks')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'maintenance_tasks'
        verbose_name = 'Tâche de maintenance'
        verbose_name_plural = 'Tâches de maintenance'

    def __str__(self):
        return f"{self.task_title} - {self.ouvrage.nom_ouvrage}"


class EquipementConstitutif(models.Model):
    """
    Modèle représentant les équipements constitutifs d'une infrastructure
    (pompes, vannes, compteurs, etc.)
    """
    # Types d'équipements maintenant gérés par le modèle TypeEquipement
    
    STATUS_CHOICES = [
        ('operationnel', 'Opérationnel'),
        ('en_panne', 'En panne'),
        ('en_maintenance', 'En maintenance'),
        ('hors_service', 'Hors service'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom = models.CharField(max_length=255, help_text="Nom de l'équipement")
    description = models.TextField(null=True, blank=True)
    type_equipement = models.ForeignKey(TypeEquipement, on_delete=models.PROTECT, related_name='equipements', verbose_name="Type d'équipement", null=True, blank=True)
    volume_m3 = models.DecimalField(
        max_digits=12,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0')), StepValueValidator(Decimal('0.5'))],
        verbose_name="Volume (m³)",
        help_text="Capacité en mètres cubes pour les équipements de type citerne",
    )
    code_equipement = models.CharField(max_length=100, unique=True, null=True, blank=True, help_text="Code unique de l'équipement")
    
    # Relation avec l'ouvrage parent (utilise organization.Ouvrage, la vraie table avec 1233 ouvrages)
    # Nullable temporairement pour permettre la migration depuis infrastructure.Ouvrage
    ouvrage = models.ForeignKey(OrgOuvrage, on_delete=models.CASCADE, related_name='equipements_constitutifs', db_column='ouvrage_id', null=True, blank=True)
    
    # Photo de référence pour les inspections
    photo_reference = models.ForeignKey(
        'filemanager.FileUpload',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='equipements_reference',
        help_text="Photo de l'équipement en parfait état de fonctionnement"
    )
    
    # Statut et dates
    statut = models.CharField(max_length=50, choices=STATUS_CHOICES, default='operationnel')
    date_installation = models.DateField(null=True, blank=True)
    derniere_maintenance = models.DateField(null=True, blank=True)
    prochaine_maintenance = models.DateField(null=True, blank=True)
    
    # Responsable
    responsable = models.ForeignKey(Employe, on_delete=models.SET_NULL, null=True, blank=True, related_name='equipements_responsables')
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='equipements_modifies',
        verbose_name="Mis ? jour par"
    )

    # Géolocalisation pour vérification de présence sur site lors des inspections
    latitude = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True, help_text="Latitude GPS de l'équipement")
    longitude = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True, help_text="Longitude GPS de l'équipement")

    # Nouveaux champs de maintenance et caractéristiques
    nombre_nettoyages_annuels = models.IntegerField(null=True, blank=True, verbose_name="Nombre de nettoyages annuels", help_text="Fréquence de nettoyage par an")
    temps_acces_heures = models.FloatField(null=True, blank=True, verbose_name="Temps d'accès (heures)", help_text="Temps nécessaire pour accéder à l'équipement")
    particularite_equipement = models.TextField(null=True, blank=True, verbose_name="Particularité de l'équipement", help_text="Éléments particuliers à connaître sur cet équipement")
    point_depart = models.CharField(max_length=255, null=True, blank=True, verbose_name="Point de départ", help_text="Point de départ pour accéder à l'équipement")
    longueur_perimetre = models.IntegerField(null=True, blank=True, verbose_name="Longueur périmètre (m)", help_text="Longueur du périmètre en mètres")
    haie_vive_cultivable = models.BooleanField(default=False, verbose_name="Haie vive cultivable", help_text="Présence d'une haie vive cultivable")
    boite_a_vanne = models.BooleanField(default=False, verbose_name="Boîte à vanne", help_text="Présence d'une boîte à vanne")
    boite_a_vanne_utile = models.BooleanField(default=False, verbose_name="Boîte à vanne utile", help_text="La boîte à vanne est-elle utile/fonctionnelle")
    vanne_flotteur = models.BooleanField(default=False, verbose_name="Vanne flotteur", help_text="Présence d'une vanne flotteur")
    duree_nettoyage = models.FloatField(null=True, blank=True, verbose_name="Durée nettoyage (heures)", help_text="Durée moyenne d'un nettoyage en heures")
    est_dans_village = models.BooleanField(default=False, verbose_name="Est dans le village", help_text="Indique si l'équipement est situé dans le village")

    # Photos de l'équipement (stockées en JSON avec métadonnées)
    photos = models.JSONField(null=True, blank=True, verbose_name="Photos", help_text="Liste des photos de l'équipement avec leurs métadonnées")

    DISTANCE_MATERIAUX_CHOICES = [
        ('proche', 'Proche'),
        ('moyen', 'Moyen'),
        ('eloigne', 'Éloigné'),
    ]
    distance_materiaux_locaux = models.CharField(
        max_length=20,
        choices=DISTANCE_MATERIAUX_CHOICES,
        null=True,
        blank=True,
        verbose_name="Distance matériaux locaux",
        help_text="Distance pour obtenir les matériaux locaux"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'equipements_constitutifs'
        verbose_name = 'Équipement Constitutif'
        verbose_name_plural = 'Équipements Constitutifs'

    def __str__(self):
        if self.ouvrage:
            return f"{self.nom} ({self.ouvrage.nom_ouvrage})"
        return self.nom
        
    # Alias pour compatibilité
    @property
    def infrastructure(self):
        return self.ouvrage


class LiaisonHydraulique(models.Model):
    """
    Graphe dirige amont -> aval entre equipements, compteurs de tete et points d'eau.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ouvrage = models.ForeignKey(
        OrgOuvrage,
        on_delete=models.CASCADE,
        related_name='liaisons_hydrauliques',
        verbose_name="Ouvrage",
    )

    amont_equipement = models.ForeignKey(
        'infrastructure.EquipementConstitutif',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='liaisons_sortantes',
        verbose_name="Equipement amont",
    )
    amont_compteur_tete = models.ForeignKey(
        'billing.CompteurTete',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='liaisons_sortantes',
        verbose_name="Compteur amont",
    )
    amont_point_eau = models.ForeignKey(
        'billing.PointEau',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='liaisons_sortantes',
        verbose_name="Point d'eau amont",
    )

    aval_equipement = models.ForeignKey(
        'infrastructure.EquipementConstitutif',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='liaisons_entrantes',
        verbose_name="Equipement aval",
    )
    aval_compteur_tete = models.ForeignKey(
        'billing.CompteurTete',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='liaisons_entrantes',
        verbose_name="Compteur aval",
    )
    aval_point_eau = models.ForeignKey(
        'billing.PointEau',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='liaisons_entrantes',
        verbose_name="Point d'eau aval",
    )

    ordre = models.PositiveIntegerField(default=0, verbose_name="Ordre")
    actif = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'liaisons_hydrauliques'
        verbose_name = 'Liaison hydraulique'
        verbose_name_plural = 'Liaisons hydrauliques'
        ordering = ['ouvrage__nom_ouvrage', 'ordre', 'created_at']

    @staticmethod
    def _effective_ouvrage_id_for_ouvrage(ouvrage):
        if not ouvrage:
            return None

        source_effective = getattr(ouvrage, 'ouvrage_source_effectif', None)
        if source_effective and getattr(source_effective, 'id', None):
            return source_effective.id
        return getattr(ouvrage, 'id', None)

    @classmethod
    def _effective_ouvrage_id_for_node(cls, node):
        ouvrage = getattr(node, 'ouvrage', None)
        return cls._effective_ouvrage_id_for_ouvrage(ouvrage)

    def get_amont_node(self):
        return self.amont_equipement or self.amont_compteur_tete or self.amont_point_eau

    def get_aval_node(self):
        return self.aval_equipement or self.aval_compteur_tete or self.aval_point_eau

    def get_amont_type(self):
        if self.amont_equipement_id:
            return 'equipement'
        if self.amont_compteur_tete_id:
            return 'compteur'
        if self.amont_point_eau_id:
            return 'point_eau'
        return None

    def get_aval_type(self):
        if self.aval_equipement_id:
            return 'equipement'
        if self.aval_compteur_tete_id:
            return 'compteur'
        if self.aval_point_eau_id:
            return 'point_eau'
        return None

    @staticmethod
    def _node_token(node_type, node):
        if not node_type or node is None or not getattr(node, 'pk', None):
            return None
        return f"{node_type}:{node.pk}"

    def _would_create_cycle(self, amont_type, amont_node, aval_type, aval_node):
        source_token = self._node_token(amont_type, amont_node)
        target_token = self._node_token(aval_type, aval_node)
        if not source_token or not target_token or not self.ouvrage_id:
            return False

        adjacency = {}
        existing_liaisons = LiaisonHydraulique.objects.filter(
            ouvrage_id=self.ouvrage_id,
            actif=True,
        ).exclude(pk=self.pk)

        for liaison in existing_liaisons:
            existing_source = self._node_token(liaison.get_amont_type(), liaison.get_amont_node())
            existing_target = self._node_token(liaison.get_aval_type(), liaison.get_aval_node())
            if not existing_source or not existing_target:
                continue
            adjacency.setdefault(existing_source, set()).add(existing_target)

        adjacency.setdefault(source_token, set()).add(target_token)

        visited = set()
        stack = [target_token]

        while stack:
            current = stack.pop()
            if current == source_token:
                return True
            if current in visited:
                continue
            visited.add(current)
            stack.extend(adjacency.get(current, ()))

        return False

    def clean(self):
        super().clean()

        amont_count = sum(
            bool(node_id) for node_id in (
                self.amont_equipement_id,
                self.amont_compteur_tete_id,
                self.amont_point_eau_id,
            )
        )
        aval_count = sum(
            bool(node_id) for node_id in (
                self.aval_equipement_id,
                self.aval_compteur_tete_id,
                self.aval_point_eau_id,
            )
        )

        if amont_count != 1:
            raise ValidationError("Une liaison doit avoir exactement un element amont.")
        if aval_count != 1:
            raise ValidationError("Une liaison doit avoir exactement un element aval.")

        amont_type = self.get_amont_type()
        aval_type = self.get_aval_type()
        amont_node = self.get_amont_node()
        aval_node = self.get_aval_node()

        if amont_type == aval_type and getattr(amont_node, 'pk', None) == getattr(aval_node, 'pk', None):
            raise ValidationError("Une liaison ne peut pas boucler sur le meme element.")

        base_ouvrage_id = self._effective_ouvrage_id_for_ouvrage(self.ouvrage)
        node_effective_ids = {
            node_id for node_id in (
                self._effective_ouvrage_id_for_node(amont_node),
                self._effective_ouvrage_id_for_node(aval_node),
            ) if node_id
        }

        if base_ouvrage_id and node_effective_ids and any(node_id != base_ouvrage_id for node_id in node_effective_ids):
            raise ValidationError("Les elements relies doivent appartenir au meme ouvrage ou au meme groupe source/extension.")

        if self._would_create_cycle(amont_type, amont_node, aval_type, aval_node):
            raise ValidationError("Cette liaison creerait une boucle dans l'organigramme hydraulique.")

    def __str__(self):
        amont = self.get_amont_node()
        aval = self.get_aval_node()
        return f"{amont or 'Amont'} -> {aval or 'Aval'}"


class Incident(models.Model):
    SEVERITY_CHOICES = [
        ('faible', 'Faible'),
        ('moyenne', 'Moyenne'),
        ('elevee', 'Élevée'),
        ('critique', 'Critique'),
    ]
    
    STATUS_CHOICES = [
        ('ouvert', 'Ouvert'),
        ('en_cours', 'En cours'),
        ('resolu', 'Résolu'),
        ('ferme', 'Fermé'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    incident_title = models.CharField(max_length=255)
    incident_description = models.TextField()
    incident_date = models.DateTimeField()
    resolution_date = models.DateTimeField(null=True, blank=True)
    severity = models.CharField(max_length=50, choices=SEVERITY_CHOICES)
    incident_status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='ouvert')
    resolution_notes = models.TextField(null=True, blank=True)
    impact_description = models.TextField(null=True, blank=True)
    
    ouvrage = models.ForeignKey('organization.Ouvrage', on_delete=models.CASCADE, related_name='incidents')
    reported_by = models.ForeignKey(Employe, on_delete=models.SET_NULL, null=True, blank=True, related_name='reported_incidents')
    assigned_to = models.ForeignKey(Employe, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_incidents')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'incidents'
        verbose_name = 'Incident'
        verbose_name_plural = 'Incidents'

    def __str__(self):
        return f"{self.incident_title} - {self.ouvrage.nom_ouvrage}"


class Adresse(models.Model):
    """
    Modèle représentant les adresses liées aux ouvrages
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Lier vers organization.Ouvrage au lieu de infrastructure.Ouvrage
    ouvrage = models.ForeignKey('organization.Ouvrage', on_delete=models.CASCADE, related_name='adresses_infra')
    nomadresse = models.CharField(max_length=255, verbose_name="Nom de l'adresse")
    adresse_complete = models.TextField(null=True, blank=True, verbose_name="Adresse complète")
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    type_adresse = models.CharField(max_length=50, default='principale', choices=[
        ('principale', 'Adresse principale'),
        ('technique', 'Adresse technique'),
        ('administrative', 'Adresse administrative'),
        ('autre', 'Autre'),
    ])
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'adresses'
        verbose_name = 'Adresse'
        verbose_name_plural = 'Adresses'

    def __str__(self):
        return f"{self.nomadresse} - {self.ouvrage.nom_ouvrage}"


class CarteSociale(models.Model):
    """
    Modèle représentant les cartes sociales liées aux points d'eau
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    numero_carte = models.CharField(max_length=50, blank=True, null=True, verbose_name="Numéro de carte")
    nom_beneficiaire = models.CharField(max_length=255, verbose_name="Nom du bénéficiaire")

    # Relation avec l'ouvrage et le point d'eau
    ouvrage = models.ForeignKey('organization.Ouvrage', on_delete=models.CASCADE, related_name='cartes_sociales_infra')
    point_eau = models.ForeignKey('billing.PointEau', on_delete=models.SET_NULL, null=True, blank=True, related_name='cartes_sociales', verbose_name="Point d'eau")
    point_eau_nom = models.CharField(max_length=255, null=True, blank=True, verbose_name="Nom du point d'eau (obsolète)")

    nombre_habitants = models.IntegerField(null=True, blank=True, verbose_name="Nombre d'habitants")

    date_creation = models.DateField(auto_now_add=True)
    date_expiration = models.DateField(null=True, blank=True)
    statut = models.CharField(max_length=50, default='active', choices=[
        ('active', 'Active'),
        ('suspendue', 'Suspendue'),
        ('expiree', 'Expirée'),
        ('annulee', 'Annulée'),
    ])
    observations = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'cartes_sociales'
        verbose_name = 'Carte Sociale'
        verbose_name_plural = 'Cartes Sociales'

    def __str__(self):
        return f"Carte {self.numero_carte} - {self.nom_beneficiaire}"


class PointControleInfra(models.Model):
    """
    Modèle représentant les points de contrôle pour les inspections d'équipements d'infrastructure
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom = models.CharField(max_length=255, help_text="Nom du point de contrôle")
    description = models.TextField(null=True, blank=True, help_text="Description détaillée du point de contrôle")
    ordre = models.PositiveIntegerField(help_text="Ordre d'inspection du point de contrôle")

    # Relation avec l'équipement
    equipement = models.ForeignKey(EquipementConstitutif, on_delete=models.CASCADE, related_name='points_controle_infra')

    # Photo de référence pour ce point de contrôle spécifique
    photo_reference = models.ForeignKey(
        'filemanager.FileUpload',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='points_controle_infra_reference',
        help_text="Photo de référence montrant l'état normal de ce point de contrôle"
    )

    # Instructions pour l'inspection
    instructions = models.TextField(null=True, blank=True, help_text="Instructions spécifiques pour contrôler ce point")

    # Critères de validation
    criteres_validation = models.JSONField(
        null=True,
        blank=True,
        help_text="Critères de validation sous forme JSON (ex: {'couleur': 'claire', 'pression': '>2bar'})"
    )

    is_obligatoire = models.BooleanField(default=True, help_text="Point de contrôle obligatoire")
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'points_controle_infra'
        verbose_name = 'Point de Contrôle Infrastructure'
        verbose_name_plural = 'Points de Contrôle Infrastructure'
        ordering = ['equipement', 'ordre']
        unique_together = ['equipement', 'ordre']

    def __str__(self):
        return f"{self.nom} ({self.equipement.nom})"


class InspectionInfra(models.Model):
    """
    Modèle représentant une inspection d'équipement d'infrastructure
    """
    STATUS_CHOICES = [
        ('en_cours', 'En cours'),
        ('terminee', 'Terminée'),
        ('suspendue', 'Suspendue'),
        ('annulee', 'Annulée'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    titre = models.CharField(max_length=255, help_text="Titre de l'inspection")
    description = models.TextField(null=True, blank=True)

    # Relation avec l'équipement inspecté
    equipement = models.ForeignKey(EquipementConstitutif, on_delete=models.CASCADE, related_name='inspections_infra')

    # Inspecteur
    inspecteur = models.ForeignKey(Employe, on_delete=models.SET_NULL, null=True, blank=True, related_name='inspections_infra_realisees')

    # Dates
    date_programmee = models.DateTimeField(help_text="Date et heure prévues pour l'inspection")
    date_debut = models.DateTimeField(null=True, blank=True, help_text="Date et heure de début réel")
    date_fin = models.DateTimeField(null=True, blank=True, help_text="Date et heure de fin")

    # Statut et résultats
    statut = models.CharField(max_length=50, choices=STATUS_CHOICES, default='en_cours')
    resultat_global = models.CharField(max_length=50, choices=[
        ('conforme', 'Conforme'),
        ('non_conforme', 'Non conforme'),
        ('attention', 'Attention requise'),
        ('en_attente', 'En attente'),
    ], null=True, blank=True)

    # Notes générales
    observations = models.TextField(null=True, blank=True)
    recommandations = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'inspections_infra'
        verbose_name = 'Inspection Infrastructure'
        verbose_name_plural = 'Inspections Infrastructure'
        ordering = ['-date_programmee']

    def __str__(self):
        return f"Inspection {self.titre} - {self.equipement.nom}"

    @property
    def nb_points_controle(self):
        """Nombre total de points de contrôle pour cet équipement"""
        return self.equipement.points_controle_infra.filter(is_active=True).count()

    @property
    def nb_points_completes(self):
        """Nombre de points de contrôle complétés"""
        return self.resultats_controle_infra.filter(statut='complete').count()

    @property
    def progression(self):
        """Pourcentage de progression de l'inspection"""
        if self.nb_points_controle == 0:
            return 0
        return int(round((self.nb_points_completes / self.nb_points_controle) * 100))


class ResultatControleInfra(models.Model):
    """
    Modèle représentant le résultat du contrôle d'un point spécifique lors d'une inspection d'infrastructure
    """
    STATUT_CHOICES = [
        ('en_attente', 'En attente'),
        ('complete', 'Complété'),
        ('ignore', 'Ignoré'),
    ]

    RESULTAT_CHOICES = [
        ('conforme', 'Conforme'),
        ('non_conforme', 'Non conforme'),
        ('attention', 'Attention'),
        ('non_applicable', 'Non applicable'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    inspection = models.ForeignKey(InspectionInfra, on_delete=models.CASCADE, related_name='resultats_controle_infra')
    point_controle = models.ForeignKey(PointControleInfra, on_delete=models.CASCADE, related_name='resultats_infra')

    # Statut du contrôle
    statut = models.CharField(max_length=50, choices=STATUT_CHOICES, default='en_attente')
    resultat = models.CharField(max_length=50, choices=RESULTAT_CHOICES, null=True, blank=True)

    # Photo prise lors du contrôle
    photo_resultat = models.ForeignKey(
        'filemanager.FileUpload',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resultats_controle_infra',
        help_text="Photo prise lors du contrôle de ce point"
    )

    # Observations et mesures
    observations = models.TextField(null=True, blank=True, help_text="Observations spécifiques à ce point de contrôle")
    mesures_prises = models.JSONField(
        null=True,
        blank=True,
        help_text="Mesures prises sous forme JSON (ex: {'pression': '2.5bar', 'temperature': '25°C'})"
    )

    # Horodatage
    date_controle = models.DateTimeField(null=True, blank=True, help_text="Date et heure du contrôle")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'resultats_controle_infra'
        verbose_name = 'Résultat de Contrôle Infrastructure'
        verbose_name_plural = 'Résultats de Contrôle Infrastructure'
        unique_together = ['inspection', 'point_controle']
        ordering = ['point_controle__ordre']

    def __str__(self):
        return f"Contrôle {self.point_controle.nom} - {self.inspection.titre}"


class EquipementControle(models.Model):
    """Modèle pour associer des points de contrôle spécifiques aux équipements"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    equipement = models.ForeignKey(EquipementConstitutif, on_delete=models.CASCADE, related_name='points_controle')
    point_de_controle = models.ForeignKey('inspections.PointDeControle', on_delete=models.CASCADE)
    ordre = models.PositiveIntegerField(default=0, help_text="Ordre d'affichage du point de contrôle")
    est_obligatoire = models.BooleanField(default=True, help_text="Ce point de contrôle est-il obligatoire?")
    frequence_jours = models.PositiveIntegerField(null=True, blank=True, help_text="Fréquence de contrôle en jours")
    derniere_verification = models.DateTimeField(null=True, blank=True, help_text="Date de la dernière vérification")
    notes = models.TextField(blank=True, help_text="Notes spécifiques pour ce point de contrôle")
    actif = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'equipement_controles'
        verbose_name = 'Point de contrôle pour équipement'
        verbose_name_plural = 'Points de contrôle pour équipements'
        ordering = ['equipement', 'ordre']
        unique_together = ['equipement', 'point_de_controle']

    def __str__(self):
        return f"{self.equipement.nom} - {self.point_de_controle.nom}"

    @property
    def est_en_retard(self):
        """Indique si ce point de contrôle est en retard de vérification"""
        if not self.frequence_jours or not self.derniere_verification:
            return None

        from django.utils import timezone
        from datetime import timedelta

        prochaine_verification = self.derniere_verification + timedelta(days=self.frequence_jours)
        return timezone.now().date() > prochaine_verification.date()

    @property
    def prochaine_verification_due(self):
        """Date de la prochaine vérification due"""
        if not self.frequence_jours or not self.derniere_verification:
            return None

        from datetime import timedelta
        return self.derniere_verification + timedelta(days=self.frequence_jours)
