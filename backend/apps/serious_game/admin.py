from django.contrib import admin

from .models import (
    GameLevelBest,
    GameRun,
    QuizBadge,
    QuizQuestion,
    QuizReponse,
    QuizSession,
    QuizSessionQuestion,
    QuizTheme,
    QuizUserBadge,
    QuizUserProgress,
)


class QuizReponseInline(admin.TabularInline):
    model = QuizReponse
    extra = 1
    fields = ("ordre_affichage", "texte_reponse", "est_correcte")


@admin.register(QuizTheme)
class QuizThemeAdmin(admin.ModelAdmin):
    list_display = ("nom", "parcours_code", "module_code", "module_precedent", "score_deblocage", "role_cible", "ordre_affichage", "actif")
    list_filter = ("actif", "role_cible", "parcours_code")
    search_fields = ("nom", "description", "role_cible", "module_code")
    ordering = ("ordre_affichage", "nom")


@admin.register(QuizQuestion)
class QuizQuestionAdmin(admin.ModelAdmin):
    list_display = (
        "texte_question",
        "theme",
        "type_question",
        "difficulte",
        "est_dynamique",
        "actif",
        "ordre_affichage",
    )
    list_filter = ("theme", "type_question", "difficulte", "est_dynamique", "actif")
    search_fields = ("texte_question", "explication", "code_generation")
    ordering = ("theme__ordre_affichage", "ordre_affichage", "created_at")
    inlines = [QuizReponseInline]


@admin.register(QuizReponse)
class QuizReponseAdmin(admin.ModelAdmin):
    list_display = ("texte_reponse", "question", "est_correcte", "ordre_affichage")
    list_filter = ("est_correcte", "question__theme")
    search_fields = ("texte_reponse", "question__texte_question")
    ordering = ("question", "ordre_affichage")


class QuizSessionQuestionInline(admin.TabularInline):
    model = QuizSessionQuestion
    extra = 0
    can_delete = False
    readonly_fields = (
        "ordre",
        "question_text",
        "question_type",
        "is_correct",
        "points_earned",
        "user_answer_text",
        "answered_at",
    )


@admin.register(QuizSession)
class QuizSessionAdmin(admin.ModelAdmin):
    list_display = (
        "utilisateur",
        "theme",
        "statut",
        "score",
        "total_questions",
        "pourcentage",
        "xp_gagne",
        "bonus_xp",
        "meilleure_serie",
        "started_at",
    )
    list_filter = ("statut", "theme", "rewards_processed")
    search_fields = ("utilisateur__username", "utilisateur__first_name", "utilisateur__last_name", "theme__nom")
    readonly_fields = ("started_at", "completed_at", "created_at", "updated_at")
    inlines = [QuizSessionQuestionInline]


@admin.register(QuizBadge)
class QuizBadgeAdmin(admin.ModelAdmin):
    list_display = ("code", "nom", "condition_type", "condition_value", "actif")
    list_filter = ("actif", "condition_type")
    search_fields = ("code", "nom", "description")


@admin.register(QuizUserProgress)
class QuizUserProgressAdmin(admin.ModelAdmin):
    list_display = ("user", "level", "total_xp", "current_streak", "best_streak", "quizzes_completed", "last_activity_date")
    search_fields = ("user__username", "user__first_name", "user__last_name")
    readonly_fields = ("created_at", "updated_at")


@admin.register(QuizUserBadge)
class QuizUserBadgeAdmin(admin.ModelAdmin):
    list_display = ("user", "badge", "earned_at")
    list_filter = ("badge",)
    search_fields = ("user__username", "badge__nom", "badge__code")
    readonly_fields = ("earned_at", "created_at", "updated_at")


@admin.register(GameRun)
class GameRunAdmin(admin.ModelAdmin):
    list_display = ("user", "level", "statut", "stars_mask", "xp_gagne", "client_duration_ms", "started_at")
    list_filter = ("level", "statut")
    search_fields = ("user__username", "user__first_name", "user__last_name")
    readonly_fields = (
        "started_at", "finished_at", "updated_at", "quiz_snapshot", "answers", "events", "segments", "assists",
    )


@admin.register(GameLevelBest)
class GameLevelBestAdmin(admin.ModelAdmin):
    list_display = ("user", "level", "best_stars_mask", "best_score", "best_time_ms", "runs_completed", "first_completed_at")
    list_filter = ("level",)
    search_fields = ("user__username", "user__first_name", "user__last_name")
    readonly_fields = ("updated_at",)
