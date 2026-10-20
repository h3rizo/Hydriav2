"""
Phase B - branche la page CRUD des regles de saisie :
  - import + routes dans apps/accounting/urls.py
  - liens "Regles de saisie" dans templates/accounting/base.html (navbar + 2 sidebars)

  cd /home/soakoja/hydria/backend && python patch_regles_saisie_ui.py

Idempotent. Signale "ANCRE INTROUVABLE" sans rien casser si une ancre a bouge.
Prerequis : le patch Phase 5 (liens "Saisie comptable") doit deja etre applique.
"""


def patch(path, steps):
    try:
        s = open(path, encoding="utf-8").read()
    except FileNotFoundError:
        print(f"  {path} : absent"); return
    orig = s
    for label, done, fn in steps:
        if done(s):
            print(f"  {path} : {label} -> deja fait"); continue
        s2 = fn(s)
        print(f"  {path} : {label} -> " + ("OK" if s2 != s else "ANCRE INTROUVABLE"))
        s = s2
    if s != orig:
        open(path, "w", encoding="utf-8").write(s)


# --- urls.py ---
# L'import va apres le bloc views_ai_prefill s'il existe, sinon apres views ; les
# routes sont ajoutees en fin de fichier (independant de la mise en page).
URLS_IMPORT_ANCHOR = "try:\n    from . import views_ai_prefill\nexcept Exception:\n    views_ai_prefill = None\n"
URLS_IMPORT_ANCHOR2 = "from . import views\n"
URLS_IMPORT_ADD = "try:\n    from . import views_regles_saisie\nexcept Exception:\n    views_regles_saisie = None\n"

URLS_BLOCK_ADD = """

# Phase B - regles de saisie guidee
if views_regles_saisie is not None:
    v = views_regles_saisie
    urlpatterns += [
        path('regles-saisie/', v.regles_saisie_list, name='regles_saisie_list'),
        path('regles-saisie/api/list/', v.api_regles_list, name='api_regles_saisie_list'),
        path('regles-saisie/api/fournisseurs-search/', v.api_fournisseurs_search, name='api_regles_saisie_fournisseurs_search'),
        path('regles-saisie/<uuid:regle_id>/', v.regle_saisie_edit, name='regle_saisie_edit'),
        path('regles-saisie/api/<uuid:regle_id>/', v.api_regle_detail, name='api_regle_saisie_detail'),
        path('regles-saisie/api/<uuid:regle_id>/update/', v.api_regle_update, name='api_regle_saisie_update'),
        path('regles-saisie/api/<uuid:regle_id>/preview/', v.api_regle_preview, name='api_regle_saisie_preview'),
        path('regles-saisie/api/<uuid:regle_id>/fournisseurs/', v.api_regle_fournisseurs, name='api_regle_saisie_fournisseurs'),
    ]
"""


def _add_import(s):
    if URLS_IMPORT_ANCHOR in s:
        return s.replace(URLS_IMPORT_ANCHOR, URLS_IMPORT_ANCHOR + URLS_IMPORT_ADD, 1)
    if URLS_IMPORT_ANCHOR2 in s:
        return s.replace(URLS_IMPORT_ANCHOR2, URLS_IMPORT_ANCHOR2 + URLS_IMPORT_ADD, 1)
    return s


patch("apps/accounting/urls.py", [
    ("import views_regles_saisie",
     lambda s: "views_regles_saisie" in s,
     _add_import),
    ("routes regles-saisie (fin de fichier)",
     lambda s: "regles_saisie_list" in s,
     lambda s: s.rstrip("\n") + "\n" + URLS_BLOCK_ADD),
])

# --- base.html : lien "Regles de saisie" apres "Saisie comptable" ---
NAV_TOP_ANCHOR = ('<li><a href="{% url \'accounting:saisie_comptable_workflow\' %}" class="{% if request.path == '
                  '\'/comptabilite/saisie-workflow/\' %}bg-slate-900 text-white{% endif %}">Saisie comptable</a></li>')
# chemin litteral (le namespace 'accounting' du sous-domaine compta n'a pas cette route -> NoReverseMatch sur /accueil/)
NAV_TOP_ADD = ('<li><a href="/comptabilite/regles-saisie/" class="{% if '
               '\'/comptabilite/regles-saisie\' in request.path %}bg-slate-900 text-white{% endif %}">Regles de saisie</a></li>')

SIDE_ANCHOR = ('<li><a href="{% url \'accounting:saisie_comptable_workflow\' %}" class="rounded-2xl {% if request.path == '
               '\'/comptabilite/saisie-workflow/\' %}bg-cyan-500 text-slate-950{% endif %}">'
               '<i class="fas fa-keyboard w-5"></i>Saisie comptable</a></li>')
SIDE_ADD = ('<li><a href="/comptabilite/regles-saisie/" class="rounded-2xl {% if '
            '\'/comptabilite/regles-saisie\' in request.path %}bg-cyan-500 text-slate-950{% endif %}">'
            '<i class="fas fa-sliders w-5"></i>Regles de saisie</a></li>')

patch("templates/accounting/base.html", [
    ("navbar large",
     lambda s: "/comptabilite/regles-saisie' in request.path %}bg-slate-900" in s,
     lambda s: s.replace(NAV_TOP_ANCHOR, NAV_TOP_ANCHOR + "\n                            " + NAV_TOP_ADD, 1)),
    ("sidebars",
     lambda s: "/comptabilite/regles-saisie' in request.path %}bg-cyan-500" in s,
     lambda s: s.replace(SIDE_ANCHOR, SIDE_ANCHOR + "\n                        " + SIDE_ADD)),
])

print("\nTermine. Verifier : python manage.py check")
