"""Resolution de regle + composition d'ecriture."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from apps.accounting.models_regles_saisie import RegleSaisieCompte


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #

def resoudre_regle(organisation_id, compte_code: str) -> Optional[RegleSaisieCompte]:
    """Regle applicable : correspondance exacte, sinon prefixe le plus long."""
    compte_code = (compte_code or "").strip()
    if not organisation_id or not compte_code:
        return None
    qs = list(RegleSaisieCompte.objects.filter(organisation_id=organisation_id, actif=True))
    exact = next((r for r in qs if not r.est_prefixe and r.compte_cible == compte_code), None)
    if exact:
        return exact
    prefixes = [r for r in qs if r.est_prefixe and compte_code.startswith(r.compte_cible)]
    prefixes.sort(key=lambda r: -len(r.compte_cible))
    return prefixes[0] if prefixes else None


# --------------------------------------------------------------------------- #
# Composition
# --------------------------------------------------------------------------- #

@dataclass
class EcritureComposee:
    description: str = ""
    fournisseur: str = ""     # colonne Fournisseur (idxls ou marqueur SAL...)
    detail: str = ""          # colonne Detail (surnom employe / immatriculation)
    activ: str = ""
    fin: str = ""
    sens: str = ""            # 'in' | 'out'
    warnings: list = field(default_factory=list)
    apercu: dict = field(default_factory=dict)   # {champ_code: libelle lisible} pour l'UI

    def as_dict(self):
        return {
            "description": self.description,
            "fournisseur": self.fournisseur,
            "detail": self.detail,
            "activ": self.activ,
            "fin": self.fin,
            "sens": self.sens,
            "warnings": self.warnings,
            "apercu": self.apercu,
        }


# resolver(kind, pk) -> objet ; kind in {fournisseur, ouvrage, employe, vehicule, abonne}
Resolver = Callable[[str, object], object]


def _default_resolver(kind: str, pk):
    if pk in (None, "", "None"):
        return None
    if kind == "fournisseur":
        from apps.billing.models import Fournisseur
        return Fournisseur.objects.filter(pk=pk).first()
    if kind == "ouvrage":
        from apps.organization.models import Ouvrage
        return Ouvrage.objects.filter(pk=pk).first()
    if kind == "employe":
        from apps.employees.models import Employe
        return Employe.objects.select_related("poste").filter(pk=pk).first()
    if kind == "vehicule":
        from apps.inventory.models_vehicles import Vehicule
        return Vehicule.objects.filter(pk=pk).first()
    if kind == "abonne":
        return None  # gere au cas par cas (Phase D)
    return None


_AC_KIND = {
    "fournisseur_ac": "fournisseur",
    "ouvrage_ac": "ouvrage",
    "employe_ac": "employe",
    "vehicule_ac": "vehicule",
    "abonne_ac": "abonne",
}


def _cond(expr: Optional[str], valeurs: dict) -> bool:
    if not expr:
        return True
    expr = expr.strip()
    neg = expr.startswith("!")
    if neg:
        expr = expr[1:].strip()
    if "==" in expr:
        k, v = (p.strip() for p in expr.split("==", 1))
        res = str(valeurs.get(k, "")) == v
    elif "!=" in expr:
        k, v = (p.strip() for p in expr.split("!=", 1))
        res = str(valeurs.get(k, "")) != v
    else:
        res = bool(valeurs.get(expr))
    return (not res) if neg else res


def _fmt_nombre(v) -> str:
    s = str(v or "").strip().replace(" ", "")
    if s.endswith(".0"):
        s = s[:-2]
    return s


def _nif_prefixe(fournisseur, prestation: bool) -> str:
    if fournisseur is None:
        return ""
    has_nif = bool((getattr(fournisseur, "numero_nif", "") or "").strip()) or \
        (getattr(fournisseur, "nif_ou_isi", "") == "NIF")
    base = "NIF" if has_nif else "ISI"
    return f"{base} PREST" if prestation else base


def composer_ecriture(regle: RegleSaisieCompte, valeurs: dict, *,
                      resolver: Optional[Resolver] = None) -> EcritureComposee:
    resolver = resolver or _default_resolver
    config = regle.config or {}
    champs = {c["code"]: c for c in config.get("champs", []) if c.get("code")}
    out = EcritureComposee(sens=regle.sens)

    # 1. valeurs fixes + champs obligatoires
    vals = dict(valeurs or {})
    for code, ch in champs.items():
        if ch.get("fixe") is not None:
            vals[code] = ch["fixe"]
    for code, ch in champs.items():
        if ch.get("obligatoire") and _cond(ch.get("visible_si"), vals):
            if vals.get(code) in (None, "", []):
                out.warnings.append(f"Champ requis manquant : {ch.get('label') or code}")

    # 2. resolution des objets d'autocompletion
    objets: dict = {}
    for code, ch in champs.items():
        kind = _AC_KIND.get(ch.get("type"))
        if kind and vals.get(code) not in (None, "", "None"):
            obj = resolver(kind, vals[code])
            objets[code] = obj
            if obj is None:
                out.warnings.append(f"{ch.get('label') or code} : introuvable ({vals[code]})")

    prestation = bool(vals.get("prestation"))

    # 3. colonnes de sortie alimentees par un champ
    for code, ch in champs.items():
        sortie = ch.get("sortie")
        if not sortie:
            continue
        kind = _AC_KIND.get(ch.get("type"))
        obj = objets.get(code)
        if kind == "fournisseur" and obj is not None:
            valeur = str(getattr(obj, "idxls", "") or "")
        elif kind == "employe" and obj is not None:
            valeur = (getattr(obj, "surnom", "") or getattr(obj, "nom", "") or "").strip()
        elif kind == "vehicule" and obj is not None:
            valeur = (getattr(obj, "immatriculation", "") or "").strip()
        else:
            valeur = str(vals.get(code, "") or "")
        if sortie == "sens" and not valeur:
            continue  # rien choisi -> garder le sens par defaut de la regle
        setattr(out, sortie, valeur)

    # 4. marqueur porte par l'option select choisie (ex: SALNET) -> colonne Fournisseur
    for code, ch in champs.items():
        if ch.get("type") != "select":
            continue
        choisi = str(vals.get(code, ""))
        opt = next((o for o in ch.get("options", []) if o.get("val") == choisi), None)
        if opt and opt.get("marker"):
            out.fournisseur = opt["marker"]
    # marqueur fixe de la regle (ex: 631 -> SALIRSA), si rien d'autre ne l'a rempli
    if not out.fournisseur and config.get("fournisseur_fixe"):
        out.fournisseur = config["fournisseur_fixe"]

    # 5. valeur d'affichage d'un champ dans la description
    def _disp(code: str) -> str:
        ch = champs.get(code, {})
        kind = _AC_KIND.get(ch.get("type"))
        obj = objets.get(code)
        if kind == "fournisseur" and obj is not None:
            return (getattr(obj, "nom_fournisseur", "") or "").strip()
        if kind == "ouvrage" and obj is not None:
            return (getattr(obj, "nom_ouvrage", "") or "").strip()
        if kind == "employe" and obj is not None:
            return (getattr(obj, "nom_complet", "") or "").strip()
        if kind == "vehicule" and obj is not None:
            return (getattr(obj, "immatriculation", "") or "").strip()
        if ch.get("type") == "nombre":
            return _fmt_nombre(vals.get(code))
        if ch.get("type") == "date_jour1":
            m = re.match(r"\s*(\d{4})\D+(\d{1,2})", str(vals.get(code, "")))
            return f"01/{int(m.group(2)):02d}/{m.group(1)}" if m else ""
        return str(vals.get(code, "") or "").strip()

    def _auto(name: str) -> str:
        if name == "nif_fournisseur":
            fcode = next((c for c, ch in champs.items() if ch.get("type") == "fournisseur_ac"), None)
            return _nif_prefixe(objets.get(fcode), prestation)
        if name == "prefixe_nom_employe":
            ecode = next((c for c, ch in champs.items() if ch.get("type") == "employe_ac"), None)
            e = objets.get(ecode)
            if e is None:
                return ""
            pref = ""
            if getattr(e, "poste_id", None):
                pref = (getattr(e.poste, "prefixe", "") or "").strip()
            return f"{pref} {(getattr(e, 'nom_complet', '') or '').strip()}".strip()
        if name == "marker_nature":
            return out.fournisseur
        return ""

    # 6. assemblage : un separateur en attente (_ ou espace) n'est ecrit que si
    #    la valeur qui suit est non vide -> pas de "__" ni de "_" en trop.
    parts: list[str] = []
    pending_sep = ""
    for seg in config.get("description", []):
        if not _cond(seg.get("si"), vals):
            continue
        if "lit" in seg:
            lit = str(seg["lit"])
            if lit and set(lit) <= {"_", " "}:
                pending_sep = lit
            else:
                parts.append(pending_sep + lit)
                pending_sep = ""
            continue
        val = _disp(seg["champ"]) if "champ" in seg else _auto(seg.get("auto", ""))
        if val:
            parts.append((pending_sep if parts else "") + val)
        pending_sep = ""
    out.description = "".join(parts).strip("_ ").strip()

    # 7. apercu pour l'UI
    for code, ch in champs.items():
        if _AC_KIND.get(ch.get("type")):
            out.apercu[code] = _disp(code)

    return out
