import uuid

from django.conf import settings
from django.db import models


class QuizTheme(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nom = models.CharField(max_length=255, verbose_name="Nom")
    description = models.TextField(blank=True, verbose_name="Description")
    role_cible = models.CharField(max_length=120, blank=True, verbose_name="Role cible")
    parcours_code = models.CharField(max_length=80, blank=True, default="", verbose_name="Code parcours")
    module_code = models.CharField(max_length=120, blank=True, default="", verbose_name="Code module")
    icon = models.CharField(max_length=120, blank=True, default="", verbose_name="Icone")
    score_deblocage = models.PositiveIntegerField(default=80, verbose_name="Score de deblocage")
    module_precedent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="modules_suivants",
        verbose_name="Module precedent",
    )
    ordre_affichage = models.PositiveIntegerField(default=0, verbose_name="Ordre d'affichage")
    actif = models.BooleanField(default=True, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "quiz_themes"
        verbose_name = "Theme de quiz"
        verbose_name_plural = "Themes de quiz"
        ordering = ["ordre_affichage", "nom"]

    def __str__(self):
        return self.nom


class QuizQuestion(models.Model):
    TYPE_QCM = "qcm"
    TYPE_VRAI_FAUX = "vrai_faux"
    TYPE_NUMERIQUE = "numerique"
    TYPE_TEXTE = "texte"
    TYPE_CHOICES = [
        (TYPE_QCM, "QCM"),
        (TYPE_VRAI_FAUX, "Vrai / Faux"),
        (TYPE_NUMERIQUE, "Numerique"),
        (TYPE_TEXTE, "Texte"),
    ]

    DIFFICULTE_FACILE = "facile"
    DIFFICULTE_MOYENNE = "moyenne"
    DIFFICULTE_DIFFICILE = "difficile"
    DIFFICULTE_CHOICES = [
        (DIFFICULTE_FACILE, "Facile"),
        (DIFFICULTE_MOYENNE, "Moyenne"),
        (DIFFICULTE_DIFFICILE, "Difficile"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    theme = models.ForeignKey(
        QuizTheme,
        on_delete=models.CASCADE,
        related_name="questions",
        verbose_name="Theme",
    )
    texte_question = models.TextField(verbose_name="Question")
    type_question = models.CharField(max_length=20, choices=TYPE_CHOICES, verbose_name="Type")
    difficulte = models.CharField(
        max_length=20,
        choices=DIFFICULTE_CHOICES,
        default=DIFFICULTE_MOYENNE,
        verbose_name="Difficulte",
    )
    ordre_affichage = models.PositiveIntegerField(default=0, verbose_name="Ordre d'affichage")
    explication = models.TextField(blank=True, verbose_name="Explication")
    actif = models.BooleanField(default=True, verbose_name="Actif")
    est_dynamique = models.BooleanField(default=False, verbose_name="Question dynamique")
    code_generation = models.CharField(max_length=120, blank=True, verbose_name="Code generation")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "quiz_questions"
        verbose_name = "Question de quiz"
        verbose_name_plural = "Questions de quiz"
        ordering = ["theme__ordre_affichage", "ordre_affichage", "created_at"]

    def __str__(self):
        return self.texte_question[:80]


class QuizReponse(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey(
        QuizQuestion,
        on_delete=models.CASCADE,
        related_name="reponses",
        verbose_name="Question",
    )
    texte_reponse = models.CharField(max_length=255, verbose_name="Reponse")
    est_correcte = models.BooleanField(default=False, verbose_name="Correcte")
    ordre_affichage = models.PositiveIntegerField(default=0, verbose_name="Ordre d'affichage")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "quiz_reponses"
        verbose_name = "Reponse de quiz"
        verbose_name_plural = "Reponses de quiz"
        ordering = ["ordre_affichage", "created_at"]

    def __str__(self):
        return self.texte_reponse


class QuizSession(models.Model):
    STATUT_EN_COURS = "en_cours"
    STATUT_TERMINE = "termine"
    STATUT_ABANDONNE = "abandonne"
    STATUT_CHOICES = [
        (STATUT_EN_COURS, "En cours"),
        (STATUT_TERMINE, "Termine"),
        (STATUT_ABANDONNE, "Abandonne"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    utilisateur = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="quiz_sessions",
        verbose_name="Utilisateur",
    )
    theme = models.ForeignKey(
        QuizTheme,
        on_delete=models.CASCADE,
        related_name="sessions",
        verbose_name="Theme",
    )
    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default=STATUT_EN_COURS,
        verbose_name="Statut",
    )
    score = models.PositiveIntegerField(default=0, verbose_name="Score")
    total_questions = models.PositiveIntegerField(default=0, verbose_name="Total questions")
    pourcentage = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="Pourcentage")
    xp_gagne = models.PositiveIntegerField(default=0, verbose_name="XP gagne")
    bonus_xp = models.PositiveIntegerField(default=0, verbose_name="Bonus XP")
    meilleure_serie = models.PositiveIntegerField(default=0, verbose_name="Meilleure serie")
    rewards_processed = models.BooleanField(default=False, verbose_name="Recompenses traitees")
    started_at = models.DateTimeField(auto_now_add=True, verbose_name="Debut")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Fin")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "quiz_sessions"
        verbose_name = "Session de quiz"
        verbose_name_plural = "Sessions de quiz"
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.utilisateur} - {self.theme} - {self.started_at:%d/%m/%Y %H:%M}"


class QuizSessionQuestion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        QuizSession,
        on_delete=models.CASCADE,
        related_name="session_questions",
        verbose_name="Session",
    )
    question = models.ForeignKey(
        QuizQuestion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="session_occurrences",
        verbose_name="Question source",
    )
    ordre = models.PositiveIntegerField(default=0, verbose_name="Ordre")
    question_text = models.TextField(verbose_name="Question affichee")
    question_type = models.CharField(max_length=20, choices=QuizQuestion.TYPE_CHOICES, verbose_name="Type")
    difficulte = models.CharField(
        max_length=20,
        choices=QuizQuestion.DIFFICULTE_CHOICES,
        default=QuizQuestion.DIFFICULTE_MOYENNE,
        verbose_name="Difficulte",
    )
    explication = models.TextField(blank=True, verbose_name="Explication")
    est_dynamique = models.BooleanField(default=False, verbose_name="Question dynamique")
    code_generation = models.CharField(max_length=120, blank=True, verbose_name="Code generation")
    answer_options = models.JSONField(default=list, blank=True, verbose_name="Choix affiches")
    expected_answer = models.JSONField(default=dict, blank=True, verbose_name="Reponse attendue")
    user_answer_text = models.TextField(blank=True, verbose_name="Reponse utilisateur")
    user_answer_payload = models.JSONField(default=dict, blank=True, verbose_name="Payload reponse utilisateur")
    is_correct = models.BooleanField(null=True, blank=True, verbose_name="Bonne reponse")
    points_earned = models.PositiveIntegerField(default=0, verbose_name="Points")
    answered_at = models.DateTimeField(null=True, blank=True, verbose_name="Date reponse")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "quiz_session_questions"
        verbose_name = "Question de session de quiz"
        verbose_name_plural = "Questions de session de quiz"
        ordering = ["session", "ordre", "created_at"]
        unique_together = [("session", "ordre")]

    def __str__(self):
        return f"{self.session_id} - Q{self.ordre}"


class QuizBadge(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=120, unique=True, verbose_name="Code")
    nom = models.CharField(max_length=255, verbose_name="Nom")
    description = models.TextField(blank=True, verbose_name="Description")
    icon = models.CharField(max_length=255, blank=True, default="", verbose_name="Icone")
    condition_type = models.CharField(max_length=120, blank=True, default="", verbose_name="Type de condition")
    condition_value = models.PositiveIntegerField(default=0, verbose_name="Valeur condition")
    actif = models.BooleanField(default=False, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "quiz_badges"
        verbose_name = "Badge de quiz"
        verbose_name_plural = "Badges de quiz"
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class QuizUserProgress(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="quiz_progress",
        verbose_name="Utilisateur",
    )
    total_xp = models.PositiveIntegerField(default=0, verbose_name="XP total")
    level = models.PositiveIntegerField(default=1, verbose_name="Niveau")
    current_streak = models.PositiveIntegerField(default=0, verbose_name="Serie actuelle")
    best_streak = models.PositiveIntegerField(default=0, verbose_name="Meilleure serie")
    quizzes_completed = models.PositiveIntegerField(default=0, verbose_name="Quiz termines")
    last_activity_date = models.DateField(null=True, blank=True, verbose_name="Derniere activite")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "quiz_user_progress"
        verbose_name = "Progression quiz utilisateur"
        verbose_name_plural = "Progressions quiz utilisateurs"

    def __str__(self):
        return f"{self.user} - Niveau {self.level}"


class QuizUserBadge(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="quiz_user_badges",
        verbose_name="Utilisateur",
    )
    badge = models.ForeignKey(
        QuizBadge,
        on_delete=models.CASCADE,
        related_name="user_badges",
        verbose_name="Badge",
    )
    earned_at = models.DateTimeField(auto_now_add=True, verbose_name="Date d'obtention")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "quiz_user_badges"
        verbose_name = "Badge utilisateur de quiz"
        verbose_name_plural = "Badges utilisateurs de quiz"
        unique_together = [("user", "badge")]
        ordering = ["-earned_at"]

    def __str__(self):
        return f"{self.user} - {self.badge}"


# ---------------------------------------------------------------------------
# Hydria Quest 3D (spec §14.1)
# ---------------------------------------------------------------------------


class GameRun(models.Model):
    STATUT_EN_COURS, STATUT_TERMINE, STATUT_ABANDONNE, STATUT_REJETE = "en_cours", "termine", "abandonne", "rejete"
    STATUT_CHOICES = [(STATUT_EN_COURS, "En cours"), (STATUT_TERMINE, "Terminé"), (STATUT_ABANDONNE, "Abandonné"), (STATUT_REJETE, "Rejeté")]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="game3d_runs")
    level = models.PositiveSmallIntegerField()
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default=STATUT_EN_COURS)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    client_duration_ms = models.PositiveIntegerField(default=0)
    # [{slot, source:'db'|'fallback', question_id, fallback_id, theme, question_text, question_type,
    #   answer_options, expected_answer, explication}]
    quiz_snapshot = models.JSONField(default=list, blank=True)
    # [{slot, attempts:[choice_id...], solved:bool, first_try_correct:bool, source:'server'|'client'}]
    answers = models.JSONField(default=list, blank=True)
    quiz_first_try = models.PositiveSmallIntegerField(default=0)
    gouttes = models.PositiveSmallIntegerField(default=0)
    gouttes_total = models.PositiveSmallIntegerField(default=0)
    events = models.JSONField(default=dict, blank=True)
    segments = models.JSONField(default=list, blank=True)
    falls = models.PositiveIntegerField(default=0)
    help_bridges = models.PositiveSmallIntegerField(default=0)
    assists = models.JSONField(default=list, blank=True)
    stars_mask = models.PositiveSmallIntegerField(default=0)
    new_stars_mask = models.PositiveSmallIntegerField(default=0)
    score = models.PositiveIntegerField(default=0)
    xp_etoiles = models.PositiveIntegerField(default=0)
    xp_pratique = models.PositiveIntegerField(default=0)
    xp_bonus = models.PositiveIntegerField(default=0)
    xp_gagne = models.PositiveIntegerField(default=0)
    rewards_processed = models.BooleanField(default=False)
    quality_tier = models.CharField(max_length=12, blank=True, default="")
    client_version = models.CharField(max_length=20, blank=True, default="")
    rejected_reason = models.CharField(max_length=120, blank=True, default="")

    class Meta:
        db_table = "game3d_runs"
        ordering = ["-started_at"]
        indexes = [models.Index(fields=["user", "level", "-started_at"], name="game3d_run_user_lvl_idx")]
        verbose_name = "Partie Hydria Quest 3D"
        verbose_name_plural = "Parties Hydria Quest 3D"

    def __str__(self):
        return f"{self.user} - niveau {self.level} - {self.get_statut_display()}"


class GameLevelBestQuerySet(models.QuerySet):
    def total_stars(self):
        """Nombre total d'etoiles (0-12) des records du queryset.

        Utilisable dans un template via le gestionnaire inverse :
        ``{{ request.user.game3d_bests.total_stars }}``.
        """
        from .game3d_levels import LEVELS

        masks = self.filter(level__in=list(LEVELS.keys())).values_list("best_stars_mask", flat=True)
        return sum(bin(int(mask or 0) & 0b111).count("1") for mask in masks)


class GameLevelBest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="game3d_bests")
    level = models.PositiveSmallIntegerField()
    best_stars_mask = models.PositiveSmallIntegerField(default=0)
    best_score = models.PositiveIntegerField(default=0)
    best_time_ms = models.PositiveIntegerField(null=True, blank=True)
    runs_completed = models.PositiveIntegerField(default=0)
    first_completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = GameLevelBestQuerySet.as_manager()

    class Meta:
        db_table = "game3d_level_best"
        unique_together = [("user", "level")]
        verbose_name = "Record Hydria Quest 3D"
        verbose_name_plural = "Records Hydria Quest 3D"

    def __str__(self):
        return f"{self.user} - niveau {self.level} - etoiles {self.best_stars_mask}"
