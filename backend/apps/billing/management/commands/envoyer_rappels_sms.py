from datetime import datetime

from apps.billing.sms.config import reglage
from django.core.management.base import BaseCommand, CommandError

from datetime import timedelta

from django.utils import timezone

import time

from apps.billing.sms.gateway import envoyer_sms, etat_sms
from apps.billing.sms.rappels import ExecutionEnCours, apercu, executer_rappels, verifier_etats


class Command(BaseCommand):
    help = (
        "Envoie les rappels SMS de paiement (J-3 / J-1) des factures NON pointees. "
        "Mode simulation par defaut (SMS_DRY_RUN=True dans .env)."
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help="Force la simulation meme si SMS_DRY_RUN=False")
        parser.add_argument('--jours', help="Jours avant la date limite, ex: 3,1 (defaut: SMS_RAPPEL_JOURS)")
        parser.add_argument('--telephone-test', help="Envoie tout a CE numero (ex: 0347469964) au lieu des abonnes, "
                            "sans rien journaliser (3 rappels maximum par defaut)")
        parser.add_argument('--limite', type=int, help="Nombre maximum de rappels traites")
        parser.add_argument('--verifier-etats', action='store_true',
                            help="Controle aupres de la passerelle les SMS « envoye » des dernieres 48 h : "
                                 "ceux refuses par le telephone passent en « echec » (a lancer ~10 min apres l'envoi)")
        parser.add_argument('--heures', type=int, default=48, help="Fenetre de --verifier-etats (defaut 48)")
        parser.add_argument('--apercu', action='store_true',
                            help="Diagnostic : abonnes joignables, echeances et dates de test (n'envoie rien)")
        parser.add_argument('--date', help="Date du jour simulee (AAAA-MM-JJ), pour les tests")

    def handle(self, *args, **options):
        today = None
        if options['date']:
            try:
                today = datetime.strptime(options['date'], '%Y-%m-%d').date()
            except ValueError:
                raise CommandError("--date doit etre au format AAAA-MM-JJ")
        jours = [int(x) for x in options['jours'].split(',')] if options['jours'] else None
        if options['verifier_etats']:
            bilan = verifier_etats(options['heures'])
            self.stdout.write(f"[OK] controles={bilan['controles']} passes_en_echec={bilan['echecs']}")
            return
        if options['apercu']:
            self.afficher_apercu(today or timezone.localdate())
            return
        dry_run = True if options['dry_run'] else reglage('SMS_DRY_RUN')

        self.stdout.write(f"[INFO] Rappels SMS - mode {'SIMULATION' if dry_run else 'REEL'}"
                          + (f" - TEST vers {options['telephone_test']} (rien n'est journalise)"
                             if options['telephone_test'] else ''))
        try:
            bilan = executer_rappels(today=today, dry_run=dry_run, jours=jours, envoyer=self.envoyer_verbeux,
                                     telephone_test=options['telephone_test'], limite=options['limite'])
        except ValueError as exc:
            raise CommandError(str(exc))
        except ExecutionEnCours as exc:
            self.stdout.write(f"[WARNING] {exc}")
            return
        self.stdout.write(
            f"[OK] envoyes={bilan['envoyes']} simules={bilan['simules']} "
            f"ignores={bilan['ignores']} echecs={bilan['echecs']}"
        )

    def afficher_apercu(self, today):
        a = apercu(today)
        self.stdout.write(f"[INFO] Apercu au {today:%d/%m/%Y} (aucun SMS envoye)")
        self.stdout.write(f"[DATA] Points d'eau avec telephone (non arretes) : {a['points_avec_telephone']}"
                          f" | numero valide : {a['telephones_valides']}"
                          f" | type avec regle de date (Kiosque/BP/BI volume) : {a['valides_avec_regle_de_date']}")
        self.stdout.write(f"[DATA] Abonnes joignables avec facture(s) non pointee(s) : {a['abonnes_avec_factures']}"
                          f" ({a['factures']} facture(s))")
        if not a['echeances']:
            self.stdout.write("[WARNING] Aucune echeance : aucun rappel ne partirait.")
        for date_limite, nb in a['echeances'][:12]:
            j3, j1 = date_limite - timedelta(days=3), date_limite - timedelta(days=1)
            self.stdout.write(f"[DATA] Echeance {date_limite:%d/%m/%Y} : {nb} abonne(s)"
                              f" -> tester avec --date {j3:%Y-%m-%d} (J-3) ou --date {j1:%Y-%m-%d} (J-1)")

    def envoyer_verbeux(self, telephone, texte, dry_run):
        """Envoie puis affiche le message, son identifiant et l'etat vu par la passerelle."""
        resultat = envoyer_sms(telephone, texte, dry_run)
        self.stdout.write(f"[SMS] vers {telephone} ({len(texte)} car.) : {texte}")
        if not resultat['simule']:
            time.sleep(6)  # laisse le temps au telephone de traiter le message
            self.stdout.write(f"[SMS] id={resultat['id']} etat={etat_sms(resultat['id'])}")
        return resultat
