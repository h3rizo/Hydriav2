"""
Modèles pour la gestion des familles d'employés et des remboursements
(frais médicaux et frais de scolarité)
"""
from django.db import models
import uuid
from decimal import Decimal


class FamilleEmploye(models.Model):
    """
    Membre de la famille d'un employé.
    Utilisé pour les remboursements de frais médicaux et de scolarité.
    """
    LIEN_CHOICES = [
        ('conjoint', 'Conjoint(e)'),
        ('enfant', 'Enfant'),
        ('parent', 'Parent'),
        ('autre', 'Autre'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    employe = models.ForeignKey(
        'employees.Employe',
        on_delete=models.CASCADE,
        related_name='famille',
        verbose_name="Employé"
    )

    nom = models.CharField(max_length=255, verbose_name="Nom complet")
    date_naissance = models.DateField(null=True, blank=True, verbose_name="Date de naissance")
    lien_parente = models.CharField(
        max_length=20,
        choices=LIEN_CHOICES,
        default='enfant',
        verbose_name="Lien de parenté"
    )

    # Pour les enfants scolarisés
    ecole = models.CharField(max_length=255, null=True, blank=True, verbose_name="École")
    classe = models.CharField(max_length=100, null=True, blank=True, verbose_name="Classe")

    actif = models.BooleanField(default=True, verbose_name="Actif")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'famille_employes'
        verbose_name = "Membre de famille"
        verbose_name_plural = "Membres de famille"
        ordering = ['employe__nom', 'nom']

    def __str__(self):
        return f"{self.nom} ({self.get_lien_parente_display()}) - {self.employe.nom_affichage}"

    @property
    def age(self):
        """Calcule l'âge à partir de la date de naissance"""
        if not self.date_naissance:
            return None
        from datetime import date
        today = date.today()
        return today.year - self.date_naissance.year - (
            (today.month, today.day) < (self.date_naissance.month, self.date_naissance.day)
        )


class FraisMedicaux(models.Model):
    """
    Remboursement de frais médicaux pour un membre de la famille.

    Règles:
    - Remboursement par affection et par mois
    - 80% des soins remboursables
    - Plafonné par organisation.plafond_soins_simples
    - Plafond séparé pour lunettes (organisation.plafond_lunettes)
    - Fortifiants non remboursés
    """
    STATUT_CHOICES = [
        ('en_attente', 'En attente'),
        ('imprime', 'Imprimé'),
        ('exporte', 'Exporté vers DiameX'),
    ]

    TYPE_SOIN_CHOICES = [
        ('soins', 'Soins médicaux'),
        ('lunettes', 'Lunettes / soins dentaires / accouchement'),
        ('hospitalisation', 'Hospitalisation'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Bénéficiaire : soit un membre de famille, soit l'employé lui-même
    membre_famille = models.ForeignKey(
        FamilleEmploye,
        on_delete=models.CASCADE,
        related_name='frais_medicaux',
        verbose_name="Membre de la famille",
        null=True,
        blank=True,
        help_text="Laisser vide si le bénéficiaire est l'employé lui-même"
    )

    employe_beneficiaire = models.ForeignKey(
        'employees.Employe',
        on_delete=models.CASCADE,
        related_name='frais_medicaux_personnels',
        verbose_name="Employé bénéficiaire",
        null=True,
        blank=True,
        help_text="Renseigné si l'employé est le bénéficiaire direct"
    )

    date = models.DateField(verbose_name="Date du remboursement")
    mois_concerne = models.DateField(
        verbose_name="Mois concerné",
        help_text="Premier jour du mois concerné par les soins"
    )

    affection = models.CharField(
        max_length=255,
        verbose_name="Affection/Motif",
        help_text="Description de l'affection ou du motif des soins"
    )

    type_soin = models.CharField(
        max_length=20,
        choices=TYPE_SOIN_CHOICES,
        default='soins',
        verbose_name="Type de soin"
    )

    # Montants
    montant_soins = models.DecimalField(
        max_digits=12, decimal_places=2,
        verbose_name="Montant total des soins (Ar)",
        help_text="Montant total des soins remboursables présentés"
    )
    montant_rembourse = models.DecimalField(
        max_digits=12, decimal_places=2,
        verbose_name="Montant remboursé (Ar)",
        help_text="Montant effectivement remboursé (80% plafonné)"
    )

    # Repos médical (si bénéficiaire = employé)
    repos_medical = models.BooleanField(
        default=False,
        verbose_name="Repos médical"
    )
    repos_date_debut = models.DateField(
        null=True,
        blank=True,
        verbose_name="Début repos médical"
    )
    repos_nb_jours = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Nombre de jours de repos"
    )

    # Justificatif (hospitalisation)
    justificatif_hospitalisation = models.FileField(
        upload_to='frais_medicaux/justificatifs/',
        null=True,
        blank=True,
        verbose_name="Justificatif hospitalisation"
    )

    # Workflow
    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default='en_attente',
        verbose_name="Statut"
    )

    # DiameX
    numero_diamex = models.CharField(
        max_length=50, null=True, blank=True,
        verbose_name="Numéro DiameX"
    )
    base_diamex = models.CharField(
        max_length=50, null=True, blank=True,
        verbose_name="Base DiameX"
    )

    # Dates workflow
    date_impression = models.DateTimeField(null=True, blank=True, verbose_name="Date d'impression")
    date_export = models.DateTimeField(null=True, blank=True, verbose_name="Date d'export DiameX")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'frais_medicaux'
        verbose_name = "Frais médical"
        verbose_name_plural = "Frais médicaux"
        ordering = ['-date']

    def __str__(self):
        beneficiaire = self.nom_beneficiaire
        return f"{beneficiaire} - {self.affection} - {self.mois_concerne.strftime('%m/%Y')}"

    @property
    def employe(self):
        """Retourne l'employé concerné (soit via membre_famille, soit direct)"""
        if self.membre_famille:
            return self.membre_famille.employe
        return self.employe_beneficiaire

    @property
    def nom_beneficiaire(self):
        """Retourne le nom du bénéficiaire"""
        if self.membre_famille:
            return self.membre_famille.nom
        elif self.employe_beneficiaire:
            return self.employe_beneficiaire.nom_complet
        return "Inconnu"

    @classmethod
    def calculer_remboursement(cls, montant_soins, type_soin, organisation):
        """
        Calcule le montant du remboursement selon les règles.

        Args:
            montant_soins: Montant total des soins
            type_soin: 'soins' ou 'lunettes'
            organisation: Instance Organisation (pour les plafonds)

        Returns:
            Decimal: Montant remboursé
        """
        if type_soin == 'hospitalisation':
            return Decimal('0')

        montant = Decimal(str(montant_soins))

        # 80% du montant
        remboursement = montant * Decimal('0.80')

        # Appliquer le plafond selon le type
        if type_soin == 'lunettes':
            plafond = Decimal(str(organisation.plafond_lunettes or 0))
        else:
            plafond = Decimal(str(organisation.plafond_soins_simples or 0))

        if plafond > 0 and remboursement > plafond:
            remboursement = plafond

        # Arrondir à 100 Ar (au supérieur)
        import math
        remboursement = Decimal(math.ceil(float(remboursement) / 100) * 100)

        return remboursement


class FraisScolarite(models.Model):
    """
    Remboursement de frais de scolarité pour un enfant.

    Règles:
    - Remboursement de 50% des frais de scolarité
    """
    STATUT_CHOICES = [
        ('en_attente', 'En attente'),
        ('imprime', 'Imprimé'),
        ('exporte', 'Exporté vers DiameX'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    membre_famille = models.ForeignKey(
        FamilleEmploye,
        on_delete=models.CASCADE,
        related_name='frais_scolarite',
        verbose_name="Enfant"
    )

    date = models.DateField(verbose_name="Date du remboursement")
    annee_scolaire = models.CharField(
        max_length=20,
        verbose_name="Année scolaire",
        help_text="Ex: 2024-2025"
    )

    ecole = models.CharField(max_length=255, verbose_name="École")
    classe = models.CharField(max_length=100, verbose_name="Classe")

    # Montants
    montant_frais = models.DecimalField(
        max_digits=12, decimal_places=2,
        verbose_name="Montant frais de scolarité (Ar)",
        help_text="Montant total des frais de scolarité"
    )
    montant_rembourse = models.DecimalField(
        max_digits=12, decimal_places=2,
        verbose_name="Montant remboursé (Ar)",
        help_text="Montant effectivement remboursé (50%)"
    )

    # Workflow
    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default='en_attente',
        verbose_name="Statut"
    )

    # DiameX
    numero_diamex = models.CharField(
        max_length=50, null=True, blank=True,
        verbose_name="Numéro DiameX"
    )
    base_diamex = models.CharField(
        max_length=50, null=True, blank=True,
        verbose_name="Base DiameX"
    )

    # Dates workflow
    date_impression = models.DateTimeField(null=True, blank=True, verbose_name="Date d'impression")
    date_export = models.DateTimeField(null=True, blank=True, verbose_name="Date d'export DiameX")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'frais_scolarite'
        verbose_name = "Frais de scolarité"
        verbose_name_plural = "Frais de scolarité"
        ordering = ['-date', 'membre_famille__employe__nom']
        # Un seul remboursement par enfant/année scolaire
        unique_together = ('membre_famille', 'annee_scolaire')

    def __str__(self):
        return f"{self.membre_famille.nom} - {self.annee_scolaire} - {self.ecole}"

    @property
    def employe(self):
        return self.membre_famille.employe

    @classmethod
    def calculer_remboursement(cls, montant_frais):
        """
        Calcule le montant du remboursement (50%).

        Args:
            montant_frais: Montant total des frais de scolarité

        Returns:
            Decimal: Montant remboursé
        """
        montant = Decimal(str(montant_frais))

        # 50% du montant
        remboursement = montant * Decimal('0.50')

        # Arrondir à 100 Ar (au supérieur)
        import math
        remboursement = Decimal(math.ceil(float(remboursement) / 100) * 100)

        return remboursement
