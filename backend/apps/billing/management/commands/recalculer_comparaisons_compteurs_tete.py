from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.billing.models import CompteurTete
from apps.organization.views_compteurs_releves import _resequence_releves


class Command(BaseCommand):
    help = (
        "Recalcule les volumes aval et les ecarts des compteurs de tete "
        "sur les memes periodes de releve."
    )

    def add_arguments(self, parser):
        parser.add_argument('--compteur', dest='compteur_id')
        parser.add_argument('--ouvrage', dest='ouvrage_id')
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--fail-fast', action='store_true')

    def handle(self, *args, **options):
        compteurs = CompteurTete.objects.filter(
            releves_compteur_tete__isnull=False,
        ).select_related('ouvrage').distinct().order_by(
            'ouvrage__nom_ouvrage',
            'numerocompteur',
        )

        if options.get('compteur_id'):
            compteurs = compteurs.filter(id=options['compteur_id'])
        if options.get('ouvrage_id'):
            compteurs = compteurs.filter(ouvrage_id=options['ouvrage_id'])

        total = compteurs.count()
        if total == 0:
            raise CommandError('Aucun compteur de tete avec releves ne correspond aux filtres.')

        success_count = 0
        error_count = 0
        for compteur in compteurs:
            try:
                with transaction.atomic():
                    _resequence_releves(compteur)
                    if options.get('dry_run'):
                        transaction.set_rollback(True)
                success_count += 1
                self.stdout.write(
                    f"OK {compteur.numerocompteur} - "
                    f"{getattr(compteur.ouvrage, 'nom_ouvrage', '')}"
                )
            except Exception as exc:
                error_count += 1
                self.stderr.write(
                    self.style.ERROR(f"ERREUR {compteur.numerocompteur}: {exc}")
                )
                if options.get('fail_fast'):
                    raise CommandError(str(exc)) from exc

        mode = 'Simulation' if options.get('dry_run') else 'Recalcul'
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode} termine: {success_count}/{total} compteur(s), "
                f"{error_count} erreur(s)."
            )
        )
