from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.employees.models import Employe, Poste
from apps.geography.models import Commune, District, Fokontany, Region, Village
from apps.organization.models import Base, Organisation

from .models import Autorite, RepresentantUsager, TiersParticipant, TypeAutorite


class ParticipantAutocompleteDetailsTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(
            username='autocomplete-participants-test',
            password='test-password',
        )
        self.client.force_login(user)

        self.region = Region.objects.create(nom_region='Atsinanana')
        self.district = District.objects.create(
            nom_district='Toamasina',
            region=self.region,
        )
        self.commune = Commune.objects.create(
            nom_commune='Ambodimanga',
            district=self.district,
        )
        self.fokontany = Fokontany.objects.create(
            nom_fokontany='Centre',
            commune=self.commune,
        )
        village = Village.objects.create(
            nom_village='Vohitra',
            fokontany=self.fokontany,
        )
        RepresentantUsager.objects.create(
            nom='Rasoa Representante',
            village=village,
        )

        TypeAutorite.objects.create(slug='maire-test', nom='Maire')
        Autorite.objects.create(
            nom='Rakoto Autorite',
            type_autorite='maire-test',
            region=self.region,
            district=self.district,
            commune=self.commune,
        )

        organisation = Organisation.objects.create(nom_organisation='Organisation test')
        base = Base.objects.create(nom_base='Toamasina', organisation=organisation)
        poste = Poste.objects.create(nom_poste='Animateur', organisation=organisation)
        Employe.objects.create(
            nom_employe='Jean Employe',
            nom='Employe',
            prenom='Jean',
            surnom='Jean',
            poste=poste,
            base=base,
        )

        TiersParticipant.objects.create(
            nom='Paul Tiers',
            fonction='President association',
        )

    def _search(self, participant_type, search):
        response = self.client.get(
            reverse('usagers:reunion_participant_search'),
            {
                'type': participant_type,
                'search': search,
                'commune_id': str(self.commune.id),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        return response.json()['results'][0]

    def test_representative_detail_contains_village_and_commune(self):
        result = self._search('representant', 'Rasoa')
        self.assertEqual(result['label'], 'Rasoa Representante')
        self.assertEqual(result['detail'], 'Vohitra - Ambodimanga')

    def test_authority_detail_contains_type_and_most_specific_attachment(self):
        result = self._search('autorite', 'Rakoto')
        self.assertEqual(result['label'], 'Rakoto Autorite')
        self.assertEqual(result['detail'], 'Maire - Commune Ambodimanga')

    def test_employee_detail_contains_position_and_base(self):
        result = self._search('employe', 'Jean')
        self.assertEqual(result['label'], 'Jean')
        self.assertEqual(result['detail'], 'Animateur - Toamasina')

    def test_third_party_detail_contains_function(self):
        result = self._search('tiers', 'Paul')
        self.assertEqual(result['label'], 'Paul Tiers')
        self.assertEqual(result['detail'], 'President association')
