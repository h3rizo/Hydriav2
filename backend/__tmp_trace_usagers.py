from django.test import RequestFactory
from apps.usagers import views
import traceback

class DummyUser:
    is_authenticated = True
    is_staff = True
    is_superuser = True
    is_active = True
    client = None
    username = 'dummy'
    first_name = 'Dummy'
    last_name = 'User'
    email = 'dummy@example.com'

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

class DummyQS:
    def order_by(self, *args, **kwargs):
        return []

class DummyMgr:
    def filter(self, *args, **kwargs):
        return DummyQS()

class DummyEmploye:
    objects = DummyMgr()

old = views.Employe
views.Employe = DummyEmploye

req = RequestFactory().get('/usagers/representants/')
req.user = DummyUser()

try:
    resp = views.representants_list.__wrapped__(req)
    print('resp_type', type(resp))
    print('resp_status', getattr(resp, 'status_code', None))
except Exception:
    traceback.print_exc()
finally:
    views.Employe = old
