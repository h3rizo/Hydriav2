"""Admin en lecture seule pour auditer le circuit de pointage manuel.

Les décisions ne se prennent que via la page /comptabilite/pointage-mensuel/ ;
l'admin sert uniquement à consulter l'historique.
"""
from django.contrib import admin

from .ai_prefill.models_ai_prefill import ScanExtraction
from .models_pointage import DecisionPointage, MoisPointage, ObjetPointage
from .models_regles_saisie import CompteFournisseurAutorise, RegleSaisieCompte


class _LectureSeuleAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MoisPointage)
class MoisPointageAdmin(_LectureSeuleAdmin):
    list_display = ('fichier_source', 'periode', 'valide_le', 'valide_par')
    list_filter = ('fichier_source', 'periode')
    search_fields = ('fichier_source',)
    date_hierarchy = 'periode'
    ordering = ('-periode', 'fichier_source')


@admin.register(ObjetPointage)
class ObjetPointageAdmin(_LectureSeuleAdmin):
    list_display = ('mois', 'nature', 'cle', 'niveau', 'correction')
    list_filter = ('nature', 'niveau', 'correction', 'mois__fichier_source')
    search_fields = ('cle',)
    ordering = ('-mois__periode', 'cle')


@admin.register(DecisionPointage)
class DecisionPointageAdmin(_LectureSeuleAdmin):
    list_display = ('cree_le', 'mois', 'objet', 'auteur_libelle', 'role', 'action')
    list_filter = ('action', 'role', 'mois__fichier_source')
    search_fields = ('auteur_libelle', 'remarque', 'objet__cle')
    date_hierarchy = 'cree_le'
    ordering = ('-cree_le',)


@admin.register(ScanExtraction)
class ScanExtractionAdmin(_LectureSeuleAdmin):
    """Journal des extractions IA de justificatifs (suivi couts / qualite)."""
    list_display = ('created_at', 'source_name', 'model', 'status', 'montant_extrait',
                    'tokens_in', 'tokens_out', 'cout_usd', 'latence_ms')
    list_filter = ('status', 'model', 'created_at')
    search_fields = ('source_name', 'file_sha256', 'request_id')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)

    @admin.display(description='Montant extrait')
    def montant_extrait(self, obj):
        try:
            return (obj.extracted or {}).get('montant_total')
        except Exception:
            return None


@admin.register(RegleSaisieCompte)
class RegleSaisieCompteAdmin(admin.ModelAdmin):
    list_display = ('compte_cible', 'est_prefixe', 'mode', 'sens', 'libelle', 'organisation', 'actif')
    list_filter = ('mode', 'sens', 'est_prefixe', 'actif', 'organisation')
    search_fields = ('compte_cible', 'libelle')
    ordering = ('organisation__nom_organisation', 'compte_cible')


@admin.register(CompteFournisseurAutorise)
class CompteFournisseurAutoriseAdmin(admin.ModelAdmin):
    list_display = ('compte_code', 'fournisseur', 'organisation', 'created_at')
    list_filter = ('organisation',)
    search_fields = ('compte_code', 'fournisseur__nom_fournisseur')
    autocomplete_fields = ('fournisseur',)
