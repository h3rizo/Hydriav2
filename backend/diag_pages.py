from django.test import Client
from django.contrib.auth import get_user_model
import traceback

User = get_user_model()
u = User.objects.filter(is_superuser=True).first()
print('user:', u)

c = Client(SERVER_NAME='hydria.mg')
c.force_login(u)

for url in [
    '/organisations/ouvrages/',
    '/rapports/analyse-villages-desserte/',
    '/chantiers/demandes/',
    '/chantiers/workflows/',
]:
    print('=' * 60)
    print('URL:', url)
    try:
        r = c.get(url)
        print('STATUS:', r.status_code)
    except Exception:
        print('EXCEPTION:')
        traceback.print_exc()
