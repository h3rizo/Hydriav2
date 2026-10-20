"""
Commande Django pour nettoyer les doublons dans la table ConsoCarteSociale.

Règle: 1 carte par personne par mois maximum.
Pour chaque groupe de doublons (même carte_sociale, même mois), on garde le plus ancien
et on supprime les autres.

Usage:
    python manage.py clean_duplicate_cartes_sociales --dry-run  # Prévisualisation
    python manage.py clean_duplicate_cartes_sociales            # Exécution réelle
"""

from django.core.management.base import BaseCommand
from django.db.models import Count
from apps.billing.models import ConsoCarteSociale
from collections import defaultdict


class Command(BaseCommand):
    help = 'Nettoie les doublons dans ConsoCarteSociale (1 carte par personne par mois maximum)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Prévisualisation sans suppression réelle',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING('[MODE DRY-RUN] Aucune suppression ne sera effectuée'))
        else:
            self.stdout.write(self.style.WARNING('[MODE RÉEL] Les doublons seront supprimés'))

        self.stdout.write('')
        self.stdout.write('Recherche des doublons...')

        # Récupérer toutes les consommations
        all_consos = ConsoCarteSociale.objects.select_related('carte_sociale').exclude(date__isnull=True)

        null_date_count = ConsoCarteSociale.objects.filter(date__isnull=True).count()
        if null_date_count > 0:
            self.stdout.write(self.style.WARNING(
                f'{null_date_count} enregistrement(s) avec date NULL ignore(s)'
            ))
            self.stdout.write('')

        # Grouper par (carte_sociale_id, année, mois)
        groups = defaultdict(list)
        for conso in all_consos:
            key = (conso.carte_sociale_id, conso.date.year, conso.date.month)
            groups[key].append(conso)

        # Trouver les groupes avec doublons
        duplicates_found = 0
        records_to_delete = 0
        deleted_count = 0

        for key, consos_list in groups.items():
            if len(consos_list) > 1:
                duplicates_found += 1
                carte_sociale_id, year, month = key

                # Trier par date (le plus ancien en premier)
                consos_list.sort(key=lambda x: x.date)

                # Garder le premier (le plus ancien), supprimer les autres
                to_keep = consos_list[0]
                to_delete = consos_list[1:]

                records_to_delete += len(to_delete)

                self.stdout.write(
                    f'\n[DOUBLON TROUVÉ] Carte: {to_keep.carte_sociale.nom_beneficiaire} '
                    f'({month:02d}/{year})'
                )
                self.stdout.write(f'  → Garder: {to_keep.date.strftime("%d/%m/%Y")} (ID: {to_keep.id})')

                for conso_dup in to_delete:
                    self.stdout.write(
                        f'  → Supprimer: {conso_dup.date.strftime("%d/%m/%Y")} (ID: {conso_dup.id})'
                    )

                    if not dry_run:
                        conso_dup.delete()
                        deleted_count += 1

        # Résumé
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(self.style.SUCCESS('RÉSUMÉ'))
        self.stdout.write(self.style.SUCCESS('=' * 60))
        self.stdout.write(f'Groupes de doublons trouvés: {duplicates_found}')
        self.stdout.write(f'Enregistrements à supprimer: {records_to_delete}')

        if dry_run:
            self.stdout.write(self.style.WARNING(
                '\n[DRY-RUN] Aucune suppression effectuée. '
                'Exécutez sans --dry-run pour supprimer réellement.'
            ))
        else:
            self.stdout.write(self.style.SUCCESS(f'\n✓ {deleted_count} enregistrement(s) supprimé(s)'))
            self.stdout.write(self.style.SUCCESS('Nettoyage terminé avec succès!'))
