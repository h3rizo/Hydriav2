"""Vues de Hydria Quest 3D : page du jeu + API JSON (spec §14.4 a §14.6)."""
import functools
import hashlib
import json
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import render
from django.templatetags.static import static
from django.views.decorators.http import require_GET, require_POST

from . import game3d_services as services
from .game3d_levels import GAME3D_VERSION, LEVELS, fallback_questions_public, levels_meta
from .models import GameRun
from .quiz_services import get_or_create_user_progress, get_progress_to_next_level

THREE_VERSION = "0.170.0"
THREE_CDN = f"https://cdn.jsdelivr.net/npm/three@{THREE_VERSION}"
ACADEMY3D_DIR = Path(__file__).resolve().parent / "static" / "serious_game" / "academy3d"
CSS_FILE = Path(__file__).resolve().parent / "static" / "serious_game" / "css" / "academy3d.css"


def _short_hash(path):
    try:
        return hashlib.sha1(path.read_bytes()).hexdigest()[:10]
    except OSError:
        return "0"


def _build_importmap():
    imports = {
        "three": f"{THREE_CDN}/build/three.module.js",
        "three/addons/": f"{THREE_CDN}/examples/jsm/",
        # Repli pour un fichier ajoute apres le calcul du cache (les entrees exactes priment).
        "a3d/": static("serious_game/academy3d/"),
    }
    if ACADEMY3D_DIR.is_dir():
        for path in sorted(ACADEMY3D_DIR.rglob("*.js")):
            rel = path.relative_to(ACADEMY3D_DIR).as_posix()
            imports[f"a3d/{rel}"] = f"{static('serious_game/academy3d/' + rel)}?v={_short_hash(path)}"
    return json.dumps({"imports": imports}, ensure_ascii=False)


@functools.lru_cache(maxsize=1)
def _cached_assets():
    return _build_importmap(), _short_hash(CSS_FILE)


def _assets():
    """Import map + hash CSS : recalcules a chaque requete en DEBUG, mis en cache sinon."""
    if settings.DEBUG:
        return _build_importmap(), _short_hash(CSS_FILE)
    return _cached_assets()


def _display_name(user):
    employe = getattr(user, "employe", None)
    if employe is not None:
        name = (getattr(employe, "surnom", "") or "").strip()
        if name:
            return name
    return (user.first_name or "").strip() or user.username


def _json_error(code, status=400, **extra):
    return JsonResponse({"ok": False, "error": code, **extra}, status=status)


def _read_json(request):
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


@login_required
def jeu_3d(request):
    importmap, css_hash = _assets()
    progress = get_or_create_user_progress(request.user)
    bests = services.get_bests(request.user)
    total_stars = sum(services.popcount(best["stars_mask"]) for best in bests.values())
    has_completed = GameRun.objects.filter(user=request.user, statut=GameRun.STATUT_TERMINE).exists()
    bootstrap = {
        "version": GAME3D_VERSION,
        "debug": request.GET.get("debug") == "1",
        "urls": {
            "questions": "/serious-game/jeu-3d/api/questions/",
            "answer": "/serious-game/jeu-3d/api/repondre/",
            "result": "/serious-game/jeu-3d/api/resultat/",
            "home": "/serious-game/",
            "simulation": "/serious-game/simulation/",
            "progress": "/serious-game/quiz/progression/",
        },
        "csrf": get_token(request),
        "user": {"display_name": _display_name(request.user), "is_staff": bool(request.user.is_staff)},
        "progress": {
            "total_xp": progress.total_xp,
            "level": progress.level,
            "level_progress": get_progress_to_next_level(progress.total_xp),
        },
        "best": bests,
        "total_stars": total_stars,
        "unlock_all": bool(request.user.is_staff),
        "assist_default": None if has_completed else "debutant",
        "levels_meta": levels_meta(),
        "fallback_questions": fallback_questions_public(),
    }
    context = {
        "title": "Hydria Quest 3D",
        "a3d_version": GAME3D_VERSION,
        "a3d_importmap": importmap,
        "a3d_css_hash": css_hash,
        "a3d_bootstrap": bootstrap,
        "total_stars": total_stars,
        "max_stars": 3 * len(LEVELS),
    }
    return render(request, "serious_game/jeu_3d.html", context)


@login_required
@require_GET
def api_questions(request):
    try:
        level = int(request.GET.get("level", ""))
    except ValueError:
        return _json_error("niveau_invalide")
    if level not in LEVELS:
        return _json_error("niveau_invalide")
    count = request.GET.get("count")
    try:
        count = int(count) if count not in (None, "") else None
    except ValueError:
        count = None
    try:
        run = services.start_run(request.user, level, count)
    except services.Game3DError as exc:
        return _json_error(exc.code, exc.status, **exc.extra)
    response = JsonResponse({
        "ok": True,
        "run_id": str(run.id),
        "level": run.level,
        "questions": services.public_questions(run),
        "best": services.get_bests(request.user).get(str(level)),
    })
    response["Cache-Control"] = "no-store"
    return response


@login_required
@require_POST
def api_answer(request):
    data = _read_json(request)
    if data is None:
        return _json_error("json_invalide")
    slot, choice_id = data.get("slot"), data.get("choice_id")
    if not isinstance(slot, str) or not isinstance(choice_id, str):
        return _json_error("parametres_invalides")
    try:
        result = services.answer_question(request.user, data.get("run_id"), slot, choice_id)
    except Http404:
        return _json_error("partie_introuvable", 404)
    except services.Game3DError as exc:
        return _json_error(exc.code, exc.status, **exc.extra)
    return JsonResponse(result)


@login_required
@require_POST
def api_result(request):
    data = _read_json(request)
    if data is None:
        return _json_error("json_invalide")
    try:
        result = services.finalize_game_run(data.get("run_id"), request.user, data)
    except Http404:
        return _json_error("partie_introuvable", 404)
    except services.Game3DError as exc:
        return _json_error(exc.code, exc.status, **exc.extra)
    return JsonResponse(result)
