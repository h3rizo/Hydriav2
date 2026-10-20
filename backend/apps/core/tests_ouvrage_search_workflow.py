from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.billing.models import ModaliteGestion, PointEau, TypePointEau
from apps.geography.models import Commune, District, Fokontany, Parcelle, Region, Village
from apps.organization.models import Organisation, Ouvrage, TypeOuvrage
from apps.employees.models import FichePoste
from apps.planning.models import Planning, TypeActivite

from .views import _get_ouvrage_repair_plannings
from .views_ouvrage_interventions import (
    _activity_deadline_summary_by_ouvrage,
    _accessible_ouvrages,
    _historique_interventions,
)


class OuvrageSearchWorkflowTests(TestCase):
    """Tests fonctionnels des deux pages du workflow Recherche des ouvrages."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username="ouvrage-search-admin",
            email="ouvrage-search@example.com",
            password="secret123",
        )
        cls.ouvrage_type = TypeOuvrage.objects.create(nom_type_ouvrage="AEPG test recherche")
        cls.point_type = TypePointEau.objects.create(nom_type="Borne fontaine test")

        cls.region_a = Region.objects.create(nom_region="Region Alpha")
        cls.region_b = Region.objects.create(nom_region="Region Beta")
        cls.district_a1 = District.objects.create(nom_district="District Alpha 1", region=cls.region_a)
        cls.district_a2 = District.objects.create(nom_district="District Alpha 2", region=cls.region_a)
        cls.district_b1 = District.objects.create(nom_district="District Beta 1", region=cls.region_b)
        cls.commune_a1 = Commune.objects.create(nom_commune="Commune Alpha 1", district=cls.district_a1)
        cls.commune_a2 = Commune.objects.create(nom_commune="Commune Alpha 2", district=cls.district_a2)
        cls.commune_b1 = Commune.objects.create(nom_commune="Commune Beta 1", district=cls.district_b1)

        cls._create_located_ouvrage("Ouvrage Alpha 1", cls.commune_a1, "01")
        cls._create_located_ouvrage("Ouvrage Alpha 2", cls.commune_a2, "02")
        cls._create_located_ouvrage("Ouvrage Beta 1", cls.commune_b1, "10")

    @classmethod
    def _create_located_ouvrage(cls, name, commune, idxls):
        fokontany = Fokontany.objects.create(
            nom_fokontany=f"Fokontany {name}",
            commune=commune,
        )
        village = Village.objects.create(
            nom_village=f"Village {name}",
            fokontany=fokontany,
        )
        parcelle = Parcelle.objects.create(
            reference_parcelle=f"Parcelle {name}",
            village=village,
        )
        ouvrage = Ouvrage.objects.create(nom_ouvrage=name, type_ouvrage=cls.ouvrage_type)
        PointEau.objects.create(
            ouvrage=ouvrage,
            parcelle=parcelle,
            type_point_eau=cls.point_type,
            nomabonne=f"Abonne {name}",
            idxls=idxls,
        )
        return ouvrage

    def setUp(self):
        self.client.force_login(self.user)

    def _get_with_accessible_ouvrages(self, url_name, params):
        with patch(
            "apps.core.views_ouvrage_interventions._accessible_ouvrages",
            return_value=Ouvrage.objects.all(),
        ):
            return self.client.get(reverse(url_name), params)

    def test_quick_search_region_limits_districts_and_communes(self):
        response = self._get_with_accessible_ouvrages(
            "core:recherche_ouvrages_rapide",
            {"region": str(self.region_a.id)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(
            response.context["districts"],
            [self.district_a1, self.district_a2],
        )
        self.assertQuerySetEqual(
            response.context["communes"],
            [self.commune_a1, self.commune_a2],
        )
        self.assertEqual(response.context["page_obj"].paginator.count, 2)

    def test_quick_search_district_limits_communes(self):
        response = self._get_with_accessible_ouvrages(
            "core:recherche_ouvrages_rapide",
            {
                "region": str(self.region_a.id),
                "district": str(self.district_a2.id),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(response.context["communes"], [self.commune_a2])
        self.assertEqual(response.context["page_obj"].paginator.count, 1)

    def test_recent_interventions_use_the_same_geographic_cascade(self):
        response = self._get_with_accessible_ouvrages(
            "core:interventions_recentes",
            {
                "region": str(self.region_a.id),
                "district": str(self.district_a1.id),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertQuerySetEqual(
            response.context["districts"],
            [self.district_a1, self.district_a2],
        )
        self.assertQuerySetEqual(response.context["communes"], [self.commune_a1])

    def test_long_due_list_controls_are_present_in_modal_template(self):
        response = self._get_with_accessible_ouvrages(
            "core:recherche_ouvrages_rapide",
            {},
        )

        self.assertContains(response, 'id="ouvrageDueAdvanced"')
        self.assertContains(response, 'id="ouvrageDueDateFilter"')
        self.assertContains(response, "ouvrageDueRowsData.length > 10")

    def test_overdue_counter_drops_to_zero_when_interventions_are_completed(self):
        ouvrage = Ouvrage.objects.get(nom_ouvrage="Ouvrage Alpha 1")
        activity_type = TypeActivite.objects.create(nomtype="Reparation compteur")
        fiche = FichePoste.objects.create(
            type_activites=activity_type,
            tache="Reparation pompe compteur",
            description="Intervention de reparation pour le test du compteur",
            dans_planning=True,
        )
        overdue = Planning.objects.create(
            ouvrage=ouvrage,
            fiche_poste=fiche,
            type_activite=activity_type,
            date=timezone.now() - timedelta(days=2),
            statut="en_cours",
        )
        Planning.objects.create(
            ouvrage=ouvrage,
            fiche_poste=fiche,
            type_activite=activity_type,
            date=timezone.now() - timedelta(days=3),
            statut="termine",
        )

        response = self._get_with_accessible_ouvrages(
            "core:recherche_ouvrages_rapide",
            {"q": "Ouvrage Alpha 1"},
        )
        self.assertEqual(
            response.context["page_obj"].object_list[0].unfinished_overdue_contributions_count,
            1,
        )

        overdue.statut = "termine"
        overdue.save(update_fields=["statut"])
        response = self._get_with_accessible_ouvrages(
            "core:recherche_ouvrages_rapide",
            {"q": "Ouvrage Alpha 1"},
        )
        self.assertEqual(
            response.context["page_obj"].object_list[0].unfinished_overdue_contributions_count,
            0,
        )

    def test_history_hides_completed_interventions_by_default(self):
        ouvrage = Ouvrage.objects.get(nom_ouvrage="Ouvrage Alpha 1")
        activity_type = TypeActivite.objects.create(nomtype="Reparation historique")
        fiche = FichePoste.objects.create(
            type_activites=activity_type,
            tache="Reparation pompe historique",
            description="Intervention de reparation pour le test historique",
            dans_planning=True,
        )
        for index in range(6):
            Planning.objects.create(
                ouvrage=ouvrage,
                fiche_poste=fiche,
                type_activite=activity_type,
                date=timezone.now() - timedelta(days=index + 1),
                statut="en_cours",
            )
        for index in range(2):
            Planning.objects.create(
                ouvrage=ouvrage,
                fiche_poste=fiche,
                type_activite=activity_type,
                date=timezone.now() - timedelta(days=index + 10),
                statut="termine",
            )

        url = reverse("core:historique_interventions_ouvrage", args=[ouvrage.id])
        with patch(
            "apps.core.views_ouvrage_interventions._accessible_ouvrages",
            return_value=Ouvrage.objects.all(),
        ):
            response = self.client.get(url)
            response_with_completed = self.client.get(
                url,
                {"show_completed": "1", "page": "2"},
            )

        default_data = response.json()
        self.assertEqual(default_data["pagination"]["count"], 6)
        self.assertEqual(default_data["pagination"]["completed_count"], 2)
        self.assertFalse(default_data["pagination"]["show_completed"])
        self.assertNotIn("termine", {item["statut_code"] for item in default_data["items"]})

        completed_data = response_with_completed.json()
        self.assertEqual(completed_data["pagination"]["count"], 8)
        self.assertTrue(completed_data["pagination"]["show_completed"])
        self.assertIn("termine", {item["statut_code"] for item in completed_data["items"]})

    def test_overdue_activity_stats_count_unique_ouvrages_by_activity_type(self):
        maintenance_only = Ouvrage.objects.get(nom_ouvrage="Ouvrage Alpha 1")
        repair_and_maintenance = Ouvrage.objects.get(nom_ouvrage="Ouvrage Alpha 2")
        maintenance_type = TypeActivite.objects.create(nomtype="Entretien")
        maintenance_fiche = FichePoste.objects.create(
            type_activites=maintenance_type,
            tache="Nettoyage et entretien pompe",
            description="Entretien periodique",
            dans_planning=True,
        )
        repair_type = TypeActivite.objects.create(nomtype="Reparation")
        repair_fiche = FichePoste.objects.create(
            type_activites=repair_type,
            tache="Reparation pompe en panne",
            description="Reparation corrective",
            dans_planning=True,
        )
        for ouvrage, fiche, activity_type in (
            (maintenance_only, maintenance_fiche, maintenance_type),
            (repair_and_maintenance, maintenance_fiche, maintenance_type),
            (repair_and_maintenance, repair_fiche, repair_type),
        ):
            Planning.objects.create(
                ouvrage=ouvrage,
                fiche_poste=fiche,
                type_activite=activity_type,
                date=timezone.now() - timedelta(days=2),
                statut="en_cours",
            )
        Planning.objects.create(
            ouvrage=maintenance_only,
            fiche_poste=repair_fiche,
            type_activite=repair_type,
            date=timezone.now() + timedelta(days=2),
            statut="en_cours",
        )
        Planning.objects.create(
            ouvrage=maintenance_only,
            fiche_poste=maintenance_fiche,
            type_activite=maintenance_type,
            date=timezone.now() + timedelta(days=3),
            statut="en_cours",
        )

        response = self._get_with_accessible_ouvrages(
            "core:recherche_ouvrages_rapide",
            {},
        )

        self.assertEqual(response.context["overdue_unfinished_count"], 3)
        self.assertEqual(response.context["overdue_repair_ouvrages_count"], 1)
        self.assertEqual(response.context["overdue_repair_ouvrages_percentage"], 33.3)
        self.assertEqual(
            response.context["overdue_maintenance_only_ouvrages_count"],
            1,
        )
        self.assertEqual(
            response.context["overdue_maintenance_only_ouvrages_percentage"],
            33.3,
        )
        self.assertEqual(response.context["filtered_ouvrages_count"], 3)
        self.assertEqual(response.context["activity_deadline_totals"], {
            "repair_overdue": 1,
            "repair_upcoming": 1,
            "other_overdue": 2,
            "other_upcoming": 1,
        })
        summary = _activity_deadline_summary_by_ouvrage(
            Ouvrage.objects.values_list("id", flat=True),
            today=timezone.localdate(),
        )
        self.assertEqual(
            {
                bucket: len(planning_ids)
                for bucket, planning_ids in summary["planning_ids"].items()
            },
            response.context["activity_deadline_totals"],
        )

    def test_excluded_activity_is_not_restored_by_ouvrage_entry_marker(self):
        ouvrage = Ouvrage.objects.get(nom_ouvrage="Ouvrage Alpha 1")
        activity_type = TypeActivite.objects.create(nomtype="Maintenance")
        fiche = FichePoste.objects.create(
            type_activites=activity_type,
            tache="Appui agent de maintenance",
            description="Activite exclue",
            dans_planning=True,
        )
        for days in (-2, 2):
            Planning.objects.create(
                ouvrage=ouvrage,
                fiche_poste=fiche,
                type_activite=activity_type,
                date=timezone.now() + timedelta(days=days),
                statut="en_cours",
                remarque="[Saisie depuis la fiche ouvrage]",
            )
        self.assertEqual(_historique_interventions(ouvrage), [])
        summary = _activity_deadline_summary_by_ouvrage([ouvrage.id])
        self.assertEqual(summary["counts"], {})
        self.assertTrue(all(total == 0 for total in summary["totals"].values()))

    def test_workflow_documentation_page_loads(self):
        response = self.client.get(reverse("core:recherche_ouvrages_workflow_documentation"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Recherche rapide des ouvrages")
        self.assertContains(response, "Filtres géographiques en cascade")
        self.assertContains(response, "Rapport d’exécution automatisée")


class OuvrageFutureManagementScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username="future-management-admin",
            email="future-management@example.com",
            password="secret123",
        )
        cls.ouvrage_type = TypeOuvrage.objects.create(
            nom_type_ouvrage="AEPG test modalite future"
        )
        cls.gestionnaire = Organisation.objects.create(
            nom_organisation="Gestionnaire modalite future test",
            type_organisation=Organisation.TYPE_GESTIONNAIRE,
        )

    def _create_ouvrage_with_management(self, name, *, start, end, status):
        ouvrage = Ouvrage.objects.create(
            nom_ouvrage=name,
            type_ouvrage=self.ouvrage_type,
        )
        ModaliteGestion.objects.create(
            ouvrage=ouvrage,
            type_gestion="privee",
            gestionnaire=self.gestionnaire,
            date_debut=start,
            date_fin=end,
            statut=status,
        )
        return ouvrage

    def test_future_fixed_term_management_keeps_ouvrage_accessible(self):
        """Une modalite future avec date de fin reste visible aux interventions."""
        today = timezone.localdate()
        ouvrage = self._create_ouvrage_with_management(
            "Ouvrage contrat futur",
            start=today + timedelta(days=30),
            end=today + timedelta(days=395),
            status="actif",
        )

        self.assertTrue(_accessible_ouvrages(self.user).filter(pk=ouvrage.pk).exists())

    def test_expired_management_keeps_ouvrage_outside_scope(self):
        today = timezone.localdate()
        ouvrage = self._create_ouvrage_with_management(
            "Ouvrage contrat expire",
            start=today - timedelta(days=395),
            end=today - timedelta(days=30),
            status="resilie",
        )

        self.assertFalse(_accessible_ouvrages(self.user).filter(pk=ouvrage.pk).exists())

    def test_history_includes_repair_without_planning_detail(self):
        ouvrage = Ouvrage.objects.create(
            nom_ouvrage="Ouvrage reparation sans piece",
            type_ouvrage=self.ouvrage_type,
        )
        activity_type = TypeActivite.objects.create(nomtype="Reparation")
        fiche = FichePoste.objects.create(
            type_activites=activity_type,
            tache="Reparation panne",
            description="Reparation avec photos, sans piece utilisee",
            dans_planning=True,
        )
        planning = Planning.objects.create(
            ouvrage=ouvrage,
            fiche_poste=fiche,
            type_activite=activity_type,
            date=timezone.now(),
            statut="en_cours",
            photo='[{"type":"image/jpeg","data":"data:image/jpeg;base64,YQ=="}]',
        )

        history = _get_ouvrage_repair_plannings(ouvrage, [fiche.id], [])

        self.assertTrue(history.filter(pk=planning.pk).exists())
        self.assertFalse(planning.details.exists())

    def test_history_keeps_photo_intervention_outside_strict_repair_catalogue(self):
        ouvrage = Ouvrage.objects.create(
            nom_ouvrage="Ouvrage intervention photo catalogue elargi",
            type_ouvrage=self.ouvrage_type,
        )
        activity_type = TypeActivite.objects.create(nomtype="Entretien terrain")
        fiche = FichePoste.objects.create(
            type_activites=activity_type,
            tache="Nettoyage des citernes et boites",
            description="Activite permise par le formulaire photographique",
            dans_planning=True,
        )
        planning = Planning.objects.create(
            ouvrage=ouvrage,
            fiche_poste=fiche,
            type_activite=activity_type,
            date=timezone.now(),
            statut="en_cours",
            remarque="[Saisie depuis la fiche ouvrage] Equipement: citerne",
            photo='[{"type":"image/jpeg","data":"data:image/jpeg;base64,YQ=="}]',
        )

        history = _get_ouvrage_repair_plannings(ouvrage, [], [])

        self.assertTrue(history.filter(pk=planning.pk).exists())

        quick_history = _historique_interventions(ouvrage)
        self.assertEqual([item["id"] for item in quick_history], [str(planning.id)])
