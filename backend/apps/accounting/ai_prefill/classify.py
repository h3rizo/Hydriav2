"""
Phase 3 - classification par vote pondere des ecritures historiques voisines.

A partir des k voisins retournes par l'index de similarite, on predit chaque champ
(journal_code, compte_code, fournisseur, sens) par vote pondere par la similarite,
avec un score de confiance par champ.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Optional


@dataclass
class FieldPrediction:
    value: Optional[str] = None
    confidence: float = 0.0     # 0..1
    support: float = 0.0        # poids cumule du gagnant
    total: float = 0.0          # poids cumule total (voisins ayant une valeur)
    n_votants: int = 0          # nb de voisins ayant vote


@dataclass
class RowPrediction:
    journal: FieldPrediction
    compte: FieldPrediction
    fournisseur: FieldPrediction
    sens: FieldPrediction
    top_similarite: float = 0.0
    n_voisins: int = 0


def _vote(pairs: Iterable[tuple], allowed: Optional[set], top_sim: float) -> FieldPrediction:
    """pairs = [(valeur, poids), ...] ; valeurs vides ignorees."""
    weights = defaultdict(float)
    n = 0
    for val, w in pairs:
        if val in (None, "", "None"):
            continue
        if allowed is not None and val not in allowed:
            continue
        weights[val] += w
        n += 1
    if not weights:
        return FieldPrediction()
    total = sum(weights.values())
    val, sup = max(weights.items(), key=lambda kv: kv[1])
    conf = sup / total if total else 0.0
    # penalise si le meilleur voisin est lexicalement lointain, ou peu de votants
    conf *= min(1.0, top_sim / 0.35)
    if n == 1:
        conf *= 0.6
    return FieldPrediction(value=val, confidence=round(min(conf, 1.0), 3),
                           support=round(sup, 3), total=round(total, 3), n_votants=n)


def predict_row(
    neighbours: list[tuple],
    *,
    allowed_journaux: Optional[set] = None,
    allowed_comptes: Optional[set] = None,
    allowed_fournisseurs: Optional[set] = None,
) -> RowPrediction:
    """
    neighbours = liste [(doc_id, similarite, meta), ...] triee par similarite desc.
    meta doit contenir journal_code / compte_code / fournisseur / sens.
    """
    if not neighbours:
        empty = FieldPrediction()
        return RowPrediction(empty, empty, empty, empty, 0.0, 0)

    top_sim = neighbours[0][1]
    w = [(m, s) for (_id, s, m) in neighbours]

    return RowPrediction(
        journal=_vote(((m.get("journal_code"), s) for m, s in w), allowed_journaux, top_sim),
        compte=_vote(((m.get("compte_code"), s) for m, s in w), allowed_comptes, top_sim),
        fournisseur=_vote(((m.get("fournisseur"), s) for m, s in w), allowed_fournisseurs, top_sim),
        sens=_vote(((m.get("sens"), s) for m, s in w), {"in", "out"}, top_sim),
        top_similarite=round(top_sim, 4),
        n_voisins=len(neighbours),
    )
