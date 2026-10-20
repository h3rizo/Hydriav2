from django.test import TestCase

from apps.employees.models import Employe, Poste
from apps.organization.models import Base, Organisation

from .views import _regrouper_details_par_base_et_poste


class RegrouperDetailsParBaseEtPosteTests(TestCase):
    def setUp(self):
        self.organisation = Organisation.objects.create(nom_organisation='Org System Tests')
        self.base_a = Base.objects.create(nom_base='Base A', organisation=self.organisation)
        self.base_b = Base.objects.create(nom_base='Base B', organisation=self.organisation)
        self.poste_directeur = Poste.objects.create(nom_poste='Directeur', organisation=self.organisation)
        self.poste_superviseur = Poste.objects.create(nom_poste='Superviseur technique', organisation=self.organisation)

    def _employe(self, nom, base=None, poste=None):
        return Employe.objects.create(nom_employe=nom, nom=nom, base=base, poste=poste)

    def test_regroupe_par_base_puis_poste(self):
        emp1 = self._employe('Emp1', base=self.base_a, poste=self.poste_directeur)
        emp2 = self._employe('Emp2', base=self.base_a, poste=self.poste_superviseur)
        emp3 = self._employe('Emp3', base=self.base_b, poste=self.poste_directeur)
        details = [
            {'employe': emp1}, {'employe': emp2}, {'employe': emp3},
        ]
        groupes = _regrouper_details_par_base_et_poste(details)
        self.assertEqual(set(groupes.keys()), {'Base A', 'Base B'})
        self.assertEqual(set(groupes['Base A'].keys()), {'Directeur', 'Superviseur technique'})
        self.assertEqual(len(groupes['Base A']['Directeur']), 1)
        self.assertEqual(len(groupes['Base B']['Directeur']), 1)

    def test_tri_alphabetique_bases_et_postes(self):
        emp_b = self._employe('EmpB', base=self.base_b, poste=self.poste_directeur)
        emp_a = self._employe('EmpA', base=self.base_a, poste=self.poste_superviseur)
        details = [{'employe': emp_b}, {'employe': emp_a}]
        groupes = _regrouper_details_par_base_et_poste(details)
        self.assertEqual(list(groupes.keys()), ['Base A', 'Base B'])

    def test_employe_sans_poste_regroupe_sous_libelle_explicite(self):
        emp = self._employe('SansPoste', base=self.base_a, poste=None)
        details = [{'employe': emp}]
        groupes = _regrouper_details_par_base_et_poste(details)
        self.assertIn('Sans poste', groupes['Base A'])

    def test_liste_vide_donne_dict_vide(self):
        self.assertEqual(_regrouper_details_par_base_et_poste([]), {})
