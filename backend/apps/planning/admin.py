from django.contrib import admin
from .models import (
    Planning, PlanningEmploye, Indemnite, TypeActivite, TypeDesignation, Designation,
    Activite, ActivitePoste, PlanningDetail, DesignationCompte, BonLivraison, PlanningPiece
)


@admin.register(Planning)
class PlanningAdmin(admin.ModelAdmin):
    list_display = ('date', 'ouvrage', 'statut', 'employe', 'type_activite', 'estvalide')
    list_filter = ('statut', 'estvalide', 'type_activite')
    search_fields = ('remarque', 'bilan', 'employe__nom', 'ouvrage__nom')
    ordering = ('-date',)
    raw_id_fields = ('employe', 'ouvrage', 'type_activite')


@admin.register(PlanningEmploye)
class PlanningEmployeAdmin(admin.ModelAdmin):
    list_display = ('planning', 'employee', 'is_present')
    list_filter = ('is_present', 'planning__date')
    search_fields = ('employee__nom', 'employee__prenom')


@admin.register(Indemnite)
class IndemniteAdmin(admin.ModelAdmin):
    list_display = ('employee', 'indemnite_type', 'indemnite_amount', 'indemnite_date', 'indemnite_status')
    list_filter = ('indemnite_type', 'indemnite_status', 'indemnite_date')
    search_fields = ('employee__nom', 'employee__prenom')
    ordering = ('-indemnite_date',)


@admin.register(TypeActivite)
class TypeActiviteAdmin(admin.ModelAdmin):
    list_display = ('nomtype', 'createdat')
    search_fields = ('nomtype',)
    ordering = ('nomtype',)


@admin.register(TypeDesignation)
class TypeDesignationAdmin(admin.ModelAdmin):
    list_display = ('nom', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('nom', 'description')
    ordering = ('nom',)


@admin.register(Designation)
class DesignationAdmin(admin.ModelAdmin):
    list_display = ('nom', 'type_designation', 'prix_unitaire', 'unite', 'actif')
    list_filter = ('type_designation', 'actif', 'concerne_livraison', 'concerne_avance')
    search_fields = ('nom', 'description')
    ordering = ('type_designation__nom', 'nom')


@admin.register(Activite)
class ActiviteAdmin(admin.ModelAdmin):
    list_display = ('nom', 'type_activite', 'is_active', 'est_corrective')
    list_filter = ('type_activite', 'is_active', 'est_corrective')
    search_fields = ('nom', 'description')
    ordering = ('type_activite__nomtype', 'nom')

    fieldsets = (
        ('Informations activité', {
            'fields': ('nom', 'type_activite', 'is_active', 'est_corrective')
        }),
        ('Description', {
            'fields': ('description',)
        })
    )


@admin.register(ActivitePoste)
class ActivitePosteAdmin(admin.ModelAdmin):
    list_display = ('nom', 'activite', 'frequence_mois', 'mode_frequence', 'is_active')
    list_filter = ('activite__type_activite', 'frequence_mois', 'mode_frequence', 'is_active')
    search_fields = ('nom', 'description', 'activite__nom')
    ordering = ('activite__nom', 'nom')


@admin.register(PlanningDetail)
class PlanningDetailAdmin(admin.ModelAdmin):
    list_display = ('planning_id', 'designation', 'quantity', 'pu', 'montant', 'acheteur')
    list_filter = ('designation__type_designation',)
    search_fields = ('designation__nom', 'acheteur')
    ordering = ('-planning_id', 'designation__nom')

    fieldsets = (
        ('Référence planning', {
            'fields': ('planning_id', 'designation')
        }),
        ('Quantités et prix', {
            'fields': ('quantity', 'pu', 'montant')
        }),
        ('Logistique', {
            'fields': ('acheteur',)
        })
    )


@admin.register(BonLivraison)
class BonLivraisonAdmin(admin.ModelAdmin):
    list_display = ('numero_bon', 'designation', 'quantite', 'magasin', 'utilise', 'retour', 'created_at')
    list_filter = ('utilise', 'retour', 'magasin')
    search_fields = ('numero_bon', 'designation__nom', 'planning__employe__surnom')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Informations de base', {
            'fields': ('planning', 'designation', 'quantite', 'magasin')
        }),
        ('Livraison', {
            'fields': ('point_eau', 'equipement')
        }),
        ('Statut workflow', {
            'fields': ('numero_bon', 'utilise', 'date_utilisation', 'retour', 'date_retour')
        }),
        ('Justificatif', {
            'fields': ('photo_justificatif',)
        }),
        ('Métadonnées', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )


@admin.register(DesignationCompte)
class DesignationCompteAdmin(admin.ModelAdmin):
    list_display = ('designation', 'compte', 'is_active')
    list_filter = ('designation__type_designation', 'is_active')
    search_fields = ('designation__nom', 'compte__nom_compte', 'compte__compte')
    ordering = ('designation__nom', 'compte__nom_compte')


@admin.register(PlanningPiece)
class PlanningPieceAdmin(admin.ModelAdmin):
    list_display = ('planning', 'fichier', 'created_at')
    search_fields = ('planning__id', 'fichier__original_filename')
