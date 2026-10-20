"""
Commande de rattrapage : renseigne le champ entry_id des PointageReunionDiameX existants
qui ne l'ont pas encore, en le retrouvant via le couple (numero_diamex, base_diamex)
correspondant a (BaseDiameX.id_access, BaseDiameX.prog).

Contexte : le champ entry_id a ete ajoute au modele PointageReunionDiameX apres coup
(migration 0018_pointagereuniondiamex_entry_id), donc les pointages crees avant cette
migration ont entry_id=NULL. Consequence visible : dans le modal de detail d'une reunion
(page /usagers/reunions/), le bouton "Voir le scan" de la colonne Depenses DiameX pointees
n'apparait que si entry_id est renseigne (cf. reunions_list.html, detail-pointages-body) :
d'ou l'incoherence "parfois une colonne scan, parfois non" rapportee par l'utilisateur.

Usage:
    python manage.py resoudre_entry_id_pointages --dry-run
    python manage.py resoudre_entry_id_pointages
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounting.models import BaseDiameX
from apps.usagers.models import PointageReunionDiameX


class Command(BaseCommand):
    help = "Renseigne entry_id sur les PointageReunionDiameX existants qui ne l'ont pas, via (numero_diamex, base_diamex)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help="N'ecrit rien en base, affiche seulement ce qui serait fait.",
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        pointages_sans_entry_id = PointageReunionDiameX.objects.filter(entry_id__isnull=True)
        total = pointages_sans_entry_id.count()
        self.stdout.write(f"{total} pointage(s) sans entry_id a traiter.")

        if not total:
            self.stdout.write(self.style.SUCCESS("Rien a faire."))
            return

        # Index BaseDiameX par (id_access, prog) pour resoudre en une seule requete groupee,
        # plutot qu'une requete par pointage.
        couples = [
            (p.numero_diamex, p.base_diamex)
            for p in pointages_sans_entry_id
            if p.numero_diamex and p.base_diamex
        ]
        numeros = {c[0] for c in couples}
        entries = BaseDiameX.objects.filter(id_access__in=numeros).values('id', 'id_access', 'prog')
        entry_id_par_couple = {
            (str(e['id_access']), (e['prog'] or '').strip()): e['id']
            for e in entries
        }

        nb_resolus = 0
        nb_introuvables = 0
        a_mettre_a_jour = []

        with transaction.atomic():
            for pointage in pointages_sans_entry_id:
                couple = (pointage.numero_diamex, pointage.base_diamex)
                entry_id = entry_id_par_couple.get(couple)

                if entry_id is None:
                    nb_introuvables += 1
                    self.stdout.write(self.style.WARNING(
                        f"  - Introuvable : {pointage.reunion.objet} - {pointage.numero_diamex}/{pointage.base_diamex}"
                    ))
                    continue

                nb_resolus += 1
                self.stdout.write(
                    f"  + {pointage.reunion.objet} - {pointage.numero_diamex}/{pointage.base_diamex} -> entry_id={entry_id}"
                )
                pointage.entry_id = entry_id
                a_mettre_a_jour.append(pointage)

            if not dry_run and a_mettre_a_jour:
                PointageReunionDiameX.objects.bulk_update(a_mettre_a_jour, ['entry_id'])

            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS(
            f"\nTermine{' (dry-run, rien ecrit)' if dry_run else ''} : "
            f"{nb_resolus} entry_id resolu(s), {nb_introuvables} introuvable(s) (ligne BaseDiameX absente/supprimee)."
        ))
