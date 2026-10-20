"""Importe les contours administratifs (région, district, commune, fokontany) depuis un shapefile ou un JSON préparé.

    python manage.py importer_contours data/Communes.shp                          # niveau déduit du nom (pyproj requis)
    python manage.py importer_contours data/fokontany.shp --ecrire-json fkt.json  # prépare un fichier léger pour le serveur
    python manage.py importer_contours fkt.json                                   # import sans pyproj
"""
import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.geography.models_contours import ContourAdmin
from apps.geography.services import contours_communes as svc


class Command(BaseCommand):
    help = "Importe les contours administratifs d'un niveau (shapefile ou JSON préparé) et les rattache aux objets de la base."

    def add_arguments(self, parser):
        parser.add_argument('chemin', help="Shapefile (Region, District, Communes, fokontany) ou fichier .json préparé")
        parser.add_argument('--niveau', choices=sorted(svc.TOLERANCES), help="Niveau, si le nom du fichier ne le dit pas")
        parser.add_argument('--ecrire-json', metavar='FICHIER', help="Écrit les enregistrements préparés dans un JSON, sans toucher à la base")
        parser.add_argument('--dry-run', action='store_true', help="Lit et compte, n'écrit rien")

    def handle(self, *args, chemin, niveau=None, ecrire_json=None, dry_run=False, **options):
        try:
            niveau, enregistrements, ignorees = svc.lire_source(chemin, niveau)
        except FileNotFoundError:
            raise CommandError(f"Fichier introuvable : {chemin}")
        except ValueError as exc:
            raise CommandError(str(exc))
        self.stdout.write(f"{len(enregistrements)} entités « {niveau} » lues" + (f" ({ignorees} formes vides ignorées)." if ignorees else "."))

        if ecrire_json:
            with open(ecrire_json, 'w', encoding='utf-8') as f:
                json.dump({'niveau': niveau, 'enregistrements': enregistrements}, f, ensure_ascii=False, separators=(',', ':'))
            self.stdout.write(self.style.SUCCESS(f"Fichier préparé : {ecrire_json}"))
            return
        if dry_run:
            self.stdout.write("Dry-run : rien n'est écrit.")
            return

        champs = [f.name for f in ContourAdmin._meta.fields if f.name not in ('id', 'niveau', 'cle', 'objet_id', 'updated_at')]
        creations = modifications = 0
        with transaction.atomic():
            existants = {k.cle: k for k in ContourAdmin.objects.filter(niveau=niveau)}
            nouveaux, a_modifier = [], []
            for e in enregistrements:
                valeurs = {c: e[c] for c in champs if c in e}
                if e['cle'] in existants:
                    k = existants[e['cle']]
                    for champ, valeur in valeurs.items():
                        setattr(k, champ, valeur)
                    a_modifier.append(k)
                else:
                    nouveaux.append(ContourAdmin(niveau=niveau, cle=e['cle'], **valeurs))
            ContourAdmin.objects.bulk_create(nouveaux, batch_size=200)
            if a_modifier:
                ContourAdmin.objects.bulk_update(a_modifier, champs, batch_size=200)
            creations, modifications = len(nouveaux), len(a_modifier)
            bilan = svc.rattacher(niveau, ContourAdmin.objects.filter(niveau=niveau))
        self.stdout.write(self.style.SUCCESS(
            f"{creations} créées, {modifications} mises à jour. Rattachées à la base : {bilan['rattaches']} · "
            f"ambiguës : {bilan['ambigus']} · sans correspondance : {bilan['sans_correspondance']}."))
