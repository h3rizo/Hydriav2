from django.contrib import admin

from .models import Commune, District, Fokontany, LiaisonVillage, Parcelle, Region, Village


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ('nom_region',)
    search_fields = ('nom_region',)
    ordering = ('nom_region',)


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ('nom_district', 'region')
    list_filter = ('region',)
    search_fields = ('nom_district', 'region__nom_region')
    ordering = ('region__nom_region', 'nom_district')


@admin.register(Commune)
class CommuneAdmin(admin.ModelAdmin):
    list_display = ('nom_commune', 'district', 'region')
    list_filter = ('district__region', 'district')
    search_fields = ('nom_commune', 'district__nom_district', 'district__region__nom_region')
    ordering = ('district__region__nom_region', 'district__nom_district', 'nom_commune')

    def region(self, obj):
        return obj.district.region.nom_region


@admin.register(Fokontany)
class FokontanyAdmin(admin.ModelAdmin):
    list_display = ('nom_fokontany', 'commune', 'district', 'region')
    list_filter = ('commune__district__region', 'commune__district', 'commune')
    search_fields = (
        'nom_fokontany',
        'commune__nom_commune',
        'commune__district__nom_district',
        'commune__district__region__nom_region',
    )
    ordering = (
        'commune__district__region__nom_region',
        'commune__district__nom_district',
        'commune__nom_commune',
        'nom_fokontany',
    )

    def district(self, obj):
        return obj.commune.district.nom_district

    def region(self, obj):
        return obj.commune.district.region.nom_region


@admin.register(Village)
class VillageAdmin(admin.ModelAdmin):
    list_display = ('nom_village', 'fokontany', 'commune', 'district', 'region')
    list_filter = ('fokontany__commune__district__region', 'fokontany__commune__district', 'fokontany__commune', 'fokontany')
    search_fields = (
        'nom_village',
        'fokontany__nom_fokontany',
        'fokontany__commune__nom_commune',
        'fokontany__commune__district__nom_district',
        'fokontany__commune__district__region__nom_region',
    )
    ordering = (
        'fokontany__commune__district__region__nom_region',
        'fokontany__commune__district__nom_district',
        'fokontany__commune__nom_commune',
        'fokontany__nom_fokontany',
        'nom_village',
    )

    def commune(self, obj):
        return obj.fokontany.commune.nom_commune if obj.fokontany_id else None

    def district(self, obj):
        return obj.fokontany.commune.district.nom_district if obj.fokontany_id else None

    def region(self, obj):
        return obj.fokontany.commune.district.region.nom_region if obj.fokontany_id else None


@admin.register(Parcelle)
class ParcelleAdmin(admin.ModelAdmin):
    list_display = ('reference_parcelle', 'village', 'nombre_habitants', 'nombre_menages', 'source_donnees', 'fokontany', 'commune', 'district', 'region')
    list_filter = (
        'village__fokontany__commune__district__region',
        'village__fokontany__commune__district',
        'village__fokontany__commune',
        'village__fokontany',
        'village',
        'source_donnees',
    )
    search_fields = (
        'reference_parcelle',
        'village__nom_village',
        'village__fokontany__nom_fokontany',
        'village__fokontany__commune__nom_commune',
        'village__fokontany__commune__district__nom_district',
        'village__fokontany__commune__district__region__nom_region',
        'source_donnees',
    )
    ordering = (
        'village__fokontany__commune__district__region__nom_region',
        'village__fokontany__commune__district__nom_district',
        'village__fokontany__commune__nom_commune',
        'village__fokontany__nom_fokontany',
        'village__nom_village',
        'reference_parcelle',
    )

    def fokontany(self, obj):
        return obj.village.fokontany.nom_fokontany if obj.village_id and obj.village.fokontany_id else None

    def commune(self, obj):
        return obj.village.fokontany.commune.nom_commune if obj.village_id and obj.village.fokontany_id else None

    def district(self, obj):
        return obj.village.fokontany.commune.district.nom_district if obj.village_id and obj.village.fokontany_id else None

    def region(self, obj):
        return obj.village.fokontany.commune.district.region.nom_region if obj.village_id and obj.village.fokontany_id else None


@admin.register(LiaisonVillage)
class LiaisonVillageAdmin(admin.ModelAdmin):
    list_display = ('village_source', 'village_cible', 'type_liaison', 'ordre', 'actif')
    list_filter = ('type_liaison', 'actif')
    search_fields = ('village_source__nom_village', 'village_cible__nom_village')
    ordering = ('ordre', 'village_source__nom_village', 'village_cible__nom_village')
