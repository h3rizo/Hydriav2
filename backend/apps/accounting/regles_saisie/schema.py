"""Schema et validation de `RegleSaisieCompte.config`."""
from __future__ import annotations

# --- types de champ du formulaire guide -----------------------------------
TYPES_CHAMP = {
    "fournisseur_ac",   # autocomplete Fournisseur (filtre par CompteFournisseurAutorise)
    "ouvrage_ac",       # autocomplete Ouvrage
    "employe_ac",       # autocomplete Employe (filtre par Poste.compte_* si 631/641/646)
    "vehicule_ac",      # autocomplete Vehicule
    "abonne_ac",        # autocomplete abonne / point d'eau (recettes)
    "texte",
    "nombre",
    "select",           # options: [{"val": "...", "marker": "SAL..."}]
    "prestation",       # case a cocher ; fixe=True/False pour forcer
    "mois_annee",       # -> "YYYY MM" (mois en numero)
    "date_jour1",       # <input month> -> "01/MM/YYYY" (recettes datees au 1er du mois)
    "annee",            # -> "YYYY"
    "fixe",             # valeur constante (rare)
}

# --- colonnes de sortie qu'un champ peut alimenter -----------------------
# "sens" : permet a un champ (typiquement un "select" Avance/Remboursement) de
# surcharger le sens par defaut de la regle (ex: compte 00PERS, utilise a la
# fois en avance (out) et en remboursement (in) - cf. options[].val = "in"/"out").
SORTIES = {"fournisseur", "detail", "activ", "fin", "sens", None}

# --- segments du gabarit `description` ----------------------------------
AUTOS = {
    "nif_fournisseur",     # NIF | NIF PREST | ISI | ISI PREST
    "prefixe_nom_employe", # "{Poste.prefixe} {Employe.nom_complet}"
    "ouvrage_nom",
    "vehicule_immat",
    "abonne_nom",
    "marker_nature",       # le marker de l'option select choisie (ex: SALNET)
}


def valider_config(config: dict) -> list[str]:
    """Retourne la liste des erreurs de structure (vide si OK)."""
    err: list[str] = []
    if not isinstance(config, dict):
        return ["config doit etre un objet"]

    champs = config.get("champs", [])
    if not isinstance(champs, list):
        err.append("champs doit etre une liste")
        champs = []
    codes = set()
    for i, ch in enumerate(champs):
        if not isinstance(ch, dict):
            err.append(f"champs[{i}] doit etre un objet")
            continue
        code = ch.get("code")
        if not code:
            err.append(f"champs[{i}].code manquant")
        elif code in codes:
            err.append(f"champs[{i}].code '{code}' en double")
        else:
            codes.add(code)
        t = ch.get("type")
        if t not in TYPES_CHAMP:
            err.append(f"champs[{i}].type '{t}' inconnu")
        if ch.get("sortie") not in SORTIES:
            err.append(f"champs[{i}].sortie '{ch.get('sortie')}' invalide")
        if t == "select":
            opts = ch.get("options")
            if not isinstance(opts, list) or not opts:
                err.append(f"champs[{i}] (select) : options requis")

    segs = config.get("description", [])
    if not isinstance(segs, list):
        err.append("description doit etre une liste de segments")
        segs = []
    for i, s in enumerate(segs):
        if not isinstance(s, dict):
            err.append(f"description[{i}] doit etre un objet")
            continue
        keys = {"lit", "champ", "auto"} & set(s)
        if len(keys) != 1:
            err.append(f"description[{i}] doit avoir exactement un de lit/champ/auto")
            continue
        if "champ" in s and s["champ"] not in codes:
            err.append(f"description[{i}].champ '{s['champ']}' n'est pas un code de champ")
        if "auto" in s and s["auto"] not in AUTOS:
            err.append(f"description[{i}].auto '{s['auto']}' inconnu")
    return err
