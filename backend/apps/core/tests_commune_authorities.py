from django.test import TestCase

from apps.geography.models import Commune, District, Fokontany, Region
from apps.usagers.models_reunions import Autorite

from .views import _get_commune_authorities


class CommuneAuthoritiesScopeTests(TestCase):
    def setUp(self):
        self.region = Region.objects.create(nom_region='Region test')
        self.district = District.objects.create(
            nom_district='District test',
            region=self.region,
        )
        self.commune = Commune.objects.create(
            nom_commune='Commune choisie',
            district=self.district,
        )
        self.other_commune = Commune.objects.create(
            nom_commune='Autre commune',
            district=self.district,
        )
        self.fokontany = Fokontany.objects.create(
            nom_fokontany='Fokontany choisi',
            commune=self.commune,
        )
        self.other_fokontany = Fokontany.objects.create(
            nom_fokontany='Autre fokontany',
            commune=self.other_commune,
        )

    def test_only_authorities_from_selected_commune_branch_are_returned(self):
        Autorite.objects.create(nom='Autorite regionale', region=self.region)
        Autorite.objects.create(
            nom='Autorite communale',
            region=self.region,
            district=self.district,
            commune=self.commune,
        )
        Autorite.objects.create(
            nom='Autorite fokontany',
            region=self.region,
            district=self.district,
            commune=self.commune,
            fokontany=self.fokontany,
        )
        Autorite.objects.create(
            nom='Autorite autre commune',
            region=self.region,
            district=self.district,
            commune=self.other_commune,
        )
        Autorite.objects.create(
            nom='Autorite autre fokontany',
            region=self.region,
            district=self.district,
            commune=self.other_commune,
            fokontany=self.other_fokontany,
        )

        groups = _get_commune_authorities(self.commune)

        self.assertEqual(
            {authority.nom for authority in groups['region']},
            {'Autorite regionale'},
        )
        self.assertEqual(
            {authority.nom for authority in groups['commune']},
            {'Autorite communale'},
        )
        self.assertEqual(
            {authority.nom for authority in groups['fokontany']},
            {'Autorite fokontany'},
        )
        all_names = {
            authority.nom
            for authorities in groups.values()
            for authority in authorities
        }
        self.assertNotIn('Autorite autre commune', all_names)
        self.assertNotIn('Autorite autre fokontany', all_names)
