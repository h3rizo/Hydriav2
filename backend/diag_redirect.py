from django.test import Client
from django.contrib.auth import get_user_model

User = get_user_model()
u = User.objects.filter(is_superuser=True).first()
print('user:', u, 'is_active:', getattr(u, 'is_active', None))
print('has employe attr:', hasattr(u, 'employe'), getattr(u, 'employe', None))

c = Client(SERVER_NAME='hydria.mg')
logged_in = c.login(username=u.username, password=None) if False else None
c.force_login(u)

for path in [
    '/organisations/ouvrages/',
    '/rapports/analyse-villages-desserte/',
    '/rapports/analyse-villages-desserte/json/?region=&fokontany=',
    '/chantiers/demandes/',
]:
    r = c.get(path)
    print('=' * 60)
    print('URL:', path)
    print('STATUS:', r.status_code, 'Location:', r.get('Location'))
