"""
Tests pour la classification transversale des postes (Type x Niveau).

Couvre : modele/migration (valeurs par defaut vides), formulaire de poste,
templates poste_detail/poste_list (badges + fallback "Non classe"), et les
APIs du module grille par autonomie (serialisation + filtres type/niveau,
combinables).
"""
import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.employees.forms import PosteForm
from apps.employees.models import Employe, Poste
from apps.employees.models_autonomie import GrilleAutonomie, StadeAutonomie
from apps.organization.models import Base, Organisation


class PosteClassificationModelTests(TestCase):
    def setUp(self):
        self.organisation = Organisation.objects.create(nom_organisation='Hydria Test Classification')

    def test_poste_created_without_classification_stays_null(self):
        """Un poste cree sans type/niveau ne doit PAS recevoir d'affectation arbitraire."""
        poste = Poste.objects.create(nom_poste='Poste Non Classe', organisation=self.organisation)
        self.assertIsNone(poste.type_poste)
        self.assertIsNone(poste.niveau_poste)

    def test_poste_can_be_classified(self):
        poste = Poste.objects.create(
            nom_poste='Responsable Test',
            organisation=self.organisation,
            type_poste='OPERATIONNEL',
            niveau_poste='MANAGEMENT',
        )
        poste.refresh_from_db()
        self.assertEqual(poste.type_poste, 'OPERATIONNEL')
        self.assertEqual(poste.niveau_poste, 'MANAGEMENT')

    def test_all_type_and_niveau_choices_are_valid_on_full_clean(self):
        for type_code, _ in Poste.TYPE_POSTE_CHOICES:
            for niveau_code, _ in Poste.NIVEAU_POSTE_CHOICES:
                poste = Poste(
                    nom_poste=f'{type_code}-{niveau_code}',
                    organisation=self.organisation,
                    type_poste=type_code,
                    niveau_poste=niveau_code,
                )
                poste.full_clean()  # ne doit lever aucune ValidationError


class PosteFormClassificationTests(TestCase):
    def setUp(self):
        self.organisation = Organisation.objects.create(nom_organisation='Hydria Test Form')

    def test_form_valid_with_empty_classification(self):
        form = PosteForm(data={
            'nom_poste': 'Poste Formulaire Vide',
            'organisation': str(self.organisation.id),
            'ordre_affichage': 0,
            'type_poste': '',
            'niveau_poste': '',
        })
        self.assertTrue(form.is_valid(), form.errors)
        poste = form.save()
        self.assertIsNone(poste.type_poste)
        self.assertIsNone(poste.niveau_poste)

    def test_form_valid_with_classification(self):
        form = PosteForm(data={
            'nom_poste': 'Poste Formulaire Classe',
            'organisation': str(self.organisation.id),
            'ordre_affichage': 0,
            'type_poste': 'ADMINISTRATIF',
            'niveau_poste': 'EXECUTION',
        })
        self.assertTrue(form.is_valid(), form.errors)
        poste = form.save()
        self.assertEqual(poste.type_poste, 'ADMINISTRATIF')
        self.assertEqual(poste.niveau_poste, 'EXECUTION')

    def test_form_update_can_clear_classification_back_to_non_classe(self):
        poste = Poste.objects.create(
            nom_poste='Poste A Declasser',
            organisation=self.organisation,
            type_poste='SOUTIEN',
            niveau_poste='EXECUTION',
        )
        form = PosteForm(data={
            'nom_poste': poste.nom_poste,
            'organisation': str(self.organisation.id),
            'ordre_affichage': 0,
            'type_poste': '',
            'niveau_poste': '',
        }, instance=poste)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        poste.refresh_from_db()
        self.assertIsNone(poste.type_poste)
        self.assertIsNone(poste.niveau_poste)


class PosteViewsClassificationTests(TestCase):
    def setUp(self):
        self.organisation = Organisation.objects.create(nom_organisation='Hydria Test Views')
        self.admin_user = User.objects.create_user(username='qa_admin', password='secret123', is_superuser=True, is_staff=True)
        self.client.force_login(self.admin_user)

        self.poste_classe = Poste.objects.create(
            nom_poste='Directeur QA',
            organisation=self.organisation,
            type_poste='TRANSVERSAL',
            niveau_poste='MANAGEMENT',
        )
        self.poste_non_classe = Poste.objects.create(
            nom_poste='Animateur QA',
            organisation=self.organisation,
        )

    def test_poste_list_shows_classification_column(self):
        response = self.client.get(reverse('employees:poste_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Classification')
        self.assertContains(response, 'Transversal')
        self.assertContains(response, 'Non class')

    def test_poste_detail_shows_badges_when_classified(self):
        response = self.client.get(reverse('employees:poste_detail', args=[self.poste_classe.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Transversal')
        self.assertContains(response, 'Management')

    def test_poste_detail_shows_non_classe_fallback(self):
        response = self.client.get(reverse('employees:poste_detail', args=[self.poste_non_classe.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Non class')

    def test_poste_create_form_exposes_type_and_niveau_fields(self):
        response = self.client.get(reverse('employees:poste_create'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id_type_poste')
        self.assertContains(response, 'id_niveau_poste')
        self.assertContains(response, 'post_classification.js')

    def test_poste_create_post_persists_classification(self):
        response = self.client.post(reverse('employees:poste_create'), data={
            'nom_poste': 'Poste Cree Via Formulaire',
            'organisation': str(self.organisation.id),
            'ordre_affichage': '0',
            'type_poste': 'SOUTIEN',
            'niveau_poste': 'EXECUTION',
        })
        self.assertEqual(response.status_code, 302)
        poste = Poste.objects.get(nom_poste='Poste Cree Via Formulaire')
        self.assertEqual(poste.type_poste, 'SOUTIEN')
        self.assertEqual(poste.niveau_poste, 'EXECUTION')


class GrilleAutonomieClassificationApiTests(TestCase):
    """Filtres type_poste/niveau_poste (combinables) sur les APIs du module grille par autonomie."""

    def setUp(self):
        self.organisation = Organisation.objects.create(nom_organisation='Hydria Test API')
        self.base = Base.objects.create(nom_base='Base Test API', organisation=self.organisation)
        self.admin_user = User.objects.create_user(username='qa_admin_api', password='secret123', is_superuser=True, is_staff=True)
        # has_admin_access() exige un Employe lie avec un poste "administrateur"
        # (mot-cle "directeur"), pas seulement is_superuser sur le User Django.
        poste_directeur = Poste.objects.create(nom_poste='Directeur', organisation=self.organisation)
        Employe.objects.create(
            user=self.admin_user, nom_employe='QA Directeur', nom='QA', prenom='Directeur',
            base=self.base, poste=poste_directeur, salarie=True,
        )
        self.client.force_login(self.admin_user)

        self.stade = StadeAutonomie.objects.create(
            organisation=self.organisation, nom_stade='Stade 1', ordre=0,
        )

        self.poste_operationnel_management = Poste.objects.create(
            nom_poste='Responsable operationnel QA',
            organisation=self.organisation,
            mode_reference_salariale='autonomie',
            type_poste='OPERATIONNEL',
            niveau_poste='MANAGEMENT',
        )
        self.poste_operationnel_execution = Poste.objects.create(
            nom_poste='Agent de recouvrement QA',
            organisation=self.organisation,
            mode_reference_salariale='autonomie',
            type_poste='OPERATIONNEL',
            niveau_poste='EXECUTION',
        )
        self.poste_administratif_execution = Poste.objects.create(
            nom_poste='Assistant admin QA',
            organisation=self.organisation,
            mode_reference_salariale='autonomie',
            type_poste='ADMINISTRATIF',
            niveau_poste='EXECUTION',
        )
        self.poste_non_classe = Poste.objects.create(
            nom_poste='Poste Non Classe QA',
            organisation=self.organisation,
            mode_reference_salariale='autonomie',
        )

        for poste in [
            self.poste_operationnel_management,
            self.poste_operationnel_execution,
            self.poste_administratif_execution,
            self.poste_non_classe,
        ]:
            GrilleAutonomie.objects.create(
                poste=poste,
                stade=self.stade,
                organisation=self.organisation,
                salaire_net_fixe=500000,
                date_debut_validite='2026-01-01',
            )

    def test_graphique_data_exposes_type_and_niveau(self):
        response = self.client.get(reverse('employees:api_graphique_autonomie_donnees'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        by_id = {p['poste_id']: p for p in data['postes']}
        self.assertEqual(by_id[str(self.poste_operationnel_management.id)]['type_poste'], 'OPERATIONNEL')
        self.assertEqual(by_id[str(self.poste_operationnel_management.id)]['niveau_poste'], 'MANAGEMENT')
        self.assertIsNone(by_id[str(self.poste_non_classe.id)]['type_poste'])
        self.assertIsNone(by_id[str(self.poste_non_classe.id)]['niveau_poste'])

    def test_graphique_data_filter_by_type_only(self):
        response = self.client.get(
            reverse('employees:api_graphique_autonomie_donnees'), {'type_poste': 'OPERATIONNEL'},
        )
        data = response.json()
        noms = {p['poste_nom'] for p in data['postes']}
        self.assertEqual(noms, {
            self.poste_operationnel_management.nom_poste,
            self.poste_operationnel_execution.nom_poste,
        })

    def test_graphique_data_filter_by_type_and_niveau_combined(self):
        response = self.client.get(
            reverse('employees:api_graphique_autonomie_donnees'),
            {'type_poste': 'OPERATIONNEL', 'niveau_poste': 'MANAGEMENT'},
        )
        data = response.json()
        noms = {p['poste_nom'] for p in data['postes']}
        self.assertEqual(noms, {self.poste_operationnel_management.nom_poste})

    def test_graphique_data_filter_administratif_execution(self):
        response = self.client.get(
            reverse('employees:api_graphique_autonomie_donnees'),
            {'type_poste': 'ADMINISTRATIF', 'niveau_poste': 'EXECUTION'},
        )
        data = response.json()
        noms = {p['poste_nom'] for p in data['postes']}
        self.assertEqual(noms, {self.poste_administratif_execution.nom_poste})

    def test_grilles_list_exposes_poste_type_and_niveau(self):
        response = self.client.get(reverse('employees:api_grilles_autonomie_list'))
        data = response.json()
        by_poste_id = {g['poste_id']: g for g in data['grilles']}
        self.assertEqual(
            by_poste_id[str(self.poste_administratif_execution.id)]['poste_type'], 'ADMINISTRATIF',
        )
        self.assertEqual(
            by_poste_id[str(self.poste_administratif_execution.id)]['poste_niveau'], 'EXECUTION',
        )

    def test_grilles_list_filter_combined(self):
        response = self.client.get(reverse('employees:api_grilles_autonomie_list'), {
            'type_poste': 'OPERATIONNEL', 'niveau_poste': 'EXECUTION',
        })
        data = response.json()
        poste_ids = {g['poste_id'] for g in data['grilles']}
        self.assertEqual(poste_ids, {str(self.poste_operationnel_execution.id)})

    def test_home_page_postes_data_includes_classification(self):
        response = self.client.get(reverse('employees:grilles_autonomie_home'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertIn('post_classification.js', content)
