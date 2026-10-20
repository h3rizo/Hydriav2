import os
import django
from django.db.models import Count

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hydria.settings")
django.setup()

from apps.organization.models import Organisation

try:
    organisations = Organisation.objects.annotate(
        bases_count=Count('bases', distinct=True),
        comptes_count=Count('comptes', distinct=True),
        postes_count=Count('postes', distinct=True)
    ).order_by('nom_organisation')

    print(f"Query executed successfully. Count: {organisations.count()}")
    for org in organisations:
        print(f"- {org.nom_organisation}: Bases={org.bases_count}, Comptes={org.comptes_count}, Postes={org.postes_count}")

except Exception as e:
    print(f"Error executing query: {e}")
