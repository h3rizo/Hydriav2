import os
import sys

# Setup Django environment
sys.path.append('/home/soakoja/hydria/backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')

import django
django.setup()

from apps.accounting.models import BaseDiameX

def verify():
    entry = BaseDiameX.objects.filter(fichier_source='TEST_DIAG_3.accde').first()
    if entry:
        print(f"SUCCESS: Entry found for TEST_DIAG_3.accde")
        if entry.imported_by:
            print(f"SUCCESS: Imported by: {entry.imported_by.surnom} (ID: {entry.imported_by.id})")
        else:
            print("FAILURE: Imported by is NULL")
    else:
        print("FAILURE: No entry found for TEST_DIAG_3.accde")

if __name__ == "__main__":
    verify()
