"""
Modèle de template pour grilles salariales réutilisables.
Permet d'éviter la duplication quand plusieurs postes partagent les mêmes grilles.
"""
from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal
import uuid


def _decimal_value(value):
    """Convertit une valeur en Decimal de manière sécurisée."""
    if value is None or value == '':
        return Decimal('0.00')
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


class GrilleSalarialeTemplate(models.Model):
    """
    Template réutilisable pour grilles salariales.
    Plusieurs GrilleSalariale (de postes différents) peuvent référencer le même template.
    """

    MODE_FOURCHETTE_HAUTE_CHOICES = [
        ('fixe', 'Fixe'),
        ('ratio_annuel', 'Ratio annuel'),
    ]

    MODE_RATIO_HAUTE_CHOICES = [
        ('compose', 'Composé'),
        ('simple', 'Simple'),
    ]

    # Identifiant
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Métadonnées du template
    nom_template = models.CharField(
        max_length=255,
        verbose_name="Nom du modèle",
        help_text="Ex: Grille Agents Techniques, Grille Cadres, etc."
    )

    description = models.TextField(
        blank=True,
        null=True,
        verbose_name="Description",
        help_text="Description du type de postes concernés par ce modèle"
    )

    # Organisation (pour filtrage/scoping)
    organisation = models.ForeignKey(
        'organization.Organisation',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='grilles_templates',
        verbose_name="Organisation"
    )

    # Paramètres de la grille (identiques à GrilleSalariale)
    anciennete_min = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Ancienneté min (années)",
        help_text="Début de la tranche d'ancienneté (ex: 0 ou 0.50)"
    )

    anciennete_max = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Ancienneté max (années)",
        help_text="Fin de la tranche d'ancienneté (ex: 2 ou 2.50)"
    )

    fourchette_basse = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Fourchette basse (Ar)",
        help_text="Salaire minimum pour cette tranche (Ariary)"
    )

    fourchette_haute = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Fourchette haute (Ar)",
        help_text="Salaire maximum pour cette tranche (Ariary)"
    )

    # Mode de calcul de la fourchette haute
    mode_fourchette_haute = models.CharField(
        max_length=20,
        choices=MODE_FOURCHETTE_HAUTE_CHOICES,
        default='fixe',
        verbose_name="Mode fourchette haute",
        help_text="Fixe ou calculée par ratio annuel"
    )

    # Champs pour calcul dynamique de la fourchette haute
    fourchette_haute_reference = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Référence fourchette haute",
        help_text="Salaire de référence brut utilisé pour le calcul dynamique"
    )

    anciennete_reference_haute = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Ancienneté de référence haute",
        help_text="Ancienneté à partir de laquelle le ratio annuel est appliqué"
    )

    ratio_annuel_haute = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name="Ratio annuel fourchette haute (%)",
        help_text="Exemple: 6.00 pour 6% par an"
    )

    mode_ratio_haute = models.CharField(
        max_length=20,
        choices=MODE_RATIO_HAUTE_CHOICES,
        default='compose',
        verbose_name="Mode de calcul du ratio haute",
        help_text="Simple ou composé"
    )

    # Dates de validité
    date_debut_validite = models.DateField(
        verbose_name="Date début validité",
        help_text="Date à partir de laquelle ce modèle est applicable"
    )

    date_fin_validite = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date fin validité",
        help_text="Date de fin de validité (optionnel)"
    )

    # Métadonnées
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='grilles_templates_created',
        verbose_name="Créé par"
    )

    class Meta:
        db_table = 'grilles_salariales_templates'
        verbose_name = "Modèle de grille salariale"
        verbose_name_plural = "Modèles de grilles salariales"
        ordering = ['organisation', 'nom_template', 'anciennete_min']
        indexes = [
            models.Index(fields=['organisation', 'date_debut_validite']),
            models.Index(fields=['date_debut_validite', 'date_fin_validite']),
        ]

    def __str__(self):
        org_prefix = f"[{self.organisation.nom_organisation}] " if self.organisation else ""
        return f"{org_prefix}{self.nom_template} ({self.anciennete_min}-{self.anciennete_max} ans)"

    def clean(self):
        """Validation du template."""
        from django.core.exceptions import ValidationError
        
        if self.anciennete_min > self.anciennete_max:
            raise ValidationError({
                'anciennete_max': "L'anciennete maximum doit etre superieure ou egale a l'anciennete minimum",
            })
            
        if self.mode_fourchette_haute == 'ratio_annuel':
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
                    'fourchette_haute_reference': f"La fourchette haute calculee ({fourchette_haute_min}) est inferieure a la fourchette basse ({self.fourchette_basse})"
                })
        else:
            if self.fourchette_haute is not None and self.fourchette_basse > self.fourchette_haute:
                raise ValidationError({
                    'fourchette_haute': "La fourchette haute doit etre superieure ou egale a la fourchette basse"
                })

    @property
    def is_fourchette_haute_dynamic(self):
        """Indique si la fourchette haute est calculée dynamiquement."""
        return self.mode_fourchette_haute == 'ratio_annuel'

    def get_fourchette_basse_for_anciennete(self, anciennete=None):
        """Retourne la fourchette basse (toujours fixe)."""
        return self.fourchette_basse

    def get_fourchette_haute_for_anciennete(self, anciennete=None):
        """
        Calcule la fourchette haute dynamiquement si le mode ratio_annuel est activé.

        Args:
            anciennete: Ancienneté en années (Decimal). Si None, utilise anciennete_max.

        Returns:
            Decimal: Fourchette haute calculée ou fixe selon le mode.
        """
        if not self.is_fourchette_haute_dynamic:
            return self.fourchette_haute

        reference = self.fourchette_haute_reference
        if reference in (None, ''):
            return self.fourchette_haute

        try:
            anciennete_value = _decimal_value(self.anciennete_max if anciennete is None else anciennete)
        except Exception:
            anciennete_value = _decimal_value(self.anciennete_max)

        anciennete_reference = _decimal_value(self.anciennete_reference_haute)
        delta = max(Decimal('0.00'), anciennete_value - anciennete_reference)
        ratio_decimal = _decimal_value(self.ratio_annuel_haute) / Decimal('100')

        # Calcul selon le mode (intérêt simple vs intérêt composé)
        if self.mode_ratio_haute == 'simple':
            # Intérêt simple: Valeur × (1 + taux × durée)
            factor = Decimal('1.00') + (ratio_decimal * Decimal(delta))
        else:  # compose
            # Intérêt composé: Valeur × (1 + taux)^durée
            factor = (Decimal('1.00') + ratio_decimal) ** delta

        return (reference * factor).quantize(Decimal('0.01'))

    def update_fourchette_haute_cache(self):
        """
        Met à jour le cache fourchette_haute basé sur le calcul dynamique.
        À appeler après modification des paramètres de calcul.
        """
        if not self.is_fourchette_haute_dynamic:
            return
        if self.fourchette_haute_reference in (None, ''):
            return
        self.fourchette_haute = self.get_fourchette_haute_for_anciennete(self.anciennete_max)

    def get_postes_utilisant_template(self):
        """Retourne la liste des postes qui utilisent ce template."""
        return [grille.poste for grille in self.grilles_liees.all()]

    def count_grilles_liees(self):
        """Compte le nombre de grilles liées à ce template."""
        return self.grilles_liees.count()

    count_grilles_liees.short_description = "Grilles liées"
