from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.accounting import pointage_ecritures as pe

D = Decimal


class ClasserRecoupementTests(SimpleTestCase):
    def test_dans_la_limite(self):
        self.assertEqual(pe.classer_recoupement(D('20000'), 2), ('ok', D('20000')))

    def test_depassement_a_un_ariary_pres(self):
        self.assertEqual(pe.classer_recoupement(D('30000'), 3), ('ok', D('30000')))
        self.assertEqual(pe.classer_recoupement(D('30001'), 3), ('depasse', D('30000')))

    def test_indemnite_sans_forfaitaire_pointe(self):
        self.assertEqual(pe.classer_recoupement(D('5000'), 0), ('sans_forfait', D('0')))

    def test_rien_paye_rien_pointe(self):
        self.assertEqual(pe.classer_recoupement(D('0'), 0)[0], 'ok')

    def test_point_non_identifie_pas_de_controle(self):
        self.assertEqual(pe.classer_recoupement(D('90000'), 0, identified=False), ('non_identifie', None))


class AnneeExerciceTests(SimpleTestCase):
    def test_annee_du_libelle_prime_sur_la_date_compta(self):
        from apps.accounting.indemnites_points import annee_exercice as ae
        self.assertEqual(ae('X_Indemnité RBF2 2025_Fft_20000_Ambo', 2026), 2025)
        self.assertEqual(ae('X_Indemnité BF3_2024_Fft_20000_Vohi', 2026), 2024)
        self.assertEqual(ae('X_Indemnité RBF1 2026_Fft_10000_Alpha', 2026), 2026)

    def test_multi_annees_prend_la_plus_recente(self):
        from apps.accounting.indemnites_points import annee_exercice as ae
        self.assertEqual(ae('Z_Indemnité RBF7_2025 et 2024_Vohi', 2026), 2025)
        self.assertEqual(ae('Z_Indemnité RBF7_2024 et 2025_Vohi', 2025), 2025)
        self.assertEqual(ae('Z_Indemnité RBF7_2026 et 2025_Vohi', 2025), 2026)    # paye en 2025 pour 2026 : la plus recente

    def test_pas_de_faux_positifs(self):
        from apps.accounting.indemnites_points import annee_exercice as ae
        for label in ('R_Nettoyage BF3_Fft_20000_Vohi', 'R_Indemnité PPMH_U_1_5000_Ampetsapetsa PPMH2',
                      'X_Indemnité RBF1_Trimestre_Fft_2000_Ar Andranobe', 'X_Indemnité RBF1 2019_Fft_10000_Alpha', ''):
            self.assertEqual(ae(label, 2026), 2026, label)
        self.assertIsNone(ae('X_Indemnité RBF1 2025', None))


class FakeCache:
    def __init__(self):
        self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value, timeout=None):
        self.data[key] = value


class PointageIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from apps.billing.models import PointEau, TypePointEau
        from apps.organization.models import Ouvrage, TypeOuvrage

        type_ouvrage = TypeOuvrage.objects.create(nom_type_ouvrage='PMH')
        cls.ouvrage = Ouvrage.objects.create(nom_ouvrage='ZzTestPointage', type_ouvrage=type_ouvrage)
        bf, _ = TypePointEau.objects.get_or_create(nom_type='BF')
        now = timezone.now()
        cls.p1 = PointEau.objects.create(ouvrage=cls.ouvrage, type_point_eau=bf, idxls='1', nomabonne='Borne Nord',
                                         datebranchement=now, tarifforfaitaire=10000)
        cls.p2 = PointEau.objects.create(ouvrage=cls.ouvrage, type_point_eau=bf, idxls='2', nomabonne='Borne Sud',
                                         datebranchement=now, tarifforfaitaire=10000)

    def entry(self, compte, montant_in=0, montant_out=0, id_access=1, prog='P', description='x', day=None):
        from apps.accounting.models import BaseDiameX
        return BaseDiameX.objects.create(
            id_access=id_access, fichier_source='t.accdb', date_m=day or date(2026, 3, 1), date_rec=day or date(2026, 3, 1),
            description=description, montant_in=montant_in, montant_out=montant_out, compte_code=compte, prog=prog)

    def forfait(self, point, quantite, numero='', base='', day=date(2026, 1, 1)):
        from apps.billing.models import PaiementForfaitaire
        return PaiementForfaitaire.objects.create(
            point_eau=point, date_facture=day, quantite=quantite, prix_unitaire=10000,
            montant=10000 * quantite, numeroDiameX=numero or None, baseDiameX=base or None)

    # ---- 748411 -------------------------------------------------------------------------------------------
    def test_forfait_pointe_et_conforme(self):
        e = self.entry('748411', montant_in=30000, id_access=11)
        self.forfait(self.p1, 1, '11', 'P')
        self.forfait(self.p2, 2, '11', 'P')
        pe.attach_pointage([e])
        self.assertEqual((e.pointage['verdict'], e.pointage['count'], e.pointage['total']), ('ok', 2, D('30000.00')))

    def test_forfait_pointe_avec_ecart(self):
        e = self.entry('748411', montant_in=30000, id_access=12)
        self.forfait(self.p1, 1, '12', 'P')
        pe.attach_pointage([e])
        self.assertEqual((e.pointage['verdict'], e.pointage['gap']), ('ecart', D('-20000.00')))

    def test_forfait_non_pointe_et_autre_base_ignoree(self):
        e = self.entry('748411', montant_in=10000, id_access=13, prog='P')
        self.forfait(self.p1, 1, '13', 'AUTRE')            # meme numero, autre base : ce n'est pas cette ecriture
        pe.attach_pointage([e])
        self.assertEqual(e.pointage['verdict'], 'non_pointe')

    def test_ecriture_volume_pointee_sur_paiement_forfaitaire(self):
        e = self.entry('707401', montant_in=10000, id_access=14)
        self.forfait(self.p1, 1, '14', 'P')
        pe.attach_pointage([e])
        self.assertEqual((e.pointage['verdict'], e.pointage['source']), ('mauvaise_source', 'forfaitaire'))

    def test_autres_comptes_sans_pointage(self):
        e = self.entry('606100', montant_out=500, id_access=15)
        pe.attach_pointage([e])
        self.assertIsNone(e.pointage)

    def test_detail_modal(self):
        e = self.entry('748411', montant_in=20000, id_access=16)
        self.forfait(self.p2, 1, '16', 'P')
        self.forfait(self.p1, 1, '16', 'P')
        d = pe.pointage_detail(e)
        self.assertEqual((d['verdict'], d['count'], d['total']), ('ok', 2, 20000.0))
        self.assertEqual([r['idxls'] for r in d['rows']], ['1', '2'])          # tri numerique par IDXLS

    # ---- 621102 -------------------------------------------------------------------------------------------
    def indemnite(self, montant, idxls='1', id_access=100, day=date(2026, 3, 1)):
        return self.entry('621102', montant_out=montant, id_access=id_access, day=day,
                          description=f'X Y_Indemnité RBF{idxls} {day.year}_Fft_{montant}_ZzTestPointage')

    def recoupe(self, entries):
        from apps.core import views_ouvrage_interventions as v
        with patch.object(v, 'OUVRAGE_CARD_CACHE', FakeCache()):
            index = v._rbf_indemnity_lines_by_ouvrage()
        pe.attach_recoupement_indemnites(entries, index)
        return index

    def test_indemnite_dans_la_limite_du_forfaitaire_pointe(self):
        e = self.indemnite(10000)
        self.forfait(self.p1, 1, '1', 'P')
        self.recoupe([e])
        r = e.rbf_recoupement
        self.assertEqual((r['status'], r['units'], r['allowed'], r['alert']), ('ok', 1, D('10000'), False))

    def test_depassement_dix_mille_par_forfaitaire(self):
        a, b = self.indemnite(10000, id_access=101), self.indemnite(5000, id_access=102)
        self.forfait(self.p1, 1, '1', 'P')
        self.recoupe([a, b])
        self.assertEqual((a.rbf_recoupement['status'], a.rbf_recoupement['rbf_total'], a.rbf_recoupement['excess']),
                         ('depasse', D('15000.00'), D('5000.00')))
        self.assertTrue(a.rbf_recoupement['needs_explanation'])

    def test_forfaitaire_non_pointe_ne_compte_pas(self):
        e = self.indemnite(10000)
        self.forfait(self.p1, 1)                              # facture mais pas pointee
        self.recoupe([e])
        r = e.rbf_recoupement
        self.assertEqual((r['status'], r['unpointed_units']), ('sans_forfait', 1))

    def test_explication_couvre_l_alerte_jusqu_a_un_nouveau_paiement(self):
        from apps.core.models import ExplicationEcartIndemnitePoint
        a = self.indemnite(15000, id_access=101)
        self.forfait(self.p1, 1, '1', 'P')
        ExplicationEcartIndemnitePoint.objects.create(
            point_eau=self.p1, annee=2026, motif='depasse', montant_paye=15000, plafond=10000,
            unites_forfait=1, explication='Reparation exceptionnelle de la pompe')
        self.recoupe([a])
        self.assertTrue(a.rbf_recoupement['explained'])
        self.assertFalse(a.rbf_recoupement['needs_explanation'])
        b = self.indemnite(2000, id_access=102)                # nouveau paiement : 17 000 > 15 000 explique
        self.recoupe([a, b])
        self.assertFalse(a.rbf_recoupement['explained'])
        self.assertTrue(a.rbf_recoupement['needs_explanation'])

    def test_point_par_annee(self):
        old = self.indemnite(10000, id_access=101, day=date(2025, 12, 1))
        self.forfait(self.p1, 1, '1', 'P', day=date(2026, 1, 1))     # forfait 2026 : ne couvre pas 2025
        self.recoupe([old])
        self.assertEqual((old.rbf_recoupement['year'], old.rbf_recoupement['status']), (2025, 'sans_forfait'))

    def test_detail_recoupement(self):
        e = self.indemnite(10000)
        self.forfait(self.p1, 1, '1', 'P')
        index = self.recoupe([e])
        d = pe.recoupement_detail(e, index)
        self.assertTrue(d['linked'])
        self.assertEqual((d['situation']['status'], d['situation']['allowed']), ('ok', 10000.0))
        self.assertEqual((len(d['indemnities']), len(d['forfaits'])), (1, 1))
        self.assertIn('Borne Nord', d['point']['label'])

    def test_vues_ajax_et_explication(self):
        from django.contrib.auth import get_user_model
        from django.test import RequestFactory
        from apps.accounting import views_entry_pointage as vp

        user = get_user_model().objects.create_superuser('zz_pointage', 'z@z.z', 'x')
        e = self.indemnite(15000, id_access=101)
        self.forfait(self.p1, 1, '1', 'P')
        from apps.core import views_ouvrage_interventions as v
        rf = RequestFactory()
        with patch.object(v, 'OUVRAGE_CARD_CACHE', FakeCache()):
            get = rf.get('/x/'); get.user = user
            response = vp.entry_pointage_detail(get, e.id)
            self.assertEqual(response.status_code, 200)

            import json
            post = rf.post('/x/', data=json.dumps({'explication': 'court'}), content_type='application/json'); post.user = user
            self.assertEqual(vp.entry_explication_indemnite(post, e.id).status_code, 400)
            post = rf.post('/x/', data=json.dumps({'explication': 'Réparation exceptionnelle de la pompe'}),
                           content_type='application/json'); post.user = user
            self.assertEqual(vp.entry_explication_indemnite(post, e.id).status_code, 200)
        from apps.core.models import ExplicationEcartIndemnitePoint
        self.assertEqual(ExplicationEcartIndemnitePoint.objects.get().motif, 'depasse')

    def test_page_liste_affiche_les_indicateurs(self):
        from django.contrib.auth import get_user_model
        from django.test import Client
        from apps.core import views_ouvrage_interventions as v

        user = get_user_model().objects.create_superuser('zz_pointage2', 'z@z.z', 'x')
        self.entry('748411', montant_in=10000, id_access=21)
        self.forfait(self.p1, 1, '21', 'P')
        self.indemnite(15000, id_access=101)
        client = Client()
        client.force_login(user)
        with patch.object(v, 'OUVRAGE_CARD_CACHE', FakeCache()):
            page = client.get('/comptabilite/entries/?view_mode=liste&compte=748411')
            self.assertEqual(page.status_code, 200)
            self.assertContains(page, 'Pointé · Paiement forfaitaire')
            self.assertContains(page, 'openEntryPointageModal')
            page = client.get('/comptabilite/entries/?view_mode=liste&compte=621102')
            self.assertEqual(page.status_code, 200)
            self.assertContains(page, 'par forfaitaire')
            self.assertContains(page, 'Explication requise')

    def test_indemnite_d_une_autre_annee_comptee_dans_son_exercice(self):
        # Libelle « RBF1 2025 » paye en 2026 : compte dans 2025, avec le forfaitaire pointe de 2025.
        old = self.entry('621102', montant_out=10000, id_access=201, day=date(2026, 2, 1),
                         description='X Y_Indemnité RBF1 2025_Fft_10000_ZzTestPointage')
        cur = self.entry('621102', montant_out=10000, id_access=202, day=date(2026, 2, 1),
                         description='X Y_Indemnité RBF1 2026_Fft_10000_ZzTestPointage')
        self.forfait(self.p1, 1, '1', 'P', day=date(2025, 6, 1))
        self.forfait(self.p1, 1, '2', 'P', day=date(2026, 1, 1))
        self.recoupe([old, cur])
        self.assertEqual((old.rbf_recoupement['year'], old.rbf_recoupement['status'], old.rbf_exercice_decale), (2025, 'ok', 2025))
        self.assertEqual((cur.rbf_recoupement['year'], cur.rbf_recoupement['status'], cur.rbf_exercice_decale), (2026, 'ok', None))
        self.assertEqual(old.rbf_recoupement['rbf_total'], D('10000.00'))   # pas melange avec 2026
