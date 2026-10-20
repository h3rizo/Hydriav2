import datetime
import json
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.employees.models import Employe, GrilleSalarialeTemplate, Poste
from apps.employees.models_revalorisation import GrilleSalariale
from apps.organization.models import Base, Organisation


class GrillesSalarialesTemplateApiTests(TestCase):
    def setUp(self):
        self.organisation = Organisation.objects.create(
            nom_organisation='Hydria Test',
        )
        self.base = Base.objects.create(
            nom_base='Base Test',
            organisation=self.organisation,
        )
        self.user = User.objects.create_user(
            username='grille_manager',
            password='secret123',
        )
        Employe.objects.create(
            user=self.user,
            nom_employe='Manager Grille',
            nom='Manager',
            prenom='Grille',
            surnom='Manager',
            base=self.base,
            salarie=True,
        )
        self.poste = Poste.objects.create(
            nom_poste='Agent Technique',
            organisation=self.organisation,
        )
        self.template = GrilleSalarialeTemplate.objects.create(
            nom_template='Template Agents Techniques',
            organisation=self.organisation,
            anciennete_min=Decimal('0.00'),
            anciennete_max=Decimal('2.00'),
            fourchette_basse=Decimal('300000.00'),
            fourchette_haute=Decimal('450000.00'),
            mode_fourchette_haute='fixe',
            date_debut_validite=datetime.date(2026, 1, 1),
        )
        self.client.force_login(self.user)

    def test_api_create_accepts_template_without_manual_salary_payload(self):
        response = self.client.post(
            reverse('employees:api_grilles_salariales_create'),
            data=json.dumps({
                'poste_id': str(self.poste.id),
                'template_id': str(self.template.id),
            }),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertTrue(payload['success'])

        grille = GrilleSalariale.objects.get(poste=self.poste)
        self.assertEqual(grille.template_id, self.template.id)
        self.assertEqual(grille.anciennete_min, self.template.anciennete_min)
        self.assertEqual(grille.anciennete_max, self.template.anciennete_max)
        self.assertEqual(grille.date_debut_validite, self.template.date_debut_validite)
        self.assertEqual(grille.fourchette_basse, self.template.fourchette_basse)
        self.assertEqual(grille.fourchette_haute, self.template.fourchette_haute)

    def test_api_list_exposes_template_metadata_for_template_backed_grid(self):
        GrilleSalariale.objects.create(
            poste=self.poste,
            organisation=self.organisation,
            template=self.template,
            anciennete_min=self.template.anciennete_min,
            anciennete_max=self.template.anciennete_max,
            fourchette_basse=self.template.fourchette_basse,
            fourchette_haute=self.template.fourchette_haute,
            mode_fourchette_haute=self.template.mode_fourchette_haute,
            date_debut_validite=self.template.date_debut_validite,
        )

        response = self.client.get(reverse('employees:api_grilles_salariales_list'))

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertTrue(payload['success'])
        self.assertEqual(len(payload['data']), 1)
        grille_data = payload['data'][0]
        self.assertEqual(grille_data['template_id'], str(self.template.id))
        self.assertEqual(grille_data['template_nom'], self.template.nom_template)
        self.assertEqual(grille_data['mode_fourchette_haute'], self.template.mode_fourchette_haute)
