from django.db import migrations


USAGE_MODULES = [
    {
        "module_code": "usage_intro",
        "nom": "Utilisation d Hydria",
        "description": "Prise en main generale des workflows Hydria et des ecrans de base.",
        "icon": "fa-compass",
        "ordre_affichage": 10,
        "parcours_code": "usage",
        "questions": [],
    },
    {
        "module_code": "planning_validation",
        "nom": "Planning et validations",
        "description": "Saisie, validation et suivi des plannings terrain et reparations.",
        "icon": "fa-calendar-check",
        "ordre_affichage": 20,
        "parcours_code": "usage",
        "previous": "usage_intro",
        "questions": [
            {
                "texte_question": "Avant de valider un planning, que faut-il verifier en priorite ?",
                "type_question": "qcm",
                "ordre_affichage": 10,
                "explication": "La validation verrouille le contenu metier: date, participants, activite et ouvrage doivent etre cohérents.",
                "reponses": [
                    ("La coherence activite, employe et ouvrage", True),
                    ("Le theme du navigateur", False),
                    ("Le numero du serveur", False),
                    ("Le mot de passe de l'utilisateur", False),
                ],
            },
            {
                "texte_question": "Une reparation avec bon de livraison peut etre suivie depuis le module plannings.",
                "type_question": "vrai_faux",
                "ordre_affichage": 20,
                "explication": "Les reparations, avances et bons de livraison restent relies au planning de terrain.",
                "reponses": [("Vrai", True), ("Faux", False)],
            },
        ],
    },
    {
        "module_code": "releves_facturation",
        "nom": "Releves et facturation",
        "description": "Lecture des index, releves terrain et preparation de la facturation.",
        "icon": "fa-gauge-high",
        "ordre_affichage": 30,
        "parcours_code": "usage",
        "previous": "planning_validation",
        "questions": [
            {
                "texte_question": "Pourquoi un releve doit-il etre rattache au bon point d'eau ?",
                "type_question": "qcm",
                "ordre_affichage": 10,
                "explication": "Le point d'eau conditionne l'historique d'index, la facture et les tableaux de bord.",
                "reponses": [
                    ("Pour fiabiliser volume, facture et historique du client", True),
                    ("Seulement pour changer la couleur de la page", False),
                    ("Uniquement pour exporter en PDF", False),
                    ("Ce n'est pas necessaire", False),
                ],
            },
            {
                "texte_question": "Un releve mal date peut fausser le mois de facturation.",
                "type_question": "vrai_faux",
                "ordre_affichage": 20,
                "explication": "Le mois du releve est un repere critique pour la facture et le controle des encaissements.",
                "reponses": [("Vrai", True), ("Faux", False)],
            },
        ],
    },
    {
        "module_code": "encaissements",
        "nom": "Encaissements",
        "description": "Selection des factures, coherence des ouvrages et controle des recettes.",
        "icon": "fa-cash-register",
        "ordre_affichage": 40,
        "parcours_code": "usage",
        "previous": "releves_facturation",
        "questions": [
            {
                "texte_question": "Dans Hydria, peut-on encaisser ensemble des factures de mois differents ?",
                "type_question": "vrai_faux",
                "ordre_affichage": 10,
                "explication": "Le workflow d'encaissement a ete securise pour eviter de melanger mois et ouvrages dans un meme lot.",
                "reponses": [("Vrai", False), ("Faux", True)],
            },
            {
                "texte_question": "Quel ecran centralise le scan QR et le traitement des factures encaissees ?",
                "type_question": "qcm",
                "ordre_affichage": 20,
                "explication": "Le module Facturation / Encaissement reste l'ecran principal de l'operation.",
                "reponses": [
                    ("Facturation / Encaissement", True),
                    ("Recrutement / Candidats", False),
                    ("Organisation / Responsables", False),
                    ("Systeme / Utilisateurs", False),
                ],
            },
        ],
    },
    {
        "module_code": "stocks_livraisons",
        "nom": "Stocks et livraisons",
        "description": "Mouvements de stock, livraisons terrain et verification des disponibilites.",
        "icon": "fa-boxes-stacked",
        "ordre_affichage": 50,
        "parcours_code": "usage",
        "previous": "encaissements",
        "questions": [
            {
                "texte_question": "Si le magasin change et que le stock redevient positif, la ligne de livraison doit redevenir selectionnable.",
                "type_question": "vrai_faux",
                "ordre_affichage": 10,
                "explication": "Le recalcul du stock doit re-activer la ligne si le nouveau magasin permet la livraison.",
                "reponses": [("Vrai", True), ("Faux", False)],
            },
            {
                "texte_question": "Quel module sert a voir les lignes a avancer ou a livrer pour la caissiere ?",
                "type_question": "qcm",
                "ordre_affichage": 20,
                "explication": "La page des avances/livraisons centralise les lignes a traiter ensuite par la caissiere.",
                "reponses": [
                    ("Plannings / Avances", True),
                    ("Comptabilite / Import", False),
                    ("Documentation", False),
                    ("Organisation / Ouvrages", False),
                ],
            },
        ],
    },
    {
        "module_code": "dashboards_controles",
        "nom": "Dashboards et controles",
        "description": "Lecture des tableaux de bord, verification des anomalies et controle metier.",
        "icon": "fa-chart-line",
        "ordre_affichage": 60,
        "parcours_code": "usage",
        "previous": "stocks_livraisons",
        "questions": [
            {
                "texte_question": "Un dashboard Hydria sert aussi a reperer les anomalies, pas seulement a afficher des chiffres.",
                "type_question": "vrai_faux",
                "ordre_affichage": 10,
                "explication": "Les dashboards servent au recoupement, au controle et a la decision metier.",
                "reponses": [("Vrai", True), ("Faux", False)],
            },
            {
                "texte_question": "Quel dashboard compare les paiements de volumetrique et les montants attendus par ouvrage ?",
                "type_question": "qcm",
                "ordre_affichage": 20,
                "explication": "Le dashboard paiements volume est l'ecran de reference pour ce controle.",
                "reponses": [
                    ("Dashboard paiements volume", True),
                    ("Dashboard recrutement", False),
                    ("Dashboard pannes", False),
                    ("Simulation Hydria Academy", False),
                ],
            },
        ],
    },
]


DATA_MODULES = [
    {
        "module_code": "data_intro",
        "nom": "Connaissance des donnees Hydria",
        "description": "Premier test sur les ouvrages, villages, points d'eau et responsabilites.",
        "icon": "fa-map-location-dot",
        "ordre_affichage": 10,
        "parcours_code": "data",
        "questions": [],
    },
    {
        "module_code": "data_points_responsables",
        "nom": "Points d eau et responsables",
        "description": "Questions terrain sur les points d'eau actifs et les responsables d'ouvrages.",
        "icon": "fa-faucet-drip",
        "ordre_affichage": 20,
        "parcours_code": "data",
        "previous": "data_intro",
        "dynamic_questions": [
            ("Combien de points d eau actifs dans un ouvrage ?", "generate_points_eau_par_ouvrage", "numerique", 10),
            ("Combien d ouvrages actifs pour un responsable ?", "generate_ouvrages_par_responsable", "numerique", 20),
            ("Identifier le responsable d un ouvrage", "generate_responsable_ouvrage", "qcm", 30),
        ],
    },
    {
        "module_code": "data_villages_ouvrages",
        "nom": "Villages et ouvrages",
        "description": "Questions dynamiques sur les villages desservis, les ouvrages actifs et leurs points d'eau.",
        "icon": "fa-diagram-project",
        "ordre_affichage": 30,
        "parcours_code": "data",
        "previous": "data_points_responsables",
        "dynamic_questions": [
            ("Combien d ouvrages geres sur une annee ?", "generate_nombre_ouvrages_par_annee", "numerique", 10),
            ("Combien de points d eau actifs dans un village ?", "generate_points_eau_par_village", "numerique", 20),
        ],
        "questions": [
            {
                "texte_question": "Les villages desservis peuvent etre analyses depuis les donnees combinees ouvrages, parcelles et points d'eau.",
                "type_question": "vrai_faux",
                "ordre_affichage": 40,
                "explication": "La connaissance terrain repose souvent sur le croisement de plusieurs tables Hydria.",
                "reponses": [("Vrai", True), ("Faux", False)],
            },
        ],
    },
]


def _get_or_create_theme(QuizTheme, module_def, previous_theme=None):
    defaults = {
        "description": module_def["description"],
        "ordre_affichage": module_def["ordre_affichage"],
        "actif": True,
        "parcours_code": module_def["parcours_code"],
        "module_code": module_def["module_code"],
        "icon": module_def["icon"],
        "score_deblocage": 80,
        "module_precedent": previous_theme,
    }
    theme = QuizTheme.objects.filter(module_code=module_def["module_code"]).first()
    if not theme:
        theme = QuizTheme.objects.filter(nom=module_def["nom"]).first()
    if theme:
        for key, value in {"nom": module_def["nom"], **defaults}.items():
            setattr(theme, key, value)
        theme.save()
        return theme

    theme = QuizTheme.objects.create(
        nom=module_def["nom"],
        **defaults,
    )
    return theme


def _seed_static_questions(QuizQuestion, QuizReponse, theme, questions):
    for question_def in questions:
        question, _ = QuizQuestion.objects.update_or_create(
            theme=theme,
            texte_question=question_def["texte_question"],
            defaults={
                "type_question": question_def["type_question"],
                "difficulte": "moyenne",
                "ordre_affichage": question_def["ordre_affichage"],
                "explication": question_def["explication"],
                "actif": True,
                "est_dynamique": False,
                "code_generation": "",
            },
        )
        for index, (texte_reponse, est_correcte) in enumerate(question_def["reponses"], start=1):
            QuizReponse.objects.update_or_create(
                question=question,
                texte_reponse=texte_reponse,
                defaults={"est_correcte": est_correcte, "ordre_affichage": index},
            )


def _seed_dynamic_questions(QuizQuestion, theme, questions):
    for texte_question, code_generation, type_question, ordre_affichage in questions:
        QuizQuestion.objects.update_or_create(
            theme=theme,
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


def seed_modules(apps, schema_editor):
    QuizTheme = apps.get_model("serious_game", "QuizTheme")
    QuizQuestion = apps.get_model("serious_game", "QuizQuestion")
    QuizReponse = apps.get_model("serious_game", "QuizReponse")

    by_code = {}
    for module_def in USAGE_MODULES + DATA_MODULES:
        previous_theme = by_code.get(module_def.get("previous"))
        theme = _get_or_create_theme(QuizTheme, module_def, previous_theme)
        by_code[module_def["module_code"]] = theme
        if module_def.get("questions"):
            _seed_static_questions(QuizQuestion, QuizReponse, theme, module_def["questions"])
        if module_def.get("dynamic_questions"):
            _seed_dynamic_questions(QuizQuestion, theme, module_def["dynamic_questions"])


def unseed_modules(apps, schema_editor):
    QuizTheme = apps.get_model("serious_game", "QuizTheme")
    QuizTheme.objects.filter(module_code__in=[module["module_code"] for module in USAGE_MODULES + DATA_MODULES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("serious_game", "0007_quiztheme_path_fields"),
    ]

    operations = [
        migrations.RunPython(seed_modules, unseed_modules),
    ]
