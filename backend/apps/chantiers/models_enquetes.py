"""
Modèles pour les enquêtes ménages et animations de sensibilisation WASH
"""
from django.db import models
import uuid
from apps.employees.models import Employe
from apps.filemanager.models import FileUpload


class Menage(models.Model):
    """Ménages dans les parcelles des villages en collaboration"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    parcelle = models.ForeignKey(
        'geography.Parcelle',
        on_delete=models.CASCADE,
        related_name='menages',
        verbose_name="Parcelle"
    )
    chantier = models.ForeignKey(
        'chantiers.CaracteristiqueChantier',
        on_delete=models.CASCADE,
        related_name='menages',
        verbose_name="Chantier",
        help_text="Chantier dans le village"
    )

    # Informations du ménage
    nom_chef_menage = models.CharField(
        max_length=255,
        verbose_name="Nom du chef de ménage"
    )
    nombre_personnes = models.IntegerField(
        default=1,
        verbose_name="Nombre de personnes dans le ménage"
    )
    est_femme_seule = models.BooleanField(
        default=False,
        verbose_name="Femme seule"
    )

    # Coordonnées GPS
    latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        verbose_name="Latitude"
    )
    longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        verbose_name="Longitude"
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Date de modification")

    class Meta:
        db_table = 'menages'
        verbose_name = "Ménage"
        verbose_name_plural = "Ménages"
        ordering = ['nom_chef_menage']

    def __str__(self):
        return f"{self.nom_chef_menage} - {self.parcelle}"


class EnqueteMenage(models.Model):
    """Enquêtes répétées sur les ménages (initiale, check1, check2)"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    TYPE_ENQUETE_CHOICES = [
        ('initiale', 'Enquête initiale'),
        ('check1', 'Check 1 - Post animation'),
        ('check2', 'Check 2 - Post chantier'),
    ]

    TYPE_LATRINE_CHOICES = [
        ('aucune', 'Aucune latrine'),
        ('traditionnelle', 'Traditionnelle'),
        ('amelioree', 'Améliorée'),
    ]

    ORIGINE_LATRINE_CHOICES = [
        ('ancienne', 'Ancienne (avant projet)'),
        ('nouvelle', 'Nouvelle (construite pendant projet)'),
    ]

    menage = models.ForeignKey(
        Menage,
        on_delete=models.CASCADE,
        related_name='enquetes',
        verbose_name="Ménage"
    )
    type_enquete = models.CharField(
        max_length=20,
        choices=TYPE_ENQUETE_CHOICES,
        verbose_name="Type d'enquête"
    )
    employe = models.ForeignKey(
        Employe,
        on_delete=models.PROTECT,
        related_name='enquetes_menages',
        verbose_name="Employé enquêteur"
    )
    date_enquete = models.DateField(
        verbose_name="Date de l'enquête"
    )

    # === Questions sur la latrine ===
    menage_utilise_latrine = models.BooleanField(
        default=False,
        verbose_name="Le ménage utilise-t-il une latrine ?"
    )
    menage_a_latrine = models.BooleanField(
        default=False,
        verbose_name="Le ménage a-t-il une latrine ?"
    )
    type_latrine = models.CharField(
        max_length=20,
        choices=TYPE_LATRINE_CHOICES,
        default='aucune',
        verbose_name="Type de latrine"
    )

    # Pour check1 et check2
    origine_latrine = models.CharField(
        max_length=20,
        choices=ORIGINE_LATRINE_CHOICES,
        blank=True,
        verbose_name="Origine de la latrine"
    )

    photo_latrine = models.ForeignKey(
        FileUpload,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='enquetes_latrines',
        verbose_name="Photo de la latrine"
    )

    # === Messages clés WASH ===
    # Question: Comment faites-vous pour éviter la diarrhée ?
    connait_msg_latrine = models.BooleanField(
        default=False,
        verbose_name="Utiliser une latrine"
    )
    connait_msg_eau_potable = models.BooleanField(
        default=False,
        verbose_name="Boire de l'eau potable"
    )
    connait_msg_lavage_mains = models.BooleanField(
        default=False,
        verbose_name="Se laver les mains"
    )

    # Si connaît lavage mains: Avec quoi et quand ?
    lavage_apres_selles = models.BooleanField(
        default=False,
        verbose_name="Lavage après les selles"
    )
    lavage_avec_savon_cendres = models.BooleanField(
        default=False,
        verbose_name="Lavage avec savon ou cendres"
    )

    # === Questions gestion ouvrage (check2 uniquement) ===
    eau_payante = models.BooleanField(
        null=True,
        blank=True,
        verbose_name="L'eau est-elle payante ?"
    )
    paiement_pour_entretien = models.BooleanField(
        null=True,
        blank=True,
        verbose_name="Le paiement sert-il à l'entretien ?"
    )
    gestion_par_soakoja = models.BooleanField(
        null=True,
        blank=True,
        verbose_name="Soakoja gère-t-il l'ouvrage ?"
    )
    coupure_si_non_paiement = models.BooleanField(
        null=True,
        blank=True,
        verbose_name="Coupure d'eau si non-paiement ?"
    )
    appel_soakoja_probleme = models.BooleanField(
        null=True,
        blank=True,
        verbose_name="Appeler Soakoja en cas de problème ?"
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Date de modification")

    class Meta:
        db_table = 'enquetes_menages'
        verbose_name = "Enquête de ménage"
        verbose_name_plural = "Enquêtes de ménages"
        ordering = ['-date_enquete']
        unique_together = ['menage', 'type_enquete']  # Un seul type d'enquête par ménage

    def __str__(self):
        return f"{self.get_type_enquete_display()} - {self.menage.nom_chef_menage} - {self.date_enquete}"

    @property
    def score_messages_wash(self):
        """Calcule le score de rétention des messages (0-5)"""
        score = 0
        if self.connait_msg_latrine:
            score += 1
        if self.connait_msg_eau_potable:
            score += 1
        if self.connait_msg_lavage_mains:
            score += 1
            if self.lavage_apres_selles:
                score += 1
            if self.lavage_avec_savon_cendres:
                score += 1
        return score

    @property
    def score_gestion_ouvrage(self):
        """Score de connaissance de la gestion (0-5) - check2 uniquement"""
        if self.type_enquete != 'check2':
            return None
        score = 0
        if self.eau_payante:
            score += 1
        if self.paiement_pour_entretien:
            score += 1
        if self.gestion_par_soakoja:
            score += 1
        if self.coupure_si_non_paiement:
            score += 1
        if self.appel_soakoja_probleme:
            score += 1
        return score


class TypeAnimation(models.Model):
    """Types d'animations de sensibilisation"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    nom_animation = models.CharField(
        max_length=255,
        verbose_name="Nom de l'animation"
    )
    description = models.TextField(
        blank=True,
        verbose_name="Description"
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")

    class Meta:
        db_table = 'types_animations'
        verbose_name = "Type d'animation"
        verbose_name_plural = "Types d'animations"
        ordering = ['nom_animation']

    def __str__(self):
        return self.nom_animation


class SessionAnimation(models.Model):
    """Session d'animation dans un village"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    chantier = models.ForeignKey(
        'chantiers.CaracteristiqueChantier',
        on_delete=models.CASCADE,
        related_name='sessions_animation',
        verbose_name="Chantier"
    )
    type_animation = models.ForeignKey(
        TypeAnimation,
        on_delete=models.PROTECT,
        related_name='sessions',
        verbose_name="Type d'animation"
    )
    animateur = models.ForeignKey(
        Employe,
        on_delete=models.PROTECT,
        related_name='sessions_animation',
        verbose_name="Animateur"
    )
    date_animation = models.DateField(
        verbose_name="Date de l'animation"
    )
    lieu = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Lieu de l'animation"
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Date de modification")

    class Meta:
        db_table = 'sessions_animations'
        verbose_name = "Session d'animation"
        verbose_name_plural = "Sessions d'animations"
        ordering = ['-date_animation']

    def __str__(self):
        return f"{self.type_animation.nom_animation} - {self.date_animation}"

    @property
    def nb_femmes_attendues(self):
        return self.participants.filter(sexe='F').count()

    @property
    def nb_hommes_attendus(self):
        return self.participants.filter(sexe='M').count()

    @property
    def nb_femmes_presentes(self):
        return self.participants.filter(sexe='F', etait_present=True).count()

    @property
    def nb_hommes_presents(self):
        return self.participants.filter(sexe='M', etait_present=True).count()

    @property
    def taux_presence(self):
        total = self.participants.count()
        if total == 0:
            return 0
        presents = self.participants.filter(etait_present=True).count()
        return (presents / total) * 100


class ParticipantAnimation(models.Model):
    """Participants aux animations (liés aux ménages)"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    SEXE_CHOICES = [
        ('M', 'Homme'),
        ('F', 'Femme'),
    ]

    session = models.ForeignKey(
        SessionAnimation,
        on_delete=models.CASCADE,
        related_name='participants',
        verbose_name="Session d'animation"
    )
    menage = models.ForeignKey(
        Menage,
        on_delete=models.CASCADE,
        related_name='participations',
        verbose_name="Ménage"
    )
    nom_participant = models.CharField(
        max_length=255,
        verbose_name="Nom du participant"
    )
    sexe = models.CharField(
        max_length=1,
        choices=SEXE_CHOICES,
        verbose_name="Sexe"
    )
    etait_present = models.BooleanField(
        default=False,
        verbose_name="Était présent"
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")

    class Meta:
        db_table = 'participants_animations'
        verbose_name = "Participant à animation"
        verbose_name_plural = "Participants aux animations"
        ordering = ['nom_participant']
        unique_together = ['session', 'menage', 'nom_participant']

    def __str__(self):
        return f"{self.nom_participant} - {self.session.type_animation.nom_animation}"

    @property
    def nombre_animations_assistees(self):
        """Nombre total d'animations auxquelles cette personne a assisté"""
        return ParticipantAnimation.objects.filter(
            menage=self.menage,
            nom_participant=self.nom_participant,
            etait_present=True
        ).count()
