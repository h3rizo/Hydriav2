"""
Commande de rattachement retroactif des avis de representants existants vers des
Reunions. Les avis recueillis a la meme date, dans la meme commune, sont consideres
comme issus d'une seule et meme reunion : on cree (si besoin) une Reunion pour
chaque groupe (date_avis, commune) et on y rattache tous les avis correspondants.

Usage:
    python manage.py rattacher_avis_reunions --dry-run
    python manage.py rattacher_avis_reunions
"""
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.usagers.models import AvisRepresentant, Reunion


class Command(BaseCommand):
    help = "Rattache retroactivement les avis existants (meme date + meme commune) a une Reunion generee automatiquement."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help="N'ecrit rien en base, affiche seulement ce qui serait fait.",
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        avis_sans_reunion = AvisRepresentant.objects.filter(
            reunion__isnull=True
        ).select_related('representant', 'representant__village', 'representant__village__fokontany', 'representant__village__fokontany__commune')

        groupes = defaultdict(list)
        avis_sans_commune = []

        for avis in avis_sans_reunion:
            village = avis.representant.village if avis.representant else None
            fokontany = village.fokontany if village else None
            commune = fokontany.commune if fokontany else None

            if not commune:
                avis_sans_commune.append(avis)
                continue

            groupes[(avis.date_avis, commune.id)].append(avis)

        self.stdout.write(f"{len(groupes)} groupe(s) (date, commune) detecte(s), {sum(len(v) for v in groupes.values())} avis concernes.")
        if avis_sans_commune:
            self.stdout.write(self.style.WARNING(
                f"{len(avis_sans_commune)} avis ignore(s) car leur representant n'a pas de commune resolvable."
            ))

        nb_reunions_creees = 0
        nb_reunions_reutilisees = 0
        nb_avis_rattaches = 0

        with transaction.atomic():
            for (date_avis, commune_id), avis_list in groupes.items():
                commune = avis_list[0].representant.village.fokontany.commune

                reunion = Reunion.objects.filter(
                    date_reunion=date_avis,
                    commune_id=commune_id,
                ).first()

                if reunion:
                    nb_reunions_reutilisees += 1
                else:
                    nb_reunions_creees += 1
                    self.stdout.write(
                        f"  + Reunion a creer : {date_avis} - {commune.nom_commune} ({len(avis_list)} avis)"
                    )
                    if not dry_run:
                        reunion = Reunion.objects.create(
                            commune=commune,
                            date_reunion=date_avis,
                            objet=f"Reunion usagers - {commune.nom_commune}",
                            compte_rendu=(
                                "Reunion generee automatiquement lors du rattachement retroactif des avis "
                                "des representants recueillis a cette date dans cette commune."
                            ),
                        )

                if not dry_run and reunion:
                    for avis in avis_list:
                        avis.reunion = reunion
                    AvisRepresentant.objects.bulk_update(avis_list, ['reunion'])
                    nb_avis_rattaches += len(avis_list)
                elif dry_run:
                    nb_avis_rattaches += len(avis_list)

            if dry_run:
                # Annule toute ecriture eventuelle (aucune attendue ici, securite supplementaire)
                transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS(
            f"\nTermine{' (dry-run, rien ecrit)' if dry_run else ''} : "
            f"{nb_reunions_creees} reunion(s) creee(s), {nb_reunions_reutilisees} reunion(s) existante(s) reutilisee(s), "
            f"{nb_avis_rattaches} avis rattache(s)."
        ))
