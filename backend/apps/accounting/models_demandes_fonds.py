"""
Modèles pour la gestion des demandes d'envoi de fonds.

Workflow:
1. Prévisions annuelles (base de référence)
2. Budget (prévisions figées à un moment donné)
3. Demande de fonds mensuelle :
   - Soldes réels avant demande
   - Dépenses réelles dans DiameX
   - Prévisions restantes (futures)
   - Comparaison budget vs réel
   - Explications des écarts
   - Calcul du montant à demander
"""
from django.db import models
from django.contrib.auth.models import User
from decimal import Decimal
import uuid


class Budget(models.Model):
    """
    Budget annuel figé à un moment donné.
    Snapshot des prévisions validées pour l'année.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    annee = models.IntegerField(verbose_name="Année budgétaire")
    nom = models.CharField(max_length=255, verbose_name="Nom du budget", help_text="Ex: Budget 2025 - Version finale")
    description = models.TextField(blank=True, null=True)

    # Métadonnées
    date_creation = models.DateTimeField(auto_now_add=True)
    date_validation = models.DateTimeField(null=True, blank=True, verbose_name="Date de validation")
    valide = models.BooleanField(default=False, verbose_name="Budget validé et figé")
    cree_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='budgets_crees')
    valide_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='budgets_valides')

    class Meta:
        db_table = 'budgets'
        ordering = ['-annee', '-date_creation']
        verbose_name = "Budget"
        verbose_name_plural = "Budgets"

    def __str__(self):
        return f"{self.nom} ({self.annee})"


class LigneBudget(models.Model):
    """
    Ligne budgétaire par compte comptable.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name='lignes')
    compte = models.CharField(max_length=50, verbose_name="Code compte", help_text="Ex: 6211, 6212...")
    libelle_compte = models.CharField(max_length=255, verbose_name="Libellé du compte")

    # Montants prévisionnels
    montant_prevu = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Montant prévu (Ar)")

    # Répartition mensuelle (optionnel - pour prévisions détaillées)
    janvier = models.DecimalField(max_digits=15, decimal_places=2, default=0, null=True, blank=True)
    fevrier = models.DecimalField(max_digits=15, decimal_places=2, default=0, null=True, blank=True)
    mars = models.DecimalField(max_digits=15, decimal_places=2, default=0, null=True, blank=True)
    avril = models.DecimalField(max_digits=15, decimal_places=2, default=0, null=True, blank=True)
    mai = models.DecimalField(max_digits=15, decimal_places=2, default=0, null=True, blank=True)
    juin = models.DecimalField(max_digits=15, decimal_places=2, default=0, null=True, blank=True)
    juillet = models.DecimalField(max_digits=15, decimal_places=2, default=0, null=True, blank=True)
    aout = models.DecimalField(max_digits=15, decimal_places=2, default=0, null=True, blank=True)
    septembre = models.DecimalField(max_digits=15, decimal_places=2, default=0, null=True, blank=True)
    octobre = models.DecimalField(max_digits=15, decimal_places=2, default=0, null=True, blank=True)
    novembre = models.DecimalField(max_digits=15, decimal_places=2, default=0, null=True, blank=True)
    decembre = models.DecimalField(max_digits=15, decimal_places=2, default=0, null=True, blank=True)

    notes = models.TextField(blank=True, null=True, verbose_name="Notes")

    class Meta:
        db_table = 'lignes_budget'
        ordering = ['compte']
        unique_together = ('budget', 'compte')
        verbose_name = "Ligne budgétaire"
        verbose_name_plural = "Lignes budgétaires"

    def __str__(self):
        return f"{self.compte} - {self.libelle_compte}: {self.montant_prevu:,.2f} Ar"

    def get_montant_mois(self, mois):
        """Retourne le montant prévu pour un mois donné (1-12)."""
        mois_map = {
            1: self.janvier, 2: self.fevrier, 3: self.mars, 4: self.avril,
            5: self.mai, 6: self.juin, 7: self.juillet, 8: self.aout,
            9: self.septembre, 10: self.octobre, 11: self.novembre, 12: self.decembre
        }
        return mois_map.get(mois, Decimal('0')) or Decimal('0')


class DemandeFonds(models.Model):
    """
    Demande d'envoi de fonds mensuelle.
    """
    STATUT_CHOICES = [
        ('brouillon', 'Brouillon'),
        ('en_cours', 'En cours de validation'),
        ('validee', 'Validée'),
        ('envoyee', 'Envoyée'),
        ('recue', 'Fonds reçus'),
        ('annulee', 'Annulée'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    budget = models.ForeignKey(Budget, on_delete=models.PROTECT, related_name='demandes')

    # Période concernée
    mois = models.IntegerField(verbose_name="Mois (1-12)")
    annee = models.IntegerField(verbose_name="Année")

    # Montants globaux calculés
    solde_initial = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Solde initial (réel)")
    depenses_reelles = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Dépenses réelles à date")
    previsions_futures = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Prévisions restantes")
    montant_demande = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Montant demandé")

    # Workflow
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default='brouillon')
    date_creation = models.DateTimeField(auto_now_add=True)
    date_validation = models.DateTimeField(null=True, blank=True)
    date_envoi = models.DateTimeField(null=True, blank=True)
    date_reception = models.DateTimeField(null=True, blank=True)

    # Utilisateurs
    cree_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='demandes_fonds_crees')
    valide_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='demandes_fonds_valides')

    # Commentaires
    commentaire = models.TextField(blank=True, null=True, verbose_name="Commentaire général")

    class Meta:
        db_table = 'demandes_fonds'
        ordering = ['-annee', '-mois']
        unique_together = ('budget', 'annee', 'mois')
        verbose_name = "Demande de fonds"
        verbose_name_plural = "Demandes de fonds"

    def __str__(self):
        return f"Demande {self.annee}-{self.mois:02d} - {self.montant_demande:,.2f} Ar ({self.statut})"

    @property
    def mois_nom(self):
        """Retourne le nom du mois en français."""
        mois_noms = [
            '', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
            'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'
        ]
        return mois_noms[self.mois] if 1 <= self.mois <= 12 else ''


class LigneDemandeFonds(models.Model):
    """
    Détail de la demande de fonds par compte comptable.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    demande = models.ForeignKey(DemandeFonds, on_delete=models.CASCADE, related_name='lignes')
    compte = models.CharField(max_length=50, verbose_name="Code compte")
    libelle_compte = models.CharField(max_length=255, verbose_name="Libellé du compte")

    # Budget et prévisions
    budget_annuel = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Budget annuel")
    prevision_mois = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Prévision du mois")
    previsions_passees = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Prévisions mois passés")
    previsions_futures = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Prévisions mois futurs")

    # Réel
    solde_reel = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Solde réel avant demande")
    depenses_reelles = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Dépenses réelles DiameX")

    # Calculs
    budget_restant = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Reste à payer")
    depassement = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Dépassement de budget")

    # Explications
    explication_ecart = models.TextField(blank=True, null=True, verbose_name="Explication des écarts")
    explication_depassement = models.TextField(blank=True, null=True, verbose_name="Explication du dépassement")

    # Montant final
    montant_demande = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Montant demandé pour ce compte")

    class Meta:
        db_table = 'lignes_demande_fonds'
        ordering = ['compte']
        unique_together = ('demande', 'compte')
        verbose_name = "Ligne de demande de fonds"
        verbose_name_plural = "Lignes de demande de fonds"

    def __str__(self):
        return f"{self.compte} - {self.montant_demande:,.2f} Ar"

    def calculer_ecarts(self):
        """Calcule les écarts budget vs réel."""
        # Budget consommé = dépenses réelles
        budget_consomme = self.depenses_reelles

        # Budget restant = budget annuel - dépenses réelles - prévisions futures
        self.budget_restant = self.budget_annuel - budget_consomme - self.previsions_futures

        # Dépassement si budget restant négatif
        if self.budget_restant < 0:
            self.depassement = abs(self.budget_restant)
        else:
            self.depassement = Decimal('0')

        return {
            'budget_restant': self.budget_restant,
            'depassement': self.depassement
        }
