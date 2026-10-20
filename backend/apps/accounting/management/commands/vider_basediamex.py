"""
Commande Django pour vider la table BaseDiameX avant un réimport complet
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.accounting.models import BaseDiameX


class Command(BaseCommand):
    help = 'Vide la table BaseDiameX (toutes les entrées ou par fichier source)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fichier',
            type=str,
            help='Nom du fichier source à vider (si omis, vide toute la table)'
        )
        parser.add_argument(
            '--confirmer',
            action='store_true',
            help='Confirmer la suppression sans demander (pour scripts automatiques)'
        )

    def handle(self, *args, **options):
        fichier = options.get('fichier')
        auto_confirm = options.get('confirmer', False)

        self.stdout.write(self.style.WARNING('\n=== VIDAGE TABLE BASEDIAMEX ===\n'))

        # Statistiques AVANT suppression
        if fichier:
            queryset = BaseDiameX.objects.filter(fichier_source=fichier)
            self.stdout.write(f"Fichier cible: {fichier}")
        else:
            queryset = BaseDiameX.objects.all()
            self.stdout.write("Cible: TOUTE LA TABLE")

        total_avant = queryset.count()
        self.stdout.write(f"\nNombre d'entrées à supprimer: {total_avant:,}\n")

        if total_avant == 0:
            self.stdout.write(self.style.WARNING("Aucune entrée à supprimer."))
            return

        # Afficher détails par fichier
        if not fichier:
            self.stdout.write("\nRépartition par fichier source:")
            fichiers = BaseDiameX.objects.values('fichier_source').distinct()
            for f in fichiers:
                count = BaseDiameX.objects.filter(fichier_source=f['fichier_source']).count()
                self.stdout.write(f"  - {f['fichier_source']}: {count:,} entrées")

        # Confirmation
        if not auto_confirm:
            self.stdout.write(self.style.ERROR(
                f"\n[ATTENTION] Cette action est IRREVERSIBLE!"
            ))
            self.stdout.write(self.style.WARNING(
                "Assurez-vous d'avoir une sauvegarde de la base de données avant de continuer."
            ))

            confirmation = input("\nTaper 'OUI' en majuscules pour confirmer la suppression: ")

            if confirmation != 'OUI':
                self.stdout.write(self.style.WARNING("\nSuppression annulée."))
                return

        # Suppression avec transaction atomique
        self.stdout.write(f"\n[PROGRESS] Suppression en cours...")

        try:
            with transaction.atomic():
                nb_supprimes = queryset.delete()[0]

            self.stdout.write(self.style.SUCCESS(
                f"\n[OK] {nb_supprimes:,} entrée(s) supprimée(s) avec succès.\n"
            ))

            # Statistiques APRÈS suppression
            total_apres = BaseDiameX.objects.count()
            self.stdout.write(f"Entrées restantes dans BaseDiameX: {total_apres:,}")

            if not fichier and total_apres == 0:
                self.stdout.write(self.style.SUCCESS(
                    "\n[OK] La table BaseDiameX est maintenant complètement vide."
                ))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n[ERROR] Erreur lors de la suppression: {str(e)}"))
            return

        self.stdout.write(self.style.SUCCESS('\n=== VIDAGE TERMINÉ ==='))
