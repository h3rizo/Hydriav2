from django.contrib import admin
from .models import (
    Adresse, CarteSociale, EquipementConstitutif
)

# OuvrageAdmin supprimé - utiliser organization.Ouvrage à la place



@admin.register(Adresse)
class AdresseAdmin(admin.ModelAdmin):
    list_display = ('nomadresse', 'type_adresse', 'ouvrage', 'is_active')
    list_filter = ('type_adresse', 'is_active')
    search_fields = ('nomadresse', 'adresse_complete', 'ouvrage__nom_ouvrage')
    ordering = ('nomadresse',)

    fieldsets = (
        ('Informations adresse', {
            'fields': ('nomadresse', 'type_adresse', 'ouvrage', 'is_active')
        }),
        ('Détails', {
            'fields': ('adresse_complete',)
        }),
        ('Géolocalisation', {
            'fields': ('latitude', 'longitude'),
            'classes': ('collapse',)
        })
    )


@admin.register(CarteSociale)
class CarteSocialeAdmin(admin.ModelAdmin):
    list_display = ('numero_carte', 'nom_beneficiaire', 'statut', 'date_creation', 'date_expiration', 'ouvrage')
    list_filter = ('statut', 'date_creation', 'date_expiration')
    search_fields = ('numero_carte', 'nom_beneficiaire', 'point_eau_nom')
    ordering = ('-date_creation',)

    fieldsets = (
        ('Informations carte', {
            'fields': ('numero_carte', 'nom_beneficiaire', 'statut')
        }),
        ('Point d\'eau', {
            'fields': ('ouvrage', 'point_eau_nom')
        }),
        ('Dates', {
            'fields': ('date_creation', 'date_expiration')
        }),
        ('Observations', {
            'fields': ('observations',),
            'classes': ('collapse',)
        })
    )


@admin.register(EquipementConstitutif)
class EquipementConstitutifAdmin(admin.ModelAdmin):
    list_display = ('nom', 'code_equipement', 'type_equipement', 'statut', 'ouvrage', 'responsable')
    list_filter = ('type_equipement', 'statut', 'date_installation')
    search_fields = ('nom', 'code_equipement', 'description', 'ouvrage__nom_ouvrage')
    ordering = ('code_equipement',)

    fieldsets = (
        ('Informations équipement', {
            'fields': ('nom', 'code_equipement', 'type_equipement', 'statut')
        }),
        ('Description', {
            'fields': ('description',)
        }),
        ('Affectation', {
            'fields': ('ouvrage', 'responsable')
        }),
        ('Maintenance', {
            'fields': ('date_installation', 'derniere_maintenance', 'prochaine_maintenance')
        }),
        ('Documentation', {
            'fields': ('photo_reference',),
            'classes': ('collapse',)
        })
    )
