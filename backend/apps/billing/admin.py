from django.contrib import admin
from apps.organization.models import Organisation
from apps.geography.models import District
from .models import (
    ConfigTarifForfaitaire,
    TypePointEau, PointEau, CompteurTete, TarifVolumetrique,
    ModaliteGestion, Releve, ReleveCompteurTete, Fournisseur, DepenseService,
    AdresseFournisseur,
    AdresseFournisseurDistrict,
    CompteurAbonne, ChangementCompteurAbonne, SegmentConsommationReleve,
)


@admin.register(TypePointEau)
class TypePointEauAdmin(admin.ModelAdmin):
    list_display = ('nom_type', 'description', 'actif')
    list_filter = ('actif',)
    search_fields = ('nom_type', 'description')
    ordering = ('nom_type',)


@admin.register(PointEau)
class PointEauAdmin(admin.ModelAdmin):
    list_display = ('nomabonne', 'type_point_eau', 'ouvrage', 'typeabonne', 'datebranchement')
    list_filter = ('type_point_eau', 'typeabonne', 'estbranchementinstitutionnel', 'datebranchement')
    search_fields = ('nomabonne', 'contactabonne', 'numeroteleph')
    ordering = ('nomabonne',)
    readonly_fields = ('compteur_abonne_actuel', 'tarifforfaitaire')

    fieldsets = (
        ('Informations abonné', {
            'fields': ('nomabonne', 'contactabonne', 'numeroteleph', 'typeabonne')
        }),
        ('Localisation et branchement', {
            'fields': ('ouvrage', 'type_point_eau', 'parcelle', 'latitude', 'longitude')
        }),
        ('Dates', {
            'fields': ('datebranchement', 'datearretbranchement')
        }),
        ('Configuration technique', {
            'fields': ('compteur_tete', 'compteur_abonne_actuel', 'estbranchementinstitutionnel', 'pourcentage_tarif', 'tarifforfaitaire'),
            'classes': ('collapse',)
        }),
        ('Données Diamex', {
            'fields': ('numerodiamexdemande', 'numerodiamexpaiementdevis', 'basediamexdemande', 'basediamexpaiementdevis'),
            'classes': ('collapse',)
        }),
        ('Paiements', {
            'fields': ('montantdemandepaye', 'montantdevispaye'),
            'classes': ('collapse',)
        })
    )


@admin.register(CompteurTete)
class CompteurTeteAdmin(admin.ModelAdmin):
    list_display = ('numerocompteur', 'marque', 'modele', 'statut', 'ouvrage', 'date_installation')
    list_filter = ('statut', 'marque', 'date_installation')
    search_fields = ('numerocompteur', 'marque', 'modele')
    ordering = ('numerocompteur',)

    fieldsets = (
        ('Informations compteur', {
            'fields': ('numerocompteur', 'marque', 'modele', 'index_initial')
        }),
        ('Installation', {
            'fields': ('ouvrage', 'date_installation', 'statut')
        }),
        ('Dates de suivi', {
            'fields': ('createdat', 'updatedat'),
            'classes': ('collapse',)
        })
    )


@admin.register(CompteurAbonne)
class CompteurAbonneAdmin(admin.ModelAdmin):
    list_display = ('numero', 'point_eau', 'statut', 'date_installation', 'date_retrait', 'index_initial', 'index_retrait')
    list_filter = ('statut', 'date_installation', 'date_retrait')
    search_fields = ('numero', 'point_eau__nomabonne', 'point_eau__code_point_eau')
    autocomplete_fields = ('point_eau',)


@admin.register(ChangementCompteurAbonne)
class ChangementCompteurAbonneAdmin(admin.ModelAdmin):
    list_display = ('point_eau', 'ancien_compteur', 'nouveau_compteur', 'date_changement', 'motif', 'releve_facture')
    list_filter = ('motif', 'date_changement', 'ancien_compteur_illisible')
    search_fields = ('point_eau__nomabonne', 'ancien_compteur__numero', 'nouveau_compteur__numero')
    readonly_fields = tuple(field.name for field in ChangementCompteurAbonne._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SegmentConsommationReleve)
class SegmentConsommationReleveAdmin(admin.ModelAdmin):
    list_display = ('releve', 'ordre', 'compteur', 'index_debut', 'index_fin', 'volume', 'est_estime')
    search_fields = ('compteur__numero', 'releve__numero_facture', 'releve__abonne')
    readonly_fields = tuple(field.name for field in SegmentConsommationReleve._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TarifVolumetrique)
class TarifVolumetriqueAdmin(admin.ModelAdmin):
    list_display = ('ouvrage', 'datedebuttarif', 'datefintarif', 'prixabonnement', 'institutionnel', 'actif')
    list_filter = ('actif', 'institutionnel', 'datedebuttarif', 'datefintarif')
    search_fields = ('ouvrage__nom', 'ouvrage__infra_name')
    ordering = ('-datedebuttarif',)

    fieldsets = (
        ('Informations tarif', {
            'fields': ('ouvrage', 'prixabonnement', 'institutionnel', 'actif')
        }),
        ('Période de validité', {
            'fields': ('datedebuttarif', 'datefintarif')
        })
    )


@admin.register(ModaliteGestion)
class ModaliteGestionAdmin(admin.ModelAdmin):
    list_display = ('ouvrage', 'type_gestion', 'gestionnaire', 'employe', 'modalitepaiement', 'statut', 'date_debut', 'date_fin')
    list_filter = ('type_gestion', 'statut', 'modalitepaiement', 'date_debut')
    search_fields = ('gestionnaire__nom_organisation', 'employe__surnom', 'ouvrage__nom_ouvrage')
    ordering = ('-date_debut',)
    autocomplete_fields = ['ouvrage', 'gestionnaire', 'employe']

    fieldsets = (
        ('Informations gestion', {
            'fields': ('ouvrage', 'type_gestion', 'statut')
        }),
        ('Responsables', {
            'fields': ('gestionnaire', 'employe')
        }),
        ('Dates', {
            'fields': ('date_debut', 'date_fin')
        }),
        ('Conditions financières', {
            'fields': ('modalitepaiement',)
        }),
        ('Documentation', {
            'fields': ('contrat_file',),
            'classes': ('collapse',)
        })
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'gestionnaire':
            kwargs['queryset'] = Organisation.objects.filter(
                type_organisation=Organisation.TYPE_GESTIONNAIRE
            ).order_by('nom_organisation')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Releve)
class ReleveAdmin(admin.ModelAdmin):
    list_display = ('abonne', 'datereleve', 'consommation', 'montant', 'statut', 'datepaiement')
    list_filter = ('statut', 'datereleve', 'datepaiement')
    search_fields = ('abonne',)
    ordering = ('-datereleve',)

    fieldsets = (
        ('Informations relevé', {
            'fields': ('abonne', 'datereleve')
        }),
        ('Données compteur', {
            'fields': ('ancienindex', 'nouvelindex', 'consommation')
        }),
        ('Facturation', {
            'fields': ('montant', 'statut', 'datepaiement', 'montantpaye')
        })
    )


@admin.register(ReleveCompteurTete)
class ReleveCompteurTeteAdmin(admin.ModelAdmin):
    list_display = (
        'compteur_tete', 'date_releve', 'ancien_index', 'nouvel_index',
        'volume_tete', 'volume_aval', 'ecart_volume'
    )
    list_filter = ('date_releve', 'compteur_tete__ouvrage')
    search_fields = ('compteur_tete__numerocompteur', 'explication_ecart')
    ordering = ('-date_releve', '-created_at')
    autocomplete_fields = ('compteur_tete',)
    readonly_fields = ('ancien_index', 'volume_tete', 'volume_aval', 'ecart_volume', 'created_at', 'updated_at')

    fieldsets = (
        ('Releve', {
            'fields': ('compteur_tete', 'date_releve', 'nouvel_index')
        }),
        ('Comparaison', {
            'fields': ('ancien_index', 'volume_tete', 'volume_aval', 'ecart_volume', 'nb_points_eau_aval', 'explication_ecart')
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )


@admin.register(Fournisseur)
class FournisseurAdmin(admin.ModelAdmin):
    list_display = ('nom_fournisseur', 'type_fournisseur', 'telephone', 'email', 'actif')
    list_filter = ('type_fournisseur', 'actif')
    search_fields = ('nom_fournisseur', 'telephone', 'email')
    ordering = ('nom_fournisseur',)
    fieldsets = (
        ('Informations fournisseur', {
            'fields': ('nom_fournisseur', 'type_fournisseur', 'actif')
        }),
        ('Contact', {
            'fields': ('telephone', 'email', 'adresse_fournisseur', 'adresse')
        }),
        ('Informations légales', {
            'fields': ('numero_nif', 'numero_stat', 'cin', 'date_cin', 'lieu_cin'),
            'classes': ('collapse',)
        })
    )

@admin.register(AdresseFournisseur)
class AdresseFournisseurAdmin(admin.ModelAdmin):
    list_display = ('adresse', 'actif')
    list_filter = ('actif',)
    search_fields = ('adresse',)
    ordering = ('adresse',)


@admin.register(AdresseFournisseurDistrict)
class AdresseFournisseurDistrictAdmin(admin.ModelAdmin):
    list_display = ('adresse_affichee', 'district', 'actif')
    list_filter = ('actif', 'district')
    search_fields = ('adresse', 'adresse_fournisseur__adresse', 'district__nom_district', 'district__region__nom_region')
    ordering = ('adresse',)

    def adresse_affichee(self, obj):
        return obj.adresse_fournisseur.adresse if obj.adresse_fournisseur_id else obj.adresse
    adresse_affichee.short_description = 'Adresse'

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'district':
            kwargs['queryset'] = District.objects.select_related('region__ex_province').order_by(
                'region__ex_province__nom_ex_province',
                'region__nom_region',
                'nom_district',
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(DepenseService)
class DepenseServiceAdmin(admin.ModelAdmin):
    list_display = ('date_facture', 'fournisseur', 'designation', 'unite', 'prix_unitaire', 'montant', 'total', 'statut', 'signataire_1', 'signataire_2')
    list_filter = ('statut', 'date_facture', 'fournisseur')
    search_fields = ('fournisseur__nom_fournisseur', 'designation', 'unite', 'signataire_1', 'signataire_2')
    ordering = ('-date_facture', 'fournisseur')

    fieldsets = (
        ('Informations facture', {
            'fields': ('date_facture', 'fournisseur', 'designation', 'unite', 'prix_unitaire', 'montant', 'total', 'total_lettres')
        }),
        ('Workflow', {
            'fields': ('statut', 'signataire_1', 'date_signature_1', 'signataire_2', 'date_signature_2')
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at')
        })
    )



@admin.register(ConfigTarifForfaitaire)
class ConfigTarifForfaitaireAdmin(admin.ModelAdmin):
    """Tarifs pleins par type de point d'eau. Un changement de tarif = nouvelle ligne avec sa date
    de début (mettre une date de fin à l'ancienne). Les montants des points sont recalculés à
    l'enregistrement."""
    list_display = ('type_point_eau', 'tarif', 'date_debut', 'date_fin')
    list_filter = ('type_point_eau',)
    ordering = ('type_point_eau__nom_type', '-date_debut')
