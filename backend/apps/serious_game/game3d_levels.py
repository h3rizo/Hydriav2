"""Configuration serveur de Hydria Quest 3D (spec §14.2).

Module de donnees pur : aucun import de modele, il peut etre importe depuis
models.py, les migrations, les services et les vues sans cycle.

Les valeurs `gouttes`, `slots` et `min_s` doivent rester identiques aux
fichiers de niveaux JS (`academy3d/levels/L*.js`, §17 point 1).
"""

GAME3D_VERSION = "1.0.0"

LEVELS = {
    0: dict(
        code="L0_premier_jour",
        titre="Premier jour au village",
        slots=[("q1", "usage_intro", "vrai_faux")],
        gouttes=30, par_s=240, min_s=60, star_xp=15, star3="quiz_first_try", score_max=400,
    ),
    1: dict(
        code="L1_pompe_panne",
        titre="La pompe en panne",
        slots=[("q1", "stocks_livraisons", None), ("q2", "planning_validation", None)],
        gouttes=40, par_s=300, min_s=90, star_xp=25, star3="quiz_first_try", score_max=600,
    ),
    2: dict(
        code="L2_tournee",
        titre="Tournée d'encaissement",
        slots=[("q1", "encaissements", None), ("q2", "encaissements", None), ("q3", "releves_facturation", None)],
        gouttes=40, par_s=330, min_s=100, star_xp=30, star3="tournee_a_l_heure", score_max=700,
    ),
    3: dict(
        code="L3_chateau",
        titre="Journée chargée au château d'eau",
        slots=[("q1", "dashboards_controles", None), ("q2", "data_villages_ouvrages", None), ("q3", "dashboards_controles", None)],
        gouttes=50, par_s=360, min_s=80, star_xp=30, star3="service_exemplaire", score_max=800,
    ),
}

ALL_STARS_BONUS_XP = 50
PRACTICE_BASE_XP, PRACTICE_PER_QUIZ_XP, PRACTICE_DAILY_CAP = 5, 2, 30
START_RATE_LIMIT_S, RUN_MAX_AGE_H, MAX_ANSWER_POSTS_PER_RUN = 8, 48, 30
QUESTION_MAX_LEN, OPTION_MAX_LEN = 220, 80

# 3 etoiles par niveau : bit0 = termine, bit1 = toutes les gouttes, bit2 = regle du niveau.
STARS_PER_LEVEL = 3
MAX_TOTAL_STARS = STARS_PER_LEVEL * len(LEVELS)  # 12

FALLBACK_THEME_NAME = "Questions du jeu"


def _vf(qid, text, correct_is_true, explication):
    """Question vrai/faux : options toujours dans l'ordre « Vrai », « Faux »."""
    return {
        "id": qid,
        "type": "vrai_faux",
        "text": text,
        "options": [
            {"text": "Vrai", "correct": bool(correct_is_true)},
            {"text": "Faux", "correct": not correct_is_true},
        ],
        "explication": explication,
    }


def _qcm(qid, text, options, explication):
    """Question QCM : `options` est une liste de (texte, correct) dans l'ordre affiche."""
    return {
        "id": qid,
        "type": "qcm",
        "text": text,
        "options": [{"text": label, "correct": bool(ok)} for label, ok in options],
        "explication": explication,
    }


FALLBACK_QUESTIONS = {
    0: [
        _vf(
            "fb_l0_1",
            "Une borne fontaine qui fuit doit être signalée, même si l'eau coule encore.",
            True,
            "Une petite fuite gaspille de l'eau et s'aggrave : on la signale tout de suite pour planifier la réparation.",
        ),
        _vf(
            "fb_l0_2",
            "Un relevé doit être rattaché à un point d'eau pour être exploitable.",
            True,
            "Sans point d'eau, impossible de calculer le volume, la facture ni l'historique de l'usager.",
        ),
    ],
    1: [
        _qcm(
            "fb_l1_1",
            "Dans quel ordre suit-on une réparation ?",
            [
                ("Planifiée → Signalée → Validée → Terminée", False),
                ("Signalée → Planifiée → En cours → Terminée → Validée", True),
                ("En cours → Terminée → Signalée", False),
            ],
            "Une panne est d'abord signalée, puis planifiée, réalisée (en cours), terminée et enfin validée par le responsable.",
        ),
        _vf(
            "fb_l1_2",
            "Le matériel peut sortir du magasin sans bon de livraison.",
            False,
            "Le bon de livraison trace chaque sortie de matériel : sans lui, le stock et les coûts de la réparation sont faux.",
        ),
        _vf(
            "fb_l1_3",
            "Une réparation terminée doit encore être validée par le responsable.",
            True,
            "La validation par le responsable confirme le travail et clôture la réparation dans le suivi.",
        ),
    ],
    2: [
        _qcm(
            "fb_l2_1",
            "Quelle est la date limite de paiement d'une facture de kiosque ?",
            [
                ("Le 5 du mois", True),
                ("Le 15 du mois", False),
                ("Le 30 du mois", False),
            ],
            "Les factures de kiosque doivent être payées avant le 5 du mois ; le 15 concerne les branchements particuliers.",
        ),
        _vf(
            "fb_l2_2",
            "Après le paiement d'un usager coupé, il faut remettre l'eau.",
            True,
            "Une fois la dette réglée, la remise en eau doit être faite rapidement : c'est le service promis à l'usager.",
        ),
        _vf(
            "fb_l2_3",
            "Les reçus de la tournée doivent revenir à la caissière pour être enregistrés.",
            True,
            "La caissière enregistre chaque reçu : c'est ce qui permet de rapprocher l'argent encaissé et la comptabilité.",
        ),
    ],
    3: [
        _vf(
            "fb_l3_1",
            "Un tableau de bord sert aussi à repérer des anomalies.",
            True,
            "Un chiffre anormal (volume, taux de paiement, pannes) sur un tableau de bord est souvent le premier signe d'un problème.",
        ),
        _qcm(
            "fb_l3_2",
            "Depuis un ouvrage, quelle chaîne mène à sa commune ?",
            [
                ("Village → Ouvrage → District → Commune", False),
                ("Parcelle → Commune → Fokontany → Village", False),
                ("Point d'eau → Parcelle → Village → Fokontany → Commune", True),
            ],
            "Un ouvrage est relié à ses points d'eau, placés sur une parcelle d'un village, lui-même dans un fokontany de la commune.",
        ),
        _vf(
            "fb_l3_3",
            "Une vanne fermée peut priver tout un quartier d'eau.",
            True,
            "Une vanne commande tout un tronçon du réseau : il faut toujours vérifier qui est desservi avant de la fermer.",
        ),
    ],
}


def get_level_cfg(level):
    """Configuration d'un niveau, ou None si le niveau n'existe pas."""
    return LEVELS.get(level)


def slot_ids(level):
    cfg = LEVELS.get(level)
    return [slot for slot, _module, _ptype in cfg["slots"]] if cfg else []


def fallback_options(question):
    """Options d'une question de secours avec les identifiants `choice_{n}` (dans l'ordre)."""
    return [
        {"id": f"choice_{index}", "text": option["text"], "correct": bool(option["correct"])}
        for index, option in enumerate(question["options"], start=1)
    ]


def levels_meta():
    """Bloc `levels_meta` du bootstrap (§14.5)."""
    return {
        str(level): {
            "gouttes": cfg["gouttes"],
            "slots": [slot for slot, _module, _ptype in cfg["slots"]],
            "par_s": cfg["par_s"],
            "min_s": cfg["min_s"],
        }
        for level, cfg in LEVELS.items()
    }


def fallback_questions_public():
    """Bloc `fallback_questions` du bootstrap : reponses incluses (usage hors ligne uniquement, sans XP)."""
    return {
        str(level): [
            {
                "id": question["id"],
                "type": question["type"],
                "text": question["text"],
                "options": fallback_options(question),
                "explication": question["explication"],
            }
            for question in questions
        ]
        for level, questions in FALLBACK_QUESTIONS.items()
    }
