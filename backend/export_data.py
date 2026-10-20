import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
django.setup()

from django.core.management import call_command

# Liste des apps à exporter
apps_to_export = [
    'geography',
    'organization', 
    'employees',
    'billing',
    'planning',
    'inventory',
    'inspections',
    'accounting',
    'chatbot',
    'feed',
    'core',
    'ouvrages',
]

print("Export des donnees...")
for app in apps_to_export:
    try:
        output_file = f'{app}_data.json'
        print(f"Export de {app}...")
        with open(output_file, 'w', encoding='utf-8') as f:
            call_command('dumpdata', app, indent=2, stdout=f)
        
        # Vérifier la taille
        size = os.path.getsize(output_file)
        print(f"  OK {output_file} ({size} bytes)")
    except Exception as e:
        print(f"  ERREUR pour {app}: {e}")

print("\nTermine!")
