from django.db import models
import uuid

# Import des modèles de demandes de fonds
from .models_demandes_fonds import Budget, LigneBudget, DemandeFonds, LigneDemandeFonds

# Import du modèle de comptabilité partie double
from .models_partie_double import EcriturePartieDouble
from .models_pointage import MoisPointage, ObjetPointage, DecisionPointage

# Cache / journal des extractions IA de justificatifs (Phase 2 - ai_prefill)
from .ai_prefill.models_ai_prefill import ScanExtraction

# Regles de saisie guidee par compte (composition de la description)
from .models_regles_saisie import RegleSaisieCompte, CompteFournisseurAutorise


class DiameXTemporaire(models.Model):
    """
    Table temporaire pour stocker les transactions en attente d'export vers DiameX.
    Permet de valider/rejeter les transactions avant l'export final.
    """
    id = models.AutoField(primary_key=True)

    # Lien vers le planning detail source (si applicable)
    planning_detail = models.ForeignKey(
        'planning.PlanningDetail',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions_temporaires',
        verbose_name="Détail planning source"
    )

    # Lien vers l'achat source (pour les dépenses liées aux achats)
    purchase = models.ForeignKey(
        'inventory.Purchase',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions_temporaires',
        verbose_name="Achat source"
    )

    # Lien vers le salaire source (pour les dépenses de salaires)
    salaire = models.ForeignKey(
        'employees.Salaire',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions_temporaires',
        verbose_name="Salaire source"
    )

    # Lien vers le paiement IRSA source (pour les dépenses IRSA)
    paiement_irsa = models.ForeignKey(
        'employees.PaiementIRSA',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions_temporaires',
        verbose_name="Paiement IRSA source"
    )

    # Lien vers le paiement CNaPS/FMFP source (pour les charges sociales)
    paiement_cnaps_fmfp = models.ForeignKey(
        'employees.PaiementCNaPSFMFP',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions_temporaires',
        verbose_name="Paiement CNaPS/FMFP source"
    )

    # Lien vers le paiement Mutuelle Santé source (pour les charges de mutuelle)
    paiement_mutuelle_sante = models.ForeignKey(
        'employees.PaiementMutuelleSante',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions_temporaires',
        verbose_name="Paiement Mutuelle Santé source"
    )

    # Lien vers le paiement forfaitaire source (pour les recettes de paiements forfaitaires)
    paiement_forfaitaire = models.ForeignKey(
        'billing.PaiementForfaitaire',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions_temporaires',
        verbose_name="Paiement forfaitaire source"
    )

    # Liste des IDs de paiements forfaitaires pour encaissement groupé (JSON)
    paiements_forfaitaires_ids = models.JSONField(
        null=True,
        blank=True,
        verbose_name="IDs des paiements forfaitaires groupés",
        help_text="Pour encaissement groupé : liste des UUIDs des paiements inclus dans cette transaction"
    )

    # Type de transaction
    TYPE_CHOICES = [
        ('avance', 'Avance'),
        ('depense', 'Dépense'),
        ('recette', 'Recette'),
        ('transfert', 'Transfert'),
    ]
    type_transaction = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default='avance',
        verbose_name="Type de transaction"
    )

    # Champs DiameX (similaires à BaseDiameX)
    journal_code = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="Code journal"
    )

    date_m = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date mouvement"
    )

    rec = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="Numéro de reçu"
    )

    date_rec = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date reçu"
    )

    description = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Description"
    )

    montant_in = models.FloatField(
        default=0.0,
        verbose_name="Entrée (In)"
    )

    montant_out = models.FloatField(
        default=0.0,
        verbose_name="Sortie (Out)"
    )

    compte_code = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name="Code compte"
    )

    pers = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="Personne"
    )

    detail = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="Détail"
    )

    info = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Information"
    )

    scan = models.URLField(
        max_length=500,
        null=True,
        blank=True,
        verbose_name="Lien scan"
    )

    prog = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="Programme"
    )

    id_diamex = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="ID DiameX",
        help_text="ID retourné par Access après export"
    )

    activ = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="ACTIV (Volet/Base)",
        help_text="Champ ACTIV distinct de Prog - rempli avec Base.volet sauf pour 00PERS"
    )

    fin = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="Financement",
        help_text="Colonne Fin/Financement DiameX (ex: 'RL Activités')"
    )

    # Fournisseur (pour les transactions liées à des achats)
    fournisseur = models.ForeignKey(
        'billing.Fournisseur',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions_temporaires',
        verbose_name="Fournisseur"
    )

    # Statut de validation
    STATUS_CHOICES = [
        ('en_attente', 'En attente'),
        ('valide', 'Validé'),
        ('rejete', 'Rejeté'),
        ('exporte', 'Exporté'),
    ]
    statut = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='en_attente',
        verbose_name="Statut",
        db_index=True
    )

    # Métadonnées
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de création"
    )

    created_by = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions_temporaires_creees',
        verbose_name="Créé par"
    )

    validated_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Date de validation/rejet"
    )

    validated_by = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions_temporaires_validees',
        verbose_name="Validé/Rejeté par"
    )

    export_batch = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name="Lot d'export",
        help_text="Identifiant du lot d'export DiameX"
    )

    notes = models.TextField(
        null=True,
        blank=True,
        verbose_name="Notes"
    )

    class Meta:
        db_table = 'diamex_temporaire'
        verbose_name = 'Transaction DiameX temporaire'
        verbose_name_plural = 'Transactions DiameX temporaires'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['statut', 'type_transaction']),
            models.Index(fields=['date_m']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.type_transaction} - {self.description or 'Sans description'} ({self.statut})"


class BaseDiameX(models.Model):
    """
    Modèle pour stocker les données comptables importées depuis les fichiers Access DiameX.
    Les données proviennent de 3 fichiers Access différents (une base par organisation).
    """
    id = models.AutoField(primary_key=True)
    
    # ID original du fichier Access
    id_access = models.IntegerField(
        verbose_name="ID Access",
        help_text="ID original dans le fichier Access"
    )
    
    # Fichier source (pour identifier d'où vient l'enregistrement)
    fichier_source = models.CharField(
        max_length=255,
        verbose_name="Fichier source",
        help_text="Nom du fichier Access d'origine"
    )
    
    # Journal comptable
    journal = models.ForeignKey(
        'organization.Journal',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='diamex_entries',
        verbose_name="Journal",
        help_text="Journal comptable (relié via code)"
    )
    journal_code = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="Code journal (Access)",
        help_text="Code du journal tel qu'importé depuis Access"
    )
    
    # Dates
    date_m = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date mouvement",
        db_index=True
    )
    
    # Numéro de reçu
    rec = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="Numéro de reçu"
    )
    
    date_rec = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date reçu"
    )
    
    # Description
    description = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Description"
    )
    
    # Montants
    montant_in = models.FloatField(
        default=0.0,
        verbose_name="Entrée (In)",
        help_text="Montant entrant"
    )
    
    montant_out = models.FloatField(
        default=0.0,
        verbose_name="Sortie (Out)",
        help_text="Montant sortant"
    )
    
    # CCY = In - Out (calculé)
    @property
    def ccy(self):
        """Calcule CCY = In - Out"""
        return self.montant_in - self.montant_out

    @property
    def financement_attendu(self):
        """Financement configuré sur le compte relié, ou vide si aucun contrôle."""
        return (getattr(self.compte, 'financement', '') or '').strip()

    @property
    def financement_conforme(self):
        """Retourne None sans règle, sinon le résultat du contrôle Fin/compte."""
        attendu = self.financement_attendu
        if not attendu:
            return None
        valeur = ' '.join(str(self.fin or '').split()).casefold()
        attendu_normalise = ' '.join(attendu.split()).casefold()
        return valeur == attendu_normalise
    
    # Compte (catégorie)
    compte = models.ForeignKey(
        'organization.Compte',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='diamex_entries',
        verbose_name="Compte",
        help_text="Compte comptable (relié via code)"
    )
    compte_code = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name="Code compte (Access)",
        help_text="Code du compte tel qu'importé depuis Access"
    )
    
    # Autres champs
    pers = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="Personne"
    )
    
    detail = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="Détail"
    )
    
    info = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Information"
    )
    
    fin = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="Fin"
    )
    
    activ = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="Activité"
    )
    
    scan = models.URLField(
        max_length=500,
        null=True,
        blank=True,
        verbose_name="Lien scan",
        help_text="Lien hypertexte vers le document scanné"
    )

    scan_importe = models.FileField(
        upload_to='diamex_scans/',
        max_length=500,
        null=True,
        blank=True,
        verbose_name="Scan importé",
        help_text="Copie serveur du scan pour consultation web/mobile"
    )
    
    prog = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="Programme"
    )

    fournisseur = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Fournisseur",
        help_text="IDxls ou nom du fournisseur"
    )

    date_input = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date saisie",
        help_text="Date de saisie dans Access"
    )
    
    is_checked = models.BooleanField(
        default=False,
        verbose_name="Vérifié",
        db_column='check'
    )
    
    match = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="Match",
        help_text="ID de rapprochement"
    )
    
    bank_rec = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date rapprochement bancaire"
    )
    
    # Métadonnées d'import
    date_import = models.DateTimeField(
        auto_now=True,
        verbose_name="Date dernier import",
        help_text="Date de la dernière synchronisation depuis Access"
    )

    imported_by = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='imports_diamex',
        verbose_name="Importé par",
        help_text="Employé qui a importé cette ligne"
    )
    
    class Meta:
        db_table = 'basediamex'
        verbose_name = 'Entrée DiameX'
        verbose_name_plural = 'Entrées DiameX'
        ordering = ['-date_m', '-id']
        indexes = [
            models.Index(fields=['fichier_source', 'id_access']),
            models.Index(fields=['date_m']),
            models.Index(fields=['journal_code']),
            models.Index(fields=['compte_code']),
            # Index pour les statistiques (optimisation page import)
            models.Index(fields=['imported_by', 'date_import']),
            models.Index(fields=['imported_by', 'fichier_source']),
            models.Index(fields=['date_import']),
        ]
        # Contrainte d'unicité : un ID Access par fichier source
        unique_together = [['fichier_source', 'id_access']]
    
    def get_categorie_parente(self):
        """
        Détermine la catégorie parente basée sur le compte_code et le libellé
        """
        compte = self.compte_code or ''
        description = (self.description or '').upper()
        info = (self.info or '').upper()
        libelle = description + ' ' + info

        # Transferts 00BOOK (généralement pas de problème)
        if compte.startswith('00BOOK'):
            return 'Transferts 00BOOK'
        # Transferts 00FND1 sans EDF (transferts inter-fichiers)
        elif compte.startswith('00FND1') and 'EDF' not in libelle:
            return 'Transferts 00FND1'

        # EDF: 00FND1 avec EDF ou 00FND2
        elif (compte.startswith('00FND1') and 'EDF' in libelle) or compte.startswith('00FND2'):
            return 'EDF'

        # Compte de tiers: 00PERS
        elif compte.startswith('00PERS'):
            return 'Compte de tiers'

        # Acquisition: commence par 218
        elif compte.startswith('218'):
            return 'Acquisition'

        # Matériaux: commence par 601
        elif compte.startswith('601'):
            return 'Matériaux'

        # Fournitures: commence par 602
        elif compte.startswith('602'):
            return 'Fournitures'

        # Équipement: commence par 605
        elif compte.startswith('605'):
            return 'Équipement'

        # Carburant: 606
        elif compte.startswith('606'):
            return 'Carburant'

        # Fonctionnement: 608, 613, 614, 618, 622, 623, 626, 627, 654
        elif compte.startswith(('608', '613', '614', '618', '622', '623', '626', '627', '654')):
            return 'Fonctionnement'

        # Entretien véhicules: 615, 616
        elif compte.startswith(('615', '616')):
            return 'Entretien véhicules'

        # Main d'œuvre: 621
        elif compte.startswith('621'):
            return "Main d'œuvre"

        # Indemnité: 625
        elif compte.startswith('625'):
            return 'Indemnité'

        # Impôts: 631, 635, 695
        elif compte.startswith(('631', '635', '695')):
            return 'Impôts'

        # Salaires: 641
        elif compte.startswith('641'):
            return 'Salaires'

        # Charges salariales: 646
        elif compte.startswith('646'):
            return 'Charges salariales'

        # Autres recettes: codes spécifiques
        elif compte in ['707101', '707201', '748100', '748220', '748230', '748302', '748304', '761001']:
            return 'Autres recettes'

        # Vente eau au volume: 707401
        elif compte == '707401':
            return 'Vente eau au volume'

        # Paiement extension: 748201
        elif compte == '748201':
            return 'Paiement extension'

        # Vente eau au forfait: 748411
        elif compte == '748411':
            return 'Vente eau au forfait'

        # Vente carte sociale: 748415
        elif compte == '748415':
            return 'Vente carte sociale'

        # Autres (non catégorisé)
        else:
            return 'Autres'

    def __str__(self):
        return f"{self.description or 'Sans description'} - {self.date_m or 'Sans date'} ({self.fichier_source})"


class SaisieComptable(models.Model):
    """
    Table de saisie comptable manuelle, separee de BaseDiameX.
    Sert de workflow operateur avec controle des regles de charte.
    """

    STATUS_CHOICES = [
        ('brouillon', 'Brouillon'),
        ('a_corriger', 'A corriger'),
        ('valide', 'Valide'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # References organisationnelles
    base = models.ForeignKey(
        'organization.Base',
        on_delete=models.PROTECT,
        related_name='saisies_comptables',
        verbose_name='Base'
    )
    journal = models.ForeignKey(
        'organization.Journal',
        on_delete=models.PROTECT,
        related_name='saisies_comptables',
        verbose_name='Journal'
    )
    compte = models.ForeignKey(
        'organization.Compte',
        on_delete=models.PROTECT,
        related_name='saisies_comptables',
        verbose_name='Compte'
    )
    compte_code = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name='Code compte snapshot',
        help_text='Code compte copie au moment de la saisie'
    )

    # Champs comptables type DiameX
    date_m = models.DateField(verbose_name='Date mouvement')
    date_rec = models.DateField(null=True, blank=True, verbose_name='Date recu')
    description = models.CharField(max_length=255, verbose_name='Description')
    montant_in = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='Entree (In)')
    montant_out = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='Sortie (Out)')
    pers = models.CharField(max_length=50, null=True, blank=True, verbose_name='Personne')
    detail = models.CharField(max_length=50, null=True, blank=True, verbose_name='Detail')
    info = models.CharField(max_length=255, null=True, blank=True, verbose_name='Information')
    fin = models.CharField(max_length=50, null=True, blank=True, verbose_name='Fin')
    activ = models.CharField(max_length=50, null=True, blank=True, verbose_name='Activite')
    prog = models.CharField(max_length=50, null=True, blank=True, verbose_name='Programme')
    fournisseur = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name='Fournisseur',
        help_text='Nom ou IDxls fournisseur saisi par operateur'
    )

    # Workflow/validation
    statut = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='brouillon',
        db_index=True,
        verbose_name='Statut'
    )
    conforme = models.BooleanField(default=False, verbose_name='Conforme aux regles')
    erreurs_validation = models.JSONField(default=list, blank=True, verbose_name='Erreurs validation')
    avertissements_validation = models.JSONField(default=list, blank=True, verbose_name='Avertissements validation')
    regles_appliquees = models.JSONField(default=list, blank=True, verbose_name='Regles appliquees')

    # Traçabilité
    created_by = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='saisies_comptables_creees',
        verbose_name='Cree par'
    )
    validated_by = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='saisies_comptables_validees',
        verbose_name='Valide par'
    )
    validated_at = models.DateTimeField(null=True, blank=True, verbose_name='Date validation')
    source_saisie = models.CharField(max_length=30, default='manuel', verbose_name='Source saisie')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Cree le')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Modifie le')

    class Meta:
        db_table = 'saisie_comptable'
        verbose_name = 'Saisie comptable'
        verbose_name_plural = 'Saisies comptables'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['statut', 'date_m']),
            models.Index(fields=['base', 'date_m']),
            models.Index(fields=['compte_code']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.date_m} - {self.compte_code or self.compte_id} - {self.description[:50]}"


class SoldesReels(models.Model):
    """
    Table pour stocker les soldes réels issus des fichiers Access DiameX
    Permet de comparer les soldes calculés avec les soldes déclarés
    """
    id = models.AutoField(primary_key=True)

    # Champs provenant de la table SoldesReels d'Access
    journal = models.CharField(max_length=50, null=True, blank=True, verbose_name="Code journal")
    date_m = models.DateField(null=True, blank=True, verbose_name="Date mouvement (1er du mois)")
    rec = models.IntegerField(null=True, blank=True, verbose_name="Numéro de séquence")
    date_rec = models.DateField(null=True, blank=True, verbose_name="Date d'enregistrement")
    description = models.CharField(max_length=500, null=True, blank=True, verbose_name="Description")
    ccy = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name="Montant solde")
    validation = models.CharField(max_length=100, null=True, blank=True, verbose_name="Statut de validation")
    scan = models.CharField(max_length=500, null=True, blank=True, verbose_name="Chemin du scan")
    date_input = models.DateTimeField(null=True, blank=True, verbose_name="Date de saisie")

    # Métadonnées d'import
    fichier_source = models.CharField(max_length=255, verbose_name="Fichier source")
    chemin_base = models.CharField(max_length=500, null=True, blank=True, verbose_name="Chemin de la base")
    date_import = models.DateTimeField(auto_now_add=True, verbose_name="Date d'import")
    imported_by = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='soldes_reels_importes',
        verbose_name="Importé par"
    )

    class Meta:
        db_table = 'soldes_reels'
        verbose_name = 'Solde réel'
        verbose_name_plural = 'Soldes réels'
        ordering = ['-date_m', '-rec']
        indexes = [
            models.Index(fields=['journal', 'date_m']),
            models.Index(fields=['fichier_source']),
            models.Index(fields=['date_import']),
        ]

    def __str__(self):
        return f"{self.journal} - {self.date_m} (Solde: {self.ccy} Ar) - {self.fichier_source}"


class DocumentationComptable(models.Model):
    """
    Modèle pour gérer la vérification des documents comptables justificatifs.
    Chaque fichier Access doit fournir des documents spécifiques pour chaque mois.
    """

    TYPE_DOCUMENT_CHOICES = [
        ('grand_livre', 'Grand livre par Fin'),
        ('rapprochement_solde', 'Fiche de rapprochement de solde'),
        ('recap_tiers', 'Fiche récapitulatif compte de tiers'),
        ('comptage_caisse', 'Fiche de comptage de caisse (par journal)'),
        ('releve_bancaire', 'Relevé bancaire (par journal)'),
        ('suivi_carburant', 'Fiche de suivi carburant'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Période concernée
    mois = models.IntegerField(
        verbose_name="Mois",
        help_text="Mois concerné (1-12)"
    )
    annee = models.IntegerField(
        verbose_name="Année",
        help_text="Année concernée"
    )

    # Fichier Access concerné
    fichier_source = models.CharField(
        max_length=255,
        verbose_name="Fichier source",
        help_text="Nom du fichier Access concerné"
    )

    # Type de document
    type_document = models.CharField(
        max_length=50,
        choices=TYPE_DOCUMENT_CHOICES,
        verbose_name="Type de document"
    )

    # Valeur de Fin (pour grand_livre) ou Journal (pour comptage_caisse, releve_bancaire)
    valeur_fin = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Valeur Fin",
        help_text="Valeur de la colonne Fin pour les grands livres (peut être vide)"
    )

    journal_code = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="Code journal",
        help_text="Code du journal pour les documents par journal (caisse, banque)"
    )

    # Chemin du document
    chemin_document = models.CharField(
        max_length=1000,
        null=True,
        blank=True,
        verbose_name="Chemin du document",
        help_text="Chemin absolu vers le fichier justificatif (Excel, PDF, etc.)"
    )

    # Statut du document
    statut = models.CharField(
        max_length=20,
        choices=[
            ('present', 'Présent'),
            ('manquant', 'Manquant'),
            ('lien_mort', 'Lien mort'),
        ],
        default='manquant',
        verbose_name="Statut"
    )

    # Métadonnées
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Modifié le")
    created_by = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='documentations_creees',
        verbose_name="Créé par"
    )

    # Notes optionnelles
    notes = models.TextField(
        null=True,
        blank=True,
        verbose_name="Notes",
        help_text="Remarques ou observations"
    )

    class Meta:
        db_table = 'documentation_comptable'
        verbose_name = 'Documentation comptable'
        verbose_name_plural = 'Documentations comptables'
        ordering = ['-annee', '-mois', 'fichier_source', 'type_document']
        indexes = [
            models.Index(fields=['annee', 'mois']),
            models.Index(fields=['fichier_source']),
            models.Index(fields=['statut']),
            models.Index(fields=['type_document']),
        ]
        unique_together = [
            ('annee', 'mois', 'fichier_source', 'type_document', 'valeur_fin', 'journal_code')
        ]

    def __str__(self):
        label = f"{self.get_type_document_display()} - {self.fichier_source} - {self.mois:02d}/{self.annee}"
        if self.valeur_fin:
            label += f" (Fin: {self.valeur_fin})"
        if self.journal_code:
            label += f" (Journal: {self.journal_code})"
        return label

    def verifier_chemin(self):
        """Vérifie si le chemin du document existe et met à jour le statut"""
        import os
        if not self.chemin_document:
            self.statut = 'manquant'
        elif os.path.exists(self.chemin_document):
            self.statut = 'present'
        else:
            self.statut = 'lien_mort'
        return self.statut


class ScanVerificationCache(models.Model):
    """
    Cache pour stocker les résultats de vérification des scans.
    Évite de vérifier l'existence des fichiers à chaque chargement de page.
    """
    id = models.AutoField(primary_key=True)

    # Horodatage de la vérification
    date_verification = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Date de vérification"
    )

    # Fichier source concerné (si filtre appliqué)
    fichier_source = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Fichier source",
        help_text="Si spécifié, cette vérification ne concerne que ce fichier"
    )

    # Résultats de la vérification
    scans_valides_count = models.IntegerField(
        default=0,
        verbose_name="Nombre de scans valides"
    )

    liens_morts_count = models.IntegerField(
        default=0,
        verbose_name="Nombre de liens morts"
    )

    operations_sans_scan_count = models.IntegerField(
        default=0,
        verbose_name="Nombre d'opérations sans scan"
    )

    operations_total_count = models.IntegerField(
        default=0,
        verbose_name="Nombre total d'opérations"
    )

    # IDs des entrées par catégorie (stockés en JSON)
    scans_valides_ids = models.JSONField(
        default=list,
        verbose_name="IDs des entrées avec scans valides"
    )

    liens_morts_ids = models.JSONField(
        default=list,
        verbose_name="IDs des entrées avec liens morts"
    )

    # Statut de la vérification
    statut = models.CharField(
        max_length=20,
        choices=[
            ('en_cours', 'En cours'),
            ('termine', 'Terminé'),
            ('erreur', 'Erreur'),
        ],
        default='en_cours',
        verbose_name="Statut"
    )

    # Message d'erreur si applicable
    message_erreur = models.TextField(
        null=True,
        blank=True,
        verbose_name="Message d'erreur"
    )

    class Meta:
        db_table = 'scan_verification_cache'
        verbose_name = 'Cache vérification scan'
        verbose_name_plural = 'Caches vérifications scans'
        ordering = ['-date_verification']
        indexes = [
            models.Index(fields=['-date_verification']),
            models.Index(fields=['fichier_source']),
            models.Index(fields=['statut']),
        ]

    def __str__(self):
        fichier = self.fichier_source or "Tous"
        return f"Vérification du {self.date_verification.strftime('%d/%m/%Y %H:%M')} - {fichier}"

    @classmethod
    def get_derniere_verification(cls, fichier_source=None):
        """Récupère la dernière vérification terminée pour un fichier donné"""
        query = cls.objects.filter(statut='termine')
        if fichier_source:
            query = query.filter(fichier_source=fichier_source)
        else:
            query = query.filter(fichier_source__isnull=True)

        return query.first()


class ExplicationPaiementForfaitaire(models.Model):
    """
    Stocke les explications narratives des écarts de recouvrement
    pour un ouvrage et une année donnée.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ouvrage = models.ForeignKey(
        'organization.Ouvrage',
        on_delete=models.CASCADE,
        related_name='explications_forfaitaire',
        verbose_name="Ouvrage"
    )
    annee = models.IntegerField(
        verbose_name="Année"
    )
    explication = models.TextField(
        blank=True,
        verbose_name="Explication"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Modifié le")
    created_by = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='explications_forfaitaire_creees',
        verbose_name="Créé par"
    )
    updated_by = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='explications_forfaitaire_modifiees',
        verbose_name="Modifié par"
    )

    class Meta:
        db_table = 'explications_paiements_forfaitaires'
        verbose_name = 'Explication paiement forfaitaire'
        verbose_name_plural = 'Explications paiements forfaitaires'
        unique_together = [('ouvrage', 'annee')]
        ordering = ['-annee', 'ouvrage_id']

    def __str__(self):
        return f"{self.ouvrage_id} - {self.annee}"


class ConfigDeclarationCommunication(models.Model):
    """
    Configuration des natures de déclaration pour la déclaration de communication aux impôts.
    Permet de classer les transactions par nature (Fournitures, Matériaux, Services, etc.)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom = models.CharField(
        max_length=255,
        unique=True,
        verbose_name="Nature de la déclaration",
        help_text="Ex: Fournitures, Matériaux, Services, Travaux, etc."
    )
    ordre = models.IntegerField(
        default=0,
        verbose_name="Ordre d'affichage",
        help_text="Ordre d'apparition dans les listes déroulantes"
    )
    actif = models.BooleanField(
        default=True,
        verbose_name="Actif",
        help_text="Si désactivé, cette nature n'apparaîtra plus dans les choix"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Modifié le")

    class Meta:
        db_table = 'config_declaration_communication'
        verbose_name = 'Nature de déclaration'
        verbose_name_plural = 'Natures de déclaration'
        ordering = ['ordre', 'nom']

    def __str__(self):
        return self.nom
class RemboursementCommune(models.Model):
    """
    Modèle pour stocker les comptes de tiers à rembourser par les communes.
    Ces montants sont déduits du montant total des taxes communales à payer par la commune.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    commune = models.ForeignKey(
        'geography.Commune',
        on_delete=models.CASCADE,
        related_name='remboursements',
        verbose_name="Commune"
    )
    date_remboursement = models.DateField(verbose_name="Date du remboursement")
    designation = models.CharField(max_length=255, verbose_name="Désignation")
    montant = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name="Montant à rembourser"
    )
    
    annee = models.IntegerField(verbose_name="Année concernée", db_index=True)
    
    # Métadonnées
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")
    created_by = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='remboursements_crees',
        verbose_name="Créé par"
    )

    class Meta:
        db_table = 'remboursement_commune'
        verbose_name = 'Remboursement Commune'
        verbose_name_plural = 'Remboursements Communes'
        ordering = ['-date_remboursement']

    def __str__(self):
        return f"{self.commune.nom_commune} - {self.designation} ({self.montant} Ar)"


class InfoPaiementTaxeCommune(models.Model):
    """
    Stocke les informations de paiement pour une commune (mode de paiement, numéro de compte).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    commune = models.ForeignKey('geography.Commune', on_delete=models.CASCADE, related_name='infos_paiement_taxe')
    organisation = models.ForeignKey('organization.Organisation', on_delete=models.CASCADE, null=True, blank=True)
    
    MODE_CHOICES = [
        ('versement', 'Versement avec numéro de compte'),
        ('caisse', 'Paiement direct à la caisse'),
    ]
    mode_paiement = models.CharField(max_length=50, choices=MODE_CHOICES, default='caisse')
    numero_compte = models.CharField(max_length=100, blank=True, null=True, verbose_name="Numéro de compte / Référence")

    class Meta:
        db_table = 'info_paiement_taxe_commune'
        unique_together = ('commune', 'organisation')
        verbose_name = 'Info Paiement Taxe Commune'
        verbose_name_plural = 'Infos Paiement Taxes Communes'


class ImputationRemboursementTaxeCommune(models.Model):
    """
    Montant de remboursement que l'utilisateur souhaite imputer sur une année donnée.
    Le moteur applique ensuite un plafond automatique selon la taxe brute et le solde disponible.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    commune = models.ForeignKey(
        'geography.Commune',
        on_delete=models.CASCADE,
        related_name='imputations_remboursement_taxe',
        verbose_name="Commune"
    )
    organisation = models.ForeignKey(
        'organization.Organisation',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='imputations_remboursement_taxe'
    )
    annee = models.IntegerField(verbose_name="Année", db_index=True)
    montant_impute = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name="Montant à rembourser cette année"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'imputation_remboursement_taxe_commune'
        unique_together = ('commune', 'organisation', 'annee')
        verbose_name = 'Imputation remboursement taxe commune'
        verbose_name_plural = 'Imputations remboursements taxes communes'

    def __str__(self):
        return f"{self.commune.nom_commune} - {self.annee} - {self.montant_impute} Ar"


class RemarqueRecouvrementVolume(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ouvrage = models.ForeignKey(
        'organization.Ouvrage',
        on_delete=models.CASCADE,
        related_name='remarques_recouvrement_volume',
        verbose_name="Ouvrage"
    )
    annee = models.IntegerField(verbose_name="Annee", db_index=True)
    mois = models.IntegerField(verbose_name="Mois", db_index=True)
    remarque = models.TextField(blank=True, default='', verbose_name="Remarque")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de creation")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Date de modification")
    created_by = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='remarques_recouvrement_volume_creees',
        verbose_name="Cree par"
    )
    updated_by = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='remarques_recouvrement_volume_modifiees',
        verbose_name="Modifie par"
    )

    class Meta:
        db_table = 'remarque_recouvrement_volume'
        verbose_name = 'Remarque recouvrement volume'
        verbose_name_plural = 'Remarques recouvrement volume'
        unique_together = ('ouvrage', 'annee', 'mois')
        ordering = ['ouvrage__nom_ouvrage', 'annee', 'mois']

    def __str__(self):
        return f"{self.ouvrage} - {self.mois:02d}/{self.annee}"


class SaisieComptableArticle(models.Model):
    """
    Detail d'une saisie comptable d'achat (comptes 218 / 601 / 602 / 605).

    mode 'stock'      : l'article entre au stock de la base (Stock + FicheStock) a la validation de la saisie.
    mode 'hors_stock' : l'article va directement a un ouvrage, un employe ou un vehicule ; la table sert
                        de suivi des restes a livrer (la mention est aussi portee par le champ detail).
    reste_a_livrer = quantite - quantite_recue.
    """
    MODE_STOCK = 'stock'
    MODE_HORS_STOCK = 'hors_stock'
    MODE_CHOICES = [
        (MODE_STOCK, 'Entree en stock'),
        (MODE_HORS_STOCK, 'Hors stock (livraison directe)'),
    ]
    DEST_CHOICES = [
        ('ouvrage', 'Ouvrage / chantier'),
        ('employe', 'Employe (equipement)'),
        ('vehicule', 'Vehicule'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    saisie = models.ForeignKey(
        SaisieComptable, on_delete=models.CASCADE, related_name='articles', verbose_name='Saisie'
    )
    designation = models.ForeignKey(
        'planning.Designation', on_delete=models.PROTECT, related_name='lignes_saisie_comptable',
        verbose_name='Designation'
    )
    mode = models.CharField(max_length=12, choices=MODE_CHOICES, default=MODE_STOCK)
    quantite = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Quantite achetee')
    quantite_recue = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        verbose_name='Quantite recue / livree',
        help_text='Le reste (quantite - recue) est un reste a livrer'
    )
    prix_unitaire = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    destination_type = models.CharField(max_length=10, choices=DEST_CHOICES, blank=True, default='')
    ouvrage = models.ForeignKey(
        'organization.Ouvrage', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='articles_saisie_comptable'
    )
    employe = models.ForeignKey(
        'employees.Employe', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='articles_saisie_comptable'
    )
    vehicule = models.ForeignKey(
        'inventory.Vehicule', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='articles_saisie_comptable'
    )

    # Effets appliques a la validation de la saisie (idempotence)
    appliquee_at = models.DateTimeField(null=True, blank=True)
    fiche_stock_id = models.CharField(max_length=50, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'saisie_comptable_articles'
        verbose_name = 'Article de saisie comptable'
        verbose_name_plural = 'Articles de saisie comptable'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['saisie']),
            models.Index(fields=['mode', 'appliquee_at']),
        ]

    @property
    def reste_a_livrer(self):
        return (self.quantite or 0) - (self.quantite_recue or 0)

    def __str__(self):
        return f"{self.designation_id} x{self.quantite} ({self.mode})"


class LivraisonArticle(models.Model):
    """Historique des livraisons / receptions de complement d'un article d'achat (reste a livrer)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    article = models.ForeignKey(
        SaisieComptableArticle, on_delete=models.CASCADE, related_name='livraisons', verbose_name='Article'
    )
    quantite = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Quantite livree')
    date_livraison = models.DateField(verbose_name='Date de livraison')
    remarque = models.CharField(max_length=255, blank=True, default='')
    fiche_stock_id = models.CharField(max_length=50, blank=True, default='')
    created_by = models.ForeignKey(
        'employees.Employe', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='livraisons_articles_saisie'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    annulee = models.BooleanField(default=False)
    annulee_at = models.DateTimeField(null=True, blank=True)
    annulee_par = models.ForeignKey(
        'employees.Employe', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='livraisons_articles_saisie_annulees'
    )

    class Meta:
        db_table = 'saisie_comptable_livraisons'
        verbose_name = 'Livraison de reste a livrer'
        verbose_name_plural = 'Livraisons de restes a livrer'
        ordering = ['date_livraison', 'created_at']
        indexes = [models.Index(fields=['article', 'annulee'])]

    def __str__(self):
        return f"{self.article_id} +{self.quantite} ({self.date_livraison})"
