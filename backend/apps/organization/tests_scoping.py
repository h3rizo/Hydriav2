from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from django.urls import reverse

from apps.organization.scoping import (
    apply_user_responsable_ouvrage_scope,
    get_active_employee_ouvrage_ids,
    get_active_employee_scope_ids,
    get_employe_ids_with_responsible_ouvrage_scope,
    current_modalite_q,
)


class _FakeValuesListResult:
    def __init__(self, values):
        self.values = values

    def distinct(self):
        return self.values

    def __iter__(self):
        return iter(self.values)


class _FakeFilterChain:
    def __init__(self, values):
        self.values = values

    def filter(self, *args, **kwargs):
        return self

    def values_list(self, *args, **kwargs):
        return _FakeValuesListResult(self.values)


class ResponsableOuvrageScopeTests(SimpleTestCase):
    def test_current_modalite_condition_requires_started_contract(self):
        condition = current_modalite_q('modalites_gestion')
        rendered = str(condition)

        self.assertIn('modalites_gestion__date_debut__lte', rendered)
        self.assertIn('modalites_gestion__date_fin__isnull', rendered)
        self.assertIn('modalites_gestion__date_fin__gte', rendered)
        self.assertIn('modalites_gestion__statut__in', rendered)

    def test_employee_choices_include_ancestors_of_direct_responsables(self):
        employe_manager = SimpleNamespace(
            filter=lambda *args, **kwargs: _FakeFilterChain([1, 2, 3])
        )
        ouvrage_manager = SimpleNamespace(
            filter=lambda *args, **kwargs: _FakeFilterChain([3])
        )
        hierarchy_manager = SimpleNamespace(
            filter=lambda *args, **kwargs: _FakeFilterChain([(1, 2), (2, 3)])
        )
        with patch('apps.employees.models.Employe.objects', employe_manager), \
             patch('apps.employees.models.EmployeOuvrages.objects', ouvrage_manager), \
             patch('apps.employees.models.HierarchieEmploye.objects', hierarchy_manager):
            eligible_ids = get_employe_ids_with_responsible_ouvrage_scope()

        self.assertEqual(eligible_ids, {1, 2, 3})

    def test_responsable_export_route(self):
        self.assertEqual(
            reverse('organization:export_ouvrages_responsable_excel'),
            '/organisations/ouvrages/export-excel-responsable/',
        )

    def test_employee_scope_excludes_debauched_employees(self):
        fake_manager = SimpleNamespace(
            filter=lambda *args, **kwargs: _FakeFilterChain([10, 12])
        )
        with patch(
            'apps.organization.scoping.get_active_subordinate_employe_ids',
            return_value={10, 11, 12},
        ), patch('apps.employees.models.Employe.objects', fake_manager):
            scoped_ids = get_active_employee_scope_ids(10)

        self.assertEqual(scoped_ids, {10, 12})

    def test_employee_ouvrage_scope_includes_subordinates_assignments(self):
        fake_manager = SimpleNamespace(
            filter=lambda *args, **kwargs: _FakeFilterChain(['ouvrage-a', 'ouvrage-b'])
        )
        with patch(
            'apps.organization.scoping.get_active_employee_scope_ids',
            return_value={10, 12},
        ), patch('apps.employees.models.EmployeOuvrages.objects', fake_manager):
            ouvrage_ids = get_active_employee_ouvrage_ids(10)

        self.assertEqual(ouvrage_ids, {'ouvrage-a', 'ouvrage-b'})

    def test_partenaire_keeps_gestionnaire_scope(self):
        partenaire = SimpleNamespace(type_organisation='partenaire')
        user = SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            employe=SimpleNamespace(
                id=10,
                base=SimpleNamespace(organisation=partenaire),
            ),
        )

        scoped_ids = apply_user_responsable_ouvrage_scope({1, 2, 3}, user)

        self.assertEqual(scoped_ids, {1, 2, 3})

    def test_directeur_keeps_full_scope(self):
        user = SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            employe=SimpleNamespace(id=1),
        )

        with patch('apps.employees.permissions.is_directeur_poste', return_value=True):
            scoped_ids = apply_user_responsable_ouvrage_scope({1, 2, 3}, user)

        self.assertEqual(scoped_ids, {1, 2, 3})

    def test_non_directeur_is_limited_to_active_responsable_ouvrages(self):
        user = SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            employe=SimpleNamespace(id=10),
        )

        fake_manager = SimpleNamespace(
            filter=lambda *args, **kwargs: _FakeFilterChain([2, 4, 6])
        )

        with patch('apps.employees.permissions.is_directeur_poste', return_value=False), \
             patch('apps.organization.scoping.get_active_subordinate_employe_ids', return_value={10, 11, 12}), \
             patch('apps.employees.models.EmployeOuvrages.objects', fake_manager):
            scoped_ids = apply_user_responsable_ouvrage_scope({1, 2, 3, 4}, user)

        self.assertEqual(scoped_ids, {2, 4})

    def test_support_role_can_see_same_base_responsables_when_enabled(self):
        user = SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            employe=SimpleNamespace(
                id=10,
                base_id='base-1',
                poste=SimpleNamespace(nom_poste='Caissière'),
            ),
        )

        fake_employe_manager = SimpleNamespace(
            filter=lambda *args, **kwargs: _FakeFilterChain([10, 11, 12])
        )
        fake_relation_manager = SimpleNamespace(
            filter=lambda *args, **kwargs: _FakeFilterChain([4, 6, 8])
        )

        with patch('apps.employees.permissions.is_directeur_poste', return_value=False), \
             patch('apps.employees.models.Employe.objects', fake_employe_manager), \
             patch('apps.employees.models.EmployeOuvrages.objects', fake_relation_manager):
            scoped_ids = apply_user_responsable_ouvrage_scope(
                {1, 4, 5, 6},
                user,
                allow_same_base_support_roles=True,
            )

        self.assertEqual(scoped_ids, {4, 6})

    def test_user_without_employe_gets_empty_scope(self):
        user = SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            employe=None,
        )

        with patch('apps.employees.permissions.is_directeur_poste', return_value=False):
            scoped_ids = apply_user_responsable_ouvrage_scope({1, 2, 3}, user)

        self.assertEqual(scoped_ids, set())
