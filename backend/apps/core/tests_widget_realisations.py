import uuid
from datetime import date, datetime, timezone as dt_timezone
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.core import widget_realisations as wr
from apps.core.models import ConstatRealisation

TZ = wr.TZ_MADAGASCAR


def mg(*args):
    return TZ.localize(datetime(*args))


OUV_A, OUV_B = uuid.uuid4(), uuid.uuid4()


def etat(volume=None, forfait=None, activites=None):
    return {
        'pointage_volume': volume or {},
        'pointage_forfait': forfait or {},
        'activite_terminee': activites or {},
    }


class BornesPeriodeTests(SimpleTestCase):
    def test_jour_compare_hier_a_la_meme_heure(self):
        debut, fin, debut_prec, fin_prec = wr.bornes_periode('jour', mg(2026, 10, 14, 10, 30))
        self.assertEqual(debut, mg(2026, 10, 14))
        self.assertEqual(debut_prec, mg(2026, 10, 13))
        self.assertEqual(fin_prec, mg(2026, 10, 13, 10, 30))

    def test_semaine_commence_le_lundi(self):
        # Mercredi 14 octobre 2026 -> lundi 12.
        debut, _, debut_prec, fin_prec = wr.bornes_periode('semaine', mg(2026, 10, 14, 9))
        self.assertEqual(debut, mg(2026, 10, 12))
        self.assertEqual(debut_prec, mg(2026, 10, 5))
        self.assertEqual(fin_prec, mg(2026, 10, 7, 9))

    def test_mois_plafonne_au_debut_du_mois_courant(self):
        # 31 mars : février n'a que 28 jours, la période précédente s'arrête au 1er mars.
        debut, _, debut_prec, fin_prec = wr.bornes_periode('mois', mg(2026, 3, 31, 12))
        self.assertEqual(debut, mg(2026, 3, 1))
        self.assertEqual(debut_prec, mg(2026, 2, 1))
        self.assertEqual(fin_prec, mg(2026, 3, 1))
        self.assertEqual(wr._jours(debut_prec, fin_prec), (date(2026, 2, 1), date(2026, 2, 28)))

    def test_mois_de_janvier_remonte_en_decembre(self):
        _, _, debut_prec, fin_prec = wr.bornes_periode('mois', mg(2026, 1, 10, 8))
        self.assertEqual(debut_prec, mg(2025, 12, 1))
        self.assertEqual(fin_prec, mg(2025, 12, 10, 8))

    def test_bornes_en_heure_de_madagascar_meme_si_now_en_utc(self):
        # 22 h UTC le 13 = 1 h du matin le 14 à Madagascar.
        now_utc = datetime(2026, 10, 13, 22, 0, tzinfo=dt_timezone.utc)
        debut, *_ = wr.bornes_periode('jour', now_utc)
        self.assertEqual(debut, mg(2026, 10, 14))

    def test_periode_inconnue(self):
        with self.assertRaises(ValueError):
            wr.bornes_periode('annee')


class ReconcilierTests(SimpleTestCase):
    def test_depointage_puis_repointage_garde_la_date_d_origine(self):
        origine = mg(2026, 10, 1, 9)
        constat = ConstatRealisation(constate_le=origine)
        self.assertTrue(wr.reconcilier(constat, False, mg(2026, 10, 3)))
        self.assertEqual(constat.retire_le, mg(2026, 10, 3))
        self.assertTrue(wr.reconcilier(constat, True, mg(2026, 10, 6)))
        self.assertIsNone(constat.retire_le)
        self.assertEqual(constat.constate_le, origine)

    def test_aucun_changement(self):
        self.assertFalse(wr.reconcilier(ConstatRealisation(constate_le=mg(2026, 10, 1)), True, mg(2026, 10, 2)))
        retire = ConstatRealisation(constate_le=mg(2026, 10, 1), retire_le=mg(2026, 10, 2))
        self.assertFalse(wr.reconcilier(retire, False, mg(2026, 10, 3)))


@mock.patch.object(wr, '_indemnites_rbf', return_value=(0, 0.0))
class ConstaterEtCompteursTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_premier_constat_marque_l_existant_initial_et_ne_le_compte_pas(self, _rbf):
        wr.constater(mg(2026, 10, 14, 8), etat(volume={'r1': (OUV_A, '', 1000)}))
        self.assertIsNone(ConstatRealisation.objects.get(objet_id='r1').constate_le)
        res = wr.compteurs('jour', None, mg(2026, 10, 14, 18))
        self.assertEqual(res['compteurs']['pointages_volume']['courant'], 0)

    def test_nouveau_pointage_compte_aujourd_hui_et_hier_sert_de_comparaison(self, _rbf):
        wr.constater(mg(2026, 10, 12, 7), etat(volume={'r0': (OUV_A, '', 500)}))
        wr.constater(mg(2026, 10, 13, 9), etat(volume={'r0': (OUV_A, '', 500), 'r1': (OUV_A, '', 1000)}))
        wr.constater(mg(2026, 10, 14, 9), etat(volume={
            'r0': (OUV_A, '', 500), 'r1': (OUV_A, '', 1000),
            'r2': (OUV_A, '', 2000), 'r3': (OUV_B, '', 3000),
        }))
        bloc = wr.compteurs('jour', None, mg(2026, 10, 14, 10))['compteurs']['pointages_volume']
        self.assertEqual((bloc['courant'], bloc['montant']), (2, 5000.0))
        self.assertEqual((bloc['precedent'], bloc['montant_precedent']), (1, 1000.0))

    def test_comparaison_a_date_equivalente(self, _rbf):
        wr.constater(mg(2026, 10, 12, 7), etat(volume={'r0': (OUV_A, '', 1)}))
        # Hier à 15 h : après l'heure actuelle (10 h), donc hors comparaison.
        wr.constater(mg(2026, 10, 13, 15), etat(volume={'r0': (OUV_A, '', 1), 'r1': (OUV_A, '', 1)}))
        bloc = wr.compteurs('jour', None, mg(2026, 10, 14, 10))['compteurs']['pointages_volume']
        self.assertEqual(bloc['precedent'], 0)
        bloc = wr.compteurs('jour', None, mg(2026, 10, 14, 16))['compteurs']['pointages_volume']
        self.assertEqual(bloc['precedent'], 1)

    def test_depointage_retire_le_compteur(self, _rbf):
        wr.constater(mg(2026, 10, 12, 7), etat(forfait={'p0': (OUV_A, '', 1)}))
        wr.constater(mg(2026, 10, 14, 8), etat(forfait={'p0': (OUV_A, '', 1), 'p1': (OUV_A, '', 5)}))
        wr.constater(mg(2026, 10, 14, 9), etat(forfait={'p0': (OUV_A, '', 1)}))
        bloc = wr.compteurs('jour', None, mg(2026, 10, 14, 10))['compteurs']['pointages_forfait']
        self.assertEqual(bloc['courant'], 0)
        # Repointé : revient, à sa date d'origine.
        wr.constater(mg(2026, 10, 15, 9), etat(forfait={'p0': (OUV_A, '', 1), 'p1': (OUV_A, '', 5)}))
        bloc = wr.compteurs('jour', None, mg(2026, 10, 15, 10))['compteurs']['pointages_forfait']
        self.assertEqual((bloc['courant'], bloc['precedent']), (0, 1))

    def test_perimetre_et_familles_d_activites(self, _rbf):
        wr.constater(mg(2026, 10, 12, 7), etat(activites={'x': (OUV_A, 'autre', None)}))
        wr.constater(mg(2026, 10, 14, 8), etat(activites={
            'x': (OUV_A, 'autre', None),
            'a1': (OUV_A, 'reparation', None),
            'a2': (OUV_A, 'rehabilitation', None),
            'a3': (OUV_B, 'reparation', None),
            'a4': (None, 'installation', None),
        }))
        c = wr.compteurs('semaine', [str(OUV_A)], mg(2026, 10, 14, 9))['compteurs']
        self.assertEqual(c['reparations_terminees']['courant'], 1)
        self.assertEqual(c['rehabilitations_terminees']['courant'], 1)
        self.assertEqual(c['installations_terminees']['courant'], 0)
        c = wr.compteurs('semaine', None, mg(2026, 10, 14, 9))['compteurs']
        self.assertEqual(c['reparations_terminees']['courant'], 2)
        self.assertEqual(c['installations_terminees']['courant'], 1)

    def test_constat_idempotent(self, _rbf):
        e = etat(volume={'r1': (OUV_A, '', 1)})
        wr.constater(mg(2026, 10, 12, 7), e)
        resume = wr.constater(mg(2026, 10, 12, 8), e)
        self.assertEqual(resume['pointage_volume'], {'nouveaux': 0, 'modifies': 0, 'initial': False})
        self.assertEqual(ConstatRealisation.objects.count(), 1)

    def test_rbf_compare_les_jours_de_la_periode(self, rbf):
        wr.compteurs('mois', None, mg(2026, 10, 14, 10))
        appels = [c.args[1:] for c in rbf.call_args_list]
        self.assertEqual(appels, [
            (date(2026, 10, 1), date(2026, 10, 14)),
            (date(2026, 9, 1), date(2026, 9, 14)),
        ])


class EtatCourantTests(TestCase):
    """L'état courant sur les vraies tables : une base vide ne doit pas planter."""

    def test_etat_courant_base_vide(self):
        self.assertEqual(wr.etat_courant(date(2026, 10, 14)), etat())


class ApiRealisationsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_superuser('dir', 'dir@example.com', 'x')
        self.client.force_login(self.user)

    def test_periode_invalide(self):
        response = self.client.get(reverse('core:api_widget_realisations'), {'periode': 'annee'})
        self.assertEqual(response.status_code, 400)

    @mock.patch('apps.core.views_widget._resolve_scoped_ouvrage_ids', return_value=[])
    def test_reponse_semaine(self, _scope):
        response = self.client.get(reverse('core:api_widget_realisations'), {'periode': 'semaine'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['periode'], 'semaine')
        self.assertEqual(
            set(data['compteurs']),
            {'pointages_volume', 'pointages_forfait', 'reparations_terminees', 'rehabilitations_terminees',
             'installations_terminees', 'autres_activites_terminees', 'indemnites_rbf_payees'},
        )
        self.assertEqual(set(data['compteurs']['pointages_volume']),
                         {'courant', 'precedent', 'montant', 'montant_precedent'})
        self.assertIsNotNone(data['dernier_constat'])
