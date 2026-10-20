"""
Modeles pour la gestion des revalorisations salariales annuelles.
"""
import datetime
import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


def _decimal_value(value, default='0.00'):
    if value in (None, ''):
        return Decimal(default)
    return Decimal(str(value))


def _format_decimal_display(value):
    decimal_value = _decimal_value(value)
    normalized = format(decimal_value.normalize(), 'f')
    if '.' in normalized:
        normalized = normalized.rstrip('0').rstrip('.')
    return normalized or '0'


class GrilleSalariale(models.Model):
    """
    Grille salariale definissant les fourchettes de salaire par poste et anciennete.
    Cette grille est versionnee dans le temps via les dates de validite.
    """

    MODE_FOURCHETTE_HAUTE_CHOICES = [
        ('fixe', 'Fixe'),
        ('ratio_annuel', 'Ratio annuel'),
    ]

    MODE_RATIO_HAUTE_CHOICES = [
        ('compose', 'Compose'),
        ('simple', 'Simple'),
    ]

    NIVEAU_JUNIOR = 'junior'
    NIVEAU_CONFIRME = 'confirme'
    NIVEAU_CHOICES = [
        (NIVEAU_JUNIOR, 'Junior (non autonome)'),
        (NIVEAU_CONFIRME, 'Confirme (par anciennete)'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    niveau = models.CharField(
        max_length=20,
        choices=NIVEAU_CHOICES,
        default=NIVEAU_CONFIRME,
        verbose_name="Niveau",
        help_text="Junior : fourchette unique, independante de l'anciennete. "
                  "Confirme : tranches d'anciennete comptees depuis la sortie du niveau Junior.",
    )

    poste = models.ForeignKey(
        'employees.Poste',
        on_delete=models.CASCADE,
        related_name='grilles_salariales',
        verbose_name="Poste",
    )

    organisation = models.ForeignKey(
        'organization.Organisation',
        on_delete=models.CASCADE,
        related_name='grilles_salariales',
        verbose_name="Organisation",
        null=True,
        blank=True,
        help_text="Organisation a laquelle cette grille s'applique",
    )

    template = models.ForeignKey(
        'employees.GrilleSalarialeTemplate',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='grilles_liees',
        verbose_name="Modèle de grille",
        help_text="Template réutilisable permettant de partager les mêmes paramètres entre plusieurs postes. "
                  "Si défini, les paramètres de la grille sont hérités du template."
    )

    anciennete_min = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Anciennete minimum (annees)",
        help_text="Debut de la tranche d'anciennete (ex: 0 ou 0.50)",
    )

    anciennete_max = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Anciennete maximum (annees)",
        help_text="Fin de la tranche d'anciennete (ex: 2 ou 2.50)",
    )

    fourchette_basse = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Fourchette basse",
        help_text="Salaire minimum pour cette tranche (Ariary)",
    )

    fourchette_haute = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Fourchette haute",
        help_text="Salaire maximum pour cette tranche (Ariary)",
    )

    mode_fourchette_haute = models.CharField(
        max_length=20,
        choices=MODE_FOURCHETTE_HAUTE_CHOICES,
        default='fixe',
        verbose_name="Mode fourchette haute",
        help_text="Fixe ou calculee par ratio annuel",
    )

    fourchette_haute_reference = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Reference fourchette haute",
        help_text="Salaire de reference brut utilise pour le calcul dynamique",
    )

    anciennete_reference_haute = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Anciennete de reference haute",
        help_text="Anciennete a partir de laquelle le ratio annuel est applique",
    )

    ratio_annuel_haute = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Ratio annuel fourchette haute (%)",
        help_text="Exemple: 6.00 pour 6% par an",
    )

    mode_ratio_haute = models.CharField(
        max_length=20,
        choices=MODE_RATIO_HAUTE_CHOICES,
        default='compose',
        verbose_name="Mode de calcul du ratio haute",
        help_text="Simple ou compose",
    )

    date_debut_validite = models.DateField(
        verbose_name="Date de debut de validite",
        help_text="Date a partir de laquelle cette grille est applicable",
    )

    date_fin_validite = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date de fin de validite",
        help_text="Date jusqu'a laquelle cette grille est applicable (NULL = indefini)",
    )

    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'grilles_salariales'
        ordering = ['poste', 'anciennete_min', '-date_debut_validite']
        verbose_name = "Grille salariale"
        verbose_name_plural = "Grilles salariales"
        indexes = [
            models.Index(fields=['poste', 'date_debut_validite']),
            models.Index(fields=['anciennete_min', 'anciennete_max']),
        ]

    def __str__(self):
        poste_nom = self.poste.nom_poste if self.poste else 'Sans poste'
        if self.est_junior:
            return f"{poste_nom} - Junior ({self.date_debut_validite})"
        return (
            f"{poste_nom} - "
            f"{_format_decimal_display(self.anciennete_min)}-"
            f"{_format_decimal_display(self.anciennete_max)} ans "
            f"({self.date_debut_validite})"
        )

    @property
    def est_junior(self):
        return self.niveau == self.NIVEAU_JUNIOR

    @property
    def est_active(self):
        """Verifie si cette grille est actuellement active."""
        aujourd_hui = datetime.date.today()

        if self.date_debut_validite > aujourd_hui:
            return False

        if self.date_fin_validite and self.date_fin_validite < aujourd_hui:
            return False

        return True

    @property
    def tpl_fourchette_basse(self):
        return self.template.fourchette_basse if self.template else self.fourchette_basse

    @property
    def tpl_fourchette_haute(self):
        return self.template.fourchette_haute if self.template else self.fourchette_haute

    @property
    def tpl_mode_fourchette_haute(self):
        return self.template.mode_fourchette_haute if self.template else self.mode_fourchette_haute

    @property
    def tpl_fourchette_haute_reference(self):
        return self.template.fourchette_haute_reference if self.template else self.fourchette_haute_reference

    @property
    def tpl_anciennete_reference_haute(self):
        return self.template.anciennete_reference_haute if self.template else self.anciennete_reference_haute

    @property
    def tpl_ratio_annuel_haute(self):
        return self.template.ratio_annuel_haute if self.template else self.ratio_annuel_haute

    @property
    def tpl_mode_ratio_haute(self):
        return self.template.mode_ratio_haute if self.template else self.mode_ratio_haute

    @property
    def is_fourchette_haute_dynamic(self):
        return self.tpl_mode_fourchette_haute == 'ratio_annuel'

    def get_fourchette_basse_for_anciennete(self, anciennete=None):
        return self.tpl_fourchette_basse

    def get_fourchette_haute_for_anciennete(self, anciennete=None):
        if not self.is_fourchette_haute_dynamic:
            return self.tpl_fourchette_haute

        reference = self.tpl_fourchette_haute_reference
        if reference in (None, ''):
            return self.tpl_fourchette_haute

        try:
            anciennete_value = _decimal_value(self.anciennete_max if anciennete is None else anciennete)
        except Exception:
            anciennete_value = _decimal_value(self.anciennete_max)

        anciennete_reference = _decimal_value(self.tpl_anciennete_reference_haute)
        delta = max(Decimal('0.00'), anciennete_value - anciennete_reference)
        ratio_decimal = _decimal_value(self.tpl_ratio_annuel_haute) / Decimal('100')

        if self.tpl_mode_ratio_haute == 'simple':
            factor = Decimal('1.00') + (ratio_decimal * Decimal(delta))
        else:
            factor = (Decimal('1.00') + ratio_decimal) ** delta

        return (reference * factor).quantize(Decimal('0.01'))

    def update_fourchette_haute_cache(self):
        if not self.is_fourchette_haute_dynamic:
            if self.template:
                self.fourchette_haute = self.template.fourchette_haute
            return

        if self.tpl_fourchette_haute_reference in (None, ''):
            if self.template:
                self.fourchette_haute = self.template.fourchette_haute
            return

        self.fourchette_haute = self.get_fourchette_haute_for_anciennete(self.anciennete_max)

    def save(self, *args, **kwargs):
        self.update_fourchette_haute_cache()
        super().save(*args, **kwargs)

    def clean(self):
        """Validation personnalisee."""
        from django.core.exceptions import ValidationError

        if self.anciennete_min > self.anciennete_max:
            raise ValidationError({
                'anciennete_max': "L'anciennete maximum doit etre superieure ou egale a l'anciennete minimum",
            })

        if self.est_junior:
            if self.template_id:
                raise ValidationError("Une grille Junior ne peut pas etre liee a un template d'anciennete.")
            if self.mode_fourchette_haute != 'fixe':
                raise ValidationError({
                    'mode_fourchette_haute': "Une grille Junior a une fourchette haute fixe (pas de ratio annuel).",
                })

        # Si un template est utilise, valider la coherence avec les valeurs heritees
        if self.template:
            fourchette_haute_calculee = self.get_fourchette_haute_for_anciennete(self.anciennete_min)
            if self.tpl_fourchette_basse > fourchette_haute_calculee:
                raise ValidationError(
                    f"Avec le template, la fourchette haute calculee ({fourchette_haute_calculee}) "
                    f"est inferieure a la fourchette basse ({self.tpl_fourchette_basse})."
                )
        else:
            # Logique de validation originale si aucun template n'est utilise
            if self.is_fourchette_haute_dynamic:
                errors = {}
                if self.fourchette_haute_reference in (None, ''):
                    errors['fourchette_haute_reference'] = "La reference de la fourchette haute est obligatoire pour le mode ratio annuel"
                if self.anciennete_reference_haute is None:
                    errors['anciennete_reference_haute'] = "L'anciennete de reference est obligatoire pour le mode ratio annuel"
                if self.ratio_annuel_haute in (None, ''):
                    errors['ratio_annuel_haute'] = "Le ratio annuel est obligatoire pour le mode ratio annuel"
                elif Decimal(str(self.ratio_annuel_haute or 0)) <= 0:
                    errors['ratio_annuel_haute'] = "Le ratio annuel doit etre superieur a zero"

                if errors:
                    raise ValidationError(errors)

                fourchette_haute_min = self.get_fourchette_haute_for_anciennete(self.anciennete_min)
                if self.fourchette_basse > fourchette_haute_min:
                    raise ValidationError({
                        'fourchette_haute_reference': "La fourchette haute calculee doit etre superieure ou egale a la fourchette basse",
                    })
            else:
                if self.fourchette_basse > self.fourchette_haute:
                    raise ValidationError({
                        'fourchette_haute': "La fourchette haute doit etre superieure ou egale a la fourchette basse",
                    })

        if self.date_fin_validite and self.date_fin_validite <= self.date_debut_validite:
            raise ValidationError({
                'date_fin_validite': "La date de fin doit etre posterieure a la date de debut",
            })

    @classmethod
    def _valides_a(cls, date_reference):
        return cls.objects.filter(date_debut_validite__lte=date_reference).filter(
            models.Q(date_fin_validite__gte=date_reference) | models.Q(date_fin_validite__isnull=True)
        )

    @classmethod
    def get_grille_junior_for_poste(cls, poste, date_reference=None):
        """Grille Junior applicable a un poste (independante de l'anciennete)."""
        if date_reference is None:
            date_reference = datetime.date.today()
        return cls._valides_a(date_reference).filter(
            poste=poste, niveau=cls.NIVEAU_JUNIOR,
        ).order_by('-date_debut_validite').first()

    @classmethod
    def get_grille_for_employe(cls, employe, date_reference=None):
        """
        Grille applicable a un employe : grille Junior de son poste tant qu'il est
        Junior a date_reference, sinon la tranche correspondant a son anciennete
        comptee depuis sa sortie du niveau Junior.
        """
        if date_reference is None:
            date_reference = datetime.date.today()
        if not employe.poste_id:
            return None
        if employe.est_junior(date_reference):
            return cls.get_grille_junior_for_poste(employe.poste, date_reference)
        return cls.get_grille_for_poste_and_anciennete(
            employe.poste, employe.anciennete_grille_annees(date_reference), date_reference,
        )

    @classmethod
    def get_grille_for_poste_and_anciennete(cls, poste, anciennete, date_reference=None):
        """
        Recupere la grille salariale (niveau confirme) applicable pour un poste
        et une anciennete donnes.
        """
        if date_reference is None:
            date_reference = datetime.date.today()

        return cls.objects.filter(
            poste=poste,
            niveau=cls.NIVEAU_CONFIRME,
            anciennete_min__lte=anciennete,
            anciennete_max__gte=anciennete,
            date_debut_validite__lte=date_reference,
        ).filter(
            models.Q(date_fin_validite__gte=date_reference) | models.Q(date_fin_validite__isnull=True)
        ).order_by('-date_debut_validite', '-anciennete_min', 'anciennete_max').first()


class Revalorisation(models.Model):
    """
    Modele pour enregistrer les revalorisations salariales annuelles des employes
    avec leurs justifications et historique.
    """

    STATUT_CHOICES = [
        ('brouillon', 'Brouillon'),
        ('soumise', 'Soumise pour validation'),
        ('validee', 'Validee'),
        ('appliquee', 'Appliquee'),
        ('rejetee', 'Rejetee'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    employe = models.ForeignKey(
        'employees.Employe',
        on_delete=models.CASCADE,
        related_name='revalorisations',
        verbose_name="Employe",
    )

    annee = models.PositiveIntegerField(
        verbose_name="Annee",
        help_text="Annee de la revalorisation salariale",
    )

    salaire_actuel = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Salaire actuel",
        help_text="Salaire mensuel brut actuel (Ariary)",
    )

    salaire_propose = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Salaire propose",
        help_text="Nouveau salaire mensuel brut propose (Ariary)",
    )

    pourcentage_augmentation = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name="Pourcentage d'augmentation",
        help_text="Pourcentage d'augmentation calcule automatiquement",
        editable=False,
    )

    justification = models.TextField(
        verbose_name="Justification",
        help_text="Justification detaillee de l'augmentation salariale",
    )

    grille_salariale = models.ForeignKey(
        'GrilleSalariale',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='revalorisations',
        verbose_name="Grille salariale de reference",
        help_text="Grille salariale utilisee comme reference",
    )

    evaluation = models.ForeignKey(
        'employees.Evaluation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='revalorisations',
        verbose_name="Evaluation de reference",
        help_text="Evaluation de l'employe servant de base a la decision",
    )

    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default='brouillon',
        verbose_name="Statut",
    )

    date_soumission = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date de soumission",
    )

    date_validation = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date de validation",
    )

    validateur = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='revalorisations_validees',
        verbose_name="Validateur",
        help_text="Employe ayant valide la revalorisation",
    )

    date_application = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date d'application",
        help_text="Date effective d'application du nouveau salaire",
    )

    commentaire_validation = models.TextField(
        blank=True,
        verbose_name="Commentaire de validation",
        help_text="Commentaire du validateur",
    )

    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    createur = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='revalorisations_creees',
        verbose_name="Createur",
    )

    class Meta:
        db_table = 'revalorisations'
        ordering = ['-annee', 'employe__nom']
        verbose_name = "Revalorisation salariale"
        verbose_name_plural = "Revalorisations salariales"
        unique_together = ('employe', 'annee')
        indexes = [
            models.Index(fields=['employe', '-annee']),
            models.Index(fields=['statut']),
            models.Index(fields=['annee']),
        ]

    def __str__(self):
        display_name = self.employe.surnom if self.employe.surnom else self.employe.nom
        return f"{display_name} - {self.annee} ({self.get_statut_display()})"

    def save(self, *args, **kwargs):
        """Calcul automatique du pourcentage d'augmentation avant sauvegarde."""
        if self.salaire_actuel and self.salaire_propose:
            if self.salaire_actuel > 0:
                augmentation = self.salaire_propose - self.salaire_actuel
                self.pourcentage_augmentation = (augmentation / self.salaire_actuel) * 100
            else:
                self.pourcentage_augmentation = Decimal('0.00')

        super().save(*args, **kwargs)

    def clean(self):
        """Validation personnalisee."""
        from django.core.exceptions import ValidationError

        if self.salaire_propose <= 0:
            raise ValidationError({
                'salaire_propose': "Le salaire propose doit etre positif",
            })

        if self.salaire_actuel <= 0:
            raise ValidationError({
                'salaire_actuel': "Le salaire actuel doit etre positif",
            })

    @property
    def montant_augmentation(self):
        """Calcule le montant de l'augmentation."""
        return self.salaire_propose - self.salaire_actuel

    @property
    def est_dans_fourchette(self):
        """
        Verifie si le salaire propose est dans la fourchette de la grille salariale.

        Returns:
            tuple (bool, str): (dans_fourchette, message)
        """
        if not self.grille_salariale:
            return (None, "Aucune grille salariale de reference")

        # Anciennete de grille : comptee depuis la sortie du niveau Junior (0 pour un Junior).
        anciennete = Decimal('0')
        if self.employe:
            date_reference = (
                self.date_application
                or self.date_validation
                or self.date_soumission
                or datetime.date(int(self.annee), 1, 1)
            )
            if hasattr(date_reference, 'date'):
                date_reference = date_reference.date()
            anciennete = self.employe.anciennete_grille_annees(date_reference)

        fourchette_basse = self.grille_salariale.get_fourchette_basse_for_anciennete(anciennete)
        fourchette_haute = self.grille_salariale.get_fourchette_haute_for_anciennete(anciennete)

        if self.salaire_propose < fourchette_basse:
            return (False, f"Sous la fourchette basse ({fourchette_basse:,.0f} Ar)")

        if self.salaire_propose > fourchette_haute:
            return (False, f"Au-dessus de la fourchette haute ({fourchette_haute:,.0f} Ar)")

        return (True, "Dans la fourchette")

    def soumettre(self):
        """Soumet la revalorisation pour validation."""
        if self.statut != 'brouillon':
            raise ValueError("Seules les revalorisations en brouillon peuvent etre soumises")

        self.statut = 'soumise'
        self.date_soumission = datetime.date.today()
        self.save()

    def valider(self, validateur, commentaire=''):
        """Valide la revalorisation."""
        if self.statut != 'soumise':
            raise ValueError("Seules les revalorisations soumises peuvent etre validees")

        self.statut = 'validee'
        self.date_validation = datetime.date.today()
        self.validateur = validateur
        self.commentaire_validation = commentaire
        self.save()

    def rejeter(self, validateur, commentaire):
        """Rejette la revalorisation."""
        if self.statut != 'soumise':
            raise ValueError("Seules les revalorisations soumises peuvent etre rejetees")

        self.statut = 'rejetee'
        self.date_validation = datetime.date.today()
        self.validateur = validateur
        self.commentaire_validation = commentaire
        self.save()

    def appliquer(self, date_application=None):
        """Applique la revalorisation (logique de paie a brancher ensuite)."""
        if self.statut != 'validee':
            raise ValueError("Seules les revalorisations validees peuvent etre appliquees")

        self.statut = 'appliquee'
        self.date_application = date_application or datetime.date.today()
        self.save()

        # TODO: Creer une nouvelle entree GrilleSalaire pour l'employe avec le nouveau salaire.
