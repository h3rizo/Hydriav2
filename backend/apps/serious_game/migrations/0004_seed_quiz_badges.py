from django.db import migrations


BADGES = [
    ("first_quiz_completed", "Premier quiz termine", "Premiere lecon terminee dans Hydria Academy.", "fa-flag-checkered", "completed_quizzes", 1),
    ("five_quizzes_completed", "Cinq quiz termines", "Vous avez termine cinq quiz Hydria.", "fa-hand-sparkles", "completed_quizzes", 5),
    ("perfect_score", "Score parfait", "Obtenir 100 % sur un quiz.", "fa-bullseye", "perfect_score", 100),
    ("streak_5_correct", "Serie de 5", "Atteindre cinq bonnes reponses d'affilee.", "fa-fire", "correct_streak", 5),
    ("planning_beginner", "Planning debutant", "Premier quiz planning reussi.", "fa-calendar-check", "theme_success", 1),
    ("encaissement_beginner", "Encaissement debutant", "Premier quiz encaissement reussi.", "fa-cash-register", "theme_success", 1),
    ("data_explorer", "Explorateur terrain", "Premier quiz de donnees terrain reussi.", "fa-map-location-dot", "theme_success", 1),
]


def seed_badges(apps, schema_editor):
    QuizBadge = apps.get_model("serious_game", "QuizBadge")
    existing = QuizBadge.objects.all().order_by("created_at")
    for index, badge in enumerate(existing, start=1):
        if not badge.code:
            badge.code = f"legacy_badge_{index}"
            badge.save(update_fields=["code"])

    for code, nom, description, icon, condition_type, condition_value in BADGES:
        QuizBadge.objects.update_or_create(
            code=code,
            defaults={
                "nom": nom,
                "description": description,
                "icon": icon,
                "condition_type": condition_type,
                "condition_value": condition_value,
                "actif": True,
            },
        )


def unseed_badges(apps, schema_editor):
    QuizBadge = apps.get_model("serious_game", "QuizBadge")
    QuizBadge.objects.filter(code__in=[badge[0] for badge in BADGES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("serious_game", "0003_quiz_progression"),
    ]

    operations = [
        migrations.RunPython(seed_badges, unseed_badges),
    ]
