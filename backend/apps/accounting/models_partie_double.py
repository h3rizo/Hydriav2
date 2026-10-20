"""
Modèle pour la comptabilité en partie double
"""
from django.db import models
import uuid


class EcriturePartieDouble(models.Model):
    """
    Modèle pour stocker les écritures comptables en partie double.
    Chaque transaction DiameX génère 1 ou 2 lignes selon le type :
    - Cat=00BOOK : 1 ligne (déjà en partie double)
    - Autres : 2 lignes (conversion In/Out → Débit/Crédit)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Lien vers l'entrée DiameX source
    entree_diamex = models.ForeignKey(
        'accounting.BaseDiameX',
        on_delete=models.CASCADE,
        related_name='ecritures_partie_double',
        verbose_name="Entrée DiameX source"
    )

    # Numéro de ligne pour les conversions (1 ou 2)
    # Cat=00BOOK : toujours ligne 1
    # Autres : ligne 1 (Compte=Code Journal) et ligne 2 (Compte=Code Cat)
    numero_ligne = models.IntegerField(
        default=1,
        verbose_name="Numéro de ligne",
        help_text="1 ou 2 pour les écritures doubles"
    )

    # Colonnes de la comptabilité partie double
    rec = models.IntegerField(
        null=True,
        blank=True,
        verbose_name="Numéro de reçu"
    )

    date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date",
        db_index=True
    )

    compte = models.CharField(
        max_length=20,
        verbose_name="Compte",
        help_text="Code comptable (6 chiffres)",
        db_index=True
    )

    libelle = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Libellé"
    )

    debit = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        verbose_name="Débit"
    )

    credit = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        verbose_name="Crédit"
    )

    fournisseur = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Fournisseur"
    )

    detail = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="Détail"
    )

    activ = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="Activité"
    )

    financement = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="Financement"
    )

    info = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="Information"
    )

    id_lien = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name="ID Lien",
        help_text="Identifiant de liaison entre les 2 lignes"
    )

    scan = models.URLField(
        max_length=500,
        null=True,
        blank=True,
        verbose_name="Lien scan"
    )

    # Type de conversion appliquée
    TYPE_CONVERSION_CHOICES = [
        ('00BOOK', 'Cat 00BOOK (déjà partie double)'),
        ('standard', 'Conversion standard (2 lignes)'),
    ]
    type_conversion = models.CharField(
        max_length=20,
        choices=TYPE_CONVERSION_CHOICES,
        default='standard',
        verbose_name="Type de conversion"
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
        related_name='ecritures_partie_double_creees',
        verbose_name="Créé par"
    )

    class Meta:
        db_table = 'ecritures_partie_double'
        verbose_name = 'Écriture comptable partie double'
        verbose_name_plural = 'Écritures comptables partie double'
        ordering = ['date', 'rec', 'numero_ligne']
        indexes = [
            models.Index(fields=['date', 'compte']),
            models.Index(fields=['rec']),
            models.Index(fields=['type_conversion']),
        ]
        # Une entrée DiameX peut générer max 2 lignes
        unique_together = [('entree_diamex', 'numero_ligne')]

    def __str__(self):
        return f"{self.date} - {self.compte} - Débit: {self.debit} / Crédit: {self.credit}"

    @property
    def est_equilibree(self):
        """
        Vérifie si l'écriture est équilibrée (Débit = Crédit pour la paire de lignes)
        """
        if self.type_conversion == '00BOOK':
            # Pour 00BOOK, une seule ligne suffit
            return True

        # Pour les conversions standard, vérifier que les 2 lignes existent et sont équilibrées
        lignes = EcriturePartieDouble.objects.filter(entree_diamex=self.entree_diamex)
        if lignes.count() != 2:
            return False

        total_debit = sum(ligne.debit for ligne in lignes)
        total_credit = sum(ligne.credit for ligne in lignes)

        return abs(total_debit - total_credit) < 0.01  # Tolérance pour erreurs d'arrondi
