import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from apps.organization.forms import BaseForm
print("BaseForm fields:", BaseForm.Meta.fields)
print("\nTest successful!")
