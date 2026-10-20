from django.contrib import admin

from .models import (
    BonCommande,
    BonCommandeItem,
    DemandeAchat,
    DemandeAchatItem,
    Proforma,
    ProformaItem,
)


class DemandeAchatItemInline(admin.TabularInline):
    model = DemandeAchatItem
    extra = 0


class ProformaItemInline(admin.TabularInline):
    model = ProformaItem
    extra = 0


class BonCommandeItemInline(admin.TabularInline):
    model = BonCommandeItem
    extra = 0


@admin.register(DemandeAchat)
class DemandeAchatAdmin(admin.ModelAdmin):
    list_display = ('numero_demande', 'base', 'demandeur', 'statut', 'date_creation')
    list_filter = ('statut', 'base')
    search_fields = ('numero_demande', 'motif')
    inlines = [DemandeAchatItemInline]


@admin.register(Proforma)
class ProformaAdmin(admin.ModelAdmin):
    list_display = ('demande_achat', 'fournisseur', 'date_reception', 'montant_total')
    list_filter = ('fournisseur',)
    inlines = [ProformaItemInline]


@admin.register(BonCommande)
class BonCommandeAdmin(admin.ModelAdmin):
    list_display = ('numero_bc', 'demande_achat', 'fournisseur', 'statut', 'montant_total', 'date_creation')
    list_filter = ('statut', 'fournisseur')
    search_fields = ('numero_bc',)
    inlines = [BonCommandeItemInline]
