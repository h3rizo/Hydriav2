import datetime
from types import SimpleNamespace

from django.test import SimpleTestCase
from django.utils import timezone

from apps.planning.views_livraisons import (
    _build_employee_equipment_statuses,
    _classify_employee_equipment_designation,
)


class EmployeeEquipmentHelpersTests(SimpleTestCase):
    def test_classify_designation_detects_known_employee_equipment(self):
        self.assertEqual(_classify_employee_equipment_designation("Bottes de securite"), "botte")
        self.assertEqual(_classify_employee_equipment_designation("Sac a dos terrain"), "sac_a_dos")
        self.assertEqual(_classify_employee_equipment_designation("Imperméable bleu"), "impermeable")

    def test_build_status_marks_eligible_when_no_recent_delivery(self):
        employe = SimpleNamespace(id="emp-1")

        statuses = _build_employee_equipment_statuses([employe], [])

        self.assertEqual(statuses["emp-1"]["botte"]["state"], "eligible")
        self.assertEqual(statuses["emp-1"]["sac_a_dos"]["state"], "eligible")
        self.assertEqual(statuses["emp-1"]["impermeable"]["state"], "eligible")

    def test_build_status_marks_quota_atteint_within_period(self):
        employe = SimpleNamespace(id="emp-1")
        fiche = SimpleNamespace(
            employee_id="emp-1",
            designation=SimpleNamespace(nom="Botte PVC"),
            operation_date=timezone.now() - datetime.timedelta(days=30),
            notes="[DOTATION_EQUIPEMENT_EMPLOYE]",
            reference="DOT-TEST",
        )

        statuses = _build_employee_equipment_statuses([employe], [fiche])

        self.assertEqual(statuses["emp-1"]["botte"]["state"], "quota_atteint")
        self.assertEqual(statuses["emp-1"]["botte"]["remaining"], 0)

    def test_build_status_marks_depasse_when_more_than_one_delivery_in_period(self):
        employe = SimpleNamespace(id="emp-1")
        fiche_recent = SimpleNamespace(
            employee_id="emp-1",
            designation=SimpleNamespace(nom="Sac a dos"),
            operation_date=timezone.now() - datetime.timedelta(days=20),
            notes="[DOTATION_EQUIPEMENT_EMPLOYE]",
            reference="DOT-TEST-1",
        )
        fiche_old = SimpleNamespace(
            employee_id="emp-1",
            designation=SimpleNamespace(nom="Sac a dos"),
            operation_date=timezone.now() - datetime.timedelta(days=200),
            notes="[DOTATION_EQUIPEMENT_EMPLOYE]",
            reference="DOT-TEST-2",
        )

        statuses = _build_employee_equipment_statuses([employe], [fiche_recent, fiche_old])

        self.assertEqual(statuses["emp-1"]["sac_a_dos"]["state"], "depasse")
        self.assertEqual(statuses["emp-1"]["sac_a_dos"]["count_in_period"], 2)
