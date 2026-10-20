"""
Commande de diagnostic pour vérifier les incohérences entre fichiers Access et BaseDiameX
"""
from django.core.management.base import BaseCommand
from apps.accounting.models import BaseDiameX
from django.db.models import Count
import os


class Command(BaseCommand):
    help = 'Diagnostic des imports DiameX - Vérifier les doublons et fichiers sources'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fichier',
            type=str,
            help='Nom du fichier source à analyser (optionnel)'
        )
        parser.add_argument(
            '--id',
            type=int,
            help='ID Access à rechercher'
        )

    def handle(self, *args, **options):
        fichier = options.get('fichier')
        id_access = options.get('id')

        self.stdout.write(self.style.SUCCESS('=== DIAGNOSTIC IMPORTS DIAMEX ===\n'))

        # Statistiques générales
        total = BaseDiameX.objects.count()
        self.stdout.write(f"Total d'entrées dans BaseDiameX: {total:,}")

        # Fichiers sources distincts
        fichiers = BaseDiameX.objects.values('fichier_source').distinct()
        self.stdout.write(f"\nNombre de fichiers sources distincts: {fichiers.count()}")

        for f in fichiers:
            count = BaseDiameX.objects.filter(fichier_source=f['fichier_source']).count()
            self.stdout.write(f"  - {f['fichier_source']}: {count:,} entrées")

        # Recherche par ID si spécifié
        if id_access:
            self.stdout.write(f"\n=== RECHERCHE ID ACCESS = {id_access} ===")
            entries = BaseDiameX.objects.filter(id_access=id_access)

            if not entries.exists():
                self.stdout.write(self.style.WARNING(f"Aucune entrée trouvée avec ID={id_access}"))
            else:
                self.stdout.write(f"Trouvé {entries.count()} entrée(s):")
                for entry in entries:
                    self.stdout.write(f"\n  Fichier source: {entry.fichier_source}")
                    self.stdout.write(f"  Description: {entry.description}")
                    self.stdout.write(f"  Date: {entry.date_m}")
                    self.stdout.write(f"  Montant Out: {entry.montant_out}")
                    self.stdout.write(f"  Compte: {entry.compte_code}")

        # Recherche par fichier si spécifié
        if fichier:
            self.stdout.write(f"\n=== ANALYSE FICHIER: {fichier} ===")
            entries = BaseDiameX.objects.filter(fichier_source__icontains=fichier)

            if not entries.exists():
                self.stdout.write(self.style.WARNING(f"Aucune entrée trouvée pour le fichier '{fichier}'"))
            else:
                count = entries.count()
                self.stdout.write(f"Total: {count:,} entrées")

                # IDs min et max
                ids = entries.values_list('id_access', flat=True).order_by('id_access')
                self.stdout.write(f"ID Access min: {ids.first()}")
                self.stdout.write(f"ID Access max: {ids.last()}")

                # Exemple d'entrées
                self.stdout.write("\nPremières 5 entrées:")
                for entry in entries[:5]:
                    self.stdout.write(f"  ID={entry.id_access}: {entry.description[:60]}")

        # Détecter les doublons potentiels (même ID dans plusieurs fichiers)
        self.stdout.write("\n=== RECHERCHE DE DOUBLONS (même ID Access, fichiers différents) ===")

        doublons = BaseDiameX.objects.values('id_access').annotate(
            count=Count('id'),
            fichiers_count=Count('fichier_source', distinct=True)
        ).filter(fichiers_count__gt=1).order_by('-count')[:20]

        if doublons:
            self.stdout.write(self.style.WARNING(f"Trouvé {len(doublons)} ID Access présents dans plusieurs fichiers:"))
            for doublon in doublons:
                entries = BaseDiameX.objects.filter(id_access=doublon['id_access'])
                fichiers = entries.values_list('fichier_source', flat=True).distinct()
                self.stdout.write(f"\n  ID={doublon['id_access']} ({doublon['count']} entrées):")
                for f in fichiers:
                    self.stdout.write(f"    - {f}")
        else:
            self.stdout.write(self.style.SUCCESS("Aucun doublon détecté"))

        self.stdout.write(self.style.SUCCESS('\n=== DIAGNOSTIC TERMINÉ ==='))
