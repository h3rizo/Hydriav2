import os
import django
import sys

sys.path.append('/home/soakoja/hydria/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.organization.models import Compte

# List of accounts to update
counts = Compte.objects.filter(compte__startswith='6251')
charte = 'indemnite_terrain'

for c in counts:
    c.charte_verification = charte
    c.save()
    print(f"Compte {c.compte} ({c.nom_compte}) mis à jour avec charte '{charte}'.")
