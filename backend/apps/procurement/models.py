import uuid

from django.db import models
from django.utils import timezone


class DemandeAchat(models.Model):
    """Demande d'achat interne (DA), avant l'obtention de proformas et la génération de Bons de Commande."""

    STATUT_CHOICES = [
        ('brouillon', 'Brouillon'),
        ('proformas', 'Proformas en cours'),
        ('analyse', 'Analyse / Comparatif'),
        ('termine', 'Terminé'),
        ('annule', 'Annulé'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    numero_demande = models.CharField(max_length=20, unique=True, editable=False, verbose_name="Numéro de demande")

    base = models.ForeignKey(
        'organization.Base',
        on_delete=models.PROTECT,
        related_name='demandes_achat',
        verbose_name="Base demandeuse",
    )
    demandeur = models.ForeignKey(
        'employees.Employe',
        on_delete=models.PROTECT,
        related_name='demandes_achat',
        verbose_name="Demandeur",
    )
    motif = models.TextField(verbose_name="Motif de la demande")
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='brouillon', verbose_name="Statut")

    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'demandes_achat'
        verbose_name = "Demande d'achat"
        verbose_name_plural = "Demandes d'achat"
        ordering = ['-date_creation']

    def __str__(self):
        return f"{self.numero_demande} - {self.base}"

    def save(self, *args, **kwargs):
        if not self.numero_demande:
            self.numero_demande = self._generer_numero()
        super().save(*args, **kwargs)

    @staticmethod
    def _generer_numero():
        annee = timezone.now().year
        prefix = f'DA-{annee}-'
        dernieres = DemandeAchat.objects.filter(
            numero_demande__startswith=prefix
        ).values_list('numero_demande', flat=True).order_by('-numero_demande')

        dernier_numero = 0
        if dernieres.exists():
            try:
                dernier_numero = int(dernieres.first().split('-')[-1])
            except (ValueError, IndexError):
                pass

        return f'{prefix}{dernier_numero + 1:04d}'

    @property
    def fournisseurs_ayant_repondu(self):
        return set(
            item.fournisseur_id
            for item in Proforma.objects.filter(demande_achat=self)
        )

    @property
    def est_comparable(self):
        """Au moins 1 article, avec au moins 2 fournisseurs ayant soumis un proforma."""
        return self.items.exists() and len(self.fournisseurs_ayant_repondu) >= 1


class DemandeAchatItem(models.Model):
    """Ligne d'article demandée dans une Demande d'Achat."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    demande = models.ForeignKey(
        DemandeAchat,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name="Demande d'achat",
    )
    designation = models.ForeignKey(
        'planning.Designation',
        on_delete=models.PROTECT,
        related_name='demande_achat_items',
        verbose_name="Article",
    )
    quantite = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Quantité souhaitée")
    remarques = models.TextField(null=True, blank=True, verbose_name="Remarques")

    class Meta:
        db_table = 'demande_achat_items'
        verbose_name = "Article de demande d'achat"
        verbose_name_plural = "Articles de demande d'achat"
        ordering = ['id']

    def __str__(self):
        return f"{self.designation} x{self.quantite}"

    @property
    def prix_le_plus_bas(self):
        """Retourne le ProformaItem avec le prix unitaire le plus bas parmi les offres reçues pour cet article."""
        return (
            ProformaItem.objects.filter(demande_item=self, prix_unitaire__isnull=False)
            .order_by('prix_unitaire')
            .first()
        )


class Proforma(models.Model):
    """Devis (proforma) soumis par un fournisseur en réponse à une Demande d'Achat."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    demande_achat = models.ForeignKey(
        DemandeAchat,
        on_delete=models.CASCADE,
        related_name='proformas',
        verbose_name="Demande d'achat",
    )
    fournisseur = models.ForeignKey(
        'billing.Fournisseur',
        on_delete=models.PROTECT,
        related_name='proformas',
        verbose_name="Fournisseur",
    )
    scan_document = models.FileField(
        upload_to='procurement/proformas/%Y/%m/',
        null=True,
        blank=True,
        verbose_name="Scan du proforma",
    )
    date_reception = models.DateField(default=timezone.now, verbose_name="Date de réception")
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'proformas'
        verbose_name = "Proforma"
        verbose_name_plural = "Proformas"
        ordering = ['-date_reception']
        unique_together = ('demande_achat', 'fournisseur')

    def __str__(self):
        return f"Proforma {self.fournisseur} - {self.demande_achat.numero_demande}"

    @property
    def montant_total(self):
        return sum(
            (item.montant_ligne for item in self.items.all()),
            start=0,
        )


class ProformaItem(models.Model):
    """Prix unitaire proposé par un fournisseur pour un article donné de la Demande d'Achat."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    proforma = models.ForeignKey(
        Proforma,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name="Proforma",
    )
    demande_item = models.ForeignKey(
        DemandeAchatItem,
        on_delete=models.CASCADE,
        related_name='offres',
        verbose_name="Article demandé",
    )
    prix_unitaire = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, verbose_name="Prix unitaire proposé"
    )
    est_selectionne = models.BooleanField(default=False, verbose_name="Offre retenue")
    justification_non_moins_cher = models.TextField(
        null=True, blank=True,
        verbose_name="Justification (si offre retenue n'est pas la moins chère)",
    )

    class Meta:
        db_table = 'proforma_items'
        verbose_name = "Ligne de proforma"
        verbose_name_plural = "Lignes de proforma"
        ordering = ['id']
        unique_together = ('proforma', 'demande_item')

    def __str__(self):
        return f"{self.demande_item.designation} - {self.proforma.fournisseur} - {self.prix_unitaire}"

    @property
    def montant_ligne(self):
        if self.prix_unitaire is None:
            return 0
        return self.prix_unitaire * self.demande_item.quantite

    @property
    def est_moins_cher(self):
        moins_cher = self.demande_item.prix_le_plus_bas
        return moins_cher is not None and moins_cher.id == self.id


class BonCommande(models.Model):
    """Bon de commande officiel généré pour un fournisseur, regroupant les articles retenus à son nom."""

    STATUT_CHOICES = [
        ('genere', 'Généré'),
        ('envoye', 'Envoyé au fournisseur'),
        ('recu', 'Marchandise reçue'),
        ('annule', 'Annulé'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    numero_bc = models.CharField(max_length=20, unique=True, editable=False, verbose_name="Numéro de bon de commande")

    demande_achat = models.ForeignKey(
        DemandeAchat,
        on_delete=models.PROTECT,
        related_name='bons_commande',
        verbose_name="Demande d'achat d'origine",
    )
    fournisseur = models.ForeignKey(
        'billing.Fournisseur',
        on_delete=models.PROTECT,
        related_name='bons_commande',
        verbose_name="Fournisseur",
    )
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='genere', verbose_name="Statut")

    date_creation = models.DateTimeField(auto_now_add=True)
    cree_par = models.ForeignKey(
        'employees.Employe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bons_commande_generes',
        verbose_name="Généré par",
    )

    class Meta:
        db_table = 'bons_commande'
        verbose_name = "Bon de commande"
        verbose_name_plural = "Bons de commande"
        ordering = ['-date_creation']

    def __str__(self):
        return f"{self.numero_bc} - {self.fournisseur}"

    def save(self, *args, **kwargs):
        if not self.numero_bc:
            self.numero_bc = self._generer_numero()
        super().save(*args, **kwargs)

    @staticmethod
    def _generer_numero():
        annee = timezone.now().year
        prefix = f'BC-{annee}-'
        dernieres = BonCommande.objects.filter(
            numero_bc__startswith=prefix
        ).values_list('numero_bc', flat=True).order_by('-numero_bc')

        dernier_numero = 0
        if dernieres.exists():
            try:
                dernier_numero = int(dernieres.first().split('-')[-1])
            except (ValueError, IndexError):
                pass

        return f'{prefix}{dernier_numero + 1:04d}'

    @property
    def montant_total(self):
        return sum((item.montant_ligne for item in self.items.all()), start=0)


class BonCommandeItem(models.Model):
    """Ligne d'article d'un Bon de Commande, provenant de l'offre retenue d'un proforma."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bon_commande = models.ForeignKey(
        BonCommande,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name="Bon de commande",
    )
    proforma_item = models.ForeignKey(
        ProformaItem,
        on_delete=models.PROTECT,
        related_name='bon_commande_items',
        verbose_name="Offre retenue",
    )
    designation = models.ForeignKey(
        'planning.Designation',
        on_delete=models.PROTECT,
        related_name='bon_commande_items',
        verbose_name="Article",
    )
    quantite = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Quantité")
    prix_unitaire = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Prix unitaire")

    class Meta:
        db_table = 'bon_commande_items'
        verbose_name = "Ligne de bon de commande"
        verbose_name_plural = "Lignes de bon de commande"
        ordering = ['id']

    def __str__(self):
        return f"{self.designation} x{self.quantite}"

    @property
    def montant_ligne(self):
        return self.prix_unitaire * self.quantite
