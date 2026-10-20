import json
import uuid
from datetime import timedelta
from unittest.mock import patch
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.core.models import MobileRefreshToken, WidgetAuthToken
from apps.core.mobile_api_v1 import _is_maintenance_activity


class MobileApiV1AuthenticationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='logistique-mobile',
            password='mot-de-passe-solide',
            is_active=True,
        )
        self.device_id = str(uuid.uuid4())

    def post_json(self, path, payload):
        return self.client.post(path, data=json.dumps(payload), content_type='application/json')

    @patch('apps.core.mobile_api_v1._get_inventory_scope', return_value='base')
    def test_login_creates_short_access_and_refresh_tokens(self, _scope):
        response = self.post_json('/api/mobile/v1/auth/login', {
            'username': self.user.username,
            'password': 'mot-de-passe-solide',
            'device_id': self.device_id,
            'device_label': 'Test Android',
        })

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['token_type'], 'Bearer')
        self.assertEqual(payload['expires_in'], 900)
        access = WidgetAuthToken.objects.get(key=payload['access_token'])
        refresh = MobileRefreshToken.objects.get(key=payload['refresh_token'])
        self.assertEqual(access.scope, WidgetAuthToken.SCOPE_MOBILE)
        self.assertGreater(access.expires_at, timezone.now())
        self.assertEqual(str(refresh.device_id), self.device_id)

    @patch('apps.core.mobile_api_v1._get_inventory_scope', return_value='none')
    def test_login_refuses_user_without_logistics_scope(self, _scope):
        response = self.post_json('/api/mobile/v1/auth/login', {
            'username': self.user.username,
            'password': 'mot-de-passe-solide',
            'device_id': self.device_id,
        })
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['code'], 'NO_LOGISTICS_SCOPE')

    @patch('apps.core.mobile_api_v1._get_inventory_scope', return_value='base')
    def test_refresh_is_rotated_and_cannot_be_reused(self, _scope):
        login = self.post_json('/api/mobile/v1/auth/login', {
            'username': self.user.username,
            'password': 'mot-de-passe-solide',
            'device_id': self.device_id,
        }).json()

        first = self.post_json('/api/mobile/v1/auth/refresh', {'refresh_token': login['refresh_token']})
        replay = self.post_json('/api/mobile/v1/auth/refresh', {'refresh_token': login['refresh_token']})

        self.assertEqual(first.status_code, 200)
        self.assertNotEqual(first.json()['refresh_token'], login['refresh_token'])
        self.assertEqual(replay.status_code, 401)

    def test_expired_access_token_is_rejected(self):
        token = WidgetAuthToken.objects.create(
            user=self.user,
            scope=WidgetAuthToken.SCOPE_MOBILE,
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        response = self.client.get(
            '/api/mobile/v1/me',
            HTTP_AUTHORIZATION=f'Bearer {token.key}',
        )
        self.assertEqual(response.status_code, 401)

    @patch('apps.core.mobile_api_v1._get_inventory_scope', return_value='base')
    def test_me_accepts_bearer_mobile_token(self, _scope):
        token = WidgetAuthToken.objects.create(
            user=self.user,
            scope=WidgetAuthToken.SCOPE_MOBILE,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        response = self.client.get(
            '/api/mobile/v1/me',
            HTTP_AUTHORIZATION=f'Bearer {token.key}',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['user']['username'], self.user.username)


class MobileApiV1ActivityClassificationTests(TestCase):
    def planning(self, type_name, task=''):
        activity_type = SimpleNamespace(nomtype=type_name)
        fiche = SimpleNamespace(type_activites=activity_type, tache=task)
        return SimpleNamespace(fiche_poste=fiche, type_activite=None)

    def test_entretien_is_maintenance(self):
        self.assertTrue(_is_maintenance_activity(self.planning('Entretien')))

    def test_reparation_is_not_maintenance(self):
        self.assertFalse(_is_maintenance_activity(self.planning('Réparation')))

    def test_maintenance_keyword_in_task_is_detected(self):
        self.assertTrue(_is_maintenance_activity(self.planning('Travaux', 'Maintenance pompe')))
