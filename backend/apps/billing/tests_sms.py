"""Tests des rappels SMS de paiement, sans base de donnees ni reseau."""
from contextlib import nullcontext
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.billing.sms import rappels
from apps.billing.sms.echeances import jour_limite_pour_type, prochaine_date_limite
from apps.billing.sms.gateway import (
    LIMITE_SMS_GSM7, ErreurPasserelle, envoyer_sms, normaliser_numero, vers_gsm7,
)
from apps.billing.sms.messages import construire_messages
from apps.billing.sms.rappels import Abonne, FactureDue, RappelPlan, est_pointee, selectionner_rappels

MVOLA = '034 11 111 11'


def facture(id_, montant, limite, reference='F-2026-014', type_='releve'):
    return FactureDue(type_, id_, reference, Decimal(montant), limite)


def abonne(pid='p1', tel='034 12 345 67', type_nom='Kiosque', idxls='81', nom='RAKOTO Jean'):
    return Abonne(pid, tel, type_nom, idxls, nom)


class NumeroTests(SimpleTestCase):
    def test_formats_valides(self):
        self.assertEqual(normaliser_numero('034 12 345 67'), '+261341234567')
        self.assertEqual(normaliser_numero('+261 32 11 222 33'), '+261321122233')
        self.assertEqual(normaliser_numero('00261341234567'), '+261341234567')
        self.assertEqual(normaliser_numero('261341234567'), '+261341234567')

    def test_numero_sans_zero_initial_frequent_en_base(self):
        self.assertEqual(normaliser_numero('347128573'), '+261347128573')

    def test_numeros_invalides(self):
        for brut in ('0022334455', 'abc', '', None, '0212345678', '12345'):
            self.assertIsNone(normaliser_numero(brut), brut)


class Gsm7Tests(SimpleTestCase):
    def test_accents_et_apostrophes(self):
        self.assertEqual(vers_gsm7('Facture réglée à Ambanja, l’eau'), "Facture reglee a Ambanja, l'eau")
        self.assertEqual(vers_gsm7('“Merci” – à bientôt'), '"Merci" - a bientot')

    def test_caracteres_etendus_retires(self):
        self.assertEqual(vers_gsm7('a[b]{c}~|^€d'), 'abcd')


class EcheanceTests(SimpleTestCase):
    def test_jours_par_type(self):
        self.assertEqual(jour_limite_pour_type('Kiosque'), 5)
        self.assertEqual(jour_limite_pour_type(' kiosque '), 5)
        self.assertEqual(jour_limite_pour_type('BP'), 15)
        self.assertEqual(jour_limite_pour_type('BI volume'), 15)
        self.assertIsNone(jour_limite_pour_type(None))

    def test_prochaine_date_limite(self):
        self.assertEqual(prochaine_date_limite(date(2026, 10, 1), 5), date(2026, 10, 5))
        self.assertEqual(prochaine_date_limite(date(2026, 10, 5), 5), date(2026, 10, 5))
        self.assertEqual(prochaine_date_limite(date(2026, 10, 6), 5), date(2026, 11, 5))
        self.assertEqual(prochaine_date_limite(date(2026, 12, 20), 15), date(2027, 1, 15))


class PointageTests(SimpleTestCase):
    def test_couple_diamex_complet_requis(self):
        self.assertTrue(est_pointee('123', 'BASE'))
        for numero, base in ((None, None), ('', ''), ('  ', 'BASE'), ('123', ''), ('123', None)):
            self.assertFalse(est_pointee(numero, base), (numero, base))


class MessageTests(SimpleTestCase):
    def plan(self, ab=None, courantes=None, anterieures=None):
        return RappelPlan(ab or abonne(), 'J-3', date(2026, 10, 5),
                          courantes or [facture('a', '12500', date(2026, 10, 5))], anterieures or [])

    def test_message_court_tient_en_un_sms(self):
        messages = construire_messages(self.plan(), MVOLA, langue='fr')
        self.assertEqual(len(messages), 1)
        texte = messages[0]
        self.assertLessEqual(len(texte), LIMITE_SMS_GSM7)
        for attendu in ('F-2026-014', '12 500 Ar', '05/10/2026', MVOLA, 'Kiosque81RAKOTOJean'):
            self.assertIn(attendu, texte)

    def test_pire_cas_deux_sms_de_160_caracteres_maximum(self):
        ab = abonne(type_nom='BI volume', idxls='99999',
                    nom='RAKOTOMANANA Andrianaivo Jean Marie Emmanuel Sylvestre')
        courantes = [facture('a', '9999999', date(2026, 10, 5), reference='F-2026-99999-XXXXXXXX')]
        anterieures = [facture(f'o{i}', '9999999', date(2026, 9, 5)) for i in range(3)]
        messages = construire_messages(self.plan(ab, courantes, anterieures), MVOLA, langue='fr')
        self.assertLessEqual(len(messages), 2)
        for texte in messages:
            self.assertLessEqual(len(texte), LIMITE_SMS_GSM7)
            self.assertEqual(texte, vers_gsm7(texte))
        joint = ' '.join(messages)
        self.assertIn(MVOLA, joint)
        self.assertIn('39 999 996 Ar', joint)  # cumul 4 x 9 999 999 Ar

    def test_factures_anterieures_incluses_dans_le_total(self):
        messages = construire_messages(
            self.plan(anterieures=[facture('o', '8000', date(2026, 9, 5), reference='F-2026-002')]), MVOLA, langue='fr')
        joint = ' '.join(messages)
        self.assertIn('1 facture anterieure impayee: 8 000 Ar', joint)
        self.assertIn('TOTAL: 20 500 Ar', joint)


class MessageMalgacheTests(SimpleTestCase):
    def plan(self, ab=None, courantes=None, anterieures=None):
        return RappelPlan(ab or abonne(), 'J-3', date(2026, 10, 5),
                          courantes or [facture('a', '12500', date(2026, 10, 5))], anterieures or [])

    def test_malgache_par_defaut(self):
        texte = ' '.join(construire_messages(self.plan(), MVOLA))
        for attendu in ("Faktiran'ny rano F-2026-014", '12 500 Ar', "alohan'ny 05/10/2026", MVOLA, 'Kiosque81RAKOTOJean'):
            self.assertIn(attendu, texte)
        self.assertNotIn('Facture', texte)

    def test_anterieures_et_repli_du_numero_de_facture(self):
        courantes = [facture('a', '12500', date(2026, 10, 5), reference='mois 09/2026')]
        anterieures = [facture('o', '8000', date(2026, 9, 5), reference='forfait 08/2026')]
        joint = ' '.join(construire_messages(self.plan(courantes=courantes, anterieures=anterieures), MVOLA))
        self.assertIn('volana 09/2026', joint)
        self.assertIn('Trosa taloha: faktira 1 (8 000 Ar)', joint)
        self.assertIn('REHETRA: 20 500 Ar', joint)

    def test_pire_cas_deux_sms_de_160_caracteres_maximum(self):
        ab = abonne(type_nom='BI volume', idxls='99999',
                    nom='RAKOTOMANANA Andrianaivo Jean Marie Emmanuel Sylvestre')
        courantes = [facture('a', '9999999', date(2026, 10, 5), reference='F-2026-99999-XXXXXXXX')]
        anterieures = [facture(f'o{i}', '9999999', date(2026, 9, 5)) for i in range(3)]
        messages = construire_messages(self.plan(ab, courantes, anterieures), MVOLA)
        self.assertLessEqual(len(messages), 2)
        for texte in messages:
            self.assertLessEqual(len(texte), LIMITE_SMS_GSM7)
            self.assertEqual(texte, vers_gsm7(texte))
        self.assertIn(MVOLA, ' '.join(messages))
        self.assertIn('39 999 996 Ar', ' '.join(messages))

    @override_settings(SMS_LANGUE='fr')
    def test_francais_reste_disponible(self):
        self.assertIn('Facture eau', ' '.join(construire_messages(self.plan(), MVOLA)))


class SelectionTests(SimpleTestCase):
    def donnees(self):
        ab = abonne()
        autre = abonne(pid='p2', type_nom='BP')
        return {
            'p1': (ab, [facture('c', '12500', date(2026, 10, 5)),
                        facture('o', '8000', date(2026, 9, 5)),
                        facture('f', '3000', date(2026, 11, 5))]),   # future : jamais incluse
            'p2': (autre, [facture('x', '5000', date(2026, 10, 15))]),
        }

    def test_j3_et_j1_selectionnent_la_bonne_echeance(self):
        plans = selectionner_rappels(self.donnees(), date(2026, 10, 2), [3, 1])
        self.assertEqual([(p.abonne.point_eau_id, p.type_rappel) for p in plans], [('p1', 'J-3')])
        plan = plans[0]
        self.assertEqual([f.id for f in plan.courantes], ['c'])
        self.assertEqual([f.id for f in plan.anterieures], ['o'])
        self.assertEqual(plan.montant_total, Decimal('20500'))
        plans = selectionner_rappels(self.donnees(), date(2026, 10, 4), [3, 1])
        self.assertEqual([p.type_rappel for p in plans], ['J-1'])
        self.assertEqual(selectionner_rappels(self.donnees(), date(2026, 10, 12), [3, 1])[0].abonne.point_eau_id, 'p2')


class FakeStore:
    def __init__(self):
        self.lignes = {}

    def existant(self, pid, echeance, type_rappel, partie):
        return self.lignes.get((pid, echeance, type_rappel, partie))

    def enregistrer(self, existant, plan, partie, telephone, message):
        ligne = existant or SimpleNamespace()
        ligne.__dict__.update(telephone=telephone, message=message, statut='en_attente', gateway_id='', erreur='')
        self.lignes[(plan.abonne.point_eau_id, plan.date_echeance, plan.type_rappel, partie)] = ligne
        return ligne

    def maj(self, ligne, **champs):
        ligne.__dict__.update(champs)


@override_settings(SMS_NUMERO_MVOLA=MVOLA, SMS_DELAI_SECONDES=0, SMS_LANGUE='fr')
class ExecutionTests(SimpleTestCase):
    def setUp(self):
        patcher = patch.object(rappels, 'verrou_execution', lambda: nullcontext())
        patcher.start()
        self.addCleanup(patcher.stop)
        self.store = FakeStore()
        self.envois = []

    def envoyer(self, telephone, texte, dry_run):
        self.envois.append((telephone, texte))
        return {'simule': dry_run, 'id': '' if dry_run else 'gw-1'}

    def lancer(self, donnees, today=date(2026, 10, 2), dry_run=True, reverifier=lambda p: p, envoyer=None):
        return rappels.executer_rappels(
            today=today, dry_run=dry_run, jours=[3, 1], donnees=donnees, store=self.store,
            envoyer=envoyer or self.envoyer, reverifier=reverifier, pause=lambda s: None)

    def donnees(self, tel='034 12 345 67'):
        return {'p1': (abonne(tel=tel), [facture('c', '12500', date(2026, 10, 5))])}

    def test_dry_run_simule_sans_doublon_a_la_deuxieme_execution(self):
        self.assertEqual(self.lancer(self.donnees()), {'envoyes': 0, 'simules': 1, 'ignores': 0, 'echecs': 0})
        bilan = self.lancer(self.donnees())
        self.assertEqual((bilan['simules'], bilan['ignores']), (0, 1))
        self.assertEqual(len(self.store.lignes), 1)

    def test_passage_en_reel_reutilise_la_ligne_simulee(self):
        self.lancer(self.donnees())
        bilan = self.lancer(self.donnees(), dry_run=False)
        self.assertEqual(bilan['envoyes'], 1)
        self.assertEqual(len(self.store.lignes), 1)
        self.assertEqual(next(iter(self.store.lignes.values())).statut, 'envoye')
        self.assertEqual(self.lancer(self.donnees(), dry_run=False)['envoyes'], 0)  # jamais deux fois

    def test_numero_invalide_ignore(self):
        bilan = self.lancer(self.donnees(tel='0022334455'))
        self.assertEqual((bilan['simules'], bilan['ignores']), (0, 1))
        self.assertEqual(self.envois, [])

    def test_facture_pointee_entre_selection_et_envoi_ignoree(self):
        bilan = self.lancer(self.donnees(), reverifier=lambda plan: None)
        self.assertEqual((bilan['simules'], bilan['ignores']), (0, 1))
        self.assertEqual(self.envois, [])
        self.assertEqual(self.store.lignes, {})

    def test_rappel_en_deux_sms_echec_partie_1_garde_la_suite_en_attente(self):
        ab = abonne(type_nom='BI volume', nom='RAKOTOMANANA Andrianaivo Jean Marie Emmanuel Sylvestre')
        donnees = {'p1': (ab, [facture('c', '9999999', date(2026, 10, 5)),
                               facture('o', '9999999', date(2026, 9, 5))])}

        def en_panne(telephone, texte, dry_run):
            raise ErreurPasserelle('HTTP 503')

        bilan = self.lancer(donnees, dry_run=False, envoyer=en_panne)
        self.assertEqual(bilan['echecs'], 1)
        statuts = sorted(l.statut for l in self.store.lignes.values())
        self.assertEqual(statuts, ['echec', 'en_attente'])

    def test_reverification_retire_les_factures_pointees(self):
        plan = RappelPlan(abonne(), 'J-3', date(2026, 10, 5),
                          [facture('c', '12500', date(2026, 10, 5))],
                          [facture('o1', '8000', date(2026, 9, 5)), facture('o2', '4000', date(2026, 8, 5))])
        with patch.object(rappels, 'ids_toujours_non_pointes', return_value={'c', 'o2'}):
            nouveau = rappels.reverifier_plan(plan)
        self.assertEqual([f.id for f in nouveau.anterieures], ['o2'])
        with patch.object(rappels, 'ids_toujours_non_pointes', return_value={'o1'}):
            self.assertIsNone(rappels.reverifier_plan(plan))


class PasserelleTests(SimpleTestCase):
    @override_settings(SMS_DRY_RUN=True)
    def test_dry_run_n_appelle_pas_le_reseau(self):
        with patch('apps.billing.sms.gateway.requests.post') as post:
            self.assertEqual(envoyer_sms('+261341234567', 'Bonjour'), {'simule': True, 'id': ''})
            post.assert_not_called()

    @override_settings(SMS_DRY_RUN=False, SMS_GATEWAY_URL='', SMS_GATEWAY_USER='', SMS_GATEWAY_PASS='')
    def test_reel_sans_configuration_leve_une_erreur(self):
        with self.assertRaises(ErreurPasserelle):
            envoyer_sms('+261341234567', 'Bonjour')


class VueTests(SimpleTestCase):
    """Vues de suivi : controle d'acces, bouton « Lancer », protection contre les doubles executions."""

    def requete(self, admin=True):
        from django.test import RequestFactory
        req = RequestFactory().post('/facturation/sms/lancer/')
        req.user = SimpleNamespace(is_authenticated=True, is_superuser=admin)
        return req

    def setUp(self):
        from apps.billing import views_sms
        self.vues = views_sms
        patcher = patch.object(views_sms, 'messages')
        self.messages = patcher.start()
        self.addCleanup(patcher.stop)

    def test_acces_refuse_a_un_non_administrateur(self):
        with patch.object(self.vues, 'has_admin_compta_access', return_value=False):
            self.assertEqual(self.vues.lancer(self.requete(admin=False)).status_code, 403)
            self.assertEqual(self.vues.historique(self.requete(admin=False)).status_code, 403)

    @override_settings(SMS_DRY_RUN=True)
    def test_lancer_en_simulation_affiche_le_bilan(self):
        bilan = {'envoyes': 0, 'simules': 3, 'ignores': 1, 'echecs': 0}
        with patch.object(self.vues.rappels, 'executer_rappels', return_value=bilan):
            reponse = self.vues.lancer(self.requete())
        self.assertEqual(reponse.status_code, 302)
        self.assertIn('3 simule(s)', self.messages.success.call_args[0][1])

    @override_settings(SMS_DRY_RUN=False, SMS_NUMERO_MVOLA='')
    def test_lancer_reel_sans_numero_mvola_refuse(self):
        with patch.object(self.vues.threading, 'Thread') as thread:
            self.vues.lancer(self.requete())
        thread.assert_not_called()
        self.messages.error.assert_called_once()

    @override_settings(SMS_DRY_RUN=False, SMS_NUMERO_MVOLA=MVOLA)
    def test_lancer_reel_refuse_si_une_execution_est_en_cours(self):
        with patch.object(self.vues.rappels, 'verrou_libre', return_value=False), \
                patch.object(self.vues.threading, 'Thread') as thread:
            self.vues.lancer(self.requete())
        thread.assert_not_called()
        self.messages.warning.assert_called_once()

    @override_settings(SMS_DRY_RUN=False, SMS_NUMERO_MVOLA=MVOLA)
    def test_lancer_reel_demarre_un_thread(self):
        with patch.object(self.vues.rappels, 'verrou_libre', return_value=True), \
                patch.object(self.vues.threading, 'Thread') as thread:
            self.vues.lancer(self.requete())
        thread.return_value.start.assert_called_once()

    def test_relancer_ignore_un_sms_deja_envoye(self):
        ligne = SimpleNamespace(statut='envoye')
        with patch.object(self.vues, 'get_object_or_404', return_value=ligne), \
                patch.object(self.vues.rappels, 'relancer_groupe') as relance:
            self.vues.relancer(self.requete(), pk='x')
        relance.assert_not_called()

    def test_relancer_un_echec_appelle_la_relance(self):
        ligne = SimpleNamespace(statut='echec')
        with patch.object(self.vues, 'get_object_or_404', return_value=ligne), \
                patch.object(self.vues.rappels, 'relancer_groupe', return_value=(True, '2 SMS')) as relance:
            self.vues.relancer(self.requete(), pk='x')
        relance.assert_called_once_with(ligne)
        self.messages.success.assert_called_once()


@override_settings(SMS_NUMERO_MVOLA=MVOLA, SMS_DELAI_SECONDES=0, SMS_LANGUE='fr')
class ModeTestTests(SimpleTestCase):
    def setUp(self):
        patcher = patch.object(rappels, 'verrou_execution', lambda: nullcontext())
        patcher.start()
        self.addCleanup(patcher.stop)
        self.envois = []

    def envoyer(self, telephone, texte, dry_run):
        self.envois.append(telephone)
        return {'simule': dry_run, 'id': ''}

    def donnees(self):
        return {f'p{i}': (abonne(pid=f'p{i}', tel='034 99 999 99'), [facture(f'c{i}', '1000', date(2026, 10, 5))])
                for i in range(5)}

    def lancer(self, **kw):
        return rappels.executer_rappels(today=date(2026, 10, 2), dry_run=True, jours=[3], donnees=self.donnees(),
                                        envoyer=self.envoyer, reverifier=lambda p: p, pause=lambda s: None, **kw)

    def test_les_sms_vont_au_numero_de_test_sans_journal_et_sont_limites(self):
        bilan = self.lancer(telephone_test='0347469964')
        self.assertEqual(bilan['simules'], 3)                       # limite par defaut = 3 rappels
        self.assertEqual(set(self.envois), {'+261347469964'})       # jamais le numero des abonnes
        self.assertEqual(self.lancer(telephone_test='0347469964')['simules'], 3)  # rien journalise : rejouable

    def test_numero_de_test_invalide_refuse(self):
        with self.assertRaises(ValueError):
            self.lancer(telephone_test='123')


class MotifMvolaTests(SimpleTestCase):
    def test_motif_tout_attache_sans_espace(self):
        from apps.billing.sms.messages import motif_mvola
        self.assertEqual(motif_mvola('BI volume', '81', "RAKOTO Jean d'Arc"), "BIvolume81RAKOTOJeand'Arc")
        self.assertEqual(motif_mvola(None, None, 'Rasoa  Florine'), 'RasoaFlorine')

    def test_nom_tronque_quand_le_sms_de_paiement_deborde(self):
        ab = abonne(type_nom='BP', idxls='81', nom='RAKOTOMANANA ' * 12)
        for langue in ('mg', 'fr'):
            messages = construire_messages(RappelPlan(ab, 'J-3', date(2026, 10, 5),
                                                      [facture('a', '12500', date(2026, 10, 5))], []), MVOLA, langue=langue)
            for texte in messages:
                self.assertLessEqual(len(texte), LIMITE_SMS_GSM7)
            paiement = messages[-1]
            self.assertIn('BP81RAKOTOMANANA', paiement)      # type + IDXls conserves, nom tronque
            self.assertNotIn(' RAKOTO', paiement.split('motif:')[-1].split('antony:')[-1].split('.')[0])


class VerifierEtatsTests(SimpleTestCase):
    def ligne(self, gateway_id):
        return SimpleNamespace(statut='envoye', gateway_id=gateway_id, erreur='', save=lambda: None)

    def test_un_sms_refuse_par_le_telephone_passe_en_echec(self):
        refuse, livre, inconnu = self.ligne('a'), self.ligne('b'), self.ligne('c')
        etats = {'a': {'state': 'Failed', 'error': 'Send result: RESULT_NO_DEFAULT_SMS_APP'},
                 'b': {'state': 'Delivered', 'error': ''}, 'c': None}
        with patch('apps.billing.models.SmsLog') as modele, \
                patch.object(rappels, 'etat_sms_detail', side_effect=lambda i: etats[i]):
            modele.objects.filter.return_value.exclude.return_value = [refuse, livre, inconnu]
            bilan = rappels.verifier_etats()
        self.assertEqual(bilan, {'controles': 2, 'echecs': 1})
        self.assertEqual((refuse.statut, livre.statut, inconnu.statut), ('echec', 'envoye', 'envoye'))
        self.assertIn('RESULT_NO_DEFAULT_SMS_APP', refuse.erreur)
