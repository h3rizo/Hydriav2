"""Tests de Hydria Quest 3D (spec §14.7).

python manage.py test apps.serious_game.tests_game3d --testrunner django.test.runner.DiscoverRunner
"""
import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from hydria.test_academy_subdomain import PLANNING_SETTINGS

from . import game3d_services as services
from .game3d_levels import LEVELS, PRACTICE_DAILY_CAP
from .models import GameLevelBest, GameRun, QuizQuestion, QuizUserBadge, QuizUserProgress

QUESTIONS_URL = "/serious-game/jeu-3d/api/questions/"
ANSWER_URL = "/serious-game/jeu-3d/api/repondre/"
RESULT_URL = "/serious-game/jeu-3d/api/resultat/"

THIRD_STAR_EVENTS = {
    0: {}, 1: {},
    2: {"on_time_payments": 2, "restores": 1},
    3: {"missed_breakdowns": 0, "repairs": 3},
}


def make_run(user, level, minutes_ago=30):
    """Partie prete a etre terminee (cree sans passer par la limite de 8 s)."""
    run = GameRun.objects.create(
        user=user, level=level,
        quiz_snapshot=services.build_run_questions(user, level),
        gouttes_total=LEVELS[level]["gouttes"],
    )
    GameRun.objects.filter(id=run.id).update(started_at=timezone.now() - timedelta(minutes=minutes_ago))
    run.refresh_from_db()
    return run


def perfect_answers(run):
    return [
        {"slot": item["slot"], "attempts": [item["expected_answer"]["choice_ids"][0]]}
        for item in run.quiz_snapshot
    ]


def payload(run, **overrides):
    cfg = LEVELS[run.level]
    data = {
        "run_id": str(run.id), "level": run.level, "completed": True,
        "duration_ms": cfg["min_s"] * 1000 + 30000,
        "gouttes": cfg["gouttes"], "gouttes_total": cfg["gouttes"],
        "answers": perfect_answers(run),
        "events": dict(THIRD_STAR_EVENTS[run.level]),
        "segments": [], "falls": 0, "help_bridges": 0, "assists": ["profile:debutant"],
        "score_client": 100, "quality_tier": "low", "client_version": "a3d-1.0.0",
    }
    data.update(overrides)
    return data


class BaseGame3DTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="koto", password="x-test-pass-1")
        self.other = User.objects.create_user(username="intrus", password="x-test-pass-2")
        self.client.force_login(self.user)

    def post_json(self, url, data, client=None):
        return (client or self.client).post(url, data=json.dumps(data), content_type="application/json")


@override_settings(**PLANNING_SETTINGS)
class Game3DPageTests(BaseGame3DTest):
    def test_page_requires_login(self):
        response = Client().get("/serious-game/jeu-3d/", HTTP_HOST="planning.hydria.mg")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_page_renders_in_planning_shell_with_importmap_and_bootstrap(self):
        response = self.client.get("/serious-game/jeu-3d/", HTTP_HOST="planning.hydria.mg")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "planning/base.html")
        self.assertContains(response, "three@0.170.0")
        self.assertContains(response, "a3d/main.js")
        self.assertContains(response, 'id="a3d-bootstrap"')
        bootstrap = response.context["a3d_bootstrap"]
        self.assertEqual(bootstrap["assist_default"], "debutant")
        self.assertEqual(bootstrap["levels_meta"]["2"]["gouttes"], 40)


class Game3DQuestionsTests(BaseGame3DTest):
    def test_creates_run_with_one_snapshot_per_slot_and_hides_answers(self):
        response = self.client.get(QUESTIONS_URL, {"level": 2})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        run = GameRun.objects.get(id=data["run_id"])
        self.assertEqual(len(run.quiz_snapshot), len(LEVELS[2]["slots"]))
        self.assertEqual([q["slot"] for q in data["questions"]], ["q1", "q2", "q3"])
        raw = response.content.decode()
        self.assertNotIn("expected_answer", raw)
        self.assertNotIn("explication", raw)
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_uses_db_questions_of_the_level_module(self):
        # Les migrations 0002/0008 creent des questions pour les modules des niveaux.
        data = self.client.get(QUESTIONS_URL, {"level": 0}).json()
        self.assertEqual(data["questions"][0]["source"], "db")

    def test_uses_fallback_questions_without_db_questions(self):
        QuizQuestion.objects.update(actif=False)
        data = self.client.get(QUESTIONS_URL, {"level": 0}).json()
        self.assertEqual(data["questions"][0]["source"], "fallback")

    def test_rate_limited_within_8_seconds(self):
        self.assertEqual(self.client.get(QUESTIONS_URL, {"level": 0}).status_code, 200)
        response = self.client.get(QUESTIONS_URL, {"level": 1})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["error"], "trop_rapide")

    def test_unknown_level(self):
        self.assertEqual(self.client.get(QUESTIONS_URL, {"level": 9}).status_code, 400)


class Game3DAnswerTests(BaseGame3DTest):
    def setUp(self):
        super().setUp()
        QuizQuestion.objects.update(actif=False)  # questions de secours : contenu connu
        self.run = make_run(self.user, 1)  # q1 = QCM fb_l1_1, q2 = vrai/faux fb_l1_2
        self.qcm = self.run.quiz_snapshot[0]
        self.vf = self.run.quiz_snapshot[1]

    def answer(self, slot, choice, run=None, client=None):
        return self.post_json(ANSWER_URL, {"run_id": str((run or self.run).id), "slot": slot, "choice_id": choice}, client)

    def test_qcm_wrong_then_correct(self):
        correct = self.qcm["expected_answer"]["choice_ids"][0]
        wrong = next(o["id"] for o in self.qcm["answer_options"] if o["id"] != correct)
        first = self.answer("q1", wrong).json()
        self.assertFalse(first["correct"])
        self.assertFalse(first["solved"])
        self.assertEqual(first["eliminated"], [wrong])
        self.assertEqual(first["explication"], "")
        second = self.answer("q1", correct).json()
        self.assertTrue(second["correct"])
        self.assertTrue(second["solved"])
        self.assertFalse(second["first_try_correct"])
        self.assertEqual(second["reveal_choice_ids"], [correct])
        self.assertTrue(second["explication"])

    def test_vrai_faux_wrong_reveals_and_solves(self):
        correct = self.vf["expected_answer"]["choice_ids"][0]
        wrong = next(o["id"] for o in self.vf["answer_options"] if o["id"] != correct)
        data = self.answer("q2", wrong).json()
        self.assertFalse(data["correct"])
        self.assertTrue(data["solved"])
        self.assertEqual(data["reveal_choice_ids"], [correct])

    def test_idempotent_after_solved(self):
        correct = self.vf["expected_answer"]["choice_ids"][0]
        self.answer("q2", correct)
        data = self.answer("q2", correct).json()
        self.assertTrue(data["already"])
        self.run.refresh_from_db()
        self.assertEqual(len(self.run.answers[0]["attempts"]), 1)

    def test_other_user_run_is_404(self):
        intruder = Client()
        intruder.force_login(self.other)
        self.assertEqual(self.answer("q1", "choice_1", client=intruder).status_code, 404)

    def test_finished_run_is_409(self):
        GameRun.objects.filter(id=self.run.id).update(statut=GameRun.STATUT_TERMINE)
        self.assertEqual(self.answer("q1", "choice_1").status_code, 409)

    def test_unknown_choice_is_400(self):
        self.assertEqual(self.answer("q1", "choice_99").status_code, 400)


class Game3DResultTests(BaseGame3DTest):
    def finish(self, level, **overrides):
        run = make_run(self.user, level)
        return run, self.post_json(RESULT_URL, payload(run, **overrides)).json()

    def test_too_short_duration_is_rejected(self):
        _, data = self.finish(0, duration_ms=1000)
        self.assertEqual(data["statut"], GameRun.STATUT_REJETE)
        self.assertEqual(data["rejected_reason"], "duree_trop_courte")
        self.assertEqual(data["xp_gagne"], 0)

    def test_duration_longer_than_real_time_is_rejected(self):
        run = make_run(self.user, 0, minutes_ago=2)
        data = self.post_json(RESULT_URL, payload(run, duration_ms=10 * 60 * 1000)).json()
        self.assertEqual(data["rejected_reason"], "duree_incoherente")

    def test_too_many_gouttes_is_rejected(self):
        _, data = self.finish(0, gouttes=31)
        self.assertEqual(data["rejected_reason"], "gouttes_invalides")

    def test_not_completed_is_abandoned(self):
        _, data = self.finish(0, completed=False)
        self.assertEqual(data["statut"], GameRun.STATUT_ABANDONNE)
        self.assertEqual(data["xp_gagne"], 0)

    def test_first_completion_gives_star_xp_and_replay_gives_none(self):
        _, first = self.finish(0)
        self.assertEqual(first["stars"], [True, True, True])
        self.assertEqual(first["xp_detail"]["etoiles"], 3 * LEVELS[0]["star_xp"])
        _, replay = self.finish(0)
        self.assertEqual(replay["xp_detail"]["etoiles"], 0)
        self.assertEqual(replay["xp_detail"]["pratique"], 0)  # meme niveau deja pratique aujourd'hui
        self.assertEqual(GameLevelBest.objects.get(user=self.user, level=0).runs_completed, 2)

    def test_second_post_is_already_processed(self):
        run, first = self.finish(0)
        again = self.post_json(RESULT_URL, payload(run)).json()
        self.assertTrue(again["already_processed"])
        self.assertEqual(QuizUserProgress.objects.get(user=self.user).total_xp, first["total_xp"])

    def test_progress_updated_without_touching_quiz_counters(self):
        _, data = self.finish(0)
        progress = QuizUserProgress.objects.get(user=self.user)
        self.assertEqual(progress.total_xp, data["xp_gagne"])
        self.assertEqual(progress.level, data["level"])
        self.assertEqual(progress.quizzes_completed, 0)

    def test_practice_xp_capped_per_day_and_all_stars_bonus_once(self):
        results = [self.finish(level)[1] for level in range(4)]
        self.assertEqual(sum(r["xp_detail"]["pratique"] for r in results), PRACTICE_DAILY_CAP)
        self.assertEqual(results[-1]["total_stars"], 12)
        self.assertEqual([r["xp_detail"]["bonus"] for r in results], [0, 0, 0, 50])
        _, replay = self.finish(3)
        self.assertEqual(replay["xp_detail"]["bonus"], 0)

    def test_badges_awarded(self):
        _, data = self.finish(0)
        self.assertIn("jeu_premiers_pas", [b["code"] for b in data["badges"]])
        self.assertTrue(QuizUserBadge.objects.filter(user=self.user, badge__code="jeu_premiers_pas").exists())

    def test_post_without_csrf_token_is_403(self):
        run = make_run(self.user, 0)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.user)
        response = self.post_json(RESULT_URL, payload(run), client=strict)
        self.assertEqual(response.status_code, 403)


class PracticeXpRuleTests(TestCase):
    """Regle anti-farm de l'XP de pratique (spec §14.3 etape 9, §18 A2)."""

    def test_base_plus_quiz_bonus(self):
        self.assertEqual(services.compute_practice_xp(0, 0, False), 5)
        self.assertEqual(services.compute_practice_xp(3, 0, False), 11)

    def test_zero_when_level_already_practiced_today(self):
        self.assertEqual(services.compute_practice_xp(3, 0, True), 0)

    def test_daily_cap(self):
        self.assertEqual(services.compute_practice_xp(3, 25, False), 5)
        self.assertEqual(services.compute_practice_xp(3, 30, False), 0)
        self.assertEqual(services.compute_practice_xp(3, 45, False), 0)
