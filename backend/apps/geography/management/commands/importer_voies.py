from decimal import Decimal

import networkx as nx
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.geography.models_routes import NoeudRoute, TronconRoute
from apps.geography.services.reseau_routier import construire_reseau
from apps.geography.services.voies_config import TOLERANCE_RACCORD_M


class Command(BaseCommand):
    help = (
        "Importe un shapefile de voies : coupe aux intersections, raccorde les bouts "
        "isolés proches et crée TronconRoute / NoeudRoute. Les tracés manuels sont conservés."
    )

    def add_arguments(self, parser):
        parser.add_argument('shapefile', help="Chemin du .shp (avec ou sans extension)")
        parser.add_argument('--tolerance-m', type=float, default=TOLERANCE_RACCORD_M,
                            help="Distance max (m) pour raccorder un bout isolé (défaut %(default)s)")
        parser.add_argument('--dry-run', action='store_true', help="Calcule et affiche les stats sans écrire")

    def handle(self, *args, **opts):
        chemin = opts['shapefile']
        if chemin.lower().endswith('.shp'):
            chemin = chemin[:-4]
        try:
            troncons, stats = construire_reseau(chemin, opts['tolerance_m'])
        except Exception as exc:  # fichier absent, illisible...
            raise CommandError(f"Lecture impossible : {exc}")

        def cle(pt):
            return (round(pt[0], 7), round(pt[1], 7))

        graphe = nx.Graph()
        for t in troncons:
            graphe.add_edge(cle(t['coords'][0]), cle(t['coords'][-1]))
        composantes = sorted((len(c) for c in nx.connected_components(graphe)), reverse=True)

        self.stdout.write(f"[INFO] Lignes lues: {stats['lignes_lues']} (formes ignorées: {stats['formes_ignorees']})")
        self.stdout.write(f"[INFO] Tronçons: {stats['troncons']} dont {stats['raccords']} raccords | {stats['km_total']:.0f} km")
        self.stdout.write(f"[INFO] Noeuds: {graphe.number_of_nodes()} | composantes: {len(composantes)} "
                          f"| plus grande: {composantes[0]} noeuds ({100 * composantes[0] / graphe.number_of_nodes():.0f} %)")

        if opts['dry_run']:
            self.stdout.write("[OK] Dry-run : rien n'a été écrit.")
            return

        with transaction.atomic():
            TronconRoute.objects.filter(source__in=['shapefile', 'raccord']).delete()
            NoeudRoute.objects.filter(troncons_debut__isnull=True, troncons_fin__isnull=True).delete()

            existants = {(n.longitude, n.latitude): n for n in NoeudRoute.objects.all()}
            nouveaux = {}
            for k in graphe.nodes:
                d = (Decimal(f"{k[0]:.7f}"), Decimal(f"{k[1]:.7f}"))
                if d not in existants:
                    nouveaux[k] = NoeudRoute(longitude=d[0], latitude=d[1])
            NoeudRoute.objects.bulk_create(nouveaux.values(), batch_size=2000)
            index = {(n.longitude, n.latitude): n for n in NoeudRoute.objects.all()}

            def noeud(k):
                return index[(Decimal(f"{k[0]:.7f}"), Decimal(f"{k[1]:.7f}"))]

            TronconRoute.objects.bulk_create([
                TronconRoute(
                    nom=t['nom'], type_voie=t['type_voie'], categorie=t['categorie'],
                    interet=t['interet'], commune_nom=t['commune_nom'], source=t['source'],
                    noeud_debut=noeud(cle(t['coords'][0])), noeud_fin=noeud(cle(t['coords'][-1])),
                    geometrie=[list(c) for c in t['coords']], longueur_m=t['longueur_m'],
                ) for t in troncons
            ], batch_size=2000)

        self.stdout.write(self.style.SUCCESS(f"[OK] {len(troncons)} tronçons importés."))
