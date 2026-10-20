import json
from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.billing.models import PointEau, Releve, TypePointEau
from apps.employees.models import Employe, EmployeOuvrages, HierarchieEmploye, Poste
from apps.employees.models_evaluation import FichePoste
from apps.employees.models_evaluation_resultats import EvaluationResultats
from apps.employees.views_evaluations_resultats import _build_evaluation_snapshot
from apps.organization.models import Base, Organisation, Ouvrage, TypeOuvrage
from apps.planning.models import Planning, TypeActivite


class EvaluationResultatsRoleBasedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organisation = Organisation.objects.create(
            nom_organisation="Org Test",
            type_organisation=Organisation.TYPE_GESTIONNAIRE,
        )
        cls.type_ouvrage = TypeOuvrage.objects.create(nom_type_ouvrage="Forage")
        cls.type_point_eau = TypePointEau.objects.create(nom_type="Branchement privé")
        cls.base = Base.objects.create(
            nom_base="Base Test",
            organisation=cls.organisation,
        )

        cls.poste_mpikojakoja = Poste.objects.create(
            nom_poste="Mpikojakoja ifotony",
            organisation=cls.organisation,
        )
        cls.poste_recouvrement = Poste.objects.create(
            nom_poste="Agent de recouvrement",
            organisation=cls.organisation,
        )
        cls.poste_superieur = Poste.objects.create(
            nom_poste="Superviseur technique",
            organisation=cls.organisation,
        )

        cls.mpikojakoja = Employe.objects.create(
            nom_employe="Mpikojakoja Test",
            nom="Test",
            prenom="Mpikojakoja",
            surnom="MP",
            base=cls.base,
            poste=cls.poste_mpikojakoja,
        )
        cls.agent_recouvrement = Employe.objects.create(
            nom_employe="Recouvrement Test",
            nom="Test",
            prenom="Recouvrement",
            surnom="REC",
            base=cls.base,
            poste=cls.poste_recouvrement,
        )
        cls.superieur = Employe.objects.create(
            nom_employe="Superieur Test",
            nom="Test",
            prenom="Superieur",
            surnom="SUP",
            base=cls.base,
            poste=cls.poste_superieur,
        )

        HierarchieEmploye.objects.create(
            employe=cls.mpikojakoja,
            superieur=cls.superieur,
            date_debut=date(2026, 1, 1),
        )
        HierarchieEmploye.objects.create(
            employe=cls.agent_recouvrement,
            superieur=cls.superieur,
            date_debut=date(2026, 1, 1),
        )

        cls.ouvrage_reparation = Ouvrage.objects.create(
            nom_ouvrage="Ouvrage Réparation",
            type_ouvrage=cls.type_ouvrage,
        )
        cls.ouvrage_recouvrement = Ouvrage.objects.create(
            nom_ouvrage="Ouvrage Recouvrement",
            type_ouvrage=cls.type_ouvrage,
        )

        EmployeOuvrages.objects.create(
            employe=cls.mpikojakoja,
            ouvrage=cls.ouvrage_reparation,
            date_debut=date(2026, 1, 1),
            est_responsable_principal=True,
        )
        EmployeOuvrages.objects.create(
            employe=cls.agent_recouvrement,
            ouvrage=cls.ouvrage_recouvrement,
            date_debut=date(2026, 1, 1),
            est_responsable_principal=True,
        )

        type_reparation = TypeActivite.objects.create(nomtype="Reparation")
        fiche_reparation = FichePoste.objects.create(
            type_activites=type_reparation,
            tache="Réparer pompe",
            description="Réparation terrain",
        )

        Planning.objects.create(
            date=timezone.make_aware(datetime(2026, 1, 10, 9, 0, 0)),
            employe=cls.mpikojakoja,
            fiche_poste=fiche_reparation,
            type_activite=type_reparation,
            ouvrage=cls.ouvrage_reparation,
            estvalide=True,
        )
        Planning.objects.create(
            date=timezone.make_aware(datetime(2026, 1, 15, 9, 0, 0)),
            employe=cls.mpikojakoja,
            fiche_poste=fiche_reparation,
            type_activite=type_reparation,
            ouvrage=cls.ouvrage_reparation,
            estvalide=False,
        )

        point_eau = PointEau.objects.create(
            nomabonne="Abonné Recouvrement",
            ouvrage=cls.ouvrage_recouvrement,
            type_point_eau=cls.type_point_eau,
            code_point_eau="PE-001",
        )
        Releve.objects.create(
            point_eau=point_eau,
            abonne=point_eau.nomabonne,
            datereleve=date(2026, 1, 20),
            ancienindex=0,
            nouvelindex=10,
            consommation=10,
            montant=Decimal("100.00"),
            montantpaye=Decimal("100.00"),
            statut="paye",
            numeroDiameX="DIA-001",
        )

    def test_mpikojakoja_snapshot_uses_repairs_done_vs_pending(self):
        snapshot = _build_evaluation_snapshot(
            self.mpikojakoja,
            date(2026, 1, 1),
            date(2026, 1, 31),
        )

        self.assertEqual(snapshot["mode_evaluation"], "reparations")
        self.assertEqual(snapshot["score_obtenu"], 1)
        self.assertEqual(snapshot["score_maximum"], 2)
        self.assertEqual(snapshot["metrics"]["reparations_terminees"], 1)
        self.assertEqual(snapshot["metrics"]["reparations_non_terminees"], 1)
        self.assertEqual(len(snapshot["details"]), 1)

    def test_superieur_snapshot_aggregates_repair_and_recouvrement_subordinates(self):
        snapshot = _build_evaluation_snapshot(
            self.superieur,
            date(2026, 1, 1),
            date(2026, 1, 31),
        )

        self.assertEqual(snapshot["mode_evaluation"], "hierarchie")
        self.assertEqual(snapshot["score_obtenu"], 75)
        self.assertEqual(snapshot["score_maximum"], 100)
        self.assertEqual(snapshot["metrics"]["subordonnes_contributeurs"], 2)
        self.assertEqual(snapshot["metrics"]["subordonnes_reparations"], 1)
        self.assertEqual(snapshot["metrics"]["subordonnes_recouvrement"], 1)
        self.assertEqual(snapshot["metrics"]["score_moyen_sur_100"], 75)

    def test_api_create_persists_mode_and_snapshot(self):
        user_model = get_user_model()
        user = user_model.objects.create_superuser(
            username="admin_eval_resultats",
            email="admin_eval_resultats@example.com",
            password="testpass123",
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("employees:api_evaluation_resultats_create"),
            data=json.dumps(
                {
                    "employe_id": str(self.superieur.id),
                    "periode_debut": "2026-01-01",
                    "periode_fin": "2026-01-31",
                    "statut": "provisoire",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])

        evaluation = EvaluationResultats.objects.get(employe=self.superieur)
        self.assertEqual(evaluation.mode_evaluation, "hierarchie")
        self.assertEqual(evaluation.score_obtenu, 75)
        self.assertEqual(evaluation.score_maximum, 100)
        self.assertEqual(len(evaluation.details_snapshot), 2)
