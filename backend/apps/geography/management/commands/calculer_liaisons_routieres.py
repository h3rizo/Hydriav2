from django.core.management.base import BaseCommand

from apps.geography.models import LiaisonVillage
from apps.geography.services import liaisons_routes


class Command(BaseCommand):
    help = ("Calcule le tracé, la distance et la durée par la route de chaque liaison entre villages. "
            "Par défaut: seulement les liaisons jamais calculées ou antérieures à la dernière modification du réseau.")

    def add_arguments(self, parser):
        parser.add_argument('--tout', action='store_true', help="Recalcule toutes les liaisons")
        parser.add_argument('--critere', choices=['temps', 'distance'], default='temps',
                            help="Chemin le plus rapide (défaut) ou le plus court")
        parser.add_argument('--forcer-distances', action='store_true',
                            help="ÉCRASE distance_km et temps_acces_minutes saisis à la main par les valeurs calculées")
        parser.add_argument('--dry-run', action='store_true', help="Calcule et résume sans écrire")

    def handle(self, *args, **opts):
        qs = LiaisonVillage.objects.all() if opts['tout'] else liaisons_routes.liaisons_a_recalculer()
        qs = qs.select_related('village_source', 'village_cible')
        total = qs.count()
        self.stdout.write(f"[INFO] {total} liaison(s) à calculer.")
        if not total:
            return
        if opts['forcer_distances'] and not opts['dry_run']:
            self.stdout.write("[WARNING] --forcer-distances : les distances/temps saisis seront remplacés.")
        stats = liaisons_routes.calculer(
            qs, critere=opts['critere'], forcer_distances=opts['forcer_distances'], dry_run=opts['dry_run'])
        self.stdout.write(
            f"[OK] ok: {stats['ok']} | aucun chemin: {stats['introuvable']} | hors route (pirogue/rivière): {stats['ignore']}"
            + (" (simulation, rien écrit)" if opts['dry_run'] else ""))
        if stats['introuvable']:
            self.stdout.write("[INFO] 'Aucun chemin' : village sans GPS, ou réseau coupé entre les deux. "
                              "Voir /geography/routes/coupures/ et /geography/routes/jonctions/.")
