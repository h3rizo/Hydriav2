"""
Modèle pour les demandes de devis générées depuis le calcul de commandes
"""
from django.db import models
from apps.organization.models import Base
from apps.employees.models import Employe
import uuid


class DemandeDevis(models.Model):
    """
    Demande de devis générée automatiquement depuis le workflow de calcul de commandes
    """
    STATUS_CHOICES = [
        ('brouillon', 'Brouillon'),
        ('soumise', 'Soumise'),
        ('en_cours', 'En cours'),
        ('validee', 'Validée'),
        ('annulee', 'Annulée'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    numero_demande = models.CharField(max_length=50, unique=True, verbose_name="Numéro de demande")
    date_creation = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")
    date_modification = models.DateTimeField(auto_now=True, verbose_name="Date de modification")
    statut = models.CharField(max_length=20, choices=STATUS_CHOICES, default='brouillon', verbose_name="Statut")

    # Contexte de calcul
    periode_analyse = models.IntegerField(null=True, blank=True, verbose_name="Période d'analyse (mois)")
    date_debut_analyse = models.DateField(null=True, blank=True, verbose_name="Date début analyse")
    mode_calcul = models.CharField(max_length=50, null=True, blank=True, verbose_name="Mode de calcul")

    # Relations
    base = models.ForeignKey(Base, on_delete=models.CASCADE, related_name='demandes_devis', verbose_name="Base")
    creee_par = models.ForeignKey(Employe, on_delete=models.SET_NULL, null=True, blank=True, related_name='demandes_devis_creees', verbose_name="Créée par")

    # Métadonnées
    notes = models.TextField(null=True, blank=True, verbose_name="Notes")
    total_articles = models.IntegerField(default=0, verbose_name="Total articles")
    montant_estime = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Montant estimé")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'demandes_devis'
        verbose_name = 'Demande de Devis'
        verbose_name_plural = 'Demandes de Devis'
        ordering = ['-date_creation']
        indexes = [
            models.Index(fields=['date_creation']),
            models.Index(fields=['statut']),
            models.Index(fields=['base']),
        ]

    def __str__(self):
        return f"Demande {self.numero_demande} - {self.base.nom_base} - {self.statut}"


class DemandeDevisItem(models.Model):
    """
    Articles/lignes d'une demande de devis
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Relations
    demande_devis = models.ForeignKey(DemandeDevis, on_delete=models.CASCADE, related_name='items', verbose_name="Demande de devis")
    designation = models.ForeignKey('planning.Designation', on_delete=models.CASCADE, related_name='demandes_devis_items', verbose_name="Désignation")

    # Quantités calculées
    besoin_retenu = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Besoin retenu")
    bons_attente = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Bons en attente")
    stock_precedent = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Stock précédent")
    achats_effectues = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Achats effectués")
    estimation_historique = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Estimation historique")
    stock_actuel = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Stock actuel")
    quantite_a_commander = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Quantité à commander")
    quantite_finale = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Quantité finale")

    # Métadonnées
    nb_lignes_bl = models.IntegerField(default=0, verbose_name="Nombre de lignes BL")
    source_calcul = models.CharField(max_length=50, null=True, blank=True, verbose_name="Source de calcul", help_text="bons_livraison, historique_stock_achats ou auto")
    prix_unitaire_estime = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Prix unitaire estimé")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'demandes_devis_items'
        verbose_name = 'Article Demande de Devis'
        verbose_name_plural = 'Articles Demandes de Devis'
        unique_together = ['demande_devis', 'designation']

    def __str__(self):
        return f"{self.demande_devis.numero_demande} - {self.designation.nom} - Qté: {self.quantite_a_commander}"
