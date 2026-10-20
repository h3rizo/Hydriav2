from django.core.exceptions import ValidationError
from django.conf import settings
from django.db import models
from .models_mobile_volume import MobileVolumeOperation, MobileVolumeInvoiceSnapshot
from django.utils import timezone
from apps.organization.models import Base
from apps.employees.models import Employe
from apps.geography.models import Parcelle
from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta, datetime
import uuid

# Import des modèles de prévisions
from .models_previsions import PrevisionBudget, ConfigurationPrevision


class TypePointEau(models.Model):
    """Modèle représentant les types de points d'eau (forage, puits, borne fontaine, etc.)"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom_type = models.CharField(max_length=255, verbose_name="Nom du type de point d'eau")
    description = models.TextField(null=True, blank=True, verbose_name="Description")
    actif = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'typepointeaus'
        verbose_name = "Type de point d'eau"
        verbose_name_plural = "Types de points d'eau"
        ordering = ['nom_type']

    def __str__(self):
        return self.nom_type


class ConfigTarifForfaitaire(models.Model):
    """Tarif forfaitaire plein d'un type de point d'eau, avec période de validité.

    Le tarif d'un point d'eau = tarif plein du type à la date considérée x
    ``PointEau.pourcentage_tarif`` / 100. Un changement de tarif = une nouvelle ligne avec
    sa date de début (l'ancienne reçoit une date de fin).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    type_point_eau = models.ForeignKey(
        TypePointEau, on_delete=models.CASCADE, related_name='configs_tarif_forfaitaire',
        verbose_name="Type de point d'eau",
    )
    tarif = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Tarif plein (Ar)")
    date_debut = models.DateField(verbose_name="Date de début")
    date_fin = models.DateField(null=True, blank=True, verbose_name="Date de fin")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'configtarifforfaitaire'
        verbose_name = "Tarif forfaitaire plein"
        verbose_name_plural = "Tarifs forfaitaires pleins"
        ordering = ['type_point_eau__nom_type', '-date_debut']

    def clean(self):
        if self.date_fin and self.date_debut and self.date_fin < self.date_debut:
            raise ValidationError("La date de fin doit être postérieure à la date de début.")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from .tarifs_forfaitaires import appliquer_tarifs_forfaitaires
        appliquer_tarifs_forfaitaires()

    def delete(self, *args, **kwargs):
        result = super().delete(*args, **kwargs)
        from .tarifs_forfaitaires import appliquer_tarifs_forfaitaires
        appliquer_tarifs_forfaitaires()
        return result

    def __str__(self):
        fin = self.date_fin.strftime('%d/%m/%Y') if self.date_fin else 'en cours'
        return f"{self.type_point_eau} : {self.tarif} Ar ({self.date_debut:%d/%m/%Y} - {fin})"


class PointEau(models.Model):
    """Modèle pour les branchements (pointseaus) - représente les clients"""
    TYPE_ABONNE_CHOICES = [
        ('particulier', 'Particulier'),
        ('boutique', 'Boutique'),
    ]
    PROBLEMATIQUE_PAIEMENT_CHOICES = [
        (0, '0'),
        (1, '1'),
        (2, '2'),
        (3, '3'),
        (4, '4'),
        (5, '5'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code_point_eau = models.CharField(max_length=255, null=True, blank=True, unique=True, verbose_name="Code du point d'eau")
    nomabonne = models.CharField(max_length=255, verbose_name="Nom de l'abonné")
    numeroteleph = models.CharField(max_length=20, null=True, blank=True, verbose_name="Numéro de téléphone")
    contactabonne = models.CharField(max_length=255, null=True, blank=True, verbose_name="Contact")
    # Relations UUID vers les entités correspondantes - avec noms de colonnes explicites
    compteur_tete = models.ForeignKey('CompteurTete', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Compteur de tête", db_column='compteurteteid')
    compteur_abonne_actuel = models.ForeignKey(
        'CompteurAbonne',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='points_eau_actuels',
        verbose_name="Compteur abonne actuel",
    )
    ouvrage = models.ForeignKey('organization.Ouvrage', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Ouvrage", db_column='ouvrageid')
    type_point_eau = models.ForeignKey(TypePointEau, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Type de point d'eau", db_column='typepointeauid')
    parcelle = models.ForeignKey(Parcelle, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Parcelle", db_column='parcelleid')
    datebranchement = models.DateTimeField(null=True, blank=True, verbose_name="Date de branchement")
    datearretbranchement = models.DateTimeField(null=True, blank=True, verbose_name="Date d'arrêt")
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    typeabonne = models.CharField(max_length=255, choices=TYPE_ABONNE_CHOICES, null=True, blank=True, verbose_name="Type d'abonné")
    estbranchementinstitutionnel = models.BooleanField(default=False, verbose_name="Branchement institutionnel")
    tarifforfaitaire = models.FloatField(
        null=True, blank=True, verbose_name="Tarif forfaitaire",
        help_text="Montant appliqué en Ar, calculé : tarif plein du type x pourcentage. "
                  "Conservé pour les pages qui lisent le montant.",
    )
    pourcentage_tarif = models.DecimalField(
        max_digits=8, decimal_places=4, null=True, blank=True,
        verbose_name="% du tarif plein",
        help_text="100 = tarif plein du type de point d'eau (voir ConfigTarifForfaitaire)",
    )
    numerodiamexdemande = models.IntegerField(null=True, blank=True)
    numerodiamexpaiementdevis = models.CharField(max_length=255, null=True, blank=True)
    basediamexdemande = models.CharField(max_length=255, null=True, blank=True, verbose_name="Base DiameX demande")
    basediamexpaiementdevis = models.CharField(max_length=255, null=True, blank=True)
    montant_demande_bp = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name="Montant de la demande BP")
    montantdemandepaye = models.FloatField(null=True, blank=True, verbose_name="Montant demande payé")
    montantdevispaye = models.FloatField(null=True, blank=True, verbose_name="Montant devis payé")
    problematique_paiement = models.IntegerField(
        choices=PROBLEMATIQUE_PAIEMENT_CHOICES,
        default=0,
        verbose_name="Problématique paiement",
        help_text="0: pas de problème, 1: attente avant paiement, 2: certains usagers ne paient pas, 3: coupure avant paiement, 4: coupure longue avant paiement, 5: usagers ne paient pas et coupure impossible",
    )
    problematique_commentaire = models.TextField(
        null=True,
        blank=True,
        verbose_name="Problématique commentaire",
    )

    # Champs ajoutés pour compléter la gestion des points d'eau
    nombre_consommateurs = models.IntegerField(null=True, blank=True, verbose_name="Nombre de consommateurs")
    nombre_menages_consommateurs = models.IntegerField(null=True, blank=True, verbose_name="Nombre de ménages consommateurs")
    idxls = models.CharField(max_length=50, null=True, blank=True, verbose_name="ID Excel")
    numerodiamexdevis = models.IntegerField(null=True, blank=True, verbose_name="Diamètre devis")
    basediamexdevis = models.CharField(max_length=255, null=True, blank=True, verbose_name="Base diamètre devis")
    datepaiementdemande = models.DateTimeField(null=True, blank=True, verbose_name="Date paiement demande")
    datepaiementdevis = models.DateTimeField(null=True, blank=True, verbose_name="Date paiement devis")

    # Champs pour le workflow de BP
    distance = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name="Distance (mètres)",
        help_text="Distance depuis le point de raccordement en mètres"
    )
    promotion_devis = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, default=0,
        verbose_name="Promotion devis (Ar)",
        help_text="Montant de la promotion accordée sur le devis (en Ariary)"
    )

    # Photos du point d'eau (stockées en JSON avec métadonnées)
    photos = models.JSONField(null=True, blank=True, verbose_name="Photos", help_text="Liste des photos du point d'eau avec leurs métadonnées")

    # Besoin en clôture
    besoin_en_cloture = models.BooleanField(default=False, verbose_name="Besoin en clôture", help_text="Indique si le point d'eau nécessite une clôture")

    createdat = models.DateTimeField(null=True, blank=True)
    updatedat = models.DateTimeField(null=True, blank=True)
    updated_by = models.ForeignKey(
        Employe,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='points_eau_modifies',
        verbose_name="Mis à jour par"
    )

    class Meta:
        db_table = 'pointseaus'
        verbose_name = 'Point d\'eau (Client)'
        verbose_name_plural = 'Points d\'eau (Clients)'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Valeur du tarif à la lecture : permet de savoir si un code a modifié le montant
        # directement (anciens formulaires, imports) plutôt que le pourcentage
        self._tarif_initial = self.__dict__.get('tarifforfaitaire')

    def save(self, *args, **kwargs):
        """Horodate toute sauvegarde, y compris avec ``update_fields``.

        Garde ``tarifforfaitaire`` (montant) et ``pourcentage_tarif`` cohérents : un montant
        saisi directement redéduit le pourcentage, sinon le montant est recalculé depuis
        le pourcentage et le tarif plein en vigueur."""
        self.updatedat = timezone.now()
        from .tarifs_forfaitaires import synchroniser_tarif_point
        synchroniser_tarif_point(self)
        update_fields = kwargs.get('update_fields')
        if update_fields is not None:
            update_fields = set(update_fields)
            if update_fields:
                update_fields.add('updatedat')
                if update_fields & {'tarifforfaitaire', 'pourcentage_tarif', 'type_point_eau'}:
                    update_fields.update({'tarifforfaitaire', 'pourcentage_tarif'})
                kwargs['update_fields'] = list(update_fields)
        result = super().save(*args, **kwargs)
        self._tarif_initial = self.__dict__.get('tarifforfaitaire')
        return result

    def __str__(self):
        return f"{self.nomabonne} ({self.get_typeabonne_display() or 'N/A'})"

    @property
    def forfaitaire_display_label(self):
        idxls = (self.idxls or '').strip()
        nomabonne = (self.nomabonne or '').strip()

        if idxls and nomabonne:
            return f"{idxls} - {nomabonne}"
        if idxls:
            return idxls
        if nomabonne:
            return nomabonne
        if self.code_point_eau:
            return self.code_point_eau
        return str(self.pk)

    @property
    def nom(self):
        """
        Alias de compatibilite pour les anciens templates qui attendent `point_eau.nom`.
        """
        return self.forfaitaire_display_label

    @property
    def tarif(self):
        """
        Alias de compatibilite pour les anciens templates qui attendent `point_eau.tarif`.
        """
        return self.tarifforfaitaire

    @property
    def is_active(self):
        """Un branchement est actif s'il a une date de branchement et pas de date d'arrêt"""
        return self.datebranchement is not None and self.datearretbranchement is None

    @property
    def is_private(self):
        """Retourne True si le point d'eau est un branchement privé"""
        if self.type_point_eau:
            return 'privé' in self.type_point_eau.nom_type.lower() or 'prive' in self.type_point_eau.nom_type.lower()
        return False

    @property
    def is_public(self):
        """Retourne True si le point d'eau est public (non privé)"""
        return not self.is_private

    @classmethod
    def get_private_count(cls):
        """Retourne le nombre de points d'eau privés (avec datebranchement non vide)"""
        return cls.objects.filter(
            type_point_eau__nom_type__icontains='privé',
            datebranchement__isnull=False
        ).count()

    @classmethod
    def get_public_count(cls):
        """Retourne le nombre de points d'eau publics (avec datebranchement non vide)"""
        return cls.objects.filter(
            datebranchement__isnull=False
        ).exclude(
            type_point_eau__nom_type__icontains='privé'
        ).count()

    @classmethod
    def get_total_count(cls):
        """Retourne le nombre total de points d'eau (avec datebranchement non vide)"""
        return cls.objects.filter(datebranchement__isnull=False).count()

    @classmethod
    def get_cut_count(cls):
        """Retourne le nombre de points d'eau coupés (datebranchement ET datearret non vides)"""
        return cls.objects.filter(
            datebranchement__isnull=False,
            datearretbranchement__isnull=False
        ).count()

    @property
    def is_cut(self):
        """Retourne True si le point d'eau est coupé (branché puis arrêté)"""
        return self.datebranchement is not None and self.datearretbranchement is not None


class CompteurTete(models.Model):
    """Modèle pour les compteurs de tête"""
    STATUT_CHOICES = [
        ('operationnel', 'Opérationnel'),
        ('en_panne', 'En panne'),
        ('en_maintenance', 'En maintenance'),
        ('hors_service', 'Hors service'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ouvrage = models.ForeignKey('organization.Ouvrage', on_delete=models.CASCADE, related_name='compteurs_tete', db_column='ouvrageid', null=True, blank=True)
    numerocompteur = models.CharField(max_length=255, verbose_name="Numéro compteur")
    marque = models.CharField(max_length=100, null=True, blank=True, verbose_name="Marque")
    modele = models.CharField(max_length=100, null=True, blank=True, verbose_name="Modèle")
    date_installation = models.DateField(null=True, blank=True, verbose_name="Date d'installation")
    index_initial = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Index initial")
    statut = models.CharField(max_length=50, choices=STATUT_CHOICES, default='operationnel', verbose_name="Statut")
    createdat = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updatedat = models.DateTimeField(auto_now=True, null=True, blank=True)

    class Meta:
        db_table = 'compteurtetes'
        verbose_name = 'Compteur de tête'
        verbose_name_plural = 'Compteurs de tête'

    def __str__(self):
        return f"Compteur {self.numerocompteur}"


class ReleveCompteurTete(models.Model):
    """Historique des releves des compteurs de tete avec comparaison aval."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    compteur_tete = models.ForeignKey(
        'CompteurTete',
        on_delete=models.CASCADE,
        related_name='releves_compteur_tete',
        verbose_name="Compteur de tete",
    )
    date_releve = models.DateField(verbose_name="Date du releve")
    ancien_index = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Ancien index",
    )
    nouvel_index = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Nouvel index",
    )
    volume_tete = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Volume compteur tete",
    )
    volume_aval = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Volume points aval",
    )
    ecart_volume = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Ecart de volume",
    )
    nb_points_eau_aval = models.PositiveIntegerField(
        default=0,
        verbose_name="Nombre de points d'eau aval",
    )
    explication_ecart = models.TextField(
        null=True,
        blank=True,
        verbose_name="Explication de l'ecart",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'releves_compteurs_tete'
        verbose_name = 'Releve compteur de tete'
        verbose_name_plural = 'Releves compteurs de tete'
        ordering = ['-date_releve', '-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['compteur_tete', 'date_releve'],
                name='uniq_releve_compteur_tete_date',
            )
        ]
        indexes = [
            models.Index(fields=['compteur_tete', 'date_releve']),
            models.Index(fields=['date_releve']),
        ]

    def __str__(self):
        return f"{self.compteur_tete} - {self.date_releve}"

    @property
    def has_significant_gap(self):
        try:
            return abs(Decimal(str(self.ecart_volume or 0))) > Decimal('0.01')
        except Exception:
            return False

    def clean(self):
        super().clean()

        ancien_index = Decimal(str(self.ancien_index or 0))
        nouvel_index = Decimal(str(self.nouvel_index or 0))
        if nouvel_index < ancien_index:
            raise ValidationError({
                'nouvel_index': "Le nouvel index doit etre superieur ou egal a l'ancien index."
            })


class ChangementCompteurTete(models.Model):
    """Trace un remplacement physique de compteur sans creer de volume negatif."""

    MOTIF_CHOICES = [
        ('defectueux', 'Compteur defectueux'),
        ('bloque', 'Compteur bloque'),
        ('casse', 'Compteur casse'),
        ('fin_vie', 'Fin de vie'),
        ('vole', 'Compteur vole'),
        ('preventif', 'Remplacement preventif'),
        ('autre', 'Autre'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ancien_compteur = models.OneToOneField(
        'CompteurTete',
        on_delete=models.PROTECT,
        related_name='changement_sortant',
        verbose_name='Ancien compteur',
    )
    nouveau_compteur = models.OneToOneField(
        'CompteurTete',
        on_delete=models.PROTECT,
        related_name='changement_entrant',
        verbose_name='Nouveau compteur',
    )
    releve_final_ancien = models.OneToOneField(
        'ReleveCompteurTete',
        on_delete=models.PROTECT,
        related_name='changement_compteur',
        verbose_name="Releve final de l'ancien compteur",
    )
    date_changement = models.DateField(verbose_name='Date du changement')
    index_retrait = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Index de retrait de l'ancien compteur",
    )
    index_initial_nouveau = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name='Index initial du nouveau compteur',
    )
    motif = models.CharField(max_length=30, choices=MOTIF_CHOICES, verbose_name='Motif')
    explication = models.TextField(verbose_name='Explication')
    nb_points_transferes = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='changements_compteurs_tete_crees',
        verbose_name='Effectue par',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'changements_compteurs_tete'
        verbose_name = 'Changement de compteur de tete'
        verbose_name_plural = 'Changements de compteurs de tete'
        ordering = ['-date_changement', '-created_at']
        indexes = [models.Index(fields=['date_changement'])]

    def __str__(self):
        return f"{self.ancien_compteur} -> {self.nouveau_compteur} ({self.date_changement})"

    def clean(self):
        super().clean()
        if self.ancien_compteur_id and self.nouveau_compteur_id:
            if self.ancien_compteur_id == self.nouveau_compteur_id:
                raise ValidationError({'nouveau_compteur': 'Le nouveau compteur doit etre different.'})
            if self.ancien_compteur.ouvrage_id != self.nouveau_compteur.ouvrage_id:
                raise ValidationError({'nouveau_compteur': 'Les deux compteurs doivent appartenir au meme ouvrage.'})


class CompteurAbonne(models.Model):
    """Compteur physique pose sur un point d'eau abonne."""

    STATUT_CHOICES = [
        ('operationnel', 'Operationnel'),
        ('hors_service', 'Hors service'),
        ('perdu', 'Perdu ou vole'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    point_eau = models.ForeignKey(
        PointEau, on_delete=models.PROTECT, related_name='compteurs_abonnes'
    )
    numero = models.CharField(max_length=100, unique=True, verbose_name='Numero de compteur')
    marque = models.CharField(max_length=100, null=True, blank=True)
    modele = models.CharField(max_length=100, null=True, blank=True)
    date_installation = models.DateField(verbose_name="Date d'installation")
    date_retrait = models.DateField(null=True, blank=True)
    index_initial = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    index_retrait = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    statut = models.CharField(max_length=30, choices=STATUT_CHOICES, default='operationnel')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'compteurs_abonnes'
        ordering = ['point_eau_id', '-date_installation', '-created_at']
        indexes = [models.Index(fields=['point_eau', 'statut'])]

    def __str__(self):
        return f"{self.numero} - {self.point_eau}"

    def clean(self):
        super().clean()
        if self.index_initial is not None and self.index_initial < 0:
            raise ValidationError({'index_initial': "L'index initial ne peut pas etre negatif."})
        if self.index_retrait is not None and self.index_retrait < self.index_initial:
            raise ValidationError({'index_retrait': "L'index de retrait ne peut pas etre inferieur a l'index initial."})
        if self.date_retrait and self.date_retrait < self.date_installation:
            raise ValidationError({'date_retrait': "La date de retrait precede l'installation."})


class ChangementCompteurAbonne(models.Model):
    """Rupture documentee entre deux compteurs d'un meme abonne."""

    MOTIF_CHOICES = [
        ('defectueux', 'Compteur defectueux'),
        ('bloque', 'Compteur bloque'),
        ('casse', 'Compteur casse'),
        ('fin_vie', 'Fin de vie'),
        ('vole', 'Compteur vole'),
        ('preventif', 'Remplacement preventif'),
        ('autre', 'Autre'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    point_eau = models.ForeignKey(
        PointEau, on_delete=models.PROTECT, related_name='changements_compteurs_abonnes'
    )
    ancien_compteur = models.OneToOneField(
        CompteurAbonne, on_delete=models.PROTECT, related_name='changement_sortant'
    )
    nouveau_compteur = models.OneToOneField(
        CompteurAbonne, on_delete=models.PROTECT, related_name='changement_entrant'
    )
    releve_precedent = models.ForeignKey(
        'Releve', on_delete=models.PROTECT, null=True, blank=True,
        related_name='changements_compteur_apres_releve'
    )
    releve_facture = models.ForeignKey(
        'Releve', on_delete=models.PROTECT, null=True, blank=True,
        related_name='changements_compteur_factures',
        help_text='Premier releve qui additionne les consommations avant et apres remplacement.'
    )
    date_changement = models.DateField()
    index_reference_ancien = models.DecimalField(max_digits=12, decimal_places=2)
    index_retrait = models.DecimalField(max_digits=12, decimal_places=2)
    index_initial_nouveau = models.DecimalField(max_digits=12, decimal_places=2)
    motif = models.CharField(max_length=30, choices=MOTIF_CHOICES)
    explication = models.TextField()
    ancien_compteur_illisible = models.BooleanField(default=False)
    consommation_ancienne_estimee = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Utilisee uniquement si l'ancien compteur est illisible."
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='changements_compteurs_abonnes_crees'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'changements_compteurs_abonnes'
        ordering = ['-date_changement', '-created_at']
        indexes = [
            models.Index(fields=['point_eau', 'date_changement']),
            models.Index(fields=['point_eau', 'releve_facture']),
        ]

    @property
    def volume_ancien(self):
        if self.ancien_compteur_illisible:
            return self.consommation_ancienne_estimee or Decimal('0')
        return (self.index_retrait or Decimal('0')) - (self.index_reference_ancien or Decimal('0'))

    def clean(self):
        super().clean()
        if self.ancien_compteur_id == self.nouveau_compteur_id:
            raise ValidationError({'nouveau_compteur': 'Le nouveau compteur doit etre different.'})
        if self.ancien_compteur_id and self.ancien_compteur.point_eau_id != self.point_eau_id:
            raise ValidationError({'ancien_compteur': "L'ancien compteur n'appartient pas a ce point d'eau."})
        if self.nouveau_compteur_id and self.nouveau_compteur.point_eau_id != self.point_eau_id:
            raise ValidationError({'nouveau_compteur': "Le nouveau compteur n'appartient pas a ce point d'eau."})
        if self.index_initial_nouveau < 0:
            raise ValidationError({'index_initial_nouveau': "L'index initial ne peut pas etre negatif."})
        if self.ancien_compteur_illisible:
            if self.consommation_ancienne_estimee is None or self.consommation_ancienne_estimee < 0:
                raise ValidationError({'consommation_ancienne_estimee': 'Une estimation positive ou nulle est obligatoire.'})
        elif self.index_retrait < self.index_reference_ancien:
            raise ValidationError({'index_retrait': "L'index de retrait est inferieur au dernier index connu."})


class Releve(models.Model):
    """Modèle pour les relevés existants dans Supabase"""
    STATUT_CHOICES = [
        ('paye', 'Payé'),
        ('impaye', 'Impayé'),
        ('en_attente', 'En attente'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Relation avec le point d'eau
    point_eau = models.ForeignKey(
        'billing.PointEau',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='releves',
        verbose_name="Point d'eau"
    )
    compteur_abonne = models.ForeignKey(
        CompteurAbonne,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='releves',
        verbose_name='Compteur abonne releve',
    )
    origine_calcul = models.CharField(
        max_length=20,
        choices=[
            ('legacy', 'Historique'),
            ('simple', 'Compteur unique'),
            ('multi_compteur', 'Changement de compteur'),
        ],
        default='legacy',
        help_text="Les anciennes lignes restent en mode historique sans recalcul.",
    )

    abonne = models.CharField(max_length=255, verbose_name="Abonné")
    datereleve = models.DateField(verbose_name="Date du relevé")
    ancienindex = models.FloatField(verbose_name="Ancien index")
    nouvelindex = models.FloatField(verbose_name="Nouvel index")
    consommation = models.FloatField(verbose_name="Consommation")

    # Nouveaux champs pour le workflow complet
    volume_carte_sociale = models.FloatField(
        default=0,
        verbose_name="Volume carte sociale (m³)",
        help_text="Volume consommé via les cartes sociales"
    )
    volume_non_facture = models.FloatField(
        default=0,
        verbose_name="Volume non facturé (m³)",
        help_text="Volume non facturé (peut être négatif, ex: changement compteur)"
    )
    volume_facture = models.FloatField(
        null=True,
        blank=True,
        verbose_name="Volume facturé (m³)",
        help_text="Volume réellement facturé (consommation - cartes sociales - non facturé)"
    )
    remarque = models.TextField(
        null=True,
        blank=True,
        verbose_name="Remarque",
        help_text="Remarque concernant ce relevé (obligatoire si volume non facturé renseigné)"
    )

    montant = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Montant",
        help_text="Montant à payer (sera calculé via workflow spécifique)"
    )
    statut = models.CharField(max_length=50, choices=STATUT_CHOICES, verbose_name="Statut")
    datepaiement = models.DateField(null=True, blank=True, verbose_name="Date de paiement")
    montantpaye = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Montant payé")

    # Champs DiameX pour suivi comptable
    numeroDiameX = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="Numéro DiameX",
        help_text="Numéro de pièce DiameX - indique que le paiement est enregistré en comptabilité"
    )
    baseDiameX = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="Base DiameX",
        help_text="Code base DiameX"
    )

    # Photo du relevé
    photo_releve = models.ImageField(
        upload_to='releves/%Y/%m/',
        null=True,
        blank=True,
        verbose_name="Photo du relevé",
        help_text="Photo du compteur au moment du relevé"
    )

    # Contexte de la saisie mobile Terrain. Ces valeurs décrivent la position
    # de l'agent au moment du relevé, pas les coordonnées de référence du point.
    terrain_local_uuid = models.UUIDField(null=True, blank=True, unique=True, db_index=True)
    terrain_agent = models.ForeignKey(
        Employe,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='releves_terrain_saisis',
    )
    terrain_captured_at = models.DateTimeField(null=True, blank=True)
    terrain_latitude = models.FloatField(null=True, blank=True)
    terrain_longitude = models.FloatField(null=True, blank=True)
    terrain_gps_accuracy_m = models.FloatField(null=True, blank=True)
    terrain_distance_point_m = models.FloatField(null=True, blank=True)
    terrain_gps_anomaly = models.BooleanField(default=False)

    # Numéro de facture séquentiel
    numero_facture = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        unique=True,
        verbose_name="Numéro de facture",
        help_text="Numéro de facture au format F-YYYY-NNN (ex: F-2025-001)"
    )

    # Suivi de l'impression de la facture
    facture_imprimee = models.BooleanField(
        default=False,
        verbose_name="Facture imprimée",
        help_text="Indique si la facture a été imprimée - empêche le recalcul"
    )
    date_impression = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date d'impression",
        help_text="Date et heure de la première impression de la facture"
    )

    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'releves'
        verbose_name = 'Relevé'
        verbose_name_plural = 'Relevés'
        ordering = ['-datereleve']

    def __str__(self):
        return f"Relevé {self.abonne} - {self.datereleve}"

    @property
    def est_paye(self):
        """
        Un relevé est considéré comme payé si le numéro DiameX est renseigné
        (indique qu'il a été enregistré en comptabilité)
        """
        return bool(self.numeroDiameX and self.numeroDiameX.strip())

    def save(self, *args, **kwargs):
        """Calcul automatique du volume facturé"""
        if self.volume_facture is None:
            self.volume_facture = max(
                0,
                self.consommation - self.volume_carte_sociale - self.volume_non_facture
            )
        super().save(*args, **kwargs)


class SegmentConsommationReleve(models.Model):
    """Part de consommation d'une facture mesuree par un compteur physique."""

    TYPE_CHOICES = [
        ('normal', 'Compteur de la periode'),
        ('avant_changement', 'Avant changement'),
        ('apres_changement', 'Apres changement'),
        ('estime', 'Ancien compteur illisible - estimation'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    releve = models.ForeignKey(
        Releve, on_delete=models.CASCADE, related_name='segments_consommation'
    )

    compteur = models.ForeignKey(
        CompteurAbonne, on_delete=models.PROTECT, related_name='segments_consommation'
    )
    ordre = models.PositiveSmallIntegerField(default=1)
    type_segment = models.CharField(max_length=30, choices=TYPE_CHOICES, default='normal')
    date_debut = models.DateField(null=True, blank=True)
    date_fin = models.DateField(null=True, blank=True)
    index_debut = models.DecimalField(max_digits=12, decimal_places=2)
    index_fin = models.DecimalField(max_digits=12, decimal_places=2)
    volume = models.DecimalField(max_digits=12, decimal_places=2)
    est_estime = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'segments_consommation_releves'
        ordering = ['releve_id', 'ordre']
        constraints = [
            models.UniqueConstraint(fields=['releve', 'ordre'], name='uniq_segment_releve_ordre')
        ]

    def clean(self):
        super().clean()
        if self.volume < 0:
            raise ValidationError({'volume': 'Le volume du segment ne peut pas etre negatif.'})
        if not self.est_estime and self.index_fin < self.index_debut:
            raise ValidationError({'index_fin': "L'index final est inferieur a l'index initial."})


class ConsoCarteSociale(models.Model):
    """
    Modèle pour stocker les détails de consommation par carte sociale pour chaque relevé
    Volume unitaire fixe : 20L par bidon
    """
    # Constante : volume d'un bidon en litres
    VOLUME_BIDON_LITRES = 20.0

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Relations
    releve = models.ForeignKey(
        'Releve',
        on_delete=models.CASCADE,
        related_name='consommations_cartes_sociales',
        verbose_name="Relevé",
        null=True,
        blank=True
    )
    carte_sociale = models.ForeignKey(
        'infrastructure.CarteSociale',
        on_delete=models.CASCADE,
        related_name='consommations',
        verbose_name="Carte sociale"
    )

    # Données de consommation
    quantite_bidons = models.IntegerField(
        default=0,
        verbose_name="Quantité de bidons",
        help_text="Nombre de bidons de 20L consommés"
    )
    volume_total = models.FloatField(
        verbose_name="Volume total (m³)",
        help_text="Volume total en m³ (quantité × 20L / 1000)"
    )

    # Données de facturation et de suivi
    date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date de facture",
        help_text="Date de la facture à déduire du kiosque"
    )
    montant_paye = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Montant payé",
        help_text="Montant payé pour cette carte sociale"
    )

    # Photo de justification
    photo = models.TextField(
        null=True,
        blank=True,
        verbose_name="Photo du ticket rempli",
        help_text="Photo du ticket de caisse rempli justifiant la consommation"
    )

    # Synchronisation DiameX
    numeroDiameX = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="Numéro DiameX",
        help_text="Numéro de la pièce dans DiameX"
    )
    baseDiameX = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="Base DiameX",
        help_text="Prog/Base DiameX"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'conso_cartes_sociales'
        verbose_name = 'Consommation Carte Sociale'
        verbose_name_plural = 'Consommations Cartes Sociales'

    def __str__(self):
        return f"{self.carte_sociale.nom_beneficiaire} - {self.quantite_bidons} bidons - {self.volume_total} m³"

    def save(self, *args, **kwargs):
        """Calcule le volume et garde la date alignee sur le releve lie."""
        self.volume_total = (self.quantite_bidons * self.VOLUME_BIDON_LITRES) / 1000
        if self.releve_id:
            # La consommation de carte sociale appartient a la meme periode que
            # son releve. Cette regle protege aussi les creations faites depuis
            # les imports et les autres API.
            self.date = self.releve.datereleve
        if kwargs.get('update_fields') is not None:
            kwargs['update_fields'] = set(kwargs['update_fields']) | {'date', 'volume_total'}
        super().save(*args, **kwargs)


class AdresseFournisseur(models.Model):
    """Adresse fournisseur dediee, reutilisable par plusieurs fournisseurs."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    adresse = models.TextField(unique=True, verbose_name="Adresse fournisseur")
    actif = models.BooleanField(default=True, verbose_name="Active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'adresses_fournisseurs'
        verbose_name = "Adresse fournisseur"
        verbose_name_plural = "Adresses fournisseurs"
        ordering = ['adresse']

    def __str__(self):
        return self.adresse


class AdresseFournisseurDistrict(models.Model):
    """Correspondance entre une adresse fournisseur et un district."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    adresse = models.TextField(unique=True, verbose_name="Adresse fournisseur")
    adresse_fournisseur = models.ForeignKey(
        'AdresseFournisseur',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='mappings_districts',
        verbose_name="Adresse fournisseur (relation)"
    )
    district = models.ForeignKey(
        'geography.District',
        on_delete=models.CASCADE,
        related_name='adresses_fournisseurs',
        verbose_name="District"
    )
    actif = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'adresses_fournisseurs_districts'
        verbose_name = "Adresse fournisseur / district"
        verbose_name_plural = "Adresses fournisseurs / districts"
        ordering = ['adresse']

    def __str__(self):
        return f"{self.adresse} -> {self.district.nom_district}"

    @property
    def ex_province(self):
        region = getattr(self.district, 'region', None)
        return getattr(region, 'ex_province', None) if region else None


class Fournisseur(models.Model):
    """Modèle pour les fournisseurs de services/équipements"""
    TYPE_FOURNISSEUR_CHOICES = [
        ('equipement', 'Équipement'),
        ('service', 'Service'),
        ('maintenance', 'Maintenance'),
        ('construction', 'Construction'),
        ('mecanicien', 'Mecanicien'),
        ('autre', 'Autre'),
    ]

    NIF_ISI_CHOICES = [
        ('', 'Vide'),
        ('ISI', 'ISI'),
        ('NIF', 'NIF'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    idxls = models.IntegerField(null=True, blank=True, unique=True, verbose_name="ID XLS", help_text="Identifiant unique pour import/export Excel")
    nom_fournisseur = models.CharField(max_length=255, verbose_name="Nom du fournisseur")
    telephone = models.CharField(max_length=20, null=True, blank=True, verbose_name="Téléphone")
    email = models.EmailField(null=True, blank=True, verbose_name="Email")

    # Adresse comme ForeignKey vers la table Adresse
    adresse_relation = models.ForeignKey('infrastructure.Adresse', on_delete=models.SET_NULL, null=True, blank=True, related_name='fournisseurs', verbose_name="Adresse (relation)")
    adresse_fournisseur = models.ForeignKey(
        'AdresseFournisseur',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fournisseurs',
        verbose_name="Adresse fournisseur"
    )
    adresse = models.TextField(null=True, blank=True, verbose_name="Adresse (texte)")
    code_postal = models.CharField(max_length=3, null=True, blank=True, verbose_name="Code postal")

    type_fournisseur = models.CharField(max_length=50, choices=TYPE_FOURNISSEUR_CHOICES, null=True, blank=True, verbose_name="Type")

    # Informations légales
    nif_ou_isi = models.CharField(max_length=3, choices=NIF_ISI_CHOICES, blank=True, default='', verbose_name="NIF ou ISI")
    numero_nif = models.CharField(max_length=10, null=True, blank=True, verbose_name="Numéro NIF (10 chiffres)")
    numero_stat = models.CharField(max_length=17, null=True, blank=True, verbose_name="Numéro STAT (17 chiffres)")
    cin = models.CharField(max_length=12, null=True, blank=True, verbose_name="CIN (12 chiffres)")
    date_cin = models.DateField(null=True, blank=True, verbose_name="Date CIN")
    lieu_cin = models.CharField(max_length=255, null=True, blank=True, verbose_name="Lieu CIN")
    code_tiers = models.CharField(
        max_length=6,
        null=True,
        blank=True,
        unique=True,
        verbose_name="Code Tiers",
        help_text="Code tiers comptabilité (6 chiffres) - doit être unique"
    )

    # Autres informations
    autre_information = models.TextField(null=True, blank=True, verbose_name="Autres informations")
    tacheron = models.BooleanField(default=False, verbose_name="Tâcheron")
    devis = models.BooleanField(default=False, verbose_name="Devis")
    prestation = models.BooleanField(default=False, verbose_name="Prestataire", help_text="Si coché, affichera 'PREST' dans la description DiameX")

    actif = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'fournisseurs'
        verbose_name = 'Fournisseur'
        verbose_name_plural = 'Fournisseurs'
        ordering = ['nom_fournisseur']

    def __str__(self):
        return self.nom_fournisseur

    @property
    def ex_province(self):
        adresse = (self.adresse_fournisseur.adresse if self.adresse_fournisseur_id else self.adresse or '').strip()
        if not adresse:
            return None
        mapping = (
            AdresseFournisseurDistrict.objects
            .select_related('district__region__ex_province')
            .filter(models.Q(adresse_fournisseur=self.adresse_fournisseur) | models.Q(adresse__iexact=adresse), actif=True)
            .first()
        )
        if not mapping:
            return None
        return mapping.ex_province


class FournisseurFusionInstruction(models.Model):
    """Suivi des corrections manuelles a effectuer dans les bases DiameX apres fusion."""

    STATUS_PENDING = 'pending'
    STATUS_DONE = 'done'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'En attente'),
        (STATUS_DONE, 'Corrige'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_fournisseur = models.ForeignKey(
        Fournisseur,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fusion_instructions_source',
        verbose_name='Fournisseur fusionne',
    )
    target_fournisseur = models.ForeignKey(
        Fournisseur,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fusion_instructions_target',
        verbose_name='Fournisseur conserve',
    )
    source_nom_snapshot = models.CharField(max_length=255, blank=True, default='', verbose_name='Nom source snapshot')
    target_nom_snapshot = models.CharField(max_length=255, blank=True, default='', verbose_name='Nom cible snapshot')
    ancien_idxls = models.IntegerField(null=True, blank=True, verbose_name='Ancien IDxls')
    nouvel_idxls = models.IntegerField(null=True, blank=True, verbose_name='Nouvel IDxls')
    lignes_diamex_a_corriger = models.PositiveIntegerField(default=0, verbose_name='Lignes DiameX a corriger')
    lignes_diamex_details = models.JSONField(default=list, blank=True, verbose_name='Details lignes DiameX')
    statut = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
        verbose_name='Statut',
    )
    note = models.TextField(
        blank=True,
        default='',
        verbose_name='Instruction',
        help_text='Texte montre aux admins pour corriger les codes fournisseurs dans DiameX.',
    )
    commentaire_admin = models.TextField(blank=True, default='', verbose_name='Commentaire admin')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Cree le')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Mis a jour le')
    done_at = models.DateTimeField(null=True, blank=True, verbose_name='Corrige le')

    class Meta:
        db_table = 'fournisseur_fusion_instructions'
        verbose_name = 'Instruction fusion fournisseur'
        verbose_name_plural = 'Instructions fusion fournisseurs'
        ordering = ['statut', '-created_at']

    def __str__(self):
        return (
            f"{self.source_nom_display} -> "
            f"{self.target_nom_display}"
        )

    @property
    def source_nom_display(self):
        if self.source_fournisseur_id and self.source_fournisseur:
            return self.source_fournisseur.nom_fournisseur
        return self.source_nom_snapshot or 'Fournisseur source supprime'

    @property
    def target_nom_display(self):
        if self.target_fournisseur_id and self.target_fournisseur:
            return self.target_fournisseur.nom_fournisseur
        return self.target_nom_snapshot or 'Fournisseur cible supprime'


class FournisseurDuplicateSuggestionIgnore(models.Model):
    """Suggestion de doublon masquee par un utilisateur admin."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    signature = models.CharField(max_length=500, unique=True, verbose_name='Signature suggestion')
    label = models.CharField(max_length=255, blank=True, default='', verbose_name='Libelle suggestion')
    reason = models.TextField(blank=True, default='', verbose_name='Raison')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Cree le')

    class Meta:
        db_table = 'fournisseur_duplicate_suggestion_ignores'
        verbose_name = 'Suggestion doublon ignoree'
        verbose_name_plural = 'Suggestions doublons ignorees'
        ordering = ['-created_at']

    def __str__(self):
        return self.label or self.signature


class TarifVolumetrique(models.Model):
    """Table 1: tarifvolumetriques - Tarifs principaux par ouvrage"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ouvrage = models.ForeignKey('organization.Ouvrage', on_delete=models.CASCADE, related_name='tarifs_volumetriques')
    type_point_eau = models.ForeignKey(TypePointEau, on_delete=models.SET_NULL, null=True, blank=True, related_name='tarifs', verbose_name="Type de point d'eau")
    datedebuttarif = models.DateField(verbose_name="Date de début du tarif", default='2024-01-01')
    datefintarif = models.DateField(null=True, blank=True, verbose_name="Date de fin du tarif")
    prixabonnement = models.IntegerField(verbose_name="Prix d'abonnement (Ar)", default=0)
    volume_minimum_facture = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Volume minimal facturé (m³)")
    institutionnel = models.BooleanField(
        default=False,
        verbose_name="Tarif des branchements institutionnels",
        help_text="Appliqué aux points d'eau cochés « branchement institutionnel » ; à défaut, ils prennent le tarif ordinaire de leur type.",
    )
    actif = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tarifsvolumetriques'
        verbose_name = 'Tarif volumétrique'
        verbose_name_plural = 'Tarifs volumétriques'
        ordering = ['ouvrage', '-datedebuttarif']

    def __str__(self):
        return f"{self.ouvrage.nom_ouvrage} - Tarif du {self.datedebuttarif}"

    @property
    def is_active_now(self):
        """Vérifie si le tarif est actuellement actif"""
        from django.utils import timezone
        today = timezone.now().date()
        return (self.actif and
                self.datedebuttarif <= today and
                (self.datefintarif is None or self.datefintarif >= today))


class TarifVolumetrique2(models.Model):
    """Table 2: tarifvolumetriques2 - Tranches de tarifs volumétriques"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tarifvolumetrique = models.ForeignKey(TarifVolumetrique, on_delete=models.CASCADE, related_name='tranches')
    tranchesuperieur = models.IntegerField(verbose_name="Tranche supérieure (m³)")
    tarif = models.IntegerField(verbose_name="Tarif (Ar/m³)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tarifvolumetriques2'
        verbose_name = 'Tranche de tarif volumétrique'
        verbose_name_plural = 'Tranches de tarifs volumétriques'
        ordering = ['tarifvolumetrique', 'tranchesuperieur']
        unique_together = ['tarifvolumetrique', 'tranchesuperieur']

    def __str__(self):
        return f"{self.tarifvolumetrique} - Jusqu'à {self.tranchesuperieur}m³ : {self.tarif} Ar/m³"


class ModaliteGestion(models.Model):
    """Modèle pour les modalités de gestion des ouvrages"""
    TYPE_GESTION_CHOICES = [
        ('privee', 'Privée'),
        ('comite_eau', 'Comité eau'),
        ('pas_de_gestion', 'Pas de gestion'),
    ]

    STATUT_CHOICES = [
        ('actif', 'Actif'),
        ('suspendu', 'Suspendu'),
        ('resilie', 'Résilié'),
    ]

    MODALITE_PAIEMENT_CHOICES = [
        ('forfaitaire', 'Forfaitaire'),
        ('au_volume', 'Au volume'),
        ('cotisation_annuelle', 'Cotisation annuelle'),
        ('mixte', 'Mixte'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ouvrage = models.ForeignKey('organization.Ouvrage', on_delete=models.CASCADE, related_name='modalites_gestion')
    type_gestion = models.CharField(max_length=50, choices=TYPE_GESTION_CHOICES, verbose_name="Type de gestion")

    # Gestionnaire comme ForeignKey vers Organisation
    gestionnaire = models.ForeignKey('organization.Organisation', on_delete=models.SET_NULL, null=True, blank=True, related_name='modalites_gerees', verbose_name="Organisation gestionnaire")

    # Employé responsable de la gestion
    employe = models.ForeignKey(Employe, on_delete=models.SET_NULL, null=True, blank=True, related_name='modalites_gestion', verbose_name="Employé responsable")

    # Dates de gestion
    date_debut = models.DateField(verbose_name="Date de début")
    date_fin = models.DateField(null=True, blank=True, verbose_name="Date de fin")
    explication_fin = models.TextField(null=True, blank=True, verbose_name="Explication de fin")

    # Modalité de paiement
    modalitepaiement = models.CharField(max_length=50, choices=MODALITE_PAIEMENT_CHOICES, null=True, blank=True, verbose_name="Modalité de paiement")

    statut = models.CharField(max_length=50, choices=STATUT_CHOICES, default='actif', verbose_name="Statut")
    contrat_file = models.FileField(upload_to='contrats_gestion/', null=True, blank=True, verbose_name="Fichier contrat")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'modalitesgestions'
        verbose_name = 'Modalité de gestion'
        verbose_name_plural = 'Modalités de gestion'
        ordering = ['ouvrage', '-date_debut']

    def __str__(self):
        return f"{self.ouvrage.nom_ouvrage} - {self.get_type_gestion_display()}"

    def clean(self):
        super().clean()
        if self.gestionnaire and not self.gestionnaire.is_gestionnaire:
            raise ValidationError({
                'gestionnaire': "Seules les organisations de type Gestionnaire sont autorisées."
            })

    @staticmethod
    def _normalize_date_value(value):
        from django.utils.dateparse import parse_date
        import datetime as dt

        if value in (None, ''):
            return None
        if isinstance(value, dt.datetime):
            return value.date()
        if isinstance(value, dt.date):
            return value
        if not isinstance(value, str):
            value = str(value)

        parsed = parse_date(value)
        if parsed:
            return parsed

        for fmt in ('%d/%m/%Y', '%Y-%m-%d'):
            try:
                return dt.datetime.strptime(value, fmt).date()
            except ValueError:
                continue

        return None

    def save(self, *args, **kwargs):
        """Calcule automatiquement le statut selon date_fin"""
        import datetime as dt

        self.date_debut = self._normalize_date_value(self.date_debut)
        self.date_fin = self._normalize_date_value(self.date_fin)
        self.explication_fin = (self.explication_fin or '').strip() or None

        if self.date_fin is None:
            self.statut = 'actif'
            self.explication_fin = None
        else:
            from django.utils import timezone
            if isinstance(self.date_fin, dt.date) and self.date_fin < timezone.now().date():
                self.statut = 'resilie'
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def is_active_now(self):
        """Vérifie si la modalité de gestion est actuellement active"""
        from django.utils import timezone
        today = timezone.now().date()
        date_debut = self._normalize_date_value(self.date_debut)
        date_fin = self._normalize_date_value(self.date_fin)
        if not date_debut:
            return False
        return (self.statut == 'actif' and
                date_debut <= today and
                (date_fin is None or date_fin >= today))


class PointEauControle(models.Model):
    """Modèle pour associer des points de contrôle spécifiques aux points d'eau"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    point_eau = models.ForeignKey(PointEau, on_delete=models.CASCADE, related_name='points_controle')
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
        db_table = 'point_eau_controles'
        verbose_name = 'Point de contrôle pour point d\'eau'
        verbose_name_plural = 'Points de contrôle pour points d\'eau'
        ordering = ['point_eau', 'ordre']
        unique_together = ['point_eau', 'point_de_controle']

    def __str__(self):
        return f"{self.point_eau.nomabonne} - {self.point_de_controle.nom}"

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


class PaiementForfaitaire(models.Model):
    """
    Modèle pour les paiements forfaitaires des points d'eau

    Un paiement forfaitaire permet d'ouvrir un point d'eau pour une durée déterminée.
    Règle: 1 quantité = 3 mois d'ouverture
    Exemple: Quantité=2 → 6 mois d'ouverture (2 x 3 mois)

    Similaire aux relevés mais avec montant fixe basé sur la quantité, pas sur la consommation.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Relation avec le point d'eau (doit avoir modalité forfaitaire)
    point_eau = models.ForeignKey(
        'billing.PointEau',
        on_delete=models.CASCADE,
        related_name='paiements_forfaitaires',
        verbose_name="Point d'eau",
        help_text="Point d'eau avec modalité de paiement forfaitaire"
    )

    planning = models.ForeignKey(
        'planning.Planning',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='paiements_forfaitaires',
        verbose_name="Planning"
    )

    # Date de la facture
    date_facture = models.DateField(
        verbose_name="Date de la facture",
        help_text="Date d'émission de la facture de paiement forfaitaire"
    )

    # Quantité (1 quantité = 3 mois d'ouverture)
    quantite = models.IntegerField(
        verbose_name="Quantité",
        help_text="Nombre de périodes de 3 mois (ex: 2 = 6 mois d'ouverture)"
    )

    # Prix unitaire (= TarifForfaitaire du point d'eau)
    prix_unitaire = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Prix unitaire",
        help_text="Tarif forfaitaire pour 3 mois (copié depuis PointEau.tarifforfaitaire)"
    )

    # Montant total (calculé: quantité x prix_unitaire)
    montant = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Montant total",
        help_text="Montant total = Quantité × Prix unitaire"
    )

    # Statut de paiement
    paye = models.BooleanField(
        default=False,
        verbose_name="Payé",
        help_text="Indique si le paiement a été effectué"
    )

    traite_en_avance = models.BooleanField(
        default=False,
        verbose_name="Traité en avance",
        help_text="Indique si la ligne a été sortie de la file des avances"
    )

    # Date de paiement
    date_paiement = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date de paiement",
        help_text="Date à laquelle le paiement a été effectué"
    )

    # Encaissement par la caissière (étape 1, avant la saisie compta et le pointage)
    date_encaissement = models.DateField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="Date d'encaissement",
        help_text="Date à laquelle la caissière a encaissé ce paiement (vide = pas encore encaissé)"
    )

    encaisse_par = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='paiements_forfaitaires_encaisses',
        verbose_name="Encaissé par"
    )

    # Champs DiameX pour suivi comptable
    numeroDiameX = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="Numéro DiameX",
        help_text="Numéro de pièce DiameX - indique que le paiement est enregistré en comptabilité"
    )

    baseDiameX = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="Base DiameX",
        help_text="Code base DiameX"
    )

    # Dates de validité calculées automatiquement
    date_debut_validite = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date de début de validité",
        help_text="Date de début de la période d'ouverture du point d'eau"
    )

    date_fin_validite = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date de fin de validité",
        help_text="Date de fin de la période d'ouverture (début + quantité × 3 mois)"
    )

    # Remarque optionnelle
    remarque = models.TextField(
        null=True,
        blank=True,
        verbose_name="Remarque",
        help_text="Remarque ou commentaire concernant ce paiement"
    )

    # Audit
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Modifié le")

    class Meta:
        db_table = 'paiements_forfaitaires'
        verbose_name = "Paiement forfaitaire"
        verbose_name_plural = "Paiements forfaitaires"
        ordering = ['-date_facture', '-created_at']
        indexes = [
            models.Index(fields=['point_eau', 'date_facture']),
            models.Index(fields=['paye']),
            models.Index(fields=['numeroDiameX']),
            models.Index(fields=['date_debut_validite', 'date_fin_validite']),
        ]

    def __str__(self):
        return f"Paiement {self.point_eau.nom if self.point_eau else 'N/A'} - {self.date_facture} - {self.montant} Ar"

    @property
    def duree_mois(self):
        """Durée totale en mois (quantité × 3)"""
        return self.quantite * 3

    @property
    def est_pointe_complet(self):
        """Le paiement n'est pointe que si le couple DiameX est complet."""
        return bool(
            str(self.numeroDiameX or '').strip()
            and str(self.baseDiameX or '').strip()
        )

    @property
    def est_paye(self):
        """Indique si le paiement est payé (via numeroDiameX ou flag paye)"""
        return self.est_pointe_complet

    @property
    def est_encaisse(self):
        """Encaissé par la caissière (pointé ou non). Un paiement pointé compte
        aussi comme encaissé : le pointage confirme l'encaissement."""
        return bool(self.date_encaissement) or self.est_pointe_complet

    @property
    def est_encaisse_non_pointe(self):
        """Encaissé mais pas encore confirmé par le pointage compta."""
        return bool(self.date_encaissement) and not self.est_pointe_complet

    @staticmethod
    def _as_date(value):
        if isinstance(value, datetime):
            return value.date()
        return value

    @property
    def effective_payment_date(self):
        if self.date_paiement:
            return self.date_paiement
        if self.est_paye:
            if self.date_facture:
                return self.date_facture
            return timezone.localdate()
        return None

    @property
    def has_cut_status_anomaly(self):
        if not self.est_paye or not self.point_eau_id:
            return False

        point_eau = getattr(self, 'point_eau', None)
        if point_eau is None:
            point_eau = PointEau.objects.filter(id=self.point_eau_id).only('datearretbranchement').first()

        date_arret = self._as_date(getattr(point_eau, 'datearretbranchement', None))
        date_paiement = self.effective_payment_date
        return bool(date_arret and date_paiement and date_paiement >= date_arret)

    def _auto_restore_water_if_needed(self):
        if not self.point_eau_id:
            return False

        point_eau = PointEau.objects.filter(id=self.point_eau_id).first()
        if not point_eau:
            return False

        date_arret = self._as_date(point_eau.datearretbranchement)
        date_paiement = self.effective_payment_date
        if not date_arret or not date_paiement or date_paiement < date_arret:
            return False

        if CoupureEau.objects.filter(
            point_eau=point_eau,
            type_evenement='remise',
            date_evenement=date_paiement
        ).exists():
            return False

        CoupureEau.objects.create(
            point_eau=point_eau,
            type_evenement='remise',
            date_evenement=date_paiement,
            raison='autre',
            notes=(
                "Remise en eau automatique suite au paiement forfaitaire "
                f"{self.id} du {date_paiement.strftime('%d/%m/%Y')}"
            ),
        )
        return True

    @property
    def est_actif(self):
        """Indique si la période de validité est active (en cours)"""
        if not self.date_debut_validite or not self.date_fin_validite:
            return False

        from django.utils import timezone
        aujourd_hui = timezone.now().date()
        return self.date_debut_validite <= aujourd_hui <= self.date_fin_validite

    @property
    def jours_restants(self):
        """Nombre de jours restants avant expiration"""
        if not self.date_fin_validite:
            return None

        from django.utils import timezone
        aujourd_hui = timezone.now().date()

        if aujourd_hui > self.date_fin_validite:
            return 0  # Expiré

        delta = self.date_fin_validite - aujourd_hui
        return delta.days

    def save(self, *args, **kwargs):
        """Override save pour calculer automatiquement le montant et les dates"""
        update_fields = kwargs.get('update_fields')
        if update_fields is not None:
            update_fields = set(update_fields)

        if self.planning_id and self.point_eau_id:
            planning_obj = getattr(self, 'planning', None)
            point_eau_obj = getattr(self, 'point_eau', None)

            planning_ouvrage_id = getattr(planning_obj, 'ouvrage_id', None)
            point_eau_ouvrage_id = getattr(point_eau_obj, 'ouvrage_id', None)

            if planning_ouvrage_id is None:
                from apps.planning.models import Planning
                planning_ouvrage_id = Planning.objects.filter(
                    id=self.planning_id
                ).values_list('ouvrage_id', flat=True).first()

            if point_eau_ouvrage_id is None:
                point_eau_ouvrage_id = PointEau.objects.filter(
                    id=self.point_eau_id
                ).values_list('ouvrage_id', flat=True).first()

            if (
                planning_ouvrage_id
                and point_eau_ouvrage_id
                and planning_ouvrage_id != point_eau_ouvrage_id
            ):
                raise ValidationError(
                    "Incoherence paiement forfaitaire: le planning et le point d'eau "
                    "doivent appartenir au meme ouvrage."
                )

        cleaned_numero_diamex = str(self.numeroDiameX or '').strip()
        cleaned_base_diamex = str(self.baseDiameX or '').strip()
        normalized_numero_diamex = cleaned_numero_diamex or None
        normalized_base_diamex = cleaned_base_diamex or None

        if self.numeroDiameX != normalized_numero_diamex:
            self.numeroDiameX = normalized_numero_diamex
            if update_fields is not None:
                update_fields.add('numeroDiameX')

        if self.baseDiameX != normalized_base_diamex:
            self.baseDiameX = normalized_base_diamex
            if update_fields is not None:
                update_fields.add('baseDiameX')

        # Calculer le montant si non défini
        if self.quantite and self.prix_unitaire:
            self.montant = self.quantite * self.prix_unitaire
            if update_fields is not None:
                update_fields.add('montant')

        is_paid_now = bool(cleaned_numero_diamex and cleaned_base_diamex)
        if self.paye != is_paid_now:
            self.paye = is_paid_now
            if update_fields is not None:
                update_fields.add('paye')

        if is_paid_now and not self.date_paiement:
            self.date_paiement = self.date_facture or timezone.localdate()
            if update_fields is not None:
                update_fields.add('date_paiement')

        if not is_paid_now and self.date_paiement is not None:
            self.date_paiement = None
            if update_fields is not None:
                update_fields.add('date_paiement')

        # Calculer les dates de validité si paiement effectué et non déjà calculées
        if is_paid_now and not self.date_debut_validite and self.date_paiement:
            from dateutil.relativedelta import relativedelta
            self.date_debut_validite = self.date_paiement
            self.date_fin_validite = self.date_paiement + relativedelta(months=self.duree_mois)
            if update_fields is not None:
                update_fields.update(['date_debut_validite', 'date_fin_validite'])

        if not is_paid_now and (self.date_debut_validite is not None or self.date_fin_validite is not None):
            self.date_debut_validite = None
            self.date_fin_validite = None
            if update_fields is not None:
                update_fields.update(['date_debut_validite', 'date_fin_validite'])

        if update_fields is not None:
            kwargs['update_fields'] = list(update_fields)

        super().save(*args, **kwargs)
        self._auto_remise_effectuee = bool(is_paid_now and self._auto_restore_water_if_needed())


class CoupureEau(models.Model):
    """
    Modèle pour gérer les coupures et remises en eau des points d'eau

    Une coupure permet de marquer une période où le point d'eau est fermé,
    et donc aucune facturation ne doit être faite pendant cette période.
    """

    TYPE_COUPURE_CHOICES = [
        ('coupure', 'Coupure d\'eau'),
        ('remise', 'Remise en eau'),
    ]

    RAISON_CHOICES = [
        ('non_paiement', 'Non paiement'),
        ('travaux', 'Travaux'),
        ('maintenance', 'Maintenance'),
        ('saison', 'Fermeture saisonnière'),
        ('autre', 'Autre'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Relation avec le point d'eau
    point_eau = models.ForeignKey(
        'billing.PointEau',
        on_delete=models.CASCADE,
        related_name='coupures_eau',
        verbose_name="Point d'eau"
    )

    # Type d'événement
    type_evenement = models.CharField(
        max_length=10,
        choices=TYPE_COUPURE_CHOICES,
        verbose_name="Type d'événement",
        help_text="Coupure ou remise en eau"
    )

    # Date de l'événement
    date_evenement = models.DateField(
        verbose_name="Date de l'événement",
        help_text="Date de la coupure ou de la remise en eau"
    )

    # Raison
    raison = models.CharField(
        max_length=20,
        choices=RAISON_CHOICES,
        null=True,
        blank=True,
        verbose_name="Raison",
        help_text="Raison de la coupure/remise"
    )

    # Notes
    notes = models.TextField(
        null=True,
        blank=True,
        verbose_name="Notes",
        help_text="Informations complémentaires"
    )

    # Créateur
    cree_par = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='coupures_creees',
        verbose_name="Créé par"
    )

    # Dates de suivi
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'coupures_eau'
        verbose_name = 'Coupure d\'eau'
        verbose_name_plural = 'Coupures d\'eau'
        ordering = ['-date_evenement']
        indexes = [
            models.Index(fields=['point_eau', 'date_evenement']),
            models.Index(fields=['type_evenement']),
        ]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.sync_point_eau_status()

    def delete(self, *args, **kwargs):
        point_eau = self.point_eau
        super().delete(*args, **kwargs)
        # On doit recréer une instance temporaire ou utiliser une méthode de classe pour resynchroniser
        CoupureEau.sync_specific_point_eau(point_eau)

    def sync_point_eau_status(self):
        """Met à jour le champ datearretbranchement du PointEau associé"""
        CoupureEau.sync_specific_point_eau(self.point_eau)

    @classmethod
    def sync_specific_point_eau(cls, point_eau):
        """Logique de synchronisation pour un point d'eau donné"""
        # Récupérer le dernier événement par date
        dernier_evenement = cls.objects.filter(point_eau=point_eau).order_by('-date_evenement', '-created_at').first()

        update_fields = ['datearretbranchement']
        if dernier_evenement and dernier_evenement.type_evenement == 'coupure':
            # Si le dernier événement est une coupure, on met la date d'arrêt
            point_eau.datearretbranchement = dernier_evenement.date_evenement
        else:
            # Sinon (remise ou aucun événement), on vide la date d'arrêt
            point_eau.datearretbranchement = None

        # Règle métier: un point d'eau coupé depuis plus d'un an sans remise
        # ne doit plus conserver de tarif forfaitaire actif.
        date_arret = point_eau.datearretbranchement
        if isinstance(date_arret, datetime):
            date_arret = date_arret.date()

        cutoff_date = timezone.localdate() - timedelta(days=365)
        modalite_forfaitaire_active = ModaliteGestion.objects.filter(
            ouvrage_id=point_eau.ouvrage_id,
            modalitepaiement__in=['forfaitaire', 'mixte'],
            statut='actif'
        ).filter(
            models.Q(date_debut__isnull=True) | models.Q(date_debut__lte=timezone.localdate())
        ).filter(
            models.Q(date_fin__isnull=True) | models.Q(date_fin__gte=timezone.localdate())
        ).exists()

        if (
            date_arret
            and date_arret <= cutoff_date
            and point_eau.tarifforfaitaire is not None
            and modalite_forfaitaire_active
        ):
            point_eau.tarifforfaitaire = None
            update_fields.append('tarifforfaitaire')

        # On utilise save() simple pour garder la cohérence des champs portés
        point_eau.save(update_fields=update_fields)


class DepenseService(models.Model):
    """Factures de dépenses liées à des services (hors planningdetails)."""

    STATUT_BROUILLON = 'brouillon'
    STATUT_ATTENTE_SIGNATURE = 'attente_signature'
    STATUT_VALIDE = 'valide'

    STATUTS_CHOICES = [
        (STATUT_BROUILLON, 'Brouillon'),
        (STATUT_ATTENTE_SIGNATURE, 'En attente 2e signature'),
        (STATUT_VALIDE, 'Validé'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    date_facture = models.DateField(
        verbose_name="Date de la facture",
        help_text="Date de la dépense / facture"
    )
    fournisseur = models.ForeignKey(
        Fournisseur,
        on_delete=models.PROTECT,
        related_name='depenses_services',
        verbose_name="Fournisseur"
    )
    designation = models.TextField(verbose_name="Désignation / Motif")
    unite = models.CharField(max_length=120, verbose_name="Unité")
    prix_unitaire = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="Prix unitaire")
    montant = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        verbose_name="Montant",
        help_text="Quantité / base de calcul selon l'unité"
    )
    total = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="Total")
    total_lettres = models.CharField(max_length=500, blank=True, verbose_name="Total en toutes lettres")
    statut = models.CharField(
        max_length=20,
        choices=STATUTS_CHOICES,
        default=STATUT_BROUILLON,
        verbose_name="Statut"
    )

    signataire_1 = models.CharField(max_length=255, blank=True, verbose_name="Signataire 1")
    date_signature_1 = models.DateField(null=True, blank=True, verbose_name="Date signature 1")
    signataire_2 = models.CharField(max_length=255, blank=True, verbose_name="Signataire 2")
    date_signature_2 = models.DateField(null=True, blank=True, verbose_name="Date signature 2")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Mis à jour le")

    class Meta:
        db_table = 'depenses_services'
        verbose_name = 'Dépense de service'
        verbose_name_plural = 'Dépenses de services'
        ordering = ['-date_facture', '-created_at']
        indexes = [
            models.Index(fields=['fournisseur', 'date_facture']),
            models.Index(fields=['statut']),
        ]

    def __str__(self):
        return f"{self.fournisseur.nom_fournisseur} - {self.date_facture} - {self.total}"

    @staticmethod
    def convertir_montant_en_lettres(valeur):
        try:
            if not valeur:
                return ""

            montant_int = int(Decimal(valeur))

            try:
                from num2words import num2words
                return f"{num2words(montant_int, lang='fr').upper()} ARIARY"
            except Exception:
                return f"{montant_int:,} ARIARY".replace(',', ' ')
        except Exception:
            return ""

    @staticmethod
    def _safe_decimal(value):
        if value in (None, ''):
            return Decimal('0')
        return Decimal(str(value))

    def save(self, *args, **kwargs):
        prix = self._safe_decimal(self.prix_unitaire).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        montant = self._safe_decimal(self.montant).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        self.prix_unitaire = prix
        self.montant = montant
        if self.pk:
            lignes_qs = self.lignes.all()
            if lignes_qs.exists():
                self.total = sum(
                    (ligne.total or Decimal('0')) for ligne in lignes_qs
                ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            else:
                self.total = (prix * montant).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        else:
            self.total = (prix * montant).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        self.total_lettres = self.convertir_montant_en_lettres(self.total)
        super().save(*args, **kwargs)

    def recalculate_from_lignes(self):
        lignes = list(self.lignes.all())
        if not lignes:
            return

        first_line = lignes[0]
        self.designation = first_line.designation
        self.unite = first_line.unite
        self.prix_unitaire = first_line.prix_unitaire
        self.montant = first_line.montant
        total = sum((ligne.total or Decimal('0')) for ligne in lignes)
        self.total = Decimal(total).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        self.total_lettres = self.convertir_montant_en_lettres(self.total)


class DepenseServiceLigne(models.Model):
    """Lignes détaillées d'une facture de dépense de service."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    depense_service = models.ForeignKey(
        DepenseService,
        on_delete=models.CASCADE,
        related_name='lignes',
        verbose_name="Dépense de service"
    )
    designation = models.TextField(verbose_name="Désignation")
    unite = models.CharField(max_length=120, verbose_name="Unité")
    prix_unitaire = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="Prix unitaire")
    montant = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        verbose_name="Montant",
        help_text="Quantité / base de calcul selon l'unité"
    )
    total = models.DecimalField(max_digits=18, decimal_places=2, default=0, verbose_name="Total")
    ordre = models.PositiveIntegerField(default=0, verbose_name="Ordre")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Mis à jour le")

    class Meta:
        db_table = 'depenses_services_lignes'
        verbose_name = 'Ligne de dépense de service'
        verbose_name_plural = 'Lignes de dépenses de services'
        ordering = ['ordre', 'created_at']
        indexes = [
            models.Index(fields=['depense_service', 'ordre']),
        ]

    def __str__(self):
        return f"{self.designation} - {self.total}"

    @staticmethod
    def _safe_decimal(value):
        if value in (None, ''):
            return Decimal('0')
        return Decimal(str(value))

    def save(self, *args, **kwargs):
        prix = self._safe_decimal(self.prix_unitaire).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        montant = self._safe_decimal(self.montant).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        self.prix_unitaire = prix
        self.montant = montant
        self.total = (prix * montant).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        super().save(*args, **kwargs)


class FraisTransfertMvola(models.Model):
    """Barème des frais de transfert prélevés par MVola selon le montant envoyé"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    montant_min = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Montant minimum (Ar)")
    montant_max = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Montant maximum (Ar)")
    frais = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Frais de transfert (Ar)")
    actif = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'frais_transfert_mvola'
        verbose_name = 'Frais de transfert MVola'
        verbose_name_plural = 'Frais de transfert MVola'
        ordering = ['montant_min']

    def __str__(self):
        return f"{self.montant_min} - {self.montant_max} Ar -> {self.frais} Ar"

    def clean(self):
        if self.montant_min is not None and self.montant_max is not None and self.montant_min > self.montant_max:
            raise ValidationError("Le montant minimum doit être inférieur ou égal au montant maximum")

    @staticmethod
    def calculer_frais(montant):
        """Retourne le frais applicable pour un montant donné, ou None si aucun palier ne correspond"""
        if montant is None:
            return None
        montant_decimal = Decimal(str(montant))
        palier = FraisTransfertMvola.objects.filter(
            actif=True,
            montant_min__lte=montant_decimal,
            montant_max__gte=montant_decimal
        ).order_by('montant_min').first()
        return palier.frais if palier else None
        super().save(*args, **kwargs)


# Journal des SMS de rappel de paiement (voir apps/billing/sms/)
from .models_sms import SmsLog  # noqa: E402,F401
