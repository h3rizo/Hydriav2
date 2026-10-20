"""
Phase 3 - construit l'index de similarite lexicale sur l'historique BaseDiameX.

Lecture seule. Produit un fichier pickle autonome (libelles + labels + contexte)
reutilise par `eval_prefill_retrieval` et, plus tard, par l'endpoint de la Phase 4.

  python manage.py build_prefill_index
  python manage.py build_prefill_index --out /chemin/index.pkl --max-df 0.35
"""
import os

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounting.ai_prefill.retrieval import TrigramIndex, build_corpus_text
from apps.accounting.models import BaseDiameX
from apps.billing.models import Fournisseur


def _norm_key(v):
    c = "".join(ch.lower() if ch.isalnum() else " " for ch in str(v or "").strip())
    return " ".join(c.split())


def _sens(mi, mo):
    mi, mo = mi or 0, mo or 0
    if mi and not mo:
        return "in"
    if mo and not mi:
        return "out"
    return "nul"


class Command(BaseCommand):
    help = "Phase 3 : construit l'index de similarite lexicale (trigrammes) sur BaseDiameX."

    def add_arguments(self, parser):
        parser.add_argument("--out", default=None,
                            help="Fichier pickle de sortie (defaut: <BASE_DIR>/exports/ai_prefill/trgm_index.pkl)")
        parser.add_argument("--fichier", action="append", default=None, help="Filtre fichier_source (icontains). Repetable.")
        parser.add_argument("--date-min", default=None, help="date_m >= YYYY-MM-DD")
        parser.add_argument("--date-max", default=None, help="date_m <= YYYY-MM-DD")
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument("--max-df", type=float, default=0.4,
                            help="Retire les trigrammes presents dans plus de cette fraction des docs (bruit)")
        parser.add_argument("--no-info", action="store_true", help="Ne pas ajouter le champ `info` au texte indexe")

    def handle(self, *args, **opts):
        out = opts["out"] or os.path.join(settings.BASE_DIR, "exports", "ai_prefill", "trgm_index.pkl")
        os.makedirs(os.path.dirname(out), exist_ok=True)

        # referentiels legers pour resoudre base + nom fournisseur
        from apps.organization.models import Base
        base_by_prog = {}
        for b in Base.objects.only("id", "prog_diamex"):
            if b.prog_diamex:
                base_by_prog.setdefault(b.prog_diamex.strip(), b)
        four_name_by_idxls = {
            f.idxls: f.nom_fournisseur for f in Fournisseur.objects.only("idxls", "nom_fournisseur")
            if f.idxls is not None
        }

        qs = BaseDiameX.objects.all().only(
            "id", "description", "info", "journal_code", "compte_code",
            "fournisseur", "montant_in", "montant_out", "prog", "date_m", "fichier_source",
        )
        if opts["fichier"]:
            from django.db.models import Q
            q = Q()
            for frag in opts["fichier"]:
                q |= Q(fichier_source__icontains=frag)
            qs = qs.filter(q)
        if opts["date_min"]:
            qs = qs.filter(date_m__gte=opts["date_min"])
        if opts["date_max"]:
            qs = qs.filter(date_m__lte=opts["date_max"])
        qs = qs.order_by("id")
        if opts["limit"]:
            qs = qs[: opts["limit"]]

        idx = TrigramIndex()
        n = 0
        skipped_empty = 0
        for e in qs.iterator(chunk_size=3000):
            text = build_corpus_text(e.description, "" if opts["no_info"] else e.info)
            if not text.strip():
                skipped_empty += 1
                continue
            prog = (e.prog or "").strip()
            base = base_by_prog.get(prog)
            raw_four = (e.fournisseur or "").strip() or None
            four_name = None
            if raw_four and raw_four.isdigit():
                four_name = four_name_by_idxls.get(int(raw_four))
            idx.add(e.id, text, {
                "text": text,
                "journal_code": (e.journal_code or "").strip() or None,
                "compte_code": (e.compte_code or "").strip() or None,
                "fournisseur": raw_four,
                "fournisseur_name": four_name,
                "sens": _sens(e.montant_in, e.montant_out),
                "montant": float((e.montant_in or 0) or (e.montant_out or 0)),
                "base_id": str(base.id) if base else None,
                "prog": prog or None,
                "fichier_source": e.fichier_source,
                "date_m": e.date_m.isoformat()[:10] if e.date_m else None,
            })
            n += 1
            if n % 5000 == 0:
                self.stdout.write(f"  {n} indexes...")

        dropped = idx.prune_common(opts["max_df"])
        idx.save(out)
        size_mb = os.path.getsize(out) / (1024 * 1024)

        self.stdout.write(self.style.SUCCESS(
            f"Index construit : {n:,} ecritures, {len(idx.postings):,} trigrammes "
            f"({dropped} elagues), {skipped_empty} sans libelle.\n"
            f"  -> {out}  ({size_mb:.1f} Mo)  [{timezone.now().isoformat()}]"
        ))
