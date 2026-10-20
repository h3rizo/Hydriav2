import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.navigation_terrain.models import GeoPositionAudit, Repere, TypeRepere


class NavigationMobileApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='terrain-test', password='test')
        self.client.force_login(self.user)
        self.type_repere = TypeRepere.objects.create(nom='Pont test', icone='pont', couleur='#58D594')
        self.scope = patch('apps.navigation_terrain.views._scope', return_value=(None, set()))
        self.scope.start()
        self.addCleanup(self.scope.stop)

    def repere_payload(self, repere_id):
        return {
            'id': str(repere_id), 'local_uuid': str(repere_id), 'nom': 'Pont terrain',
            'type_repere_id': 'pont', 'latitude': '-18.9000000', 'longitude': '47.5000000',
            'altitude': '1250.25', 'accuracy_m': '8.5', 'capture_method': 'gps',
            'captured_at': '2026-08-28T17:15:00+03:00',
        }

    def test_config_requires_authentication(self):
        self.client.logout()
        response = self.client.get(reverse('navigation_terrain:mobile_config'))
        self.assertEqual(response.status_code, 401)

    def test_landmark_uuid_is_idempotent(self):
        repere_id = uuid.uuid4()
        url = reverse('navigation_terrain:mobile_repere_upsert')
        first = self.client.post(url, self.repere_payload(repere_id))
        second = self.client.post(url, self.repere_payload(repere_id))
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()['duplicate_prevented'])
        self.assertEqual(Repere.objects.get(id=repere_id).version, 1)

    def test_landmark_version_conflict_returns_409(self):
        repere_id = uuid.uuid4()
        url = reverse('navigation_terrain:mobile_repere_upsert')
        self.client.post(url, self.repere_payload(repere_id))
        repere = Repere.objects.get(id=repere_id)
        repere.version = 2
        repere.save(update_fields=['version'])
        payload = self.repere_payload(repere_id)
        payload.update({'base_version': '1', 'latitude': '-18.8000000'})
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 409)
        self.assertTrue(response.json()['conflict'])

    def test_position_retry_creates_one_audit(self):
        repere = Repere.objects.create(
            nom='Départ', type_repere=self.type_repere, latitude='-18.9', longitude='47.5',
            capture_method='gps', captured_at=timezone.now(), createur=self.user,
        )
        local_uuid = uuid.uuid4()
        payload = {
            'local_uuid': str(local_uuid), 'entity_kind': 'landmark', 'entity_id': str(repere.id),
            'latitude': '-18.8000000', 'longitude': '47.6000000', 'accuracy_m': '9.0',
            'capture_method': 'gps', 'captured_at': '2026-08-28T17:15:00+03:00',
        }
        url = reverse('navigation_terrain:mobile_position_upsert')
        first = self.client.post(url, payload)
        second = self.client.post(url, payload)
        self.assertEqual(first.status_code, 200)
        self.assertTrue(second.json()['duplicate_prevented'])
        self.assertEqual(GeoPositionAudit.objects.filter(local_uuid=local_uuid).count(), 1)
