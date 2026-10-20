from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import QuizBadge, QuizQuestion, QuizReponse, QuizSession, QuizTheme, QuizUserProgress
from .quiz_services import calculate_level


class QuizProgressionTests(TestCase):
    def test_calculate_level_thresholds(self):
        self.assertEqual(calculate_level(0), 1)
        self.assertEqual(calculate_level(99), 1)
        self.assertEqual(calculate_level(100), 2)
        self.assertEqual(calculate_level(249), 2)
        self.assertEqual(calculate_level(250), 3)
        self.assertEqual(calculate_level(500), 4)
        self.assertEqual(calculate_level(1000), 5)


class SeriousGamePageTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="serious_game_tester",
            password="testpass123",
        )

    def test_requires_login(self):
        response = self.client.get(reverse("serious_game:home"))
        self.assertEqual(response.status_code, 302)

    def test_progress_dashboard_renders_for_authenticated_user(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("serious_game:progress_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tableau de progression")
        self.assertTrue(QuizUserProgress.objects.filter(user=self.user).exists())


class QuizFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="quiz_user",
            password="testpass123",
        )
        self.theme = QuizTheme.objects.create(
            nom="Theme planning test",
            description="Theme de test",
            actif=True,
        )
        self.question = QuizQuestion.objects.create(
            theme=self.theme,
            texte_question="Quel module sert a enregistrer un releve ?",
            type_question=QuizQuestion.TYPE_QCM,
            difficulte=QuizQuestion.DIFFICULTE_FACILE,
            actif=True,
        )
        QuizReponse.objects.create(question=self.question, texte_reponse="Releves", est_correcte=True, ordre_affichage=1)
        QuizReponse.objects.create(question=self.question, texte_reponse="Stocks", est_correcte=False, ordre_affichage=2)
        QuizBadge.objects.create(code="first_quiz_completed", nom="Premier quiz termine", actif=True)
        QuizBadge.objects.create(code="planning_beginner", nom="Planning debutant", actif=True)

    def test_theme_list_renders(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("serious_game:quiz_themes"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Theme planning test")

    def test_user_can_complete_quiz_session_and_gain_xp(self):
        self.client.force_login(self.user)
        start_response = self.client.get(reverse("serious_game:quiz_start", args=[self.theme.id]))
        self.assertEqual(start_response.status_code, 302)

        session = QuizSession.objects.get(utilisateur=self.user, theme=self.theme)
        session_question = session.session_questions.first()
        self.assertIsNotNone(session_question)

        response = self.client.post(
            reverse("serious_game:quiz_take", args=[session.id]),
            {"selected_choice": session_question.answer_options[0]["id"], "action": "submit_answer"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        session.refresh_from_db()
        progress = QuizUserProgress.objects.get(user=self.user)
        self.assertEqual(session.score, 1)
        self.assertEqual(session.statut, QuizSession.STATUT_TERMINE)
        self.assertEqual(session.xp_gagne, 10)
        self.assertGreaterEqual(progress.total_xp, 10)
        self.assertTrue(progress.quizzes_completed >= 1)

    def test_first_session_awards_badge(self):
        self.client.force_login(self.user)
        self.client.get(reverse("serious_game:quiz_start", args=[self.theme.id]))
        session = QuizSession.objects.get(utilisateur=self.user, theme=self.theme)
        session_question = session.session_questions.first()
        self.client.post(
            reverse("serious_game:quiz_take", args=[session.id]),
            {"selected_choice": session_question.answer_options[0]["id"], "action": "submit_answer"},
            follow=True,
        )
        self.assertTrue(self.user.quiz_user_badges.filter(badge__code="first_quiz_completed").exists())
