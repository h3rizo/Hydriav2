"""Regles serveur de Hydria Quest 3D (spec §14.3).

- Une partie (GameRun) est creee au demarrage avec un instantane des questions :
  les bonnes reponses ne quittent jamais le serveur tant que le joueur est en ligne.
- Les reponses sont corrigees ici, question par question (POST par reponse).
- L'XP n'est accordee que pour les etoiles NOUVELLEMENT obtenues, plus une petite
  XP de pratique plafonnee par jour (anti-farm) ; le score ne donne jamais d'XP.
"""
import math
import random
from datetime import timedelta

from django.db import transaction
from django.db.models import Sum
from django.http import Http404
from django.utils import timezone

from .game3d_levels import (
    ALL_STARS_BONUS_XP,
    FALLBACK_QUESTIONS,
    FALLBACK_THEME_NAME,
    LEVELS,
    MAX_ANSWER_POSTS_PER_RUN,
    MAX_TOTAL_STARS,
    OPTION_MAX_LEN,
    PRACTICE_BASE_XP,
    PRACTICE_DAILY_CAP,
    PRACTICE_PER_QUIZ_XP,
    QUESTION_MAX_LEN,
    RUN_MAX_AGE_H,
    START_RATE_LIMIT_S,
    fallback_options,
)
from .models import (
    GameLevelBest,
    GameRun,
    QuizBadge,
    QuizQuestion,
    QuizSessionQuestion,
    QuizUserBadge,
    QuizUserProgress,
)
from .quiz_services import (
    calculate_level,
    get_or_create_user_progress,
    get_progress_to_next_level,
    serialize_question_snapshot,
)

EVENT_KEYS = (
    "repairs", "missed_breakdowns", "payments_due", "payments_overdue", "payments_cutoff",
    "restores", "on_time_payments", "receipts_delivered", "valves",
)
MISSED_WINDOW_DAYS = 30
MAX_CLIENT_ATTEMPTS = 4
_rng = random.SystemRandom()


class Game3DError(Exception):
    """Erreur metier renvoyee au client sous la forme {"ok": false, "error": code}."""

    def __init__(self, code, status=400, **extra):
        super().__init__(code)
        self.code = code
        self.status = status
        self.extra = extra


class Game3DRateLimited(Game3DError):
    def __init__(self, retry_after_s):
        super().__init__("trop_rapide", status=429, retry_after_s=int(retry_after_s))
        self.retry_after_s = int(retry_after_s)


# ---------------------------------------------------------------------------
# Outils
# ---------------------------------------------------------------------------

def popcount(mask):
    return bin(int(mask or 0) & 0b111).count("1")


def _clamp_int(value, low, high):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = low
    return max(low, min(high, number))


def _today_range():
    """Bornes [debut, fin[ du jour local (Indian/Antananarivo), en datetimes conscients."""
    start = timezone.localtime(timezone.now()).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def get_visible_themes(user):
    # Import local : views importe deja quiz_services, on evite tout cycle a l'import.
    from .views import _get_theme_queryset_for_user

    return _get_theme_queryset_for_user(user)


def _snapshot_is_playable(snap):
    if not snap:
        return False
    if snap.get("question_type") not in {QuizQuestion.TYPE_QCM, QuizQuestion.TYPE_VRAI_FAUX}:
        return False
    if len(snap.get("question_text") or "") > QUESTION_MAX_LEN:
        return False
    options = snap.get("answer_options") or []
    if not 2 <= len(options) <= 4:
        return False
    if any(len(option.get("text") or "") > OPTION_MAX_LEN for option in options):
        return False
    return bool((snap.get("expected_answer") or {}).get("choice_ids"))


def _missed_question_ids(user):
    """Questions ratees recemment (quiz classique + parties du jeu) : servies en priorite."""
    since = timezone.now() - timedelta(days=MISSED_WINDOW_DAYS)
    missed = {
        str(qid)
        for qid in QuizSessionQuestion.objects.filter(
            session__utilisateur=user, is_correct=False, answered_at__gte=since, question__isnull=False,
        ).values_list("question_id", flat=True)
    }
    for run in GameRun.objects.filter(user=user, started_at__gte=since).only("quiz_snapshot", "answers"):
        by_slot = {item.get("slot"): item for item in run.quiz_snapshot or []}
        for answer in run.answers or []:
            snap = by_slot.get(answer.get("slot"))
            if snap and snap.get("question_id") and not answer.get("first_try_correct"):
                missed.add(str(snap["question_id"]))
    return missed


def _fallback_entry(slot, question):
    options = fallback_options(question)
    return {
        "slot": slot,
        "source": "fallback",
        "question_id": None,
        "fallback_id": question["id"],
        "theme": FALLBACK_THEME_NAME,
        "question_text": question["text"],
        "question_type": question["type"],
        "answer_options": [{"id": option["id"], "text": option["text"]} for option in options],
        "expected_answer": {"choice_ids": [option["id"] for option in options if option["correct"]]},
        "explication": question.get("explication", ""),
    }


# ---------------------------------------------------------------------------
# Demarrage d'une partie
# ---------------------------------------------------------------------------

def build_run_questions(user, level, count=None):
    cfg = LEVELS[level]
    slots = list(cfg["slots"])
    if count is not None:
        slots = slots[: max(0, min(int(count), len(slots)))]

    visible = get_visible_themes(user)
    missed = _missed_question_ids(user)
    used_ids, used_fallbacks = set(), set()
    snapshot = []

    for slot, module, preferred_type in slots:
        candidates = []
        questions = (
            QuizQuestion.objects.filter(
                actif=True,
                est_dynamique=False,
                type_question__in=[QuizQuestion.TYPE_QCM, QuizQuestion.TYPE_VRAI_FAUX],
                theme__in=visible,
                theme__module_code=module,
            )
            .select_related("theme")
            .prefetch_related("reponses")
        )
        for question in questions:
            if str(question.id) in used_ids:
                continue
            snap = serialize_question_snapshot(question)
            if _snapshot_is_playable(snap):
                candidates.append((question, snap))

        if candidates:
            pool = [c for c in candidates if str(c[0].id) in missed] or candidates
            if preferred_type:
                pool = [c for c in pool if c[1]["question_type"] == preferred_type] or pool
            question, snap = _rng.choice(pool)
            used_ids.add(str(question.id))
            snapshot.append({
                "slot": slot,
                "source": "db",
                "question_id": str(question.id),
                "fallback_id": None,
                "theme": question.theme.nom,
                "question_text": snap["question_text"],
                "question_type": snap["question_type"],
                "answer_options": [{"id": o["id"], "text": o["text"]} for o in snap["answer_options"]],
                "expected_answer": {"choice_ids": list(snap["expected_answer"]["choice_ids"])},
                "explication": snap.get("explication") or "",
            })
            continue

        fallback = next((q for q in FALLBACK_QUESTIONS.get(level, []) if q["id"] not in used_fallbacks), None)
        if fallback is None:
            continue
        used_fallbacks.add(fallback["id"])
        snapshot.append(_fallback_entry(slot, fallback))

    return snapshot


def start_run(user, level, count=None):
    cfg = LEVELS.get(level)
    if cfg is None:
        raise Game3DError("niveau_inconnu")

    last = GameRun.objects.filter(user=user).order_by("-started_at").only("started_at").first()
    if last:
        elapsed = (timezone.now() - last.started_at).total_seconds()
        if elapsed < START_RATE_LIMIT_S:
            raise Game3DRateLimited(math.ceil(START_RATE_LIMIT_S - elapsed))

    return GameRun.objects.create(
        user=user,
        level=level,
        quiz_snapshot=build_run_questions(user, level, count),
        gouttes_total=cfg["gouttes"],
    )


def public_questions(run):
    """Questions envoyees au client : sans reponse attendue ni explication."""
    return [
        {
            "slot": item["slot"],
            "type": item["question_type"],
            "text": item["question_text"],
            "options": [{"id": o["id"], "text": o["text"]} for o in item["answer_options"]],
            "theme": item.get("theme") or FALLBACK_THEME_NAME,
            "source": item.get("source", "db"),
        }
        for item in run.quiz_snapshot or []
    ]


# ---------------------------------------------------------------------------
# Correction d'une reponse
# ---------------------------------------------------------------------------

def _answer_response(snap, entry, already=False):
    expected = set((snap.get("expected_answer") or {}).get("choice_ids") or [])
    attempts = entry.get("attempts") or []
    solved = bool(entry.get("solved"))
    last = attempts[-1] if attempts else None
    response = {
        "ok": True,
        "correct": last in expected if last else False,
        "solved": solved,
        "attempt": len(attempts),
        "first_try_correct": bool(entry.get("first_try_correct")),
        "eliminated": [choice for choice in dict.fromkeys(attempts) if choice not in expected],
        "reveal_choice_ids": sorted(expected) if solved else [],
        "explication": (snap.get("explication") or "") if solved else "",
    }
    if already:
        response["already"] = True
    return response


def _is_solved(question_type, attempts, expected, option_count):
    if any(choice in expected for choice in attempts):
        return True
    if question_type == QuizQuestion.TYPE_VRAI_FAUX:
        return bool(attempts)  # une erreur sur vrai/faux revele la reponse
    return len(set(attempts)) >= option_count - 1  # QCM : revele quand il ne reste qu'une option


@transaction.atomic
def answer_question(user, run_id, slot, choice_id):
    try:
        run = GameRun.objects.select_for_update().get(id=run_id, user=user)
    except (GameRun.DoesNotExist, ValueError, TypeError):
        raise Http404("Partie introuvable")

    if run.statut != GameRun.STATUT_EN_COURS:
        raise Game3DError("partie_terminee", status=409)

    snap = next((item for item in run.quiz_snapshot or [] if item.get("slot") == slot), None)
    if snap is None:
        raise Game3DError("slot_inconnu")
    option_ids = [option["id"] for option in snap.get("answer_options") or []]
    if choice_id not in option_ids:
        raise Game3DError("choix_inconnu")

    answers = list(run.answers or [])
    entry = next((item for item in answers if item.get("slot") == slot), None)
    if entry and entry.get("solved"):
        return _answer_response(snap, entry, already=True)

    if sum(len(item.get("attempts") or []) for item in answers) >= MAX_ANSWER_POSTS_PER_RUN:
        raise Game3DError("trop_de_reponses", status=429)

    if entry is None:
        entry = {"slot": slot, "attempts": [], "solved": False, "first_try_correct": False, "source": "server"}
        answers.append(entry)

    expected = set((snap.get("expected_answer") or {}).get("choice_ids") or [])
    entry["attempts"] = list(entry.get("attempts") or []) + [choice_id]
    entry["solved"] = _is_solved(snap.get("question_type"), entry["attempts"], expected, len(option_ids))
    entry["first_try_correct"] = len(entry["attempts"]) == 1 and choice_id in expected

    run.answers = answers
    run.save(update_fields=["answers", "updated_at"])
    return _answer_response(snap, entry)


# ---------------------------------------------------------------------------
# Fin de partie : etoiles, XP, records, badges
# ---------------------------------------------------------------------------

def compute_stars(completed, gouttes, quiz_first_try, snapshot_size, events, level_cfg):
    """Masque d'etoiles : bit0 termine, bit1 toutes les gouttes, bit2 regle du niveau."""
    mask = 0
    if completed:
        mask |= 0b001
    if completed and gouttes == level_cfg["gouttes"]:
        mask |= 0b010
    rule = level_cfg["star3"]
    if rule == "quiz_first_try":
        third = snapshot_size > 0 and quiz_first_try == snapshot_size
    elif rule == "tournee_a_l_heure":
        third = events.get("on_time_payments", 0) >= 2 and events.get("restores", 0) >= 1
    elif rule == "service_exemplaire":
        third = events.get("missed_breakdowns", 0) == 0 and events.get("repairs", 0) >= 3
    else:
        third = False
    if completed and third:
        mask |= 0b100
    return mask


def compute_practice_xp(quiz_first_try, done_today_xp, level_already_practiced_today):
    """XP de pratique d'une partie terminee (anti-farm, spec §14.3 etape 9 et §18 A2).

    - quiz_first_try : nombre de questions du niveau reussies du premier coup (0 a 3)
    - done_today_xp : XP de pratique deja gagnee aujourd'hui, tous niveaux confondus
    - level_already_practiced_today : ce niveau a deja rapporte de l'XP de pratique aujourd'hui
    Constantes disponibles : PRACTICE_BASE_XP (5), PRACTICE_PER_QUIZ_XP (2), PRACTICE_DAILY_CAP (30).
    Doit renvoyer un entier >= 0. Les etoiles nouvelles sont recompensees ailleurs (xp_etoiles).
    """
    # TODO(human): implementer la regle d'XP de pratique (voir PracticeXpRuleTests dans tests_game3d.py).
    return 0


def _total_best_stars(user):
    masks = GameLevelBest.objects.filter(user=user, level__in=list(LEVELS.keys())).values_list("best_stars_mask", flat=True)
    return sum(popcount(mask) for mask in masks)


def get_bests(user):
    return {
        str(best.level): {
            "stars_mask": best.best_stars_mask,
            "best_time_ms": best.best_time_ms,
            "best_score": best.best_score,
            "completed": bool(best.runs_completed or best.best_stars_mask & 1),
        }
        for best in GameLevelBest.objects.filter(user=user, level__in=list(LEVELS.keys()))
    }


def award_game_badges(user, level, stars_mask, total_stars):
    rules = []
    if level == 0 and stars_mask & 0b001:
        rules.append("jeu_premiers_pas")
    if level == 1 and stars_mask & 0b100:
        rules.append("jeu_reparateur")
    if level == 2 and stars_mask & 0b100:
        rules.append("jeu_tournee_a_l_heure")
    if level == 3 and stars_mask & 0b001:
        rules.append("jeu_chateau")
    if total_stars >= MAX_TOTAL_STARS:
        rules.append("jeu_12_etoiles")
    earned = []
    for badge in QuizBadge.objects.filter(code__in=rules, actif=True):
        _, created = QuizUserBadge.objects.get_or_create(user=user, badge=badge)
        if created:
            earned.append(badge)
    return earned


def _merge_client_answers(run, payload_answers):
    """Complete les reponses serveur avec celles du client pour les questions non postees."""
    answers = list(run.answers or [])
    answered_slots = {item.get("slot") for item in answers if item.get("attempts")}
    by_slot = {}
    for item in payload_answers or []:
        if isinstance(item, dict) and isinstance(item.get("slot"), str):
            by_slot[item["slot"]] = item.get("attempts") or []

    for snap in run.quiz_snapshot or []:
        slot = snap.get("slot")
        if slot in answered_slots:
            continue
        option_ids = {option["id"] for option in snap.get("answer_options") or []}
        attempts = [a for a in by_slot.get(slot, []) if isinstance(a, str) and a in option_ids][:MAX_CLIENT_ATTEMPTS]
        if not attempts:
            continue
        expected = set((snap.get("expected_answer") or {}).get("choice_ids") or [])
        answers = [item for item in answers if item.get("slot") != slot]
        answers.append({
            "slot": slot,
            "attempts": attempts,
            "solved": _is_solved(snap.get("question_type"), attempts, expected, len(option_ids)),
            "first_try_correct": attempts[0] in expected,
            "source": "client",
        })
    return answers


def _result_response(run, best, total_stars, progress, badges, already=False):
    return {
        "ok": True,
        "run_id": str(run.id),
        "statut": run.statut,
        "already_processed": already,
        "rejected_reason": run.rejected_reason,
        "stars_mask": run.stars_mask,
        "new_stars_mask": run.new_stars_mask,
        "stars": [bool(run.stars_mask & (1 << bit)) for bit in range(3)],
        "xp_gagne": run.xp_gagne,
        "xp_detail": {"etoiles": run.xp_etoiles, "pratique": run.xp_pratique, "bonus": run.xp_bonus},
        "total_xp": progress.total_xp,
        "level": progress.level,
        "level_progress": get_progress_to_next_level(progress.total_xp),
        "best": {
            "stars_mask": best.best_stars_mask if best else 0,
            "best_time_ms": best.best_time_ms if best else None,
            "best_score": best.best_score if best else 0,
        },
        "total_stars": total_stars,
        "badges": [{"code": b.code, "nom": b.nom, "icon": b.icon} for b in badges],
    }


def _close_without_reward(run, statut, reason=""):
    run.statut = statut
    run.rejected_reason = reason
    run.stars_mask = run.new_stars_mask = 0
    run.xp_etoiles = run.xp_pratique = run.xp_bonus = run.xp_gagne = 0
    run.finished_at = timezone.now()
    run.rewards_processed = True
    run.save()


@transaction.atomic
def finalize_game_run(run_id, user, payload):
    try:
        run = GameRun.objects.select_for_update().get(id=run_id, user=user)
    except (GameRun.DoesNotExist, ValueError, TypeError):
        raise Http404("Partie introuvable")

    best = GameLevelBest.objects.filter(user=user, level=run.level).first()
    if run.rewards_processed:
        return _result_response(run, best, _total_best_stars(user), get_or_create_user_progress(user), [], already=True)

    try:
        level = int(payload.get("level"))
    except (TypeError, ValueError):
        raise Game3DError("niveau_invalide")
    if level != run.level:
        raise Game3DError("niveau_invalide")
    cfg = LEVELS[run.level]

    now = timezone.now()
    duration_ms = _clamp_int(payload.get("duration_ms"), 0, 24 * 3600 * 1000)
    run.client_duration_ms = duration_ms
    run.falls = _clamp_int(payload.get("falls"), 0, 10000)
    run.help_bridges = _clamp_int(payload.get("help_bridges"), 0, 100)
    run.assists = [str(a)[:60] for a in (payload.get("assists") or []) if isinstance(a, str)][:30]
    run.segments = [s for s in (payload.get("segments") or []) if isinstance(s, dict)][:40]
    run.quality_tier = str(payload.get("quality_tier") or "")[:12]
    run.client_version = str(payload.get("client_version") or "")[:20]
    raw_events = payload.get("events") if isinstance(payload.get("events"), dict) else {}
    events = {key: _clamp_int(raw_events.get(key), 0, 50) for key in EVENT_KEYS}
    run.events = events

    progress = get_or_create_user_progress(user)
    if now - run.started_at > timedelta(hours=RUN_MAX_AGE_H):
        _close_without_reward(run, GameRun.STATUT_REJETE, "partie_expiree")
        return _result_response(run, best, _total_best_stars(user), progress, [])
    if not payload.get("completed"):
        _close_without_reward(run, GameRun.STATUT_ABANDONNE)
        return _result_response(run, best, _total_best_stars(user), progress, [])

    gouttes = payload.get("gouttes")
    gouttes_total = payload.get("gouttes_total")
    elapsed_ms = (now - run.started_at).total_seconds() * 1000
    reason = ""
    if duration_ms < cfg["min_s"] * 1000:
        reason = "duree_trop_courte"
    elif duration_ms > elapsed_ms + 5000:
        reason = "duree_incoherente"
    elif (
        not isinstance(gouttes, int) or isinstance(gouttes, bool) or gouttes < 0 or gouttes > cfg["gouttes"]
        or gouttes_total != cfg["gouttes"]
    ):
        reason = "gouttes_invalides"
    if reason:
        _close_without_reward(run, GameRun.STATUT_REJETE, reason)
        return _result_response(run, best, _total_best_stars(user), progress, [])

    run.gouttes = gouttes
    run.answers = _merge_client_answers(run, payload.get("answers"))
    snapshot_slots = {item.get("slot") for item in run.quiz_snapshot or []}
    run.quiz_first_try = sum(
        1 for item in run.answers if item.get("slot") in snapshot_slots and item.get("first_try_correct")
    )

    mask = compute_stars(True, gouttes, run.quiz_first_try, len(snapshot_slots), events, cfg)
    best, _ = GameLevelBest.objects.select_for_update().get_or_create(user=user, level=run.level)
    stars_before = _total_best_stars(user)
    new_mask = mask & ~best.best_stars_mask & 0b111
    run.stars_mask, run.new_stars_mask = mask, new_mask
    run.xp_etoiles = popcount(new_mask) * cfg["star_xp"]

    day_start, day_end = _today_range()
    finished_today = GameRun.objects.filter(user=user, finished_at__gte=day_start, finished_at__lt=day_end)
    done_today = finished_today.aggregate(total=Sum("xp_pratique"))["total"] or 0
    already_practiced = finished_today.filter(level=run.level, xp_pratique__gt=0).exists()
    run.xp_pratique = compute_practice_xp(run.quiz_first_try, done_today, already_practiced)

    best.best_stars_mask |= mask
    best.best_score = max(best.best_score, _clamp_int(payload.get("score_client"), 0, cfg["score_max"]))
    best.best_time_ms = duration_ms if best.best_time_ms is None else min(best.best_time_ms, duration_ms)
    best.runs_completed += 1
    if best.first_completed_at is None:
        best.first_completed_at = now
    best.save()

    total_stars = _total_best_stars(user)
    run.xp_bonus = ALL_STARS_BONUS_XP if stars_before < MAX_TOTAL_STARS <= total_stars else 0
    run.xp_gagne = run.xp_etoiles + run.xp_pratique + run.xp_bonus
    run.score = _clamp_int(payload.get("score_client"), 0, cfg["score_max"])

    progress = QuizUserProgress.objects.select_for_update().get(pk=progress.pk)
    progress.total_xp += run.xp_gagne
    progress.level = calculate_level(progress.total_xp)
    progress.last_activity_date = timezone.localdate()
    progress.save(update_fields=["total_xp", "level", "last_activity_date", "updated_at"])

    badges = award_game_badges(user, run.level, best.best_stars_mask, total_stars)

    run.statut = GameRun.STATUT_TERMINE
    run.finished_at = now
    run.rewards_processed = True
    run.save()
    return _result_response(run, best, total_stars, progress, badges)
