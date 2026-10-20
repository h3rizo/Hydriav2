"""
Cree/actualise les RegleSaisieCompte pour une ou toutes les organisations, a
partir de apps/accounting/regles_saisie/seed_data.REGLES.

  python manage.py seed_regles_saisie
  python manage.py seed_regles_saisie --organisation <uuid>
  python manage.py seed_regles_saisie --reset          # supprime avant de recreer
  python manage.py seed_regles_saisie --dry-run
"""
from django.core.management.base import BaseCommand

from apps.accounting.models_regles_saisie import RegleSaisieCompte
from apps.accounting.regles_saisie.schema import valider_config
from apps.accounting.regles_saisie.seed_data import REGLES
from apps.organization.models import Organisation


class Command(BaseCommand):
    help = "Seed des regles de saisie guidee par compte (par organisation)."

    def add_arguments(self, parser):
        parser.add_argument("--organisation", default=None, help="UUID d'une organisation (defaut: toutes)")
        parser.add_argument("--reset", action="store_true", help="Supprime les regles existantes avant")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        # validation des configs du seed
        pb = 0
        for r in REGLES:
            errs = valider_config(r["config"])
            if errs:
                pb += 1
                self.stdout.write(self.style.ERROR(f"  config invalide {r['compte_cible']}: {errs}"))
        if pb:
            self.stdout.write(self.style.ERROR(f"{pb} config(s) invalide(s) - abandon."))
            return
        self.stdout.write(f"{len(REGLES)} regles dans le seed, toutes valides.")

        orgs = Organisation.objects.all()
        if opts["organisation"]:
            orgs = orgs.filter(id=opts["organisation"])
        orgs = list(orgs)
        self.stdout.write(f"{len(orgs)} organisation(s).")

        total_c = total_u = 0
        for org in orgs:
            if opts["reset"] and not opts["dry_run"]:
                n = RegleSaisieCompte.objects.filter(organisation=org).delete()[0]
                self.stdout.write(f"  {org.nom_organisation} : {n} supprimee(s)")
            for i, r in enumerate(REGLES):
                defaults = {
                    "est_prefixe": r["est_prefixe"],
                    "mode": r["mode"],
                    "sens": r["sens"],
                    "libelle": r["libelle"],
                    "config": r["config"],
                    "ordre": i,
                    "actif": True,
                }
                if opts["dry_run"]:
                    exists = RegleSaisieCompte.objects.filter(
                        organisation=org, compte_cible=r["compte_cible"]).exists()
                    total_u += exists
                    total_c += (not exists)
                    continue
                _, created = RegleSaisieCompte.objects.update_or_create(
                    organisation=org, compte_cible=r["compte_cible"], defaults=defaults)
                total_c += created
                total_u += (not created)

        verb = "seraient" if opts["dry_run"] else ""
        self.stdout.write(self.style.SUCCESS(
            f"Termine : {total_c} creee(s) {verb}, {total_u} mise(s) a jour {verb}."
        ))
