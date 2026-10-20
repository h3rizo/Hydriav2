"""
Phase 3 - gate hors ligne : precision de la classification par similarite, en
leave-one-out sur l'historique BaseDiameX (aucun appel API).

Pour un echantillon de lignes : on cache la ligne, on recupere ses k voisins parmi
les autres, on vote chaque champ, on compare au label reel. Mesure aussi la
"precision @ confiance" = ce qu'on obtient si on ne pre-remplit qu'au-dessus d'un
seuil de confiance (le vrai KPI produit).

  python manage.py build_prefill_index
  python manage.py eval_prefill_retrieval --limit 3000 --seed 42
  python manage.py eval_prefill_retrieval --limit 3000 --restrict-base
"""
import csv
import json
import os
import random
from collections import Counter, defaultdict

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounting.ai_prefill.classify import predict_row
from apps.accounting.ai_prefill.retrieval import TrigramIndex

_SAL_MARKERS = {"salnet", "salosiefa", "salfmfp", "salcnaps", "salmed", "salxdivers"}
_CONF_SEUILS = (0.5, 0.7, 0.9)


def _norm(v):
    c = "".join(ch.lower() if ch.isalnum() else " " for ch in str(v or "").strip())
    return " ".join(c.split())


def _four_evaluable(meta):
    raw = (meta.get("fournisseur") or "").strip()
    if not raw or raw.isdigit() and not meta.get("fournisseur_name"):
        return False
    if _norm(raw) in _SAL_MARKERS:
        return False
    return True


class Command(BaseCommand):
    help = "Phase 3 gate : precision classification par similarite (leave-one-out, sans API)."

    def add_arguments(self, parser):
        parser.add_argument("--index", default=None, help="Fichier index (defaut: exports/ai_prefill/trgm_index.pkl)")
        parser.add_argument("--limit", type=int, default=3000, help="Taille de l'echantillon (0 = tout)")
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--k", type=int, default=12, help="Nombre de voisins")
        parser.add_argument("--restrict-base", action="store_true",
                            help="Contraint les predictions aux labels deja vus dans la base de la ligne")
        parser.add_argument("--out", default=None)

    def handle(self, *args, **opts):
        index_path = opts["index"] or os.path.join(settings.BASE_DIR, "exports", "ai_prefill", "trgm_index.pkl")
        if not os.path.exists(index_path):
            raise CommandError(f"Index introuvable : {index_path}\nLancer d'abord : python manage.py build_prefill_index")

        idx = TrigramIndex.load(index_path)
        self.stdout.write(f"Index : {len(idx):,} ecritures")
        out_dir = opts["out"] or os.path.join(os.path.dirname(index_path), "eval_retrieval")
        os.makedirs(out_dir, exist_ok=True)

        by_base = idx.base_label_sets() if opts["restrict_base"] else None

        # baseline : classe majoritaire par champ
        base_counts = {f: Counter() for f in ("journal_code", "compte_code", "fournisseur", "sens")}
        for m in idx.doc_meta:
            for f in base_counts:
                if m.get(f):
                    base_counts[f][m[f]] += 1
        baseline = {
            f: (c.most_common(1)[0][1] / sum(c.values())) if c else 0.0
            for f, c in base_counts.items()
        }

        # echantillon
        rnd = random.Random(opts["seed"])
        all_idx = list(range(len(idx)))
        rnd.shuffle(all_idx)
        sample = all_idx if opts["limit"] in (0, None) else all_idx[: opts["limit"]]
        self.stdout.write(f"Echantillon : {len(sample):,} lignes, k={opts['k']}, restrict_base={bool(by_base)}")

        # compteurs
        fields = ("journal", "compte", "compte3", "fournisseur", "sens")
        hit = Counter()          # bonnes predictions (parmi couvertes + evaluables)
        covered = Counter()      # predictions non nulles (evaluables)
        evaluable = Counter()    # lignes ou le label vrai est evaluable
        # precision @ confiance
        conf_hit = {f: {s: 0 for s in _CONF_SEUILS} for f in fields}
        conf_tot = {f: {s: 0 for s in _CONF_SEUILS} for f in fields}
        sim_hist = Counter()
        per_item = []

        for count, ix in enumerate(sample, 1):
            meta = idx.doc_meta[ix]
            did = idx.doc_ids[ix]
            text = meta.get("text") or ""
            neigh = idx.query(text, k=opts["k"], exclude_id=did)

            top_sim = neigh[0][1] if neigh else 0.0
            sim_hist[">=0.9" if top_sim >= 0.9 else ">=0.7" if top_sim >= 0.7
                     else ">=0.5" if top_sim >= 0.5 else ">=0.3" if top_sim >= 0.3 else "<0.3"] += 1

            allowed_j = allowed_c = allowed_f = None
            if by_base:
                b = meta.get("base_id") or "?"
                allowed_j = by_base.get(b, {}).get("journal")
                allowed_c = by_base.get(b, {}).get("compte")
                allowed_f = by_base.get(b, {}).get("fournisseur")

            pred = predict_row(neigh, allowed_journaux=allowed_j,
                               allowed_comptes=allowed_c, allowed_fournisseurs=allowed_f)

            truth = {
                "journal": meta.get("journal_code"),
                "compte": meta.get("compte_code"),
                "compte3": (meta.get("compte_code") or "")[:3] or None,
                "fournisseur": meta.get("fournisseur"),
                "sens": meta.get("sens") if meta.get("sens") in ("in", "out") else None,
            }
            predicted = {
                "journal": pred.journal,
                "compte": pred.compte,
                "compte3": pred.compte,   # meme FieldPrediction, compare sur le prefixe 3 ci-dessous
                "fournisseur": pred.fournisseur,
                "sens": pred.sens,
            }

            row = {"id": did, "top_sim": round(top_sim, 4), "n_voisins": pred.n_voisins,
                   "base_id": meta.get("base_id"), "fichier": meta.get("fichier_source")}

            for f in fields:
                fp = predicted[f]
                t = truth[f]
                pv = fp.value
                if f == "compte3" and pv:
                    pv = pv[:3]
                # evaluable ?
                if f == "fournisseur":
                    ev = _four_evaluable(meta)
                else:
                    ev = t is not None
                if ev:
                    evaluable[f] += 1
                    if pv is not None:
                        covered[f] += 1
                        ok = (pv == t)
                        if ok:
                            hit[f] += 1
                        for s in _CONF_SEUILS:
                            if fp.confidence >= s:
                                conf_tot[f][s] += 1
                                if ok:
                                    conf_hit[f][s] += 1
                        row[f] = "hit" if ok else "miss"
                        row[f + "_pred"] = pv
                        row[f + "_true"] = t
                        row[f + "_conf"] = fp.confidence
                    else:
                        row[f] = "no_pred"
                else:
                    row[f] = "na"
            per_item.append(row)
            if count % 500 == 0:
                self.stdout.write(f"  {count}/{len(sample)}")

        # -------- scorecard --------
        def acc(f):
            cov = covered[f]
            ev = evaluable[f]
            return {
                "precision_si_predit": round(100 * hit[f] / cov, 1) if cov else None,
                "couverture": round(100 * cov / ev, 1) if ev else None,
                "precision_globale": round(100 * hit[f] / ev, 1) if ev else None,
                "n_evaluables": ev,
            }

        summary = {
            "genere_le": timezone.now().isoformat(),
            "index": {"path": index_path, "ecritures": len(idx)},
            "params": {"echantillon": len(sample), "k": opts["k"], "restrict_base": bool(by_base), "seed": opts["seed"]},
            "baseline_classe_majoritaire_pct": {k: round(100 * v, 1) for k, v in baseline.items()},
            "similarite_top_voisin": dict(sim_hist),
            "precision": {f: acc(f) for f in fields},
            "precision_au_seuil_de_confiance": {
                f: {
                    str(s): {
                        "pct_lignes": round(100 * conf_tot[f][s] / evaluable[f], 1) if evaluable[f] else None,
                        "precision": round(100 * conf_hit[f][s] / conf_tot[f][s], 1) if conf_tot[f][s] else None,
                    }
                    for s in _CONF_SEUILS
                }
                for f in fields
            },
        }

        with open(os.path.join(out_dir, "scorecard_retrieval.json"), "w", encoding="utf-8") as fh:
            json.dump(summary, fh, ensure_ascii=False, indent=2)
        with open(os.path.join(out_dir, "scorecard_retrieval.md"), "w", encoding="utf-8") as fh:
            fh.write(self._md(summary))
        with open(os.path.join(out_dir, "per_item.csv"), "w", encoding="utf-8", newline="") as fh:
            cols = ["id", "top_sim", "n_voisins", "base_id", "fichier"]
            for f in fields:
                cols += [f, f + "_pred", f + "_true", f + "_conf"]
            wr = csv.DictWriter(fh, fieldnames=cols, delimiter=";", extrasaction="ignore")
            wr.writeheader()
            wr.writerows(per_item)

        self.stdout.write(self.style.SUCCESS("\n=== Scorecard retrieval ==="))
        for f in fields:
            a = summary["precision"][f]
            self.stdout.write(
                f"  {f:<12} predit {a['precision_si_predit']} %  | couverture {a['couverture']} %  "
                f"| global {a['precision_globale']} %  (n={a['n_evaluables']})"
            )
        self.stdout.write(f"  baseline (classe majoritaire) : {summary['baseline_classe_majoritaire_pct']}")
        self.stdout.write(f"  similarite top voisin : {dict(sim_hist)}")
        self.stdout.write(f"\n  -> {out_dir}")

    # ------------------------------------------------------------------ #

    def _md(self, s):
        L = [f"# Scorecard classification par similarite - Phase 3\n\n_{s['genere_le']}_\n"]
        p = s["params"]
        L.append(f"Index : {s['index']['ecritures']:,} ecritures | echantillon {p['echantillon']:,} | "
                 f"k={p['k']} | restrict_base={p['restrict_base']}\n")
        L.append(f"Similarite du meilleur voisin : `{s['similarite_top_voisin']}`\n")
        L.append("| Champ | Precision si predit | Couverture | Precision globale | Baseline classe maj. | n |")
        L.append("|---|---|---|---|---|---|")
        bl = s["baseline_classe_majoritaire_pct"]
        blmap = {"journal": bl.get("journal_code"), "compte": bl.get("compte_code"),
                 "compte3": None, "fournisseur": bl.get("fournisseur"), "sens": bl.get("sens")}
        for f, a in s["precision"].items():
            L.append(f"| {f} | {a['precision_si_predit']} % | {a['couverture']} % | "
                     f"{a['precision_globale']} % | {blmap.get(f)} % | {a['n_evaluables']} |")
        L.append("\n## Precision au seuil de confiance (KPI pre-remplissage)\n")
        L.append("Pour chaque seuil : (% des lignes evaluables au-dessus du seuil ; precision sur ces lignes)\n")
        L.append("| Champ | conf>=0.5 | conf>=0.7 | conf>=0.9 |")
        L.append("|---|---|---|---|")
        for f, d in s["precision_au_seuil_de_confiance"].items():
            cells = " | ".join(
                f"{d[str(x)]['pct_lignes']}% -> {d[str(x)]['precision']}%" for x in _CONF_SEUILS
            )
            L.append(f"| {f} | {cells} |")
        return "\n".join(L) + "\n"
