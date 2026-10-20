from django.core.management.base import BaseCommand

from apps.billing.tarifs_forfaitaires import appliquer_tarifs_forfaitaires


class Command(BaseCommand):
    help = (
        "Recalcule PointEau.tarifforfaitaire (montant) = tarif plein du type en vigueur x "
        "pourcentage. À planifier chaque jour : un nouveau tarif peut entrer en vigueur à une "
        "date future."
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help="Compte sans modifier")

    def handle(self, *args, **options):
        n = appliquer_tarifs_forfaitaires(dry_run=options['dry_run'])
        verbe = 'à modifier' if options['dry_run'] else 'mis à jour'
        self.stdout.write(f"[OK] {n} point(s) d'eau {verbe}")
