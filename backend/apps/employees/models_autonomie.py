"""
Modeles pour la grille salariale basee sur le stade d'autonomie des employes.

Ce module introduit un axe de reference alternatif a l'anciennete (GrilleSalariale) :
le stade d'autonomie professionnelle. GrilleAutonomie devient la reference active
pour les postes dont mode_reference_salariale = 'autonomie' (voir apps.employees.models.Poste).

Nommage volontairement distinct pour eviter toute confusion :
- GrilleSalariale (models_revalorisation.py) : grille historique poste x anciennete
- GrilleSalaire (models.py) : bulletin de salaire mensuel calcule
- GrilleAutonomie (ce fichier) : grille poste x stade d'autonomie
"""
import datetime
import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


STATUT_WORKFLOW_CHOICES = [
    ('brouillon', 'Brouillon'),
    ('soumise', 'Soumise pour validation'),
    ('validee', 'Validee'),
    ('appliquee', 'Appliquee'),
    ('rejetee', 'Rejetee'),
]

MODE_CAPITALISATION_ANCIENNETE_CHOICES = [
    ('simple', 'Simple (1 + taux x annees)'),
    ('compose', 'Compose ((1 + taux) ^ annees)'),
]

# Valeurs de repli si ni la grille ni ConfigSalaire ne fournissent de parametre.
TAUX_ANCIENNETE_AUTONOMIE_DEFAUT_PCT = Decimal('3.00')
PLAFOND_ANCIENNETE_AUTONOMIE_ANNEES_DEFAUT = Decimal('15.00')


class StadeAutonomie(models.Model):
    """
    Referentiel des stades de progression d'autonomie professionnelle,
    ordonnes (axe horizontal de la vue graphique de la grille).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    organisation = models.ForeignKey(
        'organization.Organisation',
        on_delete=models.CASCADE,
        related_name='stades_autonomie',
        verbose_name="Organisation",
        null=True,
        blank=True,
        help_text="Organisation a laquelle ce stade s'applique (vide = referentiel global partage)",
    )

    nom_stade = models.CharField(max_length=100, verbose_name="Nom du stade")

    ordre = models.PositiveIntegerField(
        verbose_name="Ordre de progression",
        help_text="Determine la position sur l'axe horizontal du graphique (0 = premier stade)",
    )

    description = models.TextField(blank=True, verbose_name="Description")

    couleur_hex = models.CharField(
        max_length=7,
        blank=True,
        verbose_name="Couleur (hex)",
        help_text="Optionnel, ex: #3B82F6",
    )

    declenche_anciennete = models.BooleanField(
        default=False,
        verbose_name="Declenche le comptage de l'anciennete",
        help_text=(
            "Cocher le stade 'Autonome 100 %'. A partir de ce stade (et des stades "
            "superieurs), la remuneration ne plafonne plus : elle est majoree par "
            "l'anciennete comptee depuis la date de premier acces a ce stade. "
            "Un seul stade coche par organisation (le plus bas fait foi)."
        ),
    )

    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'stades_autonomie'
        unique_together = ('organisation', 'ordre')
        ordering = ['organisation', 'ordre']
        verbose_name = "Stade d'autonomie"
        verbose_name_plural = "Stades d'autonomie"

    def __str__(self):
        return f"{self.nom_stade} (#{self.ordre})"


class GrilleAutonomie(models.Model):
    """
    Grille salariale definissant la remuneration nette par poste et stade d'autonomie.
    Versionnee dans le temps (date_debut_validite/date_fin_validite) et soumise a un
    workflow brouillon -> soumise -> validee -> appliquee (identique a Revalorisation).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    poste = models.ForeignKey(
        'employees.Poste',
        on_delete=models.CASCADE,
        related_name='grilles_autonomie',
        verbose_name="Poste",
    )

    stade = models.ForeignKey(
        StadeAutonomie,
        on_delete=models.CASCADE,
        related_name='grilles_autonomie',
        verbose_name="Stade d'autonomie",
    )

    organisation = models.ForeignKey(
        'organization.Organisation',
        on_delete=models.CASCADE,
        related_name='grilles_autonomie',
        verbose_name="Organisation",
        null=True,
        blank=True,
    )

    salaire_net_fixe = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Salaire net fixe (Ar)",
        help_text="Point plein du graphique - salaire net mensuel garanti",
    )

    prime_cible = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Prime nette de resultat cible (Ar)",
        help_text="Valeur de reference affichable ; le calcul reel passe par le moteur de primes",
    )

    prime_maximale = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Prime nette de resultat maximale (Ar)",
    )

    # --- Majoration d'anciennete (anti-plafond au sommet de grille) ---
    # Ces champs ne sont pris en compte que pour les grilles dont le stade est le
    # stade pivot (StadeAutonomie.declenche_anciennete) ou un stade superieur.
    anciennete_activee = models.BooleanField(
        default=False,
        verbose_name="Majoration d'anciennete activee",
        help_text="Si actif, le salaire net fixe est majore selon l'anciennete de l'employe a ce stade.",
    )

    anciennete_taux_annuel_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Taux d'anciennete annuel (%)",
        help_text="Ex: 3.00 pour +3 %/an. Vide = valeur par defaut de ConfigSalaire.",
    )

    anciennete_mode_capitalisation = models.CharField(
        max_length=10,
        choices=MODE_CAPITALISATION_ANCIENNETE_CHOICES,
        default='compose',
        verbose_name="Mode de capitalisation de l'anciennete",
    )

    anciennete_seuil_annees = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Seuil d'anciennete avant majoration (annees)",
        help_text="Nombre d'annees neutres avant que la majoration ne commence a courir.",
    )

    anciennete_plafond_annees = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Plafond d'anciennete comptee (annees)",
        help_text="Au-dela, l'anciennete n'augmente plus la majoration. Vide = valeur par defaut de ConfigSalaire (15 ans).",
    )

    anciennete_plafond_majoration_pct = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Plafond de majoration totale (%)",
        help_text="Optionnel. Ex: 40.00 = la majoration d'anciennete ne depasse jamais +40 % du salaire net fixe.",
    )

    statut = models.CharField(
        max_length=20,
        choices=STATUT_WORKFLOW_CHOICES,
        default='brouillon',
        verbose_name="Statut",
    )

    date_debut_validite = models.DateField(
        verbose_name="Date de debut de validite",
    )

    date_fin_validite = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date de fin de validite",
    )

    version_precedente = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='versions_suivantes',
        verbose_name="Version precedente",
        help_text="Trace l'historique lorsqu'une grille appliquee est modifiee (nouvelle version en brouillon)",
    )

    date_soumission = models.DateField(null=True, blank=True, verbose_name="Date de soumission")
    date_validation = models.DateField(null=True, blank=True, verbose_name="Date de validation")

    validateur = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='grilles_autonomie_validees',
        verbose_name="Validateur",
    )

    date_application = models.DateField(null=True, blank=True, verbose_name="Date d'application")

    commentaire_validation = models.TextField(blank=True, verbose_name="Commentaire de validation")

    createur = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='grilles_autonomie_creees',
        verbose_name="Createur",
    )

    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'grilles_autonomie'
        ordering = ['poste', 'stade__ordre', '-date_debut_validite']
        verbose_name = "Grille par autonomie"
        verbose_name_plural = "Grilles par autonomie"
        indexes = [
            models.Index(fields=['poste', 'stade', 'statut']),
            models.Index(fields=['date_debut_validite', 'date_fin_validite']),
        ]

    def __str__(self):
        poste_nom = self.poste.nom_poste if self.poste_id else 'Sans poste'
        stade_nom = self.stade.nom_stade if self.stade_id else 'Sans stade'
        return f"{poste_nom} - {stade_nom} ({self.get_statut_display()})"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.salaire_net_fixe is not None and self.salaire_net_fixe < 0:
            raise ValidationError({'salaire_net_fixe': "Le salaire net fixe ne peut pas etre negatif"})

        if self.date_fin_validite and self.date_fin_validite <= self.date_debut_validite:
            raise ValidationError({
                'date_fin_validite': "La date de fin doit etre posterieure a la date de debut",
            })

        if self.anciennete_activee:
            if self.anciennete_taux_annuel_pct is not None and self.anciennete_taux_annuel_pct < 0:
                raise ValidationError({'anciennete_taux_annuel_pct': "Le taux d'anciennete ne peut pas etre negatif"})
            if self.anciennete_plafond_annees is not None and self.anciennete_plafond_annees <= 0:
                raise ValidationError({'anciennete_plafond_annees': "Le plafond d'anciennete doit etre strictement positif"})

    @property
    def remuneration_cible(self):
        return self.salaire_net_fixe + self.prime_cible

    @property
    def remuneration_maximale(self):
        return self.salaire_net_fixe + self.prime_maximale

    def _taux_anciennete_effectif(self, config=None):
        """Taux annuel (%) : grille -> ConfigSalaire -> repli constante."""
        if self.anciennete_taux_annuel_pct is not None:
            return Decimal(str(self.anciennete_taux_annuel_pct))
        if config is not None and getattr(config, 'taux_anciennete_autonomie_defaut_pct', None) is not None:
            return Decimal(str(config.taux_anciennete_autonomie_defaut_pct))
        return TAUX_ANCIENNETE_AUTONOMIE_DEFAUT_PCT

    def _plafond_anciennete_annees_effectif(self, config=None):
        """Plafond (annees) : grille -> ConfigSalaire -> repli 15 ans."""
        if self.anciennete_plafond_annees is not None:
            return Decimal(str(self.anciennete_plafond_annees))
        if config is not None and getattr(config, 'plafond_anciennete_autonomie_annees', None) is not None:
            return Decimal(str(config.plafond_anciennete_autonomie_annees))
        return PLAFOND_ANCIENNETE_AUTONOMIE_ANNEES_DEFAUT

    def net_effectif(self, anciennete_annees, config=None):
        """
        Salaire net garanti effectif compte tenu de l'anciennete de l'employe a ce
        stade. Retourne le salaire net fixe (socle) si la majoration n'est pas
        activee ou si l'anciennete est nulle.

        anciennete_annees : nombre d'annees (Decimal/float) ecoulees depuis le
        premier acces de l'employe au stade pivot.
        """
        socle = Decimal(str(self.salaire_net_fixe or 0))
        if not self.anciennete_activee:
            return socle

        annees = Decimal(str(anciennete_annees or 0))
        seuil = Decimal(str(self.anciennete_seuil_annees or 0))
        delta = annees - seuil
        if delta <= 0:
            return socle

        plafond_annees = self._plafond_anciennete_annees_effectif(config)
        if plafond_annees is not None and delta > plafond_annees:
            delta = plafond_annees

        taux = self._taux_anciennete_effectif(config) / Decimal('100')
        if taux <= 0:
            return socle

        if self.anciennete_mode_capitalisation == 'simple':
            facteur = Decimal('1') + taux * delta
        else:
            # Exposant fractionnaire : Decimal ** Decimal n'est defini que pour un
            # exposant entier, on passe donc par float (precision suffisante pour
            # une projection de remuneration).
            facteur = Decimal(str((1.0 + float(taux)) ** float(delta)))

        net = socle * facteur

        if self.anciennete_plafond_majoration_pct is not None:
            net_max = socle * (Decimal('1') + Decimal(str(self.anciennete_plafond_majoration_pct)) / Decimal('100'))
            if net > net_max:
                net = net_max

        return net.quantize(Decimal('0.01'))

    def majoration_anciennete(self, anciennete_annees, config=None):
        """Montant de la majoration d'anciennete (net_effectif - socle)."""
        return self.net_effectif(anciennete_annees, config) - Decimal(str(self.salaire_net_fixe or 0))

    @classmethod
    def get_grille_for_poste_and_stade(cls, poste, stade, date_reference=None):
        """
        Recupere la grille par autonomie applicable (appliquee et active) pour un
        poste et un stade donnes. Miroir de GrilleSalariale.get_grille_for_poste_and_anciennete.
        """
        if date_reference is None:
            date_reference = datetime.date.today()

        return cls.objects.filter(
            poste=poste,
            stade=stade,
            statut='appliquee',
            date_debut_validite__lte=date_reference,
        ).filter(
            models.Q(date_fin_validite__gte=date_reference) | models.Q(date_fin_validite__isnull=True)
        ).order_by('-date_debut_validite').first()

    def soumettre(self):
        if self.statut != 'brouillon':
            raise ValueError("Seules les grilles en brouillon peuvent etre soumises")

        self.statut = 'soumise'
        self.date_soumission = datetime.date.today()
        self.save()

    def valider(self, validateur, commentaire=''):
        if self.statut != 'soumise':
            raise ValueError("Seules les grilles soumises peuvent etre validees")

        self.statut = 'validee'
        self.date_validation = datetime.date.today()
        self.validateur = validateur
        self.commentaire_validation = commentaire
        self.save()

    def rejeter(self, validateur, commentaire):
        if self.statut != 'soumise':
            raise ValueError("Seules les grilles soumises peuvent etre rejetees")

        self.statut = 'rejetee'
        self.date_validation = datetime.date.today()
        self.validateur = validateur
        self.commentaire_validation = commentaire
        self.save()

    def appliquer(self, date_application=None):
        """
        Applique la grille. Archive automatiquement toute version anterieure
        appliquee pour le meme (poste, stade) en renseignant sa date_fin_validite,
        pour garantir une seule version active a la fois.
        """
        if self.statut != 'validee':
            raise ValueError("Seules les grilles validees peuvent etre appliquees")

        application_date = date_application or datetime.date.today()

        anciennes = GrilleAutonomie.objects.filter(
            poste=self.poste,
            stade=self.stade,
            statut='appliquee',
        ).exclude(pk=self.pk)

        for ancienne in anciennes:
            if not ancienne.date_fin_validite or ancienne.date_fin_validite >= application_date:
                ancienne.date_fin_validite = application_date - datetime.timedelta(days=1)
                ancienne.save()

        self.statut = 'appliquee'
        self.date_application = application_date
        self.save()


class HistoriqueStadeAutonomie(models.Model):
    """
    Trace datee des passages de stade d'autonomie d'un employe.

    Sert de source de verite pour le calcul de l'anciennete "au sommet de grille" :
    la date de la premiere entree dont le stade a un ordre >= au stade pivot
    (StadeAutonomie.declenche_anciennete) demarre le comptage de l'anciennete qui
    majore la remuneration (voir Employe.anciennete_autonomie_annees).

    Une seule ligne par (employe, stade) : elle porte la date du PREMIER acces a
    ce stade. Une progression ulterieure vers un stade superieur ajoute une ligne
    mais ne remet pas le compteur a zero.
    """

    SOURCE_CHOICES = [
        ('auto', 'Automatique (changement de stade)'),
        ('manuelle', 'Saisie manuelle'),
        ('evaluation', 'Evaluation'),
        ('import', 'Import'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    employe = models.ForeignKey(
        'employees.Employe',
        on_delete=models.CASCADE,
        related_name='historique_stades_autonomie',
        verbose_name="Employe",
    )

    stade = models.ForeignKey(
        StadeAutonomie,
        on_delete=models.CASCADE,
        related_name='historique_employes',
        verbose_name="Stade d'autonomie",
    )

    date_effet = models.DateField(
        verbose_name="Date de premier acces au stade",
        help_text="Date a laquelle l'employe a atteint ce stade pour la premiere fois",
    )

    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default='manuelle',
        verbose_name="Source",
    )

    commentaire = models.TextField(blank=True, verbose_name="Commentaire")

    cree_par = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='historique_stades_autonomie_crees',
        verbose_name="Cree par",
    )

    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'historique_stades_autonomie'
        ordering = ['employe', 'date_effet', 'stade__ordre']
        unique_together = ('employe', 'stade')
        verbose_name = "Historique de stade d'autonomie"
        verbose_name_plural = "Historique des stades d'autonomie"
        indexes = [
            models.Index(fields=['employe', 'date_effet']),
        ]

    def __str__(self):
        employe_nom = self.employe.nom_affichage if self.employe_id else 'Sans employe'
        stade_nom = self.stade.nom_stade if self.stade_id else 'Sans stade'
        return f"{employe_nom} -> {stade_nom} ({self.date_effet})"


class RegleDePrime(models.Model):
    """
    Configuration d'une regle de prime de resultat, par poste et eventuellement
    par stade d'autonomie precis (si stade=None, la regle est generique au poste).
    """

    TYPE_CALCUL_CHOICES = [
        ('montant_fixe', 'Montant fixe'),
        ('pourcentage_salaire', 'Pourcentage du salaire net fixe'),
        ('paliers_resultats', 'Paliers de resultats'),
    ]

    PERIODICITE_CHOICES = [
        ('mensuelle', 'Mensuelle'),
        ('trimestrielle', 'Trimestrielle'),
        ('semestrielle', 'Semestrielle'),
        ('annuelle', 'Annuelle'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    poste = models.ForeignKey(
        'employees.Poste',
        on_delete=models.CASCADE,
        related_name='regles_primes',
        verbose_name="Poste",
    )

    stade = models.ForeignKey(
        StadeAutonomie,
        on_delete=models.CASCADE,
        related_name='regles_primes',
        null=True,
        blank=True,
        verbose_name="Stade d'autonomie",
        help_text="Vide = regle generique applicable a tous les stades de ce poste",
    )

    organisation = models.ForeignKey(
        'organization.Organisation',
        on_delete=models.CASCADE,
        related_name='regles_primes',
        verbose_name="Organisation",
        null=True,
        blank=True,
    )

    nom_regle = models.CharField(max_length=255, verbose_name="Nom de la regle")

    type_calcul = models.CharField(
        max_length=25,
        choices=TYPE_CALCUL_CHOICES,
        verbose_name="Type de calcul",
    )

    montant_fixe = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        verbose_name="Montant fixe (Ar)",
    )

    pourcentage_salaire = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        verbose_name="Pourcentage du salaire net fixe (%)",
    )

    periodicite = models.CharField(
        max_length=20,
        choices=PERIODICITE_CHOICES,
        verbose_name="Periodicite",
    )

    plafond = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        verbose_name="Plafond (Ar)",
        help_text="Plafond global applique apres agregation des indicateurs (mode paliers de resultats)",
    )

    actif = models.BooleanField(default=True, verbose_name="Actif")

    statut = models.CharField(
        max_length=20,
        choices=STATUT_WORKFLOW_CHOICES,
        default='brouillon',
        verbose_name="Statut",
    )

    date_debut_validite = models.DateField(verbose_name="Date de debut de validite")
    date_fin_validite = models.DateField(null=True, blank=True, verbose_name="Date de fin de validite")

    date_soumission = models.DateField(null=True, blank=True, verbose_name="Date de soumission")
    date_validation = models.DateField(null=True, blank=True, verbose_name="Date de validation")

    validateur = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='regles_primes_validees',
        verbose_name="Validateur",
    )

    commentaire_validation = models.TextField(blank=True, verbose_name="Commentaire de validation")

    createur = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='regles_primes_creees',
        verbose_name="Createur",
    )

    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'regles_primes'
        ordering = ['poste', 'stade__ordre', 'nom_regle']
        verbose_name = "Regle de prime"
        verbose_name_plural = "Regles de primes"
        indexes = [
            models.Index(fields=['poste', 'stade', 'actif']),
        ]

    def __str__(self):
        poste_nom = self.poste.nom_poste if self.poste_id else 'Sans poste'
        stade_nom = self.stade.nom_stade if self.stade_id else 'Tous stades'
        return f"{self.nom_regle} - {poste_nom} ({stade_nom})"

    def clean(self):
        from django.core.exceptions import ValidationError

        errors = {}
        if self.type_calcul == 'montant_fixe' and self.montant_fixe is None:
            errors['montant_fixe'] = "Le montant fixe est obligatoire pour ce type de calcul"
        if self.type_calcul == 'pourcentage_salaire' and self.pourcentage_salaire is None:
            errors['pourcentage_salaire'] = "Le pourcentage est obligatoire pour ce type de calcul"

        if self.date_fin_validite and self.date_fin_validite <= self.date_debut_validite:
            errors['date_fin_validite'] = "La date de fin doit etre posterieure a la date de debut"

        if errors:
            raise ValidationError(errors)

    def soumettre(self):
        if self.statut != 'brouillon':
            raise ValueError("Seules les regles en brouillon peuvent etre soumises")

        self.statut = 'soumise'
        self.date_soumission = datetime.date.today()
        self.save()

    def valider(self, validateur, commentaire=''):
        if self.statut != 'soumise':
            raise ValueError("Seules les regles soumises peuvent etre validees")

        self.statut = 'validee'
        self.date_validation = datetime.date.today()
        self.validateur = validateur
        self.commentaire_validation = commentaire
        self.save()

    def rejeter(self, validateur, commentaire):
        if self.statut != 'soumise':
            raise ValueError("Seules les regles soumises peuvent etre rejetees")

        self.statut = 'rejetee'
        self.date_validation = datetime.date.today()
        self.validateur = validateur
        self.commentaire_validation = commentaire
        self.save()


class IndicateurPrime(models.Model):
    """
    Indicateur de performance rattache a une RegleDePrime (mode paliers_resultats).
    Pour les modes montant_fixe/pourcentage_salaire, les indicateurs sont purement
    informatifs et ne participent pas au calcul (decision produit actee).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    regle = models.ForeignKey(
        RegleDePrime,
        on_delete=models.CASCADE,
        related_name='indicateurs',
        verbose_name="Regle de prime",
    )

    nom_indicateur = models.CharField(max_length=255, verbose_name="Nom de l'indicateur")

    unite = models.CharField(max_length=50, blank=True, verbose_name="Unite")

    ponderation = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00')), MaxValueValidator(Decimal('100.00'))],
        verbose_name="Ponderation (%)",
        help_text="La somme des ponderations des indicateurs actifs d'une regle doit etre 100%",
    )

    objectif = models.DecimalField(
        max_digits=14, decimal_places=2,
        verbose_name="Objectif",
        help_text="Valeur cible correspondant a 100% de realisation",
    )

    seuil_minimum = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        verbose_name="Seuil minimum de declenchement",
        help_text="En dessous de ce seuil, la part de prime de cet indicateur est nulle",
    )

    ordre = models.PositiveIntegerField(default=0, verbose_name="Ordre d'affichage")

    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'indicateurs_primes'
        ordering = ['regle', 'ordre']
        verbose_name = "Indicateur de prime"
        verbose_name_plural = "Indicateurs de primes"

    def __str__(self):
        return f"{self.nom_indicateur} ({self.regle.nom_regle})"


class PalierPrime(models.Model):
    """
    Palier de paiement associe a un IndicateurPrime : barème progressif
    taux de realisation -> taux de prime versee.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    indicateur = models.ForeignKey(
        IndicateurPrime,
        on_delete=models.CASCADE,
        related_name='paliers',
        verbose_name="Indicateur",
    )

    taux_realisation_min = models.DecimalField(
        max_digits=6, decimal_places=2,
        verbose_name="Taux de realisation min (%)",
    )

    taux_realisation_max = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        verbose_name="Taux de realisation max (%)",
        help_text="Vide = palier ouvert (pas de plafond de realisation)",
    )

    taux_prime = models.DecimalField(
        max_digits=6, decimal_places=2,
        verbose_name="Taux de prime verse (%)",
        help_text="% de la part theorique de l'indicateur verse dans ce palier",
    )

    class Meta:
        db_table = 'paliers_primes'
        ordering = ['indicateur', 'taux_realisation_min']
        verbose_name = "Palier de prime"
        verbose_name_plural = "Paliers de primes"

    def __str__(self):
        borne_max = self.taux_realisation_max if self.taux_realisation_max is not None else '∞'
        return f"{self.indicateur.nom_indicateur}: {self.taux_realisation_min}%-{borne_max}% -> {self.taux_prime}%"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.taux_realisation_max is not None and self.taux_realisation_max <= self.taux_realisation_min:
            raise ValidationError({
                'taux_realisation_max': "Le taux max doit etre superieur au taux min",
            })

        chevauchants = PalierPrime.objects.filter(indicateur=self.indicateur).exclude(pk=self.pk)
        for autre in chevauchants:
            autre_max = autre.taux_realisation_max if autre.taux_realisation_max is not None else Decimal('999999.99')
            propre_max = self.taux_realisation_max if self.taux_realisation_max is not None else Decimal('999999.99')
            if self.taux_realisation_min < autre_max and autre.taux_realisation_min < propre_max:
                raise ValidationError(
                    f"Ce palier chevauche un palier existant ({autre.taux_realisation_min}%-{autre_max}%)"
                )


class ResultatIndicateur(models.Model):
    """
    Resultat reel (saisi ou importe) d'un employe sur un indicateur, pour une
    periode donnee. Input du moteur de calcul des primes.
    """

    SOURCE_CHOICES = [
        ('saisie_manuelle', 'Saisie manuelle'),
        ('import', 'Import'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    employe = models.ForeignKey(
        'employees.Employe',
        on_delete=models.CASCADE,
        related_name='resultats_indicateurs',
        verbose_name="Employe",
    )

    indicateur = models.ForeignKey(
        IndicateurPrime,
        on_delete=models.CASCADE,
        related_name='resultats',
        verbose_name="Indicateur",
    )

    periode_debut = models.DateField(verbose_name="Debut de periode")
    periode_fin = models.DateField(verbose_name="Fin de periode")

    valeur_realisee = models.DecimalField(max_digits=14, decimal_places=2, verbose_name="Valeur realisee")

    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default='saisie_manuelle',
        verbose_name="Source",
    )

    saisi_par = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resultats_indicateurs_saisis',
        verbose_name="Saisi par",
    )

    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'resultats_indicateurs'
        unique_together = ('employe', 'indicateur', 'periode_debut', 'periode_fin')
        indexes = [
            models.Index(fields=['employe', 'periode_debut']),
        ]
        verbose_name = "Resultat d'indicateur"
        verbose_name_plural = "Resultats d'indicateurs"

    def __str__(self):
        return f"{self.employe.nom_affichage} - {self.indicateur.nom_indicateur} ({self.periode_debut} - {self.periode_fin})"


class MajorationTerritoriale(models.Model):
    """
    Majoration de remuneration liee a une zone geographique (District ou Base),
    utilisee par le simulateur de remuneration. Remplace, pour les postes
    concernes, les montants forfaitaires globaux de ConfigSalaire.
    """

    TYPE_MONTANT_CHOICES = [
        ('montant_fixe', 'Montant fixe'),
        ('pourcentage_salaire', 'Pourcentage du salaire net fixe'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    nom = models.CharField(max_length=255, verbose_name="Nom")

    district = models.ForeignKey(
        'geography.District',
        on_delete=models.CASCADE,
        related_name='majorations_territoriales',
        null=True,
        blank=True,
        verbose_name="District",
    )

    base = models.ForeignKey(
        'organization.Base',
        on_delete=models.CASCADE,
        related_name='majorations_territoriales',
        null=True,
        blank=True,
        verbose_name="Base",
    )

    type_montant = models.CharField(
        max_length=25,
        choices=TYPE_MONTANT_CHOICES,
        verbose_name="Type de montant",
    )

    montant_fixe = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name="Montant fixe (Ar)")
    pourcentage_salaire = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Pourcentage (%)")

    compte = models.ForeignKey(
        'organization.Compte',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='majorations_territoriales',
        verbose_name="Compte comptable",
        help_text="Compte utilise pour l'export DiameX (ex: 625107 - indemnite hors zone/terrain)",
    )

    actif = models.BooleanField(default=True, verbose_name="Actif")

    date_debut_validite = models.DateField(verbose_name="Date de debut de validite")
    date_fin_validite = models.DateField(null=True, blank=True, verbose_name="Date de fin de validite")

    organisation = models.ForeignKey(
        'organization.Organisation',
        on_delete=models.CASCADE,
        related_name='majorations_territoriales',
        null=True,
        blank=True,
        verbose_name="Organisation",
    )

    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'majorations_territoriales'
        ordering = ['nom']
        verbose_name = "Majoration territoriale"
        verbose_name_plural = "Majorations territoriales"

    def __str__(self):
        zone = self.base.nom_base if self.base_id else (self.district.nom_district if self.district_id else 'Zone non definie')
        return f"{self.nom} ({zone})"

    def clean(self):
        from django.core.exceptions import ValidationError

        if bool(self.district_id) == bool(self.base_id):
            raise ValidationError("Renseigner exactement un des deux champs : District OU Base (pas les deux, pas aucun)")

        if self.type_montant == 'montant_fixe' and self.montant_fixe is None:
            raise ValidationError({'montant_fixe': "Le montant fixe est obligatoire pour ce type"})
        if self.type_montant == 'pourcentage_salaire' and self.pourcentage_salaire is None:
            raise ValidationError({'pourcentage_salaire': "Le pourcentage est obligatoire pour ce type"})


class SimulationRemuneration(models.Model):
    """
    Historique des simulations de remuneration par employe (entretiens annuels,
    hypotheses de negociation, etc.). detail_calcul_json conserve la trace
    complete du detail par indicateur/palier pour audit.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    employe = models.ForeignKey(
        'employees.Employe',
        on_delete=models.CASCADE,
        related_name='simulations_remuneration',
        verbose_name="Employe",
    )

    poste = models.ForeignKey(
        'employees.Poste',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='simulations_remuneration',
        verbose_name="Poste (au moment de la simulation)",
    )

    stade = models.ForeignKey(
        StadeAutonomie,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='simulations_remuneration',
        verbose_name="Stade (au moment de la simulation)",
    )

    distance_annuelle_km = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        verbose_name="Distance annuelle parcourue (km)",
        help_text="Saisie manuelle",
    )

    nombre_points_eau_couverts = models.PositiveIntegerField(
        null=True, blank=True,
        verbose_name="Nombre de points d'eau couverts",
    )

    salaire_garanti = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="Salaire garanti (Ar)")
    total_primes_resultat = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="Total primes de resultat (Ar)")
    majoration_territoriale_montant = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="Majoration territoriale (Ar)")
    remuneration_nette_totale = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'), verbose_name="Remuneration nette totale estimee (Ar)")

    detail_calcul_json = models.JSONField(default=dict, blank=True, verbose_name="Detail du calcul")

    date_creation = models.DateTimeField(auto_now_add=True)

    cree_par = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='simulations_remuneration_creees',
        verbose_name="Cree par",
    )

    class Meta:
        db_table = 'simulations_remuneration'
        ordering = ['-date_creation']
        verbose_name = "Simulation de remuneration"
        verbose_name_plural = "Simulations de remuneration"
        indexes = [
            models.Index(fields=['employe', '-date_creation']),
        ]

    def __str__(self):
        return f"Simulation {self.employe.nom_affichage} - {self.date_creation:%d/%m/%Y}"
