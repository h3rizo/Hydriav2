from django.contrib import admin
from django.contrib.admin import helpers
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.contrib import messages
from django.urls import reverse
from django.utils.html import format_html
from apps.core.admin_safe import SafeProtectedDeletionMixin
from .models import (
    Organisation,
    PartenaireGestionnaireAffectation,
    TypeOuvrage,
    Ouvrage,
    OuvrageAlias,
    Base,
    Magasin,
    Journal,
    Compte,
    OuvrageGradingAnnuel,
)


@admin.register(Organisation)
class OrganisationAdmin(SafeProtectedDeletionMixin, admin.ModelAdmin):
    list_display = ('nom_organisation', 'type_organisation', 'localite', 'province', 'telephone', 'mail')
    search_fields = ('nom_organisation', 'localite', 'province', 'nif', 'stat')
    list_filter = ('type_organisation', 'province')
    ordering = ('nom_organisation',)

    fieldsets = (
        ('Informations générales', {
            'fields': ('nom_organisation', 'type_organisation', 'telephone', 'mail', 'logo')
        }),
        ('Adresse', {
            'fields': ('adresse1', 'adresse2', 'code_postal', 'localite', 'province')
        }),
        ('Informations administratives', {
            'fields': ('nif', 'stat', 'numero_cnaps'),
            'classes': ('collapse',)
        }),
        ('Tarifs et paramètres', {
            'fields': (
                'tarif_carte_sociale', 'tarif_demande', 'tarif_minimum_bp',
                'tarif_demande_bp', 'tarif_devis_bp', 'tarif_metre_supplementaire'
            ),
            'classes': ('collapse',)
        })
    )

    # Configuration des relations protégées pour Organisation
    PROTECTED_RELATIONS = {
        'bases': {
            'verbose_name': 'base(s)',
            'display_attr': 'nom_base',
            'solutions': [
                "Supprimer d'abord toutes les bases de cette organisation",
                "Chaque base peut avoir ses propres contraintes (employés, magasins, journaux)"
            ]
        },
        'ouvrages': {
            'verbose_name': 'ouvrage(s)',
            'display_attr': 'nom_ouvrage',
            'solutions': [
                "Supprimer d'abord tous les ouvrages de cette organisation"
            ]
        },
        'postes': {
            'verbose_name': 'poste(s)',
            'display_attr': 'nom_poste',
            'solutions': [
                "Supprimer d'abord tous les postes de cette organisation"
            ]
        },
        'comptes': {
            'verbose_name': 'compte(s)',
            'display_attr': 'nom_compte',
            'solutions': [
                "Supprimer d'abord tous les comptes de cette organisation"
            ]
        }
    }


@admin.register(PartenaireGestionnaireAffectation)
class PartenaireGestionnaireAffectationAdmin(admin.ModelAdmin):
    list_display = ('partenaire', 'gestionnaire', 'created_at')
    search_fields = (
        'partenaire__nom_organisation',
        'gestionnaire__nom_organisation',
    )
    list_filter = (
        'partenaire__nom_organisation',
        'gestionnaire__nom_organisation',
    )
    autocomplete_fields = ('partenaire', 'gestionnaire')

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'partenaire':
            kwargs['queryset'] = Organisation.objects.filter(
                type_organisation=Organisation.TYPE_PARTENAIRE
            ).order_by('nom_organisation')
        elif db_field.name == 'gestionnaire':
            kwargs['queryset'] = Organisation.objects.filter(
                type_organisation=Organisation.TYPE_GESTIONNAIRE
            ).order_by('nom_organisation')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(TypeOuvrage)
class TypeOuvrageAdmin(admin.ModelAdmin):
    list_display = ('nom_type_ouvrage',)
    search_fields = ('nom_type_ouvrage',)
    ordering = ('nom_type_ouvrage',)


@admin.register(Ouvrage)
class OuvrageAdmin(admin.ModelAdmin):
    list_display = (
        'nom_ouvrage', 'type_ouvrage', 'ouvrage_source',
        'annee_realisation', 'intervenant', 'saisonnier', 'marque_non_fonctionnel'
    )
    list_filter = ('type_ouvrage', 'saisonnier', 'marque_non_fonctionnel', 'annee_realisation')
    search_fields = (
        'nom_ouvrage',
        'type_ouvrage__nom_type_ouvrage', 'intervenant'
    )
    ordering = ('nom_ouvrage',)

    fieldsets = (
        ('Informations principales', {
            'fields': ('nom_ouvrage', 'type_ouvrage', 'ouvrage_source')
        }),
        ('Réalisation', {
            'fields': ('annee_realisation', 'annee_realisation_avant', 'intervenant')
        }),
        ('Caractéristiques', {
            'fields': ('saisonnier', 'marque_non_fonctionnel', 'observation', 'photo')
        }),
        ('Données techniques', {
            'fields': ('idxlsx',),
            'classes': ('collapse',)
        })
    )


@admin.register(OuvrageAlias)
class OuvrageAliasAdmin(admin.ModelAdmin):
    list_display = ('alias', 'ouvrage', 'created_at')
    search_fields = ('alias', 'ouvrage__nom_ouvrage')
    autocomplete_fields = ('ouvrage',)
    ordering = ('ouvrage__nom_ouvrage', 'alias')
    readonly_fields = ('alias_normalise', 'created_at')


@admin.register(Base)
class BaseAdmin(SafeProtectedDeletionMixin, admin.ModelAdmin):
    list_display = ('nom_base', 'organisation', 'ouvrage', 'volet')
    list_filter = ('organisation', 'volet')
    search_fields = ('nom_base', 'organisation__nom_organisation', 'ouvrage__nom_ouvrage')
    ordering = ('organisation__nom_organisation', 'nom_base')
    autocomplete_fields = ('village_depart',)

    fieldsets = (
        ('Informations principales', {
            'fields': ('nom_base', 'organisation', 'ouvrage', 'volet')
        }),
        ('Lieu de départ des déplacements', {
            'fields': ('village_depart', 'latitude_depart', 'longitude_depart'),
            'description': "Sert au calcul des trajets et des durées (contrôle des frais de déplacement). "
                           "La page Géographie → « Lieux des bases » permet de placer la base sur une carte.",
        }),
        ('Configuration Diamex', {
            'fields': ('base_diamex', 'chemin_base_diamex', 'prog_diamex'),
            'classes': ('collapse',)
        }),
        ('Journal', {
            'fields': ('journal_retour',),
            'classes': ('collapse',)
        })
    )

    # Configuration des relations protegees
    PROTECTED_RELATIONS = {
        'employes': {
            'verbose_name': 'employe(s)',
            'display_attr': 'nom_complet',
            'solutions': [
                "Supprimer d'abord les employes concernes",
                "Ou reaffecter ces employes a une autre base",
                "Puis relancer la suppression de la base"
            ]
        },
        'magasins': {
            'verbose_name': 'magasin(s)',
            'display_attr': 'nom_magasin',
            'solutions': [
                "Supprimer d'abord les magasins concernes"
            ]
        },
        'journaux': {
            'verbose_name': 'journal/journaux',
            'display_attr': 'nom_journal',
            'solutions': [
                "Supprimer d'abord les journaux concernes"
            ]
        }
    }


@admin.register(Magasin)
class MagasinAdmin(admin.ModelAdmin):
    list_display = ('nom_magasin', 'base', 'organisation')
    list_filter = ('base__organisation',)
    search_fields = ('nom_magasin', 'base__nom_base', 'base__organisation__nom_organisation')
    ordering = ('base__organisation__nom_organisation', 'base__nom_base', 'nom_magasin')

    def organisation(self, obj):
        return obj.base.organisation.nom_organisation
    organisation.short_description = 'Organisation'


@admin.register(Journal)
class JournalAdmin(admin.ModelAdmin):
    list_display = ('nom_journal', 'base', 'compte', 'code', 'organisation')
    list_filter = ('base__organisation',)
    search_fields = (
        'nom_journal', 'base__nom_base', 'base__organisation__nom_organisation',
        'compte', 'code'
    )
    ordering = ('base__organisation__nom_organisation', 'base__nom_base', 'nom_journal')

    def organisation(self, obj):
        return obj.base.organisation.nom_organisation
    organisation.short_description = 'Organisation'


@admin.register(Compte)
class CompteAdmin(admin.ModelAdmin):
    list_display = ('nom_compte', 'compte', 'organisation', 'financement', 'achat', 'fournisseur_obligatoire', 'employe_obligatoire', 'compte_vehicule', 'compte_ouvrage_analyse', 'necessite_ouvrage', 'a_recouper_hydria_diamex')
    list_filter = ('organisation', 'financement', 'achat', 'fournisseur_obligatoire', 'employe_obligatoire', 'compte_vehicule', 'compte_ouvrage_analyse', 'necessite_ouvrage', 'a_recouper_hydria_diamex')
    search_fields = ('nom_compte', 'compte', 'organisation__nom_organisation')
    ordering = ('organisation__nom_organisation', 'nom_compte')

    fieldsets = (
        ('Informations principales', {
            'fields': ('nom_compte', 'compte', 'organisation')
        }),
        ('Configuration', {
            'fields': ('financement', 'achat', 'a_recouper_hydria_diamex', 'detail')
        }),
        ('Règles DiameX', {
            'fields': ('fournisseur_obligatoire', 'employe_obligatoire', 'compte_vehicule', 'compte_ouvrage_analyse', 'necessite_ouvrage'),
            'description': (
                "Catégorisation du compte. 'Nécessite ouvrage' impacte le contrôle DiameX ; "
                "'Compte à répartir sur un ouvrage' ne sert qu'à l'analyse des coûts."
            )
        })
    )


@admin.register(OuvrageGradingAnnuel)
class OuvrageGradingAnnuelAdmin(admin.ModelAdmin):
    list_display = ('ouvrage', 'annee', 'grade', 'source', 'updated_at')
    list_filter = ('annee', 'grade', 'source')
    search_fields = ('ouvrage__nom_ouvrage', 'observation')
    ordering = ('-annee', 'ouvrage__nom_ouvrage')
