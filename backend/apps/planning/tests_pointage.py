from datetime import time

from django.test import SimpleTestCase

from apps.planning import services_pointage as svc


class HaversineTests(SimpleTestCase):
    def test_meme_point(self):
        self.assertAlmostEqual(svc.haversine_m(-18.9, 47.5, -18.9, 47.5), 0, places=3)

    def test_un_degre_de_latitude_vaut_environ_111_km(self):
        d = svc.haversine_m(-18.0, 47.5, -19.0, 47.5)
        self.assertAlmostEqual(d / 1000, 111.2, delta=0.3)

    def test_seuil_3_km(self):
        # ~0,027 degré de latitude ≈ 3,0 km
        self.assertLess(svc.haversine_m(-18.9, 47.5, -18.9 - 0.026, 47.5), svc.DISTANCE_MAX_M)
        self.assertGreater(svc.haversine_m(-18.9, 47.5, -18.9 - 0.028, 47.5), svc.DISTANCE_MAX_M)


class CreneauTests(SimpleTestCase):
    def test_fenetres(self):
        self.assertEqual(svc.creneau_pour(time(10, 0)), 'matin')
        self.assertEqual(svc.creneau_pour(time(12, 0)), 'matin')
        self.assertEqual(svc.creneau_pour(time(15, 30)), 'aprem')
        self.assertEqual(svc.creneau_pour(time(19, 0)), 'nuit')
        self.assertEqual(svc.creneau_pour(time(21, 0)), 'nuit')

    def test_hors_fenetre(self):
        for h in (time(9, 59), time(12, 1), time(14, 59), time(18, 1), time(18, 59), time(21, 1), time(3, 0)):
            self.assertIsNone(svc.creneau_pour(h), h)


class RapportMensuelTests(SimpleTestCase):
    LIGNES = [
        {'date': __import__('datetime').date(2026, 9, 2), 'villages': 'Ambato', 'activite': 'Visite',
         'matin': 'OK', 'aprem': 'Non OK', 'nuit': '—', 'total_valides': 1},
        {'date': __import__('datetime').date(2026, 9, 3), 'villages': 'Ambato, Vohipeno', 'activite': 'Réparation',
         'matin': 'OK', 'aprem': 'OK', 'nuit': 'Non OK', 'total_valides': 2},
    ]

    def test_totaux(self):
        from apps.planning import views_pointage as v
        t = v._totaux(self.LIGNES)
        self.assertEqual((t['valides'], t['prevus']), (3, 5))
        self.assertEqual((t['matin_ok'], t['aprem_non_ok'], t['nuit_non_ok']), (2, 1, 1))

    def test_navigation_de_mois(self):
        from apps.planning import views_pointage as v
        self.assertEqual(v._decaler_mois(2026, 1, -1), (2025, 12))
        self.assertEqual(v._decaler_mois(2026, 12, 1), (2027, 1))
        self.assertEqual(v._parse_mois('2026-09'), (2026, 9))

    def test_classeur_excel(self):
        from apps.planning import views_pointage as v
        ws = v.construire_classeur(self.LIGNES, 'Herizo', 2026, 9).active
        self.assertEqual([c.value for c in ws[3]], v.COLONNES)
        self.assertEqual(ws['A4'].value, '02/09/2026')
        self.assertEqual(ws['E4'].value, 'Non OK')
        self.assertEqual(ws['G6'].value, 3)  # ligne TOTAL

    def test_gabarit_compile(self):
        from django.template.loader import get_template
        get_template('planning/rapport_pointage.html')


class GroupementEmployesTests(SimpleTestCase):
    @staticmethod
    def _e(id_, surnom, base, poste, debauche=None):
        from types import SimpleNamespace as N
        return N(id=id_, surnom=surnom, nom_affichage=surnom,
                 base=N(nom_base=base) if base else None,
                 poste=N(nom_poste=poste) if poste else None, date_debauchage=debauche)

    def test_groupe_par_base_puis_poste_et_exclut_les_debauches(self):
        from datetime import date
        from apps.planning import views_pointage as v
        employes = [
            self._e(1, 'Zo', 'Soakoja', 'Technicien'),
            self._e(2, 'Ando', 'Soakoja', 'Technicien'),
            self._e(3, 'Bao', 'Ambanja', 'Technicien'),
            self._e(4, 'Chef', 'Soakoja', 'Responsable'),
            self._e(5, 'Parti', 'Soakoja', 'Technicien', debauche=date(2026, 1, 1)),
            self._e(6, 'Libre', None, None),
        ]
        groupes = v.grouper_employes(employes)
        self.assertEqual([g['label'] for g in groupes], [
            'Ambanja › Technicien', 'Soakoja › Responsable', 'Soakoja › Technicien', 'Sans base › Sans poste'])
        self.assertEqual([e['nom'] for e in groupes[2]['employes']], ['Ando', 'Zo'])
        self.assertNotIn('Parti', [e['nom'] for g in groupes for e in g['employes']])

    def test_le_debauche_affiche_reste_dans_la_liste(self):
        from datetime import date
        from apps.planning import views_pointage as v
        groupes = v.grouper_employes([self._e(5, 'Parti', 'Soakoja', 'Technicien', date(2026, 1, 1))], selectionne_id=5)
        self.assertEqual(groupes[0]['employes'][0]['nom'], 'Parti')


class FicheIndemniteTests(SimpleTestCase):
    def _lignes(self):
        from datetime import date
        return [
            {'date': date(2026, 9, 2), 'villages': 'Ambato', 'activite': 'Visite',
             'matin': 'OK', 'aprem': 'OK', 'nuit': 'OK', 'total_valides': 3},
            {'date': date(2026, 9, 3), 'villages': 'Ambato', 'activite': 'Visite',
             'matin': 'OK', 'aprem': 'Non OK', 'nuit': '—', 'total_valides': 1},
            {'date': date(2026, 9, 4), 'villages': 'Ambato', 'activite': 'Visite',
             'matin': 'Non OK', 'aprem': '—', 'nuit': '—', 'total_valides': 0},
        ]

    def test_calcul_des_montants(self):
        f = svc.calculer_fiche_indemnite(self._lignes(), 4000, 8000)
        self.assertEqual((f['nb_demi_journees'], f['nb_nuitees']), (3, 1))
        self.assertEqual(f['montant_total'], 3 * 4000 + 8000)
        self.assertEqual(len(f['detail']), 2)  # le jour sans pointage validé n'apparaît pas
        self.assertEqual(f['detail'][0]['montant'], 2 * 4000 + 8000)
        self.assertEqual((f['creneaux_prevus'], f['creneaux_non_pointes']), (6, 2))

    def test_sans_tarif_le_montant_est_zero(self):
        self.assertEqual(svc.calculer_fiche_indemnite(self._lignes(), None, None)['montant_total'], 0)

    def test_page_de_fiche_se_rend(self):
        from datetime import date
        from types import SimpleNamespace as N
        from django.template.loader import render_to_string
        html = render_to_string('planning/fiche_indemnite_pointage.html', {
            'employe_nom': 'RAKOTO Jean', 'surnom': 'Zo', 'poste': N(nom_poste='Technicien'),
            'base': N(nom_base='Soakoja'), 'organisation': N(nom_organisation='Soakoja'),
            'superieur_nom': 'Chef', 'fiche': svc.calculer_fiche_indemnite(self._lignes(), 4000, 8000),
            'mois_libelle': 'Septembre 2026', 'date_edition': date(2026, 9, 30),
        })
        for attendu in ('RAKOTO Jean', 'Technicien', 'Septembre 2026', 'TOTAL À PERCEVOIR', 'Chef'):
            self.assertIn(attendu, html)


class PlanningOuvrageNomTests(SimpleTestCase):
    """Regression : /pointage/aujourdhui renvoyait 500 (Ouvrage n'a pas d'attribut infra_name)."""

    def test_nom_de_l_ouvrage_du_planning(self):
        from apps.organization.models import Ouvrage
        from apps.planning.models import Planning
        planning = Planning(ouvrage=Ouvrage(nom_ouvrage='Ambanja BP'))
        self.assertEqual(planning.ouvrage_nom, 'Ambanja BP')

    def test_sans_ouvrage(self):
        from apps.planning.models import Planning
        self.assertEqual(Planning().ouvrage_nom, 'Aucun ouvrage')


class PointageApplicableTests(SimpleTestCase):
    """Pas de pointage sur un ouvrage dont le type « n'existe pas » (Bureau, Terrain…)."""

    @staticmethod
    def _pl(existe=None, sans_ouvrage=False):
        from types import SimpleNamespace as N
        if sans_ouvrage:
            return N(ouvrage=None)
        return N(ouvrage=N(type_ouvrage=None if existe is None else N(existe=existe)))

    def test_regle(self):
        self.assertTrue(svc.pointage_applicable(self._pl(existe=True)))
        self.assertFalse(svc.pointage_applicable(self._pl(existe=False)))
        self.assertTrue(svc.pointage_applicable(self._pl(existe=None)))       # type non renseigné
        self.assertTrue(svc.pointage_applicable(self._pl(sans_ouvrage=True)))

    def test_pointage_refuse_si_tous_les_plannings_sont_sans_pointage(self):
        from types import SimpleNamespace as N
        from unittest.mock import patch
        from datetime import datetime
        employe = N(id=1)
        ts = svc.tz_madagascar.localize(datetime(2026, 9, 25, 10, 30))
        with patch.object(svc, 'plannings_du_jour', return_value=[self._pl(existe=False)]), \
                patch.object(svc.timezone, 'now', return_value=ts), \
                patch.object(svc, '_refuser', side_effect=lambda e, statut, msg, **kw: (statut, msg)):
            statut, message = svc.enregistrer_pointage(employe, -18.9, 47.5, precision_m=10)
        self.assertEqual(statut, svc.PointageGPS.STATUT_REFUSE_SANS_PLANNING)
        self.assertIn('sans pointage', message)
