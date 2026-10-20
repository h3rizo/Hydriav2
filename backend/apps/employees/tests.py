from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch, PropertyMock
from uuid import uuid4

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .models_conges import JourFerie
from .models import GrilleSalaire
from .utils_conges import est_jour_ferie, get_jour_ferie_label, get_jours_feries
from .views import (
    _build_employe_organigramme_fiche,
    _build_organigramme_data,
    _filter_active_employes_queryset,
    _scope_organigramme_queryset,
)
from .views_recuperations import (
    _build_recuperation_year_choices,
    _get_easter_sunday,
    _get_recuperation_public_holidays,
    _filter_employes_for_selection,
)
from .views_verification_croisee import _get_annee_croise_entry, _get_mois_croise_entry


class GrilleSalaireGardienHourlyMajorationTests(SimpleTestCase):
    def test_shift_hours_use_guardian_day_and_night_durations(self):
        self.assertEqual(GrilleSalaire._gardien_shift_hours('jour'), 10)
        self.assertEqual(GrilleSalaire._gardien_shift_hours('nuit'), 14)
        self.assertEqual(GrilleSalaire._gardien_shift_hours('etendu'), 24)
        self.assertEqual(GrilleSalaire._gardien_shift_hours('conge'), 0)

    def test_night_majoration_counts_only_22h_to_05h_without_extensions(self):
        self.assertEqual(GrilleSalaire._gardien_night_majoration_hours('nuit'), 7)
        self.assertEqual(GrilleSalaire._gardien_night_majoration_hours('jour'), 0)
        self.assertEqual(GrilleSalaire._gardien_night_majoration_hours('etendu'), 0)

    def test_guardian_majorations_include_sunday_hours_at_40_percent(self):
        amounts = GrilleSalaire._calculate_gardien_majoration_amounts(Decimal('240000'), {
            'nuit': Decimal('14'),
            'dimanche': Decimal('10'),
            'ferie': Decimal('14'),
            'premier_mai': Decimal('10'),
            'remplacement': Decimal('14'),
            'remplacement_ordinaire': Decimal('0'),
        })

        self.assertEqual(amounts['taux_horaire'], Decimal('1000'))
        self.assertEqual(amounts['nuit'], Decimal('4200'))
        self.assertEqual(amounts['dimanche'], Decimal('4000'))
        self.assertEqual(amounts['ferie'], Decimal('7000'))
        self.assertEqual(amounts['premier_mai'], Decimal('10000'))
        # Remplacement = +100% fixe (14h * 1000 Ar/h), sans jour ordinaire ici.
        self.assertEqual(amounts['remplacement'], Decimal('14000'))

    def test_guardian_replacement_majoration_adds_30_percent_on_ordinary_days(self):
        amounts = GrilleSalaire._calculate_gardien_majoration_amounts(Decimal('240000'), {
            'remplacement': Decimal('10'),
            'remplacement_ordinaire': Decimal('6'),
        })

        # 10h * 1000 Ar/h * 100% (toujours) + 6h * 1000 Ar/h * 30% (jour ordinaire seulement)
        self.assertEqual(amounts['taux_horaire'], Decimal('1000'))
        self.assertEqual(amounts['remplacement'], Decimal('11800'))

    def test_guardian_rotation_hours_stay_in_their_calendar_category(self):
        from apps.employees.models_gardiens import RotationGardien
        from apps.employees.models_conges import JourFerie

        rotations = [
            SimpleNamespace(
                date=date(2026, 1, 4),  # Dimanche
                shift_type='jour',
                heures_travaillees=Decimal('10'),
                est_jour_ferie=False,
                est_dimanche=True,
                est_extension=False,
            ),
            SimpleNamespace(
                date=date(2026, 1, 6),  # Nuit ordinaire
                shift_type='nuit',
                heures_travaillees=Decimal('14'),
                est_jour_ferie=False,
                est_dimanche=False,
                est_extension=False,
            ),
        ]

        grille = GrilleSalaire(
            contrat_id=uuid4(),
            date_salaire=date(2026, 1, 31),
        )
        fake_contrat = SimpleNamespace(employe_id=uuid4())

        with patch.object(GrilleSalaire, '_get_periode_salaire', return_value=(date(2026, 1, 1), date(2026, 1, 31))):
            with patch.object(type(grille), 'contrat', new_callable=PropertyMock, return_value=fake_contrat):
                with patch.object(RotationGardien.objects, 'filter') as mock_filter:
                    mock_filter.return_value.order_by.return_value = rotations
                    with patch.object(JourFerie.objects, 'filter') as mock_jf_filter:
                        mock_jf_filter.return_value.values_list.return_value = []
                        result = grille._compute_gardien_rotation_hours()

        # Dimanche : 10h classées dimanche.
        self.assertEqual(result['dimanche'], Decimal('10'))
        # Nuit ordinaire : seul le forfait de 7h nuit compte.
        self.assertEqual(result['nuit'], Decimal('7'))
        self.assertEqual(result['ferie'], Decimal('0'))
        self.assertEqual(result['chome_paye'], Decimal('0'))
        self.assertEqual(result['premier_mai'], Decimal('0'))
        # Total du mois (10h + 14h = 24h) très inférieur à 240h : pas de remplacement.
        self.assertEqual(result['remplacement'], Decimal('0'))
        self.assertEqual(result['remplacement_ordinaire'], Decimal('0'))

    def test_guardian_replacement_is_computed_from_hours_beyond_240_per_month(self):
        from apps.employees.models_gardiens import RotationGardien
        from apps.employees.models_conges import JourFerie

        # 24 rotations de jour (10h) un jour de semaine (lundi-samedi, non
        # dimanche calendaire) = 240h ordinaires, plus 1 rotation le
        # dimanche 4 janvier 2026 (10h) = 10h spéciales. Total = 250h,
        # dépassement = 10h, entièrement prélevé sur l'ordinaire (240h dispo).
        jours_non_dimanche = [
            d for d in range(2, 32) if date(2026, 1, d).weekday() != 6
        ][:24]
        rotations = [
            SimpleNamespace(
                date=date(2026, 1, day),
                shift_type='jour',
                heures_travaillees=Decimal('10'),
                est_jour_ferie=False,
                est_dimanche=False,
                est_extension=False,
            )
            for day in jours_non_dimanche
        ] + [
            SimpleNamespace(
                date=date(2026, 1, 4),  # Dimanche
                shift_type='jour',
                heures_travaillees=Decimal('10'),
                est_jour_ferie=False,
                est_dimanche=True,
                est_extension=False,
            ),
        ]

        grille = GrilleSalaire(
            contrat_id=uuid4(),
            date_salaire=date(2026, 1, 31),
        )
        fake_contrat = SimpleNamespace(employe_id=uuid4())

        with patch.object(GrilleSalaire, '_get_periode_salaire', return_value=(date(2026, 1, 1), date(2026, 1, 31))):
            with patch.object(type(grille), 'contrat', new_callable=PropertyMock, return_value=fake_contrat):
                with patch.object(RotationGardien.objects, 'filter') as mock_filter:
                    mock_filter.return_value.order_by.return_value = rotations
                    with patch.object(JourFerie.objects, 'filter') as mock_jf_filter:
                        mock_jf_filter.return_value.values_list.return_value = []
                        result = grille._compute_gardien_rotation_hours()

        # 24 jours ordinaires x 10h = 240h ordinaires + 10h dimanche = 250h total.
        # Depassement = 10h, entierement preleve sur l'ordinaire (240h disponibles).
        self.assertEqual(result['dimanche'], Decimal('10'))
        self.assertEqual(result['remplacement'], Decimal('10'))
        self.assertEqual(result['remplacement_ordinaire'], Decimal('10'))

    def test_guardian_replacement_draws_from_special_hours_when_ordinary_hours_are_insufficient(self):
        from apps.employees.models_gardiens import RotationGardien
        from apps.employees.models_conges import JourFerie

        # 1 rotation ordinaire (10h) + 25 rotations dimanche (10h = 250h
        # speciales). Total = 260h, depassement = 20h. Les 10h ordinaires
        # ne suffisent pas a absorber les 20h de depassement : les 10h
        # restantes sont prelevees sur le stock d'heures speciales (dimanche).
        rotations = [
            SimpleNamespace(
                date=date(2026, 1, 2),
                shift_type='jour',
                heures_travaillees=Decimal('10'),
                est_jour_ferie=False,
                est_dimanche=False,
                est_extension=False,
            ),
        ] + [
            SimpleNamespace(
                date=date(2026, 1, day),
                shift_type='jour',
                heures_travaillees=Decimal('10'),
                est_jour_ferie=False,
                est_dimanche=True,
                est_extension=False,
            )
            for day in range(3, 28)  # 25 dimanches fictifs = 250h speciales
        ]

        grille = GrilleSalaire(
            contrat_id=uuid4(),
            date_salaire=date(2026, 1, 31),
        )
        fake_contrat = SimpleNamespace(employe_id=uuid4())

        with patch.object(GrilleSalaire, '_get_periode_salaire', return_value=(date(2026, 1, 1), date(2026, 1, 31))):
            with patch.object(type(grille), 'contrat', new_callable=PropertyMock, return_value=fake_contrat):
                with patch.object(RotationGardien.objects, 'filter') as mock_filter:
                    mock_filter.return_value.order_by.return_value = rotations
                    with patch.object(JourFerie.objects, 'filter') as mock_jf_filter:
                        mock_jf_filter.return_value.values_list.return_value = []
                        result = grille._compute_gardien_rotation_hours()

        # Total = 10h ordinaires + 250h dimanche = 260h. Depassement = 20h.
        # Les 10h ordinaires sont insuffisantes : 10h prises sur l'ordinaire,
        # les 10h restantes prises sur les heures speciales (dimanche).
        self.assertEqual(result['dimanche'], Decimal('250'))
        self.assertEqual(result['remplacement'], Decimal('20'))
        self.assertEqual(result['remplacement_ordinaire'], Decimal('10'))

    def test_other_employees_use_173_33_hourly_base_and_eight_hour_days(self):
        amounts = GrilleSalaire._calculate_employee_majoration_amounts(Decimal('173330'), {
            'dimanche': Decimal('8'),
            'ferie': Decimal('8'),
            'premier_mai': Decimal('8'),
        })

        self.assertEqual(amounts['taux_horaire'], Decimal('1000'))
        self.assertEqual(amounts['dimanche'], Decimal('3200'))
        self.assertEqual(amounts['ferie'], Decimal('4000'))
        self.assertEqual(amounts['premier_mai'], Decimal('8000'))


class OrganigrammeEmployesDataTests(SimpleTestCase):
    class FakeQuerySet:
        def __init__(self):
            self.filter_kwargs = []
            self.none_called = False

        def filter(self, **kwargs):
            self.filter_kwargs.append(kwargs)
            return self

        def none(self):
            self.none_called = True
            return self

    def _employe(self, nom_affichage, poste_nom='Poste', base_nom='Base', organisation_nom='Organisation'):
        employe_id = uuid4()
        return SimpleNamespace(
            id=employe_id,
            nom_complet=nom_affichage,
            nom_affichage=nom_affichage,
            poste=SimpleNamespace(nom_poste=poste_nom),
            base=SimpleNamespace(
                nom_base=base_nom,
                organisation=SimpleNamespace(nom_organisation=organisation_nom),
            ),
            telephone='0340000000',
            mail=f"{nom_affichage.lower().replace(' ', '.')}@hydria.mg",
        )

    def _hierarchie(self, employe, superieur):
        return SimpleNamespace(
            employe_id=employe.id,
            superieur_id=superieur.id,
        )

    def _ouvrage_relation(self, employe, nom_ouvrage, principal=False):
        ouvrage_id = uuid4()
        return SimpleNamespace(
            employe_id=employe.id,
            employe=employe,
            ouvrage_id=ouvrage_id,
            ouvrage=SimpleNamespace(
                nom_ouvrage=nom_ouvrage,
                type_ouvrage=SimpleNamespace(nom_type_ouvrage='Forage'),
            ),
            est_responsable_principal=principal,
            recevoir_alertes=True,
            date_debut=date(2026, 1, 1),
        )

    def _collect_node_ids(self, nodes):
        ids = []
        for node in nodes:
            ids.append(node['id'])
            ids.extend(self._collect_node_ids(node['children']))
        return ids

    def test_build_organigramme_data_creates_tree_and_assigns_ouvrages(self):
        root = self._employe('Alice Root', poste_nom='Directeur', base_nom='Base Alpha')
        child = self._employe('Bob Child', poste_nom='Technicien', base_nom='Base Alpha')

        with patch('apps.employees.views.Ouvrage.objects.filter') as ouvrage_filter:
            ouvrage_filter.return_value.values.return_value = []
            roots, stats = _build_organigramme_data(
                [root, child],
                [self._hierarchie(child, root)],
                [self._ouvrage_relation(child, 'Sahasaona', principal=True)],
            )

        self.assertEqual(len(roots), 1)
        self.assertEqual(roots[0]['id'], root.id)
        self.assertEqual(roots[0]['subordinates_count'], 1)
        self.assertEqual(roots[0]['children'][0]['id'], child.id)
        self.assertEqual(roots[0]['children'][0]['superieur_nom'], root.nom_affichage)
        self.assertEqual(roots[0]['children'][0]['ouvrages'][0]['nom'], 'Sahasaona')
        self.assertEqual(stats['total_employes'], 2)
        self.assertEqual(stats['total_relations_hierarchiques'], 1)
        self.assertEqual(stats['total_ouvrages'], 1)
        self.assertEqual(stats['total_responsables_ouvrages'], 1)

    def test_build_organigramme_data_ignores_relations_outside_scope(self):
        root = self._employe('Alice Root', poste_nom='Directeur', base_nom='Base Alpha')
        child = self._employe('Bob Child', poste_nom='Technicien', base_nom='Base Alpha')
        external = self._employe('Eve Other', poste_nom='Chef', base_nom='Base Beta', organisation_nom='Autre org')

        with patch('apps.employees.views.Ouvrage.objects.filter') as ouvrage_filter:
            ouvrage_filter.return_value.values.return_value = []
            roots, stats = _build_organigramme_data(
                [root, child],
                [
                    self._hierarchie(child, root),
                    self._hierarchie(external, root),
                ],
                [
                    self._ouvrage_relation(child, 'Sahasaona'),
                    self._ouvrage_relation(external, 'Ambondrona Nord'),
                ],
            )

        node_ids = self._collect_node_ids(roots)

        self.assertIn(root.id, node_ids)
        self.assertIn(child.id, node_ids)
        self.assertNotIn(external.id, node_ids)
        self.assertEqual(stats['total_employes'], 2)
        self.assertEqual(stats['total_ouvrages'], 1)

    def test_build_employe_organigramme_fiche_collects_descendant_ouvrages(self):
        root = self._employe('Alice Root', poste_nom='Directeur', base_nom='Base Alpha')
        child = self._employe('Bob Child', poste_nom='Technicien', base_nom='Base Alpha')
        grandchild = self._employe('Cara Grandchild', poste_nom='Agent', base_nom='Base Alpha')

        with patch('apps.employees.views.Ouvrage.objects.filter') as ouvrage_filter, patch(
            'apps.employees.views.ModaliteGestion.objects.filter'
        ) as modalite_filter:
            ouvrage_filter.return_value.values.return_value = []
            modalite_filter.return_value.filter.return_value.select_related.return_value.order_by.return_value = []

            fiche = _build_employe_organigramme_fiche(
                [root, child, grandchild],
                [
                    self._hierarchie(child, root),
                    self._hierarchie(grandchild, child),
                ],
                [
                    self._ouvrage_relation(root, 'Racine 1', principal=True),
                    self._ouvrage_relation(child, 'Child 1'),
                    self._ouvrage_relation(grandchild, 'Grandchild 1'),
                ],
                date(2026, 5, 6),
                root.id,
            )

        self.assertIsNotNone(fiche)
        self.assertEqual(fiche['employe'].id, root.id)
        self.assertEqual(fiche['subordinates_count'], 2)
        self.assertEqual(fiche['own_ouvrages_count'], 1)
        self.assertEqual(fiche['subordinate_ouvrages_count'], 2)
        self.assertEqual([item['ouvrage_nom'] for item in fiche['own_ouvrages']], ['Racine 1'])
        self.assertEqual(
            [item['owner_label'] for item in fiche['subordinates_ouvrages']],
            ['Bob Child', 'Cara Grandchild'],
        )

    def test_scope_organigramme_queryset_filters_for_superuser_with_attached_organisation(self):
        queryset = self.FakeQuerySet()
        organisation = SimpleNamespace(nom_organisation='Soakoja')
        user = SimpleNamespace(
            is_superuser=True,
            employe=SimpleNamespace(
                base=SimpleNamespace(organisation=organisation)
            ),
        )

        scoped_queryset, scoped_organisation = _scope_organigramme_queryset(queryset, user)

        self.assertIs(scoped_queryset, queryset)
        self.assertEqual(queryset.filter_kwargs, [{'base__organisation': organisation}])
        self.assertFalse(queryset.none_called)
        self.assertIs(scoped_organisation, organisation)

    def test_scope_organigramme_queryset_keeps_all_for_superuser_without_attached_organisation(self):
        queryset = self.FakeQuerySet()
        user = SimpleNamespace(
            is_superuser=True,
            employe=None,
        )

        scoped_queryset, scoped_organisation = _scope_organigramme_queryset(queryset, user)

        self.assertIs(scoped_queryset, queryset)
        self.assertEqual(queryset.filter_kwargs, [])
        self.assertFalse(queryset.none_called)
        self.assertIsNone(scoped_organisation)

    def test_filter_active_employes_queryset_only_keeps_null_date_debauchage(self):
        queryset = self.FakeQuerySet()

        filtered_queryset = _filter_active_employes_queryset(queryset)

        self.assertIs(filtered_queryset, queryset)
        self.assertEqual(queryset.filter_kwargs, [{'date_debauchage__isnull': True}])

    def test_get_mois_croise_entry_prioritizes_description_month(self):
        entry = SimpleNamespace(date_m=date(2026, 1, 5))
        info = {'mois': 12}

        self.assertEqual(_get_mois_croise_entry(entry, info), 12)

    def test_get_mois_croise_entry_falls_back_to_date_m(self):
        entry = SimpleNamespace(date_m=date(2026, 1, 5))
        info = {'mois': None}

        self.assertEqual(_get_mois_croise_entry(entry, info), 1)

    def test_get_annee_croise_entry_prioritizes_description_year(self):
        entry = SimpleNamespace(date_m=date(2026, 1, 5))
        info = {'annee': 2025}

        self.assertEqual(_get_annee_croise_entry(entry, info), 2025)


class JoursFeriesCrudTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester', password='secret123')

    def test_get_jours_feries_uses_database_source(self):
        holiday_date = date(2027, 5, 13)
        JourFerie.objects.create(date=holiday_date, nom='Ascension test', actif=True)

        self.assertIn(holiday_date, get_jours_feries(2027))
        self.assertTrue(est_jour_ferie(holiday_date))
        self.assertEqual(get_jour_ferie_label(holiday_date), 'Ascension test')

    def test_jours_feries_page_requires_login_and_loads(self):
        response = self.client.get(reverse('employees:jours_feries_list'))
        self.assertEqual(response.status_code, 302)

        self.client.login(username='tester', password='secret123')
        response = self.client.get(reverse('employees:jours_feries_list'))
        self.assertEqual(response.status_code, 200)

    def test_get_annee_croise_entry_falls_back_to_date_m_year(self):
        entry = SimpleNamespace(date_m=date(2026, 1, 5))
        info = {'annee': None}

        self.assertEqual(_get_annee_croise_entry(entry, info), 2026)


class RecuperationsYearOptionsTests(SimpleTestCase):
    def test_build_recuperation_year_choices_includes_current_window_and_data_years(self):
        years = _build_recuperation_year_choices(
            current_year=2026,
            recuperation_years=[2023, 2025],
            planning_years=[2024, 2026],
        )

        self.assertEqual(years, [2026, 2025, 2024, 2023])

    def test_get_easter_sunday_for_2026(self):
        self.assertEqual(_get_easter_sunday(2026), date(2026, 4, 5))

    def test_get_recuperation_public_holidays_for_2026(self):
        holidays = _get_recuperation_public_holidays(2026)

        self.assertIn(date(2026, 1, 1), holidays)
        self.assertIn(date(2026, 4, 3), holidays)   # Vendredi Saint
        self.assertIn(date(2026, 4, 6), holidays)   # Lundi de Paques
        self.assertIn(date(2026, 5, 14), holidays)  # Ascension
        self.assertIn(date(2026, 5, 25), holidays)  # Lundi de Pentecote
        self.assertIn(date(2026, 6, 26), holidays)


class RecuperationsEmployeSelectionScopeTests(SimpleTestCase):
    class FakeQuerySet:
        def __init__(self):
            self.filter_kwargs = []
            self.none_called = False

        def filter(self, **kwargs):
            self.filter_kwargs.append(kwargs)
            return self

        def none(self):
            self.none_called = True
            return self

    def test_non_director_selection_is_limited_to_same_base(self):
        queryset = self.FakeQuerySet()
        user = SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            employe=SimpleNamespace(
                base_id='base-1',
                poste=SimpleNamespace(nom_poste='Responsable administratif et financier'),
            ),
        )

        scoped_queryset = _filter_employes_for_selection(queryset, user)

        self.assertIs(scoped_queryset, queryset)
        self.assertEqual(queryset.filter_kwargs, [{'base_id': 'base-1'}])
        self.assertFalse(queryset.none_called)

    def test_director_selection_keeps_all_bases(self):
        queryset = self.FakeQuerySet()
        user = SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            employe=SimpleNamespace(
                base_id='base-1',
                poste=SimpleNamespace(nom_poste='Directeur'),
            ),
        )

        scoped_queryset = _filter_employes_for_selection(queryset, user)

        self.assertIs(scoped_queryset, queryset)
        self.assertEqual(queryset.filter_kwargs, [])
        self.assertFalse(queryset.none_called)
