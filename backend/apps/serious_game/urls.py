from django.urls import path

from . import views, views_game3d


app_name = "serious_game"


urlpatterns = [
    path("", views.serious_game_home, name="home"),
    path("simulation/", views.serious_game_simulation, name="simulation"),
    path("jeu-3d/", views_game3d.jeu_3d, name="jeu_3d"),
    path("jeu-3d/api/questions/", views_game3d.api_questions, name="jeu3d_questions"),
    path("jeu-3d/api/repondre/", views_game3d.api_answer, name="jeu3d_answer"),
    path("jeu-3d/api/resultat/", views_game3d.api_result, name="jeu3d_result"),
    path("quiz/", views.quiz_theme_list, name="quiz_themes"),
    path("quiz/historique/", views.quiz_history, name="quiz_history"),
    path("quiz/progression/", views.progress_dashboard, name="progress_dashboard"),
    path("quiz/theme/<uuid:theme_id>/commencer/", views.quiz_start, name="quiz_start"),
    path("quiz/session/<uuid:session_id>/", views.quiz_take, name="quiz_take"),
    path("quiz/session/<uuid:session_id>/resultat/", views.quiz_result, name="quiz_result"),
]
