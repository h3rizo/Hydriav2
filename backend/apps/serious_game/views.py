from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .models import QuizQuestion, QuizSession, QuizTheme
from .quiz_services import (
    build_theme_module_map,
    build_progress_dashboard_context,
    build_quiz_session,
    build_session_feedback,
    evaluate_session_question,
    get_correct_answer_display,
    get_next_unanswered_question,
    get_or_create_user_progress,
    get_progress_to_next_level,
    is_theme_unlocked,
    get_best_scores_by_theme,
    recalculate_session_score,
)


def _get_target_role_label(user):
    employe = getattr(user, "employe", None)
    poste = getattr(getattr(employe, "poste", None), "nom_poste", "") or ""
    return poste.strip()


def _get_theme_queryset_for_user(user):
    role_label = _get_target_role_label(user).lower()
    qs = QuizTheme.objects.filter(actif=True).prefetch_related("questions")
    visible = []
    for theme in qs:
        if not theme.role_cible:
            visible.append(theme.id)
            continue
        if role_label and theme.role_cible.lower() in role_label:
            visible.append(theme.id)
    return QuizTheme.objects.filter(id__in=visible).order_by("ordre_affichage", "nom")


@login_required
def serious_game_home(request):
    latest_session = (
        QuizSession.objects.filter(utilisateur=request.user)
        .select_related("theme")
        .order_by("-started_at")
        .first()
    )
    themes = _get_theme_queryset_for_user(request.user)
    progress = get_or_create_user_progress(request.user)
    context = {
        "title": "Hydria Academy",
        "latest_session": latest_session,
        "themes_count": themes.count(),
        "progress": progress,
        "level_progress": get_progress_to_next_level(progress.total_xp),
        "game3d_total_stars": request.user.game3d_bests.total_stars(),
        "game_config": {
            "duration_seconds": 120,
            "min_victory_score": 80,
            "failure_satisfaction_threshold": 15,
            "failure_max_pending_breakdowns": 3,
        },
    }
    return render(request, "serious_game/index.html", context)


@login_required
def serious_game_simulation(request):
    context = {
        "title": "Hydria Academy - Simulation",
        "game_config": {
            "duration_seconds": 120,
            "min_victory_score": 80,
            "failure_satisfaction_threshold": 15,
            "failure_max_pending_breakdowns": 3,
        },
    }
    return render(request, "serious_game/simulation.html", context)


@login_required
def quiz_theme_list(request):
    themes = _get_theme_queryset_for_user(request.user)
    progress = get_or_create_user_progress(request.user)
    context = {
        "title": "Hydria Academy",
        "parcours_cards": build_theme_module_map(themes, request.user),
        "progress": progress,
        "level_progress": get_progress_to_next_level(progress.total_xp),
    }
    return render(request, "serious_game/quiz_theme_list.html", context)


@login_required
def quiz_start(request, theme_id):
    theme = get_object_or_404(_get_theme_queryset_for_user(request.user), id=theme_id, actif=True)
    if not is_theme_unlocked(theme, get_best_scores_by_theme(request.user)):
        messages.error(request, "Ce module est encore verrouille. Terminez d'abord le module precedent avec le score requis.")
        return redirect("serious_game:quiz_themes")
    active_questions = theme.questions.filter(actif=True)
    if not active_questions.exists():
        messages.error(request, "Ce theme ne contient encore aucune question active.")
        return redirect("serious_game:quiz_themes")

    session = build_quiz_session(theme, request.user)
    if session.total_questions == 0:
        messages.error(request, "Impossible de generer un quiz avec les questions disponibles.")
        session.statut = QuizSession.STATUT_ABANDONNE
        session.save(update_fields=["statut", "updated_at"])
        return redirect("serious_game:quiz_themes")
    return redirect("serious_game:quiz_take", session_id=session.id)


@login_required
def quiz_take(request, session_id):
    session = get_object_or_404(
        QuizSession.objects.select_related("theme"),
        id=session_id,
        utilisateur=request.user,
    )
    session_questions = list(session.session_questions.order_by("ordre", "created_at"))
    if not session_questions:
        messages.error(request, "Cette session ne contient aucune question.")
        return redirect("serious_game:quiz_themes")

    review_mode = request.GET.get("review") == "1"
    if session.statut == QuizSession.STATUT_TERMINE and not review_mode:
        return redirect("serious_game:quiz_result", session_id=session.id)

    unanswered_question = get_next_unanswered_question(session)
    if not unanswered_question:
        recalculate_session_score(session)
        return redirect("serious_game:quiz_result", session_id=session.id)

    requested_order = request.GET.get("step")
    if requested_order:
        try:
            requested_order_int = int(requested_order)
        except (TypeError, ValueError):
            requested_order_int = unanswered_question.ordre
    else:
        requested_order_int = unanswered_question.ordre

    current_question = next(
        (item for item in session_questions if item.ordre == requested_order_int),
        unanswered_question,
    )

    if current_question.answered_at and current_question.ordre > unanswered_question.ordre:
        current_question = unanswered_question

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "next":
            next_question = get_next_unanswered_question(session)
            if next_question:
                return redirect(f"{reverse('serious_game:quiz_take', kwargs={'session_id': session.id})}?step={next_question.ordre}")
            recalculate_session_score(session)
            return redirect("serious_game:quiz_result", session_id=session.id)

        if current_question.answered_at:
            return redirect(f"{reverse('serious_game:quiz_take', kwargs={'session_id': session.id})}?step={current_question.ordre}")

        submitted_value = ""
        if current_question.question_type in {QuizQuestion.TYPE_QCM, QuizQuestion.TYPE_VRAI_FAUX}:
            submitted_value = request.POST.get("selected_choice", "")
        else:
            submitted_value = request.POST.get("answer_text", "")

        if not str(submitted_value).strip():
            messages.error(request, "Veuillez saisir une reponse avant de valider.")
        else:
            evaluate_session_question(current_question, submitted_value)
            return redirect(
                f"{reverse('serious_game:quiz_take', kwargs={'session_id': session.id})}"
                f"?step={current_question.ordre}&review=1"
            )

    current_question = next(
        (item for item in session_questions if item.id == current_question.id),
        current_question,
    )

    feedback = build_session_feedback(session, current_question)
    progress = get_or_create_user_progress(request.user)
    context = {
        "title": f"Quiz - {session.theme.nom}",
        "session": session,
        "current_question": current_question,
        "current_index": current_question.ordre,
        "total_questions": session.total_questions,
        "answered_count": feedback["answered_count"],
        "progress_percent": feedback["progress_percent"],
        "correct_answer_display": get_correct_answer_display(current_question) if current_question.answered_at else "",
        "next_question": get_next_unanswered_question(session),
        "feedback_state": feedback["feedback_state"],
        "xp_gained_live": feedback["xp_gained_live"],
        "bonus_preview": feedback["bonus_preview"],
        "current_streak": feedback["current_streak"],
        "lives_left": feedback["lives_left"],
        "progress": progress,
        "level_progress": get_progress_to_next_level(progress.total_xp),
    }
    return render(request, "serious_game/quiz_take.html", context)


@login_required
def quiz_result(request, session_id):
    session = get_object_or_404(
        QuizSession.objects.select_related("theme"),
        id=session_id,
        utilisateur=request.user,
    )
    session_questions = list(session.session_questions.order_by("ordre", "created_at"))
    if not session_questions:
        raise Http404("Session introuvable")

    recalculate_session_score(session)
    session.refresh_from_db()
    details = []
    for item in session_questions:
        details.append({
            "item": item,
            "correct_answer_display": get_correct_answer_display(item),
        })

    progress = get_or_create_user_progress(request.user)
    earned_badges = list(
        request.user.quiz_user_badges.select_related("badge").order_by("-earned_at")[:4]
    )
    context = {
        "title": f"Resultat - {session.theme.nom}",
        "session": session,
        "details": details,
        "progress": progress,
        "level_progress": get_progress_to_next_level(progress.total_xp),
        "earned_badges": earned_badges,
    }
    return render(request, "serious_game/quiz_result.html", context)


@login_required
def quiz_history(request):
    sessions = (
        QuizSession.objects.filter(utilisateur=request.user)
        .select_related("theme")
        .order_by("-started_at")
    )
    best_scores = (
        QuizSession.objects.filter(utilisateur=request.user, statut=QuizSession.STATUT_TERMINE)
        .values("theme__nom")
        .annotate(best_score=Max("pourcentage"))
        .order_by("theme__nom")
    )
    dashboard_context = build_progress_dashboard_context(request.user)
    context = {
        "title": "Historique des quiz",
        "sessions": sessions,
        "best_scores": best_scores,
        **dashboard_context,
    }
    return render(request, "serious_game/quiz_history.html", context)


@login_required
def progress_dashboard(request):
    context = {
        "title": "Hydria Academy - Progression",
        **build_progress_dashboard_context(request.user),
    }
    return render(request, "serious_game/progress_dashboard.html", context)
