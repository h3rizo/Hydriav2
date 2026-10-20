"""
Phase C - branche le formulaire de saisie guidee :
  - 3 routes API dans apps/accounting/urls.py (pour-compte / composer / autocomplete)
  - <script saisie_guidee.js> dans templates/accounting/saisie_workflow.html

  cd /home/soakoja/hydria/backend && python patch_saisie_guidee.py
  puis : python manage.py collectstatic --noinput  (pour saisie_guidee.js)

Idempotent. Prerequis : Phase B deployee (views_regles_saisie + import dans urls.py).
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


# --- urls.py : 3 routes ajoutees en fin de fichier ---
URLS_BLOCK = """

# Phase C - saisie guidee (integration formulaire de saisie)
if views_regles_saisie is not None:
    v = views_regles_saisie
    urlpatterns += [
        path('regles-saisie/api/pour-compte/', v.api_regle_pour_compte, name='api_regle_saisie_pour_compte'),
        path('regles-saisie/api/composer/', v.api_composer_compte, name='api_regle_saisie_composer'),
        path('regles-saisie/api/autocomplete/', v.api_ac, name='api_regle_saisie_ac'),
    ]
"""

patch("apps/accounting/urls.py", [
    ("routes saisie guidee (fin de fichier)",
     lambda s: "api_regle_saisie_pour_compte" in s,
     lambda s: s.rstrip("\n") + "\n" + URLS_BLOCK),
])

# --- saisie_workflow.html : <script saisie_guidee.js> ---
SG = "<script src=\"{% static 'js/saisie_guidee.js' %}\"></script>"
PREFILL = "<script src=\"{% static 'js/prefill_saisie.js' %}\"></script>"
FALLBACK = "{% block extra_js %}\n{{ block.super }}\n"


def _add_script(s):
    if PREFILL in s:
        return s.replace(PREFILL, PREFILL + "\n" + SG, 1)
    if FALLBACK in s:
        return s.replace(FALLBACK, FALLBACK + SG + "\n", 1)
    return s


patch("templates/accounting/saisie_workflow.html", [
    ("script saisie_guidee.js",
     lambda s: "saisie_guidee.js" in s,
     _add_script),
])

print("\nTermine. Verifier :")
print("  python manage.py check")
print("  python manage.py collectstatic --noinput")
