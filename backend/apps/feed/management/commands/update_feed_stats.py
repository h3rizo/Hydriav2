"""
Commande de gestion Django pour forcer la mise à jour des posts de statistiques
dans le fil d'actualité.

Usage:
    python manage.py update_feed_stats
    python manage.py update_feed_stats --type=paiements
    python manage.py update_feed_stats --type=reparations
"""
from django.core.management.base import BaseCommand
from apps.feed.signals import (
    create_or_update_paiement_forfaitaire_post,
    create_or_update_reparation_post
)


class Command(BaseCommand):
    help = 'Met à jour les posts de statistiques dans le fil d\'actualité'

    def add_arguments(self, parser):
        parser.add_argument(
            '--type',
            type=str,
            choices=['paiements', 'reparations', 'all'],
            default='all',
            help='Type de post à mettre à jour (paiements, reparations, ou all)'
        )

    def handle(self, *args, **options):
        post_type = options['type']

        if post_type in ['paiements', 'all']:
            self.stdout.write('Mise à jour du post "Paiements Forfaitaires"...')
            try:
                create_or_update_paiement_forfaitaire_post()
                self.stdout.write(self.style.SUCCESS('[OK] Post "Paiements Forfaitaires" mis à jour avec succès'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'[ERREUR] Mise à jour des paiements: {e}'))

        if post_type in ['reparations', 'all']:
            self.stdout.write('Mise à jour du post "Réparations & Réhabilitations"...')
            try:
                create_or_update_reparation_post()
                self.stdout.write(self.style.SUCCESS('[OK] Post "Réparations & Réhabilitations" mis à jour avec succès'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'[ERREUR] Mise à jour des réparations: {e}'))

        if post_type == 'all':
            self.stdout.write(self.style.SUCCESS('\n[OK] Tous les posts de statistiques ont été mis à jour'))
