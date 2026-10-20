from django.core.management.base import BaseCommand

from apps.geography.models_routes import TronconRoute
from apps.geography.services import jonctions


class Command(BaseCommand):
    help = ("Relie automatiquement les routes qui devraient se toucher (écart <= --tol-m) mais restent "
            "séparées. Les cas plus éloignés sont à valider sur la page /geography/routes/jonctions/.")

    def add_arguments(self, parser):
        parser.add_argument('--tol-m', type=float, default=25.0, help="Écart max réparé automatiquement (défaut %(default)s m)")
        parser.add_argument('--ecart-m', type=float, default=3000.0,
                            help="Une jonction n'est utile que si le trajet actuel entre les deux points dépasse ce seuil (défaut %(default)s m)")
        parser.add_argument('--dry-run', action='store_true', help="Compte sans écrire")

    def handle(self, *args, **opts):
        avant = TronconRoute.objects.count()
        n = jonctions.nettoyer_auto(opts['tol_m'], opts['ecart_m'], dry_run=opts['dry_run'],
                                    log=lambda m: self.stdout.write(m))
        if opts['dry_run']:
            self.stdout.write(f"[OK] Simulation : {n} jonction(s) seraient créées.")
        else:
            apres = TronconRoute.objects.count()
            self.stdout.write(self.style.SUCCESS(f"[OK] {n} jonction(s) créées ({apres - avant} tronçons ajoutés, découpes comprises)."))
            self.stdout.write("[INFO] Relancer ensuite: rattacher_villages (distances et réseau principal à jour).")
