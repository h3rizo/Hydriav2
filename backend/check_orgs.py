import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hydria.settings")
django.setup()

from apps.organization.models import Organisation

count = Organisation.objects.count()
print(f"Organisation count: {count}")

if count > 0:
    for org in Organisation.objects.all():
        print(f"- {org.nom_organisation} (ID: {org.id})")
else:
    print("No organizations found.")
