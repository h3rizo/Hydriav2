from datetime import date

from django.test import SimpleTestCase, TestCase

from apps.accounting import pointage_export as pe


class ParseDescriptionTests(SimpleTestCase):
    def test_volume(self):
        self.assertEqual(
            pe.parse_volume_description('Paiement au volume "Ambanja BP" 05/02/2026 (1;2;3)'),
            ('Ambanja BP', '05/02/2026'))
        self.assertEqual(
            pe.parse_volume_description('Paiement au volume "Soakoja AEPG" 31/12/2025 (8 relevés)'),
            ('Soakoja AEPG', '31/12/2025'))

    def test_volume_autres_descriptions(self):
        for text in ('', None, 'Paiement forfaitaire_U_1_5000_Ambanja BP', 'Paiement au volume Ambanja'):
            self.assertIsNone(pe.parse_volume_description(text))

    def test_abonne_bp(self):
        self.assertEqual(pe.parse_bp_subscriber('Paiement demande BP - RAKOTO Jean (Ambanja)'), 'RAKOTO Jean')
        self.assertEqual(pe.parse_bp_subscriber('Paiement devis BP - RAKOTO Jean (Ambanja) - Distance: 12.50 m'), 'RAKOTO Jean')
        self.assertIsNone(pe.parse_bp_subscriber('Paiement demande BP'))
        self.assertIsNone(pe.parse_bp_subscriber('Paiement demande BP - sans village'))

    def test_summarize(self):
        self.assertEqual(pe.summarize({'targets': [], 'warnings': []}), ('Aucun objet lié à pointer', 0))
        self.assertEqual(pe.summarize({'targets': [('Relevés (X)', 3), ('Achat', 1)], 'warnings': []}),
                         ('Relevés (X) ×3 + Achat', 4))


class PointageIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from apps.billing.models import PointEau, TypePointEau
        from apps.organization.models import Ouvrage, TypeOuvrage

        cls.ouvrage = Ouvrage.objects.create(
            nom_ouvrage='Ambanja BP', type_ouvrage=TypeOuvrage.objects.create(nom_type_ouvrage='AEPG'))
        tpe = TypePointEau.objects.create(nom_type='BP')
        cls.pe1 = PointEau.objects.create(type_point_eau=tpe, ouvrage=cls.ouvrage, idxls='1', nomabonne='RAKOTO Jean')
        cls.pe2 = PointEau.objects.create(type_point_eau=tpe, ouvrage=cls.ouvrage, idxls='2', nomabonne='RABE Paul')

    def tx(self, **kwargs):
        from apps.accounting.models import DiameXTemporaire
        defaults = dict(type_transaction='recette', date_rec=date(2026, 2, 5), description='x', montant_in=100)
        defaults.update(kwargs)
        return DiameXTemporaire.objects.create(**defaults)

    def reading(self, point, paid_on=date(2026, 2, 5), number=None):
        from apps.billing.models import Releve
        return Releve.objects.create(
            point_eau=point, abonne='x', datereleve=date(2026, 1, 1), ancienindex=0, nouvelindex=1,
            consommation=1, statut='paye', datepaiement=paid_on, numeroDiameX=number)

    def forfait(self):
        from apps.billing.models import PaiementForfaitaire
        return PaiementForfaitaire.objects.create(
            point_eau=self.pe1, date_facture=date(2026, 2, 1), quantite=1, prix_unitaire=5000, montant=5000)

    def test_releves_volume_par_idxls(self):
        r1, r2 = self.reading(self.pe1), self.reading(self.pe2)
        t = self.tx(description='Paiement au volume "Ambanja BP" 05/02/2026 (1)', detail='IDXLS:1')
        res = pe.pointer_transaction(t, 42, 'PROG1')
        r1.refresh_from_db(); r2.refresh_from_db()
        self.assertEqual((r1.numeroDiameX, r1.baseDiameX), ('42', 'PROG1'))
        self.assertIsNone(r2.numeroDiameX)
        self.assertEqual(res['targets'], [('Relevés (Ambanja BP 05/02/2026)', 1)])

    def test_releves_volume_nb_releves_ignore_les_deja_pointes(self):
        deja = self.reading(self.pe1, number='7')
        nouveau = self.reading(self.pe2)
        t = self.tx(description='Paiement au volume "Ambanja BP" 05/02/2026 (2 relevés)', detail='NB_RELEVES:2')
        pe.pointer_transaction(t, 42, 'PROG1')
        deja.refresh_from_db(); nouveau.refresh_from_db()
        self.assertEqual((deja.numeroDiameX, nouveau.numeroDiameX), ('7', '42'))

    def test_ouvrage_introuvable_est_signale_sans_planter(self):
        t = self.tx(description='Paiement au volume "Inconnu" 05/02/2026 (1)')
        res = pe.pointer_transaction(t, 42, 'P')
        self.assertEqual(res['targets'], [])
        self.assertIn('introuvable', res['warnings'][0])

    def test_paiement_forfaitaire_individuel(self):
        f = self.forfait()
        t = self.tx(paiement_forfaitaire=f, description='Paiement forfaitaire_U_1_5000_Ambanja BP')
        res = pe.pointer_transaction(t, 42, 'PROG1')
        f.refresh_from_db()
        self.assertEqual((f.numeroDiameX, f.baseDiameX), ('42', 'PROG1'))
        self.assertEqual(res['targets'], [('Paiement(s) forfaitaire(s)', 1)])

    def test_paiements_forfaitaires_groupes(self):
        f1, f2, autre = self.forfait(), self.forfait(), self.forfait()
        t = self.tx(paiement_forfaitaire=f1, paiements_forfaitaires_ids=[str(f1.id), str(f2.id)])
        res = pe.pointer_transaction(t, 42, 'PROG1')
        for f in (f1, f2, autre):
            f.refresh_from_db()
        self.assertEqual((f1.numeroDiameX, f2.numeroDiameX, autre.numeroDiameX), ('42', '42', None))
        self.assertEqual(res['targets'], [('Paiement(s) forfaitaire(s)', 2)])

    def test_demande_et_devis_bp_ne_sont_plus_masques_par_le_type_recette(self):
        d = self.tx(info='hydria paiement demande', description='Paiement demande BP - RAKOTO Jean (Ambanja)')
        pe.pointer_transaction(d, 42, 'PROG1')
        q = self.tx(info='hydria paiement devis', description='Paiement devis BP - RABE Paul (Ambanja) - Distance: 3.00 m')
        pe.pointer_transaction(q, 43, 'PROG1')
        self.pe1.refresh_from_db(); self.pe2.refresh_from_db()
        self.assertEqual((self.pe1.numerodiamexdemande, self.pe1.basediamexdemande), (42, 'PROG1'))
        self.assertEqual((self.pe2.numerodiamexpaiementdevis, self.pe2.basediamexpaiementdevis), ('43', 'PROG1'))
        self.assertIsNone(self.pe2.numerodiamexdemande)

    def test_abonne_inconnu_est_signale(self):
        t = self.tx(info='hydria paiement demande', description='Paiement demande BP - PERSONNE (X)')
        res = pe.pointer_transaction(t, 42, 'P')
        self.assertEqual(res['targets'], [])
        self.assertIn('aucun point d\'eau', res['warnings'][0])

    def test_avance_planning_detail_et_ligne_sans_lien(self):
        from apps.planning.models import Designation, PlanningDetail
        des = Designation.objects.create(nom='Tuyau', prix_unitaire=1000)
        detail = PlanningDetail.objects.create(designation=des, quantity=1, pu=1000, montant=1000)
        avance = self.tx(type_transaction='avance', planning_detail=detail)
        pe.pointer_transaction(avance, 11, 'PROG1')
        detail.refresh_from_db()
        self.assertEqual((detail.numeroDiameXAvance, detail.BaseDiameXAvance, detail.numeroDiameX), (11, 'PROG1', None))

        depense = self.tx(type_transaction='depense', planning_detail=detail)
        pe.pointer_transaction(depense, 12, 'PROG1')
        detail.refresh_from_db()
        self.assertEqual((detail.numeroDiameX, detail.numeroDiameXAvance), (12, 11))

        libre = self.tx(description='Saisie manuelle')
        res = pe.pointer_transaction(libre, 13, 'PROG1')
        self.assertEqual((res['targets'], res['warnings']), ([], []))


class FinalizeViewTests(PointageIntegrationTests):
    """La vue finalize reçoit les résultats de l'agent local et doit pointer chaque ligne."""

    def call_finalize(self, results):
        import json
        from types import SimpleNamespace
        from unittest.mock import MagicMock, patch

        from django.test import RequestFactory

        from apps.accounting import views_export_access as v

        base = SimpleNamespace(base_diamex='Base1.accdb')
        fake_model = MagicMock()
        fake_model.objects.all.return_value.get.return_value = base
        request = RequestFactory().post(
            '/x', data=json.dumps({'base_id': 1, 'prog': 'PROG1', 'results': results}),
            content_type='application/json')
        request.user = SimpleNamespace(is_authenticated=True, is_superuser=True, is_staff=True)
        with patch.object(v, 'EmployeBaseDiameX', fake_model):
            response = v.export_to_access_finalize.__wrapped__(request)
        return response.status_code, json.loads(response.content)

    def test_finalize_pointe_les_releves_et_les_forfaits(self):
        reading = self.reading(self.pe1)
        forfait = self.forfait()
        t_vol = self.tx(description='Paiement au volume "Ambanja BP" 05/02/2026 (1)', detail='IDXLS:1')
        t_for = self.tx(paiement_forfaitaire=forfait, description='Paiement forfaitaire_U_1_5000_Ambanja BP')
        status, data = self.call_finalize([
            {'transaction_id': t_vol.id, 'access_id': 501, 'success': True},
            {'transaction_id': t_for.id, 'access_id': 502, 'success': True},
        ])
        self.assertEqual(status, 200)
        self.assertEqual(data['inserted'], 2)
        self.assertEqual(data['pointage_warnings'], [])
        reading.refresh_from_db(); forfait.refresh_from_db(); t_vol.refresh_from_db()
        self.assertEqual(reading.numeroDiameX, '501')
        self.assertEqual(forfait.numeroDiameX, '502')
        self.assertEqual((t_vol.id_diamex, t_vol.statut, t_vol.prog), ('501', 'exporte', 'PROG1'))
        targets = {d['transaction_id']: (d['update_target'], d['update_count']) for d in data['details']}
        self.assertEqual(targets[t_vol.id], ('Relevés (Ambanja BP 05/02/2026)', 1))
        self.assertEqual(targets[t_for.id], ('Paiement(s) forfaitaire(s)', 1))

    def test_finalize_signale_une_ligne_introuvable_et_un_pointage_impossible(self):
        t = self.tx(description='Paiement au volume "Inconnu" 05/02/2026 (1)')
        status, data = self.call_finalize([
            {'transaction_id': t.id, 'access_id': 601, 'success': True},
            {'transaction_id': 99999999, 'access_id': 602, 'success': True},
        ])
        self.assertEqual(status, 200)
        self.assertEqual(data['inserted'], 1)                      # la ligne inconnue n'est pas comptée
        self.assertEqual(len(data['pointage_warnings']), 2)
        self.assertTrue(any('introuvable ou hors de votre' in w for w in data['pointage_warnings']))
        self.assertTrue(any('Inconnu' in w for w in data['pointage_warnings']))
        t.refresh_from_db()
        self.assertEqual((t.id_diamex, t.statut), ('601', 'exporte'))  # le numéro Access reste enregistré
