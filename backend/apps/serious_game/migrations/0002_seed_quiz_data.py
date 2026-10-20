from django.db import migrations


def seed_quiz_data(apps, schema_editor):
    QuizTheme = apps.get_model("serious_game", "QuizTheme")
    QuizQuestion = apps.get_model("serious_game", "QuizQuestion")
    QuizReponse = apps.get_model("serious_game", "QuizReponse")

    theme_usage, _ = QuizTheme.objects.get_or_create(
        nom="Utilisation d Hydria",
        defaults={
            "description": "Quiz introductif sur les workflows planning, releves, encaissements, stocks et tableaux de bord.",
            "ordre_affichage": 10,
            "actif": True,
        },
    )
    theme_data, _ = QuizTheme.objects.get_or_create(
        nom="Connaissance des donnees Hydria",
        defaults={
            "description": "Questions dynamiques basees sur les donnees reelles: ouvrages, villages, points d eau et responsables.",
            "ordre_affichage": 20,
            "actif": True,
        },
    )

    static_questions = [
        {
            "texte_question": "Dans Hydria, ou saisit-on en premier une activite terrain planifiee ?",
            "type_question": "qcm",
            "difficulte": "facile",
            "ordre_affichage": 10,
            "explication": "Le workflow commence par la saisie du planning, qui structure ensuite les details et validations.",
            "reponses": [
                ("Dans le formulaire de planning", True),
                ("Dans le module comptabilite", False),
                ("Dans les stocks", False),
                ("Dans les journaux DiameX", False),
            ],
        },
        {
            "texte_question": "Un releve doit etre rattache a un point d eau pour etre exploitable dans Hydria.",
            "type_question": "vrai_faux",
            "difficulte": "facile",
            "ordre_affichage": 20,
            "explication": "Sans rattachement au point d eau, le releve ne peut pas alimenter correctement la facturation et les analyses.",
            "reponses": [("Vrai", True), ("Faux", False)],
        },
        {
            "texte_question": "Quel module utilise-t-on pour encaisser plusieurs factures volumetriques en une seule operation ?",
            "type_question": "qcm",
            "difficulte": "moyenne",
            "ordre_affichage": 30,
            "explication": "Le module Encaissement regroupe la selection des factures, le journal et la validation comptable.",
            "reponses": [
                ("Facturation / Encaissement", True),
                ("Organisation / Ouvrages", False),
                ("Systeme / Logs", False),
                ("Recrutement", False),
            ],
        },
        {
            "texte_question": "Quand une ligne de stock est sortie sans reapprovisionnement, le stock disponible augmente.",
            "type_question": "vrai_faux",
            "difficulte": "facile",
            "ordre_affichage": 40,
            "explication": "Une sortie de stock diminue le stock disponible tant qu aucun mouvement inverse ne compense.",
            "reponses": [("Vrai", False), ("Faux", True)],
        },
        {
            "texte_question": "Quel ecran sert a suivre les pannes et reparations par ouvrage ?",
            "type_question": "qcm",
            "difficulte": "moyenne",
            "ordre_affichage": 50,
            "explication": "Le suivi des reparations centralise les ouvrages, priorites, statuts et actions de maintenance.",
            "reponses": [
                ("Plannings / Reparations", True),
                ("Facturation / Releves", False),
                ("Employees / Organigramme", False),
                ("Comptabilite / Accueil", False),
            ],
        },
        {
            "texte_question": "Les tableaux de bord servent seulement a afficher des chiffres, jamais a controler des anomalies.",
            "type_question": "vrai_faux",
            "difficulte": "moyenne",
            "ordre_affichage": 60,
            "explication": "Les dashboards Hydria servent aussi a detecter ecarts, impayes, depassements, lignes non pointees et autres anomalies.",
            "reponses": [("Vrai", False), ("Faux", True)],
        },
    ]

    for question_data in static_questions:
        question, _ = QuizQuestion.objects.get_or_create(
            theme=theme_usage,
            texte_question=question_data["texte_question"],
            defaults={
                "type_question": question_data["type_question"],
                "difficulte": question_data["difficulte"],
                "ordre_affichage": question_data["ordre_affichage"],
                "explication": question_data["explication"],
                "actif": True,
                "est_dynamique": False,
            },
        )
        for index, (texte_reponse, est_correcte) in enumerate(question_data["reponses"], start=1):
            QuizReponse.objects.get_or_create(
                question=question,
                texte_reponse=texte_reponse,
                defaults={
                    "est_correcte": est_correcte,
                    "ordre_affichage": index,
                },
            )

    dynamic_questions = [
        ("Combien d ouvrages geres sur une annee ?", "generate_nombre_ouvrages_par_annee", "numerique", 10),
        ("Combien de points d eau actifs dans un village ?", "generate_points_eau_par_village", "numerique", 20),
        ("Combien de points d eau actifs dans un ouvrage ?", "generate_points_eau_par_ouvrage", "numerique", 30),
        ("Combien d ouvrages actifs pour un responsable ?", "generate_ouvrages_par_responsable", "numerique", 40),
        ("Identifier le responsable d un ouvrage", "generate_responsable_ouvrage", "qcm", 50),
    ]

    for texte_question, code_generation, type_question, ordre_affichage in dynamic_questions:
        QuizQuestion.objects.get_or_create(
            theme=theme_data,
            texte_question=texte_question,
            defaults={
                "type_question": type_question,
                "difficulte": "moyenne",
                "ordre_affichage": ordre_affichage,
                "explication": "Question generee automatiquement a partir des donnees Hydria.",
                "actif": True,
                "est_dynamique": True,
                "code_generation": code_generation,
            },
        )


def unseed_quiz_data(apps, schema_editor):
    QuizTheme = apps.get_model("serious_game", "QuizTheme")
    QuizTheme.objects.filter(
        nom__in=["Utilisation d Hydria", "Connaissance des donnees Hydria"]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("serious_game", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_quiz_data, unseed_quiz_data),
    ]
