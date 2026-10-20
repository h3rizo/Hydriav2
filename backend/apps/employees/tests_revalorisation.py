import datetime
import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.employees.models import Contrat, Employe, GrilleSalaire, Poste
from apps.employees.models_evaluation import Evaluation, EvaluationDetail, FichePoste
from apps.employees.models_evaluation_resultats import EvaluationResultats
from apps.employees.models_revalorisation import Revalorisation
from apps.organization.models import Base, Organisation


class RevalorisationEligibilityTests(TestCase):
    def setUp(self):
        self.organisation = Organisation.objects.create(
            nom_organisation='Soakoja Test',
        )
        self.base = Base.objects.create(
            nom_base='Base Test',
            organisation=self.organisation,
        )

        self.auth_user = User.objects.create_user(
            username='manager_revalo',
            password='secret123',
        )
        self.auth_employe = Employe.objects.create(
            user=self.auth_user,
            nom_employe='Manager Revalo',
            nom='Manager',
            prenom='Revalo',
            surnom='Manager',
            base=self.base,
            salarie=True,
        )
        self.directeur_poste = Poste.objects.create(
            nom_poste='Directeur',
            organisation=self.organisation,
        )
        self.standard_poste = Poste.objects.create(
            nom_poste='Superviseur',
            organisation=self.organisation,
        )

        self.active_employee = Employe.objects.create(
            nom_employe='Employe Actif',
            nom='Actif',
            prenom='Employe',
            surnom='Actif',
            base=self.base,
            salarie=True,
            date_embauche=datetime.date(2024, 6, 1),
        )
        self.terminated_in_year_employee = Employe.objects.create(
            nom_employe='Employe Sortant',
            nom='Sortant',
            prenom='Employe',
            surnom='Sortant',
            base=self.base,
            salarie=True,
            date_embauche=datetime.date(2020, 1, 1),
            date_debauchage=datetime.date(2026, 7, 15),
        )
        self.standard_evaluator = Employe.objects.create(
            nom_employe='Evaluateur Standard',
            nom='Standard',
            prenom='Eval',
            surnom='Standard',
            base=self.base,
            poste=self.standard_poste,
            salarie=True,
        )
        self.directeur_evaluator = Employe.objects.create(
            nom_employe='Evaluateur Directeur',
            nom='Directeur',
            prenom='Eval',
            surnom='Directeur',
            base=self.base,
            poste=self.directeur_poste,
            salarie=True,
        )
        self.fiche_1 = FichePoste.objects.create(
            tache='Qualite',
            description='Qualite du travail',
        )
        self.fiche_2 = FichePoste.objects.create(
            tache='Ponctualite',
            description='Ponctualite au travail',
        )

        self.client.force_login(self.auth_user)

    def _create_reference_evaluations(self):
        evaluation_2024 = Evaluation.objects.create(
            employe=self.active_employee,
            evaluateur=self.auth_employe,
            date_evaluation=datetime.date(2025, 1, 10),
            periode_debut=datetime.date(2024, 1, 1),
            periode_fin=datetime.date(2024, 12, 31),
            commentaire_general='Evaluation annuelle 2024',
            statut='terminee',
        )
        evaluation_2025 = Evaluation.objects.create(
            employe=self.active_employee,
            evaluateur=self.auth_employe,
            date_evaluation=datetime.date(2026, 1, 15),
            periode_debut=datetime.date(2025, 1, 1),
            periode_fin=datetime.date(2025, 12, 31),
            commentaire_general='Evaluation annuelle 2025',
            statut='terminee',
        )
        return evaluation_2024, evaluation_2025

    def _create_reference_evaluations_resultats(self):
        evaluation_2024 = EvaluationResultats.objects.create(
            employe=self.active_employee,
            periode_debut=datetime.date(2024, 1, 1),
            periode_fin=datetime.date(2024, 12, 31),
            date_calcul=datetime.date(2025, 1, 10),
            score_obtenu=3,
            score_maximum=5,
            nb_ouvrages=2,
            montant_collecte_forfaitaire=120000,
            montant_collecte_volume=30000,
            montant_prevu_forfaitaire=150000,
            montant_prevu_volume=40000,
            statut='validee',
            commentaire='Resultats 2024',
        )
        evaluation_2025 = EvaluationResultats.objects.create(
            employe=self.active_employee,
            periode_debut=datetime.date(2025, 1, 1),
            periode_fin=datetime.date(2025, 12, 31),
            date_calcul=datetime.date(2026, 1, 15),
            score_obtenu=4,
            score_maximum=5,
            nb_ouvrages=3,
            montant_collecte_forfaitaire=200000,
            montant_collecte_volume=50000,
            montant_prevu_forfaitaire=210000,
            montant_prevu_volume=60000,
            statut='validee',
            commentaire='Resultats 2025',
        )
        return evaluation_2024, evaluation_2025

    def _create_evaluation_with_notes(self, evaluateur, notes, date_evaluation):
        evaluation = Evaluation.objects.create(
            employe=self.active_employee,
            evaluateur=evaluateur,
            date_evaluation=date_evaluation,
            periode_debut=datetime.date(2025, 1, 1),
            periode_fin=datetime.date(2025, 12, 31),
            commentaire_general='Evaluation de test',
            statut='terminee',
        )
        for fiche, note in zip((self.fiche_1, self.fiche_2), notes):
            EvaluationDetail.objects.create(
                evaluation=evaluation,
                fiche_poste=fiche,
                note=note,
                remarques='',
            )
        return evaluation

    def _create_salary_history_for_previous_year(self):
        contrat_2025 = Contrat.objects.create(
            employe=self.active_employee,
            debut_contrat=datetime.date(2025, 1, 1),
            fin_contrat=datetime.date(2025, 12, 31),
            type_contrat='temps_plein',
            salaire_brut_base=200000,
        )
        GrilleSalaire.objects.create(
            contrat=contrat_2025,
            date_salaire=datetime.date(2025, 1, 31),
            salaire_brut_base=200000,
        )
        GrilleSalaire.objects.create(
            contrat=contrat_2025,
            date_salaire=datetime.date(2025, 12, 31),
            salaire_brut_base=250000,
        )
        Contrat.objects.create(
            employe=self.active_employee,
            debut_contrat=datetime.date(2026, 1, 1),
            type_contrat='temps_plein',
            salaire_brut_base=400000,
        )

    def test_api_list_excludes_employee_terminated_in_selected_year(self):
        response = self.client.get(
            reverse('employees:api_revalorisations_list'),
            {'annee': 2026},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        returned_ids = {item['employe_id'] for item in payload['data']}

        self.assertIn(str(self.active_employee.id), returned_ids)
        self.assertNotIn(str(self.terminated_in_year_employee.id), returned_ids)

    def test_api_save_rejects_employee_terminated_in_selected_year(self):
        response = self.client.post(
            reverse('employees:api_revalorisation_save'),
            data=json.dumps({
                'employe_id': str(self.terminated_in_year_employee.id),
                'annee': 2026,
                'salaire_propose': 250000,
                'justification': 'Test',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload['success'])
        self.assertIn("n'est pas eligible", payload['error'])

    def test_api_list_uses_previous_period_year_for_reference_evaluation(self):
        _, evaluation_2025 = self._create_reference_evaluations()

        response = self.client.get(
            reverse('employees:api_revalorisations_list'),
            {'annee': 2026},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        employee_data = next(
            item for item in payload['data']
            if item['employe_id'] == str(self.active_employee.id)
        )

        self.assertIsNotNone(employee_data['evaluation'])
        self.assertEqual(employee_data['evaluation']['id'], str(evaluation_2025.id))

    def test_api_save_persists_previous_period_year_evaluation_as_reference(self):
        _, evaluation_2025 = self._create_reference_evaluations()
        Contrat.objects.create(
            employe=self.active_employee,
            debut_contrat=datetime.date(2024, 6, 1),
            type_contrat='temps_plein',
            salaire_brut_base=300000,
        )

        response = self.client.post(
            reverse('employees:api_revalorisation_save'),
            data=json.dumps({
                'employe_id': str(self.active_employee.id),
                'annee': 2026,
                'salaire_propose': 350000,
                'justification': 'Ajustement annuel',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200, response.content)
        revalorisation = Revalorisation.objects.get(
            employe=self.active_employee,
            annee=2026,
        )
        self.assertEqual(revalorisation.evaluation_id, evaluation_2025.id)

    def test_api_list_uses_previous_period_year_for_reference_evaluation_resultats(self):
        _, evaluation_2025 = self._create_reference_evaluations_resultats()

        response = self.client.get(
            reverse('employees:api_revalorisations_list'),
            {'annee': 2026},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        employee_data = next(
            item for item in payload['data']
            if item['employe_id'] == str(self.active_employee.id)
        )

        self.assertIsNotNone(employee_data['evaluation_resultats'])
        self.assertEqual(employee_data['evaluation_resultats']['id'], str(evaluation_2025.id))
        self.assertEqual(employee_data['evaluation_resultats']['score_obtenu'], 4)
        self.assertEqual(employee_data['evaluation_resultats']['score_maximum'], 5)
        self.assertAlmostEqual(
            employee_data['evaluation_resultats']['taux_recouvrement'],
            92.59,
            places=2,
        )

    def test_api_list_uses_last_salary_of_previous_year_as_current_salary(self):
        self._create_salary_history_for_previous_year()

        response = self.client.get(
            reverse('employees:api_revalorisations_list'),
            {'annee': 2026},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        employee_data = next(
            item for item in payload['data']
            if item['employe_id'] == str(self.active_employee.id)
        )

        self.assertEqual(employee_data['salaire_actuel_brut'], 250000.0)

    def test_api_save_uses_last_salary_of_previous_year_as_current_salary(self):
        self._create_salary_history_for_previous_year()

        response = self.client.post(
            reverse('employees:api_revalorisation_save'),
            data=json.dumps({
                'employe_id': str(self.active_employee.id),
                'annee': 2026,
                'salaire_propose': 450000,
                'justification': 'Ajustement annuel',
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200, response.content)
        revalorisation = Revalorisation.objects.get(
            employe=self.active_employee,
            annee=2026,
        )
        self.assertEqual(float(revalorisation.salaire_actuel), 250000.0)

    def test_api_list_returns_weighted_evaluation_score(self):
        self._create_evaluation_with_notes(
            evaluateur=self.standard_evaluator,
            notes=[2, 2],
            date_evaluation=datetime.date(2026, 1, 10),
        )
        self._create_evaluation_with_notes(
            evaluateur=self.active_employee,
            notes=[0, 0],
            date_evaluation=datetime.date(2026, 1, 11),
        )
        self._create_evaluation_with_notes(
            evaluateur=self.directeur_evaluator,
            notes=[1, 1],
            date_evaluation=datetime.date(2026, 1, 12),
        )

        response = self.client.get(
            reverse('employees:api_revalorisations_list'),
            {'annee': 2026},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        employee_data = next(
            item for item in payload['data']
            if item['employe_id'] == str(self.active_employee.id)
        )

        self.assertIsNotNone(employee_data['evaluation_score'])
        self.assertAlmostEqual(employee_data['evaluation_score']['percentage'], 57.14, places=2)
        self.assertEqual(employee_data['evaluation_score']['evaluations_count'], 3)
        self.assertEqual(employee_data['evaluation_score']['auto_count'], 1)
        self.assertEqual(employee_data['evaluation_score']['direction_count'], 1)
        self.assertEqual(employee_data['evaluation_score']['standard_count'], 1)

    def test_api_evaluation_detail_handles_missing_fiche_poste(self):
        evaluation = Evaluation.objects.create(
            employe=self.active_employee,
            evaluateur=self.standard_evaluator,
            date_evaluation=datetime.date(2026, 1, 10),
            periode_debut=datetime.date(2025, 1, 1),
            periode_fin=datetime.date(2025, 12, 31),
            commentaire_general='Evaluation avec tache supprimee',
            statut='terminee',
        )
        detail = EvaluationDetail.objects.create(
            evaluation=evaluation,
            fiche_poste=None,
            note=1,
            remarques='Historique conserve',
        )

        response = self.client.get(
            reverse('employees:api_evaluation_detail', kwargs={'evaluation_id': evaluation.id}),
        )

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(len(payload['details']), 1)
        self.assertEqual(payload['details'][0]['fiche_poste_id'], f'missing-{detail.id}')
        self.assertEqual(payload['details'][0]['tache'], 'Tache supprimee')
        self.assertTrue(payload['details'][0]['fiche_poste_missing'])
