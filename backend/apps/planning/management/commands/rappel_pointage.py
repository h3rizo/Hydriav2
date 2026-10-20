from django.core.management.base import BaseCommand

from apps.planning.tasks import envoyer_rappels_creneau


class Command(BaseCommand):
    help = "Envoie les rappels de pointage GPS d'un créneau (alternative cron à Celery Beat)."

    def add_arguments(self, parser):
        parser.add_argument('creneau', choices=['matin', 'aprem', 'nuit'])

    def handle(self, *args, **options):
        resultat = envoyer_rappels_creneau(options['creneau'])
        self.stdout.write(f"[OK] {resultat}")
