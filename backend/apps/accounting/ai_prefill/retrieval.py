"""
Phase 3 - recuperation par similarite lexicale (sans API, sans dependance lourde).

Index trigramme de caracteres + index inverse. Chaque document = le libelle d'une
ecriture `BaseDiameX` historique ; ses labels (journal/compte/fournisseur/sens...)
sont stockes avec lui pour que la classification se fasse entierement en memoire.

Choix v1 : trigrammes de caracteres -> robuste au francais/malgache, aux fautes,
et aux libelles semi-structures (`Paiement forfaitaire_U_1_5000_Ambanja BP`).
Les embeddings (Voyage/OpenAI + pgvector) seront un backend alternatif branchable.
"""
from __future__ import annotations

import pickle
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional

_WS = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    t = unicodedata.normalize("NFKD", str(value or ""))
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower()
    t = "".join(c if (c.isalnum() or c.isspace()) else " " for c in t)
    return _WS.sub(" ", t).strip()


def trigrams(value: str) -> set[str]:
    t = f"  {normalize_text(value)}  "
    if len(t) < 3:
        return set()
    return {t[i:i + 3] for i in range(len(t) - 2)}


@dataclass
class TrigramIndex:
    doc_ids: list = field(default_factory=list)          # id externe (BaseDiameX.pk)
    doc_len: list = field(default_factory=list)          # nb de trigrammes du doc (denominateur cosinus)
    doc_meta: list = field(default_factory=list)         # labels + contexte
    postings: dict = field(default_factory=lambda: defaultdict(list))  # trigramme -> [idx internes]
    _id_to_idx: dict = field(default_factory=dict)

    # ------------------------------------------------------------------ #

    def add(self, doc_id: Any, text: str, meta: Optional[dict] = None) -> None:
        idx = len(self.doc_ids)
        tg = trigrams(text)
        self.doc_ids.append(doc_id)
        self.doc_len.append(len(tg) or 1)
        self.doc_meta.append(meta or {})
        self._id_to_idx[doc_id] = idx
        for g in tg:
            self.postings[g].append(idx)

    def prune_common(self, max_df_ratio: float = 0.4) -> int:
        """Retire les trigrammes trop frequents (bruit + postings lourds)."""
        n = len(self.doc_ids)
        if n == 0:
            return 0
        cutoff = max(50, int(max_df_ratio * n))
        drop = [g for g, lst in self.postings.items() if len(lst) > cutoff]
        for g in drop:
            del self.postings[g]
        return len(drop)

    def finalize(self) -> None:
        self.postings = dict(self.postings)
        if not self._id_to_idx:
            self._id_to_idx = {d: i for i, d in enumerate(self.doc_ids)}

    # ------------------------------------------------------------------ #

    def query(self, text: str, k: int = 10, exclude_id: Any = None) -> list[tuple]:
        """Retourne [(doc_id, score_cosinus, meta), ...] trie par score decroissant."""
        qg = trigrams(text)
        if not qg:
            return []
        inter = Counter()
        for g in qg:
            lst = self.postings.get(g)
            if lst:
                for ix in lst:
                    inter[ix] += 1
        if not inter:
            return []
        qn = len(qg) ** 0.5
        scored = []
        for ix, c in inter.items():
            did = self.doc_ids[ix]
            if exclude_id is not None and did == exclude_id:
                continue
            cos = c / (qn * (self.doc_len[ix] ** 0.5))
            scored.append((did, cos, self.doc_meta[ix]))
        scored.sort(key=lambda x: -x[1])
        return scored[:k]

    def base_label_sets(self):
        """Pour chaque base_id, l'ensemble des journal_code / compte_code / fournisseur vus."""
        by_base = defaultdict(lambda: {"journal": set(), "compte": set(), "fournisseur": set()})
        for m in self.doc_meta:
            b = m.get("base_id") or "?"
            if m.get("journal_code"):
                by_base[b]["journal"].add(m["journal_code"])
            if m.get("compte_code"):
                by_base[b]["compte"].add(m["compte_code"])
            if m.get("fournisseur"):
                by_base[b]["fournisseur"].add(m["fournisseur"])
        return by_base

    # ------------------------------------------------------------------ #

    def save(self, path: str) -> None:
        self.finalize()
        with open(path, "wb") as fh:
            pickle.dump(
                {
                    "doc_ids": self.doc_ids,
                    "doc_len": self.doc_len,
                    "doc_meta": self.doc_meta,
                    "postings": self.postings,
                },
                fh,
                protocol=pickle.HIGHEST_PROTOCOL,
            )

    @classmethod
    def load(cls, path: str) -> "TrigramIndex":
        with open(path, "rb") as fh:
            d = pickle.load(fh)
        obj = cls(
            doc_ids=d["doc_ids"],
            doc_len=d["doc_len"],
            doc_meta=d["doc_meta"],
            postings=d["postings"],
        )
        obj._id_to_idx = {did: i for i, did in enumerate(obj.doc_ids)}
        return obj

    def __len__(self) -> int:
        return len(self.doc_ids)


def build_corpus_text(description: str, info: str = "") -> str:
    parts = [p for p in (str(description or "").strip(), str(info or "").strip()) if p]
    return " ".join(parts)
