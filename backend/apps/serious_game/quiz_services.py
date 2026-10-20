from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Avg, Count, Max
from django.utils import timezone

from .models import (
    QuizBadge,
    QuizQuestion,
    QuizSession,
    QuizSessionQuestion,
    QuizTheme,
    QuizUserBadge,
    QuizUserProgress,
)
from .quiz_generators import GENERATOR_REGISTRY


XP_PER_CORRECT = 10
XP_STREAK_BONUS = 5
XP_FINISH_BONUS = 20


def normalize_answer_text(value):
    return " ".join((value or "").strip().lower().split())


def calculate_level(total_xp):
    xp = max(0, int(total_xp or 0))
    if xp >= 1000:
        return 5
    if xp >= 500:
        return 4
    if xp >= 250:
        return 3
    if xp >= 100:
        return 2
    return 1


def get_level_bounds(level):
    if level <= 1:
        return 0, 100
    if level == 2:
        return 100, 250
    if level == 3:
        return 250, 500
    if level == 4:
        return 500, 1000
    return 1000, None


def get_progress_to_next_level(total_xp):
    level = calculate_level(total_xp)
    level_start, next_threshold = get_level_bounds(level)
    if next_threshold is None:
        return {
            "level": level,
            "progress_percent": 100,
            "current_level_xp": max(0, total_xp - level_start),
            "xp_to_next_level": 0,
            "next_level_threshold": None,
        }

    span = max(1, next_threshold - level_start)
    current_level_xp = max(0, total_xp - level_start)
    return {
        "level": level,
        "progress_percent": int(min(100, round((current_level_xp / span) * 100))),
        "current_level_xp": current_level_xp,
        "xp_to_next_level": max(0, next_threshold - total_xp),
        "next_level_threshold": next_threshold,
    }


def get_or_create_user_progress(user):
    progress, _ = QuizUserProgress.objects.get_or_create(
        user=user,
        defaults={"level": 1, "total_xp": 0},
    )
    return progress


def get_best_scores_by_theme(user):
    rows = (
        QuizSession.objects.filter(utilisateur=user, statut=QuizSession.STATUT_TERMINE)
        .values("theme")
        .annotate(best_score=Max("pourcentage"))
    )
    return {row["theme"]: Decimal(str(row["best_score"] or 0)).quantize(Decimal("0.01")) for row in rows}


def is_theme_unlocked(theme, best_scores_by_theme):
    if not theme.module_precedent_id:
        return True
    previous_score = best_scores_by_theme.get(theme.module_precedent_id, Decimal("0"))
    return previous_score >= Decimal(str(theme.module_precedent.score_deblocage or 80))


def build_theme_module_map(themes, user):
    best_scores_by_theme = get_best_scores_by_theme(user)
    groups = {}
    ordered_themes = list(
        themes.select_related("module_precedent").order_by("parcours_code", "ordre_affichage", "nom")
    )
    first_next_theme_id = None

    for theme in ordered_themes:
        parcours_code = theme.parcours_code or "general"
        best_score = best_scores_by_theme.get(theme.id)
        unlocked = is_theme_unlocked(theme, best_scores_by_theme)
        completed = bool(best_score is not None and best_score >= Decimal(str(theme.score_deblocage or 80)))
        if unlocked and not completed and first_next_theme_id is None:
            first_next_theme_id = theme.id

        groups.setdefault(parcours_code, []).append({
            "theme": theme,
            "best_score": best_score,
            "questions_count": theme.questions.filter(actif=True).count(),
            "unlocked": unlocked,
            "completed": completed,
        })

    parcours_titles = {
        "usage": "Parcours Utilisation Hydria",
        "data": "Parcours Connaissance Terrain",
        "general": "Parcours General",
    }

    parcours_cards = []
    for code, modules in groups.items():
        for module in modules:
            module["is_next_target"] = module["theme"].id == first_next_theme_id
        parcours_cards.append({
            "code": code,
            "title": parcours_titles.get(code, code.replace("_", " ").title()),
            "modules": modules,
        })
    return parcours_cards


def _serialize_static_question(question):
    correct_responses = list(question.reponses.filter(est_correcte=True).order_by("ordre_affichage", "created_at"))
    answer_options = [
        {
            "id": f"choice_{index}",
            "text": response.texte_reponse,
        }
        for index, response in enumerate(question.reponses.order_by("ordre_affichage", "created_at"), start=1)
    ]

    correct_texts = [response.texte_reponse for response in correct_responses]
    expected_answer = {}
    if question.type_question in {QuizQuestion.TYPE_QCM, QuizQuestion.TYPE_VRAI_FAUX}:
        expected_answer["choice_ids"] = [
            option["id"]
            for option in answer_options
            if option["text"] in correct_texts
        ]
    elif question.type_question == QuizQuestion.TYPE_NUMERIQUE:
        expected_answer["numeric_values"] = [normalize_answer_text(value) for value in correct_texts]
    else:
        expected_answer["accepted_texts"] = [normalize_answer_text(value) for value in correct_texts]

    return {
        "question_text": question.texte_question,
        "question_type": question.type_question,
        "difficulte": question.difficulte,
        "explication": question.explication or "",
        "answer_options": answer_options,
        "expected_answer": expected_answer,
        "est_dynamique": False,
        "code_generation": question.code_generation or "",
    }


def _serialize_dynamic_question(question):
    generator = GENERATOR_REGISTRY.get(question.code_generation or "")
    if not generator:
        return None

    generated = generator()
    if not generated:
        return None

    question_type = generated.get("type") or question.type_question
    raw_choices = list(generated.get("choix") or [])
    bonne_reponse = str(generated.get("bonne_reponse", "")).strip()

    answer_options = [
        {
            "id": f"choice_{index}",
            "text": str(choice),
        }
        for index, choice in enumerate(raw_choices, start=1)
    ]
    if question_type in {QuizQuestion.TYPE_QCM, QuizQuestion.TYPE_VRAI_FAUX} and bonne_reponse:
        has_correct = any(option["text"] == bonne_reponse for option in answer_options)
        if not has_correct:
            answer_options.append({"id": f"choice_{len(answer_options) + 1}", "text": bonne_reponse})

    expected_answer = {}
    if question_type in {QuizQuestion.TYPE_QCM, QuizQuestion.TYPE_VRAI_FAUX}:
        expected_answer["choice_ids"] = [
            option["id"]
            for option in answer_options
            if option["text"] == bonne_reponse
        ]
    elif question_type == QuizQuestion.TYPE_NUMERIQUE:
        expected_answer["numeric_values"] = [normalize_answer_text(bonne_reponse)]
    else:
        expected_answer["accepted_texts"] = [normalize_answer_text(bonne_reponse)]

    return {
        "question_text": generated.get("question") or question.texte_question,
        "question_type": question_type,
        "difficulte": question.difficulte,
        "explication": generated.get("explication") or question.explication or "",
        "answer_options": answer_options,
        "expected_answer": expected_answer,
        "est_dynamique": True,
        "code_generation": question.code_generation or "",
    }


def serialize_question_snapshot(question):
    if question.est_dynamique:
        return _serialize_dynamic_question(question)
    return _serialize_static_question(question)


@transaction.atomic
def build_quiz_session(theme, user):
    session = QuizSession.objects.create(
        utilisateur=user,
        theme=theme,
        statut=QuizSession.STATUT_EN_COURS,
    )

    questions = list(
        theme.questions.filter(actif=True).prefetch_related("reponses").order_by("ordre_affichage", "created_at")
    )
    session_questions = []
    ordre = 1
    for question in questions:
        snapshot = serialize_question_snapshot(question)
        if not snapshot:
            continue
        session_questions.append(
            QuizSessionQuestion(
                session=session,
                question=question,
                ordre=ordre,
                question_text=snapshot["question_text"],
                question_type=snapshot["question_type"],
                difficulte=snapshot["difficulte"],
                explication=snapshot["explication"],
                est_dynamique=snapshot["est_dynamique"],
                code_generation=snapshot["code_generation"],
                answer_options=snapshot["answer_options"],
                expected_answer=snapshot["expected_answer"],
            )
        )
        ordre += 1

    QuizSessionQuestion.objects.bulk_create(session_questions)
    session.total_questions = len(session_questions)
    session.save(update_fields=["total_questions", "updated_at"])
    return session


def evaluate_session_question(session_question, submitted_value):
    question_type = session_question.question_type
    expected = session_question.expected_answer or {}
    normalized_value = normalize_answer_text(submitted_value)

    is_correct = False
    user_answer_text = submitted_value or ""
    user_answer_payload = {"raw": submitted_value}

    if question_type in {QuizQuestion.TYPE_QCM, QuizQuestion.TYPE_VRAI_FAUX}:
        is_correct = normalized_value in [normalize_answer_text(v) for v in expected.get("choice_ids", [])]
    elif question_type == QuizQuestion.TYPE_NUMERIQUE:
        accepted = set(expected.get("numeric_values", []))
        try:
            numeric_value = Decimal(str(submitted_value)).normalize()
            normalized_numeric = normalize_answer_text(format(numeric_value, "f").rstrip("0").rstrip(".") or "0")
        except (InvalidOperation, TypeError, ValueError):
            normalized_numeric = normalized_value
        is_correct = normalized_numeric in accepted or normalized_value in accepted
    else:
        is_correct = normalized_value in set(expected.get("accepted_texts", []))

    session_question.user_answer_text = user_answer_text
    session_question.user_answer_payload = user_answer_payload
    session_question.is_correct = is_correct
    session_question.points_earned = 1 if is_correct else 0
    session_question.answered_at = timezone.now()
    session_question.save(
        update_fields=[
            "user_answer_text",
            "user_answer_payload",
            "is_correct",
            "points_earned",
            "answered_at",
            "updated_at",
        ]
    )
    recalculate_session_score(session_question.session)
    return is_correct


def _compute_session_rewards(session):
    streak = 0
    best_streak = 0
    bonus_xp = 0
    correct_answers = 0

    for item in session.session_questions.order_by("ordre", "created_at"):
        if item.is_correct:
            correct_answers += 1
            streak += 1
            best_streak = max(best_streak, streak)
            if streak % 3 == 0:
                bonus_xp += XP_STREAK_BONUS
        else:
            streak = 0

    xp_gagne = correct_answers * XP_PER_CORRECT
    if session.total_questions and session.pourcentage >= Decimal("80.00"):
        bonus_xp += XP_FINISH_BONUS
    return xp_gagne, bonus_xp, best_streak


def _theme_matches(theme_name, fragment):
    return fragment in normalize_answer_text(theme_name)


def check_and_award_badges(user, session):
    if session.statut != QuizSession.STATUT_TERMINE:
        return []

    badges = {badge.code: badge for badge in QuizBadge.objects.filter(actif=True)}
    if not badges:
        return []

    completed_sessions = QuizSession.objects.filter(
        utilisateur=user,
        statut=QuizSession.STATUT_TERMINE,
        rewards_processed=True,
    )
    earned = []

    def award(code):
        badge = badges.get(code)
        if not badge:
            return
        _, created = QuizUserBadge.objects.get_or_create(user=user, badge=badge)
        if created:
            earned.append(badge)

    if completed_sessions.count() >= 1:
        award("first_quiz_completed")
    if completed_sessions.count() >= 5:
        award("five_quizzes_completed")
    if session.pourcentage == Decimal("100.00"):
        award("perfect_score")
    if session.meilleure_serie >= 5:
        award("streak_5_correct")

    theme_name = normalize_answer_text(session.theme.nom)
    if _theme_matches(theme_name, "planning"):
        award("planning_beginner")
    if _theme_matches(theme_name, "encaissement"):
        award("encaissement_beginner")
    if _theme_matches(theme_name, "donnees") or _theme_matches(theme_name, "terrain"):
        award("data_explorer")

    return earned


@transaction.atomic
def finalize_session_rewards(session):
    session = QuizSession.objects.select_for_update().select_related("utilisateur", "theme").get(id=session.id)
    if session.statut != QuizSession.STATUT_TERMINE or session.rewards_processed:
        progress = get_or_create_user_progress(session.utilisateur)
        return progress, []

    progress = get_or_create_user_progress(session.utilisateur)
    xp_gagne, bonus_xp, best_streak = _compute_session_rewards(session)

    progress.total_xp += xp_gagne + bonus_xp
    progress.level = calculate_level(progress.total_xp)
    progress.current_streak = best_streak if session.pourcentage >= Decimal("80.00") else 0
    progress.best_streak = max(progress.best_streak, best_streak)
    progress.quizzes_completed += 1
    progress.last_activity_date = timezone.localdate()
    progress.save(
        update_fields=[
            "total_xp",
            "level",
            "current_streak",
            "best_streak",
            "quizzes_completed",
            "last_activity_date",
            "updated_at",
        ]
    )

    session.xp_gagne = xp_gagne
    session.bonus_xp = bonus_xp
    session.meilleure_serie = best_streak
    session.rewards_processed = True
    session.save(update_fields=["xp_gagne", "bonus_xp", "meilleure_serie", "rewards_processed", "updated_at"])

    earned_badges = check_and_award_badges(session.utilisateur, session)
    return progress, earned_badges


def recalculate_session_score(session):
    questions = session.session_questions.all()
    total_questions = questions.count()
    score = questions.filter(is_correct=True).count()
    answered_count = questions.filter(answered_at__isnull=False).count()
    percentage = Decimal("0")
    if total_questions:
        percentage = (Decimal(score) / Decimal(total_questions)) * Decimal("100")

    became_complete = bool(total_questions and answered_count >= total_questions)
    session.score = score
    session.total_questions = total_questions
    session.pourcentage = percentage.quantize(Decimal("0.01"))
    if became_complete:
        session.statut = QuizSession.STATUT_TERMINE
        session.completed_at = session.completed_at or timezone.now()
    session.save(
        update_fields=[
            "score",
            "total_questions",
            "pourcentage",
            "statut",
            "completed_at",
            "updated_at",
        ]
    )
    if became_complete:
        finalize_session_rewards(session)
    return session


def get_next_unanswered_question(session):
    return session.session_questions.filter(answered_at__isnull=True).order_by("ordre", "created_at").first()


def get_choice_text_map(session_question):
    return {
        option.get("id"): option.get("text", "")
        for option in (session_question.answer_options or [])
    }


def get_correct_answer_display(session_question):
    expected = session_question.expected_answer or {}
    choice_map = get_choice_text_map(session_question)
    if session_question.question_type in {QuizQuestion.TYPE_QCM, QuizQuestion.TYPE_VRAI_FAUX}:
        return ", ".join(choice_map.get(choice_id, choice_id) for choice_id in expected.get("choice_ids", []))
    if session_question.question_type == QuizQuestion.TYPE_NUMERIQUE:
        return ", ".join(expected.get("numeric_values", []))
    return ", ".join(expected.get("accepted_texts", []))


def build_session_feedback(session, current_question):
    answered_items = list(session.session_questions.order_by("ordre", "created_at"))
    answered_count = sum(1 for item in answered_items if item.answered_at)
    current_streak = 0
    for item in answered_items:
        if not item.answered_at:
            break
        if item.is_correct:
            current_streak += 1
        else:
            current_streak = 0

    xp_gained_live = 0
    for item in answered_items:
        if item.answered_at and item.is_correct:
            xp_gained_live += XP_PER_CORRECT

    bonus_preview = 0
    streak = 0
    for item in answered_items:
        if not item.answered_at:
            break
        if item.is_correct:
            streak += 1
            if streak % 3 == 0:
                bonus_preview += XP_STREAK_BONUS
        else:
            streak = 0

    return {
        "answered_count": answered_count,
        "progress_percent": int((answered_count / session.total_questions) * 100) if session.total_questions else 0,
        "current_streak": current_streak,
        "xp_gained_live": xp_gained_live,
        "bonus_preview": bonus_preview,
        "lives_left": max(0, 3 - sum(1 for item in answered_items if item.answered_at and item.is_correct is False)),
        "feedback_state": "neutral" if not current_question.answered_at else ("success" if current_question.is_correct else "error"),
    }


def build_progress_dashboard_context(user):
    progress = get_or_create_user_progress(user)
    sessions = QuizSession.objects.filter(utilisateur=user, statut=QuizSession.STATUT_TERMINE).select_related("theme")
    recent_sessions = list(sessions.order_by("-started_at")[:10])
    badges = list(
        QuizUserBadge.objects.filter(user=user).select_related("badge").order_by("-earned_at")
    )

    score_stats = sessions.aggregate(
        best_score=Avg("pourcentage"),
        max_score=Count("id"),
        average_score=Avg("pourcentage"),
    )
    best_score = sessions.order_by("-pourcentage").values_list("pourcentage", flat=True).first() or Decimal("0")
    average_score = score_stats.get("average_score") or Decimal("0")

    by_theme = list(
        sessions.values("theme__nom")
        .annotate(avg_score=Avg("pourcentage"), quiz_count=Count("id"))
        .order_by("theme__nom")
    )
    strongest_theme = max(by_theme, key=lambda item: item["avg_score"], default=None)
    weakest_theme = min(by_theme, key=lambda item: item["avg_score"], default=None)

    chart_timeline = [
        {
            "label": item.completed_at.strftime("%d/%m"),
            "xp": item.xp_gagne + item.bonus_xp,
            "score": float(item.pourcentage),
        }
        for item in sessions.order_by("completed_at")[:20]
        if item.completed_at
    ]
    chart_theme_scores = [
        {"theme": item["theme__nom"], "score": float(item["avg_score"] or 0)}
        for item in by_theme
    ]
    chart_theme_counts = [
        {"theme": item["theme__nom"], "count": item["quiz_count"]}
        for item in by_theme
    ]

    return {
        "progress": progress,
        "recent_sessions": recent_sessions,
        "badges": badges,
        "best_score": best_score,
        "average_score": average_score,
        "total_completed": sessions.count(),
        "strongest_theme": strongest_theme,
        "weakest_theme": weakest_theme,
        "level_progress": get_progress_to_next_level(progress.total_xp),
        "chart_timeline": chart_timeline,
        "chart_theme_scores": chart_theme_scores,
        "chart_theme_counts": chart_theme_counts,
    }
