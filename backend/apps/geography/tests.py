import json

from django.test import TestCase
from django.urls import reverse

from apps.usagers.models_reunions import Autorite

from .models import Commune, District, Fokontany, Region, Village


class RegionsApiTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(nom_region='Region avec autorites')
        self.district = District.objects.create(nom_district='District test', region=self.region)
        self.commune = Commune.objects.create(nom_commune='Commune test', district=self.district)
        self.fokontany = Fokontany.objects.create(nom_fokontany='Fokontany test', commune=self.commune)
        Autorite.objects.create(
            nom='Chef de region',
            type_autorite=Autorite.TYPE_CHEF_REGION,
            region=self.region,
        )
        Autorite.objects.create(nom='Chef de district', district=self.district)
        Autorite.objects.create(nom='Maire', commune=self.commune)
        # Les fiches reelles peuvent conserver toute la chaine geographique.
        # Le fokontany doit rester le seul rattachement direct de reference.
        Autorite.objects.create(
            nom='Chef de fokontany',
            region=self.region,
            district=self.district,
            commune=self.commune,
            fokontany=self.fokontany,
        )
        sibling_commune = Commune.objects.create(
            nom_commune='Commune voisine',
            district=self.district,
        )
        Autorite.objects.create(
            nom='Maire commune voisine',
            region=self.region,
            district=self.district,
            commune=sibling_commune,
        )

        other_region = Region.objects.create(nom_region='Autre region')
        Autorite.objects.create(nom='Autorite hors perimetre', region=other_region)

    def test_api_separates_direct_and_indirect_region_authorities(self):
        response = self.client.get(reverse('geography:api_regions'))

        self.assertEqual(response.status_code, 200)
        region_data = next(
            item for item in response.json() if item['id'] == str(self.region.id)
        )
        self.assertEqual(region_data['districts_count'], 1)
        self.assertEqual(region_data['autorites_directes_count'], 1)
        self.assertEqual(region_data['autorites_indirectes_count'], 4)

    def test_commune_counts_parent_and_child_authorities_as_indirect(self):
        response = self.client.get(
            reverse('geography:api_communes', args=[self.district.id])
        )

        self.assertEqual(response.status_code, 200)
        commune_data = response.json()[0]
        self.assertEqual(commune_data['autorites_directes_count'], 1)
        self.assertEqual(commune_data['autorites_indirectes_count'], 3)

    def test_authorities_modal_groups_results_and_exposes_attachment(self):
        response = self.client.get(
            reverse(
                'geography:api_autorites_zone',
                args=['commune', self.commune.id],
            )
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['direct_total'], 1)
        self.assertEqual(data['indirect_total'], 3)
        self.assertEqual(data['direct_results'][0]['nom'], 'Maire')
        attachment_types = {
            item['rattachement_type'] for item in data['indirect_results']
        }
        self.assertEqual(attachment_types, {'Region', 'District', 'Fokontany'})
        self.assertNotIn(
            'Autorite hors perimetre',
            {item['nom'] for item in data['results']},
        )
        self.assertNotIn(
            'Maire commune voisine',
            {item['nom'] for item in data['results']},
        )

    def test_most_specific_attachment_is_the_only_direct_level(self):
        region_response = self.client.get(
            reverse(
                'geography:api_autorites_zone',
                args=['region', self.region.id],
            )
        ).json()
        fokontany_response = self.client.get(
            reverse(
                'geography:api_autorites_zone',
                args=['fokontany', self.fokontany.id],
            )
        ).json()

        region_direct_names = {
            item['nom'] for item in region_response['direct_results']
        }
        region_indirect_names = {
            item['nom'] for item in region_response['indirect_results']
        }
        fokontany_direct_names = {
            item['nom'] for item in fokontany_response['direct_results']
        }

        self.assertNotIn('Chef de fokontany', region_direct_names)
        self.assertIn('Chef de fokontany', region_indirect_names)
        self.assertIn('Chef de fokontany', fokontany_direct_names)


class VillageFokontanyUpdateTests(TestCase):
    def setUp(self):
        region = Region.objects.create(nom_region='Region test')
        district = District.objects.create(nom_district='District test', region=region)
        self.commune = Commune.objects.create(nom_commune='Commune A', district=district)
        self.other_commune = Commune.objects.create(nom_commune='Commune B', district=district)
        self.fokontany_a = Fokontany.objects.create(nom_fokontany='Fokontany A', commune=self.commune)
        self.fokontany_b = Fokontany.objects.create(nom_fokontany='Fokontany B', commune=self.commune)
        self.foreign_fokontany = Fokontany.objects.create(
            nom_fokontany='Fokontany hors commune',
            commune=self.other_commune,
        )
        self.village = Village.objects.create(nom_village='Village test', fokontany=self.fokontany_a)

    def _update_village(self, fokontany):
        return self.client.post(
            reverse('geography:api_update'),
            data=json.dumps({
                'type': 'village',
                'id': str(self.village.id),
                'name': self.village.nom_village,
                'fokontany_id': str(fokontany.id),
            }),
            content_type='application/json',
        )

    def test_can_move_village_to_fokontany_in_same_commune(self):
        response = self._update_village(self.fokontany_b)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        self.village.refresh_from_db()
        self.assertEqual(self.village.fokontany_id, self.fokontany_b.id)

    def test_rejects_fokontany_from_another_commune(self):
        response = self._update_village(self.foreign_fokontany)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['success'])
        self.village.refresh_from_db()
        self.assertEqual(self.village.fokontany_id, self.fokontany_a.id)

    def test_village_detail_exposes_commune_and_fokontany(self):
        response = self.client.get(
            reverse('geography:api_village_detail', args=[self.village.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['commune_id'], str(self.commune.id))
        self.assertEqual(response.json()['fokontany_id'], str(self.fokontany_a.id))
