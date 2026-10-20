from types import SimpleNamespace
from uuid import uuid4

from django.test import SimpleTestCase

from .views_gps_quality import (
    _current_review, _entry, _haversine_km, _threshold,
    _valid_coordinates, _village_location_label,
)


class GPSQualityCalculationTests(SimpleTestCase):
    def test_threshold_accepts_only_two_or_three_kilometres(self):
        self.assertEqual(_threshold(SimpleNamespace(GET={'threshold': '2'})), 2.0)
        self.assertEqual(_threshold(SimpleNamespace(GET={'threshold': '3'})), 3.0)
        self.assertEqual(_threshold(SimpleNamespace(GET={'threshold': 'invalid'})), 3.0)

    def test_homonymous_village_label_contains_its_hierarchy(self):
        district = SimpleNamespace(nom_district='District A')
        commune = SimpleNamespace(nom_commune='Commune A', district=district)
        fokontany = SimpleNamespace(nom_fokontany='Fokontany A', commune=commune)
        village = SimpleNamespace(nom_village='Ambodivoanio', fokontany=fokontany)
        self.assertEqual(
            _village_location_label(village),
            'Ambodivoanio · Fokontany A · Commune A · District A',
        )

    def test_haversine_uses_kilometres(self):
        self.assertAlmostEqual(_haversine_km(0, 0, 1, 0), 111.195, places=2)

    def test_zero_pair_and_out_of_range_coordinates_are_invalid(self):
        self.assertFalse(_valid_coordinates(0, 0))
        self.assertFalse(_valid_coordinates(-91, 47))
        self.assertFalse(_valid_coordinates(-18, 181))
        self.assertTrue(_valid_coordinates(-18.9, 47.5))

    def test_review_becomes_stale_when_entity_coordinates_change(self):
        review = SimpleNamespace(latitude_snapshot=-18.9, longitude_snapshot=47.5)
        self.assertIs(review, _current_review(review, -18.9, 47.5))
        self.assertIsNone(_current_review(review, -18.8, 47.5))

    def test_distant_point_is_anomaly_until_explained(self):
        ouvrage_id = uuid4()
        point = SimpleNamespace(
            id=uuid4(), ouvrage_id=ouvrage_id,
            ouvrage=SimpleNamespace(nom_ouvrage='Test'),
            nomabonne='Borne test', code_point_eau='PE-1',
            type_point_eau=SimpleNamespace(nom_type='BF'),
            latitude=-18.9, longitude=47.5,
        )
        village = SimpleNamespace(
            id=uuid4(), nom_village='Village test',
            latitude=-18.8, longitude=47.5,
        )
        anomaly = _entry('point_eau', point, [village], 3, None)
        self.assertEqual(anomaly['status'], 'anomaly')
        review = SimpleNamespace(
            latitude_snapshot=-18.9, longitude_snapshot=47.5,
            status='confirmed',
        )
        confirmed = _entry('point_eau', point, [village], 3, review)
        self.assertEqual(confirmed['status'], 'confirmed')
