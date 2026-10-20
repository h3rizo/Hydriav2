import io

import openpyxl
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.geography.models import Region

from .models import ParticipantAttendu, ParticipantReunion, Reunion


class ExportReunionsExcelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='export-reunions-test',
            password='test-password',
        )
        self.client.force_login(self.user)
        self.region = Region.objects.create(nom_region='Region export test')
        self.reunion = Reunion.objects.create(
            region=self.region,
            objet='Reunion test export',
        )

        ParticipantReunion.objects.create(
            reunion=self.reunion,
            type_participant=ParticipantReunion.TYPE_REPRESENTANT,
            nom_libre='Representant present',
            present=True,
        )
        ParticipantReunion.objects.create(
            reunion=self.reunion,
            type_participant=ParticipantReunion.TYPE_EMPLOYE,
            nom_libre='Employe absent',
            present=False,
        )
        ParticipantReunion.objects.create(
            reunion=self.reunion,
            type_participant=ParticipantReunion.TYPE_AUTORITE,
            nom_libre='Autorite presente',
            present=True,
        )

        ParticipantAttendu.objects.create(
            reunion=self.reunion,
            type_participant=ParticipantReunion.TYPE_REPRESENTANT,
            nombre_attendu=3,
        )
        ParticipantAttendu.objects.create(
            reunion=self.reunion,
            type_participant=ParticipantReunion.TYPE_EMPLOYE,
            nombre_attendu=2,
        )

    def test_export_separates_present_and_expected_counts_by_participant_type(self):
        response = self.client.get(
            reverse('usagers:export_reunions_excel'),
            {'ids': str(self.reunion.id)},
        )

        self.assertEqual(response.status_code, 200)
        workbook = openpyxl.load_workbook(io.BytesIO(response.content), data_only=True)
        sheet = workbook['Reunions']
        headers = [cell.value for cell in sheet[1]]
        row = {headers[index]: cell.value for index, cell in enumerate(sheet[2])}

        self.assertEqual(row['Total presents'], 2)
        self.assertEqual(row['Presents - Representants des usagers'], 1)
        self.assertEqual(row['Presents - Employes'], 0)
        self.assertEqual(row['Presents - Autorites'], 1)
        self.assertEqual(row['Total attendus'], 5)
        self.assertEqual(row['Attendus - Representants des usagers'], 3)
        self.assertEqual(row['Attendus - Employes'], 2)

        recap = workbook['Recap par region']
        recap_headers = [cell.value for cell in recap[1]]
        recap_row = {
            recap_headers[index]: cell.value
            for index, cell in enumerate(recap[2])
        }
        self.assertEqual(recap_row['Total presents'], 2)
        self.assertEqual(recap_row['Presents - Employes'], 0)
        self.assertEqual(recap_row['Total attendus'], 5)
        self.assertEqual(recap_row['Attendus - Employes'], 2)
