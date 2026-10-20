from django.core.management.base import BaseCommand, CommandError

from apps.messaging.relance_mailer_combine import envoyer_toutes_les_relances_combinees


class Command(BaseCommand):
    help = (
        "Envoie le recapitulatif combine (paiements non pointes + reparations "
        "echues) a chaque destinataire concerne (responsable direct d'ouvrage "
        "ou superieur hierarchique), regroupe par ouvrage, un seul email par "
        "destinataire quel que soit le nombre de situations le concernant."
    )

    def add_arguments(self, parser):
        parser.add_argument('--mois', type=int, help='Mois cible pour les paiements (1-12), defaut: mois precedent')
        parser.add_argument('--annee', type=int, help='Annee cible pour les paiements, defaut: annee du mois precedent')
        parser.add_argument(
            '--dry-run', action='store_true',
            help="Calcule et affiche le resume sans envoyer ni ecrire de tracabilite",
        )
        parser.add_argument(
            '--test-email', type=str, default=None,
            help="Redirige TOUS les envois vers cette adresse unique (bandeau TEST inclus)",
        )

    def handle(self, *args, **options):
        annee, mois = options.get('annee'), options.get('mois')
        if (annee is None) != (mois is None):
            raise CommandError("--mois et --annee doivent etre fournis ensemble ou omis ensemble.")

        est_test = bool(options.get('test_email'))
        resultat = envoyer_toutes_les_relances_combinees(
            annee=annee, mois=mois,
            dry_run=options['dry_run'],
            est_test=est_test,
            email_test_override=options.get('test_email'),
        )

        self.stdout.write(f"Periode cible paiements : {resultat['mois']:02d}/{resultat['annee']}")
        self.stdout.write(f"Date de reference reparations : {resultat['date_reference_reparations']}")
        if options['dry_run']:
            self.stdout.write(self.style.WARNING("Mode --dry-run : aucun email envoye, aucune trace ecrite."))
        if est_test:
            self.stdout.write(self.style.WARNING(f"Mode test : tous les envois rediriges vers {options['test_email']}"))

        self.stdout.write(f"Destinataires concernes : {resultat['nb_destinataires']}")
        self.stdout.write(f"Reparations echues distinctes : {resultat['nb_reparations_echues']}")
        if not options['dry_run']:
            self.stdout.write(self.style.SUCCESS(f"Envoyes : {resultat['nb_envoyes']}"))
            if resultat['nb_echecs']:
                self.stdout.write(self.style.ERROR(f"Echecs : {resultat['nb_echecs']}"))
            if resultat['nb_email_manquant']:
                self.stdout.write(self.style.WARNING(f"Email manquant : {resultat['nb_email_manquant']}"))

        if resultat['factures_sans_responsable']:
            self.stdout.write(
                self.style.WARNING(
                    f"Factures sans responsable identifiable (exclues) : {resultat['factures_sans_responsable']}"
                )
            )
        if resultat['reparations_sans_responsable']:
            self.stdout.write(
                self.style.WARNING(
                    f"Reparations sans employe assigne (exclues) : {resultat['reparations_sans_responsable']}"
                )
            )

        if resultat['nb_destinataires'] == 0:
            self.stdout.write("Aucune situation a relancer : aucun email n'aurait ete envoye.")
        elif options['dry_run']:
            for detail in resultat['details']:
                employe = detail['employe']
                nom = employe.surnom or employe.nom_employe
                self.stdout.write(
                    f"  - {nom} [{detail['type_destinataire']}] : "
                    f"{detail['nb_points_eau']} point(s) d'eau, {detail['nb_factures']} facture(s), "
                    f"{detail['nb_reparations']} reparation(s)"
                    + (f", {detail['montant_total']} Ar" if detail['montant_total'] is not None else "")
                )
