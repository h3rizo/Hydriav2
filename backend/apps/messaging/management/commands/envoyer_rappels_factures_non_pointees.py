from django.core.management.base import BaseCommand, CommandError

from apps.messaging.monthly_billing_mailer import envoyer_toutes_les_relances


class Command(BaseCommand):
    help = (
        "Envoie le recapitulatif mensuel des factures non pointees a chaque "
        "responsable d'ouvrage actif (EmployeOuvrages.recevoir_alertes=True)."
    )

    def add_arguments(self, parser):
        parser.add_argument('--mois', type=int, help='Mois cible (1-12), defaut: mois precedent')
        parser.add_argument('--annee', type=int, help='Annee cible, defaut: annee du mois precedent')
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
        resultat = envoyer_toutes_les_relances(
            annee=annee, mois=mois,
            dry_run=options['dry_run'],
            est_test=est_test,
            email_test_override=options.get('test_email'),
        )

        self.stdout.write(f"Periode cible : {resultat['mois']:02d}/{resultat['annee']}")
        if options['dry_run']:
            self.stdout.write(self.style.WARNING("Mode --dry-run : aucun email envoye, aucune trace ecrite."))
        if est_test:
            self.stdout.write(self.style.WARNING(f"Mode test : tous les envois rediriges vers {options['test_email']}"))

        self.stdout.write(f"Responsables concernes : {resultat['nb_responsables']}")
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

        if resultat['nb_responsables'] == 0:
            self.stdout.write("Aucune facture non pointee ce mois-ci : aucun email n'aurait ete envoye.")
        elif options['dry_run']:
            for detail in resultat['details']:
                employe = detail['employe']
                nom = employe.surnom or employe.nom_employe
                self.stdout.write(
                    f"  - {nom} : {detail['nb_points_eau']} point(s) d'eau, "
                    f"{detail['nb_factures']} facture(s)"
                    + (f", {detail['montant_total']} Ar" if detail['montant_total'] is not None else "")
                )
