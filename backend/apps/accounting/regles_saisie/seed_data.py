"""
Regles de saisie par compte (spec utilisateur 2026-09-10).

`REGLES` : liste de dicts {compte_cible, est_prefixe, mode, sens, libelle, config}.
La commande `seed_regles_saisie` cree une RegleSaisieCompte par (organisation, compte).
"""
from __future__ import annotations

import copy

UNITES = ["U", "Kg", "L", "m", "m2", "m3", "Sac", "Lot", "Mois", "Jour", "Forfait"]


# --------------------------------------------------------------------------- #
# Fabriques
# --------------------------------------------------------------------------- #

def _champ_fournisseur():
    return {"code": "fournisseur", "type": "fournisseur_ac", "label": "Fournisseur",
            "obligatoire": True, "sortie": "fournisseur"}


def _champ_prestation(mode: str):
    # mode : "choix" | "toujours" | "jamais"
    if mode == "toujours":
        return {"code": "prestation", "type": "prestation", "label": "Prestation", "fixe": True}
    if mode == "jamais":
        return None
    return {"code": "prestation", "type": "prestation", "label": "Prestation de service"}


def _champ_libelle(fixe=None):
    return {"code": "libelle", "type": "texte" if fixe is None else "fixe",
            "label": "Libelle", "obligatoire": True, "fixe": fixe}


def _champ_unite(fixe=None):
    return {"code": "unite", "type": "select" if fixe is None else "fixe", "label": "Unite",
            "obligatoire": True, "fixe": fixe,
            "options": None if fixe is not None else [{"val": u} for u in UNITES]}


def _champ_pu():
    return {"code": "pu", "type": "nombre", "label": "Prix unitaire", "obligatoire": True}


def _champ_cible(options):
    return {"code": "cible", "type": "select", "label": "Depense pour",
            "obligatoire": True, "options": [{"val": o} for o in options]}


def _champ_ouvrage():
    return {"code": "ouvrage", "type": "ouvrage_ac", "label": "Ouvrage",
            "visible_si": "cible==ouvrage"}


def _champ_vehicule(voiture_seulement=False):
    ch = {"code": "vehicule", "type": "vehicule_ac", "label": "Vehicule (immatriculation)",
          "visible_si": "cible==vehicule", "sortie": "detail"}
    if voiture_seulement:
        ch["filtre"] = "voiture"
    return ch


def _champ_employe_cible():
    return {"code": "employe", "type": "employe_ac", "label": "Employe",
            "visible_si": "cible==employe", "sortie": "detail"}


def _champ_magasin():
    return {"code": "magasin", "type": "texte", "label": "Magasin / depot",
            "visible_si": "cible==magasin"}


def _champ_reste(label="Reste du libelle", obligatoire=False):
    return {"code": "reste", "type": "texte", "label": label, "obligatoire": obligatoire}


def _desc_fournisseur(avec_cible=None, reste=True, extra_tail=None):
    """Gabarit standard : [NIF|NIF PREST|ISI|ISI PREST]_Nom_Libelle_Unite_PU_[cible_]reste
    (le PREST est porte par le 1er segment via l'auto nif_fournisseur)."""
    segs = [
        {"auto": "nif_fournisseur"}, {"lit": "_"}, {"champ": "fournisseur"}, {"lit": "_"},
        {"champ": "libelle"}, {"lit": "_"}, {"champ": "unite"}, {"lit": "_"}, {"champ": "pu"},
    ]
    if avec_cible == "ouvrage":
        segs += [{"lit": "_"}, {"champ": "ouvrage", "si": "cible==ouvrage"}]
    if avec_cible == "employe":
        segs += [{"lit": "_"}, {"champ": "employe", "si": "cible==employe"}]
    if reste:
        segs += [{"lit": "_"}, {"champ": "reste"}]
    if extra_tail:
        segs += extra_tail
    return segs


def regle_fournisseur(comptes, *, est_prefixe=False, libelle="Depense fournisseur",
                      libelle_fixe=None, unite_fixe=None, prestation="choix",
                      cibles=None, reste_label="Reste du libelle", reste_obligatoire=False):
    """Fabrique une (ou plusieurs) regle(s) mode fournisseur."""
    if isinstance(comptes, str):
        comptes = [comptes]
    champs = [_champ_fournisseur()]
    p = _champ_prestation(prestation)
    if p:
        champs.append(p)
    champs.append(_champ_libelle(libelle_fixe))
    champs.append(_champ_unite(unite_fixe))
    champs.append(_champ_pu())

    avec_cible = None
    if cibles:
        champs.append(_champ_cible(cibles))
        if "ouvrage" in cibles:
            champs.append(_champ_ouvrage()); avec_cible = "ouvrage"
        if "vehicule" in cibles:
            champs.append(_champ_vehicule())
        if "employe" in cibles:
            champs.append(_champ_employe_cible()); avec_cible = avec_cible or "employe"
        if "magasin" in cibles:
            champs.append(_champ_magasin())
    champs.append(_champ_reste(reste_label, reste_obligatoire))

    config = {
        "champs": champs,
        "description": _desc_fournisseur(avec_cible=avec_cible),
    }
    return [
        {"compte_cible": c, "est_prefixe": est_prefixe, "mode": "fournisseur",
         "sens": "out", "libelle": libelle, "config": copy.deepcopy(config)}
        for c in comptes
    ]


def regle_employe(comptes, *, est_prefixe=False, libelle="Charge employe",
                  nature_fixe=None, natures=None, filtre_poste=None,
                  fournisseur_marker=None, reste_segments=None, avec_mois_annee=True):
    """
    Fabrique une regle mode employe.
    description = "{prefixe poste} {nom complet}_{nature}_{annee mois}[_reste]"
    detail = surnom ; fournisseur = marker (ou porte par la nature).
    """
    if isinstance(comptes, str):
        comptes = [comptes]
    champs = [{
        "code": "employe", "type": "employe_ac", "label": "Employe",
        "obligatoire": True, "sortie": "detail",
        **({"filtre_poste": filtre_poste} if filtre_poste else {}),
    }]
    if natures:
        champs.append({"code": "nature", "type": "select", "label": "Nature",
                       "obligatoire": True, "options": natures})
        nature_seg = {"champ": "nature"}
    else:
        champs.append({"code": "nature", "type": "fixe", "fixe": nature_fixe, "label": "Nature"})
        nature_seg = {"lit": nature_fixe}

    desc = [{"auto": "prefixe_nom_employe"}, {"lit": "_"}, nature_seg]
    if avec_mois_annee:
        champs.append({"code": "annee_mois", "type": "mois_annee", "label": "Mois concerne",
                       "obligatoire": True})
        desc += [{"lit": "_"}, {"champ": "annee_mois"}]
    if reste_segments:
        desc += reste_segments

    config = {"champs": champs, "description": desc}
    if fournisseur_marker:
        config["fournisseur_fixe"] = fournisseur_marker  # applique par le moteur si pas de marker nature

    return [
        {"compte_cible": c, "est_prefixe": est_prefixe, "mode": "employe",
         "sens": "out", "libelle": libelle, "config": copy.deepcopy(config)}
        for c in comptes
    ]


def regle_libre(comptes, *, sens="out", libelle="Ecriture libre"):
    if isinstance(comptes, str):
        comptes = [comptes]
    config = {
        "champs": [{"code": "description", "type": "texte", "label": "Description",
                    "obligatoire": True, "sortie": None}],
        "description": [{"champ": "description"}],
    }
    return [{"compte_cible": c, "est_prefixe": False, "mode": "libre",
             "sens": sens, "libelle": libelle, "config": copy.deepcopy(config)} for c in comptes]


# --------------------------------------------------------------------------- #
# Les regles
# --------------------------------------------------------------------------- #

REGLES: list[dict] = []

# --- 218 : immobilisations (fournisseur, sans reste) ---
REGLES += regle_fournisseur("218", est_prefixe=True, libelle="Acquisition immobilisation",
                            reste_label="Complement (optionnel)")

# --- 601 / 621 : materiaux, main d'oeuvre ---
REGLES += regle_fournisseur("601001", libelle="Materiaux - magasin",
                            cibles=["magasin"], reste_label="Magasin")
REGLES += regle_fournisseur(["601005", "601007", "621122", "621201"], libelle="Depense chantier",
                            reste_label="Chantier", reste_obligatoire=True)
REGLES += regle_fournisseur(["601011", "601040", "621508", "621511"],
                            libelle="Depense ouvrage gere / stock magasin",
                            cibles=["ouvrage", "magasin"])
REGLES += regle_fournisseur(["602206", "602254", "602301", "605100"],
                            libelle="Depense employe(s) / stock magasin",
                            cibles=["employe", "magasin"])
REGLES += regle_fournisseur("602221", libelle="Depense stock magasin",
                            cibles=["magasin"])
REGLES += regle_fournisseur(["602400", "615100"], libelle="Depense vehicule / stock magasin",
                            cibles=["vehicule", "magasin"])

# --- 606 : carburant (pas de prestation, libelle + unite fixes) ---
REGLES += regle_fournisseur("606100", libelle="Essence", libelle_fixe="Essence", unite_fixe="L",
                            prestation="jamais", cibles=["vehicule", "magasin"])
REGLES += regle_fournisseur("606107", libelle="Gasoil (voiture)", libelle_fixe="Gasoil", unite_fixe="L",
                            prestation="jamais", cibles=["vehicule"])
for _r in REGLES:
    if _r["compte_cible"] == "606107":
        for _c in _r["config"]["champs"]:
            if _c["code"] == "vehicule":
                _c["filtre"] = "voiture"
REGLES += regle_fournisseur("606190", libelle="Essence", libelle_fixe="Essence", unite_fixe="L",
                            prestation="jamais")

# --- 613 / 614 : loyer, autres ---
REGLES += regle_fournisseur("613100", libelle="Loyer magasin", libelle_fixe="Loyer",
                            unite_fixe="Mois", prestation="toujours", cibles=["magasin"])
REGLES += regle_fournisseur("614142", libelle="Depense magasin", cibles=["magasin"])

# --- 625202 : fournisseur + detail = surnom employe ---
_r625202 = regle_fournisseur("625202", libelle="Depense fournisseur (employe)")[0]
_r625202["config"]["champs"].append({
    "code": "employe", "type": "employe_ac", "label": "Employe concerne",
    "obligatoire": True, "sortie": "detail",
})
REGLES.append(_r625202)

# --- 626 : credits telephone / internet ---
REGLES += regle_fournisseur("626222", libelle="Credit telephone", libelle_fixe="Credit telephone",
                            prestation="jamais")
REGLES += regle_fournisseur("626320", libelle="Credit internet", libelle_fixe="Credit internet",
                            prestation="jamais")

# --- 627 : que des prestations ---
REGLES += regle_fournisseur(["627122", "627204", "627304"], libelle="Prestation de service",
                            prestation="toujours")

# --- Sans fournisseur : ecriture libre ---
REGLES += regle_libre(["614100", "625201", "625302", "635201"], libelle="Depense libre (sans fournisseur)")

# --------------------------------------------------------------------------- #
# Mode employe
# --------------------------------------------------------------------------- #

# 625 indemnites terrain : reste = "{nombre} x {pu} {annee mois}"
_reste_terrain = [
    {"lit": "_"}, {"champ": "nombre"}, {"lit": " x "}, {"champ": "pu"},
    {"lit": " "}, {"champ": "annee_mois"},
]
_r = regle_employe(["625107", "625109", "625125", "625193"], libelle="Indemnite terrain",
                   nature_fixe="Indemnite terrain", avec_mois_annee=False,
                   reste_segments=_reste_terrain)
for _rr in _r:
    _rr["config"]["champs"] += [
        {"code": "nombre", "type": "nombre", "label": "Nombre", "obligatoire": True},
        {"code": "pu", "type": "nombre", "label": "Prix unitaire", "obligatoire": True},
        {"code": "annee_mois", "type": "mois_annee", "label": "Annee mois", "obligatoire": True},
    ]
REGLES += _r

REGLES += regle_employe("625124", libelle="Indemnite de stage", nature_fixe="Indemnite de stage")
REGLES += regle_employe("625200", libelle="Frais de deplacement", nature_fixe="Frais de deplacement")

# 631 : IRSA (employes limites par Poste.compte_irsa)
REGLES += regle_employe("631", est_prefixe=True, libelle="IRSA", nature_fixe="IRSA",
                        filtre_poste="compte_irsa", fournisseur_marker="SALIRSA")

# 641 : salaires (Poste.compte_salaire) ; nature -> marqueur
REGLES += regle_employe("641", est_prefixe=True, libelle="Salaire / assimile",
                        filtre_poste="compte_salaire",
                        natures=[
                            {"val": "Salaire", "marker": "SALNET"},
                            {"val": "Allocation terrain", "marker": "SALDIV"},
                            {"val": "Indemnite compensatrice de conge", "marker": "SALDIV"},
                            {"val": "Frais medicaux", "marker": "SALMED"},
                            {"val": "Frais de scolarite", "marker": "SALECOLE"},
                            {"val": "Prime", "marker": "SALPRIME"},
                        ])

# 646 : CNaPS / FMFP / OSIEFA / AMIT (meme compte Poste.compte_cnaps_fmfp_sante)
REGLES += regle_employe("646", est_prefixe=True, libelle="Charges sociales (CNaPS/FMFP/...)",
                        filtre_poste="compte_cnaps_fmfp_sante",
                        natures=[
                            {"val": "CNaPS", "marker": "SALCNAPS"},
                            {"val": "FMFP", "marker": "SALFMFP"},
                            {"val": "OSIEFA", "marker": "SALOSIEFA"},
                            {"val": "AMIT", "marker": "SALOSIEFA"},  # pas de SALAMIT : meme marqueur qu'OSIEFA
                        ])

# --------------------------------------------------------------------------- #
# Recettes (In)
# --------------------------------------------------------------------------- #

REGLES += regle_libre("707101", sens="in", libelle="Recette libre")

# 748411 : Paiement forfaitaire_U_{nb tranches}_{tarif}_{ouvrage}
REGLES.append({
    "compte_cible": "748411", "est_prefixe": False, "mode": "recette", "sens": "in",
    "libelle": "Paiement forfaitaire",
    "config": {
        "champs": [
            {"code": "ouvrage", "type": "ouvrage_ac", "label": "Ouvrage", "obligatoire": True},
            {"code": "nb_tranches", "type": "nombre", "label": "Nombre de tranches payees", "obligatoire": True},
            {"code": "tarif", "type": "nombre", "label": "Tarif forfaitaire", "obligatoire": True},
        ],
        "description": [
            {"lit": "Paiement forfaitaire_U_"}, {"champ": "nb_tranches"}, {"lit": "_"},
            {"champ": "tarif"}, {"lit": "_"}, {"champ": "ouvrage"},
        ],
    },
})

# --- Phase D : recettes datees ---

# 707401 : "Paiement au volume {ouvrage} 01/MM/YYYY [releves]"
REGLES.append({
    "compte_cible": "707401", "est_prefixe": False, "mode": "recette", "sens": "in",
    "libelle": "Paiement au volume",
    "config": {
        "champs": [
            {"code": "ouvrage", "type": "ouvrage_ac", "label": "Ouvrage", "obligatoire": True},
            {"code": "periode", "type": "date_jour1", "label": "Mois de consommation", "obligatoire": True},
            {"code": "releves", "type": "texte",
             "label": "Releves (ex: 03/2025 9200; 04/2025 246500)"},
        ],
        "description": [
            {"lit": "Paiement au volume"}, {"lit": " "}, {"champ": "ouvrage"},
            {"lit": " "}, {"champ": "periode"}, {"lit": " "}, {"champ": "releves"},
        ],
    },
})

# 748415 : "Cartes sociales {ouvrage} 01/MM/YYYY"
REGLES.append({
    "compte_cible": "748415", "est_prefixe": False, "mode": "recette", "sens": "in",
    "libelle": "Cartes sociales",
    "config": {
        "champs": [
            {"code": "ouvrage", "type": "ouvrage_ac", "label": "Ouvrage", "obligatoire": True},
            {"code": "periode", "type": "date_jour1", "label": "Periode", "obligatoire": True},
        ],
        "description": [
            {"lit": "Cartes sociales"}, {"lit": " "}, {"champ": "ouvrage"},
            {"lit": " "}, {"champ": "periode"},
        ],
    },
})

# 748201 : "{abonne}_Paiement pour installation {BP|BF}_{IDxls}_{ouvrage}"
REGLES.append({
    "compte_cible": "748201", "est_prefixe": False, "mode": "recette", "sens": "in",
    "libelle": "Installation BP / BF",
    "config": {
        "champs": [
            {"code": "abonne", "type": "texte", "label": "Nom de l'abonne", "obligatoire": True},
            {"code": "type_bp", "type": "select", "label": "Type", "obligatoire": True,
             "options": [{"val": "BP"}, {"val": "BF"}]},
            {"code": "idxls", "type": "nombre", "label": "IDxls du point d'eau", "obligatoire": True},
            {"code": "ouvrage", "type": "ouvrage_ac", "label": "Ouvrage", "obligatoire": True},
        ],
        "description": [
            {"champ": "abonne"}, {"lit": "_Paiement pour installation "}, {"champ": "type_bp"},
            {"lit": "_"}, {"champ": "idxls"}, {"lit": "_"}, {"champ": "ouvrage"},
        ],
    },
})
