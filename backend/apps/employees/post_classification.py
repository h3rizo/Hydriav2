"""
Classification transversale des postes (Type x Niveau) - source Python.

Miroir exact de `static/js/post_classification.js` (memes codes, memes
libelles, memes classes Tailwind), pour les pages rendues cote serveur
(poste_detail, poste_list) sans dupliquer les regles de calcul JS.

Principe visuel : la COULEUR encode le TYPE, l'INTENSITE du badge encode
le NIVEAU (Execution = leger, Management = plein/marque).
"""

# badge_solid reste bg-{couleur}-600 en clair comme en sombre : cette teinte
# doit rester identique a PostClassification.TYPES[...].hex (static/js/post_classification.js)
# pour que la couleur des badges corresponde exactement a celle utilisee sur le graphique.
TYPES = {
    'OPERATIONNEL': {
        'label': 'Opérationnel',
        'text_class': 'text-blue-600 dark:text-blue-400',
        'badge_light': 'bg-blue-100 text-blue-700 border border-blue-200 dark:bg-blue-950 dark:text-blue-300 dark:border-blue-800',
        'badge_solid': 'bg-blue-600 text-white dark:bg-blue-600',
    },
    'ADMINISTRATIF': {
        'label': 'Administratif',
        'text_class': 'text-violet-600 dark:text-violet-400',
        'badge_light': 'bg-violet-100 text-violet-700 border border-violet-200 dark:bg-violet-950 dark:text-violet-300 dark:border-violet-800',
        'badge_solid': 'bg-violet-600 text-white dark:bg-violet-600',
    },
    'SOUTIEN': {
        'label': 'Soutien',
        'text_class': 'text-slate-600 dark:text-slate-400',
        'badge_light': 'bg-slate-100 text-slate-700 border border-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-600',
        'badge_solid': 'bg-slate-600 text-white dark:bg-slate-600',
    },
    'TRANSVERSAL': {
        'label': 'Transversal',
        'text_class': 'text-teal-600 dark:text-teal-400',
        'badge_light': 'bg-teal-100 text-teal-700 border border-teal-200 dark:bg-teal-950 dark:text-teal-300 dark:border-teal-800',
        'badge_solid': 'bg-teal-600 text-white dark:bg-teal-600',
    },
}

NIVEAUX = {
    'EXECUTION': {'label': 'Exécution', 'variant': 'light'},
    'MANAGEMENT': {'label': 'Management', 'variant': 'solid'},
}

NON_CLASSE_CLASS = 'bg-base-200 text-base-content/50 border border-base-300'


def type_label(type_code):
    entry = TYPES.get(type_code)
    return entry['label'] if entry else 'Non classé'


def niveau_label(niveau_code):
    entry = NIVEAUX.get(niveau_code)
    return entry['label'] if entry else 'Non classé'


def type_badge_class(type_code):
    entry = TYPES.get(type_code)
    return entry['badge_light'] if entry else NON_CLASSE_CLASS


def niveau_badge_class(type_code, niveau_code):
    type_entry = TYPES.get(type_code)
    niveau_entry = NIVEAUX.get(niveau_code)
    if not type_entry or not niveau_entry:
        return NON_CLASSE_CLASS
    return type_entry['badge_solid'] if niveau_entry['variant'] == 'solid' else type_entry['badge_light']


def text_class(type_code):
    entry = TYPES.get(type_code)
    return entry['text_class'] if entry else 'text-base-content/70'
