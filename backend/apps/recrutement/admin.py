"""
Configuration Admin pour le module de recrutement
"""
from django.contrib import admin
from .models import CandidatPreconfigure, Candidat, QuestionTest, SessionTest, ReponseCandidat


@admin.register(CandidatPreconfigure)
class CandidatPreconfigureAdmin(admin.ModelAdmin):
    """Admin pour les candidats préconfigurés"""
    list_display = ('email', 'poste', 'date_creation', 'test_complete', 'candidat')
    list_filter = ('test_complete', 'poste', 'date_creation')
    search_fields = ('email',)
    readonly_fields = ('date_creation', 'candidat', 'test_complete')

    fieldsets = (
        ('Préconfiguration', {
            'fields': ('email', 'poste')
        }),
        ('Statut', {
            'fields': ('test_complete', 'candidat', 'date_creation')
        }),
    )

    def get_queryset(self, request):
        """Optimiser les requêtes"""
        qs = super().get_queryset(request)
        return qs.select_related('poste', 'candidat')


@admin.register(Candidat)
class CandidatAdmin(admin.ModelAdmin):
    """Admin pour les candidats"""
    list_display = ('nom', 'prenom', 'email', 'poste_souhaite', 'statut')
    list_filter = ('statut', 'poste_souhaite')
    search_fields = ('nom', 'prenom', 'email', 'telephone')

    fieldsets = (
        ('Informations personnelles', {
            'fields': ('user', 'nom', 'prenom', 'email', 'telephone')
        }),
        ('Candidature', {
            'fields': ('poste_souhaite', 'experience', 'formation', 'cv', 'lettre_motivation')
        }),
        ('Statut', {
            'fields': ('statut',)
        }),
    )


@admin.register(QuestionTest)
class QuestionTestAdmin(admin.ModelAdmin):
    """Admin pour les questions de test"""
    list_display = ('texte_question', 'poste', 'type_question', 'points', 'ordre', 'active')
    list_filter = ('poste', 'type_question', 'active')
    search_fields = ('texte_question',)
    list_editable = ('ordre', 'active')

    fieldsets = (
        ('Question', {
            'fields': ('poste', 'type_question', 'texte_question', 'ordre')
        }),
        ('Options et réponse', {
            'fields': ('options_qcm', 'reponse_correcte', 'points')
        }),
        ('Statut', {
            'fields': ('active',)
        }),
    )

    def get_queryset(self, request):
        """Trier par poste et ordre"""
        qs = super().get_queryset(request)
        return qs.select_related('poste').order_by('poste__ordre_affichage', 'poste__nom_poste', 'ordre')


@admin.register(SessionTest)
class SessionTestAdmin(admin.ModelAdmin):
    """Admin pour les sessions de test"""
    list_display = ('candidat', 'date_debut', 'date_fin', 'statut', 'score_obtenu', 'score_total', 'pourcentage')
    list_filter = ('statut', 'date_debut')
    search_fields = ('candidat__nom', 'candidat__prenom', 'candidat__email')
    readonly_fields = ('score_obtenu', 'score_total', 'pourcentage')

    fieldsets = (
        ('Candidat', {
            'fields': ('candidat',)
        }),
        ('Timing', {
            'fields': ('date_debut', 'date_fin', 'duree_limite')
        }),
        ('Résultats', {
            'fields': ('statut', 'score_obtenu', 'score_total', 'pourcentage')
        }),
    )

    def get_queryset(self, request):
        """Optimiser les requêtes"""
        qs = super().get_queryset(request)
        return qs.select_related('candidat', 'candidat__poste_souhaite')


@admin.register(ReponseCandidat)
class ReponseCandidatAdmin(admin.ModelAdmin):
    """Admin pour les réponses des candidats"""
    list_display = ('session', 'question', 'est_correcte', 'points_obtenus')
    list_filter = ('est_correcte', 'session__statut')
    search_fields = ('session__candidat__nom', 'session__candidat__prenom', 'question__texte_question')
    readonly_fields = ('est_correcte', 'points_obtenus')

    fieldsets = (
        ('Réponse', {
            'fields': ('session', 'question', 'reponse_donnee')
        }),
        ('Évaluation', {
            'fields': ('est_correcte', 'points_obtenus')
        }),
    )

    def get_queryset(self, request):
        """Optimiser les requêtes"""
        qs = super().get_queryset(request)
        return qs.select_related('session', 'session__candidat', 'question')
