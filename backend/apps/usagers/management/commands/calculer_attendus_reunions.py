"""
Commande de rattrapage : calcule et enregistre les participants attendus par defaut
(cf. ParticipantAttendu / _calculer_attendus_par_defaut dans views_reunions.py) pour les
reunions existantes qui n'en ont encore aucun (creees avant l'ajout de cette fonctionnalite).

Ne touche jamais aux reunions ayant deja au moins un ParticipantAttendu, pour ne pas
ecraser une saisie manuelle.

L'organisation gestionnaire (necessaire pour compter les ouvrages geres) est resolue,
pour chaque reunion, dans cet ordre :
  1. --organisation-id fourni explicitement (applique a toutes les reunions traitees)
  2. l'organisation de l'employe qui a cree la reunion (Reunion.created_by.base.organisation)
Si aucune des deux n'est disponible pour une reunion, elle est ignoree et signalee.

Usage:
    python manage.py calculer_attendus_reunions --dry-run
    python manage.py calculer_attendus_reunions
    python manage.py calculer_attendus_reunions --organisation-id <uuid>
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.organization.models import Organisation
from apps.usagers.models import Reunion
from apps.usagers.views_reunions import _appliquer_attendus_par_defaut, _calculer_attendus_par_defaut


class Command(BaseCommand):
    help = (
        "Calcule et enregistre les participants attendus par defaut pour les reunions "
        "existantes qui n'en ont encore aucun."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help="N'ecrit rien en base, affiche seulement ce qui serait fait.",
        )
        parser.add_argument(
            '--organisation-id',
            default=None,
            help="UUID de l'organisation gestionnaire a utiliser pour toutes les reunions traitees. "
                 "Sans ce parametre, l'organisation du createur de chaque reunion est utilisee.",
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        organisation_id = options['organisation_id']

        gestionnaire_ids_force = None
        if organisation_id:
            if not Organisation.objects.filter(id=organisation_id).exists():
                raise CommandError(f"Organisation introuvable : {organisation_id}")
            gestionnaire_ids_force = [str(organisation_id)]

        reunions_sans_attendus = Reunion.objects.filter(
            attendus__isnull=True
        ).select_related('created_by', 'created_by__base', 'created_by__base__organisation').distinct()

        total = reunions_sans_attendus.count()
        self.stdout.write(f"{total} reunion(s) sans attendus a traiter.")

        nb_traitees = 0
        nb_ignorees = 0

        with transaction.atomic():
            for reunion in reunions_sans_attendus:
                if gestionnaire_ids_force is not None:
                    gestionnaire_ids = gestionnaire_ids_force
                else:
                    employe = reunion.created_by
                    base = getattr(employe, 'base', None)
                    organisation = getattr(base, 'organisation', None)
                    gestionnaire_ids = [str(organisation.id)] if organisation else None

                if not gestionnaire_ids:
                    nb_ignorees += 1
                    self.stdout.write(self.style.WARNING(
                        f"  - Ignoree (organisation introuvable) : {reunion.objet} - {reunion.lieu_affiche} ({reunion.date_reunion})"
                    ))
                    continue

                attendus = _calculer_attendus_par_defaut(reunion, gestionnaire_ids)
                if not attendus:
                    # Type de reunion sans regle par defaut (ex: reunion d'equipe) : rien a creer.
                    continue

                nb_traitees += 1
                detail = ', '.join(f"{k}={v}" for k, v in attendus.items())
                self.stdout.write(f"  + {reunion.objet} - {reunion.lieu_affiche} ({reunion.date_reunion}) : {detail}")

                if not dry_run:
                    _appliquer_attendus_par_defaut(reunion, gestionnaire_ids)

            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS(
            f"\nTermine{' (dry-run, rien ecrit)' if dry_run else ''} : "
            f"{nb_traitees} reunion(s) traitee(s), {nb_ignorees} ignoree(s) (organisation introuvable)."
        ))
