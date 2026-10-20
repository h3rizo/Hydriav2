"""
Phase 4 - essai interactif du chemin TEXTE (aucun appel API).

  python manage.py prefill_suggest "Achat ciment 10 sacs QUINCAILLERIE SOA"
  python manage.py prefill_suggest "Paiement forfaitaire Ambanja BP" --base <uuid> --json
"""
import json

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Teste suggest_from_text sur un libelle (retrieval seul, sans API)."

    def add_arguments(self, parser):
        parser.add_argument("texte", help="Libelle a classer")
        parser.add_argument("--base", default=None, help="base_id (UUID) pour contraindre aux codes de la base")
        parser.add_argument("--k", type=int, default=12)
        parser.add_argument("--json", action="store_true", help="Sortie JSON brute")

    def handle(self, *args, **opts):
        from apps.accounting.ai_prefill.pipeline import IndexNotBuilt, suggest_from_text

        try:
            sugg = suggest_from_text(opts["texte"], base_id=opts["base"], k=opts["k"])
        except IndexNotBuilt as exc:
            raise CommandError(f"Index absent : {exc}\nLancer d'abord : python manage.py build_prefill_index")

        if opts["json"]:
            self.stdout.write(json.dumps(sugg.as_dict(), ensure_ascii=False, indent=2))
            return

        self.stdout.write(f"\nRequete : {opts['texte']!r}")
        self.stdout.write(f"Index : {sugg.index_size:,} ecritures | seuil auto = {sugg.seuil}")
        if sugg.warnings:
            for w in sugg.warnings:
                self.stdout.write(self.style.WARNING(f"  ! {w}"))
        self.stdout.write("\n  Champ         Valeur           Conf   Auto  Libelle")
        self.stdout.write("  " + "-" * 70)
        for name, fs in sugg.fields.items():
            auto = "OUI" if fs.auto else " - "
            self.stdout.write(
                f"  {name:<12}  {str(fs.value or '-'):<15}  {fs.confidence:>4}  {auto:>4}  {fs.label[:32]}"
            )
        self.stdout.write("\n  Voisins :")
        for n in sugg.neighbours:
            self.stdout.write(
                f"   [{n['similarite']:.3f}] {n['compte_code']}/{n['journal_code']}/{n['fournisseur'] or '-'}  "
                f"{n['description'][:70]}"
            )
        self.stdout.write("")
