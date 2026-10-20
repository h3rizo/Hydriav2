from contextlib import nullcontext
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.planning.views import (
    _apply_monthly_cloture_actions,
    _build_monthly_cloture_report_datetime,
    _build_duplicate_merge_group_key,
    _get_planning_monthly_cloture_selected_status,
    _coerce_merge_duplicate_bool,
    _format_paiement_forfaitaire_validity,
    _format_planning_print_date,
    _get_planning_paper_label,
    _get_paiement_forfaitaire_point_label,
    _get_planning_status_badge_class,
    _prepare_monthly_cloture_actions,
    _resolve_planning_cloture_filters,
)
from apps.planning.views_indemnites import (
    _filter_indemnites_by_requested_status,
    _get_indemnite_ui_status,
    _is_indemnite_printable_status,
    _is_indemnite_validatable_status,
)


class MobileTerrainCompletenessTests(SimpleTestCase):
    def _point(self, type_name):
        return SimpleNamespace(type_point_eau=SimpleNamespace(nom_type=type_name))

    def test_private_connection_requires_subscriber_name(self):
        from apps.planning.views_preparation_tournee import _subscriber_name_expected
        self.assertTrue(_subscriber_name_expected(self._point('Branchement privé')))
        self.assertTrue(_subscriber_name_expected(self._point('BP')))

    def test_public_point_does_not_require_subscriber_name(self):
        from apps.planning.views_preparation_tournee import _subscriber_name_expected
        self.assertFalse(_subscriber_name_expected(self._point('Borne fontaine')))
        self.assertFalse(_subscriber_name_expected(self._point('Kiosque')))

    def test_ouvrage_age_is_rounded_to_a_whole_year(self):
        from apps.planning.views_preparation_tournee import _ouvrage_age_annees

        ouvrage = SimpleNamespace(annee_realisation=2016, annee_realisation_avant=None)
        self.assertEqual(_ouvrage_age_annees(ouvrage, date(2026, 8, 27)), 10)

    def test_ouvrage_age_uses_previous_year_when_exact_year_is_missing(self):
        from apps.planning.views_preparation_tournee import _ouvrage_age_annees

        ouvrage = SimpleNamespace(annee_realisation=None, annee_realisation_avant=2000)
        self.assertEqual(_ouvrage_age_annees(ouvrage, date(2026, 8, 27)), 26)

    def test_mobile_photo_validation(self):
        import base64
        from apps.planning.views_preparation_tournee import _decode_mobile_photo

        encoded = base64.b64encode(b'jpeg-test').decode('ascii')
        data, content_type, error = _decode_mobile_photo({
            'photo_data': encoded,
            'content_type': 'image/jpeg',
        })
        self.assertEqual(data, encoded)
        self.assertEqual(content_type, 'image/jpeg')
        self.assertIsNone(error)

        _, _, invalid_error = _decode_mobile_photo({
            'photo_data': 'not-base64',
            'content_type': 'image/jpeg',
        })
        self.assertTrue(invalid_error)

    def test_mobile_photo_retry_is_idempotent(self):
        from apps.planning.views_preparation_tournee import _photo_has_local_uuid

        photos = [{'filename': 'point.jpg', 'local_uuid': 'offline-123'}]
        self.assertTrue(_photo_has_local_uuid(photos, 'offline-123'))
        self.assertFalse(_photo_has_local_uuid(photos, 'offline-456'))
        self.assertFalse(_photo_has_local_uuid(None, 'offline-123'))

    def test_mobile_point_update_retry_is_idempotent(self):
        from apps.planning.views_preparation_tournee import _point_update_matches_payload

        point = SimpleNamespace(
            nomabonne='Rakoto', numeroteleph='0340000000',
            latitude=-18.1234567, longitude=49.1234567,
        )
        self.assertTrue(_point_update_matches_payload(point, {
            'subscriber_name': 'Rakoto', 'telephone': '0340000000',
            'latitude': '-18.1234567', 'longitude': '49.1234567',
        }))
        self.assertFalse(_point_update_matches_payload(point, {'subscriber_name': 'Rabe'}))

    def test_mobile_point_server_confirmation_contains_persisted_state(self):
        from apps.planning.views_preparation_tournee import _point_server_value

        point = SimpleNamespace(
            nomabonne='Rakoto', numeroteleph='0340000000',
            latitude=-18.1, longitude=49.2,
            photos=[{'data': 'abc'}],
        )
        value = _point_server_value(point)
        self.assertTrue(value['has_coordinates'])
        self.assertTrue(value['has_photo'])
        self.assertEqual(value['subscriber_name'], 'Rakoto')

    def test_mobile_force_sync_flag_is_explicit(self):
        from apps.planning.views_preparation_tournee import _force_sync_requested

        self.assertTrue(_force_sync_requested({'force_sync': 'true'}))
        self.assertTrue(_force_sync_requested({'force_sync': '1'}))
        self.assertFalse(_force_sync_requested({}))
        self.assertFalse(_force_sync_requested({'force_sync': 'false'}))
from apps.planning.validation_permissions import can_user_adjust_planning_validation
from apps.planning.views_livraisons import (
    _get_pending_planning_detail_cutoff_date,
    _is_pending_planning_detail_visible,
)
from apps.planning.views_analyse_consommation import _visible_month_count
from apps.planning.views_simple import (
    _build_new_secondary_participant_ids,
    _find_duplicate_plannings_by_activity_label,
    _is_shared_no_ouvrage_activity_label,
    _is_planning_operation_advanced,
    _merge_planning_photo_payloads,
    _match_duplicate_planning_by_activity_label,
    _resolve_requested_validation_value,
)
from apps.planning.views_reparations import (
    _apply_employe_hierarchy_ouvrage_scope,
    _get_scoped_modalites_queryset,
)
from apps.billing.models import ModaliteGestion
from apps.organization.models import Organisation, Ouvrage, TypeOuvrage
from apps.planning.models import DebitSourceMesure


class DebitSourceDistributionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username='debit-distribution-admin',
            email='debit@example.com',
            password='testpass123',
        )
        self.client.force_login(self.user)
        ouvrage_type = TypeOuvrage.objects.create(nom_type_ouvrage='AEPG')
        self.measured = Ouvrage.objects.create(
            nom_ouvrage='Ouvrage mesuré',
            type_ouvrage=ouvrage_type,
        )
        self.unmeasured = Ouvrage.objects.create(
            nom_ouvrage='Ouvrage non mesuré',
            type_ouvrage=ouvrage_type,
        )
        DebitSourceMesure.objects.create(
            ouvrage=self.measured,
            date_visite=date(2026, 8, 1),
            debit_l_s='1.250',
        )

    @patch('apps.planning.views._get_debit_source_ouvrages_queryset')
    @patch('apps.planning.views._get_debit_source_geo_queryset_map')
    def test_distribution_includes_ouvrages_without_measurement(self, geo_mock, ouvrages_mock):
        ouvrages_qs = Ouvrage.objects.filter(
            id__in=[self.measured.id, self.unmeasured.id],
        )
        ouvrages_mock.return_value = ouvrages_qs
        geo_mock.return_value = {
            'ouvrages': ouvrages_qs, 'regions': [], 'districts': [], 'communes': [],
        }
        response = self.client.get(reverse('planning:debit_source'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['debit_status_counts']['total'], 2)
        self.assertEqual(response.context['debit_status_counts']['non_mesure'], 1)
        self.assertContains(response, 'Répartition des ouvrages par évolution')

    @patch('apps.planning.views._get_debit_source_ouvrages_queryset')
    @patch('apps.planning.views._get_debit_source_geo_queryset_map')
    def test_non_measured_stat_filters_dashboard_rows(self, geo_mock, ouvrages_mock):
        ouvrages_qs = Ouvrage.objects.filter(
            id__in=[self.measured.id, self.unmeasured.id],
        )
        ouvrages_mock.return_value = ouvrages_qs
        geo_mock.return_value = {
            'ouvrages': ouvrages_qs, 'regions': [], 'districts': [], 'communes': [],
        }
        response = self.client.get(
            reverse('planning:debit_source'),
            {'evolution': 'non_mesure'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_evolution'], 'non_mesure')
        rows = response.context['dashboard_mesures']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['ouvrage'], self.unmeasured)


class _FakeValuesListResult:
    def __init__(self, values):
        self.values = values

    def distinct(self):
        return self.values


class _FakeFilterChain:
    def __init__(self, values):
        self.values = values

    def filter(self, *args, **kwargs):
        return self

    def values_list(self, *args, **kwargs):
        return _FakeValuesListResult(self.values)


class _FakeQuerySet:
    def __init__(self):
        self.filter_kwargs = []

    def filter(self, **kwargs):
        self.filter_kwargs.append(kwargs)
        return self


class RepairHierarchyScopeTests(SimpleTestCase):
    def test_directeur_keeps_full_scope(self):
        user = SimpleNamespace(
            is_superuser=False,
            employe=SimpleNamespace(id=1),
        )

        with patch('apps.planning.views_reparations.is_directeur_poste', return_value=True):
            scoped_ids = _apply_employe_hierarchy_ouvrage_scope({1, 2, 3}, user)

        self.assertEqual(scoped_ids, {1, 2, 3})

    def test_partenaire_keeps_gestionnaire_scope_without_own_ouvrages(self):
        """Un employé partenaire n'a pas d'EmployeOuvrages : son périmètre vient de ses affectations."""
        user = SimpleNamespace(
            is_superuser=False,
            employe=SimpleNamespace(id=10),
        )
        fake_manager = SimpleNamespace(
            filter=lambda *args, **kwargs: _FakeFilterChain([])
        )

        with patch('apps.planning.views_reparations.is_directeur_poste', return_value=False), \
             patch('apps.planning.views_reparations.is_partenaire_user', return_value=True), \
             patch('apps.planning.views_reparations.EmployeOuvrages.objects', fake_manager):
            scoped_ids = _apply_employe_hierarchy_ouvrage_scope({1, 2, 3}, user)

        self.assertEqual(scoped_ids, {1, 2, 3})

    def test_non_directeur_is_limited_to_active_responsable_ouvrages(self):
        user = SimpleNamespace(
            is_superuser=False,
            employe=SimpleNamespace(id=10),
        )

        fake_manager = SimpleNamespace(
            filter=lambda *args, **kwargs: _FakeFilterChain([2, 4, 6])
        )

        with patch('apps.planning.views_reparations.is_directeur_poste', return_value=False), \
             patch('apps.planning.views_reparations._get_active_subordinate_employe_ids', return_value={10, 11, 12}), \
             patch('apps.planning.views_reparations.EmployeOuvrages.objects', fake_manager):
            scoped_ids = _apply_employe_hierarchy_ouvrage_scope({1, 2, 3, 4}, user)

        self.assertEqual(scoped_ids, {2, 4})

    def test_caissiere_can_see_same_base_responsable_ouvrages(self):
        user = SimpleNamespace(
            is_superuser=False,
            employe=SimpleNamespace(id=10, base_id='base-1'),
        )

        fake_manager = SimpleNamespace(
            filter=lambda *args, **kwargs: _FakeFilterChain([2, 5, 7])
        )

        with patch('apps.planning.views_reparations.is_directeur_poste', return_value=False), \
             patch('apps.planning.views_reparations.is_same_base_responsable_support_role', return_value=True), \
             patch('apps.planning.views_reparations.get_same_base_active_employe_ids', return_value={10, 21, 22}), \
             patch('apps.planning.views_reparations.EmployeOuvrages.objects', fake_manager):
            scoped_ids = _apply_employe_hierarchy_ouvrage_scope({1, 2, 3, 5}, user)

        self.assertEqual(scoped_ids, {2, 5})


class RepairFutureManagementScopeTests(TestCase):
    def test_future_fixed_term_management_is_available_to_repair_history(self):
        ouvrage_type = TypeOuvrage.objects.create(nom_type_ouvrage='AEPG future scope')
        ouvrage = Ouvrage.objects.create(
            nom_ouvrage='Ouvrage future scope',
            type_ouvrage=ouvrage_type,
        )
        gestionnaire = Organisation.objects.create(
            nom_organisation='Gestionnaire future scope',
            type_organisation=Organisation.TYPE_GESTIONNAIRE,
        )
        today = timezone.localdate()
        ModaliteGestion.objects.create(
            ouvrage=ouvrage,
            type_gestion='privee',
            gestionnaire=gestionnaire,
            date_debut=today.replace(year=today.year + 1),
            date_fin=today.replace(year=today.year + 2),
            statut='actif',
        )

        scoped = _get_scoped_modalites_queryset(
            str(gestionnaire.id),
            [str(gestionnaire.id)],
        )

        self.assertTrue(scoped.filter(ouvrage=ouvrage).exists())


class PlanningOperationAdvanceStatusTests(SimpleTestCase):
    def test_marks_old_pending_operation_as_advanced(self):
        self.assertTrue(
            _is_planning_operation_advanced(
                datetime(2026, 1, 1, 8, 0, 0),
                today=date(2026, 2, 5),
            )
        )

    def test_recent_pending_operation_stays_en_cours(self):
        self.assertFalse(
            _is_planning_operation_advanced(
                datetime(2026, 1, 20, 8, 0, 0),
                today=date(2026, 2, 5),
            )
        )

    def test_manual_delivery_is_considered_advanced(self):
        self.assertTrue(
            _is_planning_operation_advanced(
                datetime(2026, 2, 1, 8, 0, 0),
                livraison=True,
                today=date(2026, 2, 5),
            )
        )


class PlanningMonthlyClotureWorkflowTests(SimpleTestCase):
    def test_default_monthly_cloture_status_falls_back_to_termine(self):
        planning = SimpleNamespace(statut='en_cours')

        self.assertEqual(_get_planning_monthly_cloture_selected_status(planning), 'termine')

    def test_report_datetime_preserves_existing_time(self):
        current_datetime = timezone.make_aware(datetime(2026, 10, 15, 14, 30, 45))
        planning = SimpleNamespace(date=current_datetime)

        report_datetime = _build_monthly_cloture_report_datetime(planning, '2026-11-02')

        localized_value = timezone.localtime(report_datetime)
        self.assertEqual(localized_value.date(), date(2026, 11, 2))
        self.assertEqual(localized_value.time().replace(tzinfo=None), datetime(2026, 11, 2, 14, 30, 45).time())

    def test_prepare_actions_requires_new_date_for_report(self):
        planning = SimpleNamespace(
            id='planning-1',
            date=datetime(2026, 10, 15, 8, 0, 0),
            statut='en_cours',
            is_blocked_activity=False,
        )

        actions, errors = _prepare_monthly_cloture_actions(
            [planning],
            {'statut_planning-1': 'reporte'},
        )

        self.assertEqual(actions, [])
        self.assertEqual(len(errors), 1)
        self.assertIn('Nouvelle date obligatoire', errors[0])

    def test_apply_actions_deletes_annulees_and_reschedules_reportees(self):
        cancelled_planning = SimpleNamespace(delete=MagicMock())
        reported_planning = SimpleNamespace(
            date=datetime(2026, 10, 15, 9, 15, 0),
            statut='reporte',
            verification='papier_ecart',
            commentaire_verification='ancien commentaire',
            estvalide=True,
            save=MagicMock(),
        )
        finished_planning = SimpleNamespace(
            statut='en_cours',
            save=MagicMock(),
        )

        with patch('apps.planning.views.transaction.atomic', return_value=nullcontext()):
            summary = _apply_monthly_cloture_actions([
                {
                    'planning': cancelled_planning,
                    'selected_status': 'annule',
                    'report_datetime': None,
                },
                {
                    'planning': reported_planning,
                    'selected_status': 'reporte',
                    'report_datetime': datetime(2026, 11, 3, 9, 15, 0),
                },
                {
                    'planning': finished_planning,
                    'selected_status': 'termine',
                    'report_datetime': None,
                },
            ])

        cancelled_planning.delete.assert_called_once_with()
        reported_planning.save.assert_called_once_with()
        finished_planning.save.assert_called_once_with()
        self.assertEqual(reported_planning.date, datetime(2026, 11, 3, 9, 15, 0))
        self.assertEqual(reported_planning.statut, 'en_cours')
        self.assertEqual(reported_planning.verification, '')
        self.assertEqual(reported_planning.commentaire_verification, '')
        self.assertFalse(reported_planning.estvalide)
        self.assertEqual(finished_planning.statut, 'termine')
        self.assertEqual(summary, {'termine': 1, 'annule': 1, 'reporte': 1})


class PlanningDuplicateMergeHelperTests(SimpleTestCase):
    def test_build_duplicate_merge_group_key_uses_normalized_activity_label(self):
        planning = SimpleNamespace(
            date=datetime(2026, 4, 1, 8, 0, 0),
            ouvrage_id='ouvrage-1',
            employe_id='emp-1',
            fiche_poste_id='fiche-1',
            type_activite_id='type-1',
            fiche_poste=SimpleNamespace(tache='Nettoyage Réservoir'),
            type_activite=None,
        )

        key = _build_duplicate_merge_group_key(planning, mode='activity')

        self.assertEqual(key, (date(2026, 4, 1), 'ouvrage-1', 'nettoyage reservoir'))

    def test_build_duplicate_merge_group_key_supports_shared_no_ouvrage_holiday(self):
        planning = SimpleNamespace(
            date=datetime(2026, 5, 1, 8, 0, 0),
            ouvrage_id=None,
            employe_id='emp-1',
            fiche_poste_id='fiche-jour-ferie',
            type_activite_id='type-jour-ferie',
            fiche_poste=SimpleNamespace(tache='Jour férié'),
            type_activite=None,
            employe=SimpleNamespace(base_id='base-1'),
        )

        key = _build_duplicate_merge_group_key(planning, mode='activity')

        self.assertEqual(key, (date(2026, 5, 1), 'shared:no-ouvrage', 'jour ferie'))

    def test_build_duplicate_merge_group_key_ignores_non_shared_no_ouvrage_activity(self):
        planning = SimpleNamespace(
            date=datetime(2026, 5, 1, 8, 0, 0),
            ouvrage_id=None,
            employe_id='emp-1',
            fiche_poste_id='fiche-conge',
            type_activite_id='type-conge',
            fiche_poste=SimpleNamespace(tache='Congé'),
            type_activite=None,
            employe=SimpleNamespace(base_id='base-1'),
        )

        key = _build_duplicate_merge_group_key(planning, mode='activity')

        self.assertIsNone(key)

    def test_find_duplicate_plannings_by_activity_label_returns_all_matches(self):
        current_planning = SimpleNamespace(
            fiche_poste=SimpleNamespace(tache='Nettoyage Reservoir'),
            type_activite=None,
        )
        first_duplicate = SimpleNamespace(
            fiche_poste=SimpleNamespace(tache='Nettoyage ReseRvoir'),
            type_activite=None,
        )
        second_duplicate = SimpleNamespace(
            fiche_poste=SimpleNamespace(tache='Nettoyage Reservoir'),
            type_activite=None,
        )
        other_planning = SimpleNamespace(
            fiche_poste=SimpleNamespace(tache='Controle pompe'),
            type_activite=None,
        )

        matches = _find_duplicate_plannings_by_activity_label(
            [first_duplicate, other_planning, second_duplicate],
            planning=current_planning,
        )

        self.assertEqual(matches, [first_duplicate, second_duplicate])

    def test_match_duplicate_planning_uses_normalized_activity_label(self):
        requested_fiche = SimpleNamespace(tache='Nettoyage Réservoir')
        duplicate_planning = SimpleNamespace(
            fiche_poste=SimpleNamespace(tache='Nettoyage Reservoir'),
            type_activite=None,
        )
        other_planning = SimpleNamespace(
            fiche_poste=SimpleNamespace(tache='Autre tache'),
            type_activite=None,
        )

        match = _match_duplicate_planning_by_activity_label(
            [other_planning, duplicate_planning],
            fiche_poste=requested_fiche,
        )

        self.assertIs(match, duplicate_planning)

    def test_build_new_secondary_participant_ids_excludes_owner_existing_and_duplicates(self):
        planning = SimpleNamespace(employe_id='chef-1')

        new_ids = _build_new_secondary_participant_ids(
            planning,
            'agent-2',
            ['agent-3', 'agent-2', 'chef-1', 'agent-4', 'agent-4'],
            existing_participant_ids=['agent-3'],
        )

        self.assertEqual(new_ids, ['agent-2', 'agent-4'])

    def test_shared_no_ouvrage_activity_label_only_allows_holidays(self):
        self.assertTrue(_is_shared_no_ouvrage_activity_label('Jour férié'))
        self.assertFalse(_is_shared_no_ouvrage_activity_label('Congé'))

    def test_merge_planning_photo_payloads_keeps_unique_entries(self):
        primary_photo = '[{"name":"a.jpg","size":10,"date":"2026-04-01","data":"img-a"}]'
        duplicate_photos = [
            '[{"name":"a.jpg","size":10,"date":"2026-04-01","data":"img-a"}]',
            '[{"name":"b.jpg","size":11,"date":"2026-04-02","data":"img-b"}]',
        ]

        merged = _merge_planning_photo_payloads(primary_photo, duplicate_photos)

        self.assertEqual(
            merged,
            '[{"name": "a.jpg", "size": 10, "date": "2026-04-01", "data": "img-a"}, {"name": "b.jpg", "size": 11, "date": "2026-04-02", "data": "img-b"}]',
        )

    def test_coerce_merge_duplicate_bool_supports_yes_and_no(self):
        self.assertTrue(_coerce_merge_duplicate_bool('oui'))
        self.assertFalse(_coerce_merge_duplicate_bool('non'))


class PlanningValidationPermissionTests(SimpleTestCase):
    def _make_user(self, employe_id, poste='Technicien', *, superuser=False):
        return SimpleNamespace(
            is_authenticated=True,
            is_superuser=superuser,
            employe=SimpleNamespace(
                id=employe_id,
                poste=SimpleNamespace(nom_poste=poste),
            ),
        )

    def test_superieur_direct_peut_valider_un_subordonne(self):
        user = self._make_user('chef-1')
        planning = SimpleNamespace(employe_id='agent-1')

        with patch(
            'apps.planning.validation_permissions.get_planning_validation_target_employe_ids',
            return_value={'agent-1'},
        ):
            self.assertTrue(can_user_adjust_planning_validation(user, planning))

    def test_superieur_indirect_peut_valider_un_subordonne_niveau_2(self):
        user = self._make_user('chef-1')
        planning = SimpleNamespace(employe_id='agent-2')

        with patch(
            'apps.planning.validation_permissions.get_planning_validation_target_employe_ids',
            return_value={'agent-1', 'agent-2'},
        ):
            self.assertTrue(can_user_adjust_planning_validation(user, planning))

    def test_employe_ne_peut_pas_valider_son_propre_planning(self):
        user = self._make_user('agent-1')
        planning = SimpleNamespace(employe_id='agent-1')

        self.assertFalse(can_user_adjust_planning_validation(user, planning))

    def test_directeur_peut_valider_son_propre_planning(self):
        user = self._make_user('dir-1', poste='Directeur')
        planning = SimpleNamespace(employe_id='dir-1')

        self.assertTrue(can_user_adjust_planning_validation(user, planning))


class PlanningValidationPayloadTests(SimpleTestCase):
    def test_missing_validation_keeps_current_value(self):
        value, provided = _resolve_requested_validation_value({}, current_validation=True)

        self.assertTrue(value)
        self.assertFalse(provided)

    def test_string_true_is_coerced(self):
        value, provided = _resolve_requested_validation_value(
            {'validation': 'true'},
            current_validation=False,
        )

        self.assertTrue(value)
        self.assertTrue(provided)

    def test_string_false_is_coerced(self):
        value, provided = _resolve_requested_validation_value(
            {'validation': 'false'},
            current_validation=True,
        )

        self.assertFalse(value)
        self.assertTrue(provided)


class PlanningIndemnitesWorkflowTests(SimpleTestCase):
    def test_get_indemnite_ui_status_maps_legacy_advance_to_validee(self):
        self.assertEqual(_get_indemnite_ui_status('avancee'), 'validee')
        self.assertEqual(_get_indemnite_ui_status('confirmee'), 'validee')
        self.assertEqual(_get_indemnite_ui_status('calculee'), 'calculee')

    def test_filter_indemnites_by_requested_status_expands_validee(self):
        queryset = _FakeQuerySet()

        filtered = _filter_indemnites_by_requested_status(queryset, 'validee')

        self.assertIs(filtered, queryset)
        self.assertEqual(queryset.filter_kwargs, [{'statut__in': ('avancee', 'confirmee')}])

    def test_indemnite_status_flags_match_simplified_workflow(self):
        self.assertTrue(_is_indemnite_validatable_status('calculee'))
        self.assertFalse(_is_indemnite_validatable_status('confirmee'))
        self.assertTrue(_is_indemnite_printable_status('avancee'))
        self.assertTrue(_is_indemnite_printable_status('confirmee'))
        self.assertFalse(_is_indemnite_printable_status('calculee'))


class GestionAvancesVisibilityTests(SimpleTestCase):
    def test_pending_planning_detail_cutoff_date_uses_30_days(self):
        self.assertEqual(
            _get_pending_planning_detail_cutoff_date(today=date(2026, 3, 29)),
            date(2026, 2, 27),
        )

    def test_old_unprocessed_detail_is_hidden_from_pending_list(self):
        self.assertFalse(
            _is_pending_planning_detail_visible(
                datetime(2026, 2, 20, 8, 0, 0),
                today=date(2026, 3, 29),
            )
        )

    def test_recent_unprocessed_detail_stays_visible(self):
        self.assertTrue(
            _is_pending_planning_detail_visible(
                datetime(2026, 3, 10, 8, 0, 0),
                today=date(2026, 3, 29),
            )
        )


class PlanningClotureHelperTests(SimpleTestCase):
    def test_status_badge_mapping_returns_expected_class(self):
        self.assertEqual(_get_planning_status_badge_class('termine'), 'badge-success')
        self.assertEqual(_get_planning_status_badge_class('annule'), 'badge-error')
        self.assertEqual(_get_planning_status_badge_class('inconnu'), 'badge-ghost')

    def test_paper_label_mapping_returns_known_or_raw_label(self):
        self.assertEqual(_get_planning_paper_label('papier_conforme'), 'Conforme au papier')
        self.assertEqual(_get_planning_paper_label(''), 'Non renseigne')
        self.assertEqual(_get_planning_paper_label('controle libre'), 'controle libre')

    def test_resolve_cloture_filters_defaults_employee_for_non_director(self):
        user = SimpleNamespace(
            is_authenticated=True,
            employe=SimpleNamespace(id='emp-1', poste=SimpleNamespace(nom_poste='Technicien')),
        )

        with patch('apps.planning.views.timezone.localdate', return_value=date(2026, 3, 29)):
            filters = _resolve_planning_cloture_filters(user, {})

        self.assertEqual(filters['employe_value'], 'emp-1')
        self.assertEqual(filters['mois_value'], '2026-03')

    def test_resolve_cloture_filters_keeps_blank_employee_for_director(self):
        user = SimpleNamespace(
            is_authenticated=True,
            employe=SimpleNamespace(id='dir-1', poste=SimpleNamespace(nom_poste='Directeur')),
        )

        filters = _resolve_planning_cloture_filters(user, {'mois': '2026-02'})

        self.assertEqual(filters['employe_value'], '')
        self.assertEqual(filters['mois_value'], '2026-02')


class PlanningPrintHelperTests(SimpleTestCase):
    def test_point_label_prefers_forfaitaire_display_label(self):
        point_eau = SimpleNamespace(
            forfaitaire_display_label='PE-12 - Andapa',
            nomabonne='Nom abonne',
            code_point_eau='PE-12',
        )

        self.assertEqual(
            _get_paiement_forfaitaire_point_label(point_eau),
            'PE-12 - Andapa',
        )

    def test_format_validity_uses_start_and_end_dates(self):
        paiement = SimpleNamespace(
            date_debut_validite=date(2026, 4, 1),
            date_fin_validite=date(2026, 6, 30),
        )

        self.assertEqual(
            _format_paiement_forfaitaire_validity(paiement),
            '01/04/2026 -> 30/06/2026',
        )

    def test_format_print_date_supports_plain_date(self):
        self.assertEqual(
            _format_planning_print_date(date(2026, 4, 1)),
            '01/04/2026',
        )


class ConsumptionChartMonthVisibilityTests(SimpleTestCase):
    def test_current_year_stops_before_current_month(self):
        reference = datetime(2026, 8, 25, 12, 0)
        self.assertEqual(_visible_month_count(2026, reference), 7)

    def test_january_has_no_completed_month(self):
        reference = datetime(2026, 1, 15, 12, 0)
        self.assertEqual(_visible_month_count(2026, reference), 0)

    def test_past_year_keeps_all_months(self):
        reference = datetime(2026, 8, 25, 12, 0)
        self.assertEqual(_visible_month_count(2025, reference), 12)

    def test_future_year_has_no_visible_month(self):
        reference = datetime(2026, 8, 25, 12, 0)
        self.assertEqual(_visible_month_count(2027, reference), 0)
