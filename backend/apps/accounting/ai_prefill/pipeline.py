"""
Phase 4 - orchestration : scan (ou texte) -> suggestions de pre-remplissage.

    suggest_from_text(texte, base_id=...)  -> Suggestion      (aucun appel API)
    suggest_from_scan(fichier, base_id=...) -> Suggestion     (extraction Claude + retrieval)

Fusion :
  - journal / compte / fournisseur  <- vote des ecritures historiques voisines
  - sens / montant / date           <- extraction du justificatif (chemin scan)
  - garde `auto` : True si confiance >= seuil (pre-remplir sans marque de doute)

L'index trigramme est charge une fois par worker et recharge si le .pkl change.
"""
from __future__ import annotations

import os
import threading
from dataclasses import asdict, dataclass, field
from typing import Optional

from django.conf import settings

from .classify import predict_row
from .retrieval import TrigramIndex, build_corpus_text

_INDEX = None
_INDEX_MTIME = None
_LOCK = threading.Lock()

_SEUIL_DEFAUT = 0.9


class IndexNotBuilt(Exception):
    """L'index n'existe pas encore : lancer `python manage.py build_prefill_index`."""


def index_path() -> str:
    p = getattr(settings, "AI_PREFILL_INDEX_PATH", "") or ""
    return p or os.path.join(settings.BASE_DIR, "exports", "ai_prefill", "trgm_index.pkl")


def get_index(force_reload: bool = False) -> TrigramIndex:
    global _INDEX, _INDEX_MTIME
    path = index_path()
    if not os.path.exists(path):
        raise IndexNotBuilt(path)
    mtime = os.path.getmtime(path)
    with _LOCK:
        if force_reload or _INDEX is None or mtime != _INDEX_MTIME:
            _INDEX = TrigramIndex.load(path)
            _INDEX_MTIME = mtime
    return _INDEX


def _seuil() -> float:
    return float(getattr(settings, "AI_PREFILL_CONFIANCE_SEUIL", _SEUIL_DEFAUT) or _SEUIL_DEFAUT)


# --------------------------------------------------------------------------- #

@dataclass
class FieldSuggestion:
    field: str
    value: Optional[str] = None
    label: str = ""
    confidence: float = 0.0
    source: str = ""          # retrieval | extraction | derived
    auto: bool = False        # confidence >= seuil

    def as_dict(self):
        return asdict(self)


@dataclass
class Suggestion:
    fields: dict = field(default_factory=dict)       # nom_champ -> FieldSuggestion
    neighbours: list = field(default_factory=list)   # top 3 voisins (transparence)
    extraction: Optional[dict] = None               # ReceiptExtraction.model_dump() si scan
    query_text: str = ""
    index_size: int = 0
    seuil: float = _SEUIL_DEFAUT
    warnings: list = field(default_factory=list)
    status: str = "ok"                              # ok | extraction_error | index_absent

    def as_dict(self):
        return {
            "status": self.status,
            "seuil_confiance": self.seuil,
            "index_size": self.index_size,
            "query_text": self.query_text[:2000],
            "fields": {k: v.as_dict() for k, v in self.fields.items()},
            "neighbours": self.neighbours,
            "extraction": self.extraction,
            "warnings": self.warnings,
        }


# --------------------------------------------------------------------------- #
# resolution des libelles (referentiel)
# --------------------------------------------------------------------------- #

def _label_journal(code, base_id):
    if not code:
        return ""
    from apps.organization.models import Journal
    qs = Journal.objects.filter(code=code)
    if base_id:
        j = qs.filter(base_id=base_id).first() or qs.first()
    else:
        j = qs.first()
    return j.nom_journal if j else ""


def _label_compte(code, base_id):
    if not code:
        return ""
    from apps.organization.models import Base, Compte
    qs = Compte.objects.filter(compte=code)
    if base_id:
        org_id = Base.objects.filter(id=base_id).values_list("organisation_id", flat=True).first()
        if org_id:
            qs = Compte.objects.filter(compte=code, organisation_id=org_id) or qs
    c = qs.first()
    return c.nom_compte if c else ""


def _label_fournisseur(val):
    if not val:
        return ""
    from apps.billing.models import Fournisseur
    if str(val).isdigit():
        f = Fournisseur.objects.filter(idxls=int(val)).only("nom_fournisseur").first()
        return f.nom_fournisseur if f else ""
    return str(val)


def _norm_name(v):
    c = "".join(ch.lower() if ch.isalnum() else " " for ch in str(v or "").strip())
    return " ".join(c.split())


def resolve_fournisseur_by_name(nom_brut: str):
    """Nom lu sur la piece -> (idxls, nom, confiance) via la table Fournisseur.
    Exact normalise, sinon meilleur match flou >= 0.85. None si rien de fiable."""
    from difflib import SequenceMatcher

    from apps.billing.models import Fournisseur

    q = _norm_name(nom_brut)
    if len(q) < 4:
        return None
    rows = [
        (f.idxls, f.nom_fournisseur, _norm_name(f.nom_fournisseur))
        for f in Fournisseur.objects.filter(actif=True, idxls__isnull=False).only("idxls", "nom_fournisseur")
    ]
    for idxls, nom, n in rows:
        if n == q:
            return (str(idxls), nom, 0.95)
    best = None
    for idxls, nom, n in rows:
        if not n or abs(len(n) - len(q)) > max(4, 0.4 * len(q)):
            continue
        qtok, ntok = set(q.split()), set(n.split())
        if qtok and (qtok <= ntok or ntok <= qtok):
            score = 0.9
        else:
            score = SequenceMatcher(None, q, n).ratio()
        if score >= 0.85 and (best is None or score > best[2]):
            best = (str(idxls), nom, round(score, 2))
    return best


# --------------------------------------------------------------------------- #

def suggest_from_text(texte: str, *, base_id: Optional[str] = None, k: int = 12,
                      seuil: Optional[float] = None) -> Suggestion:
    seuil = _seuil() if seuil is None else seuil
    try:
        idx = get_index()
    except IndexNotBuilt as exc:
        return Suggestion(status="index_absent", query_text=texte, seuil=seuil,
                          warnings=[f"Index non construit : {exc}"])

    neigh = idx.query(texte, k=k)
    allowed_j = allowed_c = allowed_f = None
    if base_id:
        sets = idx.base_label_sets().get(str(base_id))
        if sets:
            allowed_j, allowed_c, allowed_f = sets["journal"], sets["compte"], sets["fournisseur"]

    pred = predict_row(neigh, allowed_journaux=allowed_j,
                       allowed_comptes=allowed_c, allowed_fournisseurs=allowed_f)

    def fs(name, fp, source, label):
        return FieldSuggestion(field=name, value=fp.value, label=label,
                               confidence=fp.confidence, source=source,
                               auto=bool(fp.value and fp.confidence >= seuil))

    fields = {
        "journal_code": fs("journal_code", pred.journal, "retrieval",
                           _label_journal(pred.journal.value, base_id)),
        "compte_code": fs("compte_code", pred.compte, "retrieval",
                          _label_compte(pred.compte.value, base_id)),
        "fournisseur": fs("fournisseur", pred.fournisseur, "retrieval",
                          _label_fournisseur(pred.fournisseur.value)),
        "sens": fs("sens", pred.sens, "retrieval", ""),
    }

    neighbours = [
        {
            "id": did,
            "similarite": round(sim, 4),
            "description": (m.get("text") or "")[:200],
            "journal_code": m.get("journal_code"),
            "compte_code": m.get("compte_code"),
            "fournisseur": m.get("fournisseur"),
            "fournisseur_name": m.get("fournisseur_name"),
            "fichier_source": m.get("fichier_source"),
            "date_m": m.get("date_m"),
        }
        for did, sim, m in neigh[:3]
    ]

    return Suggestion(fields=fields, neighbours=neighbours, query_text=texte,
                      index_size=len(idx), seuil=seuil)


def suggest_from_scan(file_bytes: bytes, filename: str = "", *,
                      base_id: Optional[str] = None, seuil: Optional[float] = None) -> Suggestion:
    from .services import ApiAccountError, BudgetExceeded, extract_receipt

    seuil = _seuil() if seuil is None else seuil
    try:
        outcome = extract_receipt(file_bytes, filename=filename)
    except (BudgetExceeded, ApiAccountError) as exc:
        return Suggestion(status="extraction_error", seuil=seuil,
                          warnings=[f"Extraction indisponible : {exc}"])
    except Exception as exc:  # noqa: BLE001
        return Suggestion(status="extraction_error", seuil=seuil,
                          warnings=[f"Extraction en echec : {exc}"])

    ex = outcome.extraction
    if outcome.status != "ok" or ex is None:
        return Suggestion(status="extraction_error", seuil=seuil,
                          warnings=[f"Extraction : {outcome.status} {outcome.erreur}".strip()])

    query = build_corpus_text(ex.texte_integral, ex.fournisseur_nom_brut or "")
    sugg = suggest_from_text(query, base_id=base_id, seuil=seuil)
    sugg.extraction = ex.model_dump()

    # champs qui viennent du justificatif, pas du retrieval
    sens_map = {"depense": "out", "recette": "in"}
    sens_val = sens_map.get(ex.sens_probable or "")
    if sens_val:
        sugg.fields["sens"] = FieldSuggestion(
            field="sens", value=sens_val, source="extraction",
            confidence=ex.confiance_sens,
            auto=bool(sens_val and ex.confiance_sens >= seuil),
        )
    sugg.fields["montant"] = FieldSuggestion(
        field="montant", value=(str(ex.montant_total) if ex.montant_total is not None else None),
        label=(ex.devise or "MGA"), source="extraction", confidence=ex.confiance_montant,
        auto=bool(ex.montant_total is not None and ex.confiance_montant >= seuil),
    )
    sugg.fields["date_piece"] = FieldSuggestion(
        field="date_piece", value=ex.date_piece, source="extraction",
        confidence=ex.confiance_date,
        auto=bool(ex.date_piece and ex.confiance_date >= seuil),
    )
    # fournisseur : d'abord resolution par le nom lu sur la piece, sinon on garde
    # le vote des voisins (deja dans sugg.fields["fournisseur"])
    if ex.fournisseur_nom_brut:
        match = resolve_fournisseur_by_name(ex.fournisseur_nom_brut)
        if match:
            idxls, nom, sc = match
            sugg.fields["fournisseur"] = FieldSuggestion(
                field="fournisseur", value=idxls, label=nom, source="extraction",
                confidence=sc, auto=bool(sc >= seuil),
            )
        else:
            sugg.warnings.append(
                f"Fournisseur lu sur la piece : {ex.fournisseur_nom_brut!r} - "
                f"aucun rattachement fiable dans la table Fournisseur"
            )
    if ex.lisibilite != "bonne":
        sugg.warnings.append(f"Lisibilite {ex.lisibilite}" + (" - manuscrit" if ex.manuscrit else ""))

    return sugg
