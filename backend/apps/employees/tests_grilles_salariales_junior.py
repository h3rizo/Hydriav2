import datetime
import json
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.employees.models import Employe, Poste
from apps.employees.models_revalorisation import GrilleSalariale
from apps.employees.views_grilles_salariales_cartographie import _statut_fourchette
from apps.organization.models import Base, Organisation


class StatutFourchetteTests(SimpleTestCase):
    def test_tolerance_deux_pourcent(self):
        self.assertEqual(_statut_fourchette(98_500, 100_000, 200_000), 'dans')
        self.assertEqual(_statut_fourchette(97_900, 100_000, 200_000), 'sous')
        self.assertEqual(_statut_fourchette(203_000, 100_000, 200_000), 'dans')
        self.assertEqual(_statut_fourchette(205_000, 100_000, 200_000), 'au_dessus')


class EcartAuPalierTests(SimpleTestCase):
    def test_fourchettes_chevauchantes_prend_la_plus_basse(self):
        from apps.employees.views_grilles_salariales_cartographie import _ecart_au_palier
        paliers = {'0-2': (704000, 994100), '2-4': (766700, 1190100)}
        # Meme logique que l'API : min dans l'ordre des paliers, le premier gagne a egalite.
        choix = min(['0-2', '2-4'], key=lambda cle: _ecart_au_palier(950000, *paliers[cle]))
        self.assertEqual(choix, '0-2')

    def test_hors_fourchette_prend_le_plus_proche(self):
        from apps.employees.views_grilles_salariales_cartographie import _ecart_au_palier
        paliers = {'0-2': (704000, 994100), '2-4': (766700, 1190100)}
        choix = min(['0-2', '2-4'], key=lambda cle: _ecart_au_palier(1250000, *paliers[cle]))
        self.assertEqual(choix, '2-4')


class EmployeAncienneteGrilleTests(SimpleTestCase):
    def test_sans_date_sortie_est_junior(self):
        employe = Employe(date_embauche=datetime.date(2015, 1, 1))
        self.assertTrue(employe.est_junior(datetime.date(2026, 9, 28)))
        self.assertEqual(employe.anciennete_grille_annees(datetime.date(2026, 9, 28)), Decimal('0'))

    def test_anciennete_comptee_depuis_sortie_junior(self):
        employe = Employe(date_embauche=datetime.date(2015, 1, 1), date_sortie_junior=datetime.date(2024, 9, 28))
        self.assertFalse(employe.est_junior(datetime.date(2026, 9, 28)))
        self.assertEqual(employe.anciennete_grille_annees(datetime.date(2026, 9, 28)), Decimal('2.00'))

    def test_date_sortie_future_reste_junior(self):
        employe = Employe(date_sortie_junior=datetime.date(2027, 1, 1))
        self.assertTrue(employe.est_junior(datetime.date(2026, 9, 28)))


class GrillesSalarialesJuniorApiTests(TestCase):
    def setUp(self):
        self.organisation = Organisation.objects.create(nom_organisation='Hydria Test')
        self.base = Base.objects.create(nom_base='Base Test', organisation=self.organisation)
        self.user = User.objects.create_user(username='grille_junior', password='secret123')
        self.poste = Poste.objects.create(nom_poste='Agent Technique', organisation=self.organisation)
        Employe.objects.create(
            user=self.user, nom_employe='Manager', nom='Manager', surnom='Manager',
            base=self.base, salarie=True,
        )
        self.client.force_login(self.user)

    def _creer(self, **extra):
        payload = {
            'poste_id': str(self.poste.id),
            'fourchette_basse': 250000,
            'fourchette_haute': 300000,
            'mode_fourchette_haute': 'fixe',
            'date_debut_validite': '2026-01-01',
            **extra,
        }
        return self.client.post(
            reverse('employees:api_grilles_salariales_create'),
            data=json.dumps(payload), content_type='application/json',
        )

    def test_grille_junior_ignore_anciennete_et_coexiste_avec_tranche_0(self):
        response = self._creer(niveau='junior', anciennete_min=5, anciennete_max=9)
        self.assertEqual(response.status_code, 200, response.content)
        junior = GrilleSalariale.objects.get(poste=self.poste, niveau='junior')
        self.assertEqual(junior.anciennete_max, Decimal('0.00'))

        response = self._creer(niveau='confirme', anciennete_min=0, anciennete_max=2,
                               fourchette_basse=320000, fourchette_haute=400000)
        self.assertEqual(response.status_code, 200, response.content)

    def test_deux_grilles_junior_meme_periode_refusees(self):
        self.assertEqual(self._creer(niveau='junior').status_code, 200)
        response = self._creer(niveau='junior')
        self.assertEqual(response.status_code, 400)
        self.assertIn('Junior', response.json()['error'])

    def test_recherche_par_anciennete_exclut_junior(self):
        self._creer(niveau='junior')
        grille = GrilleSalariale.get_grille_for_poste_and_anciennete(
            self.poste, Decimal('0'), datetime.date(2026, 6, 1),
        )
        self.assertIsNone(grille)
        self.assertIsNotNone(GrilleSalariale.get_grille_junior_for_poste(self.poste, datetime.date(2026, 6, 1)))

    def test_cartographie_et_saisie_date_sortie_junior(self):
        self._creer(niveau='junior')
        self._creer(niveau='confirme', anciennete_min=0, anciennete_max=5,
                    fourchette_basse=320000, fourchette_haute=400000)
        employe = Employe.objects.create(
            nom_employe='Rakoto', nom='Rakoto', surnom='Koto', base=self.base,
            poste=self.poste, salarie=True, date_embauche=datetime.date(2020, 1, 1),
        )

        data = self.client.get(reverse('employees:api_grilles_salariales_cartographie')).json()
        self.assertEqual([c['cle'] for c in data['colonnes']], ['junior', '0-5'])
        emp = next(e for e in data['employes'] if e['employe_id'] == str(employe.id))
        self.assertTrue(emp['est_junior'])
        self.assertEqual(emp['colonne'], 'junior')
        self.assertEqual(emp['statut'], 'sans_salaire')

        url = reverse('employees:api_employe_date_sortie_junior', kwargs={'employe_id': employe.id})
        response = self.client.post(url, data=json.dumps({'date_sortie_junior': '2024-01-01'}),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)

        data = self.client.get(reverse('employees:api_grilles_salariales_cartographie')).json()
        emp = next(e for e in data['employes'] if e['employe_id'] == str(employe.id))
        self.assertFalse(emp['est_junior'])
        self.assertEqual(emp['colonne'], '0-5')

    def test_grille_employe_junior_puis_tranche_depuis_sortie(self):
        self._creer(niveau='junior')
        self._creer(niveau='confirme', anciennete_min=0, anciennete_max=2,
                    fourchette_basse=320000, fourchette_haute=400000)
        self._creer(niveau='confirme', anciennete_min=2, anciennete_max=10,
                    fourchette_basse=420000, fourchette_haute=550000)
        # Embauche en 2015 : avec l'ancienne regle il serait dans la tranche 2-10 ans.
        employe = Employe.objects.create(
            nom_employe='Rakoto', nom='Rakoto', base=self.base, poste=self.poste,
            salarie=True, date_embauche=datetime.date(2015, 1, 1),
        )
        ref = datetime.date(2026, 6, 1)
        self.assertEqual(GrilleSalariale.get_grille_for_employe(employe, ref).niveau, 'junior')

        employe.date_sortie_junior = datetime.date(2025, 6, 1)  # 1 an depuis la sortie
        grille = GrilleSalariale.get_grille_for_employe(employe, ref)
        self.assertEqual((grille.niveau, grille.anciennete_min), ('confirme', Decimal('0.00')))

    def test_revalorisation_est_dans_fourchette_utilise_anciennete_grille(self):
        from apps.employees.models_revalorisation import Revalorisation
        self._creer(niveau='junior')
        employe = Employe.objects.create(
            nom_employe='Rabe', nom='Rabe', base=self.base, poste=self.poste,
            salarie=True, date_embauche=datetime.date(2015, 1, 1),
        )
        grille = GrilleSalariale.objects.get(poste=self.poste, niveau='junior')
        reval = Revalorisation(
            employe=employe, annee=2026, grille_salariale=grille,
            salaire_actuel=grille.fourchette_basse, salaire_propose=grille.fourchette_basse,
        )
        dans, _message = reval.est_dans_fourchette
        self.assertTrue(dans)

    def test_affectation_template_en_plusieurs_exemplaires_sans_doublon(self):
        from apps.employees.models_grille_template import GrilleSalarialeTemplate
        for _copie in range(3):
            for a, b, basse, haute in [(0, 2, 300000, 400000), (2, 5, 420000, 550000)]:
                template = GrilleSalarialeTemplate.objects.create(
                    nom_template='Modele duplique', organisation=self.organisation,
                    anciennete_min=Decimal(a), anciennete_max=Decimal(b),
                    fourchette_basse=Decimal(basse), fourchette_haute=Decimal(haute),
                    mode_fourchette_haute='fixe', date_debut_validite=datetime.date(2026, 1, 1),
                )
        response = self.client.post(
            reverse('employees:api_grilles_salariales_create'),
            data=json.dumps({'template_id': str(template.id), 'poste_id': str(self.poste.id)}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(GrilleSalariale.objects.filter(poste=self.poste).count(), 2)

    def test_recrutement_compare_a_la_grille_junior(self):
        from apps.recrutement.views_gestion import _get_salary_grid_comparison
        self._creer(niveau='confirme', anciennete_min=0, anciennete_max=2,
                    fourchette_basse=320000, fourchette_haute=400000)
        self.assertEqual(_get_salary_grid_comparison(self.poste, Decimal('300'))['label'], 'Grille Junior indisponible')

        self._creer(niveau='junior')
        junior = GrilleSalariale.objects.get(poste=self.poste, niveau='junior')
        resultat = _get_salary_grid_comparison(self.poste, Decimal('1'))
        self.assertTrue(resultat['available'])
        self.assertAlmostEqual(resultat['embauche_max_kariary'], float(junior.fourchette_haute / 1000), places=2)

    def test_cartographie_place_selon_salaire_le_plus_proche(self):
        from unittest import mock
        self._creer(niveau='junior')  # 250 000 - 300 000 net
        self._creer(niveau='confirme', anciennete_min=0, anciennete_max=5,
                    fourchette_basse=320000, fourchette_haute=400000)
        employe = Employe.objects.create(
            nom_employe='Koto', nom='Koto', base=self.base, poste=self.poste,
            salarie=True, date_embauche=datetime.date(2020, 1, 1),
        )  # sans date de sortie : Junior en theorie
        salaire = {employe.id: (Decimal('350000'), datetime.date(2026, 8, 31))}
        with mock.patch(
            'apps.employees.views_grilles_salariales_cartographie._dernier_salaire_net_par_employe',
            return_value=salaire,
        ):
            data = self.client.get(reverse('employees:api_grilles_salariales_cartographie')).json()
        emp = next(e for e in data['employes'] if e['employe_id'] == str(employe.id))
        self.assertEqual((emp['colonne'], emp['colonne_theorique']), ('0-5', 'junior'))
        self.assertFalse(emp['coherent'])
        self.assertEqual(emp['statut'], 'dans')

    def _modifier_fourchette(self, grille, **payload):
        return self.client.post(
            reverse('employees:api_grille_modifier_fourchette', kwargs={'grille_id': grille.id}),
            data=json.dumps(payload), content_type='application/json',
        )

    def _deux_postes_sur_un_template(self):
        from apps.employees.models_grille_template import GrilleSalarialeTemplate
        template = GrilleSalarialeTemplate.objects.create(
            nom_template='Modele commun', organisation=self.organisation,
            anciennete_min=Decimal('0'), anciennete_max=Decimal('2'),
            fourchette_basse=Decimal('300000'), fourchette_haute=Decimal('400000'),
            mode_fourchette_haute='fixe', date_debut_validite=datetime.date(2026, 1, 1),
        )
        autre_poste = Poste.objects.create(nom_poste='Caissiere', organisation=self.organisation)
        for poste in (self.poste, autre_poste):
            response = self.client.post(
                reverse('employees:api_grilles_salariales_create'),
                data=json.dumps({'template_id': str(template.id), 'poste_id': str(poste.id)}),
                content_type='application/json',
            )
            self.assertEqual(response.status_code, 200, response.content)
        return template, GrilleSalariale.objects.get(poste=self.poste), GrilleSalariale.objects.get(poste=autre_poste)

    def test_modifier_fourchette_grille_sans_template(self):
        self._creer(niveau='junior')
        grille = GrilleSalariale.objects.get(poste=self.poste, niveau='junior')
        response = self._modifier_fourchette(grille, portee='grille', fourchette_basse=260000, fourchette_haute=330000)
        self.assertEqual(response.status_code, 200, response.content)
        grille.refresh_from_db()
        self.assertGreater(grille.fourchette_haute, grille.fourchette_basse)

    def test_modifier_fourchette_template_modifie_tous_les_postes(self):
        template, g1, g2 = self._deux_postes_sur_un_template()
        response = self._modifier_fourchette(g1, portee='template', fourchette_basse=310000, fourchette_haute=450000)
        self.assertEqual(response.status_code, 200, response.content)
        template.refresh_from_db(); g1.refresh_from_db(); g2.refresh_from_db()
        self.assertEqual(g1.template_id, template.id)
        self.assertEqual(g2.fourchette_haute, template.fourchette_haute)
        self.assertNotEqual(template.fourchette_haute, Decimal('400000'))

    def test_modifier_fourchette_ce_poste_seulement_detache_du_template(self):
        template, g1, g2 = self._deux_postes_sur_un_template()
        response = self._modifier_fourchette(g1, portee='grille', fourchette_basse=310000, fourchette_haute=450000)
        self.assertEqual(response.status_code, 200, response.content)
        template.refresh_from_db(); g1.refresh_from_db(); g2.refresh_from_db()
        self.assertIsNone(g1.template_id)
        self.assertEqual(g2.template_id, template.id)
        self.assertEqual(template.fourchette_haute, Decimal('400000'))

    def test_modifier_fourchette_haute_inferieure_refusee(self):
        self._creer(niveau='junior')
        grille = GrilleSalariale.objects.get(poste=self.poste, niveau='junior')
        response = self._modifier_fourchette(grille, portee='grille', fourchette_basse=400000, fourchette_haute=300000)
        self.assertEqual(response.status_code, 400)

    def test_temps_partiel_compare_a_la_fourchette_proratisee(self):
        from unittest import mock
        from apps.employees.models import Contrat
        self._creer(niveau='junior')  # 250 000 - 300 000 net a temps plein
        employe = Employe.objects.create(
            nom_employe='Menage', nom='Menage', base=self.base, poste=self.poste,
            salarie=True, date_embauche=datetime.date(2020, 1, 1),
        )
        Contrat.objects.create(
            employe=employe, poste=self.poste, debut_contrat=datetime.date(2020, 1, 1),
            type_contrat='temps_partiel', quotite_temps_travail=Decimal('25'),
        )
        salaire = {employe.id: (Decimal('70000'), datetime.date(2026, 8, 31))}
        with mock.patch(
            'apps.employees.views_grilles_salariales_cartographie._dernier_salaire_net_par_employe',
            return_value=salaire,
        ):
            data = self.client.get(reverse('employees:api_grilles_salariales_cartographie')).json()
        emp = next(e for e in data['employes'] if e['employe_id'] == str(employe.id))
        self.assertEqual(emp['quotite'], 25.0)
        self.assertEqual(emp['statut'], 'dans')  # 70 000 dans [~62 500 ; ~75 000]
        self.assertAlmostEqual(emp['salaire_position'], 280000, places=0)
        self.assertLess(emp['fourchette_haute'], 80000)

    def test_api_quotite_modifie_le_contrat_en_vigueur(self):
        from apps.employees.models import Contrat
        employe = Employe.objects.create(
            nom_employe='Agent', nom='Agent', base=self.base, poste=self.poste, salarie=True,
        )
        contrat = Contrat.objects.create(employe=employe, poste=self.poste, debut_contrat=datetime.date(2024, 1, 1))
        url = reverse('employees:api_employe_quotite', kwargs={'employe_id': employe.id})
        response = self.client.post(url, data=json.dumps({'quotite': '50'}), content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        contrat.refresh_from_db()
        self.assertEqual(contrat.quotite_temps_travail, Decimal('50.00'))
        response = self.client.post(url, data=json.dumps({'quotite': '0'}), content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_date_sortie_avant_embauche_refusee(self):
        employe = Employe.objects.create(
            nom_employe='Rabe', nom='Rabe', base=self.base, poste=self.poste,
            salarie=True, date_embauche=datetime.date(2022, 1, 1),
        )
        url = reverse('employees:api_employe_date_sortie_junior', kwargs={'employe_id': employe.id})
        response = self.client.post(url, data=json.dumps({'date_sortie_junior': '2021-06-01'}),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 400)
