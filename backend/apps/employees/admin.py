from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms import ModelForm
from django.contrib import messages
from apps.core.admin_safe import SafeAdminMixin
from .models import (
    Poste,
    Employe,
    Contrat,
    ConfigSalaire,
    GrilleSalarialeTemplate,
    GrilleSalaire,
    Salaire,
    ContratArticleModele,
    ContratTravail,
    ContratTravailArticle,
    AvenantContratTravail,
    AvenantArticleModifie,
)
from .models_revalorisation import GrilleSalariale
from .models_autonomie import StadeAutonomie, GrilleAutonomie, HistoriqueStadeAutonomie
from .models_conges import JourFerie, TypePermission, DemandeConge, SoldeConge


@admin.register(Poste)
class PosteAdmin(admin.ModelAdmin):
    list_display = ('nom_poste', 'organisation', 'tarif_indemnite')
    list_filter = ('organisation',)
    search_fields = ('nom_poste', 'organisation__nom_organisation')
    ordering = ('nom_poste',)


class HistoriqueStadeAutonomieInline(admin.TabularInline):
    model = HistoriqueStadeAutonomie
    fk_name = 'employe'
    extra = 0
    fields = ('stade', 'date_effet', 'source', 'commentaire')
    autocomplete_fields = ('stade',)
    verbose_name = "Passage de stade d'autonomie"
    verbose_name_plural = "Historique des stades d'autonomie (ancienneté au sommet de grille)"


class EmployeForm(ModelForm):
    """Formulaire personnalisé pour les employés avec validation des contraintes"""

    class Meta:
        model = Employe
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        base = cleaned_data.get('base')
        poste = cleaned_data.get('poste')

        # Vérifier que la base et le poste appartiennent à la même organisation
        if base and poste:
            if base.organisation != poste.organisation:
                raise ValidationError({
                    'poste': f"ERREUR: Le poste '{poste}' appartient a l'organisation '{poste.organisation}' "
                           f"mais la base '{base}' appartient a '{base.organisation}'. "
                           f"\nSOLUTION: Choisissez un poste de la meme organisation que la base.",
                    'base': f"ERREUR: Cette base appartient a l'organisation '{base.organisation}' "
                           f"mais le poste selectionne appartient a '{poste.organisation}'. "
                           f"\nSOLUTION: Choisissez une base de la meme organisation que le poste."
                })

        return cleaned_data


@admin.register(Employe)
class EmployeAdmin(SafeAdminMixin, admin.ModelAdmin):
    form = EmployeForm
    list_display = ('prenom', 'nom', 'poste', 'base', 'date_embauche', 'salarie')
    list_filter = ('poste', 'base__organisation', 'salarie', 'date_embauche')
    search_fields = ('nom', 'prenom', 'surnom', 'numero_cin')
    ordering = ('nom', 'prenom')

    inlines = [HistoriqueStadeAutonomieInline]

    fieldsets = (
        ('Informations personnelles', {
            'fields': ('nom_employe', 'nom', 'prenom', 'surnom', 'numero_cin', 'telephone', 'mail')
        }),
        ('Affectation', {
            'fields': ('base', 'poste'),
            'description': 'IMPORTANT: la base et le poste doivent appartenir a la meme organisation.'
        }),
        ('Statut & Dates', {
            'fields': ('date_embauche', 'date_sortie_junior', 'date_debauchage', 'salarie', 'personnes_charge')
        }),
        ("Grille par autonomie", {
            'fields': ('stade_autonomie_actuel',),
            'description': "Le stade validé en évaluation. Le passage au stade « Autonome 100 % » ou au-dessus "
                           "démarre le comptage de l'ancienneté (voir l'historique ci-dessous).",
        }),
        ('Références', {
            'fields': ('numero_cnaps', 'idxlsx'),
            'classes': ('collapse',)
        })
    )

    def get_form(self, request, obj=None, **kwargs):
        """Personnalise le formulaire pour afficher des informations utiles"""
        form = super().get_form(request, obj, **kwargs)

        if obj and obj.base:
            # Afficher l'organisation de la base actuelle
            organisation = obj.base.organisation
            form.base_fields['base'].help_text = f"Organisation actuelle : {organisation}"
            form.base_fields['poste'].help_text = f"Choisir un poste de l'organisation : {organisation}"

        return form

    def save_model(self, request, obj, form, change):
        """Validation supplémentaire avant sauvegarde"""
        # Vérification finale des contraintes
        if obj.base and obj.poste:
            if obj.base.organisation != obj.poste.organisation:
                self.add_safe_message(
                    request,
                    'error',
                    f"ERREUR DE COHERENCE: Base '{obj.base}' ({obj.base.organisation}) "
                    f"et Poste '{obj.poste}' ({obj.poste.organisation}) "
                    f"appartiennent a des organisations differentes."
                )
                return

        super().save_model(request, obj, form, change)


@admin.register(Contrat)
class ContratAdmin(admin.ModelAdmin):
    list_display = ('employe', 'debut_contrat', 'fin_contrat', 'type_contrat', 'categorie_professionnel', 'is_active')
    list_filter = ('type_contrat', 'categorie_professionnel', 'debut_contrat', 'fin_contrat')
    search_fields = ('employe__nom', 'employe__prenom', 'employe__nom_employe')
    ordering = ('-debut_contrat',)

    fieldsets = (
        ('Employé', {
            'fields': ('employe',)
        }),
        ('Période du contrat', {
            'fields': ('debut_contrat', 'fin_contrat')
        }),
        ('Catégorisation', {
            'fields': ('type_contrat', 'quotite_temps_travail', 'categorie_professionnel')
        })
    )

    def is_active(self, obj):
        return obj.is_active
    is_active.boolean = True
    is_active.short_description = 'Actif'


@admin.register(ContratArticleModele)
class ContratArticleModeleAdmin(admin.ModelAdmin):
    list_display = ('organisation', 'numero_article', 'actif')
    list_filter = ('organisation', 'actif')
    search_fields = ('organisation__nom_organisation', 'contenu_article')
    ordering = ('organisation__nom_organisation', 'numero_article')


@admin.register(ContratTravail)
class ContratTravailAdmin(admin.ModelAdmin):
    list_display = ('contrat', 'organisation', 'statut', 'date_signature', 'date_impression', 'date_classement')
    list_filter = ('organisation', 'statut')
    search_fields = (
        'contrat__employe__nom',
        'contrat__employe__prenom',
        'contrat__employe__nom_employe',
    )
    ordering = ('-date_creation',)


@admin.register(ContratTravailArticle)
class ContratTravailArticleAdmin(admin.ModelAdmin):
    list_display = ('contrat_travail', 'numero_article', 'date_modification')
    search_fields = ('contrat_travail__contrat__employe__nom', 'contenu_article')
    ordering = ('contrat_travail', 'numero_article')


@admin.register(AvenantContratTravail)
class AvenantContratTravailAdmin(admin.ModelAdmin):
    list_display = ('contrat_travail', 'numero_avenant', 'date_effet', 'statut', 'est_applique')
    list_filter = ('statut', 'est_applique')
    search_fields = ('contrat_travail__contrat__employe__nom', 'motif')
    ordering = ('-date_creation',)


@admin.register(AvenantArticleModifie)
class AvenantArticleModifieAdmin(admin.ModelAdmin):
    list_display = ('avenant', 'numero_article')
    search_fields = ('ancien_contenu', 'nouveau_contenu')
    ordering = ('avenant', 'numero_article')


@admin.register(GrilleSalaire)
class GrilleSalaireAdmin(admin.ModelAdmin):
    list_display = (
        'contrat', 'date_salaire', 'salaire_brut_base',
        'salaire_brut_total', 'salaire_net', 'charge_cnaps_employe', 'irsa'
    )
    list_filter = ('date_salaire', 'contrat__employe__poste', 'contrat__employe__base')
    search_fields = (
        'contrat__employe__nom', 'contrat__employe__prenom',
        'contrat__employe__surnom'
    )
    ordering = ('-date_salaire',)
    readonly_fields = (
        'majoration_nuit_gardien', 'majoration_dimanche_gardien',
        'montant_jours_feries_gardien', 'montant_majoration_1er_mai', 'montant_remplacement_gardien',
        'salaire_brut_total', 'charge_cnaps_employe', 'base_imposable',
        'deduction_impots', 'irsa', 'salaire_net'
    )

    fieldsets = (
        ('Contrat et période', {
            'fields': ('contrat', 'date_salaire', 'personnes_charge')
        }),
        ('Objectif salaire', {
            'fields': ('salaire_net_cible', 'salaire_brut_base')
        }),
        ('Temps de travail (gardiens/journaliers)', {
            'fields': (
                'nb_jours_presence', 'nb_jours_feries_gardien', 'a_travaille_1er_mai',
                'nb_heures_remplacement_gardien'
            ),
            'classes': ('collapse',)
        }),
        ('Majorations gardien (calculé automatiquement)', {
            'fields': (
                'majoration_nuit_gardien', 'majoration_dimanche_gardien',
                'montant_jours_feries_gardien', 'montant_majoration_1er_mai', 'montant_remplacement_gardien'
            ),
            'classes': ('collapse',)
        }),
        ('Salaires (calculé automatiquement)', {
            'fields': ('salaire_brut_total', 'salaire_net')
        }),
        ('Cotisations et impôts (calculé automatiquement)', {
            'fields': (
                'charge_cnaps_employe', 'base_imposable',
                'deduction_impots', 'irsa'
            ),
            'classes': ('collapse',)
        })
    )


@admin.register(GrilleSalariale)
class GrilleSalarialeAdmin(admin.ModelAdmin):
    list_display = (
        'poste', 'organisation', 'template', 'anciennete_min', 'anciennete_max',
        'fourchette_basse', 'fourchette_haute', 'mode_fourchette_haute',
        'ratio_annuel_haute', 'date_debut_validite', 'date_fin_validite'
    )
    list_filter = ('organisation', 'template', 'poste', 'date_debut_validite', 'date_fin_validite')
    search_fields = ('poste__nom_poste', 'organisation__nom_organisation', 'template__nom_template')
    ordering = ('organisation__nom_organisation', 'poste__nom_poste', 'anciennete_min', '-date_debut_validite')


@admin.register(GrilleSalarialeTemplate)
class GrilleSalarialeTemplateAdmin(admin.ModelAdmin):
    list_display = (
        'nom_template', 'organisation', 'anciennete_min', 'anciennete_max',
        'mode_fourchette_haute', 'date_debut_validite', 'date_fin_validite'
    )
    list_filter = ('organisation', 'mode_fourchette_haute', 'date_debut_validite', 'date_fin_validite')
    search_fields = ('nom_template', 'organisation__nom_organisation', 'description')
    ordering = ('organisation__nom_organisation', 'nom_template', 'anciennete_min', '-date_debut_validite')


@admin.register(Salaire)
class SalaireAdmin(admin.ModelAdmin):
    list_display = (
        'grille_salaire', 'date_paiement', 'salaire_net_paye',
        'irsa_paye', 'cnaps_paye', 'mutuelle_sante_paye'
    )
    list_filter = ('date_paiement',)
    search_fields = (
        'grille_salaire__contrat__employe__nom',
        'grille_salaire__contrat__employe__prenom'
    )
    ordering = ('-date_paiement',)

    fieldsets = (
        ('Grille de référence', {
            'fields': ('grille_salaire', 'date_paiement')
        }),
        ('Paiements effectués', {
            'fields': ('salaire_net_paye', 'irsa_paye', 'cnaps_paye', 'fmfp_paye', 'mutuelle_sante_paye')
        }),
        ('Numéros Diamex', {
            'fields': (
                'numero_diamex_salaire', 'numero_diamex_irsa', 'numero_diamex_cnaps',
                'numero_diamex_fmfp', 'numero_diamex_mutuelle_sante'
            ),
            'classes': ('collapse',)
        }),
        ('Bases Diamex', {
            'fields': (
                'base_diamex_salaire', 'base_diamex_irsa', 'base_diamex_cnaps',
                'base_diamex_fmfp', 'base_diamex_mutuelle_sante'
            ),
            'classes': ('collapse',)
        })
    )


@admin.register(JourFerie)
class JourFerieAdmin(admin.ModelAdmin):
    list_display = ('date', 'nom', 'type_jour', 'actif')
    list_filter = ('actif', 'type_jour', 'date')
    search_fields = ('nom', 'description')
    ordering = ('date',)


@admin.register(TypePermission)
class TypePermissionAdmin(admin.ModelAdmin):
    list_display = ('evenement', 'nb_jours_accordes', 'actif')
    list_filter = ('actif',)
    search_fields = ('evenement', 'description')
    ordering = ('evenement',)


@admin.register(DemandeConge)
class DemandeCongeAdmin(admin.ModelAdmin):
    list_display = ('employe', 'type_demande', 'date_debut', 'date_fin', 'statut')
    list_filter = ('type_demande', 'statut')
    search_fields = ('employe__nom', 'employe__prenom', 'motif')
    ordering = ('-date_debut',)


@admin.register(SoldeConge)
class SoldeCongeAdmin(admin.ModelAdmin):
    list_display = ('employe', 'mois', 'annee', 'solde_conges_fin', 'solde_permissions_fin')
    list_filter = ('annee', 'mois')
    search_fields = ('employe__nom', 'employe__prenom')
    ordering = ('-annee', '-mois', 'employe__nom')


# ==================== Grille salariale par stade d'autonomie ====================

@admin.register(StadeAutonomie)
class StadeAutonomieAdmin(admin.ModelAdmin):
    list_display = ('nom_stade', 'ordre', 'organisation', 'declenche_anciennete')
    list_editable = ('declenche_anciennete',)
    list_filter = ('organisation', 'declenche_anciennete')
    search_fields = ('nom_stade',)
    ordering = ('organisation', 'ordre')


@admin.register(GrilleAutonomie)
class GrilleAutonomieAdmin(admin.ModelAdmin):
    list_display = (
        'poste', 'stade', 'salaire_net_fixe', 'statut',
        'anciennete_activee', 'anciennete_taux_annuel_pct', 'date_debut_validite',
    )
    list_filter = ('statut', 'anciennete_activee', 'organisation', 'stade')
    search_fields = ('poste__nom_poste',)
    ordering = ('poste', 'stade__ordre', '-date_debut_validite')
    fieldsets = (
        (None, {
            'fields': ('poste', 'stade', 'organisation', 'statut',
                       'date_debut_validite', 'date_fin_validite', 'version_precedente')
        }),
        ('Montants nets', {
            'fields': ('salaire_net_fixe', 'prime_cible', 'prime_maximale')
        }),
        ("Majoration d'ancienneté (anti-plafond)", {
            'fields': ('anciennete_activee', 'anciennete_taux_annuel_pct',
                       'anciennete_mode_capitalisation', 'anciennete_seuil_annees',
                       'anciennete_plafond_annees', 'anciennete_plafond_majoration_pct'),
            'description': "Prise en compte uniquement pour le stade pivot « Autonome 100 % » et les stades supérieurs. "
                           "Les champs vides retombent sur les valeurs par défaut de la Configuration Salaire.",
        }),
    )


@admin.register(HistoriqueStadeAutonomie)
class HistoriqueStadeAutonomieAdmin(admin.ModelAdmin):
    list_display = ('employe', 'stade', 'date_effet', 'source')
    list_filter = ('source', 'stade')
    search_fields = ('employe__nom', 'employe__prenom', 'employe__surnom')
    autocomplete_fields = ('employe', 'stade', 'cree_par')
    ordering = ('-date_effet',)


@admin.register(ConfigSalaire)
class ConfigSalaireAdmin(admin.ModelAdmin):
    """Singleton : la table ne doit contenir qu'une ligne."""
    list_display = ('salaire_minimum', 'taux_anciennete_autonomie_defaut_pct',
                    'plafond_anciennete_autonomie_annees', 'updated_at')
    fieldsets = (
        ('Paie', {
            'fields': ('salaire_minimum', 'deduction_irsa', 'minimum_irsa',
                       'indemnite_hors_zone', 'indemnite_terrain', 'indemnite_herizo')
        }),
        ('Grille par autonomie — contrôles de cohérence', {
            'fields': ('remuneration_nette_min_autorisee', 'remuneration_nette_max_autorisee',
                       'seuil_alerte_progression_pct')
        }),
        ('Grille par autonomie — majoration d\u2019ancienneté (valeurs par défaut)', {
            'fields': ('taux_anciennete_autonomie_defaut_pct', 'plafond_anciennete_autonomie_annees'),
            'description': "Appliquées quand une grille active la majoration d'ancienneté sans préciser son propre taux / plafond.",
        }),
    )

    def has_add_permission(self, request):
        return not ConfigSalaire.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
