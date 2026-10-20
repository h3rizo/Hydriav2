import csv
from decimal import Decimal

import networkx as nx
from django.core.management.base import BaseCommand
from django.db import transaction
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree

from apps.geography.models import Village
from apps.geography.models_routes import TronconRoute, VillageAccesRoute
from apps.geography.services.reseau_routier import haversine_m

# Emprise approximative de Madagascar : hors de ce cadre, le GPS du village est suspect.
LON_MIN, LON_MAX, LAT_MIN, LAT_MAX = 43.0, 51.0, -26.0, -11.5


class Command(BaseCommand):
    help = "Rattache chaque village (avec GPS) au tronçon de route le plus proche et liste ceux à compléter."

    def add_arguments(self, parser):
        parser.add_argument('--seuil-m', type=float, default=1000,
                            help="Au-delà, le village est jugé à compléter (défaut %(default)s m)")
        parser.add_argument('--csv', default='data/villages_a_completer.csv',
                            help="Fichier d'export des villages à compléter ('' pour désactiver)")

    def handle(self, *args, **opts):
        seuil = opts['seuil_m']
        troncons = list(TronconRoute.objects.all().only('id', 'geometrie', 'noeud_debut_id', 'noeud_fin_id'))
        if not troncons:
            self.stderr.write("[ERROR] Aucun tronçon : lancer d'abord importer_voies.")
            return
        lignes = [LineString(t.geometrie) for t in troncons]
        arbre = STRtree(lignes)

        graphe = nx.Graph()
        graphe.add_edges_from((t.noeud_debut_id, t.noeud_fin_id) for t in troncons)
        principale = max(nx.connected_components(graphe), key=len)

        villages = (Village.objects
                    .exclude(latitude__isnull=True).exclude(longitude__isnull=True)
                    .select_related('fokontany__commune'))
        sans_gps = Village.objects.filter(latitude__isnull=True).count() + \
            Village.objects.filter(longitude__isnull=True, latitude__isnull=False).count()

        acces, a_completer = [], []
        for v in villages:
            lon, lat = float(v.longitude), float(v.latitude)
            commune = v.fokontany.commune.nom_commune if v.fokontany_id and v.fokontany.commune_id else ''
            hors = not (LON_MIN <= lon <= LON_MAX and LAT_MIN <= lat <= LAT_MAX)
            ligne_csv = {'id': v.id, 'village': v.nom_village, 'commune': commune, 'latitude': lat, 'longitude': lon}
            if hors:
                a_completer.append({**ligne_csv, 'distance_m': '', 'raison': 'GPS hors Madagascar'})
                continue
            p = Point(lon, lat)
            idx = int(arbre.nearest(p))
            ligne = lignes[idx]
            fraction = ligne.project(p, normalized=True)
            q = ligne.interpolate(fraction, normalized=True)
            dist = haversine_m(lon, lat, q.x, q.y)
            t = troncons[idx]
            dans_principal = t.noeud_debut_id in principale
            acces.append(VillageAccesRoute(
                village=v, troncon_id=t.id, fraction=fraction, distance_m=dist,
                longitude=Decimal(f"{q.x:.7f}"), latitude=Decimal(f"{q.y:.7f}"),
                reseau_principal=dans_principal,
            ))
            raisons = []
            if dist > seuil:
                raisons.append(f"à plus de {seuil:.0f} m d'une route")
            if not dans_principal:
                raisons.append("route proche isolée du réseau principal")
            if raisons:
                a_completer.append({**ligne_csv, 'distance_m': round(dist), 'raison': ' + '.join(raisons)})

        with transaction.atomic():
            VillageAccesRoute.objects.all().delete()
            VillageAccesRoute.objects.bulk_create(acces, batch_size=1000)

        dists = sorted(a.distance_m for a in acces)
        n = len(dists)
        self.stdout.write(f"[OK] {n} villages rattachés ({sans_gps} sans GPS ignorés).")
        for s in (50, 250, 1000):
            k = sum(1 for d in dists if d <= s)
            self.stdout.write(f"[INFO] <= {s} m : {k} ({100 * k / n:.0f} %)")
        self.stdout.write(f"[INFO] Médiane : {dists[n // 2]:.0f} m | max : {dists[-1] / 1000:.1f} km")
        isoles = sum(1 for a in acces if not a.reseau_principal)
        self.stdout.write(f"[INFO] Villages sur un morceau de réseau isolé : {isoles}")
        self.stdout.write(f"[INFO] À compléter : {len(a_completer)}")

        if opts['csv'] and a_completer:
            a_completer.sort(key=lambda r: (r['distance_m'] == '', r['distance_m']), reverse=True)
            with open(opts['csv'], 'w', newline='', encoding='utf-8-sig') as f:
                w = csv.DictWriter(f, fieldnames=list(a_completer[0].keys()), delimiter=';')
                w.writeheader()
                w.writerows(a_completer)
            self.stdout.write(f"[OK] Export : {opts['csv']}")
