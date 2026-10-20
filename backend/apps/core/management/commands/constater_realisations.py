"""Constat des réalisations (pointages, activités terminées) pour les compteurs « fait » du widget.

À lancer par cron sur le VPS (Celery Beat est désactivé), par exemple toutes les heures :
    0 * * * * cd /home/soakoja/hydria/backend && ../venv/bin/python manage.py constater_realisations
L'API du widget fait aussi un constat à la demande, au plus toutes les 5 minutes.
"""
from django.core.management.base import BaseCommand

from apps.core.widget_realisations import constater


class Command(BaseCommand):
    help = "Enregistre les nouvelles réalisations constatées pour le widget Hydria."

    def handle(self, *args, **options):
        for categorie, resume in constater().items():
            etat = ' (premier constat : existant marqué initial)' if resume['initial'] else ''
            self.stdout.write(
                f"[OK] {categorie} : {resume['nouveaux']} nouveau(x), {resume['modifies']} modifié(s){etat}"
            )
