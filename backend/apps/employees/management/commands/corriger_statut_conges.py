"""
Script pour corriger le statut des congés migrés qui sont déjà passés
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
import pytz

from apps.employees.models_conges import DemandeConge


class Command(BaseCommand):
    help = 'Corrige le statut des congés passés (inscrite_planning -> validee_directeur)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simule le traitement sans enregistrer en base',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        self.stdout.write(self.style.WARNING('=' * 80))
        self.stdout.write(self.style.WARNING('CORRECTION DU STATUT DES CONGES PASSES'))
        self.stdout.write(self.style.WARNING('=' * 80))

        if dry_run:
            self.stdout.write(self.style.WARNING('MODE SIMULATION (--dry-run) - Aucune modification en base'))

        # Timezone Madagascar
        tz_madagascar = pytz.timezone('Indian/Antananarivo')
        aujourd_hui = timezone.now().astimezone(tz_madagascar).date()

        # Récupérer les congés passés avec statut "inscrite_planning"
        conges_a_corriger = DemandeConge.objects.filter(
            statut='inscrite_planning',
            date_fin__lt=aujourd_hui,
            motif__icontains='Migré depuis Planning'  # Uniquement les congés migrés
        ).select_related('employe')

        nb_total = conges_a_corriger.count()
        self.stdout.write(f"\n{nb_total} conge(s) a corriger\n")

        if nb_total == 0:
            self.stdout.write(self.style.WARNING('Aucun conge a corriger'))
            return

        # Afficher quelques exemples
        self.stdout.write("Exemples de conges a corriger:")
        for conge in conges_a_corriger[:5]:
            self.stdout.write(f"  * {conge.employe.nom_affichage}: {conge.date_debut} -> {conge.date_fin}")
        if nb_total > 5:
            self.stdout.write(f"  ... et {nb_total - 5} autre(s)\n")

        if not dry_run:
            # Mettre à jour le statut
            nb_mis_a_jour = conges_a_corriger.update(statut='validee_directeur')

            self.stdout.write('\n')
            self.stdout.write(self.style.SUCCESS(f'{nb_mis_a_jour} conge(s) mis a jour'))
            self.stdout.write(self.style.SUCCESS(f'Statut change: inscrite_planning -> validee_directeur'))
        else:
            self.stdout.write('\n' + self.style.WARNING('MODE SIMULATION - Aucune modification en base'))
            self.stdout.write(self.style.WARNING(f'{nb_total} conge(s) seraient mis a jour'))

        self.stdout.write('\n' + self.style.WARNING('=' * 80))
        self.stdout.write(self.style.WARNING('Note: Les dates de validation sont deja renseignees'))
        self.stdout.write(self.style.WARNING('Le statut "validee_directeur" indique que le conge a ete approuve'))
        self.stdout.write(self.style.WARNING('=' * 80))
