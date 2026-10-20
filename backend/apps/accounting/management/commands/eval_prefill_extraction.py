"""
Phase 2 - gate : mesure la precision de l'extraction IA sur l'echantillon
`eval_sample.jsonl` produit par `export_diamex_dataset` (Phase 1).

Pour chaque ligne : resout le fichier scan (copie serveur `scan_importe` sous
MEDIA_ROOT), lance `ai_prefill.extract_receipt`, compare montant / sens / date /
fournisseur a la verite terrain. Ecrit un scorecard.

A lancer SUR LE VPS (les scans y sont). Consomme du budget API : chaque ligne non
deja en cache fait un appel Claude.

  python manage.py eval_prefill_extraction --sample exports/diamex_dataset/<ts>/eval_sample.jsonl
  python manage.py eval_prefill_extraction --sample .../eval_sample.jsonl --limit 20
"""
import csv
import json
import os
from collections import Counter
from difflib import SequenceMatcher

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


def _norm(value):
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in str(value or "").strip())
    return " ".join(cleaned.split())


def _gt_montant(labels):
    mi, mo = labels.get("montant_in") or 0, labels.get("montant_out") or 0
    if mi and not mo:
        return float(mi)
    if mo and not mi:
        return float(mo)
    return float(mo or mi or 0)


def _montant_match(gt, pred):
    if not gt or pred is None:
        return "na"
    if round(gt) == round(pred):
        return "exact"
    if abs(gt - pred) <= max(1.0, 0.01 * gt):
        return "1pct"
    return "miss"


def _sens_match(gt, pred):
    if gt not in ("in", "out"):
        return "na"
    mapped = {"depense": "out", "recette": "in"}.get(pred or "", "")
    return "hit" if mapped == gt else "miss"


def _date_match(rec, pred):
    if not pred:
        return "na"
    targets = {rec.get("date_m"), rec.get("date_rec")}
    targets.discard(None)
    if not targets:
        return "na"
    return "hit" if pred[:10] in targets else "miss"


# marqueurs internes (salaires / charges sociales) : pas de fournisseur reel a predire
_SAL_MARKERS = {"salnet", "salosiefa", "salfmfp", "salcnaps", "salmed", "salxdivers"}


def _four_gt(labels):
    """Verite terrain fournisseur = nom resolu depuis billing.Fournisseur (le champ
    brut est le plus souvent un idxls entier). None si non evaluable."""
    raw = (labels.get("fournisseur_raw") or "").strip()
    name = (labels.get("fournisseur_name") or "").strip()
    if name:
        return name
    if not raw or raw.isdigit() or _norm(raw) in _SAL_MARKERS:
        return None  # vide, idxls orphelin, ou marqueur salaire -> non evaluable
    return raw


def _four_match(gt_name, pred_raw):
    if not gt_name:
        return "na"
    g, p = _norm(gt_name), _norm(pred_raw)
    if not p:
        return "miss"
    if g == p:
        return "exact"
    gt_toks, p_toks = set(g.split()), set(p.split())
    if gt_toks and (gt_toks <= p_toks or p_toks <= gt_toks):
        return "fuzzy"
    if SequenceMatcher(None, g, p).ratio() >= 0.8:
        return "fuzzy"
    return "miss"


class Command(BaseCommand):
    help = "Phase 2 gate : precision de l'extraction IA vs verite terrain (eval_sample.jsonl)."

    def add_arguments(self, parser):
        parser.add_argument("--sample", required=True, help="Chemin vers eval_sample.jsonl (Phase 1)")
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument("--force", action="store_true", help="Ignore le cache ScanExtraction")
        parser.add_argument("--out", default=None, help="Dossier de sortie (defaut: a cote du sample)")
        parser.add_argument("--media-root", default=None, help="Override MEDIA_ROOT (tests locaux)")

    def handle(self, *args, **opts):
        from apps.accounting.ai_prefill.services import ApiAccountError, BudgetExceeded, extract_receipt

        sample_path = opts["sample"]
        if not os.path.exists(sample_path):
            raise CommandError(f"Introuvable : {sample_path}")

        out_dir = opts["out"] or os.path.join(os.path.dirname(os.path.abspath(sample_path)), "eval_prefill")
        os.makedirs(out_dir, exist_ok=True)
        media_root = opts["media_root"] or settings.MEDIA_ROOT

        rows = []
        with open(sample_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        if opts["limit"]:
            rows = rows[: opts["limit"]]
        self.stdout.write(f"{len(rows)} ligne(s) a evaluer -> {out_dir}")

        per_item = []
        tallies = {k: Counter() for k in ("montant", "sens", "date", "fournisseur")}
        n_ok = n_refus = n_err = n_nofile = n_cache = 0
        cout_total = 0.0
        conf_buckets = {"haute": Counter(), "basse": Counter()}  # conf>=0.7 vs <0.7 : montant exact ?

        for i, rec in enumerate(rows, 1):
            scan = rec.get("scan", {})
            data = None
            src = scan.get("server_copy") or ""
            if src:
                try:
                    if opts["media_root"]:
                        path = os.path.join(media_root, src.replace("/", os.sep))
                        with open(path, "rb") as f:
                            data = f.read()
                    else:
                        with default_storage.open(src, "rb") as f:
                            data = f.read()
                except Exception as exc:  # noqa: BLE001
                    self.stdout.write(self.style.WARNING(f"  [{i}] scan illisible {src}: {exc}"))
            if data is None and scan.get("hyperlink") and os.path.exists(scan["hyperlink"]):
                with open(scan["hyperlink"], "rb") as f:
                    data = f.read()

            if data is None:
                n_nofile += 1
                per_item.append({"id": rec.get("id"), "resultat": "sans_fichier", "source": src})
                continue

            try:
                outcome = extract_receipt(data, filename=src or scan.get("hyperlink") or "", force=opts["force"])
            except BudgetExceeded as exc:
                self.stdout.write(self.style.ERROR(str(exc)))
                break
            except ApiAccountError as exc:
                self.stdout.write(self.style.ERROR(
                    f"Compte Anthropic : {exc}\n"
                    f"-> Charger des credits sur console.anthropic.com (Plans & Billing), puis relancer."
                ))
                break

            if outcome.from_cache:
                n_cache += 1
            else:
                cout_total += float(outcome.record.cout_usd)

            if outcome.status == "refusal":
                n_refus += 1
                per_item.append({"id": rec.get("id"), "resultat": "refus", "erreur": outcome.erreur})
                continue
            if outcome.status == "error" or outcome.extraction is None:
                n_err += 1
                per_item.append({"id": rec.get("id"), "resultat": "erreur", "erreur": outcome.erreur})
                continue

            n_ok += 1
            ex = outcome.extraction
            labels = rec.get("labels", {})
            gt_m = _gt_montant(labels)
            m_res = _montant_match(gt_m, ex.montant_total)
            s_res = _sens_match(labels.get("sens"), ex.sens_probable)
            d_res = _date_match(rec, ex.date_piece)
            gt_four = _four_gt(labels)
            f_res = _four_match(gt_four, ex.fournisseur_nom_brut)

            for k, v in (("montant", m_res), ("sens", s_res), ("date", d_res), ("fournisseur", f_res)):
                tallies[k][v] += 1

            bucket = "haute" if ex.confiance_montant >= 0.7 else "basse"
            conf_buckets[bucket][m_res] += 1

            per_item.append({
                "id": rec.get("id"),
                "resultat": "ok",
                "from_cache": outcome.from_cache,
                "montant": m_res, "montant_gt": gt_m, "montant_pred": ex.montant_total,
                "sens": s_res, "sens_gt": labels.get("sens"), "sens_pred": ex.sens_probable,
                "date": d_res, "date_gt": rec.get("date_m"), "date_rec_gt": rec.get("date_rec"), "date_pred": ex.date_piece,
                "fournisseur": f_res, "four_gt": gt_four, "four_raw_gt": labels.get("fournisseur_raw"),
                "four_pred": ex.fournisseur_nom_brut,
                "manuscrit": ex.manuscrit, "lisibilite": ex.lisibilite, "langue": ex.langue,
                "conf_montant": ex.confiance_montant, "conf_four": ex.confiance_fournisseur,
                "cout_usd": float(outcome.record.cout_usd), "latence_ms": outcome.record.latence_ms,
                "notes": ex.notes[:200],
            })
            if i % 10 == 0:
                self.stdout.write(f"  {i}/{len(rows)}  (cout cumule {cout_total:.2f} $)")

        # ---- scorecard ----
        def rate(counter, hits):
            scored = sum(v for k, v in counter.items() if k != "na")
            got = sum(counter.get(h, 0) for h in hits)
            return (round(100 * got / scored, 1) if scored else None), scored

        summary = {
            "genere_le": timezone.now().isoformat(),
            "modele": getattr(settings, "ANTHROPIC_MODEL", ""),
            "effort": getattr(settings, "ANTHROPIC_EFFORT", ""),
            "lignes": len(rows),
            "ok": n_ok, "refus": n_refus, "erreurs": n_err, "sans_fichier": n_nofile,
            "depuis_cache": n_cache,
            "cout_total_usd_hors_cache": round(cout_total, 4),
            "precision": {
                "montant_exact": rate(tallies["montant"], ("exact",)),
                "montant_exact_ou_1pct": rate(tallies["montant"], ("exact", "1pct")),
                "sens": rate(tallies["sens"], ("hit",)),
                "date": rate(tallies["date"], ("hit",)),
                "fournisseur_exact": rate(tallies["fournisseur"], ("exact",)),
                "fournisseur_exact_ou_fuzzy": rate(tallies["fournisseur"], ("exact", "fuzzy")),
            },
            "detail_tallies": {k: dict(v) for k, v in tallies.items()},
            "confiance_vs_exactitude_montant": {
                "conf>=0.7": dict(conf_buckets["haute"]),
                "conf<0.7": dict(conf_buckets["basse"]),
            },
        }

        with open(os.path.join(out_dir, "scorecard.json"), "w", encoding="utf-8") as fh:
            json.dump(summary, fh, ensure_ascii=False, indent=2)

        with open(os.path.join(out_dir, "scorecard.md"), "w", encoding="utf-8") as fh:
            p = summary["precision"]
            fh.write(f"# Scorecard extraction IA - Phase 2\n\n_{summary['genere_le']}_\n\n")
            fh.write(f"Modele : `{summary['modele']}` (effort `{summary['effort']}`)\n\n")
            fh.write(f"- Lignes : {summary['lignes']} | OK : {n_ok} | refus : {n_refus} | "
                     f"erreurs : {n_err} | sans fichier : {n_nofile} | depuis cache : {n_cache}\n")
            fh.write(f"- Cout total (hors cache) : **{summary['cout_total_usd_hors_cache']} $**\n\n")
            fh.write("| Champ | Precision | n evalues |\n|---|---|---|\n")
            for label, key in (
                ("Montant exact", "montant_exact"),
                ("Montant exact ou ±1%", "montant_exact_ou_1pct"),
                ("Sens (in/out)", "sens"),
                ("Date (= date_m ou date_rec)", "date"),
                ("Fournisseur nom exact", "fournisseur_exact"),
                ("Fournisseur exact ou proche", "fournisseur_exact_ou_fuzzy"),
            ):
                val, n = p[key]
                fh.write(f"| {label} | {val if val is not None else 'n/a'} % | {n} |\n")
            fh.write(f"\nDetail : `{json.dumps(summary['detail_tallies'], ensure_ascii=False)}`\n")
            fh.write(f"\nConfiance montant vs exactitude : "
                     f"`{json.dumps(summary['confiance_vs_exactitude_montant'], ensure_ascii=False)}`\n")

        with open(os.path.join(out_dir, "per_item.csv"), "w", encoding="utf-8", newline="") as fh:
            cols = ["id", "resultat", "from_cache", "montant", "montant_gt", "montant_pred",
                    "sens", "sens_gt", "sens_pred", "date", "date_gt", "date_rec_gt", "date_pred",
                    "fournisseur", "four_gt", "four_raw_gt", "four_pred", "manuscrit", "lisibilite", "langue",
                    "conf_montant", "conf_four", "cout_usd", "latence_ms", "erreur", "notes", "source"]
            wr = csv.DictWriter(fh, fieldnames=cols, delimiter=";", extrasaction="ignore")
            wr.writeheader()
            for row in per_item:
                wr.writerow(row)

        self.stdout.write(self.style.SUCCESS("\n=== Scorecard ==="))
        for label, key in (("Montant exact", "montant_exact"), ("Montant ±1%", "montant_exact_ou_1pct"),
                           ("Sens", "sens"), ("Date", "date"),
                           ("Fournisseur exact", "fournisseur_exact"), ("Fournisseur proche", "fournisseur_exact_ou_fuzzy")):
            val, n = summary["precision"][key]
            self.stdout.write(f"  {label:<22} {val if val is not None else 'n/a'} %   (n={n})")
        self.stdout.write(f"  Cout total (hors cache) : {summary['cout_total_usd_hors_cache']} $")
        self.stdout.write(f"\n  -> {out_dir}")
