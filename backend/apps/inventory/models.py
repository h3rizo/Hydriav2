from django.db import models
from django.core.validators import FileExtensionValidator
from apps.organization.models import Base
from apps.employees.models import Employe
import uuid

# Import des modèles de demande de devis
from .models_demande_devis import DemandeDevis, DemandeDevisItem


class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category_name = models.CharField(max_length=255)
    category_description = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'categories'
        verbose_name = 'Catégorie'
        verbose_name_plural = 'Catégories'

    def __str__(self):
        return self.category_name


class Product(models.Model):
    UNIT_CHOICES = [
        ('piece', 'Pièce'),
        ('kg', 'Kilogramme'),
        ('litre', 'Litre'),
        ('metre', 'Mètre'),
        ('m2', 'Mètre carré'),
        ('m3', 'Mètre cube'),
        ('lot', 'Lot'),
        ('paquet', 'Paquet'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product_code = models.CharField(max_length=50, unique=True)
    product_name = models.CharField(max_length=255)
    product_description = models.TextField(null=True, blank=True)
    unit = models.CharField(max_length=50, choices=UNIT_CHOICES, default='piece')
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    min_stock_level = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_stock_level = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products')
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'products'
        verbose_name = 'Produit'
        verbose_name_plural = 'Produits'

    def __str__(self):
        return f"{self.product_name} ({self.product_code})"


class Stock(models.Model):
    ETAT_CHOICES = [
        ('bon', 'Bon'),
        ('moyen', 'Moyen'),
        ('mauvais', 'Mauvais'),
        ('hs', 'HS'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    current_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    reserved_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    available_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    inventory_date = models.DateField(null=True, blank=True, verbose_name="Date d'inventaire", help_text="Date du dernier inventaire physique")
    rapproche = models.BooleanField(default=False, verbose_name="Rapproché", help_text="Indique si le stock a été rapproché avec la comptabilité")
    etat = models.CharField(max_length=20, choices=ETAT_CHOICES, default='bon', verbose_name="État")
    photo = models.ImageField(
        upload_to='stocks/photos/%Y/%m/',
        null=True,
        blank=True,
        verbose_name='Photo du stock',
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'webp'])]
    )
    last_updated = models.DateTimeField(auto_now=True)

    designation = models.ForeignKey('planning.Designation', on_delete=models.CASCADE, related_name='stocks', null=True, blank=True)
    base = models.ForeignKey(Base, on_delete=models.CASCADE, related_name='stocks')
    utilisateur = models.ForeignKey('employees.Employe', on_delete=models.SET_NULL, related_name='stocks_geres', null=True, blank=True, verbose_name="Utilisateur", help_text="Employé responsable de ce stock")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'stocks'
        verbose_name = 'Stock'
        verbose_name_plural = 'Stocks'
        unique_together = ['designation', 'base']

    def save(self, *args, **kwargs):
        self.available_quantity = self.current_quantity - self.reserved_quantity
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.designation.nom} - {self.base.nom_base}: {self.available_quantity} {self.designation.unite or ''}"


class Supplier(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    supplier_name = models.CharField(max_length=255)
    supplier_contact = models.CharField(max_length=255, null=True, blank=True)
    supplier_phone = models.CharField(max_length=20, null=True, blank=True)
    supplier_email = models.EmailField(null=True, blank=True)
    supplier_address = models.TextField(null=True, blank=True)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'suppliers'
        verbose_name = 'Fournisseur'
        verbose_name_plural = 'Fournisseurs'

    def __str__(self):
        return self.supplier_name


class Purchase(models.Model):
    STATUS_CHOICES = [
        ('brouillon', 'Brouillon'),
        ('commande', 'Commandé'),
        ('livre', 'Livré'),
        ('recu', 'Réceptionné'),
        ('facture', 'Facturé'),
        ('paye', 'Payé'),
        ('annule', 'Annulé'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    purchase_number = models.CharField(max_length=50, unique=True)
    purchase_date = models.DateField()
    order_date = models.DateField(null=True, blank=True, verbose_name="Date de commande")
    actual_delivery_date = models.DateField(null=True, blank=True, verbose_name="Date de réception")
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    purchase_status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='brouillon')
    notes = models.TextField(null=True, blank=True)

    # Champs DiameX
    numeroDiameX = models.CharField(max_length=50, null=True, blank=True, verbose_name="Numéro DiameX")
    baseDiameX = models.CharField(max_length=50, null=True, blank=True, verbose_name="Base DiameX")

    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='purchases', null=True, blank=True)
    fournisseur = models.ForeignKey('billing.Fournisseur', on_delete=models.CASCADE, related_name='purchases_inventory', null=True, blank=True)
    base = models.ForeignKey(Base, on_delete=models.CASCADE, related_name='purchases_old', null=True, blank=True)
    magasin = models.ForeignKey('organization.Magasin', on_delete=models.CASCADE, related_name='purchases', null=True, blank=True, verbose_name="Magasin")
    compte = models.ForeignKey('organization.Compte', on_delete=models.SET_NULL, null=True, blank=True, related_name='purchases', verbose_name="Compte comptable")
    ordered_by = models.ForeignKey(Employe, on_delete=models.SET_NULL, null=True, blank=True, related_name='ordered_purchases')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'purchases'
        verbose_name = 'Achat'
        verbose_name_plural = 'Achats'

    def __str__(self):
        if self.fournisseur:
            return f"Achat {self.purchase_number} - {self.fournisseur.nom_fournisseur}"
        elif self.supplier:
            return f"Achat {self.purchase_number} - {self.supplier.supplier_name}"
        return f"Achat {self.purchase_number}"


class PurchaseItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quantity_ordered = models.DecimalField(max_digits=10, decimal_places=2)
    quantity_received = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name='purchase_items')
    designation = models.ForeignKey('planning.Designation', on_delete=models.CASCADE, related_name='purchase_items', null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'purchase_items'
        verbose_name = 'Article d\'achat'
        verbose_name_plural = 'Articles d\'achat'

    def save(self, *args, **kwargs):
        self.total_price = self.quantity_ordered * self.unit_price
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.designation.nom} - {self.quantity_ordered} {self.designation.unite or ''}"


class StockMovement(models.Model):
    MOVEMENT_TYPE_CHOICES = [
        ('entree', 'Entrée'),
        ('sortie', 'Sortie'),
        ('transfert', 'Transfert'),
        ('ajustement', 'Ajustement'),
        ('perte', 'Perte'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    movement_date = models.DateTimeField()
    movement_type = models.CharField(max_length=50, choices=MOVEMENT_TYPE_CHOICES)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    reference = models.CharField(max_length=100, null=True, blank=True)
    notes = models.TextField(null=True, blank=True)

    designation = models.ForeignKey('planning.Designation', on_delete=models.CASCADE, related_name='stock_movements', null=True, blank=True)
    base = models.ForeignKey(Base, on_delete=models.CASCADE, related_name='stock_movements')
    employee = models.ForeignKey(Employe, on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_movements')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'stock_movements'
        verbose_name = 'Mouvement de stock'
        verbose_name_plural = 'Mouvements de stock'

    def __str__(self):
        return f"{self.movement_type} - {self.designation.nom if self.designation else 'N/A'} - {self.quantity}"


class Transfert(models.Model):
    """Modèle pour les transferts de stock entre magasins"""
    STATUS_CHOICES = [
        ('en_attente', 'En attente'),
        ('en_cours', 'En cours'),
        ('recu', 'Reçu'),
        ('annule', 'Annulé'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transfer_number = models.CharField(max_length=50, unique=True, verbose_name="Numéro de transfert")
    transfer_date = models.DateTimeField(verbose_name="Date de transfert")
    expected_arrival_date = models.DateTimeField(null=True, blank=True, verbose_name="Date d'arrivée prévue")
    actual_arrival_date = models.DateTimeField(null=True, blank=True, verbose_name="Date d'arrivée réelle")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='en_attente', verbose_name="Statut")
    notes = models.TextField(null=True, blank=True, verbose_name="Notes")

    magasin_origine = models.ForeignKey('organization.Magasin', on_delete=models.CASCADE, related_name='transferts_sortants', verbose_name="Magasin d'origine")
    magasin_destination = models.ForeignKey('organization.Magasin', on_delete=models.CASCADE, related_name='transferts_entrants', verbose_name="Magasin de destination")
    initiated_by = models.ForeignKey(Employe, on_delete=models.SET_NULL, null=True, blank=True, related_name='transferts_inities', verbose_name="Initié par")
    received_by = models.ForeignKey(Employe, on_delete=models.SET_NULL, null=True, blank=True, related_name='transferts_recus', verbose_name="Reçu par")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'transferts'
        verbose_name = 'Transfert'
        verbose_name_plural = 'Transferts'

    def __str__(self):
        return f"Transfert {self.transfer_number} - {self.magasin_origine} â†’ {self.magasin_destination}"


class TransfertItem(models.Model):
    """Articles dans un transfert"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quantity_sent = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Quantité envoyée")
    quantity_received = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Quantité reçue")

    transfert = models.ForeignKey(Transfert, on_delete=models.CASCADE, related_name='items')
    designation = models.ForeignKey('planning.Designation', on_delete=models.CASCADE, related_name='transfert_items')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'transfert_items'
        verbose_name = 'Article de transfert'
        verbose_name_plural = 'Articles de transfert'

    def __str__(self):
        return f"{self.designation.nom} - {self.quantity_sent} {self.designation.unite or ''}"


class FicheStock(models.Model):
    """
    Fiche de stock automatiquement alimentée par:
    - Livraisons (PlanningDetail avec livraison=True)
    - Achats (Purchase)
    - Transferts (Transfert)
    """
    OPERATION_TYPE_CHOICES = [
        ('livraison', 'Livraison'),
        ('achat', 'Achat'),
        ('transfert_sortie', 'Transfert Sortie'),
        ('transfert_entree', 'Transfert Entrée'),
        ('retour_terrain', 'Retour terrain'),
        ('inventaire', 'Inventaire'),
        ('ajustement', 'Ajustement'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    operation_date = models.DateTimeField(verbose_name="Date de l'opération")
    operation_type = models.CharField(max_length=20, choices=OPERATION_TYPE_CHOICES, verbose_name="Type d'opération")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Quantité")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Prix unitaire")

    # Référence vers la source de l'opération
    planning_detail_id = models.CharField(max_length=50, null=True, blank=True, verbose_name="ID Planning Detail")
    purchase_id = models.CharField(max_length=50, null=True, blank=True, verbose_name="ID Purchase")
    transfert_id = models.CharField(max_length=50, null=True, blank=True, verbose_name="ID Transfert")
    reference = models.CharField(max_length=100, null=True, blank=True, verbose_name="Référence", help_text="Numéro de bon/transfert pour traçabilité")

    # Relations
    designation = models.ForeignKey('planning.Designation', on_delete=models.SET_NULL, null=True, blank=True, related_name='fiches_stock')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name='fiches_stock')
    base = models.ForeignKey(Base, on_delete=models.CASCADE, related_name='fiches_stock', verbose_name="Base")
    employee = models.ForeignKey(Employe, on_delete=models.SET_NULL, null=True, blank=True, related_name='fiches_stock', verbose_name="Employé")

    # Métadonnées
    notes = models.TextField(null=True, blank=True, verbose_name="Notes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'fiches_stock'
        verbose_name = 'Fiche de Stock'
        verbose_name_plural = 'Fiches de Stock'
        ordering = ['-operation_date']
        indexes = [
            models.Index(fields=['operation_date']),
            models.Index(fields=['operation_type']),
            models.Index(fields=['base']),
            models.Index(fields=['designation']),
            models.Index(fields=['product']),
        ]

    def __str__(self):
        item_name = self.designation.nom if self.designation else (self.product.product_name if self.product else 'Inconnu')
        return f"{self.get_operation_type_display()} - {item_name} - {self.quantity}"


# Import des modeles vehicules
from .models_vehicles import (
    Vehicule,
    AffectationVehicule,
    ReparationVehicule,
    RelevéCompteur,
    UtilisationPieceVehicule,
    UtilisationCarburantVehicule,
    UtilisationPersoVehicule,
    ClotureCarburantMois,
    CarnetBordMensuelScan,
    RapportConsommationCarburantScan,
    RapportConsommationCarburantRemarque,
)

