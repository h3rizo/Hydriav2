from django.contrib import admin
from django.utils.html import format_html
from .models import (
    PointDeControle,
    Checklist,
    ChecklistPointControle,
    Visite,
    ResultatControle,
    # Nouveaux modèles
    ComposantTypeEquipement,
    ComposantTypePointEau,
    PointDeControleComposant,
    Inspection,
    ResultatInspectionComposant,
    ActionCorrective
)


@admin.register(PointDeControle)
class PointDeControleAdmin(admin.ModelAdmin):
    """Administration des points de contrôle."""
    list_display = ['nom', 'type_resultat', 'valeur_min', 'valeur_max', 'unite', 'created_at']
    list_filter = ['type_resultat', 'created_at']
    search_fields = ['nom', 'description']
    ordering = ['nom']


class ChecklistPointControleInline(admin.TabularInline):
    """Inline pour les points de contrôle d'une checklist."""
    model = ChecklistPointControle
    extra = 1
    ordering = ['ordre']


@admin.register(Checklist)
class ChecklistAdmin(admin.ModelAdmin):
    """Administration des checklists."""
    list_display = ['nom', 'equipement_constitutif', 'type_visite', 'frequence_jours', 'is_active']
    list_filter = ['type_visite', 'is_active', 'equipement_constitutif__type_equipement']
    search_fields = ['nom', 'equipement_constitutif__nom']
    inlines = [ChecklistPointControleInline]


@admin.register(Visite)
class VisiteAdmin(admin.ModelAdmin):
    """Administration des visites."""
    list_display = ['ouvrage', 'agent', 'date_visite', 'type_visite', 'statut', 'nombre_anomalies']
    list_filter = ['type_visite', 'statut', 'date_visite', 'ouvrage']
    search_fields = ['ouvrage__nom', 'agent__first_name', 'agent__last_name']
    readonly_fields = ['nombre_anomalies']
    date_hierarchy = 'date_visite'
    
    def nombre_anomalies(self, obj):
        """Affiche le nombre d'anomalies détectées."""
        return obj.nombre_anomalies
    nombre_anomalies.short_description = 'Anomalies'


@admin.register(ResultatControle)
class ResultatControleAdmin(admin.ModelAdmin):
    """Administration des résultats de contrôle."""
    list_display = [
        'point_de_controle', 'equipement', 'visite', 'resultat_display', 
        'est_conforme', 'necessite_action', 'heure_controle'
    ]
    list_filter = [
        'necessite_action', 'point_de_controle__type_resultat', 
        'equipement__type_equipement', 'heure_controle'
    ]
    search_fields = [
        'point_de_controle__nom', 'equipement__nom', 
        'visite__ouvrage__nom', 'commentaire'
    ]
    readonly_fields = ['resultat_display', 'est_conforme']
    date_hierarchy = 'heure_controle'
    
    def resultat_display(self, obj):
        """Affiche le résultat de manière formatée."""
        result = obj.resultat_display
        if obj.est_conforme is False:
            return format_html('<span style="color: red;">{}</span>', result)
        elif obj.est_conforme is True:
            return format_html('<span style="color: green;">{}</span>', result)
        return result
    resultat_display.short_description = 'Résultat'
    
    def est_conforme(self, obj):
        """Indicateur de conformité."""
        if obj.est_conforme is True:
            return format_html('<span style="color: green;">✓</span>')
        elif obj.est_conforme is False:
            return format_html('<span style="color: red;">✗</span>')
        return '-'
    est_conforme.short_description = 'Conforme'


# ============================================
# ADMINISTRATION DES NOUVEAUX MODÈLES
# ============================================

@admin.register(ComposantTypeEquipement)
class ComposantTypeEquipementAdmin(admin.ModelAdmin):
    """Administration des composants de types d'équipements."""
    list_display = ['nom_composant', 'type_equipement', 'ordre_affichage', 'est_obligatoire', 'created_at']
    list_filter = ['type_equipement', 'est_obligatoire', 'created_at']
    search_fields = ['nom_composant', 'description', 'type_equipement__nom_type']
    ordering = ['type_equipement__nom_type', 'ordre_affichage', 'nom_composant']


@admin.register(ComposantTypePointEau)
class ComposantTypePointEauAdmin(admin.ModelAdmin):
    """Administration des composants de types de points d'eau."""
    list_display = ['nom_composant', 'type_point_eau', 'ordre_affichage', 'est_obligatoire', 'created_at']
    list_filter = ['type_point_eau', 'est_obligatoire', 'created_at']
    search_fields = ['nom_composant', 'description', 'type_point_eau__nom_type']
    ordering = ['type_point_eau__nom_type', 'ordre_affichage', 'nom_composant']


@admin.register(PointDeControleComposant)
class PointDeControleComposantAdmin(admin.ModelAdmin):
    """Administration des liaisons points de contrôle - composants."""
    list_display = ['point_de_controle', 'get_composant', 'est_obligatoire', 'ordre_affichage']
    list_filter = ['est_obligatoire', 'composant_equipement__type_equipement', 'composant_point_eau__type_point_eau']
    search_fields = [
        'point_de_controle__nom',
        'composant_equipement__nom_composant',
        'composant_point_eau__nom_composant'
    ]
    ordering = ['ordre_affichage']

    def get_composant(self, obj):
        """Retourne le composant associé."""
        return obj.composant_equipement or obj.composant_point_eau
    get_composant.short_description = 'Composant'


class ResultatInspectionComposantInline(admin.TabularInline):
    """Inline pour les résultats d'inspection par composant."""
    model = ResultatInspectionComposant
    extra = 0
    readonly_fields = ['conforme']


@admin.register(Inspection)
class InspectionAdmin(admin.ModelAdmin):
    """Administration des inspections."""
    list_display = [
        'numero_inspection', 'get_objet_inspecte', 'inspecteur',
        'date_inspection', 'statut', 'conforme_global', 'score_global'
    ]
    list_filter = ['statut', 'conforme_global', 'date_inspection']
    search_fields = [
        'numero_inspection', 'equipement__nom', 'point_eau__nomabonne',
        'inspecteur__first_name', 'inspecteur__last_name'
    ]
    readonly_fields = ['numero_inspection', 'conforme_global', 'score_global']
    date_hierarchy = 'date_inspection'
    inlines = [ResultatInspectionComposantInline]

    def get_objet_inspecte(self, obj):
        """Retourne l'objet inspecté."""
        return obj.objet_inspecte
    get_objet_inspecte.short_description = 'Objet inspecté'


@admin.register(ResultatInspectionComposant)
class ResultatInspectionComposantAdmin(admin.ModelAdmin):
    """Administration des résultats d'inspection par composant."""
    list_display = [
        'inspection', 'get_composant', 'point_de_controle',
        'valeur_mesuree', 'conforme', 'niveau_gravite', 'date_mesure'
    ]
    list_filter = [
        'conforme', 'niveau_gravite', 'date_mesure',
        'composant_equipement__type_equipement',
        'composant_point_eau__type_point_eau'
    ]
    search_fields = [
        'inspection__numero_inspection', 'point_de_controle__nom',
        'observations', 'valeur_mesuree'
    ]
    readonly_fields = ['conforme']
    date_hierarchy = 'date_mesure'

    def get_composant(self, obj):
        """Retourne le composant associé."""
        return obj.composant
    get_composant.short_description = 'Composant'


class ActionCorrectiveInline(admin.TabularInline):
    """Inline pour les actions correctives."""
    model = ActionCorrective
    extra = 0


@admin.register(ActionCorrective)
class ActionCorrectiveAdmin(admin.ModelAdmin):
    """Administration des actions correctives."""
    list_display = [
        'titre', 'get_inspection', 'priorite', 'statut',
        'responsable', 'date_prevue', 'est_en_retard'
    ]
    list_filter = ['priorite', 'statut', 'date_prevue', 'date_creation']
    search_fields = ['titre', 'description', 'responsable__first_name', 'responsable__last_name']
    readonly_fields = ['est_en_retard']
    date_hierarchy = 'date_prevue'

    def get_inspection(self, obj):
        """Retourne l'inspection liée."""
        return obj.resultat_inspection.inspection.numero_inspection
    get_inspection.short_description = 'Inspection'

    def est_en_retard(self, obj):
        """Indicateur de retard."""
        if obj.est_en_retard:
            return format_html('<span style="color: red;">⚠️ En retard</span>')
        return format_html('<span style="color: green;">✓ À jour</span>')
    est_en_retard.short_description = 'Statut'
