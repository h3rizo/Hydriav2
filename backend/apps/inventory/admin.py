from django.contrib import admin
from .models import Category, DemandeDevis, DemandeDevisItem


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('category_name', 'category_description', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('category_name', 'category_description')
    ordering = ('category_name',)


class DemandeDevisItemInline(admin.TabularInline):
    model = DemandeDevisItem
    extra = 0
    fields = ('designation', 'stock_actuel', 'estimation_historique', 'quantite_a_commander', 'quantite_finale')
    readonly_fields = ('designation', 'stock_actuel', 'estimation_historique', 'quantite_a_commander')


@admin.register(DemandeDevis)
class DemandeDevisAdmin(admin.ModelAdmin):
    list_display = ('numero_demande', 'base', 'creee_par', 'date_creation', 'statut', 'total_articles')
    list_filter = ('statut', 'base', 'date_creation')
    search_fields = ('numero_demande', 'notes')
    inlines = [DemandeDevisItemInline]
    date_hierarchy = 'date_creation'
    readonly_fields = ('numero_demande', 'base', 'creee_par', 'date_creation')
