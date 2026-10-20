"""
Pre-remplit CompteFournisseurAutorise a partir de la comptabilite existante
(BaseDiameX) : pour chaque regle en mode "fournisseur", on autorise les
fournisseurs qui ont deja ete utilises sur ce compte dans l'historique.

  python manage.py seed_compte_fournisseurs_autorises --dry-run
  python manage.py seed_compte_fournisseurs_autorises
  python manage.py seed_compte_fournisseurs_autorises --organisation <uuid> --min-occurrences 2
  python manage.py seed_compte_fournisseurs_autorises --reset      # vide avant de recreer

Scope org : progs de Base.prog_diamex de l'organisation -> BaseDiameX.prog
(meme logique que _get_diamex_scope_by_prog). Sans --commit implicite : ecrit
sauf si --dry-run. Affiche toujours les chaines fournisseur non rapprochees.
"""
from collections import defaultdict

from django.core.management.base import BaseCommand

from apps.accounting.models_regles_saisie import RegleSaisieCompte
from apps.accounting.regles_saisie.seed_fournisseurs import (
    peupler_fournisseurs_pour_compte,
    progs_organisation,
)
from apps.organization.models import Organisation


class Command(BaseCommand):
    help = "Autorise les fournisseurs par compte d'apres l'historique BaseDiameX."

    def add_arguments(self, parser):
        parser.add_argument("--organisation", default=None, help="UUID (defaut: toutes)")
        parser.add_argument("--min-occurrences", type=int, default=1,
                            help="Nb minimum d'ecritures historiques pour retenir un fournisseur")
        parser.add_argument("--reset", action="store_true",
                            help="Vide les autorisations des comptes concernes avant")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        min_occ = max(1, opts["min_occurrences"])
        dry = opts["dry_run"]

        orgs = Organisation.objects.all()
        if opts["organisation"]:
            orgs = orgs.filter(id=opts["organisation"])
        orgs = list(orgs)

        total_liens = 0
        total_orgs = 0
        non_rapproches_global = defaultdict(int)

        for org in orgs:
            progs = progs_organisation(org)
            regles = list(
                RegleSaisieCompte.objects.filter(organisation=org, mode="fournisseur", actif=True)
            )
            if not progs or not regles:
                continue
            total_orgs += 1
            self.stdout.write(self.style.MIGRATE_HEADING(
                f"\n{org.nom_organisation}  ({len(progs)} prog, {len(regles)} regles fournisseur)"
            ))

            for r in regles:
                stats = peupler_fournisseurs_pour_compte(
                    org, r.compte_cible, est_prefixe=r.est_prefixe,
                    min_occurrences=min_occ, reset=opts["reset"], dry_run=dry,
                )
                total_liens += stats["crees"]
                for raw, n in stats["inconnus"]:
                    non_rapproches_global[raw] += n

                if stats["trouves"] or stats["inconnus"]:
                    inconnus_aff = [f"{raw} (x{n})" for raw, n in stats["inconnus"][:6]]
                    self.stdout.write(
                        f"  {r.compte_cible:<8} {stats['trouves']:>3} fournisseur(s)"
                        + (f"  | {stats['ignores']} sous le seuil" if stats["ignores"] else "")
                        + (f"  | non rapproches: {', '.join(inconnus_aff)}" if inconnus_aff else "")
                    )

        verbe = "seraient crees" if dry else "crees"
        self.stdout.write(self.style.SUCCESS(
            f"\n{total_liens} lien(s) {verbe} sur {total_orgs} organisation(s)."
        ))
        if non_rapproches_global:
            self.stdout.write(self.style.WARNING(
                "\nChaines fournisseur non rapprochees (a corriger dans BaseDiameX ou creer le Fournisseur) :"
            ))
            for raw, n in sorted(non_rapproches_global.items(), key=lambda x: -x[1])[:40]:
                self.stdout.write(f"  x{n:<5} {raw}")
        if dry:
            self.stdout.write(self.style.NOTICE("\n--dry-run : rien ecrit. Relancer sans --dry-run pour appliquer."))
