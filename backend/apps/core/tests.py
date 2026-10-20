from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.test import TestCase
from django.urls import reverse

from django.test import SimpleTestCase, override_settings

from apps.core.models import (
    CalculationRule,
    DocumentationChangeLog,
    DocumentationModule,
    IndicatorDefinition,
    KnownLimitation,
    PartnerQuarterlyReportArchive,
    RepairActivityEquipmentPolicy,
    RepairActivityPointTypePolicy,
    TestExecution,
    TestProtocol,
    partner_report_archive_upload_to,
)
from apps.billing.models import TypePointEau
from apps.employees.models import FichePoste
from apps.infrastructure.models import TypeEquipement
from apps.planning.models import TypeActivite
from apps.core.partner_report_archives import (
    _build_archive_filename,
    _build_partner_report_docx_bytes,
)
from apps.core.views_villages_desserte import _summarize_village_desserte
from apps.core.views_ouvrage_interventions import (
    _activity_allowed_for_target,
    _activity_deadline_bucket,
    _activity_matches_target,
    _activity_target_metadata,
    _is_repair_or_rehabilitation_activity,
    _is_pmh_ouvrage,
    _requires_signalement_date,
    _quick_point_eau_sort_key,
    _quick_point_eau_label,
)
from apps.planning.repair_classification import is_excluded_repair_activity


class OperationalWidgetApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username='operational-widget-admin',
            email='widget@example.com',
            password='testpass123',
        )
        self.client.force_login(self.user)

    @patch('apps.core.views_widget._head_meter_widget_rows')
    def test_head_meter_widget_counts_and_filters_critical_rows(self, rows_mock):
        rows_mock.return_value = [
            {'status': 'good', 'compteur_status': 'actif', 'label': 'C1', 'sub': 'O1'},
            {'status': 'critical', 'compteur_status': 'actif', 'label': 'C2', 'sub': 'O2'},
            {'status': 'non_mesure', 'compteur_status': 'hors_service', 'label': 'C3', 'sub': 'O3'},
        ]

        response = self.client.get(
            reverse('core:api_widget_compteurs_tete'),
            {'status': 'critical'},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['stats']['total'], 3)
        self.assertEqual(payload['stats']['critical'], 1)
        self.assertEqual(payload['stats']['non_mesure'], 1)
        self.assertEqual(payload['total'], 1)
        self.assertEqual(payload['rows'][0]['label'], 'C2')

        hors_service_response = self.client.get(
            reverse('core:api_widget_compteurs_tete'),
            {'status': 'hors_service'},
        )
        hors_service_payload = hors_service_response.json()
        self.assertEqual(hors_service_payload['total'], 1)
        self.assertEqual(hors_service_payload['rows'][0]['label'], 'C3')

    @patch('apps.core.views_widget._debit_source_widget_rows')
    def test_debit_widget_counts_unmeasured_and_filters_declines(self, rows_mock):
        rows_mock.return_value = [
            {'status': 'baisse', 'label': 'O1', 'sub': '-0.2 L/s'},
            {'status': 'stable', 'label': 'O2', 'sub': '0 L/s'},
            {'status': 'non_mesure', 'label': 'O3', 'sub': 'Aucune mesure'},
        ]

        response = self.client.get(
            reverse('core:api_widget_debits_source'),
            {'status': 'baisse'},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['stats']['total'], 3)
        self.assertEqual(payload['stats']['baisse'], 1)
        self.assertEqual(payload['stats']['non_mesure'], 1)
        self.assertEqual(payload['total'], 1)
        self.assertEqual(payload['rows'][0]['label'], 'O1')

    def test_consumption_widget_maps_widget_filters_to_analysis_filters(self):
        def fake_analysis(request):
            self.assertEqual(request.GET.get('format'), 'widget_json')
            self.assertEqual(request.GET.getlist('regions'), ['region-1'])
            self.assertEqual(request.GET.getlist('communes'), ['commune-1'])
            self.assertNotIn('region_id', request.GET)
            return JsonResponse({
                'success': True,
                'stats': {'nb_ouvrages': 2, 'population': 40},
                'charts': {'labels': ['Jan'], 'volumes': [12.5], 'conso_hab': [10.1]},
            })

        wrapped_view = SimpleNamespace(__wrapped__=fake_analysis)
        with patch('apps.planning.views_analyse_consommation.analyse_consommation', wrapped_view):
            response = self.client.get(
                reverse('core:api_widget_analyse_consommation'),
                {'region_id': 'region-1', 'commune_id': 'commune-1'},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])


class QuickRepairActivityFilteringTests(SimpleTestCase):
    def setUp(self):
        self.equipment_types = [
            {"id": "captage-id", "nom_type": "Captage"},
            {"id": "pompe-id", "nom_type": "Pompe immergée"},
        ]

    def test_commune_relations_activity_is_excluded_with_a_suffix(self):
        self.assertTrue(is_excluded_repair_activity(
            "Entretien des relations avec les communes rurales : suivi annuel"
        ))

    def test_signalement_date_is_required_only_for_breakdown_repair(self):
        self.assertTrue(_requires_signalement_date("Réparation panne"))
        self.assertTrue(_requires_signalement_date("Reparation panne"))
        self.assertFalse(_requires_signalement_date("Réparation simple"))
        self.assertFalse(_requires_signalement_date("Diagnostique réparation"))

    def test_deadline_counters_separate_repair_types_from_other_activities(self):
        def planning(type_name, planning_date):
            return SimpleNamespace(
                date=planning_date,
                fiche_poste=SimpleNamespace(
                    type_activites=SimpleNamespace(nomtype=type_name),
                    tache="Activite test",
                ),
                type_activite=None,
            )

        today = date(2026, 9, 5)
        cases = (
            ("Reparation", datetime(2026, 9, 4, 8), "repair_overdue"),
            ("Rehabilitation", datetime(2026, 9, 5, 8), "repair_upcoming"),
            ("Entretien", datetime(2026, 9, 1, 8), "other_overdue"),
            ("Nettoyage", datetime(2026, 9, 8, 8), "other_upcoming"),
        )
        for type_name, planning_date, expected in cases:
            with self.subTest(type_name=type_name):
                self.assertEqual(
                    _activity_deadline_bucket(planning(type_name, planning_date), today),
                    expected,
                )

    def test_repair_counter_uses_type_before_task_label(self):
        entretien = SimpleNamespace(
            fiche_poste=SimpleNamespace(
                type_activites=SimpleNamespace(nomtype="Entretien"),
                tache="Reparation simple",
            ),
            type_activite=None,
        )

        self.assertFalse(_is_repair_or_rehabilitation_activity(entretien))

    def test_point_eau_target_label_uses_idxls_and_subscriber_name(self):
        point = SimpleNamespace(
            id="point-id",
            idxls="IDX-245",
            nomabonne="Association du village",
            code_point_eau="PE-001",
        )
        self.assertEqual(
            _quick_point_eau_label(point),
            "245 — Association du village",
        )

    def test_point_eau_target_label_has_safe_fallbacks(self):
        point = SimpleNamespace(
            id="point-id",
            idxls="",
            nomabonne="Abonné sans IDXls",
            code_point_eau="PE-002",
        )
        self.assertEqual(_quick_point_eau_label(point), "Abonné sans IDXls")

    def test_point_eau_idxls_is_padded_and_sorted_numerically(self):
        points = [
            SimpleNamespace(id="20", idxls="IDXL-20", nomabonne="Vingt", code_point_eau=""),
            SimpleNamespace(id="2", idxls="2", nomabonne="Deux", code_point_eau=""),
            SimpleNamespace(id="1", idxls="IDXls: 1", nomabonne="Un", code_point_eau=""),
        ]

        sorted_points = sorted(points, key=_quick_point_eau_sort_key)

        self.assertEqual(
            [_quick_point_eau_label(point) for point in sorted_points],
            ["01 — Un", "02 — Deux", "20 — Vingt"],
        )

    def test_captage_activity_only_matches_a_captage_equipment(self):
        metadata = _activity_target_metadata(
            "Décapage de zone de captage",
            self.equipment_types,
        )

        self.assertEqual(metadata["equipment_type_ids"], ["captage-id"])
        self.assertTrue(_activity_matches_target(metadata, "equipement", "captage-id"))
        self.assertFalse(_activity_matches_target(metadata, "equipement", "pompe-id"))
        self.assertFalse(_activity_matches_target(metadata, "point_eau"))

    def test_generic_activity_remains_available_for_every_target(self):
        metadata = _activity_target_metadata("Entretien général", self.equipment_types)

        self.assertTrue(_activity_matches_target(metadata, "equipement", "captage-id"))
        self.assertTrue(_activity_matches_target(metadata, "point_eau"))

    def test_pmh_ouvrage_activity_policy(self):
        self.assertTrue(_is_pmh_ouvrage("FPMH"))
        self.assertTrue(_activity_allowed_for_target(
            "Graissage PMH", "FPMH", "point_eau"
        ))
        self.assertTrue(_activity_allowed_for_target(
            "Contrôle des travaux et paiement", "PPMH", "point_eau"
        ))
        self.assertTrue(_activity_allowed_for_target(
            "Mise à jour des cahiers fanarahamaso", "PMH", "point_eau"
        ))
        self.assertFalse(_activity_allowed_for_target(
            "Réparation fuite", "PMH", "point_eau"
        ))
        self.assertFalse(_activity_allowed_for_target(
            "Réparation citerne PMH", "PMH", "point_eau"
        ))
        self.assertFalse(_activity_allowed_for_target(
            "Graissage PMH", "AEPG", "point_eau"
        ))
        self.assertFalse(_activity_allowed_for_target(
            "Réparation simple", "PMH", "equipement", "Captage"
        ))

    def test_non_pmh_point_eau_activity_policy(self):
        self.assertTrue(_activity_allowed_for_target(
            "Réparation : Remplacement des robinets, manchons, vanne d'arrêt",
            "AEPG",
            "point_eau",
        ))
        self.assertFalse(_activity_allowed_for_target(
            "Enterrement des tuyaux", "AEPG", "point_eau"
        ))

    def test_captage_policy_accepts_captage_and_shared_activities(self):
        self.assertTrue(_activity_allowed_for_target(
            "Décapage de zone de captage", "AEPG", "equipement", "Captage"
        ))
        self.assertTrue(_activity_allowed_for_target(
            "Protection BV", "AEPG", "equipement", "Captage"
        ))
        self.assertTrue(_activity_allowed_for_target(
            "Nettoyage des citernes et boîtes", "AEPG", "equipement", "Captage"
        ))
        self.assertFalse(_activity_allowed_for_target(
            "Enterrement des tuyaux", "AEPG", "equipement", "Captage"
        ))

    def test_adduction_and_masonry_equipment_policies(self):
        self.assertTrue(_activity_allowed_for_target(
            "Enterrement des tuyaux", "AEPG", "equipement", "Conduite d'adduction"
        ))
        self.assertFalse(_activity_allowed_for_target(
            "Protection BV", "AEPG", "equipement", "Distribution"
        ))
        self.assertTrue(_activity_allowed_for_target(
            "Réparation maçonnerie", "AEPG", "equipement", "Brise-charge"
        ))
        self.assertTrue(_activity_allowed_for_target(
            "Vérification débit", "AEPG", "equipement", "Dessableur"
        ))
        for equipment_type in ("Répartiteur", "Brise-charge", "Regard", "Dessableur"):
            with self.subTest(equipment_type=equipment_type):
                self.assertTrue(_activity_allowed_for_target(
                    "Nettoyage des citernes et boîtes",
                    "AEPG",
                    "equipement",
                    equipment_type,
                ))


class RepairActivityEquipmentPermissionsViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff_user = get_user_model().objects.create_user(
            username="repair-policy-admin",
            password="secret123",
            is_staff=True,
        )
        cls.regular_user = get_user_model().objects.create_user(
            username="repair-policy-user",
            password="secret123",
        )
        cls.equipment_type = TypeEquipement.objects.create(nom_type="Captage test")
        cls.point_type = TypePointEau.objects.create(nom_type="Borne fontaine test")
        cls.activity_type = TypeActivite.objects.create(nomtype="Réparation")
        cls.activity = FichePoste.objects.create(
            type_activites=cls.activity_type,
            tache="Réparation simple",
            description="Test",
        )

    def test_staff_can_open_and_save_equipment_policy(self):
        self.client.force_login(self.staff_user)
        url = reverse("core:repair_activity_equipment_permissions")

        response = self.client.get(url, {"type": self.equipment_type.id})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Captage test")
        self.assertContains(response, "Réparation simple")

        response = self.client.post(url, {
            "target_kind": "equipement",
            "target_type_id": str(self.equipment_type.id),
            "activities": [str(self.activity.id)],
            "action": "save",
        })
        self.assertEqual(response.status_code, 302)
        policy = RepairActivityEquipmentPolicy.objects.get(
            type_equipement=self.equipment_type,
        )
        self.assertEqual(list(policy.allowed_activities.all()), [self.activity])

    def test_staff_can_save_an_empty_policy_and_reset_it(self):
        self.client.force_login(self.staff_user)
        url = reverse("core:repair_activity_equipment_permissions")

        self.client.post(url, {
            "target_kind": "equipement",
            "target_type_id": str(self.equipment_type.id),
            "action": "save",
        })
        policy = RepairActivityEquipmentPolicy.objects.get(
            type_equipement=self.equipment_type,
        )
        self.assertEqual(policy.allowed_activities.count(), 0)

        self.client.post(url, {
            "target_kind": "equipement",
            "target_type_id": str(self.equipment_type.id),
            "action": "reset",
        })
        self.assertFalse(RepairActivityEquipmentPolicy.objects.filter(
            type_equipement=self.equipment_type,
        ).exists())

    def test_staff_can_open_and_save_point_type_policy(self):
        self.client.force_login(self.staff_user)
        url = reverse("core:repair_activity_equipment_permissions")

        response = self.client.get(url, {
            "target": "point_eau",
            "type": self.point_type.id,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Borne fontaine test")
        self.assertContains(response, "Points d'eau")

        response = self.client.post(url, {
            "target_kind": "point_eau",
            "target_type_id": str(self.point_type.id),
            "activities": [str(self.activity.id)],
            "action": "save",
        })
        self.assertEqual(response.status_code, 302)
        policy = RepairActivityPointTypePolicy.objects.get(
            type_point_eau=self.point_type,
        )
        self.assertEqual(list(policy.allowed_activities.all()), [self.activity])

    def test_regular_user_cannot_open_policy_page(self):
        self.client.force_login(self.regular_user)
        response = self.client.get(
            reverse("core:repair_activity_equipment_permissions")
        )
        self.assertEqual(response.status_code, 302)


class DashboardPaymentsFlatControlFilterTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username='admin_dashboard_forfaitaire',
            email='admin.dashboard.forfaitaire@example.com',
            password='testpass123',
        )
        self.client.force_login(self.user)

    def test_control_card_filter_is_exposed_and_rendered(self):
        response = self.client.get(
            reverse('core:dashboard_payments_flat'),
            {'controle_tranches': 'a_completer'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['controle_tranches_filter'], 'a_completer')
        self.assertContains(response, "toggleControleTranchesFilter('a_completer')")
        self.assertContains(response, 'Filtre actif')
        self.assertContains(response, 'modal-forfaitaire-pointage-target')
        self.assertContains(response, 'modal-forfaitaire-select-all-btn')
        self.assertContains(response, 'toggleAllSelectableForfaitairePaiements')
        self.assertContains(response, 'max-w-[96vw]')
        self.assertContains(response, 'Paiements forfaitaires a pointer')
        self.assertContains(response, 'Lignes comptables DiameX')
        self.assertContains(response, 'modal-forfaitaire-en-eau-count')
        self.assertContains(response, 'modal-forfaitaire-coupes-count')
        self.assertContains(response, 'updateForfaitaireCoupureCounts')

    def test_invalid_control_filter_is_ignored(self):
        response = self.client.get(
            reverse('core:dashboard_payments_flat'),
            {'controle_tranches': 'invalide'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['controle_tranches_filter'], '')

    def test_score_gap_filter_is_exposed_and_rendered(self):
        response = self.client.get(
            reverse('core:dashboard_payments_flat'),
            {'score_ecart': '1'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['show_only_score_gap'])
        self.assertContains(response, 'toggleScoreGapFilter()')
        self.assertContains(response, 'name="score_ecart" value="1"')

    def test_overdue_filter_distinguishes_previous_and_current_month(self):
        previous_response = self.client.get(
            reverse('core:dashboard_payments_flat'),
            {'impayes_echus': 'avant_mois'},
        )
        current_response = self.client.get(
            reverse('core:dashboard_payments_flat'),
            {'impayes_echus': 'mois_courant'},
        )

        self.assertEqual(previous_response.status_code, 200)
        self.assertEqual(previous_response.context['impayes_echus_mode'], 'avant_mois')
        self.assertEqual(current_response.status_code, 200)
        self.assertEqual(current_response.context['impayes_echus_mode'], 'mois_courant')
        self.assertEqual(
            previous_response.context['nb_points_eau_stats'],
            previous_response.context['nb_tout_paye']
            + previous_response.context['nb_partiellement_paye']
            + previous_response.context['nb_non_paye']
            + previous_response.context['nb_coupe'],
        )
        self.assertContains(previous_response, "toggleImpayesEchusFilter('avant_mois')")
        self.assertContains(current_response, "toggleImpayesEchusFilter('mois_courant')")
        self.assertContains(previous_response, 'Annuler le filtre')
        self.assertContains(previous_response, 'clearQuickDashboardFilters')


class PartnerQuarterlyReportArchiveTests(SimpleTestCase):
    def test_upload_to_preserves_word_extension(self):
        archive_stub = SimpleNamespace(
            organisation_id='org-123',
            report_year=2026,
            report_quarter=1,
            scope_key='commune:abc',
        )

        result = partner_report_archive_upload_to(archive_stub, 'rapport-final.docx')

        self.assertEqual(
            result,
            'partner_report_archives/org-123/2026/T1/commune_abc.docx',
        )

    def test_upload_to_defaults_to_docx_without_extension(self):
        archive_stub = SimpleNamespace(
            organisation_id='org-123',
            report_year=2026,
            report_quarter=3,
            scope_key='organisation:all',
        )

        result = partner_report_archive_upload_to(archive_stub, 'rapport-final')

        self.assertEqual(
            result,
            'partner_report_archives/org-123/2026/T3/organisation_all.docx',
        )

    def test_word_file_properties_detect_extension(self):
        archive = PartnerQuarterlyReportArchive()
        archive.document_file.name = 'partner_report_archives/org-123/2026/T1/commune_abc.docx'

        self.assertEqual(archive.file_extension, '.docx')
        self.assertTrue(archive.is_word_document)

        archive.document_file.name = 'partner_report_archives/org-123/2026/T1/commune_abc.pdf'

        self.assertEqual(archive.file_extension, '.pdf')
        self.assertFalse(archive.is_word_document)

    def test_build_archive_filename_uses_docx_extension(self):
        archive_stub = SimpleNamespace(
            organisation=SimpleNamespace(nom_organisation='Soakoja'),
            report_quarter=2,
            report_year=2026,
            region_id=None,
            district_id=None,
            commune_id=None,
            region=None,
            district=None,
            commune=None,
        )

        filename = _build_archive_filename(archive_stub)

        self.assertEqual(
            filename,
            'rapport-partenaires-Soakoja-T2-2026-organisation.docx',
        )

    def test_build_partner_report_docx_bytes_returns_docx_archive(self):
        context = {
            'report_identity': {
                'organisation_label': 'Soakoja',
                'scope_level_label': 'Organisation',
                'scope_label': 'Soakoja',
                'region_label': '',
                'district_label': '',
                'commune_label': '',
                'period_label': 'T1 2026',
            },
            'generated_at': '18/03/2026 10:00',
            'dashboard_data': {
                'stat_sections': [],
                'modalite_rows': [],
                'is_commune_detail_mode': False,
                'stats_par_commune_groups': [],
                'ouvrage_detail_visible_columns': {},
                'ouvrage_detail_rows': [],
            },
            'visites_data': {
                'nb_ouvrages': 0,
                'total_visites': 0,
                'total_visites_reparation': 0,
                'total_visites_reparation_panne': 0,
                'moyenne_visites': 0,
                'median_visites': 0,
            },
            'grading_data': {
                'stats': {
                    'ouvrages_filtres': 0,
                    'avec_grading_from': 0,
                    'avec_grading_to': 0,
                    'avec_deux_annees': 0,
                    'uniquement_depart': 0,
                    'uniquement_arrivee': 0,
                },
                'dist_from_rows': [],
                'dist_to_rows': [],
                'transition_top': [],
            },
            'recettes_data': {
                'stats_global': {
                    'total_prevu': 0,
                    'total_paye': 0,
                    'ecart': 0,
                    'taux_recouvrement': 0,
                    'nb_ouvrages_total': 0,
                },
                'categories': [],
                'communes_breakdown': [],
            },
            'representants_data': {
                'stats': {
                    'nb_representants': 0,
                    'total_avis': 0,
                    'total_points_negatifs': 0,
                    'taux_negatif_global': 0,
                    'satisfaction_moyenne': 0,
                    'score_moyen_global': 0,
                },
                'yearly_rows': [],
            },
        }

        document_bytes = _build_partner_report_docx_bytes(context)

        self.assertTrue(document_bytes.startswith(b'PK'))


class VillageDesserteSummaryTests(SimpleTestCase):
    def test_summarize_village_desserte_splits_levels_consistently(self):
        summary = _summarize_village_desserte(
            all_village_ids={'v1', 'v2', 'v3', 'v4', 'v5'},
            served_ids={'v1', 'v2', 'v3'},
            functional_ids={'v1', 'v3', 'vx'},
            requested_ids={'v4', 'v9'},
        )

        self.assertEqual(summary['total_count'], 5)
        self.assertEqual(summary['served_count'], 3)
        self.assertEqual(summary['non_served_count'], 2)
        self.assertEqual(summary['functional_count'], 2)
        self.assertEqual(summary['non_functional_count'], 1)
        self.assertEqual(summary['requested_count'], 1)
        self.assertEqual(summary['without_request_count'], 1)
        self.assertEqual(summary['non_functional_ids'], {'v2'})
        self.assertEqual(summary['without_request_ids'], {'v5'})


class DocumentationProtocolsViewsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.user = user_model.objects.create_user(username='doc-user', password='secret123')
        cls.admin_user = user_model.objects.create_user(
            username='doc-admin',
            password='secret123',
            is_staff=True,
        )

        cls.module = DocumentationModule.objects.create(
            # Module principal neutre : les vrais modules Planning sont
            # volontairement rediriges vers planning.hydria.mg.
            slug='operations',
            workspace=DocumentationModule.WORKSPACE_MAIN,
            name='Operations',
            short_name='Operations',
            objective='Piloter les plannings et les operations terrain.',
            target_audience='Agents terrain, validateurs et responsables.',
            data_used='Planning, activites, employes, ouvrages.',
            pages_in_scope=['/plannings/', '/plannings/avances/'],
            buttons=['Valider un planning', 'Imprimer recap depart'],
            filters=['Filtre par mois', 'Filtre par employe'],
            tables=['Table des plannings', 'Table des avances'],
            statistics=['Nombre de plannings valides'],
            charts=['Charge par agent'],
            calculation_rules_text='Sommes des montants des lignes selectionnees.',
            validation_status=DocumentationModule.STATUS_VALIDATED,
            is_priority=True,
        )
        IndicatorDefinition.objects.create(
            module=cls.module,
            name='Taux de couverture planning',
            slug='taux-couverture-planning',
            objective='Mesurer le niveau de planification.',
            formula='plannings valides / plannings prevus',
        )
        CalculationRule.objects.create(
            module=cls.module,
            title='Calcul avance a faire',
            description='Difference entre total avances et total recettes.',
            formula='max(0, total avances - total recettes)',
        )
        KnownLimitation.objects.create(
            module=cls.module,
            title='Dependance aux donnees de planning',
            description='Les plannings non valides ne remontent pas dans certaines vues.',
        )
        cls.protocol = TestProtocol.objects.create(
            code='PL-001',
            module=cls.module,
            test_type=TestProtocol.TYPE_FUNCTIONAL,
            objective='Verifier le chargement de la page plannings.',
            preconditions='Utilisateur connecte.',
            required_data='Un planning valide.',
            steps='1. Ouvrir la page. 2. Verifier le tableau.',
            expected_result='La page se charge.',
            last_result='La page se charge correctement.',
            status=TestProtocol.STATUS_SUCCESS,
            criticality=TestProtocol.CRITICALITY_HIGH,
            executed_by_name='Equipe QA',
        )
        TestExecution.objects.create(
            protocol=cls.protocol,
            status=TestProtocol.STATUS_SUCCESS,
            executed_by_name='Equipe QA',
            result_obtained='Chargement OK',
        )
        cls.failed_protocol = TestProtocol.objects.create(
            code='PL-002',
            module=cls.module,
            test_type=TestProtocol.TYPE_FILTER,
            objective='Verifier les filtres.',
            expected_result='Les filtres restreignent le tableau.',
            status=TestProtocol.STATUS_FAILED,
            criticality=TestProtocol.CRITICALITY_CRITICAL,
        )
        cls.payroll_module = DocumentationModule.objects.create(
            slug='fiches-paie',
            workspace=DocumentationModule.WORKSPACE_PAYROLL,
            name='Fiches de paie',
            short_name='Paie',
            objective='Documenter le circuit de paie.',
            target_audience='RH et comptabilite sociale.',
            data_used='Employes, bulletins, retenues.',
            validation_status=DocumentationModule.STATUS_VALIDATED,
        )
        cls.payroll_protocol = TestProtocol.objects.create(
            code='PAY-001',
            module=cls.payroll_module,
            test_type=TestProtocol.TYPE_FUNCTIONAL,
            objective='Verifier le chargement des fiches de paie.',
            expected_result='La page paie se charge.',
            status=TestProtocol.STATUS_SUCCESS,
            criticality=TestProtocol.CRITICALITY_MEDIUM,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_documentation_protocols_home_loads(self):
        response = self.client.get(reverse('core:documentation_protocols_home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Documentation &amp; Protocoles')

    def test_documentation_module_list_loads(self):
        response = self.client.get(reverse('core:documentation_module_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Operations')
        self.assertNotContains(response, 'Fiches de paie')

    @override_settings(ALLOWED_HOSTS=['testserver', 'paie.hydria.mg'])
    def test_documentation_module_list_is_scoped_by_subdomain(self):
        response = self.client.get(reverse('core:documentation_module_list'), HTTP_HOST='paie.hydria.mg')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Fiches de paie')
        self.assertNotContains(response, 'Operations')

    def test_documentation_module_list_post_creates_module_for_authorized_user(self):
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse('core:documentation_module_list'),
            {
                'slug': 'ouvrages',
                'name': 'Ouvrages',
                'short_name': 'Ouvrages',
                'validation_status': DocumentationModule.STATUS_REVIEW,
                'display_order': '4',
                'objective': 'Documenter les pages ouvrages.',
                'target_audience': 'Equipe technique.',
                'data_used': 'Ouvrages, equipements.',
                'pages_in_scope': '/ouvrages/\n/ouvrages/detail/',
                'buttons': 'Creer\nModifier',
                'is_priority': 'on',
            },
        )

        self.assertEqual(response.status_code, 302)
        created = DocumentationModule.objects.get(slug='ouvrages')
        self.assertEqual(created.name, 'Ouvrages')
        self.assertEqual(created.workspace, DocumentationModule.WORKSPACE_MAIN)
        self.assertEqual(created.validation_status, DocumentationModule.STATUS_REVIEW)
        self.assertEqual(created.pages_in_scope, ['/ouvrages/', '/ouvrages/detail/'])
        self.assertTrue(created.is_priority)

    def test_documentation_module_list_post_forbidden_for_read_only_user(self):
        response = self.client.post(
            reverse('core:documentation_module_list'),
            {
                'slug': 'refus-module',
                'name': 'Refus module',
                'objective': 'Test refus',
                'target_audience': 'Lecture seule',
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(DocumentationModule.objects.filter(slug='refus-module').exists())

    def test_documentation_module_detail_loads(self):
        response = self.client.get(reverse('core:documentation_module_detail', args=[self.module.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Piloter les plannings')

    def test_documentation_module_detail_post_updates_module_for_authorized_user(self):
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse('core:documentation_module_detail', args=[self.module.slug]),
            {
                'name': 'Planning terrain',
                'short_name': 'Planning',
                'icon': 'fas fa-calendar',
                'display_order': '7',
                'validation_status': DocumentationModule.STATUS_VALIDATED,
                'workflow_url': '/documentation/workflow/planning/',
                'objective': 'Piloter et verifier les plannings terrain.',
                'target_audience': 'Agents terrain et validation.',
                'data_used': 'Plannings, ouvrages.',
                'pages_in_scope': '/plannings/\n/plannings/avances/',
                'buttons': 'Valider\nImprimer',
                'filters': 'Mois\nAgent',
                'tables': 'Table principale',
                'statistics': 'Nb plannings',
                'charts': 'Charge agent',
                'calculation_rules_text': 'Sommes sur selection.',
                'display_conditions': 'Visible pour agents connectes.',
                'possible_errors': 'Aucun planning trouve.',
                'edge_cases': 'Periode vide.',
                'known_limits': 'Depend des donnees terrain.',
                'test_notes': 'Verifier le PDF.',
                'source_code_refs': 'apps/planning/views.py',
                'is_priority': 'on',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.module.refresh_from_db()
        self.assertEqual(self.module.name, 'Planning terrain')
        self.assertEqual(self.module.icon, 'fas fa-calendar')
        self.assertEqual(self.module.pages_in_scope, ['/plannings/', '/plannings/avances/'])
        self.assertEqual(self.module.filters, ['Mois', 'Agent'])
        self.assertTrue(self.module.is_priority)

    def test_documentation_module_detail_post_forbidden_for_read_only_user(self):
        response = self.client.post(
            reverse('core:documentation_module_detail', args=[self.module.slug]),
            {
                'name': 'Refus edition',
                'objective': 'Refus edition',
                'target_audience': 'Lecture seule',
            },
        )

        self.assertEqual(response.status_code, 403)
        self.module.refresh_from_db()
        self.assertEqual(self.module.name, 'Operations')

    def test_documentation_module_detail_post_creates_indicator_for_authorized_user(self):
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse('core:documentation_module_detail', args=[self.module.slug]),
            {
                'form_type': 'indicator',
                'name': 'Taux de validation',
                'slug': 'taux-validation',
                'objective': 'Mesurer la validation des plannings.',
                'formula': 'valides / total',
                'data_source': 'Planning',
                'refresh_frequency': IndicatorDefinition.UPDATE_WEEKLY,
                'interpretation': 'Plus haut est mieux.',
                'limitations': 'Depend des donnees saisies.',
                'example': '8/10 = 80%',
                'display_order': '3',
            },
        )

        self.assertEqual(response.status_code, 302)
        indicator = IndicatorDefinition.objects.get(slug='taux-validation')
        self.assertEqual(indicator.module, self.module)
        self.assertEqual(indicator.refresh_frequency, IndicatorDefinition.UPDATE_WEEKLY)

    def test_documentation_module_detail_post_updates_indicator_for_authorized_user(self):
        self.client.force_login(self.admin_user)
        indicator = self.module.indicator_definitions.first()

        response = self.client.post(
            reverse('core:documentation_module_detail', args=[self.module.slug]),
            {
                'form_type': 'indicator_update',
                'object_id': str(indicator.id),
                'name': 'Taux couverture revise',
                'slug': 'taux-couverture-revise',
                'objective': 'Mesure revisee.',
                'formula': 'valide / prevu',
                'data_source': 'Planning revise',
                'refresh_frequency': IndicatorDefinition.UPDATE_DAILY,
                'interpretation': 'Suivi journalier.',
                'limitations': 'Depend des saisies du jour.',
                'example': '5/6',
                'display_order': '9',
            },
        )

        self.assertEqual(response.status_code, 302)
        indicator.refresh_from_db()
        self.assertEqual(indicator.name, 'Taux couverture revise')
        self.assertEqual(indicator.slug, 'taux-couverture-revise')
        self.assertEqual(indicator.refresh_frequency, IndicatorDefinition.UPDATE_DAILY)

    def test_documentation_module_detail_post_deletes_indicator_for_authorized_user(self):
        self.client.force_login(self.admin_user)
        indicator = self.module.indicator_definitions.first()

        response = self.client.post(
            reverse('core:documentation_module_detail', args=[self.module.slug]),
            {
                'form_type': 'indicator_delete',
                'object_id': str(indicator.id),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(IndicatorDefinition.objects.filter(id=indicator.id).exists())

    def test_documentation_module_detail_post_creates_rule_for_authorized_user(self):
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse('core:documentation_module_detail', args=[self.module.slug]),
            {
                'form_type': 'rule',
                'title': 'Calcul ecart planning',
                'description': 'Compare prevu et realise.',
                'formula': 'realise - prevu',
                'source_fields': 'prevu, realise',
                'caveats': 'Verifier les doublons.',
                'display_order': '2',
            },
        )

        self.assertEqual(response.status_code, 302)
        rule = CalculationRule.objects.get(title='Calcul ecart planning')
        self.assertEqual(rule.module, self.module)
        self.assertEqual(rule.display_order, 2)

    def test_documentation_module_detail_post_updates_rule_for_authorized_user(self):
        self.client.force_login(self.admin_user)
        rule = self.module.calculation_rules.first()

        response = self.client.post(
            reverse('core:documentation_module_detail', args=[self.module.slug]),
            {
                'form_type': 'rule_update',
                'object_id': str(rule.id),
                'title': 'Calcul avance revise',
                'description': 'Nouvelle description.',
                'formula': 'max(0, recette - avance)',
                'source_fields': 'recette,avance',
                'caveats': 'Verifier les montants.',
                'example': '100 - 80',
                'display_order': '6',
            },
        )

        self.assertEqual(response.status_code, 302)
        rule.refresh_from_db()
        self.assertEqual(rule.title, 'Calcul avance revise')
        self.assertEqual(rule.display_order, 6)

    def test_documentation_module_detail_post_deletes_rule_for_authorized_user(self):
        self.client.force_login(self.admin_user)
        rule = self.module.calculation_rules.first()

        response = self.client.post(
            reverse('core:documentation_module_detail', args=[self.module.slug]),
            {
                'form_type': 'rule_delete',
                'object_id': str(rule.id),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(CalculationRule.objects.filter(id=rule.id).exists())

    def test_documentation_module_detail_post_creates_limitation_for_authorized_user(self):
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse('core:documentation_module_detail', args=[self.module.slug]),
            {
                'form_type': 'limitation',
                'title': 'Connexion terrain instable',
                'description': 'Peut ralentir la synchronisation.',
                'impact': 'Retard de validation.',
                'workaround': 'Reprendre plus tard.',
                'severity': KnownLimitation.SEVERITY_HIGH,
                'status': KnownLimitation.STATUS_MONITORED,
                'display_order': '5',
            },
        )

        self.assertEqual(response.status_code, 302)
        limitation = KnownLimitation.objects.get(title='Connexion terrain instable')
        self.assertEqual(limitation.module, self.module)
        self.assertEqual(limitation.status, KnownLimitation.STATUS_MONITORED)

    def test_documentation_module_detail_post_updates_limitation_for_authorized_user(self):
        self.client.force_login(self.admin_user)
        limitation = self.module.known_limitations.first()

        response = self.client.post(
            reverse('core:documentation_module_detail', args=[self.module.slug]),
            {
                'form_type': 'limitation_update',
                'object_id': str(limitation.id),
                'title': 'Dependance donnees revisee',
                'description': 'Description ajustee.',
                'impact': 'Impact ajuste.',
                'workaround': 'Contournement ajuste.',
                'severity': KnownLimitation.SEVERITY_CRITICAL,
                'status': KnownLimitation.STATUS_RESOLVED,
                'display_order': '8',
            },
        )

        self.assertEqual(response.status_code, 302)
        limitation.refresh_from_db()
        self.assertEqual(limitation.title, 'Dependance donnees revisee')
        self.assertEqual(limitation.status, KnownLimitation.STATUS_RESOLVED)

    def test_documentation_module_detail_post_deletes_limitation_for_authorized_user(self):
        self.client.force_login(self.admin_user)
        limitation = self.module.known_limitations.first()

        response = self.client.post(
            reverse('core:documentation_module_detail', args=[self.module.slug]),
            {
                'form_type': 'limitation_delete',
                'object_id': str(limitation.id),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(KnownLimitation.objects.filter(id=limitation.id).exists())

    def test_documentation_module_detail_post_creates_change_log_for_authorized_user(self):
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse('core:documentation_module_detail', args=[self.module.slug]),
            {
                'form_type': 'change_log',
                'title': 'Ajout protocole export',
                'entry_type': DocumentationChangeLog.TYPE_TEST,
                'details': 'Nouveau test pour le recap depart.',
                'happened_on': '2026-06-05',
            },
        )

        self.assertEqual(response.status_code, 302)
        change_log = DocumentationChangeLog.objects.get(title='Ajout protocole export')
        self.assertEqual(change_log.module, self.module)
        self.assertEqual(change_log.entry_type, DocumentationChangeLog.TYPE_TEST)

    def test_documentation_module_detail_post_updates_change_log_for_authorized_user(self):
        self.client.force_login(self.admin_user)
        change_log = DocumentationChangeLog.objects.create(
            module=self.module,
            title='Ancienne entree',
            entry_type=DocumentationChangeLog.TYPE_DOC,
            details='Ancien detail',
            happened_on='2026-06-04',
        )

        response = self.client.post(
            reverse('core:documentation_module_detail', args=[self.module.slug]),
            {
                'form_type': 'change_log_update',
                'object_id': str(change_log.id),
                'title': 'Entree mise a jour',
                'entry_type': DocumentationChangeLog.TYPE_VALIDATION,
                'details': 'Detail mis a jour',
                'happened_on': '2026-06-05',
            },
        )

        self.assertEqual(response.status_code, 302)
        change_log.refresh_from_db()
        self.assertEqual(change_log.title, 'Entree mise a jour')
        self.assertEqual(change_log.entry_type, DocumentationChangeLog.TYPE_VALIDATION)

    def test_documentation_module_detail_post_deletes_change_log_for_authorized_user(self):
        self.client.force_login(self.admin_user)
        change_log = DocumentationChangeLog.objects.create(
            module=self.module,
            title='Entree a supprimer',
            entry_type=DocumentationChangeLog.TYPE_DOC,
            happened_on='2026-06-05',
        )

        response = self.client.post(
            reverse('core:documentation_module_detail', args=[self.module.slug]),
            {
                'form_type': 'change_log_delete',
                'object_id': str(change_log.id),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(DocumentationChangeLog.objects.filter(id=change_log.id).exists())

    def test_test_protocol_list_loads(self):
        response = self.client.get(reverse('core:test_protocol_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'PL-001')

    def test_test_protocol_list_post_creates_protocol_for_authorized_user(self):
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse('core:test_protocol_list'),
            {
                'code': 'OUV-003',
                'module_id': str(self.module.id),
                'test_type': TestProtocol.TYPE_DISPLAY,
                'criticality': TestProtocol.CRITICALITY_HIGH,
                'objective': 'Verifier le rendu du recap depart.',
                'preconditions': 'Avoir un planning valide.',
                'required_data': 'Un ouvrage et un agent.',
                'steps': '1. Ouvrir la page. 2. Imprimer le recap.',
                'expected_result': 'Le recap affiche toutes les sections attendues.',
            },
        )

        self.assertEqual(response.status_code, 302)
        created = TestProtocol.objects.get(code='OUV-003')
        self.assertEqual(created.module, self.module)
        self.assertEqual(created.status, TestProtocol.STATUS_TODO)
        self.assertEqual(created.test_type, TestProtocol.TYPE_DISPLAY)

    def test_test_protocol_list_post_forbidden_for_read_only_user(self):
        response = self.client.post(
            reverse('core:test_protocol_list'),
            {
                'code': 'OUV-004',
                'module_id': str(self.module.id),
                'test_type': TestProtocol.TYPE_DISPLAY,
                'criticality': TestProtocol.CRITICALITY_HIGH,
                'objective': 'Tentative sans droit.',
                'steps': '1. Tester.',
                'expected_result': 'Refus attendu.',
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(TestProtocol.objects.filter(code='OUV-004').exists())

    def test_test_protocol_filters_by_status(self):
        response = self.client.get(reverse('core:test_protocol_list'), {'status': TestProtocol.STATUS_SUCCESS})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'PL-001')
        self.assertNotContains(response, 'PL-002')

    def test_test_protocol_detail_loads(self):
        response = self.client.get(reverse('core:test_protocol_detail', args=[self.protocol.code]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Chargement OK')

    def test_test_protocol_detail_post_creates_execution_for_authorized_user(self):
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse('core:test_protocol_detail', args=[self.protocol.code]),
            {
                'status': TestProtocol.STATUS_FAILED,
                'result_obtained': 'Le tableau ne charge plus apres validation.',
                'executed_by_name': 'Responsable QA',
                'comment': 'Regression constatee sur la vue de recap.',
                'evidence_path': '/captures/tests/ouv-001.png',
                'related_issue': 'BUG-142',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.protocol.refresh_from_db()
        execution = self.protocol.executions.first()
        self.assertEqual(execution.status, TestProtocol.STATUS_FAILED)
        self.assertEqual(execution.executed_by_name, 'Responsable QA')
        self.assertEqual(self.protocol.status, TestProtocol.STATUS_FAILED)
        self.assertEqual(self.protocol.last_result, 'Le tableau ne charge plus apres validation.')
        self.assertEqual(self.protocol.related_issue, 'BUG-142')
        self.assertIsNotNone(self.protocol.last_executed_at)

    def test_test_protocol_detail_post_updates_protocol_for_authorized_user(self):
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse('core:test_protocol_detail', args=[self.protocol.code]),
            {
                'form_type': 'protocol_update',
                'code': 'PL-010',
                'module_id': str(self.module.id),
                'test_type': TestProtocol.TYPE_EXPORT,
                'criticality': TestProtocol.CRITICALITY_CRITICAL,
                'protocol_status': TestProtocol.STATUS_FIX,
                'objective': 'Verifier export recap depart.',
                'preconditions': 'Avoir un planning valide.',
                'required_data': 'Planning et agent.',
                'steps': '1. Exporter. 2. Controler le PDF.',
                'expected_result': 'Le PDF contient toutes les signatures.',
                'last_result': 'La ligne de validation manque encore.',
                'executed_by_name': 'Lead QA',
                'comment': 'A reprendre apres correctif.',
                'evidence_path': '/captures/pl-010.png',
                'related_issue': 'BUG-200',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.protocol.refresh_from_db()
        self.assertEqual(self.protocol.code, 'PL-010')
        self.assertEqual(self.protocol.test_type, TestProtocol.TYPE_EXPORT)
        self.assertEqual(self.protocol.status, TestProtocol.STATUS_FIX)
        self.assertEqual(self.protocol.related_issue, 'BUG-200')

    def test_test_protocol_detail_post_deletes_protocol_for_authorized_user(self):
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse('core:test_protocol_detail', args=[self.protocol.code]),
            {
                'form_type': 'protocol_delete',
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(TestProtocol.objects.filter(id=self.protocol.id).exists())

    def test_test_protocol_detail_post_forbidden_for_read_only_user(self):
        response = self.client.post(
            reverse('core:test_protocol_detail', args=[self.protocol.code]),
            {
                'status': TestProtocol.STATUS_SUCCESS,
                'result_obtained': 'Tentative non autorisee.',
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.protocol.executions.count(), 1)

    def test_remaining_documentation_pages_load(self):
        urls = [
            reverse('core:architecture_documentation'),
            reverse('core:planning_workflow_documentation'),
            reverse('core:facturation_workflow_documentation'),
            reverse('core:reparations_workflow_documentation'),
            reverse('core:fiches_paie_workflow_documentation'),
            reverse('core:inventory_workflow_documentation'),
            reverse('core:paiements_irsa_workflow_documentation'),
            reverse('core:caissiere_workflow_documentation'),
            reverse('core:cartes_sociales_workflow_documentation'),
            reverse('core:workflow_terrain_documentation'),
            reverse('core:analyses_eau_workflow_documentation'),
            reverse('core:recherche_ouvrages_workflow_documentation'),
        ]

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)

    def test_models_accept_expected_data(self):
        self.assertEqual(self.module.test_protocols.count(), 2)
        self.assertEqual(self.module.indicator_definitions.count(), 1)
        self.assertEqual(self.module.calculation_rules.count(), 1)

    def test_summary_counts_render_on_home(self):
        response = self.client.get(reverse('core:documentation_protocols_home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Critiques en echec')


class SearchDetailResponsableOuvrageAccessTests(TestCase):
    """Durcissement de search_detail : un Employe non-admin doit etre
    responsable actif direct (EmployeOuvrages) de l'ouvrage/point d'eau
    consulte, sinon 403. Superuser/admin restent illimites."""

    def setUp(self):
        from datetime import date

        from apps.employees.models import Employe, EmployeOuvrages
        from apps.billing.models import PointEau
        from apps.organization.models import Base, Organisation, Ouvrage, TypeOuvrage

        user_model = get_user_model()

        self.organisation = Organisation.objects.create(nom_organisation='Org SearchDetail Tests')
        self.base = Base.objects.create(nom_base='Base SearchDetail Tests', organisation=self.organisation)
        self.type_ouvrage = TypeOuvrage.objects.create(nom_type_ouvrage='AEPG SearchDetail Tests')
        self.ouvrage = Ouvrage.objects.create(nom_ouvrage='Ouvrage SearchDetail Tests', type_ouvrage=self.type_ouvrage)
        self.point_eau = PointEau.objects.create(nomabonne='Abonne SearchDetail Tests', ouvrage=self.ouvrage)

        self.user_responsable = user_model.objects.create_user(
            username='responsable_search_detail_tests', password='testpass123',
        )
        self.employe_responsable = Employe.objects.create(
            nom_employe='Responsable SearchDetail', nom='Responsable', base=self.base,
            user=self.user_responsable,
        )
        EmployeOuvrages.objects.create(
            employe=self.employe_responsable, ouvrage=self.ouvrage, date_debut=date(2026, 1, 1),
        )

        self.user_non_responsable = user_model.objects.create_user(
            username='non_responsable_search_detail_tests', password='testpass123',
        )
        self.employe_non_responsable = Employe.objects.create(
            nom_employe='Non Responsable SearchDetail', nom='NonResp', base=self.base,
            user=self.user_non_responsable,
        )

        self.user_admin = user_model.objects.create_superuser(
            username='admin_search_detail_tests', email='admin@example.com', password='testpass123',
        )

    def _url_point_eau(self):
        return reverse('core:search_detail', kwargs={'entity_type': 'point_eau', 'entity_id': str(self.point_eau.id)})

    def _url_ouvrage(self):
        return reverse('core:search_detail', kwargs={'entity_type': 'ouvrage', 'entity_id': str(self.ouvrage.id)})

    @override_settings(ALLOWED_HOSTS=['*'])
    def test_responsable_actif_accede_au_point_eau(self):
        self.client.force_login(self.user_responsable)
        response = self.client.get(self._url_point_eau())
        self.assertEqual(response.status_code, 200)

    @override_settings(ALLOWED_HOSTS=['*'])
    def test_responsable_actif_accede_a_l_ouvrage(self):
        self.client.force_login(self.user_responsable)
        response = self.client.get(self._url_ouvrage())
        self.assertEqual(response.status_code, 200)

    @override_settings(ALLOWED_HOSTS=['*'])
    def test_non_responsable_refuse_sur_point_eau(self):
        self.client.force_login(self.user_non_responsable)
        response = self.client.get(self._url_point_eau())
        self.assertEqual(response.status_code, 403)

    @override_settings(ALLOWED_HOSTS=['*'])
    def test_non_responsable_refuse_sur_ouvrage(self):
        self.client.force_login(self.user_non_responsable)
        response = self.client.get(self._url_ouvrage())
        self.assertEqual(response.status_code, 403)

    @override_settings(ALLOWED_HOSTS=['*'])
    def test_admin_non_affecte_par_le_durcissement(self):
        from apps.employees.models import Employe

        Employe.objects.create(
            nom_employe='Admin SearchDetail', nom='Admin', base=self.base, user=self.user_admin,
        )
        self.client.force_login(self.user_admin)
        response = self.client.get(self._url_point_eau())
        self.assertEqual(response.status_code, 200)


class VillageFluxChantierEnCoursTests(TestCase):
    """Étape « chantier en cours » du diagramme de flux (workflow chantier non clôturé)."""

    def test_chantier_en_cours_entre_demande_et_modalite(self):
        from apps.billing.models import PointEau
        from apps.chantiers.models import DemandeVillage
        from apps.chantiers.models_workflow import ChantierWorkflow
        from apps.core.views_villages_desserte import _compute_village_flux
        from apps.geography.models import Commune, District, Fokontany, Parcelle, Region, Village
        from apps.organization.models import Ouvrage, TypeOuvrage

        type_ouvrage = TypeOuvrage.objects.create(nom_type_ouvrage='Travaux en cours test')
        region = Region.objects.create(nom_region='Region flux test')
        district = District.objects.create(nom_district='District flux test', region=region)
        commune = Commune.objects.create(nom_commune='Commune flux test', district=district)
        fokontany = Fokontany.objects.create(nom_fokontany='Fokontany flux test', commune=commune)
        village_a = Village.objects.create(nom_village='Village A chantier', fokontany=fokontany)
        village_b = Village.objects.create(nom_village='Village B sans chantier', fokontany=fokontany)
        ouvrage = Ouvrage.objects.create(nom_ouvrage='Ouvrage en chantier', type_ouvrage=type_ouvrage)
        parcelle = Parcelle.objects.create(reference_parcelle='P1', village=village_a)
        PointEau.objects.create(nomabonne='PE chantier', ouvrage=ouvrage, parcelle=parcelle)
        DemandeVillage.objects.create(
            village=village_a, type_travaux='construction', type_ouvrage=type_ouvrage,
            detail_travaux='x', type_main_oeuvre='paye', semestre_prevision='S1 2026')
        ChantierWorkflow.objects.create(
            code='WF-TEST-0001', ouvrage=ouvrage, statut='execution', type_travaux='construction',
            description='Captage et adduction', statut_chantier='en_cours')
        cloture = Ouvrage.objects.create(nom_ouvrage='Ouvrage cloture', type_ouvrage=type_ouvrage)
        PointEau.objects.create(
            nomabonne='PE cloture', ouvrage=cloture,
            parcelle=Parcelle.objects.create(reference_parcelle='P2', village=village_b))
        ChantierWorkflow.objects.create(code='WF-TEST-0002', ouvrage=cloture, statut='cloture')

        data = _compute_village_flux('', '', '', '', 'http://x/')

        nodes = {}

        def walk(n):
            nodes[n['key']] = n
            for child in n['children']:
                walk(child)
        walk(data['tree'])
        self.assertEqual(nodes['requested_chantier']['count'], 1)
        self.assertEqual(nodes['requested_sans_chantier']['count'], 0)
        self.assertEqual(nodes['without_request_chantier']['count'], 0)
        self.assertEqual(nodes['without_request_sans_chantier']['count'], 1)  # workflow clôturé ignoré
        self.assertEqual(len(data['chantiers']), 1)
        chantier = data['chantiers'][0]
        self.assertEqual(chantier['o'], 'Ouvrage en chantier')
        self.assertEqual(chantier['t'], 'Construction')
        self.assertEqual(chantier['s'], 'En cours')
        self.assertEqual(chantier['d'], 'Captage et adduction')
        self.assertEqual(nodes['requested_chantier']['ci'], [0])
